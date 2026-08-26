"""사양서 §14 분할 분석의 계약을 고정한다.

**전체 기간 평균은 구조적 차이를 가린다.** 사양서 §14 가 그렇게 적었고, 실측이 그 이유를 보여줬다 —
환전 2005~ 는 「분할매수 후 보유」에 −309만원 지지만 그 차이가 어느 국면에서 났는지는
전 기간 요약에 안 나온다.

핵심 계약은 다섯 가지다.

- **구간을 자를 때 직전 거래일을 앵커로 포함한다** (결정 C109). 앵커가 없으면 경계일의 수익률이
  **어느 구간에도 안 들어간다** — 예외가 나지 않고 조용히 사라진다
- **연속 분할은 전 기간을 빠짐없이 덮고 겹치지 않는다.** 사양서 8구간은 반대로
  **겹침과 빠짐을 그대로 둔다** — 원문을 재는 표라 그것이 사실이다 (결정 C107)
- **수익률이 1개 미만이면 지표가 `None` 이다** (결정 C91). 실측에서 금리차 부호 구간 39개 중
  1거래일짜리가 여럿이라 이 경계가 실제로 걸린다
- **금리차 부호는 원지표 DTB3 − CD91 이고 동률(0)은 별도 칸이다** (결정 C110).
  실수령 금리로 재면 상품 스프레드와 하한이 걸려 **금리차가 아니라 상품 조건의 부호**가 된다
- **구간이 곡선 범위 밖이면 조용히 빠지지 않는다.** ETF 두 경로는 2017~ 이라 사양서 8구간 중
  앞 다섯이 비는데, 빼 버리면 「기간 밖」과 「재고 0」이 구분되지 않는다
"""

import pandas as pd
import pytest

from verify_lab.strategy.grid.constants import (
    RATE_GAP_EQUAL,
    RATE_GAP_NEGATIVE,
    RATE_GAP_POSITIVE,
    REGIME_AXIS_CONTIGUOUS,
    REGIME_AXIS_RATE_GAP,
    REGIME_AXIS_SPEC,
)
from verify_lab.strategy.grid.regimes import (
    CONTIGUOUS_REGIMES,
    SHORT_EPISODE_DAYS,
    SPEC_REGIMES,
    Regime,
    evaluate_regimes,
    rate_gap_regimes,
    rate_gap_summaries,
    slice_curve,
)

# 비율 비교 허용오차
RATE_TOLERANCE = 1e-9

# 전략 곡선을 가리키는 키. 벤치마크 키와 같은 평면에 놓인다
STRATEGY_KEY = "strategy"


def _curve(values: list[float], *, start: str = "2020-01-01") -> pd.Series:
    """거래일 하루 간격의 총자산 곡선을 만든다."""
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def _flat_rf(curve: pd.Series, *, rate: float = 0.0) -> pd.Series:
    """곡선과 같은 인덱스의 무위험 수익률 계열 (연%)."""
    return pd.Series(rate, index=curve.index, dtype=float)


def _regime(name: str, start: str, end: str, *, axis: str = REGIME_AXIS_CONTIGUOUS, nature: str = "검사") -> Regime:
    """검사용 국면 하나."""
    return Regime(axis=axis, name=name, nature=nature, start=pd.Timestamp(start), end=pd.Timestamp(end))


class TestSliceCurve:
    """구간 슬라이스의 계약 — 앵커 규칙이 여기서 고정된다."""

    def test_직전_거래일을_앵커로_포함한다(self) -> None:
        """
        목적: 결정 C109 — 구간의 첫 수익률이 경계를 넘어 계산되도록 앵커를 붙인다

        Given: 5거래일 곡선과 3번째 날부터 시작하는 구간
        When: 구간을 자른다
        Then: 잘린 곡선의 첫 날이 **구간 시작 하루 전**이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0, 130.0, 140.0])

        # When
        sliced = slice_curve(curve, start=pd.Timestamp("2020-01-03"), end=pd.Timestamp("2020-01-05"))

        # Then
        assert sliced.index[0] == pd.Timestamp("2020-01-02"), "앵커가 붙지 않으면 1월 3일의 수익률이 사라집니다"
        assert sliced.index[-1] == pd.Timestamp("2020-01-05")
        assert len(sliced) == 4

    def test_첫_구간은_앵커가_없어_곡선_첫날부터다(self) -> None:
        """
        목적: 곡선 앞에 데이터가 없으면 앵커를 만들어내지 않는다

        Given: 곡선 첫날부터 시작하는 구간
        When: 구간을 자른다
        Then: 잘린 곡선의 첫 날이 곡선의 첫 날이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])

        # When
        sliced = slice_curve(curve, start=pd.Timestamp("2020-01-01"), end=pd.Timestamp("2020-01-02"))

        # Then
        assert sliced.index[0] == pd.Timestamp("2020-01-01")
        assert len(sliced) == 2

    def test_연속_분할은_수익률을_하나도_잃지_않는다(self) -> None:
        """
        목적: **앵커 규칙의 존재 이유** — 구간을 이어 붙이면 전체 수익률 개수가 정확히 복원된다

        Given: 10거래일 곡선을 겹치지 않게 세 구간으로 나눈다
        When: 구간마다 앵커를 포함해 자른다
        Then: 구간별 수익률 개수의 합이 **전체 수익률 개수와 같다**
        """
        # Given
        curve = _curve([100.0 + index for index in range(10)])
        regimes = (
            _regime("A", "2020-01-01", "2020-01-03"),
            _regime("B", "2020-01-04", "2020-01-07"),
            _regime("C", "2020-01-08", "2020-01-10"),
        )

        # When
        returns_per_regime = [len(slice_curve(curve, start=item.start, end=item.end)) - 1 for item in regimes]

        # Then
        assert sum(returns_per_regime) == len(curve) - 1, "경계일의 수익률이 어느 구간에도 안 들어갔습니다"

    def test_곡선_범위_밖이면_빈_결과다(self) -> None:
        """
        목적: 범위 밖 구간을 예외로 끊지 않고 빈 것으로 돌려준다 (ETF 경로의 앞 다섯 구간)

        Given: 곡선보다 이른 구간
        When: 구간을 자른다
        Then: 빈 곡선이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0], start="2020-01-01")

        # When
        sliced = slice_curve(curve, start=pd.Timestamp("2010-01-01"), end=pd.Timestamp("2010-12-31"))

        # Then
        assert sliced.empty

    def test_거꾸로_된_구간은_거부한다(self) -> None:
        """
        목적: 시작이 종료보다 늦은 구간은 입력 오류다

        Given: 종료가 시작보다 이른 구간
        When: 구간을 자른다
        Then: `ValueError`
        """
        # Given
        curve = _curve([100.0, 110.0])

        # When / Then
        with pytest.raises(ValueError, match="구간"):
            slice_curve(curve, start=pd.Timestamp("2020-01-02"), end=pd.Timestamp("2020-01-01"))


class TestRegimeDefinitions:
    """사양서 §14 축1 의 두 구간표 — 겹침 정책이 서로 반대다."""

    def test_연속_분할은_겹치지_않고_빈틈도_없다(self) -> None:
        """
        목적: 결정 C108 — 연속 분할이 전 기간을 빠짐없이 덮는다

        Given: 연속 분할 구간표
        When: 인접한 두 구간을 이어 본다
        Then: 앞 구간의 종료 다음 날이 뒤 구간의 시작이다
        """
        # Given
        regimes = CONTIGUOUS_REGIMES

        # When / Then
        for earlier, later in zip(regimes, regimes[1:], strict=False):
            assert earlier.end < later.start, f"{earlier.name} 과 {later.name} 이 겹칩니다"
            assert (later.start - earlier.end).days == 1, f"{earlier.name} 과 {later.name} 사이가 빕니다"

    def test_연속_분할이_매매_시작일부터_덮는다(self) -> None:
        """
        목적: 첫 구간이 사양서 §11.4 의 매매 시작일보다 늦게 시작하면 앞부분이 통째로 빠진다

        Given: 연속 분할 구간표
        When: 첫 구간의 시작을 본다
        Then: 2005-01-01 이하다
        """
        # Given / When
        first = CONTIGUOUS_REGIMES[0]

        # Then
        assert first.start <= pd.Timestamp("2005-01-01")

    def test_사양서_구간은_겹침을_그대로_둔다(self) -> None:
        """
        목적: 결정 C107 — 원문을 재는 표라 겹침이 사실이다. 고쳐서 재면 원문을 잰 것이 아니다

        Given: 사양서 8구간
        When: 겹치는 쌍을 센다
        Then: 하나 이상 있다 (2009·2014·2016·2018)
        """
        # Given
        regimes = SPEC_REGIMES

        # When
        overlaps = [
            (earlier.name, later.name)
            for earlier, later in zip(regimes, regimes[1:], strict=False)
            if later.start <= earlier.end
        ]

        # Then
        assert overlaps, "사양서 구간의 겹침이 사라졌습니다 - 원문을 고쳐 쓴 것입니다"

    def test_사양서_구간이_여덟_개다(self) -> None:
        """
        목적: 사양서 §14 축1 의 표가 8행이다

        Given / When: 사양서 구간표
        Then: 8개이고 축 이름이 전부 같다
        """
        # Given / When / Then
        assert len(SPEC_REGIMES) == 8
        assert {item.axis for item in SPEC_REGIMES} == {REGIME_AXIS_SPEC}

    def test_연속_분할도_여덟_개이며_사양서_성격을_유지한다(self) -> None:
        """
        목적: 결정 C108 — 경계만 겹침 없이 옮기고 사양서의 성격 라벨은 그대로 쓴다

        Given / When: 연속 분할 구간표
        Then: 8개이고 성격이 전부 사양서 표에 있는 것이다
        """
        # Given / When
        natures = {item.nature for item in CONTIGUOUS_REGIMES}

        # Then
        assert len(CONTIGUOUS_REGIMES) == 8
        assert {item.axis for item in CONTIGUOUS_REGIMES} == {REGIME_AXIS_CONTIGUOUS}
        assert natures <= {item.nature for item in SPEC_REGIMES}, "사양서에 없는 성격을 새로 만들었습니다"


class TestRateGapRegimes:
    """사양서 §14 축2 — 부호가 같은 날이 이어지는 구간."""

    def test_부호_전환마다_구간이_갈린다(self) -> None:
        """
        목적: 산식 고정 — 부호가 바뀌는 지점에서만 구간이 갈린다

        Given: (+) 3일 → (−) 2일 → (+) 1일 인 금리 계열
        When: 부호 구간을 만든다
        Then: 구간이 3개이고 길이가 3·2·1 이다
        """
        # Given
        index = pd.date_range("2020-01-01", periods=6, freq="D")
        tbill = pd.Series([2.0, 2.0, 2.0, 1.0, 1.0, 2.0], index=index, dtype=float)
        cd91 = pd.Series([1.0, 1.0, 1.0, 2.0, 2.0, 1.0], index=index, dtype=float)

        # When
        regimes = rate_gap_regimes(tbill, cd91)

        # Then
        assert [item.nature for item in regimes] == [RATE_GAP_POSITIVE, RATE_GAP_NEGATIVE, RATE_GAP_POSITIVE]
        assert [item.start for item in regimes] == [index[0], index[3], index[5]]
        assert [item.end for item in regimes] == [index[2], index[4], index[5]]

    def test_동률은_별도_칸이다(self) -> None:
        """
        목적: 결정 C110 — 동률은 (+)의 정의에도 (−)의 정의에도 해당하지 않는다.
              실측에서 2005~ 에 13일 존재한다

        Given: 가운데 하루가 정확히 같은 금리 계열
        When: 부호 구간을 만든다
        Then: 그 하루가 동률 구간으로 따로 잡힌다
        """
        # Given
        index = pd.date_range("2020-01-01", periods=3, freq="D")
        tbill = pd.Series([2.0, 1.0, 0.5], index=index, dtype=float)
        cd91 = pd.Series([1.0, 1.0, 1.0], index=index, dtype=float)

        # When
        regimes = rate_gap_regimes(tbill, cd91)

        # Then
        assert [item.nature for item in regimes] == [RATE_GAP_POSITIVE, RATE_GAP_EQUAL, RATE_GAP_NEGATIVE]

    def test_축_이름이_금리차다(self) -> None:
        """
        목적: 세 구간표가 한 CSV 에 섞이므로 축 이름으로 갈린다

        Given: 부호가 한 번도 안 바뀌는 계열
        When: 부호 구간을 만든다
        Then: 축 이름이 금리차다
        """
        # Given
        index = pd.date_range("2020-01-01", periods=3, freq="D")

        # When
        regimes = rate_gap_regimes(pd.Series(2.0, index=index, dtype=float), pd.Series(1.0, index=index, dtype=float))

        # Then
        assert [item.axis for item in regimes] == [REGIME_AXIS_RATE_GAP]

    def test_두_계열의_인덱스가_다르면_거부한다(self) -> None:
        """
        목적: 정렬이 어긋난 계열로 부호를 재면 날짜가 밀린 채 조용히 계산된다

        Given: 길이가 다른 두 계열
        When: 부호 구간을 만든다
        Then: `ValueError`
        """
        # Given
        tbill = pd.Series(2.0, index=pd.date_range("2020-01-01", periods=3), dtype=float)
        cd91 = pd.Series(1.0, index=pd.date_range("2020-01-01", periods=2), dtype=float)

        # When / Then
        with pytest.raises(ValueError, match="어긋"):
            rate_gap_regimes(tbill, cd91)

    def test_부호별_요약이_구간_수와_최장_길이를_함께_낸다(self) -> None:
        """
        목적: 결정 C111 — 실측에서 39개 구간 중 31개가 20일 미만이라
              **일수만 보면 독립 표본 수를 39개로 오독한다**

        Given: (+) 4일 한 구간과 (+) 1일 한 구간, 사이에 (−) 1일
        When: 부호별 요약을 만든다
        Then: (+) 의 구간 수가 2, 총 일수가 5, 최장이 4, 20일 미만 구간이 2 다
        """
        # Given
        index = pd.date_range("2020-01-01", periods=6, freq="D")
        tbill = pd.Series([2.0, 2.0, 2.0, 2.0, 1.0, 2.0], index=index, dtype=float)
        cd91 = pd.Series([1.0, 1.0, 1.0, 1.0, 2.0, 1.0], index=index, dtype=float)

        # When
        summaries = {item.sign: item for item in rate_gap_summaries(rate_gap_regimes(tbill, cd91))}

        # Then
        positive = summaries[RATE_GAP_POSITIVE]
        assert positive.episodes == 2
        assert positive.trading_days == 5
        assert positive.longest_days == 4
        assert positive.short_episodes == 2, f"{SHORT_EPISODE_DAYS}거래일 미만 구간을 세지 않았습니다"


class TestEvaluateRegimes:
    """구간별 지표 — 곡선 하나만 받는 계약을 그대로 쓴다."""

    def test_구간마다_곡선별_지표가_나온다(self) -> None:
        """
        목적: 전략과 벤치마크가 **같은 구간**으로 잘려야 "어느 국면에서 지는가"에 답한다

        Given: 전략과 벤치마크 곡선 각각, 그리고 두 구간
        When: 구간별 지표를 낸다
        Then: 구간마다 두 곡선의 총수익률이 손계산 값과 같다
        """
        # Given
        strategy = _curve([100.0, 110.0, 121.0, 121.0])
        benchmark = _curve([100.0, 100.0, 100.0, 200.0])
        regimes = (
            _regime("앞", "2020-01-01", "2020-01-02"),
            _regime("뒤", "2020-01-03", "2020-01-04"),
        )

        # When
        results = evaluate_regimes(
            {STRATEGY_KEY: strategy, "bench": benchmark},
            risk_free=_flat_rf(strategy),
            regimes=regimes,
        )

        # Then
        first, second = results
        first_strategy = first.metrics[STRATEGY_KEY]
        second_strategy, second_bench = second.metrics[STRATEGY_KEY], second.metrics["bench"]
        assert first_strategy is not None and second_strategy is not None and second_bench is not None
        assert first_strategy.total_return_rate == pytest.approx(0.10, abs=RATE_TOLERANCE)
        # 뒤 구간은 앵커(1월 2일 110)에서 시작해 121 → 121 이므로 +10%
        assert second_strategy.total_return_rate == pytest.approx(0.10, abs=RATE_TOLERANCE)
        assert second_bench.total_return_rate == pytest.approx(1.00, abs=RATE_TOLERANCE)

    def test_수익률이_없으면_지표가_None_이다(self) -> None:
        """
        목적: 결정 C91 — 1거래일 구간은 수익률이 0개다. 0 으로 답하면 "제자리였다"로 읽힌다

        Given: 곡선 첫날 하루짜리 구간 (앵커가 없어 수익률이 0개)
        When: 구간별 지표를 낸다
        Then: 지표가 `None` 이고 수익률 개수가 0 이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])
        regimes = (_regime("하루", "2020-01-01", "2020-01-01"),)

        # When
        results = evaluate_regimes({STRATEGY_KEY: curve}, risk_free=_flat_rf(curve), regimes=regimes)

        # Then
        assert results[0].returns == 0
        assert results[0].metrics[STRATEGY_KEY] is None

    def test_범위_밖_구간은_빠지지_않고_남는다(self) -> None:
        """
        목적: 표본 보존 — ETF 두 경로는 사양서 8구간 중 앞 다섯이 빈다.
              빼 버리면 「기간 밖」과 「재고 0」이 구분되지 않는다

        Given: 곡선보다 이른 구간 하나와 곡선 안의 구간 하나
        When: 구간별 지표를 낸다
        Then: 결과가 두 줄이고 앞 줄은 거래일 0 · 지표 `None` 이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0], start="2020-01-01")
        regimes = (
            _regime("기간 밖", "2010-01-01", "2010-12-31"),
            _regime("기간 안", "2020-01-02", "2020-01-03"),
        )

        # When
        results = evaluate_regimes({STRATEGY_KEY: curve}, risk_free=_flat_rf(curve), regimes=regimes)

        # Then
        assert len(results) == 2, "구간이 조용히 사라졌습니다"
        assert results[0].trading_days == 0
        assert results[0].metrics[STRATEGY_KEY] is None
        assert results[1].metrics[STRATEGY_KEY] is not None

    def test_곡선과_무위험_수익률의_인덱스가_다르면_거부한다(self) -> None:
        """
        목적: rf 가 어긋나면 Sharpe 가 조용히 다른 것을 잰다

        Given: 곡선보다 짧은 rf 계열
        When: 구간별 지표를 낸다
        Then: `ValueError`
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])
        risk_free = _flat_rf(curve).iloc[:2]

        # When / Then
        with pytest.raises(ValueError, match="어긋"):
            evaluate_regimes(
                {STRATEGY_KEY: curve},
                risk_free=risk_free,
                regimes=(_regime("전체", "2020-01-01", "2020-01-03"),),
            )

    def test_곡선들의_인덱스가_다르면_거부한다(self) -> None:
        """
        목적: 벤치마크가 전략과 다른 거래일을 겪으면 구간 비교가 성립하지 않는다

        Given: 전략보다 짧은 벤치마크 곡선
        When: 구간별 지표를 낸다
        Then: `ValueError`
        """
        # Given
        strategy = _curve([100.0, 110.0, 120.0])
        benchmark = _curve([100.0, 110.0])

        # When / Then
        with pytest.raises(ValueError, match="어긋"):
            evaluate_regimes(
                {STRATEGY_KEY: strategy, "bench": benchmark},
                risk_free=_flat_rf(strategy),
                regimes=(_regime("전체", "2020-01-01", "2020-01-03"),),
            )

    def test_뒤를_잘라내도_앞_구간의_지표가_같다(self) -> None:
        """
        목적: **look-ahead 감시** — 구간 지표는 그 구간까지의 곡선으로만 정해진다.
              상태 구동이라도 예외가 아니다

        Given: 10거래일 곡선과 앞쪽 구간 하나
        When: 곡선의 뒤를 잘라낸 것과 전체로 각각 지표를 낸다
        Then: 두 지표가 한 자리도 다르지 않다
        """
        # Given
        whole = _curve([100.0, 105.0, 103.0, 110.0, 108.0, 115.0, 120.0, 118.0, 125.0, 130.0])
        truncated = whole.iloc[:5]
        regimes = (_regime("앞", "2020-01-02", "2020-01-04"),)

        # When
        from_whole = evaluate_regimes({STRATEGY_KEY: whole}, risk_free=_flat_rf(whole), regimes=regimes)
        from_truncated = evaluate_regimes({STRATEGY_KEY: truncated}, risk_free=_flat_rf(truncated), regimes=regimes)

        # Then
        whole_metrics = from_whole[0].metrics[STRATEGY_KEY]
        truncated_metrics = from_truncated[0].metrics[STRATEGY_KEY]
        assert whole_metrics is not None and truncated_metrics is not None
        assert truncated_metrics.total_return_rate == pytest.approx(
            whole_metrics.total_return_rate, abs=RATE_TOLERANCE
        ), "뒤 데이터가 앞 구간의 지표를 바꿨습니다 - 미래를 참조하고 있습니다"
        assert truncated_metrics.max_drawdown == pytest.approx(whole_metrics.max_drawdown, abs=RATE_TOLERANCE)
