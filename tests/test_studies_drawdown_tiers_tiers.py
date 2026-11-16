"""하락_단계_매수 — 단계 신호 · 하락장 시작일 · 다음 거래일 종가 진입 · 기준선

**이 매매법의 정의는 「한 구간 안에서 단계마다 처음 닿은 날 한 번, 회복하면 다시 켬」이다.** 여기가 틀리면
신호 수부터 조용히 틀린다. 손으로 만든 짧은 계열로 아래를 박는다.

| 무엇 | 근거 (`docs/검증/하락_단계_매수/설계.md` 「확정된 설계 결정」의 번호) |
| --- | --- |
| 단계 격자와 다시 켜는 수준 | Q7 · Q9 — 낙폭은 새 고점, VIX 는 20 미만, 공포탐욕지수는 50 이상에서 다시 켠다 |
| 경계 — 「이하」 · 「이상」 · 「미만」 | Q7 · Q9 |
| 데이터 첫날이 이미 구간 안이면 그 구간은 판정하지 않는다 | D4 |
| 지표 값이 없는 날은 판정하지 않는다 — 이월하지 않는다 | D5 |
| 사건은 판정일이 속한 하락장의 시작일(역대 고점일) | D6 |
| 판정일 다음 거래일 종가에 진입한다 | D1 |
| 기준선은 그 지표를 판정할 수 있는 기간의 모든 거래일, 같은 진입 규칙 | D8 |
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_VALUE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.statistics import (
    COL_BASELINE_SAMPLE_COUNT,
    COL_MEAN_EXCESS,
    COL_SIGNAL_SAMPLE_COUNT,
    COL_WIN_RATE_EXCESS,
    excess,
    summarize,
)
from verify_lab.studies.drawdown_tiers.constants import (
    COL_ENTRY_DATE,
    COL_INDICATOR_VALUE,
    COL_TIER,
    DRAWDOWN_RULE,
    FEAR_GREED_RULE,
    HORIZONS,
    REASON_BEFORE_LISTING,
    VIX_RULE,
    TierRule,
)
from verify_lab.studies.drawdown_tiers.tiers import (
    align_indicator,
    baseline_returns,
    drawdown_rates,
    entry_returns,
    peak_dates,
    tier_signals,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md)
EXACT = 1e-12

NAN = float("nan")

# 합성 계열의 첫날. 월요일이라 `bdate_range` 가 주말을 건너뛰는 자리가 예시마다 같다
FIRST_DAY = "2026-01-05"

# 진입 규칙 테스트의 보유 기간. **실제 격자(`HORIZONS`)와 다르게** 짧게 둔다 — 손으로 셀 수 있어야 한다
SHORT_HORIZONS = (2, 3)

# look-ahead 감시용 합성 계열의 길이 · 시드
WALK_LENGTH = 400
WALK_SEED = 7


def _days(count: int) -> pd.DatetimeIndex:
    """`FIRST_DAY` 부터 주중 `count` 일."""
    return pd.bdate_range(FIRST_DAY, periods=count)


def _series(values: list[float]) -> pd.Series:
    """주중 날짜를 인덱스로 단 지표 · 종가 계열."""
    return pd.Series(values, index=_days(len(values)), dtype="float64")


def _prices(closes: list[float], days: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """날짜 · 종가 두 칸의 합성 시세."""
    index = days if days is not None else _days(len(closes))
    return pd.DataFrame({COL_DATE: index, COL_CLOSE: closes})


def _pairs(signals: pd.DataFrame) -> list[tuple[pd.Timestamp, float]]:
    """신호 표를 (판정일, 단계) 목록으로 — 순서까지 비교한다."""
    return list(zip(pd.DatetimeIndex(signals[COL_DATE]), signals[COL_TIER].tolist(), strict=True))


def _expected(days: pd.DatetimeIndex, pairs: list[tuple[int, float]]) -> list[tuple[pd.Timestamp, float]]:
    """(위치, 단계) 목록을 (날짜, 단계) 목록으로."""
    return [(days[position], tier) for position, tier in pairs]


def _dense_signals(values: pd.Series, rule: TierRule) -> pd.DataFrame:
    """날짜 × 단계 전부에 신호 여부(1 · 0)를 단 표 — 미래 참조 감시가 양방향으로 비교되게 한다.

    신호 목록끼리만 견주면 「짧은 입력에만 없는 신호」가 빠져나간다. 칸 전부를 두면 겹치는 범위가 통째로 비교된다.
    """
    signals = tier_signals(values, rule).signals
    grid = pd.MultiIndex.from_product([values.index, list(rule.levels)], names=[COL_DATE, COL_TIER]).to_frame(
        index=False
    )
    fired = signals[[COL_DATE, COL_TIER]].assign(fired=1.0)
    dense = grid.merge(fired, on=[COL_DATE, COL_TIER], how="left")
    dense["fired"] = dense["fired"].fillna(0.0)
    return dense


def _walk_closes(count: int, seed: int) -> pd.Series:
    """하락장이 여러 번 생기는 합성 종가 — 일간 ±3% 안팎의 기하 random walk."""
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.03, count)))
    return pd.Series(closes, index=_days(count), dtype="float64")


def _walk_vix(count: int, seed: int) -> pd.Series:
    """20 아래와 60 위를 여러 번 오가는 합성 변동 지수."""
    rng = np.random.default_rng(seed)
    values = 30.0 + 25.0 * np.sin(np.arange(count) / 9.0) + rng.normal(0.0, 6.0, count)
    return pd.Series(np.abs(values), index=_days(count), dtype="float64")


class TestRuleValues:
    """단계 격자 · 보유 기간은 사용자 결정 그대로다 — 바뀌면 신호 수와 모든 칸이 바뀐다."""

    def test_단계_격자와_다시_켜는_수준은_Q7_Q9_그대로다(self) -> None:
        """
        목적: 세 지표의 단계(얕은 → 깊은 순)와 다시 켜는 수준을 사용자 결정으로 고정한다

        Given: 매매법의 규칙 상수
        When: 단계 · 방향 · 다시 켜는 수준을 보면
        Then: 낙폭 −5 ~ −50%(이하 · 새 고점) / VIX 25 ~ 60(이상 · 20 미만) / 공포탐욕지수 25 ~ 5(이하 · 50 이상)
        """
        # Given / When / Then
        assert DRAWDOWN_RULE.levels == (-0.05, -0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50)
        assert DRAWDOWN_RULE.fires_below is True
        assert DRAWDOWN_RULE.rearm_level == 0.0

        assert VIX_RULE.levels == (25.0, 30.0, 35.0, 40.0, 50.0, 60.0)
        assert VIX_RULE.fires_below is False
        assert VIX_RULE.rearm_level == 20.0

        assert FEAR_GREED_RULE.levels == (25.0, 20.0, 15.0, 10.0, 5.0)
        assert FEAR_GREED_RULE.fires_below is True
        assert FEAR_GREED_RULE.rearm_level == 50.0

    def test_보유_기간은_Q10_그대로다(self) -> None:
        """
        목적: 보유 기간 격자(거래일)를 사용자 결정으로 고정한다

        Given: 매매법의 보유 기간 상수
        When: 값을 보면
        Then: 21 · 63 · 126 · 252 · 504 · 756 거래일이다
        """
        # Given / When / Then
        assert HORIZONS == (21, 63, 126, 252, 504, 756)


class TestTierRuleGuards:
    """단계 규칙이 스스로 모순되면 만들 때 멈춘다 — 판정 중에 조용히 신호가 사라지지 않게."""

    def test_아래로_닿는_규칙의_단계가_다시_켜는_수준_이상이면_예외다(self) -> None:
        """
        목적: 「닿는 날」과 「다시 켜는 날」이 겹치는 규칙을 막는다 — 겹치면 같은 날 켜고 끄는 순서가 결과를 만든다

        Given: 다시 켜는 수준 50, 단계 55(이하에서 닿음)
        When: 규칙을 만들면
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="다시 켜는"):
            TierRule(indicator="시험", levels=(55.0,), fires_below=True, rearm_level=50.0)

    def test_위로_닿는_규칙의_단계가_다시_켜는_수준보다_낮으면_예외다(self) -> None:
        """
        목적: 위로 닿는 규칙도 같은 겹침을 막는다

        Given: 다시 켜는 수준 20(미만에서 켬), 단계 15(이상에서 닿음)
        When: 규칙을 만들면
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="다시 켜는"):
            TierRule(indicator="시험", levels=(15.0,), fires_below=False, rearm_level=20.0)

    def test_단계가_얕은_것부터_깊은_순이_아니면_예외다(self) -> None:
        """
        목적: 단계 순서를 고정한다 — 신호 표의 같은 날 행 순서와 산출물의 단계 순서가 이 순서를 따른다

        Given: 아래로 닿는 규칙인데 단계가 10 → 20 (깊은 것이 먼저)
        When: 규칙을 만들면
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="순"):
            TierRule(indicator="시험", levels=(10.0, 20.0), fires_below=True, rearm_level=50.0)

    def test_단계가_없으면_예외다(self) -> None:
        """
        목적: 빈 격자를 막는다 (경계 조건) — 신호가 0건인 이유가 「격자가 비었다」로 숨지 않게 한다

        Given: 빈 단계 목록
        When: 규칙을 만들면
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="단계"):
            TierRule(indicator="시험", levels=(), fires_below=True, rearm_level=50.0)


class TestDrawdownRates:
    """낙폭 = 그날까지의 역대 최고 종가 대비 비율 (0 이하)."""

    def test_역대_최고_종가_대비_비율이다(self) -> None:
        """
        목적: 낙폭 산식을 손계산으로 고정한다

        Given: 종가 100 → 110 → 99 → 88 → 121 → 100
        When: 낙폭을 구하면
        Then: 0 · 0 · 99/110−1 · 88/110−1 · 0 · 100/121−1
        """
        # Given
        closes = _series([100.0, 110.0, 99.0, 88.0, 121.0, 100.0])

        # When
        rates = drawdown_rates(closes)

        # Then
        expected = [0.0, 0.0, 99 / 110 - 1, 88 / 110 - 1, 0.0, 100 / 121 - 1]
        assert rates.tolist() == pytest.approx(expected, abs=EXACT)
        assert rates.index.equals(closes.index)

    def test_미래_참조_감시(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: 낙폭이 그날 뒤의 종가를 보지 않음을 고정한다 (look-ahead 감시)

        Given: 합성 random walk 종가
        When: 뒤를 자른 입력과 전체 입력으로 낙폭을 구하면
        Then: 겹치는 날의 값이 같다
        """
        # Given
        closes = _walk_closes(WALK_LENGTH, WALK_SEED)
        frame = pd.DataFrame({COL_DATE: closes.index, COL_VALUE: closes.to_numpy()})

        def run(df: pd.DataFrame) -> pd.DataFrame:
            rates = drawdown_rates(pd.Series(df[COL_VALUE].to_numpy(), index=pd.DatetimeIndex(df[COL_DATE])))
            return pd.DataFrame({COL_DATE: rates.index, "rate": rates.to_numpy()})

        # When / Then
        assert_stable_under_truncation(run, frame, WALK_LENGTH // 2, key_columns=[COL_DATE], value_column="rate")


class TestPeakDates:
    """사건(D6) — 판정일이 속한 하락장의 시작일 = 그날까지 마지막으로 역대 최고 종가였던 날."""

    def test_하락장의_시작일은_마지막_역대_고점일이다(self) -> None:
        """
        목적: 사건 묶음의 기준일을 고정한다 — 같은 하락장의 신호는 같은 날을 받는다

        Given: 종가 100 → 110(고점) → 99 → 88 → 121(새 고점) → 100
        When: 날마다 하락장 시작일을 구하면
        Then: d0 · d1 · d1 · d1 · d4 · d4
        """
        # Given
        closes = _series([100.0, 110.0, 99.0, 88.0, 121.0, 100.0])
        days = closes.index

        # When
        peaks = peak_dates(closes)

        # Then
        assert list(pd.DatetimeIndex(peaks)) == [days[0], days[1], days[1], days[1], days[4], days[4]]
        assert peaks.index.equals(days)

    def test_역대_고점과_같은_종가도_새_하락장의_시작이다(self) -> None:
        """
        목적: 고점과 같은 종가로 「회복」한 날의 처리를 고정한다 (경계 조건) — 낙폭이 0 이 되어 단계를 다시 켜는 날과 같은 날이다

        Given: 종가 100 → 90 → 100(고점과 같음) → 95
        When: 하락장 시작일을 구하면
        Then: 마지막 날의 시작일은 d2 다
        """
        # Given
        closes = _series([100.0, 90.0, 100.0, 95.0])
        days = closes.index

        # When
        peaks = peak_dates(closes)

        # Then
        assert list(pd.DatetimeIndex(peaks)) == [days[0], days[0], days[2], days[2]]

    def test_미래_참조_감시(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: 하락장 시작일이 그날 뒤의 종가를 보지 않음을 고정한다 (look-ahead 감시)

        Given: 합성 random walk 종가
        When: 뒤를 자른 입력과 전체 입력으로 시작일을 구하면
        Then: 겹치는 날의 값이 같다
        """
        # Given
        closes = _walk_closes(WALK_LENGTH, WALK_SEED)
        frame = pd.DataFrame({COL_DATE: closes.index, COL_VALUE: closes.to_numpy()})
        epoch = pd.Timestamp("1970-01-01")

        def run(df: pd.DataFrame) -> pd.DataFrame:
            peaks = peak_dates(pd.Series(df[COL_VALUE].to_numpy(), index=pd.DatetimeIndex(df[COL_DATE])))
            ordinal = (pd.DatetimeIndex(peaks) - epoch).days.astype("float64")
            return pd.DataFrame({COL_DATE: peaks.index, "peak": ordinal})

        # When / Then
        assert_stable_under_truncation(run, frame, WALK_LENGTH // 2, key_columns=[COL_DATE], value_column="peak")


class TestDrawdownTiers:
    """낙폭 단계 — 이하에서 닿고, 새 고점에서 다시 켠다 (Q7 · Q9)."""

    def test_구간마다_단계별로_처음_닿은_날_한_번이다(self) -> None:
        """
        목적: 낙폭 단계 신호를 손계산으로 고정한다 — 경계(정확히 −10%)는 그 단계에 든다

        Given: 종가 100 · 96 · 94 · 90 · 85 · 92 · 102(새 고점) · 90 · 103(새 고점) · 80
        When: 낙폭 단계 신호를 구하면
        Then: d2 −5 · d3 −10(정확히 −10%) · d4 −15 · d7 −5 · d7 −10 · d9 −5 · −10 · −15 · −20
        """
        # Given
        closes = _series([100.0, 96.0, 94.0, 90.0, 85.0, 92.0, 102.0, 90.0, 103.0, 80.0])
        days = closes.index

        # When
        result = tier_signals(drawdown_rates(closes), DRAWDOWN_RULE)

        # Then
        expected = [
            (2, -0.05),
            (3, -0.10),
            (4, -0.15),
            (7, -0.05),
            (7, -0.10),
            (9, -0.05),
            (9, -0.10),
            (9, -0.15),
            (9, -0.20),
        ]
        assert _pairs(result.signals) == _expected(days, expected)
        assert result.missing_days == 0
        assert result.unjudged_days == 0

    def test_신호의_지표_값은_그날의_낙폭이다(self) -> None:
        """
        목적: 원자료에 실리는 지표 값이 판정에 쓴 그날 값임을 고정한다 — 사용자가 차트로 대조하는 값이다

        Given: 종가 100 · 94 · 85
        When: 낙폭 단계 신호를 구하면
        Then: d1 −5 의 값은 94/100−1, d2 −10 · −15 의 값은 85/100−1
        """
        # Given
        closes = _series([100.0, 94.0, 85.0])

        # When
        signals = tier_signals(drawdown_rates(closes), DRAWDOWN_RULE).signals

        # Then
        assert signals[COL_INDICATOR_VALUE].tolist() == pytest.approx(
            [94 / 100 - 1, 85 / 100 - 1, 85 / 100 - 1], abs=EXACT
        )

    def test_깊은_단계는_같은_구간의_얕은_단계보다_먼저_닿지_않는다(self) -> None:
        """
        목적: 단계 사이의 불변조건을 고정한다 — 깊은 단계가 닿은 구간에는 모든 얕은 단계가 같은 날이나 그 전에 닿았다

        Given: 하락장이 여러 번 생기는 합성 종가
        When: 낙폭 단계 신호를 구간(새 고점 사이)마다 묶으면
        Then: 단계마다 구간당 한 번 이하이고, 깊은 단계의 날 ≥ 바로 얕은 단계의 날이다
        """
        # Given
        closes = _walk_closes(2_000, WALK_SEED)
        rates = drawdown_rates(closes)
        episode = (rates >= 0.0).cumsum()

        # When
        signals = tier_signals(rates, DRAWDOWN_RULE).signals
        signals = signals.assign(episode=episode.reindex(pd.DatetimeIndex(signals[COL_DATE])).to_numpy())

        # Then
        assert not signals.duplicated(subset=["episode", COL_TIER]).any()
        levels = list(DRAWDOWN_RULE.levels)
        deep_episodes = 0
        for _, group in signals.groupby("episode"):
            first_day = dict(zip(group[COL_TIER], group[COL_DATE], strict=True))
            for shallow, deep in zip(levels, levels[1:], strict=False):
                if deep in first_day:
                    assert shallow in first_day
                    assert first_day[shallow] <= first_day[deep]
            deep_episodes += int(len(first_day) >= 3)
        assert deep_episodes > 0, "−15% 까지 내려간 구간이 없어 불변조건이 비어 있습니다 — 시드나 길이를 바꾸세요"

    def test_미래_참조_감시(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: 낙폭 단계 신호가 그날 뒤의 종가를 보지 않음을 고정한다 (look-ahead 감시) — 날짜 × 단계 전부를 비교한다

        Given: 합성 random walk 종가
        When: 뒤를 자른 입력과 전체 입력으로 신호를 구하면
        Then: 겹치는 날의 모든 칸에서 신호 여부가 같다
        """
        # Given
        closes = _walk_closes(WALK_LENGTH, WALK_SEED)
        frame = pd.DataFrame({COL_DATE: closes.index, COL_VALUE: closes.to_numpy()})

        def run(df: pd.DataFrame) -> pd.DataFrame:
            series = pd.Series(df[COL_VALUE].to_numpy(), index=pd.DatetimeIndex(df[COL_DATE]))
            return _dense_signals(drawdown_rates(series), DRAWDOWN_RULE)

        # When / Then
        assert_stable_under_truncation(
            run, frame, WALK_LENGTH // 2, key_columns=[COL_DATE, COL_TIER], value_column="fired"
        )


class TestVixTiers:
    """VIX 단계 — 이상에서 닿고, 20 미만에서 다시 켠다 (Q7 · Q9)."""

    def test_구간마다_단계별로_처음_닿은_날_한_번이다(self) -> None:
        """
        목적: VIX 단계 신호와 두 경계를 손계산으로 고정한다 — 정확히 25 는 25 단계에 들고, 정확히 20 은 다시 켜지 않는다

        Given: 18 · 22 · 25 · 24 · 31 · 19.99(켬) · 30 · 20(켜지 않음) · 26 · 19(켬) · 61
        When: VIX 단계 신호를 구하면
        Then: d2 25 · d4 30 · d6 25 · 30 · d10 25 ~ 60 여섯 — d8 의 26 은 신호가 아니다
        """
        # Given
        values = _series([18.0, 22.0, 25.0, 24.0, 31.0, 19.99, 30.0, 20.0, 26.0, 19.0, 61.0])
        days = values.index

        # When
        result = tier_signals(values, VIX_RULE)

        # Then
        expected = [
            (2, 25.0),
            (4, 30.0),
            (6, 25.0),
            (6, 30.0),
            (10, 25.0),
            (10, 30.0),
            (10, 35.0),
            (10, 40.0),
            (10, 50.0),
            (10, 60.0),
        ]
        assert _pairs(result.signals) == _expected(days, expected)
        assert result.unjudged_days == 0

    def test_미래_참조_감시(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: VIX 단계 신호가 그날 뒤의 값을 보지 않음을 고정한다 (look-ahead 감시)

        Given: 20 아래와 60 위를 오가는 합성 계열
        When: 뒤를 자른 입력과 전체 입력으로 신호를 구하면
        Then: 겹치는 날의 모든 칸에서 신호 여부가 같다
        """
        # Given
        values = _walk_vix(WALK_LENGTH, WALK_SEED)
        frame = pd.DataFrame({COL_DATE: values.index, COL_VALUE: values.to_numpy()})

        def run(df: pd.DataFrame) -> pd.DataFrame:
            series = pd.Series(df[COL_VALUE].to_numpy(), index=pd.DatetimeIndex(df[COL_DATE]))
            return _dense_signals(series, VIX_RULE)

        # When / Then
        assert_stable_under_truncation(
            run, frame, WALK_LENGTH // 2, key_columns=[COL_DATE, COL_TIER], value_column="fired"
        )


class TestFearGreedTiers:
    """공포탐욕지수 단계 — 이하에서 닿고, 50 이상에서 다시 켠다 (Q7 · Q9)."""

    def test_구간마다_단계별로_처음_닿은_날_한_번이다(self) -> None:
        """
        목적: 공포탐욕지수 단계 신호와 두 경계를 손계산으로 고정한다 — 정확히 25 는 25 단계에 들고, 정확히 50 은 다시 켠다

        Given: 60 · 30 · 25 · 26 · 14 · 49.99(켜지 않음) · 24 · 50(켬) · 24 · 5
        When: 공포탐욕지수 단계 신호를 구하면
        Then: d2 25 · d4 20 · 15 · d8 25 · d9 20 · 15 · 10 · 5 — d6 의 24 는 신호가 아니다
        """
        # Given
        values = _series([60.0, 30.0, 25.0, 26.0, 14.0, 49.99, 24.0, 50.0, 24.0, 5.0])
        days = values.index

        # When
        result = tier_signals(values, FEAR_GREED_RULE)

        # Then
        expected = [(2, 25.0), (4, 20.0), (4, 15.0), (8, 25.0), (9, 20.0), (9, 15.0), (9, 10.0), (9, 5.0)]
        assert _pairs(result.signals) == _expected(days, expected)
        assert result.unjudged_days == 0


class TestUnjudgedFirstEpisode:
    """D4 — 데이터 첫날이 이미 구간 안이면 그 구간이 언제 시작했는지 몰라 판정하지 않고 날 수를 남긴다."""

    def test_VIX_첫날이_20_이상이면_처음_켜질_때까지_판정하지_않는다(self) -> None:
        """
        목적: 시작을 모르는 첫 구간의 「처음 닿은 날」을 지어내지 않음을 고정한다

        Given: 22 · 26 · 19(켬) · 27
        When: VIX 단계 신호를 구하면
        Then: d1 의 26 은 신호가 아니고, d3 25 하나만 나오며 판정하지 않은 날이 2일이다
        """
        # Given
        values = _series([22.0, 26.0, 19.0, 27.0])
        days = values.index

        # When
        result = tier_signals(values, VIX_RULE)

        # Then
        assert _pairs(result.signals) == _expected(days, [(3, 25.0)])
        assert result.unjudged_days == 2

    def test_공포탐욕지수_첫날이_50_미만이면_처음_켜질_때까지_판정하지_않는다(self) -> None:
        """
        목적: 아래로 닿는 규칙에도 같은 처리를 고정한다

        Given: 40 · 20 · 55(켬) · 20
        When: 공포탐욕지수 단계 신호를 구하면
        Then: d3 25 · 20 만 나오고 판정하지 않은 날이 2일이다
        """
        # Given
        values = _series([40.0, 20.0, 55.0, 20.0])
        days = values.index

        # When
        result = tier_signals(values, FEAR_GREED_RULE)

        # Then
        assert _pairs(result.signals) == _expected(days, [(3, 25.0), (3, 20.0)])
        assert result.unjudged_days == 2

    def test_앞쪽의_빈_날은_판정하지_않은_날이_아니라_빠진_날로_센다(self) -> None:
        """
        목적: 두 건수가 겹치지 않음을 고정한다 — 값이 없는 날(D5)과 시작을 모르는 구간의 날(D4)을 따로 센다

        Given: 빈 값 · 22 · 19(켬) · 26
        When: VIX 단계 신호를 구하면
        Then: 빠진 날 1 · 판정하지 않은 날 1 · d3 25 하나
        """
        # Given
        values = _series([NAN, 22.0, 19.0, 26.0])
        days = values.index

        # When
        result = tier_signals(values, VIX_RULE)

        # Then
        assert _pairs(result.signals) == _expected(days, [(3, 25.0)])
        assert result.missing_days == 1
        assert result.unjudged_days == 1


class TestMissingValues:
    """D5 — 값이 없는 날은 그 지표로 판정하지 않는다. 이월하지도 않고, 다시 켜지도 않는다."""

    def test_빈_날에는_신호도_다시_켜기도_없다(self) -> None:
        """
        목적: 빈 날을 앞뒤 값으로 메우지 않고, 빈 날이 구간을 끝내지 않음을 고정한다

        Given: 60 · 빈 값 · 24 · 빈 값 · 23 · 60(켬) · 20
        When: 공포탐욕지수 단계 신호를 구하면
        Then: d2 25(뒤 값으로 메우면 d1 이 된다) · d6 25 · 20 — d4 의 23 은 신호가 아니다(빈 날이 켜면 신호가 된다) · 빠진 날 2
        """
        # Given
        values = _series([60.0, NAN, 24.0, NAN, 23.0, 60.0, 20.0])
        days = values.index

        # When
        result = tier_signals(values, FEAR_GREED_RULE)

        # Then
        assert _pairs(result.signals) == _expected(days, [(2, 25.0), (6, 25.0), (6, 20.0)])
        assert result.missing_days == 2
        assert result.unjudged_days == 0

    def test_위로_닿는_규칙도_빈_날이_다시_켜지_않는다(self) -> None:
        """
        목적: 방향이 반대인 규칙에서도 빈 날이 구간을 끝내지 않음을 고정한다

        Given: 18 · 26 · 빈 값 · 27
        When: VIX 단계 신호를 구하면
        Then: d1 25 하나 · 빠진 날 1
        """
        # Given
        values = _series([18.0, 26.0, NAN, 27.0])
        days = values.index

        # When
        result = tier_signals(values, VIX_RULE)

        # Then
        assert _pairs(result.signals) == _expected(days, [(1, 25.0)])
        assert result.missing_days == 1

    def test_날짜가_오름차순이_아니면_예외다(self) -> None:
        """
        목적: 「처음 닿은 날」이 날짜 순서에 기대므로 순서가 어긋난 입력을 막는다

        Given: 날짜가 거꾸로 선 계열
        When: 단계 신호를 구하면
        Then: ValueError
        """
        # Given
        values = _series([18.0, 26.0, 27.0]).iloc[::-1]

        # When / Then
        with pytest.raises(ValueError, match="오름차순"):
            tier_signals(values, VIX_RULE)


class TestAlignIndicator:
    """D5 — 판정일은 대상의 거래일이다. 지표의 다른 날 값은 쓰지 않고, 지표 첫날 전은 판정 기간 밖이다."""

    def test_대상_거래일에_맞추고_빈_날은_비워_둔다(self) -> None:
        """
        목적: 지표를 대상 거래일 위에 놓는 규칙을 고정한다

        Given: 거래일 월 ~ 다음 주 월(6일), 지표는 화 · 수 · 금 · 토(휴장) · 월 — 목요일 값이 없다
        When: 지표를 거래일에 맞추면
        Then: 화부터 다음 주 월까지 5일이고(월요일은 지표 첫날 전), 목요일은 비고, 토요일 값은 쓰이지 않는다
        """
        # Given
        trading_days = _days(6)
        indicator = pd.DataFrame(
            {
                COL_DATE: pd.to_datetime(["2026-01-06", "2026-01-07", "2026-01-09", "2026-01-10", "2026-01-12"]),
                COL_VALUE: [21.0, 22.0, 24.0, 99.0, 25.0],
            }
        )

        # When
        aligned = align_indicator(trading_days, indicator)

        # Then
        assert aligned.index.equals(trading_days[1:])
        assert aligned.tolist() == pytest.approx([21.0, 22.0, NAN, 24.0, 25.0], abs=EXACT, nan_ok=True)


class TestEntryReturns:
    """D1 — 판정일 다음 거래일 종가에 진입해 보유 기간 뒤 거래일 종가에 판다."""

    def test_다음_거래일_종가에_진입하고_보유_기간_뒤_종가에_판다(self) -> None:
        """
        목적: 진입 위치와 수익률 산식을 손계산으로 고정한다

        Given: 종가 100 · 101 · 103 · 102 · 106 · 110 · 108 · 112, 판정일 d1
        When: 보유 2 · 3 거래일의 수익률을 구하면
        Then: 진입 d2(103) → d4(106) · d5(110)
        """
        # Given
        prices = _prices([100.0, 101.0, 103.0, 102.0, 106.0, 110.0, 108.0, 112.0])
        days = pd.DatetimeIndex(prices[COL_DATE])

        # When
        frame = entry_returns(prices, days[[1]], horizons=SHORT_HORIZONS, price_column=COL_CLOSE)

        # Then
        assert frame[COL_HORIZON].tolist() == [2, 3]
        assert list(pd.DatetimeIndex(frame[COL_DATE])) == [days[1], days[1]]
        assert list(pd.DatetimeIndex(frame[COL_ENTRY_DATE])) == [days[2], days[2]]
        assert list(pd.DatetimeIndex(frame[COL_EXIT_DATE])) == [days[4], days[5]]
        assert frame[COL_ENTRY_CLOSE].tolist() == pytest.approx([103.0, 103.0], abs=EXACT)
        assert frame[COL_EXIT_CLOSE].tolist() == pytest.approx([106.0, 110.0], abs=EXACT)
        assert frame[COL_FORWARD_RETURN].tolist() == pytest.approx([106 / 103 - 1, 110 / 103 - 1], abs=EXACT)
        assert (frame[COL_BASIS] == ReturnBasis.CLOSE.value).all()
        assert (frame[COL_EXCLUDED_REASON] == REASON_NONE).all()

    def test_데이터_끝을_넘으면_값을_비우고_사유를_단다(self) -> None:
        """
        목적: 끝 넘김 처리를 고정한다 (경계 조건) — 진입일이 없는 판정일(마지막 날)도 같은 사유다

        Given: 8일 종가, 판정일 d4 · d6 · d7(마지막 날)
        When: 보유 2 · 3 거래일의 수익률을 구하면
        Then: d4 의 보유 2 만 값이 있고(d5 → d7) 나머지 다섯 칸은 끝 넘김으로 비어 있다
        """
        # Given
        prices = _prices([100.0, 101.0, 103.0, 102.0, 106.0, 110.0, 108.0, 112.0])
        days = pd.DatetimeIndex(prices[COL_DATE])

        # When
        frame = entry_returns(prices, days[[4, 6, 7]], horizons=SHORT_HORIZONS, price_column=COL_CLOSE)

        # Then
        valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
        assert valid.tolist() == [True, False, False, False, False, False]
        assert frame.loc[valid, COL_FORWARD_RETURN].tolist() == pytest.approx([112 / 110 - 1], abs=EXACT)
        assert (frame.loc[~valid, COL_EXCLUDED_REASON] == REASON_OUT_OF_RANGE).all()
        assert frame.loc[~valid, COL_FORWARD_RETURN].isna().all()

    def test_대상_상장_전_판정일은_사유를_달고_남는다(self) -> None:
        """
        목적: 공통 신호(SPY 낙폭)를 늦게 상장한 대상에 걸 때의 처리를 고정한다 — 판정일에 대상이 없으면 제외한다

        Given: 대상은 d3 부터 거래, 판정일 d1 · d2(상장 전날) · d3
        When: 보유 2 거래일의 수익률을 구하면
        Then: d1 · d2 는 상장 전 사유로 비고, d3 은 d4 진입 → d6 청산이다
        """
        # Given
        all_days = _days(10)
        prices = _prices([100.0, 102.0, 104.0, 103.0, 107.0, 111.0, 109.0], days=all_days[3:])

        # When
        frame = entry_returns(prices, all_days[[1, 2, 3]], horizons=(2,), price_column=COL_CLOSE)

        # Then
        assert frame[COL_EXCLUDED_REASON].tolist() == [REASON_BEFORE_LISTING, REASON_BEFORE_LISTING, REASON_NONE]
        assert frame[COL_FORWARD_RETURN].iloc[:2].isna().all()
        assert frame[COL_FORWARD_RETURN].iloc[2] == pytest.approx(103 / 102 - 1, abs=EXACT)

    def test_입력_신호_수는_집계와_제외의_합이다(self) -> None:
        """
        목적: 표본 보존을 고정한다 — 행을 지우지 않고, 사유별 건수가 남는다

        Given: 대상은 d3 ~ d9, 판정일 d1(상장 전) · d4 · d8(진입은 되고 청산이 넘침) · d9(진입부터 넘침), 보유 2 · 3
        When: 수익률을 구하면
        Then: 행 수 = 판정일 4 × 보유 2 = 8 = 유효 2 + 상장 전 2 + 끝 넘김 4
        """
        # Given
        all_days = _days(10)
        prices = _prices([100.0, 102.0, 104.0, 103.0, 107.0, 111.0, 109.0], days=all_days[3:])
        signal_dates = all_days[[1, 4, 8, 9]]

        # When
        frame = entry_returns(prices, signal_dates, horizons=SHORT_HORIZONS, price_column=COL_CLOSE)

        # Then
        assert len(frame) == len(signal_dates) * len(SHORT_HORIZONS)
        reasons = frame[COL_EXCLUDED_REASON].value_counts().to_dict()
        assert reasons == {REASON_NONE: 2, REASON_BEFORE_LISTING: 2, REASON_OUT_OF_RANGE: 4}
        assert frame[COL_FORWARD_RETURN].notna().sum() == reasons[REASON_NONE]

    def test_행은_판정일_다음_보유_기간_오름차순이다(self) -> None:
        """
        목적: long-form 의 행 순서를 고정한다 (forward return 반환 계약 — 신호일 → 기준 → 구간)

        Given: 판정일 d1 · d2
        When: 보유 3 · 2 순으로 넘기면
        Then: (d1, 2) · (d1, 3) · (d2, 2) · (d2, 3)
        """
        # Given
        prices = _prices([100.0, 101.0, 103.0, 102.0, 106.0, 110.0, 108.0, 112.0])
        days = pd.DatetimeIndex(prices[COL_DATE])

        # When
        frame = entry_returns(prices, days[[1, 2]], horizons=(3, 2), price_column=COL_CLOSE)

        # Then
        keys = list(zip(pd.DatetimeIndex(frame[COL_DATE]), frame[COL_HORIZON], strict=True))
        assert keys == [(days[1], 2), (days[1], 3), (days[2], 2), (days[2], 3)]

    def test_대상_마지막_거래일_뒤의_판정일은_끝_넘김으로_남는다(self) -> None:
        """
        목적: 대상 사본이 신호 대상보다 짧을 때(재내보내기에서 옛 끝날에 머문 종목) 멈추지 않고 행으로 남음을 고정한다 —
        신호 대상의 마지막 날에 난 신호는 대상에 그날이 없다

        Given: 8일 시세, 판정일 d6 과 그 뒤 이틀(대상 데이터 밖)
        When: 보유 2 거래일의 수익률을 구하면
        Then: 예외 없이 세 행 모두 끝 넘김 사유로 비어 있다
        """
        # Given
        prices = _prices([100.0, 101.0, 103.0, 102.0, 106.0, 110.0, 108.0, 112.0])
        later = _days(10)[[6, 8, 9]]

        # When
        frame = entry_returns(prices, later, horizons=(2,), price_column=COL_CLOSE)

        # Then
        assert frame[COL_EXCLUDED_REASON].tolist() == [REASON_OUT_OF_RANGE] * 3
        assert frame[COL_FORWARD_RETURN].isna().all()
        assert frame[COL_ENTRY_DATE].isna().tolist() == [False, True, True]

    def test_상장_뒤인데_거래일이_아닌_판정일은_예외다(self) -> None:
        """
        목적: 달력이 어긋난 판정일을 조용히 버리지 않음을 고정한다 — 신호 판정 대상과 측정 대상의 거래일이 다르다는 뜻이다

        Given: 주중 거래일 시세, 판정일은 그 사이의 토요일
        When: 수익률을 구하면
        Then: ValueError
        """
        # Given
        prices = _prices([100.0, 101.0, 103.0, 102.0, 106.0, 110.0, 108.0, 112.0])
        saturday = pd.DatetimeIndex([pd.Timestamp("2026-01-10")])

        # When / Then
        with pytest.raises(ValueError, match="거래일"):
            entry_returns(prices, saturday, horizons=SHORT_HORIZONS, price_column=COL_CLOSE)

    def test_미래_참조_감시(self, assert_stable_under_truncation: Callable[..., None]) -> None:
        """
        목적: 앞쪽 판정일의 수익률이 뒤를 자른 시세에서도 같음을 고정한다 (look-ahead 감시)

        Given: 합성 random walk 종가와 격일 판정일
        When: 뒤를 자른 시세와 전체 시세로 수익률을 구하면
        Then: 짧은 입력에서 값이 있는 칸은 전체 입력과 같다
        """
        # Given
        closes = _walk_closes(WALK_LENGTH, WALK_SEED)
        frame = pd.DataFrame({COL_DATE: closes.index, COL_CLOSE: closes.to_numpy()})

        def run(df: pd.DataFrame) -> pd.DataFrame:
            days = pd.DatetimeIndex(df[COL_DATE])
            return entry_returns(df, days[::2], horizons=SHORT_HORIZONS, price_column=COL_CLOSE)

        # When / Then
        assert_stable_under_truncation(
            run, frame, WALK_LENGTH // 2, key_columns=[COL_DATE, COL_HORIZON], value_column=COL_FORWARD_RETURN
        )


class TestBaselineReturns:
    """D8 — 기준선은 그 지표를 판정할 수 있는 기간 안의 모든 거래일을 같은 진입 규칙으로 잰다."""

    def test_판정_가능_첫날부터_모든_거래일을_같은_규칙으로_잰다(self) -> None:
        """
        목적: 기준선 모집단과 산식을 손계산으로 고정한다

        Given: 종가 100 · 102 · 101 · 105 · 104 · 108 · 110, 판정 가능 첫날 d1, 보유 2
        When: 기준선 수익률을 구하면
        Then: 판정일 d1 ~ d6 여섯 행 — d1 · d2 · d3 만 값이 있고(다음 날 진입) 나머지 셋은 끝 넘김
        """
        # Given
        prices = _prices([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 110.0])
        days = pd.DatetimeIndex(prices[COL_DATE])

        # When
        frame = baseline_returns(prices, start=days[1], horizons=(2,), price_column=COL_CLOSE)

        # Then
        assert list(pd.DatetimeIndex(frame[COL_DATE])) == list(days[1:])
        valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
        assert valid.tolist() == [True, True, True, False, False, False]
        assert frame.loc[valid, COL_FORWARD_RETURN].tolist() == pytest.approx(
            [104 / 101 - 1, 108 / 105 - 1, 110 / 104 - 1], abs=EXACT
        )

    def test_판정_가능_첫날이_휴장이면_그_뒤_첫_거래일부터다(self) -> None:
        """
        목적: 지표 첫날이 대상의 거래일이 아닐 때 모집단 시작을 고정한다 (경계 조건)

        Given: 주중 7일 시세, 판정 가능 첫날은 그 사이의 토요일
        When: 기준선 수익률을 구하면
        Then: 판정일은 다음 월요일부터다
        """
        # Given
        prices = _prices([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 110.0])
        days = pd.DatetimeIndex(prices[COL_DATE])

        # When
        frame = baseline_returns(prices, start=pd.Timestamp("2026-01-10"), horizons=(2,), price_column=COL_CLOSE)

        # Then
        assert list(pd.DatetimeIndex(frame[COL_DATE])) == [days[5], days[6]]

    def test_판정_가능_첫날이_상장_전이면_상장일부터다(self) -> None:
        """
        목적: 공통 신호 기간이 대상보다 길 때(SPY 낙폭 × QQQ) 기준선에 상장 전 행이 섞이지 않음을 고정한다

        Given: 대상은 d3 부터, 판정 가능 첫날 d0
        When: 기준선 수익률을 구하면
        Then: 판정일은 d3 부터이고 상장 전 사유가 없다
        """
        # Given
        all_days = _days(10)
        prices = _prices([100.0, 102.0, 104.0, 103.0, 107.0, 111.0, 109.0], days=all_days[3:])

        # When
        frame = baseline_returns(prices, start=all_days[0], horizons=(2,), price_column=COL_CLOSE)

        # Then
        assert list(pd.DatetimeIndex(frame[COL_DATE])) == list(all_days[3:])
        assert (frame[COL_EXCLUDED_REASON] != REASON_BEFORE_LISTING).all()

    def test_기준선_대비_차이는_신호_평균에서_기준선_평균을_뺀_값이다(self) -> None:
        """
        목적: 이 매매법의 기준선 대비 차이를 손계산으로 고정한다 — 신호와 기준선이 같은 칸(기준 · 보유)으로 맞물린다

        Given: 위 시세, 신호 d2 하나, 기준선 판정 가능 첫날 d1, 보유 2
        When: 두 표를 요약해 차이를 내면
        Then: 평균 차이 = (108/105−1) − 평균(104/101−1, 108/105−1, 110/104−1), 표본 1 대 3, 오른 비율 차이 0
        """
        # Given
        prices = _prices([100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 110.0])
        days = pd.DatetimeIndex(prices[COL_DATE])
        signal = entry_returns(prices, days[[2]], horizons=(2,), price_column=COL_CLOSE)
        baseline = baseline_returns(prices, start=days[1], horizons=(2,), price_column=COL_CLOSE)

        # When
        table = excess(summarize(signal), summarize(baseline))

        # Then
        baseline_mean = ((104 / 101 - 1) + (108 / 105 - 1) + (110 / 104 - 1)) / 3
        assert len(table) == 1
        assert table[COL_SIGNAL_SAMPLE_COUNT].iloc[0] == 1
        assert table[COL_BASELINE_SAMPLE_COUNT].iloc[0] == 3
        assert table[COL_MEAN_EXCESS].iloc[0] == pytest.approx((108 / 105 - 1) - baseline_mean, abs=EXACT)
        assert table[COL_WIN_RATE_EXCESS].iloc[0] == pytest.approx(0.0, abs=EXACT)
