"""후보 판정의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 판정은 두 겹이며 역할이 다르다.

- **1차 게이트** (적중률 · 방향 기대값) — 볼 목록에 올릴지를 가른다
- **등급** (기준선 대비 차이 · 우연확률 · 시기 안정성) — 얼마나 믿을 만한지를 알려주되 **떨어뜨리지 않는다**

핵심 계약은 다섯이다.
- 게이트를 넘으면 **나머지 셋을 하나도 충족하지 못해도 후보로 남는다** (판단은 사용자 몫)
- 방향 기대값은 **방향 부호를 적용한 평균**이다 — 「아래」 칸은 평균이 양수면 기대값이 음수다
- 오른 쪽과 내린 쪽을 **대칭으로** 판정한다 (측정의 원칙 11)
- 시기를 쪼갤 수 없으면 등급의 **분모가 줄 뿐** 미충족으로 세지 않는다 (측정의 원칙 12)
- 축 이름을 인자로 받아 **만기월이 아닌 축에서도** 그대로 동작한다
"""

import pandas as pd
import pytest

from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_PERIOD_COUNT,
    COL_PERIOD_MIN_HIT_RATE,
    COL_SCREEN,
    COL_SUPPORT_COUNT,
    COL_SUPPORT_TOTAL,
    COL_UNMET_SUPPORT,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MIN_BASELINE_GAP,
    MIN_EXPECTED_VALUE,
    MIN_HIT_RATE,
    MIN_PERIOD_HIT_RATE,
    SCREEN_CANDIDATE,
    SCREEN_EXCLUDED,
    SCREENING_COLUMNS,
    SUPPORT_GAP,
    SUPPORT_P_VALUE,
    SUPPORT_PERIOD,
    screen_candidates,
)
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
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
) -> pd.DataFrame:
    """한 칸짜리 집계표를 만든다."""
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
        }
    )


def _periods(rates: list[float], *, axis_value: int = 9, sample: int = 15) -> pd.DataFrame:
    """시기별 집계표를 만든다. `rates` 는 각 구간의 오른 비율이다."""
    return pd.DataFrame(
        {
            AXIS: [axis_value] * len(rates),
            COL_SAMPLE_COUNT: [sample] * len(rates),
            COL_WIN_RATE: rates,
            COL_LOSS_RATE: [1.0 - rate for rate in rates],
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
        목적: **이 개편의 핵심 계약이다.** 나머지 세 지표는 등급일 뿐 게이트가 아니므로,
              전부 미달이어도 게이트를 넘었으면 사용자가 볼 목록에 남는다.

        Given: 게이트는 넘지만 차이·우연확률·시기가 전부 미달인 칸
        When: 판정하면
        Then: 후보이고 등급이 0/3 이다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.01
        summary = _down_summary(loss_excess=gap, win_excess=-gap, down_p=0.40, up_p=0.40)
        weak = MIN_PERIOD_HIT_RATE - 0.10

        # When
        result = screen_candidates(summary, _periods([1.0 - weak, 1.0 - weak]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert row[COL_SCREEN] == SCREEN_CANDIDATE
        assert int(row[COL_SUPPORT_COUNT]) == 0
        assert int(row[COL_SUPPORT_TOTAL]) == 3

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

    def test_셋을_모두_충족하면_만점이고_미충족이_비어_있다(self) -> None:
        """
        목적: 등급의 만점 상태를 고정한다.

        Given: 차이·우연확률·시기가 모두 하한을 넘는 칸
        When: 판정하면
        Then: 3/3 이고 미충족 항목이 없다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 3
        assert int(row[COL_SUPPORT_TOTAL]) == 3
        assert row[COL_UNMET_SUPPORT] == ""

    def test_차이가_작으면_미충족에_남는다(self) -> None:
        """
        목적: **차이 항목 단독으로 등급을 깎는다.** 적중률이 높아도 기준선이 이미 높으면 우위가 아니다.

        Given: 기준선 대비 차이가 하한 미만
        When: 판정하면
        Then: 2/3 이고 미충족에 차이가 남는다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.01
        summary = _down_summary(loss_excess=gap, win_excess=-gap)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 2
        assert SUPPORT_GAP in str(row[COL_UNMET_SUPPORT])

    def test_우연확률이_높으면_미충족에_남는다(self) -> None:
        """
        목적: **우연확률 항목 단독으로 등급을 깎는다.** 표본이 작으면 큰 차이도 우연히 나온다.

        Given: 우연확률만 0.20
        When: 판정하면
        Then: 2/3 이고 미충족에 우연확률이 남는다
        """
        # Given
        summary = _down_summary(down_p=0.20, up_p=0.20)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 2
        assert SUPPORT_P_VALUE in str(row[COL_UNMET_SUPPORT])

    def test_한_시기라도_무너지면_미충족에_남는다(self) -> None:
        """
        목적: **시기 항목 단독으로 등급을 깎는다.** 한 시기가 만든 값을 드러낸다.

        Given: 전체는 73% 인데 뒤 시기가 하한 미만
        When: 판정하면
        Then: 2/3 이고 미충족에 시기가 남는다
        """
        # Given
        weak = MIN_PERIOD_HIT_RATE - 0.05

        # When
        result = screen_candidates(_down_summary(), _periods([0.29, 1.0 - weak]), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 2
        assert SUPPORT_PERIOD in str(row[COL_UNMET_SUPPORT])

    def test_미충족이_여럿이면_모두_남는다(self) -> None:
        """
        목적: 미충족이 **하나로 잘리지 않는다.** 무엇이 부족한지 전부 보여야 판단할 수 있다.

        Given: 차이와 우연확률 둘 다 미달
        When: 판정하면
        Then: 1/3 이고 둘 다 미충족에 남는다
        """
        # Given
        gap = MIN_BASELINE_GAP - 0.02
        summary = _down_summary(loss_excess=gap, win_excess=-gap, down_p=0.30, up_p=0.30)

        # When
        result = screen_candidates(summary, _strong_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 1
        assert SUPPORT_GAP in str(row[COL_UNMET_SUPPORT])
        assert SUPPORT_P_VALUE in str(row[COL_UNMET_SUPPORT])

    def test_시기를_못_재면_분모가_준다(self) -> None:
        """
        목적: **못 넘은 것과 못 물은 것은 다르다** (측정의 원칙 12).
              표본이 모자라 시기를 쪼갤 수 없었던 칸을 미충족으로 세면 부당하게 깎인다.

        Given: 앞 둘은 충족하는데 시기 분할 행이 없는 칸
        When: 판정하면
        Then: 2/2 이고 미충족이 비어 있으며 시기 구간 수가 0 이다
        """
        # Given / When
        result = screen_candidates(_down_summary(), _empty_periods(), axis_column=AXIS)

        # Then
        row = result.iloc[0]
        assert int(row[COL_SUPPORT_COUNT]) == 2
        assert int(row[COL_SUPPORT_TOTAL]) == 2
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
