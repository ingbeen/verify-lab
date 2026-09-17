"""만기 매매 성적표의 구간 축 계약을 고정한다.

**균등 2분할만으로는 신호가 식는 것을 놓친다.** 실물 사례가 DIA 6월이다 — 2분할에서는
앞 92.9% / 뒤 60.0% 로 살아 있어 보였는데 최근 5년만 보면 2/6 이었다. 그래서 최근 구간을
함께 낸다 (루트 `CLAUDE.md` 측정의 원칙 17).

핵심 계약은 다섯이다.
- 칸마다 **다섯 구간**이 나온다 (전체·앞 절반·뒤 절반·최근 10년·최근 5년)
- **앞 절반 + 뒤 절반 = 전체** (표본 보존)
- **표본이 0건인 구간도 행이 남는다** — 행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다
- **표본 10건 미만이면 `판정가능` 이 아니오** — 판정에 쓰지 말라는 표시다
- **최근 N년의 기준일은 데이터 마지막 거래일**이다 — 실행 시각에 묶이면 재현되지 않는다
- **보유 중 최악은 그 구간의 최솟값**이고 결과 최악보다 나쁘거나 같다
"""

import pandas as pd
import pytest

from verify_lab.execution.constants import (
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_WORST_HOLD,
    EXIT_INTRADAY_STOP,
    EXIT_LIMIT,
    PERIOD_ALL,
    PERIOD_RECENT_5Y,
    PERIODS,
)
from verify_lab.execution.periods import period_rows
from verify_lab.measure.constants import (
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_SAMPLE_PER_CELL,
    PERIOD_FIRST_HALF,
    PERIOD_SECOND_HALF,
)
from verify_lab.report.constants import DISPLAY_JUDGEABLE, DISPLAY_MIN, DISPLAY_PERIOD, DISPLAY_SIGNAL_COUNT

# 백분율 지표 비교 허용오차 (tests/CLAUDE.md)
PERCENT_TOLERANCE = 0.1


def _dates(years: list[int]) -> pd.DatetimeIndex:
    """해마다 9월 셋째 금요일 근처의 진입일 하나씩 만든다.

    Args:
        years: 진입 연도 목록

    Returns:
        진입일 인덱스
    """
    return pd.DatetimeIndex([pd.Timestamp(f"{year}-09-15") for year in years])


def _returns(count: int) -> list[float]:
    """부호가 섞인 수익률을 만든다.

    Args:
        count: 개수

    Returns:
        수익률 목록 (비율)
    """
    return [0.01 if index % 3 else -0.02 for index in range(count)]


class TestPeriodSchema:
    """구간 축의 모양 계약"""

    def test_칸마다_다섯_구간이_나온다(self) -> None:
        """
        목적: 구간 목록이 계약임을 고정한다

        Given: 20해치 진입
        When: 구간별로 나누면
        Then: 다섯 행이며 순서가 `PERIODS` 와 같다
        """
        # Given
        years = list(range(2006, 2026))

        # When
        rows = period_rows(_dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True)

        # Then
        assert [row[DISPLAY_PERIOD] for row in rows] == list(PERIODS)

    def test_구간_목록에_최근_5년이_있다(self) -> None:
        """
        목적: 최근 5년이 빠지지 않는지 고정한다 (DIA 6월이 여기서 드러났다)

        Given: 구간 상수
        When: 목록을 보면
        Then: 최근 5년이 들어 있다
        """
        assert PERIOD_RECENT_5Y in PERIODS


class TestSampleConservation:
    """표본 보존 — 절반끼리 더하면 전체다"""

    def test_앞_절반과_뒤_절반의_합이_전체다(self) -> None:
        """
        목적: 표본이 조용히 사라지지 않는지 고정한다

        Given: 23해치 진입 (홀수)
        When: 구간별로 나누면
        Then: 앞 + 뒤 = 전체
        """
        # Given
        years = list(range(2003, 2026))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row[DISPLAY_SIGNAL_COUNT]
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_FIRST_HALF] + rows[PERIOD_SECOND_HALF] == rows[PERIOD_ALL]
        assert rows[PERIOD_ALL] == len(years)

    def test_홀수면_뒤_절반이_하나_많다(self) -> None:
        """
        목적: 분할 규칙을 고정한다 (어느 쪽이 많은지가 정책이다)

        Given: 23해치 진입
        When: 구간별로 나누면
        Then: 앞 11 · 뒤 12
        """
        # Given
        years = list(range(2003, 2026))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row[DISPLAY_SIGNAL_COUNT]
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_FIRST_HALF] == 11
        assert rows[PERIOD_SECOND_HALF] == 12


class TestEmptyPeriod:
    """표본이 없는 구간도 행이 남는다"""

    def test_최근_5년에_진입이_없어도_행이_남는다(self) -> None:
        """
        목적: **행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다**

        Given: 진입이 전부 2010년 이전인 시세
        When: 구간별로 나누면
        Then: 최근 5년 행이 **있고** 신호가 0이다
        """
        # Given
        years = list(range(2000, 2011))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert PERIOD_RECENT_5Y in rows
        assert rows[PERIOD_RECENT_5Y][DISPLAY_SIGNAL_COUNT] == 0

    def test_표본이_0건이면_판정가능이_아니오다(self) -> None:
        """
        목적: 빈 구간을 판정에 쓰지 말라는 표시를 고정한다 (엣지 케이스)

        Given: 진입이 전부 2010년 이전인 시세
        When: 구간별로 나누면
        Then: 최근 5년의 판정가능이 아니오다
        """
        # Given
        years = list(range(2000, 2011))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_RECENT_5Y][DISPLAY_JUDGEABLE] == JUDGEABLE_NO


class TestJudgeable:
    """판정가능 표시 — 표본 하한(원칙 12의 10건)"""

    def test_표본이_하한_이상이면_예다(self) -> None:
        """
        목적: 하한 경계를 고정한다

        Given: 하한과 정확히 같은 표본
        When: 구간별로 나누면
        Then: 전체 행의 판정가능이 예다
        """
        # Given
        years = list(range(2016, 2016 + MIN_SAMPLE_PER_CELL))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_ALL][DISPLAY_JUDGEABLE] == JUDGEABLE_YES

    def test_표본이_하한_미만이면_아니오다(self) -> None:
        """
        목적: 하한 바로 아래를 고정한다 (엣지 케이스)

        Given: 하한보다 하나 적은 표본
        When: 구간별로 나누면
        Then: 전체 행의 판정가능이 아니오다
        """
        # Given
        years = list(range(2017, 2017 + MIN_SAMPLE_PER_CELL - 1))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_ALL][DISPLAY_JUDGEABLE] == JUDGEABLE_NO


class TestRecentBoundary:
    """최근 N년의 기준일 — 실행 시각이 아니라 데이터 마지막 거래일"""

    def test_기준일이_데이터_마지막_거래일이다(self) -> None:
        """
        목적: **같은 데이터면 언제 돌려도 같은 결과**임을 고정한다

        실행 시각을 기준으로 삼으면 코드를 안 고쳐도 날짜가 지나면 결과가 바뀐다.
        재현이 이 프로젝트의 존재 이유다.

        Given: 같은 진입 목록과 서로 다른 마지막 거래일
        When: 구간별로 나누면
        Then: 최근 5년의 표본 수가 달라진다
        """
        # Given
        years = list(range(2006, 2026))
        entries, returns = _dates(years), _returns(len(years))

        # When
        early = {
            row[DISPLAY_PERIOD]: row[DISPLAY_SIGNAL_COUNT]
            for row in period_rows(entries, returns, last_day=pd.Timestamp("2015-12-31"), tradable=True)
        }
        late = {
            row[DISPLAY_PERIOD]: row[DISPLAY_SIGNAL_COUNT]
            for row in period_rows(entries, returns, last_day=pd.Timestamp("2026-08-25"), tradable=True)
        }

        # Then
        assert early[PERIOD_RECENT_5Y] != late[PERIOD_RECENT_5Y]

    def test_최근_5년은_마지막_거래일에서_5년_안이다(self) -> None:
        """
        목적: 경계 산식을 고정한다

        Given: 2006~2025 해마다 9월 15일 진입, 마지막 거래일 2026-08-25
        When: 구간별로 나누면
        Then: 2021-08-25 이후 진입인 2021~2025 다섯 건이다
        """
        # Given
        years = list(range(2006, 2026))

        # When
        rows = {
            row[DISPLAY_PERIOD]: row[DISPLAY_SIGNAL_COUNT]
            for row in period_rows(
                _dates(years), _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True
            )
        }

        # Then
        assert rows[PERIOD_RECENT_5Y] == 5


class TestValidation:
    """입력 검증"""

    def test_길이가_다르면_거부한다(self) -> None:
        """
        목적: 진입일과 수익률이 어긋난 채로 집계되지 않게 한다

        Given: 길이가 다른 두 축
        When: 구간별로 나누면
        Then: ValueError 가 난다
        """
        # Given
        entries = _dates([2020, 2021, 2022])

        # When / Then
        with pytest.raises(ValueError, match="길이"):
            period_rows(entries, [0.01, 0.02], last_day=pd.Timestamp("2026-08-25"), tradable=True)


class TestEmptyPeriodMetrics:
    """표본 0건 구간에서는 **모든** 지표가 비어 있다"""

    def test_손절_건수도_비어_있다(self) -> None:
        """
        목적: 0 으로 채우는 마지막 자리를 없앤다 (루트 `CLAUDE.md` 측정의 원칙 17).

        합계·평균·승률·최고·최악은 이미 비우면서 갭손절·장중손절 건수만 `0` 이 찍혔다.
        **`0` 은 「그런 일이 없었다」로 읽히는데 실제로는 「잰 적이 없다」다.**
        같은 행 안에서 어떤 칸은 비고 어떤 칸은 0 이면 읽는 사람이 그 차이를 뜻으로 받아들인다.

        Given: 최근 5년에 진입이 하나도 없는 체결 목록 (청산 사유는 함께 넘긴다)
        When: 구간별 성적 행을 만든다
        Then: 최근 5년 행의 손절 건수 두 칸이 비어 있다
        """
        # Given
        years = list(range(2000, 2011))
        entry_dates = _dates(years)
        returns = _returns(len(years))
        reasons = [EXIT_INTRADAY_STOP] * len(years)
        last_day = pd.Timestamp("2026-08-25")

        # When
        rows = period_rows(entry_dates, returns, last_day=last_day, tradable=True, reasons=reasons)
        recent = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_RECENT_5Y)

        # Then
        assert recent[DISPLAY_SIGNAL_COUNT] == 0
        assert pd.isna(recent[DISPLAY_GAP_STOP_COUNT])
        assert pd.isna(recent[DISPLAY_INTRADAY_STOP_COUNT])

    def test_표본이_있으면_0건도_0으로_적는다(self) -> None:
        """
        목적: 「없었다」와 「못 쟀다」를 구분한다.

        표본이 있는데 손절이 안 걸린 것은 **사실**이므로 0 이 맞다.
        앞 테스트가 모든 0 을 지우는 방향으로 과잉 적용되지 않게 짝으로 둔다.

        Given: 전 구간에 진입이 있고 손절은 하나도 걸리지 않은 목록
        When: 구간별 성적 행을 만든다
        Then: 전체 행의 손절 건수가 0 이다
        """
        # Given
        years = list(range(2016, 2016 + MIN_SAMPLE_PER_CELL))
        entry_dates = _dates(years)
        returns = _returns(len(years))
        reasons = [EXIT_LIMIT] * len(years)
        last_day = pd.Timestamp(f"{years[-1]}-12-30")

        # When
        rows = period_rows(entry_dates, returns, last_day=last_day, tradable=True, reasons=reasons)
        whole = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_ALL)

        # Then
        assert whole[DISPLAY_SIGNAL_COUNT] == len(years)
        assert whole[DISPLAY_GAP_STOP_COUNT] == 0
        assert whole[DISPLAY_INTRADAY_STOP_COUNT] == 0


class TestWorstHoldColumn:
    """보유 중 최악은 그 구간에서 **가장 깊이 밀린 한 건**이다

    기존 `최악(%)` 과 대칭이라 두 값을 같은 행에서 바로 견줄 수 있다 —
    「매도 시점 -5%」와 「보유 중 -20%」가 한 줄에 나란히 있어야 감당할 손실이 보인다.
    """

    def test_구간_최솟값이_실린다(self) -> None:
        """
        목적: 집계 방식이 **평균이 아니라 최솟값**임을 고정한다

        평균으로 내면 한 번 크게 밀린 체결이 다른 체결에 희석돼 **감당해야 할 최대 손실이
        표에서 사라진다.** 그것이 이 컬럼을 만든 이유다.

        Given: 보유 중 최악이 -3% · -18% · -5% 인 체결 셋
        When: 구간별 성적 행을 만든다
        Then: 전체 행의 보유 중 최악이 **-18%** 다
        """
        # Given
        years = [2020, 2021, 2022]
        entry_dates = _dates(years)

        # When
        rows = period_rows(
            entry_dates,
            [0.01, -0.02, 0.01],
            last_day=pd.Timestamp("2026-08-25"),
            tradable=True,
            worst_hold_rates=[-0.03, -0.18, -0.05],
        )
        whole = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_ALL)

        # Then
        assert whole[DISPLAY_WORST_HOLD] == pytest.approx(-18.0, abs=PERCENT_TOLERANCE)

    def test_결과_최악보다_나쁘거나_같다(self) -> None:
        """
        목적: 불변조건 `보유 중 최악(%) <= 최악(%)` 을 구간 행에서 고정한다

        체결마다 성립하는 부등식이 최솟값끼리에서도 성립한다 — 결과 최악을 만든 체결의
        보유 중 최악이 이미 그보다 나쁘기 때문이다. 깨지면 두 컬럼이 서로 다른 체결 목록을
        보고 있다는 뜻이다.

        Given: 부호가 섞인 체결 10건
        When: 구간별 성적 행을 만든다
        Then: 표본이 있는 모든 구간에서 부등식이 성립한다
        """
        # Given
        years = list(range(2016, 2026))
        returns = _returns(len(years))
        worst = [value - 0.04 for value in returns]

        # When
        rows = period_rows(
            _dates(years),
            returns,
            last_day=pd.Timestamp("2025-12-30"),
            tradable=True,
            worst_hold_rates=worst,
        )

        # Then
        measured = [row for row in rows if row[DISPLAY_SIGNAL_COUNT] > 0]
        assert measured, "표본이 있는 구간이 없어 계약을 검사하지 못했습니다"
        for row in measured:
            assert row[DISPLAY_WORST_HOLD] <= row[DISPLAY_MIN], f"보유 중 최악이 결과 최악보다 낫습니다: {row}"

    def test_표본_0건_구간은_비어_있다(self) -> None:
        """
        목적: 같은 행의 다른 지표와 어긋나지 않게 한다 (엣지 케이스)

        `0` 은 「한 번도 안 밀렸다」로 읽히는데 실제로는 「잰 적이 없다」다.

        Given: 최근 5년에 진입이 하나도 없는 체결 목록
        When: 구간별 성적 행을 만든다
        Then: 최근 5년 행의 보유 중 최악이 비어 있다
        """
        # Given
        years = list(range(2000, 2011))
        returns = _returns(len(years))

        # When
        rows = period_rows(
            _dates(years),
            returns,
            last_day=pd.Timestamp("2026-08-25"),
            tradable=True,
            worst_hold_rates=[value - 0.04 for value in returns],
        )
        recent = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_RECENT_5Y)

        # Then
        assert recent[DISPLAY_SIGNAL_COUNT] == 0
        assert pd.isna(recent[DISPLAY_WORST_HOLD])

    def test_길이가_어긋나면_거부한다(self) -> None:
        """
        목적: 나란한 배열의 길이 검사에 이 인자도 들어가는지 고정한다

        길이가 어긋나면 마스크 적용에서 numpy 가 영문 `IndexError` 를 내고 **어느 인자가
        잘못됐는지 말해 주지 않는다.**

        Given: 수익률 3건에 보유 중 최악 2건
        When: 구간별 성적 행을 만든다
        Then: ValueError 가 난다
        """
        # Given
        entries = _dates([2020, 2021, 2022])

        # When / Then
        with pytest.raises(ValueError, match="길이"):
            period_rows(
                entries,
                [0.01, 0.02, 0.03],
                last_day=pd.Timestamp("2026-08-25"),
                tradable=True,
                worst_hold_rates=[-0.01, -0.02],
            )


class TestPeriodSpan:
    """구간이 실제로 어느 기간인지 행 안에서 드러난다"""

    def test_구간_기간이_그_구간의_진입일_최소최대다(self) -> None:
        """
        목적: 구간 시작일·종료일이 **그 구간에 실제로 들어간 진입일의 최소·최대**임을 고정한다.

        구간 이름만으로는 기간을 알 수 없다 — 「앞 절반」이 30년 지수에서는 1996~2011 이고
        11년 ETF 에서는 2015~2020 이다. 대상마다 기간이 다른 행을 한 표에 놓고 비교하게 되므로
        그 사실이 행 안에서 드러나야 한다.

        Given: 2016~2025 의 진입 10건
        When: 구간별 성적 행을 만든다
        Then: 전체는 2016~2025, 앞 절반은 2016~2020, 뒤 절반은 2021~2025 다
        """
        # Given
        from verify_lab.execution.constants import DISPLAY_PERIOD_END, DISPLAY_PERIOD_START

        years = list(range(2016, 2026))
        entry_dates = _dates(years)

        # When
        rows = period_rows(entry_dates, _returns(len(years)), last_day=pd.Timestamp("2025-12-30"), tradable=True)
        by_period = {row[DISPLAY_PERIOD]: row for row in rows}

        # Then
        assert by_period[PERIOD_ALL][DISPLAY_PERIOD_START] == "2016-09-15"
        assert by_period[PERIOD_ALL][DISPLAY_PERIOD_END] == "2025-09-15"
        assert by_period[PERIOD_FIRST_HALF][DISPLAY_PERIOD_START] == "2016-09-15"
        assert by_period[PERIOD_FIRST_HALF][DISPLAY_PERIOD_END] == "2020-09-15"
        assert by_period[PERIOD_SECOND_HALF][DISPLAY_PERIOD_START] == "2021-09-15"
        assert by_period[PERIOD_SECOND_HALF][DISPLAY_PERIOD_END] == "2025-09-15"

    def test_표본이_0건인_구간은_기간을_비운다(self) -> None:
        """
        목적: 표본이 없는 구간의 기간을 **비움**을 고정한다.

        임의의 날짜로 채우면 **잰 적이 없는 구간이 잰 것처럼 읽힌다.**
        `_period_row` 가 이미 지표를 비우는 것과 같은 규칙이다.

        Given: 오래된 진입만 있어 최근 5년이 비는 목록
        When: 구간별 성적 행을 만든다
        Then: 최근 5년 행의 기간이 비어 있다
        """
        # Given
        from verify_lab.execution.constants import DISPLAY_PERIOD_END, DISPLAY_PERIOD_START

        years = list(range(2000, 2010))
        entry_dates = _dates(years)

        # When
        rows = period_rows(entry_dates, _returns(len(years)), last_day=pd.Timestamp("2026-08-25"), tradable=True)
        recent = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_RECENT_5Y)

        # Then
        assert recent[DISPLAY_SIGNAL_COUNT] == 0
        assert pd.isna(recent[DISPLAY_PERIOD_START])
        assert pd.isna(recent[DISPLAY_PERIOD_END])

    def test_구간_기간이_전체_범위를_벗어나지_않는다(self) -> None:
        """
        목적: 어느 구간도 **전체 구간의 범위 밖으로 나가지 않음**을 고정한다.

        경계 계산이 어긋나면 값은 나오는데 예외가 없다.

        Given: 2016~2025 의 진입 10건
        When: 구간별 성적 행을 만든다
        Then: 표본이 있는 모든 구간이 전체 범위 안에 있다
        """
        # Given
        from verify_lab.execution.constants import DISPLAY_PERIOD_END, DISPLAY_PERIOD_START

        years = list(range(2016, 2026))

        # When
        rows = period_rows(_dates(years), _returns(len(years)), last_day=pd.Timestamp("2025-12-30"), tradable=True)
        whole = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_ALL)

        # Then
        for row in rows:
            if row[DISPLAY_SIGNAL_COUNT] == 0:
                continue
            assert row[DISPLAY_PERIOD_START] >= whole[DISPLAY_PERIOD_START]
            assert row[DISPLAY_PERIOD_END] <= whole[DISPLAY_PERIOD_END]
