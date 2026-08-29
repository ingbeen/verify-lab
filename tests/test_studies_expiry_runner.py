"""검증 #7 실행 계층의 계약을 고정한다.

집계표는 **행이 무엇에 대한 값인지**를 스스로 밝혀야 한다. 식별 컬럼이 빠진 표는 예외 없이
정상으로 보이면서 해석이 불가능해진다 — 실제로 축 컬럼이 사라진 채 산출된 적이 있다.

고정하는 계약은 넷이다.
- 집계표에 축과 식별 컬럼이 모두 남는다
- 일간 등락 집계는 **앞날을 보지 않는다** (그날 종가와 전날 종가만 쓴다)
- 국면·위칭으로 자를 때 **시세가 아니라 신호일만** 잘린다
- 만기 창 안 + 창 밖 = 전체 거래일 (표본 보존)
"""

from collections.abc import Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_MEAN_P_VALUE,
    COL_SAMPLE_COUNT,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
)
from verify_lab.studies.option_expiry.constants import (
    COL_DAILY_RETURN,
    COL_EXPIRY_MONTH_NUMBER,
    COL_HOLD_DAYS,
    COL_MEAN_RATE_CONFLICT,
    COL_MONTH_DAY_INDEX,
    COL_OFFSET,
    COL_TIME_HALF,
    DISPLAY_TIME_HALF_EARLY,
    DISPLAY_TIME_HALF_LATE,
    FRIDAY,
    HORIZON_NEXT_WEEK_EXIT,
    KR_MONTHLY_EXPIRY,
    MIN_SAMPLE_FOR_HALVES,
    US_MONTHLY_EXPIRY,
    Dataset,
    PriceSeries,
)
from verify_lab.studies.option_expiry.runner import (
    _aggregate_by_month,
    _aggregate_month_halves,
    _annotate,
    _month_day_index,
    _per_length,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _market(closes: Sequence[float], start: str = "2026-01-02") -> pd.DataFrame:
    """합성 시세를 만든다. 만기일 판정과 일간 등락은 날짜와 종가만 보므로 나머지는 종가와 같게 둔다."""
    prices = list(closes)

    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range(start, periods=len(prices)),
            COL_OPEN: prices,
            COL_HIGH: prices,
            COL_LOW: prices,
            COL_CLOSE: prices,
            COL_VOLUME: [1_000] * len(prices),
        }
    )


def _dataset(rule: object) -> Dataset:
    """실행 계층이 요구하는 최소 대상 정의를 만든다. 파일은 읽지 않는다."""
    return Dataset(
        key="synthetic",
        ticker="합성",
        rule=rule,  # pyright: ignore[reportArgumentType]
        regimes=(),
        series=(PriceSeries(basis="합성", file_name="none.csv", primary=True),),
        price_decimals=4,
        exit_weekdays=(FRIDAY,),
    )


class TestAnnotate:
    """시세에 붙는 부가 컬럼의 계약을 고정한다."""

    def test_일간_등락은_전날_종가만_쓴다(self) -> None:
        """
        목적: **앞날을 보지 않음**을 고정한다

        Given: 종가 100 → 110 인 합성 시세
        When: 부가 컬럼을 붙이면
        Then: 둘째 날의 일간 등락이 0.1 이고 첫날은 비어 있다
        """
        # Given
        df = _market([100.0, 110.0, 99.0])

        # When
        _, annotated = _annotate(df, _dataset(US_MONTHLY_EXPIRY))

        # Then
        assert pd.isna(annotated[COL_DAILY_RETURN].iloc[0])
        assert float(annotated[COL_DAILY_RETURN].iloc[1]) == pytest.approx(0.1, abs=EXACT_TOLERANCE)

    def test_표본이_보존된다(self) -> None:
        """
        목적: 만기 창 안 + 창 밖 = 전체 거래일 을 고정한다

        Given: 6개월치 합성 시세
        When: 부가 컬럼을 붙이면
        Then: offset 이 있는 날과 없는 날의 합이 전체 거래일과 같다
        """
        # Given
        df = _market([100.0 + index for index in range(130)])

        # When
        _, annotated = _annotate(df, _dataset(KR_MONTHLY_EXPIRY))

        # Then
        inside = int(annotated[COL_OFFSET].notna().sum())
        outside = int(annotated[COL_OFFSET].isna().sum())
        assert inside + outside == len(df)

    def test_월중_서수는_달마다_1부터_다시_센다(self) -> None:
        """
        목적: 월중 서수 축의 정의를 고정한다

        Given: 두 달에 걸친 거래일
        When: 월중 서수를 매기면
        Then: 달이 바뀌는 날에 1 로 돌아간다
        """
        # Given
        dates = pd.Series(pd.to_datetime(["2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03"]))

        # When
        result = _month_day_index(dates)

        # Then
        assert result.tolist() == [1, 2, 1, 2]


class TestWeeklyTradeAssembly:
    """만기일 매수 → 다음주 청산 매매의 조립 계약을 고정한다."""

    def test_길이별_변환은_제외행을_버리고_보유일수를_축으로_쓴다(self) -> None:
        """
        목적: 「같은 길이 단순 보유」와 견줄 수 있는 형태를 고정한다

        제외된 행은 보유일수가 없어 어느 칸에도 속하지 못한다. **제외 건수는 묶음 표가 담당**하며,
        여기서 빠지는 것이 정상이다.

        Given: 유효 2행(보유 4·5일)과 제외 1행
        When: 길이별로 바꾸면
        Then: 제외행이 빠지고 구간 축이 보유일수가 된다
        """
        # Given
        frame = pd.DataFrame(
            {
                COL_HOLD_DAYS: pd.array([4, 5, None], dtype="Int64"),
                COL_HORIZON: [HORIZON_NEXT_WEEK_EXIT] * 3,
                COL_EXCLUDED_REASON: [REASON_NONE, REASON_NONE, REASON_OUT_OF_RANGE],
            }
        )

        # When
        result = _per_length(frame)

        # Then
        assert len(result) == 2
        assert result[COL_HORIZON].tolist() == [4, 5]

    def test_만기월_축은_같은_달_베이스라인을_달고_나온다(self) -> None:
        """
        목적: **9월 약세가 만기 효과인지 그 달의 계절성인지 가를 수 있어야 한다**를 고정한다
        (`docs/spec/option_expiry.md` 결정 ㉓)

        같은 달 베이스라인 없이 월별 값만 내면 두 설명을 구별할 수 없다.

        Given: 3월·9월에 신호가 있고 베이스라인은 전 월에 걸친 입력
        When: 만기월 축으로 집계하면
        Then: 신호가 있는 달만 나오고 각 행에 베이스라인 통계와 초과분이 함께 있다
        """
        # Given
        signal = _long_form(["2026-03-20", "2026-09-18"], [0.02, -0.01])
        baseline = _long_form(
            ["2026-03-06", "2026-03-13", "2026-09-04", "2026-09-11", "2026-05-08"],
            [0.01, 0.00, 0.00, 0.01, 0.05],
        )

        # When
        result = _aggregate_by_month(signal, baseline, repeats=10, seed=0)

        # Then
        assert result[COL_EXPIRY_MONTH_NUMBER].tolist() == [3, 9], "신호가 없는 5월이 섞였습니다"
        assert f"{COL_MEAN}_baseline" in result.columns, "같은 달 베이스라인이 빠졌습니다"
        assert COL_MEAN_P_VALUE in result.columns, "만기월 칸에 검정이 빠졌습니다"
        march = result[result[COL_EXPIRY_MONTH_NUMBER] == 3].iloc[0]
        assert float(march[COL_MEAN]) == pytest.approx(0.02, abs=EXACT_TOLERANCE)
        assert float(march[f"{COL_MEAN}_baseline"]) == pytest.approx(0.005, abs=EXACT_TOLERANCE)
        assert float(march["MeanExcess"]) == pytest.approx(0.015, abs=EXACT_TOLERANCE)

    def test_만기월_축에_두_방향_비율과_각각의_우연확률이_붙는다(self) -> None:
        """
        목적: **아래로 치우친 달을 잡으려면 비율 축이 있어야 한다**를 고정한다
        (루트 `CLAUDE.md` 측정의 원칙 11).

        평균만 검정하면 "대부분의 해가 내렸는데 소수의 큰 상승이 평균을 올린" 달을 놓친다.

        Given: 9월 신호 12건 중 9건이 내린 입력
        When: 만기월 축으로 집계하면
        Then: 두 방향 비율과 그 차이·우연확률이 모두 붙어 나온다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [-0.01] * 9 + [0.02] * 3)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_WIN_RATE]) == pytest.approx(3 / 12, abs=EXACT_TOLERANCE)
        assert float(row[COL_LOSS_RATE]) == pytest.approx(9 / 12, abs=EXACT_TOLERANCE)
        for column in (COL_LOSS_RATE_EXCESS, COL_UP_RATE_P_VALUE, COL_DOWN_RATE_P_VALUE):
            assert column in result.columns, f"{column} 이 만기월 축에서 빠졌습니다"

    def test_평균과_방향_비율이_어긋나는_칸에_표시가_남는다(self) -> None:
        """
        목적: **평균이 양수인데 절반 넘게 내린 칸을 표시한다** (측정의 원칙 13).

        실물 사례가 SPY 3월 만기다 — 평균은 양수인데 3분의 2가 내렸고,
        평균만 보고 "오르는 달"로 기각했던 칸이다.

        Given: 큰 상승 2건이 평균을 양수로 만들지만 12건 중 10건이 내린 9월 신호
        When: 만기월 축으로 집계하면
        Then: 어긋남 표시가 True 다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [0.50, 0.45] + [-0.02] * 10)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_MEAN]) > 0
        assert float(row[COL_LOSS_RATE]) > 0.5
        assert bool(row[COL_MEAN_RATE_CONFLICT]) is True

    def test_평균과_방향_비율이_같은_쪽이면_표시가_없다(self) -> None:
        """
        목적: 어긋남 표시가 **아무 칸에나 붙지 않는다**를 고정한다.

        Given: 평균이 음수이고 대부분 내린 9월 신호 (두 축이 같은 쪽을 가리킨다)
        When: 만기월 축으로 집계하면
        Then: 어긋남 표시가 False 다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(dates, [-0.02] * 10 + [0.01] * 2)
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(13, 28)], [0.01] * 8 + [-0.01] * 7)

        # When
        result = _aggregate_by_month(signal, baseline, repeats=50, seed=0)

        # Then
        row = result.iloc[0]
        assert float(row[COL_MEAN]) < 0
        assert bool(row[COL_MEAN_RATE_CONFLICT]) is False

    def test_시기_2등분은_표본이_모자란_달을_내지_않는다(self) -> None:
        """
        목적: **쪼갤 수 없으면 쪼개지 않는다** (측정의 원칙 12).

        후보 판정 기준 4 는 시기를 갈라 방향이 유지되는지 보는데, 절반씩 나눴을 때
        검정 하한(10건)에 못 미치면 숫자를 만들어내는 것이 된다.

        Given: 9월 신호가 하한 미만인 입력
        When: 시기 2등분으로 집계하면
        Then: 그 달의 행이 나오지 않는다
        """
        # Given
        dates = [f"2026-09-{day:02d}" for day in range(1, MIN_SAMPLE_FOR_HALVES)]
        signal = _long_form(dates, [-0.01] * len(dates))
        baseline = _long_form([f"2026-09-{day:02d}" for day in range(20, 29)], [0.01] * 9)

        # When
        result = _aggregate_month_halves(signal, baseline, repeats=10, seed=0)

        # Then
        assert result.empty, "표본이 하한에 못 미치는 달이 쪼개졌습니다"

    def test_시기_2등분은_앞뒤를_시간순으로_균등하게_가른다(self) -> None:
        """
        목적: 국면 축과 달리 **양쪽 표본을 맞춘다**를 고정한다.

        국면은 달력 경계라 칸마다 표본이 들쭉날쭉하지만, 이 축은 신호를 시간순으로 세어
        가르므로 기준 4 를 표본 하한을 지키며 잴 수 있다.

        Given: 9월 신호 24건 (앞 12건은 내리고 뒤 12건은 오른다)
        When: 시기 2등분으로 집계하면
        Then: 앞뒤 두 행이 나오고 방향이 서로 반대로 갈린다
        """
        # Given
        early = [f"2020-09-{day:02d}" for day in range(1, 13)]
        late = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(early + late, [-0.02] * 12 + [0.02] * 12)
        baseline = _long_form(
            [f"2020-09-{day:02d}" for day in range(13, 25)] + [f"2026-09-{day:02d}" for day in range(13, 25)],
            [0.01] * 24,
        )

        # When
        result = _aggregate_month_halves(signal, baseline, repeats=20, seed=0)

        # Then
        assert result[COL_TIME_HALF].tolist() == [DISPLAY_TIME_HALF_EARLY, DISPLAY_TIME_HALF_LATE]
        assert result[COL_SAMPLE_COUNT].tolist() == [12, 12], "앞뒤 표본이 균등하지 않습니다"
        first, second = result.iloc[0], result.iloc[1]
        assert float(first[COL_LOSS_RATE]) == pytest.approx(1.0, abs=EXACT_TOLERANCE)
        assert float(second[COL_WIN_RATE]) == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_시기_2등분은_보유일수가_섞여도_한_칸으로_센다(self) -> None:
        """
        목적: 입력이 **보유일수를 구간 축으로** 갖고 있어도 한 달이 한 칸으로 집계된다.

        그대로 집계하면 한 달이 보유일수별로 쪼개져 앞뒤 표본이 어긋난다.
        실제 데이터에서 앞 14건 · 뒤 2건 처럼 갈라진 적이 있어 계약으로 고정한다.

        Given: 9월 신호 24건의 보유일수가 4·5·6 으로 섞인 입력
        When: 시기 2등분으로 집계하면
        Then: 앞뒤 두 행만 나오고 표본이 12건씩 균등하다
        """
        # Given
        early = [f"2020-09-{day:02d}" for day in range(1, 13)]
        late = [f"2026-09-{day:02d}" for day in range(1, 13)]
        signal = _long_form(early + late, [-0.02] * 12 + [0.02] * 12)
        signal[COL_HORIZON] = [4, 5, 6] * 8
        baseline = _long_form(
            [f"2020-09-{day:02d}" for day in range(13, 25)] + [f"2026-09-{day:02d}" for day in range(13, 25)],
            [0.01] * 24,
        )
        baseline[COL_HORIZON] = [4, 5, 6] * 8

        # When
        result = _aggregate_month_halves(signal, baseline, repeats=20, seed=0)

        # Then
        assert len(result) == 2, "한 달이 보유일수별로 쪼개졌습니다"
        assert result[COL_SAMPLE_COUNT].tolist() == [12, 12]


def _long_form(dates: Sequence[str], returns: Sequence[float]) -> pd.DataFrame:
    """만기월 집계가 요구하는 최소 long-form 을 만든다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(list(dates)),
            COL_BASIS: ["close"] * len(dates),
            COL_HORIZON: [HORIZON_NEXT_WEEK_EXIT] * len(dates),
            COL_FORWARD_RETURN: list(returns),
            COL_EXCLUDED_REASON: [REASON_NONE] * len(dates),
        }
    )


def test_월중_서수와_offset_이_함께_붙는다() -> None:
    """
    목적: 만기 축과 월중 위치 축이 **함께** 산출되는지 고정한다

    만기 창은 언제나 월 중순이라 두 축이 거의 붙어 다닌다. 둘을 함께 내야 독자가
    "만기 때문인가 월 중순이라서인가"를 직접 볼 수 있다 (`docs/spec/option_expiry.md` 결정 ⑭).

    Given: 3개월치 합성 시세
    When: 부가 컬럼을 붙이면
    Then: offset 과 월중 서수가 모두 들어 있다
    """
    # Given
    df = _market([100.0 + index for index in range(70)])

    # When
    _, annotated = _annotate(df, _dataset(US_MONTHLY_EXPIRY))

    # Then
    assert COL_OFFSET in annotated.columns
    assert COL_MONTH_DAY_INDEX in annotated.columns
    assert annotated[COL_MONTH_DAY_INDEX].min() == 1
