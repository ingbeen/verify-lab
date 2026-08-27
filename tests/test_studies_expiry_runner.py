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
from verify_lab.measure.statistics import COL_MEAN, COL_SAMPLE_COUNT
from verify_lab.studies.option_expiry.constants import (
    COL_DAILY_RETURN,
    COL_MONTH_DAY_INDEX,
    COL_OFFSET,
    KR_MONTHLY_EXPIRY,
    US_MONTHLY_EXPIRY,
    Dataset,
    PriceSeries,
    Regime,
    WitchingGroup,
)
from verify_lab.studies.option_expiry.runner import (
    _aggregate_daily,
    _annotate,
    _month_day_index,
    _regime_mask,
    _witching_mask,
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
    )


class TestAggregateDaily:
    """집계표가 자기 축을 잃지 않는지 고정한다."""

    def test_축_컬럼이_집계표에_남는다(self) -> None:
        """
        목적: **행이 무엇에 대한 값인지 알 수 있어야 한다**를 고정한다

        Given: offset 이 붙은 일간 등락 3행
        When: offset 축으로 집계하면
        Then: 결과에 offset 컬럼이 있고 값이 보존된다
        """
        # Given
        frame = pd.DataFrame({COL_OFFSET: [-1.0, -1.0, 2.0], COL_DAILY_RETURN: [0.01, 0.03, -0.02]})

        # When
        result = _aggregate_daily(frame, COL_OFFSET)

        # Then
        assert COL_OFFSET in result.columns, "집계표에서 축 컬럼이 사라졌습니다"
        assert result[COL_OFFSET].tolist() == [-1, 2]

    def test_평균과_표본수가_맞는다(self) -> None:
        """
        목적: 산식을 손으로 계산한 값으로 고정한다

        Given: offset -1 에 0.01 과 0.03
        When: 집계하면
        Then: 표본 2건, 평균 0.02
        """
        # Given
        frame = pd.DataFrame({COL_OFFSET: [-1.0, -1.0, 2.0], COL_DAILY_RETURN: [0.01, 0.03, -0.02]})

        # When
        result = _aggregate_daily(frame, COL_OFFSET)

        # Then
        first = result[result[COL_OFFSET] == -1].iloc[0]
        assert int(first[COL_SAMPLE_COUNT]) == 2
        assert float(first[COL_MEAN]) == pytest.approx(0.02, abs=EXACT_TOLERANCE)

    def test_값이_없는_날은_표본에서_빠진다(self) -> None:
        """
        목적: 경계 조건 — 첫날처럼 등락을 낼 수 없는 날의 처리를 고정한다

        Given: 일간 등락이 비어 있는 행이 섞인 입력
        When: 집계하면
        Then: 그 행은 표본에 들어가지 않는다
        """
        # Given
        frame = pd.DataFrame({COL_OFFSET: [-1.0, -1.0], COL_DAILY_RETURN: [float("nan"), 0.03]})

        # When
        result = _aggregate_daily(frame, COL_OFFSET)

        # Then
        assert int(result[COL_SAMPLE_COUNT].iloc[0]) == 1

    def test_표본이_하나도_없으면_빈_표를_돌려준다(self) -> None:
        """
        목적: 경계 조건 — 표본 0건이 예외가 아니라 정상 결과임을 고정한다

        Given: 일간 등락이 전부 비어 있는 입력
        When: 집계하면
        Then: 같은 스키마의 빈 표가 나온다
        """
        # Given
        frame = pd.DataFrame({COL_OFFSET: [-1.0], COL_DAILY_RETURN: [float("nan")]})

        # When
        result = _aggregate_daily(frame, COL_OFFSET)

        # Then
        assert result.empty
        assert COL_OFFSET in result.columns


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


class TestMasks:
    """국면·위칭 축이 신호일만 자르는지 고정한다."""

    def test_국면은_구간_밖의_날을_뺀다(self) -> None:
        """
        목적: 국면 경계가 날짜 기준으로 적용됨을 고정한다

        Given: 2019-09-22 와 2019-09-23
        When: 위클리 이후 국면 마스크를 만들면
        Then: 앞날은 False, 뒷날은 True
        """
        # Given
        dates = pd.Series(pd.to_datetime(["2019-09-20", "2019-09-23"]))

        # When
        mask = _regime_mask(dates, Regime(label="위클리", start="2019-09-23", end=None))

        # Then
        assert mask.tolist() == [False, True]

    def test_위칭_축은_만기월로_가른다(self) -> None:
        """
        목적: 동시만기 분리가 **배정된 만기일의 달**로 이뤄짐을 고정한다

        날짜의 달이 아니다 — 만기 다음 달로 넘어간 날도 자기가 붙은 만기의 성격을 따라야 한다.

        Given: 만기월 3월과 4월
        When: 동시만기 축과 그 여집합 축을 만들면
        Then: 3월만 동시만기이고 여집합은 반대다
        """
        # Given
        expiry_months = pd.Series([3, 4])

        # When
        witching = _witching_mask(expiry_months, WitchingGroup(label="동시만기", months=(3, 6, 9, 12)))
        others = _witching_mask(expiry_months, WitchingGroup(label="단독", months=(3, 6, 9, 12), exclude=True))

        # Then
        assert witching.tolist() == [True, False]
        assert others.tolist() == [False, True]

    def test_전체_축은_아무것도_자르지_않는다(self) -> None:
        """
        목적: 경계 조건 — 자르지 않는 축의 정의를 고정한다

        Given: 만기월 3월과 4월
        When: 전체 축 마스크를 만들면
        Then: 전부 True
        """
        # Given
        expiry_months = pd.Series([3, 4])

        # When
        mask = _witching_mask(expiry_months, WitchingGroup(label="전체", months=None))

        # Then
        assert mask.all()


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
