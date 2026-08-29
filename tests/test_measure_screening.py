"""후보 판정의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 그래서 네 기준이 각각 단독으로
칸을 떨어뜨리는지를 하나씩 고정하고, 방향을 가리지 않는지를 대칭 입력으로 확인한다.

핵심 계약은 넷이다.
- 네 기준 중 하나라도 못 넘으면 탈락하고, **무엇에 걸렸는지가 남는다**
- 오른 쪽과 내린 쪽을 **대칭으로** 판정한다 (측정의 원칙 11)
- 시기를 쪼갤 수 없으면 **탈락이 아니라 보류**다 (측정의 원칙 12)
- 축 이름을 인자로 받아 **만기월이 아닌 축에서도** 그대로 동작한다
"""

import pandas as pd
import pytest

from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_DIRECTION,
    COL_FAILED_CRITERIA,
    COL_HIT_RATE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_VERDICT,
    CRITERION_GAP,
    CRITERION_HIT_RATE,
    CRITERION_P_VALUE,
    CRITERION_PERIOD,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MIN_BASELINE_GAP,
    MIN_HIT_RATE,
    MIN_PERIOD_HIT_RATE,
    SCREENING_COLUMNS,
    VERDICT_FAIL,
    VERDICT_HELD,
    VERDICT_PASS,
    screen_candidates,
)
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_SAMPLE_COUNT,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE,
    COL_WIN_RATE_EXCESS,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

AXIS = "만기월"


def _summary(
    *,
    win_rate: float,
    loss_rate: float,
    win_excess: float,
    loss_excess: float,
    up_p: float,
    down_p: float,
    sample: int = 30,
    axis_value: int = 9,
) -> pd.DataFrame:
    """한 칸짜리 집계표를 만든다."""
    return pd.DataFrame(
        {
            AXIS: [axis_value],
            COL_SAMPLE_COUNT: [sample],
            COL_WIN_RATE: [win_rate],
            COL_LOSS_RATE: [loss_rate],
            COL_WIN_RATE_EXCESS: [win_excess],
            COL_LOSS_RATE_EXCESS: [loss_excess],
            COL_UP_RATE_P_VALUE: [up_p],
            COL_DOWN_RATE_P_VALUE: [down_p],
        }
    )


def _periods(rates: list[float], *, axis_value: int = 9, sample: int = 15) -> pd.DataFrame:
    """시기별 집계표를 만든다. `rates` 는 각 구간의 (오른 비율, 내린 비율) 중 판정에 쓸 쪽이다."""
    return pd.DataFrame(
        {
            AXIS: [axis_value] * len(rates),
            COL_SAMPLE_COUNT: [sample] * len(rates),
            COL_WIN_RATE: rates,
            COL_LOSS_RATE: [1.0 - rate for rate in rates],
        }
    )


def _down_summary(**overrides: float) -> pd.DataFrame:
    """네 기준을 넉넉히 통과하는 「아래 방향」 칸. 개별 값을 덮어써 한 기준씩 떨어뜨린다."""
    values: dict[str, float] = {
        "win_rate": 0.27,
        "loss_rate": 0.73,
        "win_excess": -0.23,
        "loss_excess": 0.23,
        "up_p": 0.003,
        "down_p": 0.003,
    }
    values.update(overrides)

    return _summary(**values)  # type: ignore[arg-type]


class TestVerdict:
    """네 기준이 각각 단독으로 칸을 떨어뜨리는지 고정한다."""

    def test_네_기준을_모두_넘으면_통과한다(self) -> None:
        """
        목적: 기준선에서 충분히 멀고, 적중률이 높고, 우연으로 보기 어렵고,
              시기를 쪼개도 유지되면 후보로 올린다.

        Given: 아래로 73% 적중 · 기준선 대비 +23%p · 우연확률 0.003 · 시기 71%/75%
        When: 판정하면
        Then: 통과이고 방향이 「아래」다
        """
        # Given
        summary = _down_summary()
        periods = _periods([0.29, 0.25])  # 오른 비율 → 내린 비율 71%, 75%

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_PASS
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN
        assert result[COL_FAILED_CRITERIA].iloc[0] == ""

    def test_기준선과_차이가_작으면_탈락한다(self) -> None:
        """
        목적: **기준 1 단독으로 떨어뜨린다.** 적중률이 높아도 기준선이 이미 높으면 우위가 아니다.

        Given: 적중률 73% 인데 기준선 대비 차이가 하한 미만
        When: 판정하면
        Then: 탈락이고 사유에 기준 1 이 남는다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.01
        summary = _down_summary(loss_excess=gap, win_excess=-gap)

        # When
        result = screen_candidates(summary, _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_FAIL
        assert CRITERION_GAP in result[COL_FAILED_CRITERIA].iloc[0]

    def test_적중률이_낮으면_탈락한다(self) -> None:
        """
        목적: **기준 2 단독으로 떨어뜨린다.** 기준선에서 멀어도 적중률이 낮으면 집행할 수 없다.

        Given: 기준선 대비 +23%p 인데 적중률이 하한 미만
        When: 판정하면
        Then: 탈락이고 사유에 기준 2 가 남는다
        """
        # Given
        hit = MIN_HIT_RATE - 0.01
        summary = _down_summary(loss_rate=hit, win_rate=1.0 - hit)

        # When
        result = screen_candidates(summary, _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_FAIL
        assert CRITERION_HIT_RATE in result[COL_FAILED_CRITERIA].iloc[0]

    def test_우연확률이_높으면_탈락한다(self) -> None:
        """
        목적: **기준 3 단독으로 떨어뜨린다.** 표본이 작으면 큰 차이도 우연히 나온다.

        Given: 다른 셋은 넉넉히 통과하는데 우연확률만 0.20
        When: 판정하면
        Then: 탈락이고 사유에 기준 3 이 남는다
        """
        # Given
        summary = _down_summary(down_p=0.20, up_p=0.20)

        # When
        result = screen_candidates(summary, _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_FAIL
        assert CRITERION_P_VALUE in result[COL_FAILED_CRITERIA].iloc[0]

    def test_한_시기라도_무너지면_탈락한다(self) -> None:
        """
        목적: **기준 4 단독으로 떨어뜨린다.** 한 시기가 만든 값을 걸러낸다.

        Given: 전체는 73% 인데 뒤 시기가 하한 미만
        When: 판정하면
        Then: 탈락이고 사유에 기준 4 가 남는다
        """
        # Given
        weak = MIN_PERIOD_HIT_RATE - 0.05
        periods = _periods([0.29, 1.0 - weak])

        # When
        result = screen_candidates(_down_summary(), periods, axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_FAIL
        assert CRITERION_PERIOD in result[COL_FAILED_CRITERIA].iloc[0]

    def test_떨어진_기준이_여럿이면_모두_남는다(self) -> None:
        """
        목적: 사유가 **하나로 잘리지 않는다.** 기준을 조정했을 때 무엇이 달라지는지 알려면
              걸린 것이 전부 남아야 한다.

        Given: 적중률과 우연확률 둘 다 미달
        When: 판정하면
        Then: 사유에 기준 2 와 3 이 모두 남는다
        """
        # Given
        hit = MIN_HIT_RATE - 0.05
        summary = _down_summary(loss_rate=hit, win_rate=1.0 - hit, down_p=0.30, up_p=0.30)

        # When
        result = screen_candidates(summary, _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        failed = result[COL_FAILED_CRITERIA].iloc[0]
        assert CRITERION_HIT_RATE in failed
        assert CRITERION_P_VALUE in failed


class TestDirectionSymmetry:
    """오른 쪽과 내린 쪽을 대칭으로 판정하는지 고정한다 (측정의 원칙 11)."""

    def test_위로_멀어진_칸도_같은_기준으로_통과한다(self) -> None:
        """
        목적: **방향을 가리지 않는다.** 위로 멀어진 칸도 아래와 같은 기준으로 판정한다.

        Given: 오른 비율 73% · 기준선 대비 +23%p · 우연확률 0.003 · 시기 71%/75%
        When: 판정하면
        Then: 통과이고 방향이 「위」다
        """
        # Given
        summary = _summary(win_rate=0.73, loss_rate=0.27, win_excess=0.23, loss_excess=-0.23, up_p=0.003, down_p=0.003)
        periods = _periods([0.71, 0.75])

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_PASS
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP

    def test_방향은_기준선에서_멀어진_쪽으로_정해진다(self) -> None:
        """
        목적: 방향을 **절대 비율이 아니라 기준선과의 거리**로 정한다.

        주식은 원래 자주 올라 오른 비율이 절반을 넘는 칸이 흔하다. 절대 비율로 방향을 정하면
        기준선보다 낮은데도 "위" 로 판정된다.

        Given: 오른 비율 55% 지만 기준선보다 낮아 내린 쪽으로 멀어진 칸
        When: 판정하면
        Then: 방향이 「아래」다
        """
        # Given
        summary = _summary(win_rate=0.55, loss_rate=0.45, win_excess=-0.12, loss_excess=0.12, up_p=0.01, down_p=0.01)

        # When
        result = screen_candidates(summary, _periods([0.45, 0.43]), axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN


class TestHeldVerdict:
    """시기를 쪼갤 수 없는 칸이 탈락과 구분되는지 고정한다 (측정의 원칙 12)."""

    def test_시기_행이_없으면_보류다(self) -> None:
        """
        목적: **표본이 모자란 것과 기준에 못 미치는 것은 다르다.** 둘을 묶으면
              나중에 "왜 떨어졌나"를 되물을 수 없다.

        Given: 앞 셋은 통과하는데 시기 분할 행이 없는 칸
        When: 판정하면
        Then: 보류이고 시기 구간 수가 0 이다
        """
        # Given
        empty = _periods([]).iloc[0:0]

        # When
        result = screen_candidates(_down_summary(), empty, axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_HELD
        assert int(result[COL_PERIOD_COUNT].iloc[0]) == 0

    def test_앞_세_기준에_걸리면_시기가_없어도_탈락이다(self) -> None:
        """
        목적: 보류는 **다른 기준을 통과했을 때만** 쓴다. 이미 떨어진 칸을 보류로 두면
              통과 가능성이 남은 것처럼 읽힌다.

        Given: 적중률 미달이고 시기 분할 행도 없는 칸
        When: 판정하면
        Then: 보류가 아니라 탈락이다
        """
        # Given
        hit = MIN_HIT_RATE - 0.10
        summary = _down_summary(loss_rate=hit, win_rate=1.0 - hit)

        # When
        result = screen_candidates(summary, _periods([]).iloc[0:0], axis_column=AXIS)

        # Then
        assert result[COL_VERDICT].iloc[0] == VERDICT_FAIL


class TestAxisIndependence:
    """축을 모른다는 계약을 고정한다."""

    def test_만기월이_아닌_축에서도_동작한다(self) -> None:
        """
        목적: **축 이름을 인자로 받는다.** 이 모듈이 만기월에 맞춰지면 다음 검증이 다시 짜야 한다.

        Given: 축이 「요일」인 집계표
        When: 그 축 이름으로 판정하면
        Then: 축 컬럼이 결과에 그대로 남고 판정이 나온다
        """
        # Given
        axis = "요일"
        summary = _down_summary().rename(columns={AXIS: axis})
        periods = _periods([0.29, 0.25]).rename(columns={AXIS: axis})

        # When
        result = screen_candidates(summary, periods, axis_column=axis)

        # Then
        assert axis in result.columns
        assert result[COL_VERDICT].iloc[0] == VERDICT_PASS

    def test_결과_컬럼이_계약대로다(self) -> None:
        """
        목적: 산출물 스키마를 고정한다 — 계층 간 계약이다.

        Given: 정상 입력
        When: 판정하면
        Then: 축 컬럼 뒤에 `SCREENING_COLUMNS` 가 순서대로 온다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        assert list(result.columns) == [AXIS, *SCREENING_COLUMNS]

    def test_필수_컬럼이_없으면_예외다(self) -> None:
        """
        목적: 조용히 통과시키지 않는다. 비율 컬럼이 빠진 채로 판정하면 없는 우위를 보고하게 된다.

        Given: 내린 비율이 빠진 집계표
        When: 판정하면
        Then: ValueError 가 나고 메시지에 빠진 컬럼이 담긴다
        """
        # Given
        summary = _down_summary().drop(columns=[COL_LOSS_RATE])

        # When / Then
        with pytest.raises(ValueError, match=COL_LOSS_RATE):
            screen_candidates(summary, _periods([0.29, 0.25]), axis_column=AXIS)


class TestFormula:
    """산식을 손으로 계산한 값으로 박는다 (tests/CLAUDE.md 필수)."""

    def test_적중률과_차이가_방향에_맞게_실린다(self) -> None:
        """
        목적: 아래 방향 칸의 적중률은 **내린 비율**이고, 차이는 **내린 비율 차이**다.
              위 방향과 섞이면 값이 조용히 뒤집힌다.

        Given: 내린 비율 0.73 · 내린 비율 차이 0.23
        When: 판정하면
        Then: 적중률 0.73, 기준선 0.50, 차이 0.23 이 그대로 실린다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _periods([0.29, 0.25]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_HIT_RATE]) == pytest.approx(0.73, abs=EXACT_TOLERANCE)
        assert float(row[COL_BASELINE_GAP]) == pytest.approx(0.23, abs=EXACT_TOLERANCE)

    def test_시기_최솟값이_기록된다(self) -> None:
        """
        목적: 기준 4 의 판정 근거인 **가장 약한 시기**가 결과에 남는다.

        Given: 시기별 내린 비율 71%·62%
        When: 판정하면
        Then: 시기 최솟값이 0.62 이고 구간 수가 2 다
        """
        # Given
        periods = _periods([0.29, 0.38])

        # When
        result = screen_candidates(_down_summary(), periods, axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_PERIOD_MIN_HIT_RATE]) == pytest.approx(0.62, abs=EXACT_TOLERANCE)
        assert int(row[COL_PERIOD_COUNT]) == 2

    def test_표본이_보존된다(self) -> None:
        """
        목적: 판정이 칸을 조용히 버리지 않는다 (표본 보존).

        Given: 축 값이 셋인 집계표
        When: 판정하면
        Then: 세 칸이 모두 결과에 있다
        """
        # Given
        blocks = [_down_summary().assign(**{AXIS: value}) for value in (3, 6, 9)]
        summary = pd.concat(blocks, ignore_index=True)
        periods = pd.concat([_periods([0.29, 0.25], axis_value=value) for value in (3, 6, 9)], ignore_index=True)

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert sorted(result[AXIS].tolist()) == [3, 6, 9]
