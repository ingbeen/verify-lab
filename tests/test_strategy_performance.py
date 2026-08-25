"""일별 총자산 곡선에서 내는 표준 지표의 계약을 고정한다.

**지표는 틀려도 그럴듯해 보인다.** 특히 Sharpe 는 무위험 수익률 하나로 3배가 흔들리는데
자릿수가 그대로라 눈으로는 구분되지 않는다. 사양서 §13.1 이 `rf = 0` 을 명시적으로 금지하고
§15.3 이 `Sharpe > 1.0` 을 Red Flag 로 둔 이유가 그것이다.

핵심 계약은 다섯 가지다.

- **입력은 곡선과 무위험 수익률 계열 둘뿐이다.** 어떤 매매법이 그 곡선을 만들었는지 몰라야
  이벤트 구동·상태 기계가 같은 표에 오른다 (결정 B1)
- **rf 는 달력일 간격을 반영한다.** 두 거래일 사이가 주말이면 3일이고, 하루치만 주면
  rf 가 3분의 2로 깎여 Sharpe 가 3배로 부풀려진다
- **MDD 는 평가액 기준**이며 최저점과 직전 신고점의 날짜를 함께 낸다
- **연환산은 250 거래일**이고 rf 의 일할은 365 달력일이다. 둘은 다른 계수이며 그 어긋남이 사실이다
- **계산 불가는 조용히 0 으로 답하지 않는다** — MDD 가 0 이면 Calmar 는 `None` 이다
"""

import inspect
import math

import numpy as np
import pandas as pd
import pytest

from verify_lab.strategy import performance
from verify_lab.strategy.performance import TRADING_DAYS_PER_YEAR, evaluate_curve

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 통계량 허용오차
STAT_TOLERANCE = 1e-9


def _curve(values: list[float], *, start: str = "2020-01-01", freq: str = "B") -> pd.Series:
    """날짜 인덱스를 가진 총자산 곡선을 만든다."""
    return pd.Series(
        values,
        index=pd.bdate_range(start, periods=len(values)) if freq == "B" else pd.date_range(start, periods=len(values)),
    )


def _flat_rate(curve: pd.Series, annual_pct: float) -> pd.Series:
    """전 구간 고정 연이율 계열. 0 이면 무위험 수익률이 없는 상태다."""
    return pd.Series(annual_pct, index=curve.index, dtype=float)


class TestTotalReturnAndCagr:
    """총수익률과 CAGR 산식을 손계산으로 박는다."""

    def test_총수익률은_마지막을_처음으로_나눈_값이다(self) -> None:
        """
        목적: 총수익률의 정의를 고정한다 (사양서 §13.1)

        Given: 1억에서 시작해 1.5억으로 끝나는 곡선
        When: 지표를 낸다
        Then: 총수익률이 50% 다
        """
        # Given
        curve = _curve([100_000_000.0, 120_000_000.0, 150_000_000.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.total_return_rate == pytest.approx(0.5, abs=EXACT_TOLERANCE)

    def test_CAGR의_지수는_거래일_수_빼기_1이다(self) -> None:
        """
        목적: 연환산 계수를 고정한다 (결정 C9 — 250 거래일)

        Given: 거래일 251일 동안 총자산이 두 배가 되는 곡선
        When: 지표를 낸다
        Then: CAGR 이 `2 ** (250/250) − 1 = 100%` 다

        Note:
            분모는 **수익률의 개수**(거래일 수 − 1)다. 거래일 수를 그대로 쓰면
            짧은 구간에서 연환산이 조용히 작아진다
        """
        # Given — 251개 점이면 수익률이 250개다
        curve = pd.Series(
            np.geomspace(100_000_000.0, 200_000_000.0, 251),
            index=pd.bdate_range("2020-01-01", periods=251),
        )

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.cagr == pytest.approx(1.0, abs=STAT_TOLERANCE)
        assert actual.trading_days == 251

    def test_손실_구간의_CAGR은_음수다(self) -> None:
        """
        목적: 부호를 고정한다 — 지표가 손실을 감추지 않는다

        Given: 총자산이 줄어드는 곡선
        When: 지표를 낸다
        Then: 총수익률과 CAGR 이 모두 음수다
        """
        # Given
        curve = _curve([100_000_000.0, 95_000_000.0, 90_000_000.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.total_return_rate < 0
        assert actual.cagr < 0


class TestMaxDrawdown:
    """MDD 를 평가액 기준으로 고정한다 (사양서 §13.1 — 실현손익 기준 금지)."""

    def test_누적_신고점_대비_최대_낙폭이다(self) -> None:
        """
        목적: MDD 산식을 손계산으로 박는다

        Given: 100 → 120 → 90 → 130 으로 움직이는 곡선
        When: 지표를 낸다
        Then: MDD 가 `90/120 − 1 = −25%` 다

        Note:
            처음(100) 대비가 아니라 **직전 신고점(120)** 대비다. 시작값 대비로 재면
            한 번 올랐다가 빠진 낙폭이 통째로 사라진다
        """
        # Given
        curve = _curve([100.0, 120.0, 90.0, 130.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.max_drawdown == pytest.approx(-0.25, abs=EXACT_TOLERANCE)

    def test_최저점과_직전_신고점의_날짜를_함께_낸다(self) -> None:
        """
        목적: MDD 를 사용자가 차트로 대조할 수 있게 함을 고정한다

        Given: 둘째 날이 신고점이고 셋째 날이 최저점인 곡선
        When: 지표를 낸다
        Then: 두 날짜가 각각 담겨 있다
        """
        # Given
        curve = _curve([100.0, 120.0, 90.0, 130.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.max_drawdown_date == curve.index[2]
        assert actual.peak_date == curve.index[1]

    def test_단조_증가_곡선의_MDD는_0이다(self) -> None:
        """
        목적: 엣지 케이스 — 낙폭이 없는 곡선을 고정한다

        Given: 계속 오르기만 하는 곡선
        When: 지표를 낸다
        Then: MDD 가 0 이다

        Note:
            사양서 §15.3 은 **자산곡선 단조 증가 자체를 Red Flag** 로 둔다
            (실현손익만 집계했다는 신호다). 지표는 그것을 숨기지 않고 0 을 그대로 낸다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.max_drawdown == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_MDD가_0이면_Calmar가_None이다(self) -> None:
        """
        목적: 0 으로 나누는 상황을 조용히 통과시키지 않음을 고정한다 (결정 C91)

        Given: 낙폭이 없는 곡선
        When: 지표를 낸다
        Then: Calmar 가 None 이다 — 0 이나 무한대가 아니다

        Note:
            0 을 돌려주면 "위험 대비 수익이 없다"로, 무한대를 돌려주면
            "완벽하다"로 읽힌다. 둘 다 **계산할 수 없다**는 사실과 다르다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.calmar is None

    def test_Calmar는_CAGR을_MDD_절댓값으로_나눈_값이다(self) -> None:
        """
        목적: Calmar 산식을 고정한다 (사양서 §13.1)

        Given: 낙폭이 있는 곡선
        When: 지표를 낸다
        Then: `CAGR ÷ |MDD|` 다
        """
        # Given
        curve = _curve([100.0, 120.0, 90.0, 130.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.calmar is not None
        assert actual.calmar == pytest.approx(actual.cagr / abs(actual.max_drawdown), abs=STAT_TOLERANCE)


class TestRiskFreeRate:
    """무위험 수익률의 적용 방식을 고정한다 (결정 C87·C88).

    **여기가 이 모듈에서 가장 조용히 틀리는 자리다.** rf 를 잘못 주면 Sharpe 만 달라지고
    다른 지표는 멀쩡하므로 대조할 기준이 없다.
    """

    def test_rf는_달력일_간격만큼_붙는다(self) -> None:
        """
        목적: 결정 C88 을 고정한다 — 거래일 균등 분배가 아니다

        Given: 금요일·월요일 두 거래일(간격 3일)과 연 36.5% 의 rf
        When: 지표를 낸다
        Then: 그 구간의 rf 가 하루치(0.1%)가 아니라 3일치(0.3%)다

        Note:
            전략 곡선의 그 하루치 변동은 **주말을 포함한 3일치**다. rf 를 하루치만 주면
            평균 간격 1.48일인 원달러 달력에서 rf 가 3분의 2로 깎이고
            **Sharpe 가 3배로 부풀려진다**
        """
        # Given — 2020-01-03 은 금요일, 2020-01-06 은 월요일이다
        curve = pd.Series([100.0, 100.3], index=pd.DatetimeIndex(["2020-01-03", "2020-01-06"]))

        # When — 연 36.5% 는 하루 0.1% 다
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 36.5))

        # Then — 수익률 0.3% 에서 rf 0.3% 를 빼면 초과수익이 정확히 0 이다
        assert actual.excess_return_mean == pytest.approx(0.0, abs=STAT_TOLERANCE)

    def test_rf를_0으로_주면_Sharpe가_커진다(self) -> None:
        """
        목적: 사양서 §13.1 이 `rf = 0` 을 금지한 이유를 테스트가 보여준다

        Given: 같은 곡선에 rf=0 과 rf=연 2.35% 를 각각 준다
        When: 지표를 낸다
        Then: rf=0 쪽의 Sharpe 가 더 크다

        Note:
            "원화 예금만 해도 얻었을 수익"이 전략 성과로 둔갑하는 것이 §13.1 의 우려다.
            이 매매법은 **수익의 3분의 2가 이자**라 그 둔갑의 크기가 특히 크다
        """
        # Given
        curve = pd.Series(
            np.geomspace(100_000_000.0, 130_000_000.0, 300) * (1.0 + np.sin(np.arange(300)) * 0.002),
            index=pd.bdate_range("2020-01-01", periods=300),
        )

        # When
        without_rf = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))
        with_rf = evaluate_curve(curve, risk_free=_flat_rate(curve, 2.35))

        # Then
        assert without_rf.sharpe is not None
        assert with_rf.sharpe is not None
        assert without_rf.sharpe > with_rf.sharpe

    def test_rf_평균과_rf_복리_수익률을_함께_낸다(self) -> None:
        """
        목적: Sharpe 하나만으로는 "얼마나 이겼나"를 알 수 없음을 지표 구성으로 고정한다

        Given: 연 2% 고정 rf 와 500 거래일 곡선
        When: 지표를 낸다
        Then: rf 평균이 2% 이고, rf 를 복리로 굴린 총수익률이 양수다

        Note:
            §13.3 의 벤치마크 「원화 파킹 100%」가 정식으로 답하기 전까지
            이 값이 그 자리를 대신한다
        """
        # Given
        curve = pd.Series(
            np.geomspace(100_000_000.0, 130_000_000.0, 500),
            index=pd.bdate_range("2020-01-01", periods=500),
        )

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 2.0))

        # Then
        assert actual.risk_free_mean == pytest.approx(2.0, abs=EXACT_TOLERANCE)
        assert actual.risk_free_return_rate > 0.0

    def test_rf_계열이_곡선과_어긋나면_거부한다(self) -> None:
        """
        목적: 조용히 정렬을 맞추지 않음을 고정한다

        Given: 곡선보다 짧은 rf 계열
        When: 지표를 낸다
        Then: ValueError

        Note:
            길이를 맞춰 주면 **어느 날의 rf 가 어느 날에 붙었는지** 알 수 없게 된다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])

        # When / Then
        with pytest.raises(ValueError, match="무위험 수익률"):
            evaluate_curve(curve, risk_free=pd.Series([1.0, 1.0], index=curve.index[:2]))


class TestSharpeAndSortino:
    """위험조정 지표의 산식을 고정한다 (결정 C89·C90)."""

    def test_Sharpe는_초과수익_평균을_표준편차로_나눠_연환산한다(self) -> None:
        """
        목적: Sharpe 산식과 연환산 계수를 손계산으로 박는다

        Given: 오르내리는 곡선과 rf=0
        When: 지표를 낸다
        Then: `초과수익 평균 ÷ 표본 표준편차 × √250` 이다
        """
        # Given
        curve = _curve([100.0, 102.0, 101.0, 104.0, 103.0, 106.0])
        returns = curve.to_numpy()[1:] / curve.to_numpy()[:-1] - 1.0

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        expected = returns.mean() / returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
        assert actual.sharpe == pytest.approx(expected, abs=STAT_TOLERANCE)

    def test_표본_표준편차를_쓴다(self) -> None:
        """
        목적: 결정 C90 을 고정한다 — 모표준편차(ddof=0)가 아니다

        Given: 표본이 적어 두 정의의 차이가 드러나는 곡선
        When: 지표를 낸다
        Then: 변동성이 표본 표준편차(ddof=1) 기준이다
        """
        # Given
        curve = _curve([100.0, 102.0, 101.0, 104.0])
        returns = curve.to_numpy()[1:] / curve.to_numpy()[:-1] - 1.0

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.volatility == pytest.approx(
            returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR), abs=STAT_TOLERANCE
        )
        assert actual.volatility != pytest.approx(
            returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR), abs=STAT_TOLERANCE
        )

    def test_Sortino의_하방편차는_전체_관측_수로_나눈다(self) -> None:
        """
        목적: 결정 C89 를 고정한다 — 하방 관측치 개수가 분모가 아니다

        Given: 오르내리는 곡선과 rf=0
        When: 지표를 낸다
        Then: 하방편차가 `sqrt(mean(min(초과수익, 0)²))` 이다

        Note:
            하방 개수로 나누면 **하락이 드문 곡선일수록 하방편차가 커져** Sortino 가
            작아진다. 방향이 직관과 반대라 조용히 틀린다
        """
        # Given
        curve = _curve([100.0, 102.0, 101.0, 104.0, 103.0, 106.0])
        returns = curve.to_numpy()[1:] / curve.to_numpy()[:-1] - 1.0

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        downside = math.sqrt(float(np.mean(np.minimum(returns, 0.0) ** 2)))
        expected = returns.mean() / downside * math.sqrt(TRADING_DAYS_PER_YEAR)
        assert actual.sortino == pytest.approx(expected, abs=STAT_TOLERANCE)

    def test_하락이_없으면_Sortino가_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 0 으로 나누는 상황을 고정한다

        Given: 단조 증가 곡선과 rf=0 (초과수익이 전부 양수다)
        When: 지표를 낸다
        Then: Sortino 가 None 이다
        """
        # Given
        curve = _curve([100.0, 110.0, 120.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.sortino is None

    def test_변동이_없으면_Sharpe가_None이다(self) -> None:
        """
        목적: 엣지 케이스 — 표준편차가 0 인 곡선을 고정한다

        Given: 값이 전혀 변하지 않는 곡선
        When: 지표를 낸다
        Then: Sharpe 가 None 이다
        """
        # Given
        curve = _curve([100.0, 100.0, 100.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.sharpe is None


class TestValidation:
    """입력 검증 정책을 고정한다."""

    def test_거래일이_이틀이면_계산한다(self) -> None:
        """
        목적: 엣지 케이스 — 최소 길이를 고정한다

        Given: 거래일 이틀짜리 곡선
        When: 지표를 낸다
        Then: 예외 없이 총수익률이 나온다
        """
        # Given
        curve = _curve([100.0, 110.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.total_return_rate == pytest.approx(0.1, abs=EXACT_TOLERANCE)

    def test_거래일이_이틀이면_변동성_지표가_None이다(self) -> None:
        """
        목적: 표본 표준편차가 정의되지 않는 입력에서 **NaN 이 새지 않음**을 고정한다

        Given: 거래일 이틀짜리 곡선 (수익률이 하나뿐이다)
        When: 지표를 낸다
        Then: 변동성과 Sharpe 가 None 이다 — NaN 이 아니다

        Note:
            `NaN` 은 비교·정렬·집계를 **전부 조용히 통과**한다. 요약에 실리면
            "Sharpe 를 계산했는데 값이 이상하다"가 아니라 그냥 빈칸으로 보인다
        """
        # Given
        curve = _curve([100.0, 110.0])

        # When
        actual = evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

        # Then
        assert actual.volatility is None
        assert actual.sharpe is None

    def test_거래일이_하루면_거부한다(self) -> None:
        """
        목적: 수익률을 한 개도 만들 수 없는 입력을 고정한다

        Given: 거래일 하루짜리 곡선
        When: 지표를 낸다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="거래일"):
            evaluate_curve(_curve([100.0]), risk_free=_flat_rate(_curve([100.0]), 0.0))

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_총자산에_0_이하가_있으면_거부한다(self, bad: float) -> None:
        """
        목적: 수익률이 정의되지 않는 입력을 고정한다

        Given: 0 이하 값이 섞인 곡선
        When: 지표를 낸다
        Then: ValueError

        Note:
            0 으로 나누면 `inf` 가 나오고 그것이 평균을 통해 **모든 지표를 오염**시킨다
        """
        with pytest.raises(ValueError, match="총자산"):
            curve = _curve([100.0, bad, 120.0])
            evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))

    def test_날짜가_오름차순이_아니면_거부한다(self) -> None:
        """
        목적: 정렬 전제를 고정한다

        Given: 날짜가 뒤섞인 곡선
        When: 지표를 낸다
        Then: ValueError

        Note:
            정렬하지 않고 계산하면 **MDD 가 실제보다 얕게** 나오는데 예외가 나지 않는다
        """
        # Given
        curve = pd.Series([100.0, 120.0, 90.0], index=pd.DatetimeIndex(["2020-01-03", "2020-01-02", "2020-01-06"]))

        # When / Then
        with pytest.raises(ValueError, match="오름차순"):
            evaluate_curve(curve, risk_free=_flat_rate(curve, 0.0))


class TestLayerBoundary:
    """지표 계층이 매매법을 모른다는 계약을 구조로 고정한다 (결정 B1·C94)."""

    def test_그리드를_import하지_않는다(self) -> None:
        """
        목적: 입력이 곡선 하나라는 계약을 **코드 구조로** 고정한다

        Given: 표준 지표 모듈의 소스
        When: import 문을 훑는다
        Then: `strategy.grid` 를 한 번도 참조하지 않는다

        Note:
            그리드를 알기 시작하면 그리드 전용 지표가 하나둘 흘러들어오고,
            두 번째 매매법이 왔을 때 **그 함수를 쓸 수 없게** 된다.
            결정 B1 이 「입력이 전략에 의존하지 않는다」를 근거로 공통 계약을 선언했다
        """
        # Given
        source = inspect.getsource(performance)

        # Then
        assert "strategy.grid" not in source
        assert "strategy import grid" not in source
