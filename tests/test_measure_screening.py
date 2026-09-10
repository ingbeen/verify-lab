"""후보 판정의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 판정은 두 겹이며 역할이 다르다.

- **1차 게이트** (적중률 · 방향 기대값) — 볼 목록에 올릴지를 가른다
- **등급** (기준선 대비 차이 · 우연확률 · 시기 안정성 · 손익비) — 얼마나 믿을 만한지를 알려주되 **떨어뜨리지 않는다**

핵심 계약은 다섯이다.
- 게이트를 넘으면 **나머지 넷을 하나도 충족하지 못해도 후보로 남는다** (판단은 사용자 몫)
- 방향 기대값은 **방향 부호를 적용한 평균**이다 — 「아래」 칸은 평균이 양수면 기대값이 음수다
- 오른 쪽과 내린 쪽을 **대칭으로** 판정한다 (측정의 원칙 11)
- 시기를 쪼갤 수 없으면 등급의 **분모가 줄 뿐** 미충족으로 세지 않는다 (측정의 원칙 12)
- 축 이름을 인자로 받아 **만기월이 아닌 축에서도** 그대로 동작한다
"""

import pandas as pd
import pytest

from verify_lab.measure.constants import COL_JUDGEABLE, JUDGEABLE_NO, JUDGEABLE_YES
from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_BREAKEVEN_HIT_RATE,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_LOSING_COUNT,
    COL_PAYOFF_RATIO,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_SCREEN,
    COL_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL,
    COL_TOTAL_RETURN,
    COL_UNMET_SUPPORT,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MIN_BASELINE_GAP,
    MIN_EXPECTED_VALUE,
    MIN_HIT_RATE,
    MIN_PAYOFF_RATIO,
    MIN_PERIOD_HIT_RATE,
    SCREEN_CANDIDATE,
    SCREEN_EXCLUDED,
    SCREENING_COLUMNS,
    SUPPORT_GAP,
    SUPPORT_P_VALUE,
    SUPPORT_PAYOFF,
    SUPPORT_PERIOD,
    screen_candidates,
)
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_NEGATIVE_COUNT,
    COL_NEGATIVE_MEAN,
    COL_POSITIVE_COUNT,
    COL_POSITIVE_MEAN,
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
    mean: float,
    sample: int = 30,
    axis_value: int = 9,
    positive_mean: float = 0.010,
    negative_mean: float = 0.012,
    positive_count: int | None = None,
    negative_count: int | None = None,
) -> pd.DataFrame:
    """한 칸짜리 집계표를 만든다.

    양수·음수 평균의 기본값은 **아래 방향 칸에서 손익비 1.2** 가 되도록 잡았다
    (`_down_summary` 가 등급 만점이어야 한 조건씩 무너뜨리는 테스트가 성립한다).
    **위 방향 칸에서는 같은 값이 손익비 0.833 이 되어 미달**이므로, 위 방향으로 등급을
    다루는 테스트는 값을 명시해서 뒤집는다.

    **건수는 표본 수에서 파생시킨다.** 따로 두면 표본만 바꾼 테스트에서 둘이 어긋나
    「결정된 거래가 표본보다 많다」는 불변조건에 걸린다. 보합이 필요한 테스트는 건수를
    명시해서 **합이 표본보다 작게** 만든다.
    """
    positives = (sample * 4 // 15) if positive_count is None else positive_count
    negatives = (sample - positives) if negative_count is None else negative_count
    return pd.DataFrame(
        {
            AXIS: [axis_value],
            COL_SAMPLE_COUNT: [sample],
            COL_MEAN: [mean],
            COL_WIN_RATE: [win_rate],
            COL_LOSS_RATE: [loss_rate],
            COL_WIN_RATE_EXCESS: [win_excess],
            COL_LOSS_RATE_EXCESS: [loss_excess],
            COL_UP_RATE_P_VALUE: [up_p],
            COL_DOWN_RATE_P_VALUE: [down_p],
            COL_POSITIVE_MEAN: [positive_mean],
            COL_NEGATIVE_MEAN: [negative_mean],
            COL_POSITIVE_COUNT: [positives],
            COL_NEGATIVE_COUNT: [negatives],
        }
    )


def _periods(
    rates: list[float],
    *,
    loss_rates: list[float] | None = None,
    axis_value: int = 9,
    sample: int = 15,
    judgeable: list[str] | None = None,
) -> pd.DataFrame:
    """시기별 집계표를 만든다.

    Args:
        rates: 각 구간의 오른 비율
        loss_rates: 각 구간의 내린 비율. `None` 이면 **보합이 없다고 보고** `1 − 오른 비율` 로 채운다.
            **두 비율은 여집합이 아니므로**(보합이 어느 쪽에도 안 들어간다) 보합이 있는 칸을
            만들려면 반드시 명시한다
        axis_value: 축 값
        sample: 구간별 표본 수
        judgeable: 구간별 판정가능 여부. `None` 이면 전부 「예」다
    """
    return pd.DataFrame(
        {
            AXIS: [axis_value] * len(rates),
            COL_SAMPLE_COUNT: [sample] * len(rates),
            COL_WIN_RATE: rates,
            COL_LOSS_RATE: [1.0 - rate for rate in rates] if loss_rates is None else loss_rates,
            COL_JUDGEABLE: [JUDGEABLE_YES] * len(rates) if judgeable is None else judgeable,
        }
    )


def _empty_periods() -> pd.DataFrame:
    """시기를 쪼갤 수 없어 행이 하나도 없는 표."""
    return _periods([]).iloc[0:0]


def _down_summary(**overrides: float) -> pd.DataFrame:
    """게이트를 넘고 등급도 만점인 「아래 방향」 칸. 개별 값을 덮어써 한 조건씩 무너뜨린다.

    평균이 음수이므로 아래로 걸었을 때의 기대값은 양수다.
    """
    values: dict[str, float] = {
        "win_rate": 0.27,
        "loss_rate": 0.73,
        "win_excess": -0.23,
        "loss_excess": 0.23,
        "up_p": 0.003,
        "down_p": 0.003,
        "mean": -0.005,
    }
    values.update(overrides)

    return _summary(**values)  # type: ignore[arg-type]


def _strong_periods() -> pd.DataFrame:
    """아래 방향 기준으로 시기 적중률 71%·75% 인 표."""
    return _periods([0.29, 0.25])


class TestScreen:
    """1차 게이트가 무엇을 가르고 무엇을 가르지 않는지 고정한다."""

    def test_적중률과_기대값을_넘으면_후보다(self) -> None:
        """
        목적: 게이트 두 조건을 모두 넘은 칸은 후보로 올린다.

        Given: 아래로 73% 적중 · 평균 -0.5%(아래로 걸면 기대값 +0.5%)
        When: 판정하면
        Then: 후보이고 방향이 「아래」다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN

    def test_적중률이_낮으면_제외된다(self) -> None:
        """
        목적: **게이트 조건 1 단독으로 가른다.** 기대값이 좋아도 적중률이 낮으면 집행할 수 없다.

        Given: 기대값은 양수인데 적중률이 하한 미만
        When: 판정하면
        Then: 제외된다
        """
        # Given
        hit = MIN_HIT_RATE - 0.01
        summary = _down_summary(loss_rate=hit, win_rate=1.0 - hit)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_EXCLUDED

    def test_기대값이_음수면_제외된다(self) -> None:
        """
        목적: **게이트 조건 2 단독으로 가른다.** 이 조건이 없던 시기에 실제로 통과했던 칸이 있다 —
              SPY 3월은 3분의 2가 내렸지만 오르는 3분의 1이 크게 올라, 아래로 걸면 평균 손실이었다.

        Given: 아래 방향 · 적중률 64.7% 인데 평균이 +0.3123%(= 아래로 걸면 기대값 -0.3123%)
        When: 판정하면
        Then: 제외되고 기대값이 음수로 실린다
        """
        # Given
        summary = _down_summary(win_rate=0.353, loss_rate=0.647, mean=0.003123)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_EXCLUDED
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) == pytest.approx(-0.003123, abs=EXACT_TOLERANCE)

    def test_적중률이_하한과_정확히_같으면_후보다(self) -> None:
        """
        목적: 경계를 어느 쪽으로 여는지 고정한다. 하한은 **이상**이다.

        Given: 적중률이 하한과 정확히 같은 칸
        When: 판정하면
        Then: 후보다
        """
        # Given
        summary = _down_summary(loss_rate=MIN_HIT_RATE, win_rate=1.0 - MIN_HIT_RATE)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE

    def test_기대값이_정확히_0이면_제외된다(self) -> None:
        """
        목적: 기대값 경계는 **초과**다. 같은 금액을 반복 투자해 0 이 남는 것은 우위가 아니다.

        Given: 평균이 0 이라 기대값도 0 인 칸
        When: 판정하면
        Then: 제외된다
        """
        # Given
        summary = _down_summary(mean=MIN_EXPECTED_VALUE)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_EXCLUDED

    def test_등급을_하나도_충족하지_못해도_후보로_남는다(self) -> None:
        """
        목적: **이 개편의 핵심 계약이다.** 나머지 네 지표는 등급일 뿐 게이트가 아니므로,
              전부 미달이어도 게이트를 넘었으면 사용자가 볼 목록에 남는다.

        Given: 게이트는 넘지만 차이·우연확률·시기·손익비가 전부 미달인 칸
        When: 판정하면
        Then: 후보이고 등급이 0/4 이다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.01
        summary = _down_summary(
            loss_excess=gap,
            win_excess=-gap,
            down_p=0.40,
            up_p=0.40,
            positive_mean=0.012,
            negative_mean=0.010,
        )
        weak = MIN_PERIOD_HIT_RATE - 0.10

        # When
        result = screen_candidates(summary, _periods([1.0 - weak, 1.0 - weak]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert row[COL_SCREEN] == SCREEN_CANDIDATE
        assert int(row[COL_SUPPORT_COUNT]) == 0
        assert int(row[COL_SUPPORT_TOTAL]) == 4

    def test_제외된_칸도_행이_남는다(self) -> None:
        """
        목적: 판정이 칸을 **지우지 않는다.** 산출물에서 사라지면 사용자가 되짚을 수 없다.

        Given: 게이트를 넘는 칸과 못 넘는 칸이 섞인 집계표
        When: 판정하면
        Then: 두 칸이 모두 결과에 있다
        """
        # Given
        weak_hit = MIN_HIT_RATE - 0.10
        blocks = [
            _down_summary().assign(**{AXIS: 9}),
            _down_summary(loss_rate=weak_hit, win_rate=1.0 - weak_hit).assign(**{AXIS: 3}),
        ]
        summary = pd.concat(blocks, ignore_index=True)
        periods = pd.concat([_strong_periods().assign(**{AXIS: value}) for value in (3, 9)], ignore_index=True)

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert sorted(result[AXIS].tolist()) == [3, 9]
        assert sorted(result[COL_SCREEN].tolist()) == sorted([SCREEN_CANDIDATE, SCREEN_EXCLUDED])


class TestExpectedValue:
    """방향 기대값 산식을 실측값으로 박는다 (tests/CLAUDE.md 산식 고정 테스트)."""

    def test_아래_방향은_평균의_부호를_뒤집는다(self) -> None:
        """
        목적: 아래로 거는 신호에서 **주가가 내리면 버는 것**이다. 부호를 뒤집지 않으면
              손실 칸이 이익으로 보고된다.

        Given: 아래 방향 칸의 평균이 -0.9390%(DIA 9월 실측)
        When: 판정하면
        Then: 기대값이 +0.9390% 다
        """
        # Given
        summary = _down_summary(mean=-0.009390)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) == pytest.approx(0.009390, abs=EXACT_TOLERANCE)

    def test_위_방향은_평균을_그대로_쓴다(self) -> None:
        """
        목적: 위로 거는 신호에서는 평균이 곧 기대값이다.

        Given: 위 방향 칸의 평균이 +0.8959%(DIA 12월 실측)
        When: 판정하면
        Then: 기대값이 +0.8959% 다
        """
        # Given
        summary = _summary(
            win_rate=0.821,
            loss_rate=0.179,
            win_excess=0.235,
            loss_excess=-0.235,
            up_p=0.007,
            down_p=0.007,
            mean=0.008959,
        )

        # When
        result = screen_candidates(summary, _periods([0.71, 0.93]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert row[COL_DIRECTION] == DIRECTION_UP
        assert float(row[COL_EXPECTED_VALUE]) == pytest.approx(0.008959, abs=EXACT_TOLERANCE)


class TestSupport:
    """등급이 무엇을 세고 무엇을 세지 않는지 고정한다."""

    def test_넷을_모두_충족하면_만점이고_미충족이_비어_있다(self) -> None:
        """
        목적: 등급의 만점 상태를 고정한다.

        Given: 차이·우연확률·시기·손익비가 모두 하한을 넘는 칸
        When: 판정하면
        Then: 4/4 이고 미충족 항목이 없다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 4
        assert int(row[COL_SUPPORT_TOTAL]) == 4
        assert row[COL_UNMET_SUPPORT] == ""

    def test_차이가_작으면_미충족에_남는다(self) -> None:
        """
        목적: **차이 항목 단독으로 등급을 깎는다.** 적중률이 높아도 기준선이 이미 높으면 우위가 아니다.

        Given: 기준선 대비 차이가 하한 미만
        When: 판정하면
        Then: 3/4 이고 미충족에 차이가 남는다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.01
        summary = _down_summary(loss_excess=gap, win_excess=-gap)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 3
        assert SUPPORT_GAP in str(row[COL_UNMET_SUPPORT])

    def test_우연확률이_높으면_미충족에_남는다(self) -> None:
        """
        목적: **우연확률 항목 단독으로 등급을 깎는다.** 표본이 작으면 큰 차이도 우연히 나온다.

        Given: 우연확률만 0.20
        When: 판정하면
        Then: 3/4 이고 미충족에 우연확률이 남는다
        """
        # Given
        summary = _down_summary(down_p=0.20, up_p=0.20)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 3
        assert SUPPORT_P_VALUE in str(row[COL_UNMET_SUPPORT])

    def test_한_시기라도_무너지면_미충족에_남는다(self) -> None:
        """
        목적: **시기 항목 단독으로 등급을 깎는다.** 한 시기가 만든 값을 드러낸다.

        Given: 전체는 73% 인데 뒤 시기가 하한 미만
        When: 판정하면
        Then: 3/4 이고 미충족에 시기가 남는다
        """
        # Given
        weak = MIN_PERIOD_HIT_RATE - 0.05

        # When
        result = screen_candidates(_down_summary(), _periods([0.29, 1.0 - weak]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 3
        assert SUPPORT_PERIOD in str(row[COL_UNMET_SUPPORT])

    def test_미충족이_여럿이면_모두_남는다(self) -> None:
        """
        목적: 미충족이 **하나로 잘리지 않는다.** 무엇이 부족한지 전부 보여야 판단할 수 있다.

        Given: 차이와 우연확률 둘 다 미달
        When: 판정하면
        Then: 2/4 이고 둘 다 미충족에 남는다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.02
        summary = _down_summary(loss_excess=gap, win_excess=-gap, down_p=0.30, up_p=0.30)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 2
        assert SUPPORT_GAP in str(row[COL_UNMET_SUPPORT])
        assert SUPPORT_P_VALUE in str(row[COL_UNMET_SUPPORT])

    def test_시기를_못_재면_분모가_준다(self) -> None:
        """
        목적: **못 넘은 것과 못 물은 것은 다르다** (측정의 원칙 12).
              표본이 모자라 시기를 쪼갤 수 없었던 칸을 미충족으로 세면 부당하게 깎인다.

        Given: 앞 둘은 충족하는데 시기 분할 행이 없는 칸
        When: 판정하면
        Then: 3/3 이고 미충족이 비어 있으며 시기 구간 수가 0 이다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _empty_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 3
        assert int(row[COL_SUPPORT_TOTAL]) == 3
        assert row[COL_UNMET_SUPPORT] == ""
        assert int(row[COL_PERIOD_COUNT]) == 0

    def test_시기를_못_재도_게이트_판정은_그대로다(self) -> None:
        """
        목적: 시기 데이터의 유무가 **게이트를 흔들지 않는다.** 게이트는 적중률과 기대값만 본다.

        Given: 게이트를 넘고 시기 분할 행이 없는 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _empty_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE


class TestDirectionSymmetry:
    """오른 쪽과 내린 쪽을 대칭으로 판정하는지 고정한다 (측정의 원칙 11)."""

    def test_위로_멀어진_칸도_같은_기준으로_후보가_된다(self) -> None:
        """
        목적: **방향을 가리지 않는다.** 위로 멀어진 칸도 아래와 같은 기준으로 판정한다.

        Given: 오른 비율 73% · 기준선 대비 +23%p · 평균 +0.5%
        When: 판정하면
        Then: 후보이고 방향이 「위」다
        """
        # Given
        summary = _summary(
            win_rate=0.73,
            loss_rate=0.27,
            win_excess=0.23,
            loss_excess=-0.23,
            up_p=0.003,
            down_p=0.003,
            mean=0.005,
        )

        # When
        result = screen_candidates(summary, _periods([0.71, 0.75]), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE
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
        summary = _summary(
            win_rate=0.55,
            loss_rate=0.45,
            win_excess=-0.12,
            loss_excess=0.12,
            up_p=0.01,
            down_p=0.01,
            mean=-0.002,
        )

        # When
        result = screen_candidates(summary, _periods([0.45, 0.43]), axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN


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
        periods = _strong_periods().rename(columns={AXIS: axis})

        # When
        result = screen_candidates(summary, periods, axis_column=axis)

        # Then
        assert axis in result.columns
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE

    def test_결과_컬럼이_계약대로다(self) -> None:
        """
        목적: 산출물 스키마를 고정한다 — 계층 간 계약이다.

        Given: 정상 입력
        When: 판정하면
        Then: 축 컬럼 뒤에 `SCREENING_COLUMNS` 가 순서대로 온다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _strong_periods(), axis_column=AXIS)

        # Then
        assert list(result.columns) == [AXIS, *SCREENING_COLUMNS]

    def test_축_순서가_유지된다(self) -> None:
        """
        목적: **정렬은 이 계층의 일이 아니다.** 산출물이 축 순서로 읽히도록 두고,
              적중률 정렬 같은 표시 규칙은 상위 계층이 건다.

        Given: 축 값이 뒤섞여 들어온 집계표
        When: 판정하면
        Then: 축 오름차순으로 나온다
        """
        # Given
        blocks = [_down_summary().assign(**{AXIS: value}) for value in (9, 3, 6)]
        summary = pd.concat(blocks, ignore_index=True)
        periods = pd.concat([_strong_periods().assign(**{AXIS: value}) for value in (3, 6, 9)], ignore_index=True)

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert result[AXIS].tolist() == [3, 6, 9]

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
            screen_candidates(summary, _strong_periods(), axis_column=AXIS)

    def test_평균이_없으면_예외다(self) -> None:
        """
        목적: 기대값의 입력이 빠지면 **조용히 판정을 건너뛰지 않는다.**
              평균 없이 게이트를 통과시키면 손실 칸이 후보로 올라간다.

        Given: 평균이 빠진 집계표
        When: 판정하면
        Then: ValueError 가 나고 메시지에 빠진 컬럼이 담긴다
        """
        # Given
        summary = _down_summary().drop(columns=[COL_MEAN])

        # When / Then
        with pytest.raises(ValueError, match=COL_MEAN):
            screen_candidates(summary, _strong_periods(), axis_column=AXIS)

    def test_시기표에_내린_비율이_없으면_예외다(self) -> None:
        """
        목적: 시기표도 집계표와 **같은 강도로** 검증한다.
              컬럼이 없는 채로 넘어가면 판정이 KeyError 로 죽거나 조용히 건너뛴다.

        Given: 내린 비율이 빠진 시기표
        When: 판정하면
        Then: ValueError 가 나고 메시지에 빠진 컬럼이 담긴다
        """
        # Given
        periods = _strong_periods().drop(columns=[COL_LOSS_RATE])

        # When / Then
        with pytest.raises(ValueError, match=COL_LOSS_RATE):
            screen_candidates(_down_summary(), periods, axis_column=AXIS)

    def test_시기표에_축_컬럼이_없으면_예외다(self) -> None:
        """
        목적: 축이 없으면 어느 칸의 시기인지 모른다. 조용히 빈 결과로 넘기지 않는다.

        Given: 축 컬럼이 빠진 시기표
        When: 판정하면
        Then: ValueError 가 난다
        """
        # Given
        periods = _strong_periods().drop(columns=[AXIS])

        # When / Then
        with pytest.raises(ValueError, match=AXIS):
            screen_candidates(_down_summary(), periods, axis_column=AXIS)


class TestFormula:
    """산식을 손으로 계산한 값으로 박는다 (tests/CLAUDE.md 필수)."""

    def test_적중률과_차이가_방향에_맞게_실린다(self) -> None:
        """
        목적: 아래 방향 칸의 적중률은 **내린 비율**이고, 차이는 **내린 비율 차이**다.
              위 방향과 섞이면 값이 조용히 뒤집힌다.

        Given: 내린 비율 0.73 · 내린 비율 차이 0.23
        When: 판정하면
        Then: 적중률 0.73, 차이 0.23 이 그대로 실린다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_HIT_RATE]) == pytest.approx(0.73, abs=EXACT_TOLERANCE)
        assert float(row[COL_BASELINE_GAP]) == pytest.approx(0.23, abs=EXACT_TOLERANCE)

    def test_시기_적중률은_내린_비율을_직접_읽는다(self) -> None:
        """
        목적: 시기 항목도 전체 축과 **같은 컬럼**을 읽는다 (판정식 단일화).
              `1 − 오른 비율` 로 만들면 **보합이 통째로 「내림」으로 새어** 등급이 관대해진다.

        Given: 오른 30% · 내린 50% 인 시기 두 칸 (보합 20%)
        When: 「아래」 방향 칸을 판정하면
        Then: 시기 적중률이 내린 비율 0.50 이다 (`1 − 0.30 = 0.70` 이 아니다)
        """
        # Given
        periods = _periods([0.30, 0.30], loss_rates=[0.50, 0.50])

        # When
        result = screen_candidates(_down_summary(), periods, axis_column=AXIS)

        # Then
        assert float(result.iloc[0][COL_PERIOD_MIN_HIT_RATE]) == pytest.approx(0.50, abs=EXACT_TOLERANCE)

    def test_보합이_있으면_시기_항목이_미충족이_된다(self) -> None:
        """
        목적: 위 버그가 **판정을 뒤집는다**는 것을 고정한다.
              실제 내린 비율 0.50 은 하한 0.55 에 못 미치는데, `1 − 0.30 = 0.70` 은 넘는다.

        Given: 오른 30% · 내린 50% 인 시기 두 칸 (보합 20%)
        When: 등급이 만점인 「아래」 방향 칸을 판정하면
        Then: 시기 항목이 미충족으로 남는다
        """
        # Given
        periods = _periods([0.30, 0.30], loss_rates=[0.50, 0.50])

        # When
        result = screen_candidates(_down_summary(), periods, axis_column=AXIS)

        # Then
        assert SUPPORT_PERIOD in str(result.iloc[0][COL_UNMET_SUPPORT])

    def test_보합이_없으면_두_방식의_값이_같다(self) -> None:
        """
        목적: 수정이 **기존 결과를 바꾸지 않는** 범위를 고정한다 (회귀 보호).
              보합이 0인 칸에서는 `내린 비율 == 1 − 오른 비율` 이라 값이 그대로여야 한다.

        Given: 오른 29% · 내린 71% 인 시기 칸 (보합 0)
        When: 「아래」 방향 칸을 판정하면
        Then: 시기 적중률이 0.71 이고 시기 항목이 충족된다
        """
        # Given
        periods = _periods([0.29, 0.25])

        # When
        result = screen_candidates(_down_summary(), periods, axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_PERIOD_MIN_HIT_RATE]) == pytest.approx(0.71, abs=EXACT_TOLERANCE)
        assert SUPPORT_PERIOD not in str(row[COL_UNMET_SUPPORT])

    def test_위_방향은_오른_비율을_직접_읽는다(self) -> None:
        """
        목적: 「위」 방향은 보합과 무관하게 오른 비율을 그대로 쓴다 (대칭 확인).

        Given: 오른 72% · 내린 20% 인 시기 두 칸 (보합 8%)
        When: 「위」 방향 칸을 판정하면
        Then: 시기 적중률이 0.72 다
        """
        # Given
        summary = _summary(
            win_rate=0.72,
            loss_rate=0.20,
            win_excess=0.20,
            loss_excess=-0.20,
            up_p=0.004,
            down_p=0.004,
            mean=0.006,
        )
        periods = _periods([0.72, 0.72], loss_rates=[0.20, 0.20])

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert float(result.iloc[0][COL_PERIOD_MIN_HIT_RATE]) == pytest.approx(0.72, abs=EXACT_TOLERANCE)

    def test_시기_최솟값이_기록된다(self) -> None:
        """
        목적: 시기 항목의 판정 근거인 **가장 약한 시기**가 결과에 남는다.

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
        periods = pd.concat([_strong_periods().assign(**{AXIS: value}) for value in (3, 6, 9)], ignore_index=True)

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS)

        # Then
        assert sorted(result[AXIS].tolist()) == [3, 6, 9]


class TestTotalReturn:
    """합산 수익률 계약 (루트 `CLAUDE.md` 측정의 원칙 16)

    신호가 드물거나 보유가 며칠짜리인 매매법은 **회당 평균이 구조적으로 작게 나온다.**
    회당 값만 적으면 크기 감각이 없고 왕복 수수료와 견줘야 할 값인지도 보이지 않으므로,
    **같은 금액을 표본 수만큼 반복 투자했을 때의 단순 합**을 같은 표에 둔다.

    **게이트는 회당 기대값 그대로다** — 합산은 표시용이며 기준을 바꾸지 않는다.
    """

    def test_합산은_기대값_곱하기_표본_수다(self) -> None:
        """
        목적: 합산 수익률의 산식을 고정한다

        Given: 평균 -0.5% · 표본 30건인 「아래」 칸 (아래로 걸면 회당 +0.5%)
        When: 판정하면
        Then: 합산이 +15% 다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_TOTAL_RETURN]) == pytest.approx(0.005 * 30, abs=EXACT_TOLERANCE)

    def test_표본이_다르면_회당과_합산의_순서가_갈릴_수_있다(self) -> None:
        """
        목적: **합산을 표본 수 없이 비교하면 안 되는 이유**를 계약으로 남긴다

        실물 사례가 그대로 재현된다 — 옵션 만기일에서 회당은 KODEX 200 9월(23건 +1.25%)이
        SPY 9월(33건 +0.88%)을 앞서지만 합산은 뒤집힌다.

        Given: 회당이 큰 소표본 칸과 회당이 작은 대표본 칸
        When: 판정하면
        Then: **회당의 대소와 합산의 대소가 반대**다
        """
        # Given
        small = _down_summary(mean=-0.0125, sample=23, axis_value=9)
        large = _down_summary(mean=-0.0088, sample=33, axis_value=12)
        summary = pd.concat([small, large], ignore_index=True)
        periods = pd.concat([_strong_periods().assign(**{AXIS: value}) for value in (9, 12)], ignore_index=True)

        # When
        result = screen_candidates(summary, periods, axis_column=AXIS).set_index(AXIS)

        # Then
        assert float(result.loc[9, COL_EXPECTED_VALUE]) > float(result.loc[12, COL_EXPECTED_VALUE])
        assert float(result.loc[9, COL_TOTAL_RETURN]) < float(result.loc[12, COL_TOTAL_RETURN])

    def test_아래_방향은_합산도_부호가_뒤집힌다(self) -> None:
        """
        목적: 합산이 회당과 **같은 방향 규칙**을 쓰는지 고정한다 (엣지 케이스)

        Given: 평균이 **양수**인 「아래」 칸 (걸면 잃는다 — SPY 3월이 실물 사례)
        When: 판정하면
        Then: 합산도 음수다
        """
        # Given
        summary = _down_summary(mean=0.003)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert float(row[COL_TOTAL_RETURN]) == pytest.approx(-0.003 * 30, abs=EXACT_TOLERANCE)

    def test_합산은_게이트_판정을_바꾸지_않는다(self) -> None:
        """
        목적: 합산이 표시용이라는 원칙 16 의 단서를 고정한다

        표본이 1건이면 합산은 회당과 같아 작아지지만, 게이트는 회당 기대값으로만 판정한다.

        Given: 표본 1건인 「아래」 칸
        When: 판정하면
        Then: 여전히 후보다
        """
        # Given
        summary = _down_summary(sample=1)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result.iloc[0][COL_SCREEN] == SCREEN_CANDIDATE

    def test_합산_컬럼이_판정표_스키마에_있다(self) -> None:
        """
        목적: 산출물 컬럼 목록에서 빠지지 않는지 고정한다

        `candidates.csv` 를 사용자가 직접 열어 읽으므로 스키마가 계약이다.

        Given: 판정표 스키마
        When: 컬럼을 봤을 때
        Then: 합산 수익률이 들어 있다
        """
        assert COL_TOTAL_RETURN in SCREENING_COLUMNS


class TestJudgeablePeriodFilter:
    """**판정할 수 없는 시기 행은 등급에 넣지 않는다.**

    측정의 원칙 17 에 따라 표본이 모자란 구간도 산출물에는 행이 남는다. 그 행을 그대로
    등급에 넣으면 «못 물은 것»이 «못 넘은 것»으로 바뀌어, 표본이 작다는 이유로 두 번 깎인다.
    산출물 복원이 판정을 흔들지 않는다는 것이 이 계층의 계약이다.
    """

    def test_판정_불가_구간은_등급_분모에서_빠진다(self) -> None:
        """
        목적: 판정 불가 행이 늘어도 등급이 그대로임을 고정한다

        Given: 시기 두 구간이 전부 「아니오」인 표
        When: 판정하면
        Then: 시기 항목을 묻지 않은 것과 같아 분모가 3 이고 구간 수가 0 이다
        """
        # Given
        periods = _periods([0.29, 0.25], judgeable=[JUDGEABLE_NO, JUDGEABLE_NO])

        # When
        row = screen_candidates(_down_summary(), periods, axis_column=AXIS).iloc[0]

        # Then
        assert int(row[COL_SUPPORT_TOTAL]) == 3, "판정 불가 구간이 등급 분모에 들어갔습니다"
        assert int(row[COL_PERIOD_COUNT]) == 0
        assert SUPPORT_PERIOD not in str(row[COL_UNMET_SUPPORT])

    def test_판정_불가_행이_섞여도_가능한_구간만_본다(self) -> None:
        """
        목적: 섞인 표에서 판정 가능한 구간만 골라 쓰는지 고정한다

        Given: 적중률이 무너진 구간이 「아니오」, 살아 있는 구간이 「예」인 표
        When: 판정하면
        Then: 가장 약한 시기가 「예」인 구간의 값이고 시기 항목을 충족한다
        """
        # Given
        periods = _periods([0.90, 0.25], judgeable=[JUDGEABLE_NO, JUDGEABLE_YES])

        # When
        row = screen_candidates(_down_summary(), periods, axis_column=AXIS).iloc[0]

        # Then
        assert int(row[COL_PERIOD_COUNT]) == 1
        assert float(row[COL_PERIOD_MIN_HIT_RATE]) == pytest.approx(0.75, abs=EXACT_TOLERANCE)
        assert SUPPORT_PERIOD not in str(row[COL_UNMET_SUPPORT])

    def test_판정_가능한_구간이_무너지면_시기_항목을_못_넘는다(self) -> None:
        """
        목적: 필터가 시기 항목을 무력화하지 않음을 고정한다

        Given: 판정 가능한 구간의 적중률이 하한 아래인 표
        When: 판정하면
        Then: 시기 항목이 미충족으로 남는다
        """
        # Given
        periods = _periods([0.29, 0.60], judgeable=[JUDGEABLE_YES, JUDGEABLE_YES])

        # When
        row = screen_candidates(_down_summary(), periods, axis_column=AXIS).iloc[0]

        # Then
        assert int(row[COL_SUPPORT_TOTAL]) == 4
        assert SUPPORT_PERIOD in str(row[COL_UNMET_SUPPORT])


class TestPayoffSupport:
    """손익비 등급 항목의 계약을 고정한다.

    **손익비는 게이트가 아니라 등급이다.** 실측에서 채택 매매법(DIA 12월)이 손익비 1.034 로
    1.0 에 붙어 있고 그 값이 **진 거래 5건**으로 만들어졌다. 구간을 쪼개면 분모가 1~2건이
    되어 값이 폭주한다(SPY 12월 최근 10년 16.822, 진 2건). **게이트로 쓰면 데이터
    갱신만으로 채택 매매법이 죽고, 전승 구간에서는 아예 정의되지 않는다.**

    반대로 등급으로는 충분히 갈린다 — KODEX 200 9월은 0.788 이고 진 7건으로 만들어졌다.
    """

    def test_뒷받침_분모가_넷이_된다(self) -> None:
        """
        목적: 등급 항목이 조용히 빠지면 분모만 줄어 판정이 관대해진다.

        Given: 시기를 물을 수 있는 칸
        When: 판정하면
        Then: 뒷받침 분모가 4 다 (차이 · 우연확률 · 시기 · 손익비)
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert int(result[COL_SUPPORT_TOTAL].iloc[0]) == 4

    def test_손익비가_미달이어도_후보로_남는다(self) -> None:
        """
        목적: **등급은 떨어뜨리지 않는다.** 이 계약이 깨지면 손익비가 사실상 게이트가 된다.

        Given: 게이트를 넘지만 손익비가 1 미만인 아래 방향 칸
        When: 판정하면
        Then: 1차 판정은 후보이고 미충족에 「손익비」가 적힌다
        """
        # Given
        summary = _down_summary(positive_mean=0.012, negative_mean=0.010)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE
        assert SUPPORT_PAYOFF in result[COL_UNMET_SUPPORT].iloc[0]

    def test_아래로_거는_칸은_손익비가_뒤집힌다(self) -> None:
        """
        목적: 방향을 안 뒤집으면 예외 없이 값만 뒤집힌다.

        Given: 양수 평균 1.0% · 음수 평균 1.2% 인 **아래 방향** 칸
        When: 판정하면
        Then: 손익비가 1.2 다 — 주가가 내릴 때 버는 쪽이므로 음수가 이길 때다
        """
        # Given
        summary = _down_summary(positive_mean=0.010, negative_mean=0.012)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN
        assert float(result[COL_PAYOFF_RATIO].iloc[0]) == pytest.approx(1.2, abs=EXACT_TOLERANCE)

    def test_질_때_표본이_방향을_따라간다(self) -> None:
        """
        목적: 손익비의 분모가 몇 건인지가 곧 그 값의 신뢰도다 (측정의 원칙 3).

        Given: 양수 8건 · 음수 22건 인 아래 방향 칸
        When: 판정하면
        Then: 빗나간 표본은 **양수 건수**인 8 이다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert int(result[COL_LOSING_COUNT].iloc[0]) == 8

    def test_손익분기_적중률이_함께_나온다(self) -> None:
        """
        목적: 항등식 `손익분기 = 1 ÷ (1 + 손익비)` 를 판정표에 박는다.

        Given: 손익비 1.2 가 나오는 아래 방향 칸
        When: 판정하면
        Then: 손익분기 적중률이 1/2.2 다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert float(result[COL_BREAKEVEN_HIT_RATE].iloc[0]) == pytest.approx(1.0 / 2.2, abs=EXACT_TOLERANCE)

    def test_빗나간_거래가_없으면_충족으로_센다(self) -> None:
        """
        목적: 전승 칸은 손익비가 무한대이므로 **어떤 기준도 넘는다.**
        비우고 미충족으로 세면 「못 물은 것」이 「못 넘은 것」으로 바뀌어 **가장 좋은 칸이 깎인다.**

        실측: 옵션 만기일 DIA 12월의 최근 10년·최근 5년이 진 거래 0건이다.

        Given: 아래 방향인데 양수(= 빗나간 쪽)가 0건인 칸
        When: 판정하면
        Then: 손익비는 비어 있고 미충족에 「손익비」가 없다
        """
        # Given
        summary = _down_summary(positive_mean=float("nan"), positive_count=0, negative_count=30)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert pd.isna(result[COL_PAYOFF_RATIO].iloc[0])
        assert SUPPORT_PAYOFF not in result[COL_UNMET_SUPPORT].iloc[0]

    def test_표본이_없는_칸은_항목을_묻지_않는다(self) -> None:
        """
        목적: 잴 수 없는 것을 미충족으로 세면 표본이 작다는 이유로 두 번 깎인다.
        시기 항목과 같은 처리다 (측정의 원칙 12).

        Given: 유효 표본이 0건인 칸
        When: 판정하면
        Then: 뒷받침 분모에서 손익비가 빠진다
        """
        # Given
        summary = _down_summary(sample=0, positive_count=0, negative_count=0)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert int(result[COL_SUPPORT_TOTAL].iloc[0]) == 3

    def test_임계값과_같으면_충족이다(self) -> None:
        """
        목적: 경계가 어느 쪽에 속하는지 고정한다. 하한은 **이상**이다.

        Given: 손익비가 정확히 하한인 아래 방향 칸
        When: 판정하면
        Then: 미충족에 「손익비」가 없다
        """
        # Given
        summary = _down_summary(positive_mean=0.010, negative_mean=0.010 * MIN_PAYOFF_RATIO)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert SUPPORT_PAYOFF not in result[COL_UNMET_SUPPORT].iloc[0]

    def test_판정표_스키마에_들어_있다(self) -> None:
        """
        목적: 컬럼이 스키마에 없으면 저장 단계에서 조용히 빠진다.

        Given: 아무 칸
        When: 판정하면
        Then: 세 컬럼이 `SCREENING_COLUMNS` 에 있다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        for column in (COL_PAYOFF_RATIO, COL_BREAKEVEN_HIT_RATE, COL_LOSING_COUNT):
            assert column in SCREENING_COLUMNS
            assert column in result.columns


class TestGateUnchanged:
    """손익비를 더해도 **1차 게이트가 그대로**임을 고정한다.

    이 계약이 깨지면 검증 #1 192칸·검증 #10 616칸의 통과/탈락이 조용히 달라진다.
    """

    def test_손익비가_0이어도_게이트는_두_축으로만_가른다(self) -> None:
        """
        목적: 게이트 조건에 손익비가 섞이지 않았음을 확인한다.

        Given: 적중률과 기대값은 넘지만 손익비가 바닥인 칸
        When: 판정하면
        Then: 후보다
        """
        # Given
        summary = _down_summary(negative_mean=0.0001)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE

    def test_손익비가_좋아도_게이트를_못_넘으면_제외다(self) -> None:
        """
        목적: 등급이 게이트를 되살리지 못한다.

        Given: 손익비는 높지만 적중률이 하한 아래인 칸
        When: 판정하면
        Then: 제외다
        """
        # Given
        summary = _down_summary(loss_rate=MIN_HIT_RATE - 0.01, negative_mean=0.10)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_EXCLUDED


class TestAllFlatCell:
    """전부 보합인 칸이 **전승 칸으로 읽히지 않는지** 고정한다."""

    def test_전부_보합인_칸은_손익비를_묻지_않는다(self) -> None:
        """
        목적: 표본 수로 재면 「한 번도 지지 않았다」가 되어 **진짜 전승 칸과 구별되지 않는다.**
              이긴 적도 진 적도 없는 것은 「잴 수 없었다」이지 「좋았다」가 아니다.

        Given: 표본은 30건인데 이김도 짐도 0건인 칸 (전부 보합)
        When: 판정하면
        Then: 뒷받침 분모에서 손익비가 빠진다
        """
        # Given
        summary = _down_summary(
            positive_mean=float("nan"),
            negative_mean=float("nan"),
            positive_count=0,
            negative_count=0,
        )

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert int(result[COL_SUPPORT_TOTAL].iloc[0]) == 3
        assert SUPPORT_PAYOFF not in result[COL_UNMET_SUPPORT].iloc[0]

    def test_전승_칸은_손익비를_충족으로_센다(self) -> None:
        """
        목적: 위 테스트와 짝이다. **진 적이 없는 것과 이긴 적도 없는 것을 가른다.**

        Given: 표본 30건이 전부 이긴 칸 (아래 방향이므로 음수 쪽이 이긴 것)
        When: 판정하면
        Then: 손익비를 묻되 충족으로 센다
        """
        # Given
        summary = _down_summary(
            positive_mean=float("nan"),
            negative_mean=0.012,
            positive_count=0,
            negative_count=30,
        )

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        assert int(result[COL_SUPPORT_TOTAL].iloc[0]) == 4
        assert SUPPORT_PAYOFF not in result[COL_UNMET_SUPPORT].iloc[0]
        assert pd.isna(result[COL_PAYOFF_RATIO].iloc[0])
