"""원달러 그리드 동적 범위의 계약을 고정한다.

범위는 **매수 가능 구간 그 자체**다. 격자(조각 1)가 가격표를 고정하고 범위가 그중 어느 레벨을
켤지 정하므로, 창이 한 달 밀리거나 당월이 섞여 들어가면 **성적이 통째로 달라지는데 예외는 나지 않는다.**

핵심 계약은 다섯 가지다.

- **당월을 보지 않는다.** 재조정 달의 시세로 그날 범위를 정하면 룩어헤드다
- **창은 정확히 12N개월이다.** 모자라면 있는 만큼 쓰지 않고 즉시 실패한다 — 짧은 창은
  범위를 좁혀 슬롯 하나를 거대하게 만드는데, 그 사고는 조용히 지나간다
- **최소폭 강제는 기하평균 기준 대칭 확장**이며 발동 여부가 결과에 남는다
- **폭 판정은 곱셈으로 한다.** 사양서 §4.2 의 `상단/하단 − 1 < 폭` 을 문자 그대로 쓰면
  폭이 정확히 임계값일 때 오발동한다 (검사 범위 15%·20%에서 실제로 발생)
- **재조정은 월 1회**, 매월 첫 거래일이며 사이 날은 직전 범위를 그대로 쓴다
- **연장 하단은 하단 이탈 B안이 격자를 어디까지 늘릴지를 정한다.** A안이면 정식 하단과 같고,
  B안이면 직전 재조정 이후 관측된 최저 종가까지 내려가며 **매 재조정일에 초기화**된다
"""

import math
from collections.abc import Callable, Sequence

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.strategy.grid.constants import (
    COL_EXTENDED_LOW,
    COL_RANGE_HIGH,
    COL_RANGE_LOW,
    COL_RANGE_WIDENED,
    COL_RAW_RANGE_HIGH,
    COL_RAW_RANGE_LOW,
    COL_REBALANCED,
    DEFAULT_MIN_RANGE_WIDTH,
    LOWER_BREACH_EXTEND,
    LOWER_BREACH_HOLD,
)
from verify_lab.strategy.grid.price_range import build_daily_ranges, monthly_average_close, resolve_range

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 가격 비교 허용오차
PRICE_TOLERANCE = 0.01


def _series_by_month(values_by_month: dict[str, Sequence[float]]) -> pd.DataFrame:
    """월별 종가 목록으로 단일 값 시계열을 만든다.

    각 달의 거래일은 1일부터 세는 영업일이다. 달을 넘지 않도록 달마다 5개 이하로 둔다.
    """
    rows: list[tuple[pd.Timestamp, float]] = []
    for month, values in values_by_month.items():
        days = pd.bdate_range(f"{month}-01", periods=len(values))
        rows.extend(zip(days, values, strict=True))

    frame = pd.DataFrame(rows, columns=[COL_DATE, COL_VALUE])

    return frame.sort_values(COL_DATE).reset_index(drop=True)


def _one_day_per_month(start: str, values: Sequence[float]) -> pd.DataFrame:
    """달마다 거래일 하나짜리 시계열을 만든다. 워밍업 개수만 따지는 테스트에 쓴다."""
    months = pd.period_range(start, periods=len(values), freq="M")

    return pd.DataFrame(
        {
            COL_DATE: [month.to_timestamp() for month in months],
            COL_VALUE: list(values),
        }
    )


class TestMonthlyAverageClose:
    """월평균 산식을 손계산으로 박는다."""

    def test_달마다_그_달_거래일만_평균한다(self) -> None:
        """
        목적: 월평균이 **그 달 안에서만** 계산됨을 고정한다

        Given: 달마다 거래일 수가 다른 시계열
        When: 월평균을 구한다
        Then: 손으로 계산한 값과 같다
        """
        # Given
        series = _series_by_month({"2020-01": [100.0, 110.0, 120.0], "2020-02": [200.0, 220.0]})

        # When
        actual = monthly_average_close(series)

        # Then
        assert list(actual.index) == [pd.Period("2020-01", freq="M"), pd.Period("2020-02", freq="M")]
        assert actual.iloc[0] == pytest.approx(110.0, abs=EXACT_TOLERANCE)
        assert actual.iloc[1] == pytest.approx(210.0, abs=EXACT_TOLERANCE)

    def test_거래일이_하나뿐인_달도_평균이_있다(self) -> None:
        """
        목적: 엣지 케이스 — 며칠짜리 달인지 따지지 않음을 고정한다 (결정 R1)

        Given: 거래일이 하나뿐인 달
        When: 월평균을 구한다
        Then: 그 하루의 값이 곧 월평균이다

        Note:
            "며칠이면 한 달인가"는 새 파라미터이고 사양서에 없다
        """
        # Given
        series = _series_by_month({"2020-01": [1234.5]})

        # When
        actual = monthly_average_close(series)

        # Then
        assert list(actual.index) == [pd.Period("2020-01", freq="M")]
        assert actual.iloc[0] == pytest.approx(1234.5, abs=EXACT_TOLERANCE)

    def test_월_오름차순으로_돌려준다(self) -> None:
        """
        목적: 창을 잘라내는 계산이 기대는 정렬 계약을 고정한다

        Given: 여러 달짜리 시계열
        When: 월평균을 구한다
        Then: 인덱스가 월 오름차순이다
        """
        # Given
        series = _one_day_per_month("2019-01", [float(value) for value in range(1, 25)])

        # When
        actual = monthly_average_close(series)

        # Then
        assert list(actual.index) == sorted(actual.index)


class TestResolveRange:
    """참조 창과 최소폭 강제를 고정한다."""

    def _monthly(self) -> pd.Series:
        """2019-01 ~ 2020-03 의 월평균. 창 밖 달에 극단값을 심어 둔다."""
        values = {
            "2019-01": 1.0,  # 창 밖 (N=1 이면 2019-03 부터)
            "2019-02": 9999.0,  # 창 밖
            "2019-03": 1000.0,
            "2019-04": 1050.0,
            "2019-05": 1100.0,
            "2019-06": 1150.0,
            "2019-07": 1200.0,
            "2019-08": 1250.0,
            "2019-09": 1300.0,
            "2019-10": 1350.0,
            "2019-11": 1400.0,
            "2019-12": 1450.0,
            "2020-01": 1500.0,
            "2020-02": 1550.0,
            "2020-03": 7777.0,  # 당월 — 제외 대상
        }

        return pd.Series(values.values(), index=pd.PeriodIndex(list(values.keys()), freq="M"))

    def test_참조_창이_사양서_표와_일치한다(self) -> None:
        """
        목적: N=1 에서 2020-03 재조정이 **2019-03 ~ 2020-02** 를 본다 (사양서 §4.1 표)

        Given: 창 밖에 극단값(1.0·9999.0)이 있는 월평균
        When: 2020-03 의 범위를 구한다
        Then: 창 안의 min/max 인 1000 ~ 1550 이고, 창 밖 값은 섞이지 않는다
        """
        # When
        actual = resolve_range(
            self._monthly(),
            pd.Period("2020-03", freq="M"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert actual.raw_low == pytest.approx(1000.0, abs=PRICE_TOLERANCE)
        assert actual.raw_high == pytest.approx(1550.0, abs=PRICE_TOLERANCE)
        assert actual.month_count == 12
        assert actual.first_month == pd.Period("2019-03", freq="M")
        assert actual.last_month == pd.Period("2020-02", freq="M")

    def test_당월은_창에_들어가지_않는다(self) -> None:
        """
        목적: **당월 제외**를 고정한다 (사양서 §4.1·§15.1)

        Given: 당월 값을 7777 에서 0.1 로 바꾼 두 가지 월평균
        When: 각각 그 달의 범위를 구한다
        Then: 범위가 같다 — 당월 값이 결과에 전혀 관여하지 않는다

        Note:
            당월이 섞이면 **그날 시세로 그날 범위를 정하는 룩어헤드**가 된다
        """
        # Given
        target = pd.Period("2020-03", freq="M")
        original = self._monthly()
        changed = pd.Series(
            [0.1 if month == target else value for month, value in original.items()],
            index=original.index,
        )

        # When
        base = resolve_range(original, target, lookback_years=1, min_range_width=DEFAULT_MIN_RANGE_WIDTH)
        other = resolve_range(changed, target, lookback_years=1, min_range_width=DEFAULT_MIN_RANGE_WIDTH)

        # Then
        assert base.raw_low == pytest.approx(other.raw_low, abs=EXACT_TOLERANCE)
        assert base.raw_high == pytest.approx(other.raw_high, abs=EXACT_TOLERANCE)

    def test_창이_모자라면_거부한다(self) -> None:
        """
        목적: 워밍업 부족을 조용히 넘기지 않음을 고정한다 (결정 R2)

        Given: 12개월이 필요한데 앞에 11개월뿐인 월평균
        When: 범위를 구한다
        Then: ValueError 이고 메시지에 필요 개월 수가 담긴다

        Note:
            짧은 창은 범위를 좁혀 **슬롯 하나를 거대하게 만드는데 예외가 나지 않는다**
        """
        # Given
        monthly = self._monthly().loc[pd.Period("2019-04", freq="M") :]

        # When / Then
        with pytest.raises(ValueError, match="12"):
            resolve_range(
                monthly,
                pd.Period("2020-03", freq="M"),
                lookback_years=1,
                min_range_width=DEFAULT_MIN_RANGE_WIDTH,
            )

    def test_폭이_충분하면_강제하지_않는다(self) -> None:
        """
        목적: 최소폭 강제가 넓은 범위를 건드리지 않음을 고정한다

        Given: 폭이 55% 인 창 (1000 ~ 1550)
        When: 최소폭 20% 로 범위를 구한다
        Then: 원본 그대로이고 발동 표시가 꺼져 있다
        """
        # When
        actual = resolve_range(
            self._monthly(),
            pd.Period("2020-03", freq="M"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert not actual.widened
        assert actual.low == pytest.approx(actual.raw_low, abs=EXACT_TOLERANCE)
        assert actual.high == pytest.approx(actual.raw_high, abs=EXACT_TOLERANCE)

    def test_폭이_모자라면_기하평균_기준으로_대칭_확장한다(self) -> None:
        """
        목적: 최소폭 강제 산식을 고정한다 (사양서 §4.2)

        Given: 폭이 10% 인 창 (1000 ~ 1100)
        When: 최소폭 20% 로 범위를 구한다
        Then: 폭이 정확히 20% 가 되고 **기하평균은 원본과 같다** (대칭 확장)
        """
        # Given
        monthly = pd.Series(
            [1000.0, 1050.0, 1100.0] * 4,
            index=pd.period_range("2019-03", periods=12, freq="M"),
        )

        # When
        actual = resolve_range(
            monthly, pd.Period("2020-03", freq="M"), lookback_years=1, min_range_width=DEFAULT_MIN_RANGE_WIDTH
        )

        # Then
        assert actual.widened
        assert actual.high / actual.low == pytest.approx(1.0 + DEFAULT_MIN_RANGE_WIDTH, abs=EXACT_TOLERANCE)
        assert math.sqrt(actual.low * actual.high) == pytest.approx(math.sqrt(1000.0 * 1100.0), abs=PRICE_TOLERANCE)
        assert actual.raw_low == pytest.approx(1000.0, abs=PRICE_TOLERANCE)
        assert actual.raw_high == pytest.approx(1100.0, abs=PRICE_TOLERANCE)

    @pytest.mark.parametrize("min_range_width", [0.15, 0.20, 0.25, 0.30])
    def test_폭이_정확히_임계값이면_발동하지_않는다(self, min_range_width: float) -> None:
        """
        목적: 폭 판정의 부등호와 부동소수점 처리를 고정한다 (결정 R4)

        Given: 폭이 최소폭과 정확히 같은 창
        When: 범위를 구한다
        Then: 강제가 발동하지 않는다

        Note:
            사양서 §4.2 의 `상단/하단 − 1 < 폭` 을 문자 그대로 쓰면 **오발동한다** —
            `1200/1000 − 1` 이 0.19999999999999996 이라 0.20 보다 작다고 판정된다.
            사양서 검사 범위 4개 중 15%·20% 두 개에서 실제로 발생한다.
            값이 바뀌지 않으면서 「강제 발동 횟수」만 늘어 지표가 오염된다
        """
        # Given
        low, high = 1000.0, 1000.0 * (1.0 + min_range_width)
        monthly = pd.Series([low, high] * 6, index=pd.period_range("2019-03", periods=12, freq="M"))

        # When
        actual = resolve_range(
            monthly, pd.Period("2020-03", freq="M"), lookback_years=1, min_range_width=min_range_width
        )

        # Then
        assert not actual.widened

    def test_창의_월평균이_전부_같으면_강제로_열린다(self) -> None:
        """
        목적: 엣지 케이스 — 폭이 0 인 창의 처리를 고정한다

        Given: 12개월 월평균이 전부 1300 인 창
        When: 범위를 구한다
        Then: 예외 없이 폭 20% 로 열리고, 중심이 1300 이다
        """
        # Given
        monthly = pd.Series(1300.0, index=pd.period_range("2019-03", periods=12, freq="M"))

        # When
        actual = resolve_range(
            monthly, pd.Period("2020-03", freq="M"), lookback_years=1, min_range_width=DEFAULT_MIN_RANGE_WIDTH
        )

        # Then
        assert actual.widened
        assert actual.high / actual.low == pytest.approx(1.0 + DEFAULT_MIN_RANGE_WIDTH, abs=EXACT_TOLERANCE)
        assert math.sqrt(actual.low * actual.high) == pytest.approx(1300.0, abs=PRICE_TOLERANCE)

    @pytest.mark.parametrize("lookback_years", [0, -1])
    def test_룩백이_1년_미만이면_거부한다(self, lookback_years: int) -> None:
        """
        목적: 룩백의 유효 범위를 고정한다

        Given: 0 이하인 룩백
        When: 범위를 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="룩백"):
            resolve_range(
                self._monthly(),
                pd.Period("2020-03", freq="M"),
                lookback_years=lookback_years,
                min_range_width=DEFAULT_MIN_RANGE_WIDTH,
            )

    @pytest.mark.parametrize("min_range_width", [-0.1, 0.0])
    def test_최소폭이_양수가_아니면_거부한다(self, min_range_width: float) -> None:
        """
        목적: 최소폭의 유효 범위를 고정한다

        Given: 0 이하인 최소폭
        When: 범위를 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="최소 범위폭"):
            resolve_range(
                self._monthly(),
                pd.Period("2020-03", freq="M"),
                lookback_years=1,
                min_range_width=min_range_width,
            )


class TestBuildDailyRanges:
    """거래일별 범위표의 계약을 고정한다."""

    def _series(self) -> pd.DataFrame:
        """2019-01 ~ 2021-12 의 시계열. 달마다 거래일 3개씩 둔다."""
        months = pd.period_range("2019-01", periods=36, freq="M")
        values_by_month = {
            str(month): [1000.0 + index * 10.0, 1000.0 + index * 10.0 + 5.0, 1000.0 + index * 10.0 - 5.0]
            for index, month in enumerate(months)
        }

        return _series_by_month(values_by_month)

    def _run(self, frame: pd.DataFrame) -> pd.DataFrame:
        """look-ahead 감시에 쓸 실행 함수. 날짜와 하단만 남긴다."""
        return build_daily_ranges(
            frame,
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )[[COL_DATE, COL_RANGE_LOW]]

    def test_거래일마다_한_줄이다(self) -> None:
        """
        목적: 반환 형태를 고정한다 (결정 R5)

        Given: 매매 시작일 이후 거래일이 있는 시계열
        When: 거래일별 범위표를 만든다
        Then: 시작일 이후 거래일 수만큼 행이 있고 컬럼 구성이 고정돼 있다
        """
        # Given
        series = self._series()
        expected = int((series[COL_DATE] >= pd.Timestamp("2020-01-01")).sum())

        # When
        actual = build_daily_ranges(
            series,
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert len(actual) == expected
        assert list(actual.columns) == [
            COL_DATE,
            COL_RANGE_LOW,
            COL_RANGE_HIGH,
            COL_EXTENDED_LOW,
            COL_RAW_RANGE_LOW,
            COL_RAW_RANGE_HIGH,
            COL_RANGE_WIDENED,
            COL_REBALANCED,
        ]

    def test_재조정은_매월_첫_거래일에만_일어난다(self) -> None:
        """
        목적: 재조정 주기를 고정한다 (사양서 §4.3)

        Given: 달마다 거래일 3개씩인 시계열
        When: 거래일별 범위표를 만든다
        Then: 재조정 표시가 켜진 날이 달마다 정확히 하나이고, 그날이 그 달의 첫 거래일이다
        """
        # When
        actual = build_daily_ranges(
            self._series(),
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        rebalanced = actual[actual[COL_REBALANCED]]
        months = rebalanced[COL_DATE].dt.to_period("M")
        assert months.is_unique
        assert len(rebalanced) == actual[COL_DATE].dt.to_period("M").nunique()

        first_days = actual.groupby(actual[COL_DATE].dt.to_period("M"))[COL_DATE].min()
        assert sorted(rebalanced[COL_DATE]) == sorted(first_days)

    def test_재조정_사이에는_범위가_바뀌지_않는다(self) -> None:
        """
        목적: 사이 날이 직전 범위를 그대로 씀을 고정한다 (결정 R5)

        Given: 달마다 거래일 3개씩인 시계열
        When: 거래일별 범위표를 만든다
        Then: 재조정일이 아닌 날의 범위는 그 달 첫 거래일과 같다
        """
        # When
        actual = build_daily_ranges(
            self._series(),
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        for _, group in actual.groupby(actual[COL_DATE].dt.to_period("M")):
            assert group[COL_RANGE_LOW].nunique() == 1
            assert group[COL_RANGE_HIGH].nunique() == 1

    def test_첫_거래일에도_범위가_있다(self) -> None:
        """
        목적: 백테스트 첫 거래일이 월 중간이어도 범위가 있음을 고정한다 (결정 R3)

        Given: 월 첫 거래일이 아닌 날부터 매매를 시작한다
        When: 거래일별 범위표를 만든다
        Then: 첫 행이 재조정일이고 범위가 채워져 있다

        Note:
            사양서 §11.4 는 "첫날 상태: 완성된 범위와 격자 보유" 를 요구한다.
            첫날에 범위가 없으면 그 달 내내 매수가 불가능해진다
        """
        # Given
        series = self._series()
        mid_month = series.loc[series[COL_DATE] >= pd.Timestamp("2020-01-01"), COL_DATE].iloc[1]

        # When
        actual = build_daily_ranges(
            series,
            start_date=mid_month,
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert actual[COL_DATE].iloc[0] == mid_month
        assert bool(actual[COL_REBALANCED].iloc[0])
        assert actual[COL_RANGE_LOW].iloc[0] > 0

    def test_미래를_참조하지_않는다(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: look-ahead 감시 계약을 건다 (`tests/CLAUDE.md` 필수 테스트)

        Given: 36개월짜리 시계열
        When: 뒤를 잘라낸 입력과 전체 입력으로 각각 범위표를 만든다
        Then: 겹치는 날의 범위 하단이 같다

        Note:
            당월이 창에 섞이거나 창을 한 칸 잘못 자르면 여기서 걸린다
        """
        assert_stable_under_truncation(
            self._run,
            self._series(),
            80,
            key_columns=[COL_DATE],
            value_column=COL_RANGE_LOW,
        )

    def test_하단이_언제나_상단보다_낮다(self) -> None:
        """
        목적: 범위의 기본 불변조건을 고정한다

        Given: 36개월짜리 시계열
        When: 거래일별 범위표를 만든다
        Then: 모든 날에서 하단 < 상단이고 둘 다 양수다
        """
        # When
        actual = build_daily_ranges(
            self._series(),
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert (actual[COL_RANGE_LOW] > 0).all()
        assert (actual[COL_RANGE_LOW] < actual[COL_RANGE_HIGH]).all()

    def test_매매_시작일_이후만_돌려준다(self) -> None:
        """
        목적: 잘라내는 대상이 **시세가 아니라 결과 행**임을 고정한다

        Given: 워밍업 구간을 포함한 전체 시계열
        When: 매매 시작일을 주고 범위표를 만든다
        Then: 시작일 이전 행이 하나도 없다

        Note:
            시세를 먼저 자르면 월평균 창이 그 지점부터 다시 쌓여 워밍업이 무너진다.
            전체 시세를 넘기고 **결과 행만** 자르는 것이 이 프로젝트의 확정 계약이다
        """
        # When
        actual = build_daily_ranges(
            self._series(),
            start_date=pd.Timestamp("2020-06-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
        )

        # Then
        assert (actual[COL_DATE] >= pd.Timestamp("2020-06-01")).all()

    def test_워밍업이_모자라면_거부한다(self) -> None:
        """
        목적: 시작일이 워밍업을 채우지 못하면 즉시 실패함을 고정한다 (결정 R2)

        Given: 12개월이 필요한데 시작일 앞에 6개월뿐인 시계열
        When: 거래일별 범위표를 만든다
        Then: ValueError
        """
        # Given
        series = self._series()

        # When / Then
        with pytest.raises(ValueError, match="12"):
            build_daily_ranges(
                series,
                start_date=pd.Timestamp("2019-07-01"),
                lookback_years=1,
                min_range_width=DEFAULT_MIN_RANGE_WIDTH,
            )

    def test_시작일_이후_거래일이_없으면_거부한다(self) -> None:
        """
        목적: 엣지 케이스 — 빈 결과를 조용히 돌려주지 않음을 고정한다

        Given: 데이터 마지막 날보다 뒤인 시작일
        When: 거래일별 범위표를 만든다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="거래일"):
            build_daily_ranges(
                self._series(),
                start_date=pd.Timestamp("2030-01-01"),
                lookback_years=1,
                min_range_width=DEFAULT_MIN_RANGE_WIDTH,
            )


class TestExtendedLow:
    """하단 이탈 B안의 연장 하단 계약을 고정한다 (결정 C78·C79).

    연장 하단은 **격자를 어디까지 늘릴지의 목표 가격**이다. 어느 레벨이 켜지는지는 격자 계층이
    정하며, 이 계층은 가격만 낸다 (결정 C82).

    이 계층이 틀리는 방식은 셋이다 — **A안인데 하단이 움직이거나**, **이탈이 재조정을 넘어
    이월되거나**, **당일 종가가 빠져 이탈한 날 연장이 한 박자 늦는 것**이다.
    전부 예외가 나지 않고 결과만 조용히 달라진다.
    """

    def _falling_series(self) -> pd.DataFrame:
        """2019-01 ~ 2020-03 시계열. 2020-02 에 이탈하고 2020-03 에 반등한다.

        워밍업 12개월(2019-01 ~ 2019-12)을 1,000원 근처로 고정해 범위를 좁게 만든 뒤,
        2020-02 에 그 아래로 내려가는 경로를 둔다.
        """
        values_by_month = {f"2019-{month:02d}": [1000.0, 1000.0, 1000.0] for month in range(1, 13)}
        # 2020-01 은 범위 안, 2020-02 는 이탈(급락 후 얕은 반등), 2020-03 은 완전히 회복
        values_by_month["2020-01"] = [1000.0, 1000.0, 1000.0]
        values_by_month["2020-02"] = [800.0, 700.0, 750.0]
        values_by_month["2020-03"] = [1000.0, 1000.0, 1000.0]

        return _series_by_month(values_by_month)

    def _build(self, series: pd.DataFrame, lower_breach: str) -> pd.DataFrame:
        """2020-01 부터의 범위표를 만든다."""
        return build_daily_ranges(
            series,
            start_date=pd.Timestamp("2020-01-01"),
            lookback_years=1,
            min_range_width=DEFAULT_MIN_RANGE_WIDTH,
            lower_breach=lower_breach,
        )

    def test_A안이면_연장_하단이_정식_하단과_같다(self) -> None:
        """
        목적: A안에 연장이 전혀 없음을 고정한다 (회귀 안전망)

        Given: 하단을 크게 이탈하는 시계열
        When: A안으로 범위표를 만든다
        Then: 모든 행에서 연장 하단이 정식 하단과 **정확히** 같다

        Note:
            컬럼은 A안에도 언제나 존재한다 — 엔진이 「B안이면」으로 분기하지 않게 하기 위해서다.
            분기가 생기면 그 한 곳만 고쳐질 때 예외 없이 결과가 틀린다
        """
        # When
        actual = self._build(self._falling_series(), LOWER_BREACH_HOLD)

        # Then
        assert (actual[COL_EXTENDED_LOW] == actual[COL_RANGE_LOW]).all()

    def test_종가가_하단_위면_B안도_연장하지_않는다(self) -> None:
        """
        목적: 연장이 **이탈한 날에만** 일어남을 고정한다

        Given: 하단을 이탈하는 시계열
        When: B안으로 범위표를 만든다
        Then: 종가가 하단 이상인 날은 연장 하단이 정식 하단과 같다
        """
        # Given
        series = self._falling_series()
        closes = series.set_index(COL_DATE)[COL_VALUE]

        # When
        actual = self._build(series, LOWER_BREACH_EXTEND)
        close = closes.reindex(pd.DatetimeIndex(actual[COL_DATE])).to_numpy()

        # Then
        above = actual[close >= actual[COL_RANGE_LOW].to_numpy()]
        assert not above.empty
        assert (above[COL_EXTENDED_LOW] == above[COL_RANGE_LOW]).all()

    def test_이탈한_날_당일_종가까지_내려간다(self) -> None:
        """
        목적: 연장이 **당일 종가를 포함**함을 고정한다 (결정 C6 — 이탈 즉시 연장)

        Given: 2020-02 첫 거래일에 800원으로 이탈한다
        When: B안으로 범위표를 만든다
        Then: 그날 연장 하단이 800원이다

        Note:
            당일 종가를 빼고 전일까지만 보면 이탈한 날 연장이 한 박자 늦어
            **그날의 하향 돌파를 통째로 놓친다**
        """
        # When
        actual = self._build(self._falling_series(), LOWER_BREACH_EXTEND)
        breach_day = actual[actual[COL_DATE] == pd.Timestamp("2020-02-03")].iloc[0]

        # Then
        assert breach_day[COL_RANGE_LOW] > 800.0
        assert breach_day[COL_EXTENDED_LOW] == pytest.approx(800.0, abs=PRICE_TOLERANCE)

    def test_반등해도_그_달_안에서는_유지된다(self) -> None:
        """
        목적: 연장의 수명을 고정한다 — **재조정까지 유지**된다 (결정 C78)

        Given: 2020-02 에 800 → 700 → 750 으로 움직인다 (마지막 날 반등)
        When: B안으로 범위표를 만든다
        Then: 셋째 날 연장 하단이 750 이 아니라 그 달 최저인 700 이다

        Note:
            매일 재계산하면 750 이 된다. 그러면 결정 C6 의
            「다음 재조정에서 비활성화」가 죽은 문장이 되고, 반등 중 재하락 구간에서
            같은 레벨을 다시 살 수 있는지가 달라진다
        """
        # When
        actual = self._build(self._falling_series(), LOWER_BREACH_EXTEND)
        month = actual[actual[COL_DATE].dt.to_period("M") == pd.Period("2020-02", freq="M")]

        # Then
        assert list(month[COL_EXTENDED_LOW].round(4)) == pytest.approx([800.0, 700.0, 700.0], abs=PRICE_TOLERANCE)

    def test_재조정일에_초기화된다(self) -> None:
        """
        목적: 전월의 최저 종가가 이월되지 않음을 고정한다 (결정 C78)

        Given: 2020-02 에 700원까지 내려갔다가 2020-03 에 1,000원으로 회복한다
        When: B안으로 범위표를 만든다
        Then: 2020-03 의 연장 하단이 정식 하단과 같다 — 700 이 남아 있지 않다
        """
        # When
        actual = self._build(self._falling_series(), LOWER_BREACH_EXTEND)
        month = actual[actual[COL_DATE].dt.to_period("M") == pd.Period("2020-03", freq="M")]

        # Then
        assert not month.empty
        assert (month[COL_EXTENDED_LOW] == month[COL_RANGE_LOW]).all()

    def test_연장_하단은_정식_하단보다_높아지지_않는다(self) -> None:
        """
        목적: 방향 불변조건을 고정한다 — 연장은 **아래로만** 간다

        Given: 하단을 이탈하는 시계열
        When: B안으로 범위표를 만든다
        Then: 모든 날에서 연장 하단 ≤ 정식 하단이다
        """
        # When
        actual = self._build(self._falling_series(), LOWER_BREACH_EXTEND)

        # Then
        assert (actual[COL_EXTENDED_LOW] <= actual[COL_RANGE_LOW]).all()

    def test_미래를_참조하지_않는다(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: look-ahead 감시 계약을 건다 (`tests/CLAUDE.md` 필수 테스트)

        Given: 이탈이 들어 있는 시계열
        When: 뒤를 잘라낸 입력과 전체 입력으로 각각 B안 범위표를 만든다
        Then: 겹치는 날의 연장 하단이 같다

        Note:
            누적 최저 종가를 **그 달 전체**에서 구하면 이탈 이전 날의 연장 하단이
            이미 내려가 있어 여기서 걸린다
        """
        assert_stable_under_truncation(
            lambda frame: self._build(frame, LOWER_BREACH_EXTEND)[[COL_DATE, COL_EXTENDED_LOW]],
            self._falling_series(),
            41,
            key_columns=[COL_DATE],
            value_column=COL_EXTENDED_LOW,
        )

    def test_알_수_없는_하단_이탈_방식은_거부한다(self) -> None:
        """
        목적: 입력 검증 정책을 고정한다

        Given: A 도 B 도 아닌 값
        When: 범위표를 만든다
        Then: ValueError

        Note:
            조용히 A안으로 떨어지면 **B안을 돌린 줄 알고 A안 결과를 읽게 된다**
        """
        with pytest.raises(ValueError, match="하단 이탈"):
            self._build(self._falling_series(), "C")
