"""후보 판정의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 판정은 **게이트 하나뿐**이다.

- **게이트** (적중률 · 방향 기대값) — 볼 목록에 올릴지를 가른다. 이것 말고는 아무것도 떨어뜨리지 않는다

**등급은 없다** (2026-09-12 개편). 전에는 기준선 대비 차이·우연확률·시기 안정성·손익비 넷을
「충족/물음」으로 셌는데, 같은 것을 구간 게이트가 다른 기준(55% 대 60%)으로 또 묻고 있었다.
**판단은 사용자가 한다** — 코드는 볼 목록만 만든다.

핵심 계약은 다섯이다.
- 게이트 두 축**만** 가른다 — 기준선 대비 차이가 0 이어도, 우연확률이 1 이어도 후보로 남는다
- 방향 기대값은 **방향 부호를 적용한 평균**이다 — 「아래」 칸은 평균이 양수면 기대값이 음수다
- 방향은 **절대 비율이 아니라 기준선과의 거리**로 정한다 (측정의 원칙 11)
- **표본이 1건이어도 판정한다** — 과대평가 가능성은 표본 수를 보고 사용자가 판단한다
- **살 수 없는 대상(지수)은 판정하지 않는다** — 값은 내되 「판정 안 함」으로 남는다
"""

import pandas as pd
import pytest

from verify_lab.measure.screening import (
    COL_BASELINE_GAP,
    COL_BASELINE_HIT_RATE,
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_SCREEN,
    COL_TOTAL_RETURN,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MIN_EXPECTED_VALUE,
    MIN_HIT_RATE,
    SCREEN_CANDIDATE,
    SCREEN_EXCLUDED,
    SCREEN_NOT_JUDGED,
    SCREENING_COLUMNS,
    screen_candidates,
)
from verify_lab.measure.statistics import (
    COL_LOSS_RATE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN,
    COL_SAMPLE_COUNT,
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
    mean: float,
    sample: int = 30,
    axis_value: int = 9,
) -> pd.DataFrame:
    """한 칸짜리 집계표를 만든다.

    **두 방향 비율을 여집합으로 만들지 않는다.** 보합(수익률이 정확히 0)이 어느 쪽에도
    들어가지 않으므로, 호출하는 쪽이 둘을 따로 준다 (tests/CLAUDE.md 「픽스처가 코드와 같은
    가정을 하면 그 버그는 영원히 안 잡힌다」).
    """
    return pd.DataFrame(
        {
            AXIS: [axis_value],
            COL_SAMPLE_COUNT: [sample],
            COL_MEAN: [mean],
            COL_WIN_RATE: [win_rate],
            COL_LOSS_RATE: [loss_rate],
            COL_WIN_RATE_EXCESS: [win_excess],
            COL_LOSS_RATE_EXCESS: [loss_excess],
        }
    )


def _down_summary(**overrides: float) -> pd.DataFrame:
    """게이트를 넘는 「아래 방향」 칸. 개별 값을 덮어써 한 조건씩 무너뜨린다.

    평균이 음수이므로 아래로 걸었을 때의 기대값은 양수다.
    """
    values: dict[str, float] = {
        "win_rate": 0.27,
        "loss_rate": 0.73,
        "win_excess": -0.23,
        "loss_excess": 0.23,
        "mean": -0.005,
    }
    values.update(overrides)

    return _summary(**values)  # type: ignore[arg-type]


class TestScreen:
    """게이트가 무엇을 가르고 무엇을 가르지 «않는지» 고정한다."""

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
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

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
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

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
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

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
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

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
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_EXCLUDED

    def test_기준선과_똑같아도_게이트를_넘으면_후보다(self) -> None:
        """
        목적: **이 개편의 핵심 계약이다.** 게이트는 두 축뿐이므로 기준선 대비 차이가 0 이어도
              후보로 남는다. 실물 사례가 SPY 11월 — 적중률 66.7% 인데 기준선도 66.7% 다.
              **그 사실은 컬럼으로 보여 주고, 뺄지는 사용자가 정한다.**

        Given: SPY 11월 그대로 — 오른 비율 66.7% 인데 기준선도 66.7% 라 차이가 0 인 칸
        When: 판정하면
        Then: 후보이고 기준선 대비 차이가 0 으로 실린다
        """
        # Given
        summary = _summary(
            win_rate=0.667,
            loss_rate=0.333,
            win_excess=0.0,
            loss_excess=0.0,
            mean=0.0074,
        )

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        row = result.iloc[0]
        assert row[COL_SCREEN] == SCREEN_CANDIDATE
        assert float(row[COL_BASELINE_GAP]) == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_표본이_1건이어도_판정한다(self) -> None:
        """
        목적: **표본 하한을 게이트에 걸지 않는다** (2026-09-12 사용자 결정).
              과대평가 가능성은 표본 수를 보고 사용자가 판단한다.

        Given: 표본이 1건뿐인 칸 (적중률 100% · 기대값 양수)
        When: 판정하면
        Then: 후보이고 표본 수가 그대로 실린다
        """
        # Given
        summary = _down_summary(win_rate=0.0, loss_rate=1.0, sample=1)

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        row = result.iloc[0]
        assert row[COL_SCREEN] == SCREEN_CANDIDATE
        assert int(row[COL_SAMPLE_COUNT]) == 1

    def test_표본이_0건이면_판정하지_않는다(self) -> None:
        """
        목적: **「재봤더니 아니었다」와 「재본 적이 없다」를 가른다.** 표본 0건 칸은 적중률·평균이
              `NaN` 이라 비교가 전부 거짓이 되고, 가만히 두면 **「제외」로 찍힌다.**

        Given: 표본이 0건이고 지표가 결측인 칸
        When: 살 수 있는 대상으로 판정하면
        Then: 제외가 아니라 「판정 안 함」이다
        """
        # Given
        summary = _summary(
            win_rate=float("nan"),
            loss_rate=float("nan"),
            win_excess=float("nan"),
            loss_excess=float("nan"),
            mean=float("nan"),
            sample=0,
        )

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_NOT_JUDGED

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

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert sorted(result[AXIS].tolist()) == [3, 9]
        assert sorted(result[COL_SCREEN].tolist()) == sorted([SCREEN_CANDIDATE, SCREEN_EXCLUDED])


class TestNotJudged:
    """살 수 없는 대상은 값만 내고 판정하지 않는다 (측정의 원칙 9)."""

    def test_살_수_없는_대상은_판정_안_함으로_남는다(self) -> None:
        """
        목적: **지수로 「우위가 있다」를 주장하지 않는다.** 긴 시계열은 참고로 쓰되
              그 결과가 살 수 있는 대상의 판정을 대신하면 안 된다.

        Given: 게이트를 넉넉히 넘는 칸
        When: 살 수 없는 대상으로 판정하면
        Then: 후보가 아니라 「판정 안 함」이다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=False)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_NOT_JUDGED

    def test_판정_안_해도_값은_그대로_실린다(self) -> None:
        """
        목적: 판정을 막는 것이지 **값을 지우는 것이 아니다.** 참고하려면 숫자가 있어야 한다.

        Given: 같은 칸
        When: 살 수 있는 대상과 없는 대상으로 각각 판정하면
        Then: 「1차 판정」만 다르고 나머지 값이 전부 같다
        """
        # Given
        summary = _down_summary()

        # When
        judged = screen_candidates(summary, axis_column=AXIS, tradable=True)
        unjudged = screen_candidates(summary, axis_column=AXIS, tradable=False)

        # Then
        pd.testing.assert_frame_equal(
            judged.drop(columns=[COL_SCREEN]),
            unjudged.drop(columns=[COL_SCREEN]),
        )

    def test_게이트를_못_넘어도_판정_안_함이다(self) -> None:
        """
        목적: 「판정 안 함」이 「제외」를 덮는다. 살 수 없는 대상에는 합격도 불합격도 없다.

        Given: 적중률이 하한에 못 미치는 칸
        When: 살 수 없는 대상으로 판정하면
        Then: 제외가 아니라 「판정 안 함」이다
        """
        # Given
        weak = MIN_HIT_RATE - 0.10
        summary = _down_summary(loss_rate=weak, win_rate=1.0 - weak)

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=False)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_NOT_JUDGED


class TestExpectedValue:
    """방향 기대값 산식을 실측값으로 박는다 (tests/CLAUDE.md 산식 고정 테스트)."""

    def test_아래_방향은_평균의_부호를_뒤집는다(self) -> None:
        """
        목적: 아래로 걸면 주가가 내릴 때 버는 것이므로 평균의 부호가 뒤집힌다.

        Given: 아래 방향 칸의 평균이 -0.5%
        When: 판정하면
        Then: 방향 기대값이 +0.5% 다
        """
        # Given
        summary = _down_summary(mean=-0.005)

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) == pytest.approx(0.005, abs=EXACT_TOLERANCE)

    def test_위_방향은_평균을_그대로_쓴다(self) -> None:
        """
        목적: 위로 걸면 평균이 곧 기대값이다.

        Given: 위 방향 칸의 평균이 +0.7%
        When: 판정하면
        Then: 방향 기대값이 +0.7% 다
        """
        # Given
        summary = _summary(
            win_rate=0.70,
            loss_rate=0.30,
            win_excess=0.15,
            loss_excess=-0.15,
            mean=0.007,
        )

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) == pytest.approx(0.007, abs=EXACT_TOLERANCE)


class TestDirectionSymmetry:
    """오른 쪽과 내린 쪽을 대칭으로 판정한다 (측정의 원칙 11)."""

    def test_위로_멀어진_칸도_같은_기준으로_후보가_된다(self) -> None:
        """
        목적: 방향을 가리지 않는다. 위로 치우친 칸도 같은 두 조건으로 판정한다.

        Given: 오른 비율이 기준선보다 15%p 높고 평균이 양수인 칸
        When: 판정하면
        Then: 후보이고 방향이 「위」다
        """
        # Given
        summary = _summary(
            win_rate=0.68,
            loss_rate=0.32,
            win_excess=0.15,
            loss_excess=-0.15,
            mean=0.006,
        )

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP

    def test_방향은_기준선에서_멀어진_쪽으로_정해진다(self) -> None:
        """
        목적: **절대 비율로 정하면 안 된다.** 주식은 원래 자주 올라 오른 비율이 절반을 넘는
              칸이 흔하므로, 절대 비율로 정하면 기준선보다 «낮은» 칸까지 「위」가 된다.
              실측: 옵션 만기일 60칸 중 12칸이 두 방식에서 방향이 갈렸다.

        Given: 오른 비율(62.5%)이 내린 비율(37.5%)보다 큰데 기준선 대비로는 내린 쪽이 멀어진 칸
        When: 판정하면
        Then: 방향이 「아래」다
        """
        # Given
        summary = _summary(
            win_rate=0.625,
            loss_rate=0.375,
            win_excess=-0.0383,
            loss_excess=0.0383,
            mean=0.0005,
        )

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN


class TestAxisIndependence:
    """축을 모른다 — 축 이름을 인자로 받아 그대로 쓴다."""

    def test_만기월이_아닌_축에서도_동작한다(self) -> None:
        """
        목적: 이 모듈은 어떤 축이 오는지 몰라야 한다.

        Given: 축 컬럼 이름이 「요일」인 집계표
        When: 그 이름을 인자로 넘겨 판정하면
        Then: 같은 판정이 나오고 축 컬럼이 그대로 실린다
        """
        # Given
        axis = "요일"
        summary = _down_summary().rename(columns={AXIS: axis})

        # When
        result = screen_candidates(summary, axis_column=axis, tradable=True)

        # Then
        assert result[axis].iloc[0] == 9
        assert result[COL_SCREEN].iloc[0] == SCREEN_CANDIDATE

    def test_결과_컬럼이_계약대로다(self) -> None:
        """
        목적: 판정표 스키마를 고정한다. **판정에 쓰이지 않는 컬럼을 두지 않는다.**

        Given: 한 칸짜리 집계표
        When: 판정하면
        Then: 축 컬럼 뒤에 `SCREENING_COLUMNS` 가 그 순서로 붙는다
        """
        # Given
        summary = _down_summary()

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result.columns.tolist() == [AXIS, *SCREENING_COLUMNS]

    def test_축_순서가_유지된다(self) -> None:
        """
        목적: 정렬은 축 오름차순 하나로 고정한다. 무엇을 먼저 보여줄지는 표시 계층의 몫이다.

        Given: 축 값이 9·3·12 순서로 섞인 집계표
        When: 판정하면
        Then: 3·9·12 오름차순이다
        """
        # Given
        blocks = [_down_summary().assign(**{AXIS: value}) for value in (9, 3, 12)]
        summary = pd.concat(blocks, ignore_index=True)

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True)

        # Then
        assert result[AXIS].tolist() == [3, 9, 12]

    def test_필수_컬럼이_없으면_예외다(self) -> None:
        """
        목적: 컬럼이 없는 채로 통과시키면 판정이 조용히 죽는다.

        Given: 축 컬럼이 없는 집계표
        When: 판정하면
        Then: `ValueError` 다
        """
        # Given
        summary = _down_summary().drop(columns=[AXIS])

        # When · Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            screen_candidates(summary, axis_column=AXIS, tradable=True)

    def test_평균이_없으면_예외다(self) -> None:
        """
        목적: **평균 없이 게이트를 통과시키면** 방향은 맞지만 걸면 손실인 칸이 후보로 올라간다.

        Given: 평균 컬럼이 없는 집계표
        When: 판정하면
        Then: `ValueError` 다
        """
        # Given
        summary = _down_summary().drop(columns=[COL_MEAN])

        # When · Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            screen_candidates(summary, axis_column=AXIS, tradable=True)


class TestFormula:
    """적중률·기준선·표본이 방향에 맞게 실리는지 실측값으로 박는다."""

    def test_적중률과_차이가_방향에_맞게_실린다(self) -> None:
        """
        목적: 「아래」 칸은 **내린 비율**과 **내린 비율 초과분**을 읽는다.

        Given: 내린 비율 73% · 내린 비율 초과분 23%p 인 칸
        When: 판정하면
        Then: 적중률 0.73 · 차이 0.23 · 기준선 0.50 이다
        """
        # Given
        summary = _down_summary()

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert float(row[COL_HIT_RATE]) == pytest.approx(0.73, abs=EXACT_TOLERANCE)
        assert float(row[COL_BASELINE_GAP]) == pytest.approx(0.23, abs=EXACT_TOLERANCE)
        assert float(row[COL_BASELINE_HIT_RATE]) == pytest.approx(0.50, abs=EXACT_TOLERANCE)

    def test_위_방향은_오른_비율을_직접_읽는다(self) -> None:
        """
        목적: 「위」 칸은 오른 비율을 그대로 쓴다. **`1 − 내린 비율` 로 만들지 않는다** —
              보합이 어느 쪽에도 들어가지 않아 두 비율은 여집합이 아니다.

        Given: 오른 비율 66% · 내린 비율 24%(보합 10%)인 위 방향 칸
        When: 판정하면
        Then: 적중률이 0.66 이다
        """
        # Given
        summary = _summary(
            win_rate=0.66,
            loss_rate=0.24,
            win_excess=0.12,
            loss_excess=-0.12,
            mean=0.004,
        )

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert row[COL_DIRECTION] == DIRECTION_UP
        assert float(row[COL_HIT_RATE]) == pytest.approx(0.66, abs=EXACT_TOLERANCE)

    def test_표본이_보존된다(self) -> None:
        """
        목적: 표본 수를 절대 생략하지 않는다 (측정의 원칙 3).

        Given: 표본이 23건인 칸
        When: 판정하면
        Then: 표본 수가 그대로 실린다
        """
        # Given
        summary = _down_summary(sample=23)

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert int(row[COL_SAMPLE_COUNT]) == 23


class TestTotalReturn:
    """합산 수익률은 표시용이며 게이트를 바꾸지 않는다 (측정의 원칙 16).

    **회당 기대값만 적으면 크기 감각이 없다** — 신호가 드문 매매법은 회당이 구조적으로 작다.
    판정에 쓰이지 않지만 원칙이 「같은 표에 둔다」를 요구하므로 컬럼으로 남는다.
    """

    def test_합산은_기대값_곱하기_표본_수다(self) -> None:
        """
        목적: 산식을 손계산으로 박는다.

        Given: 기대값 +0.5% · 표본 30건
        When: 판정하면
        Then: 합산이 +15% 다
        """
        # Given
        summary = _down_summary(mean=-0.005, sample=30)

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert float(row[COL_TOTAL_RETURN]) == pytest.approx(0.15, abs=EXACT_TOLERANCE)

    def test_표본이_다르면_회당과_합산의_순서가_갈릴_수_있다(self) -> None:
        """
        목적: **표본 없이 합산만 비교하면 기간이 긴 칸이 자동으로 이긴다** (측정의 원칙 16).
              실물 사례: 회당은 KODEX 200 9월(23건 +1.25%)이 SPY 9월(33건 +0.88%)을 앞서는데
              합산은 +28.8% 대 +29.0% 로 뒤집힌다.

        Given: 회당이 큰 적은 표본 칸과 회당이 작은 많은 표본 칸
        When: 판정하면
        Then: 회당과 합산의 대소가 반대다
        """
        # Given
        blocks = [
            _down_summary(mean=-0.0125, sample=23).assign(**{AXIS: 9}),
            _down_summary(mean=-0.0088, sample=33).assign(**{AXIS: 3}),
        ]
        summary = pd.concat(blocks, ignore_index=True)

        # When
        result = screen_candidates(summary, axis_column=AXIS, tradable=True).set_index(AXIS)

        # Then
        assert float(result.loc[9, COL_EXPECTED_VALUE]) > float(result.loc[3, COL_EXPECTED_VALUE])
        assert float(result.loc[9, COL_TOTAL_RETURN]) < float(result.loc[3, COL_TOTAL_RETURN])

    def test_아래_방향은_합산도_부호가_뒤집힌다(self) -> None:
        """
        목적: 합산은 방향 기대값에서 파생되므로 부호 적용이 한 번만 일어난다.

        Given: 아래 방향 · 평균 +0.4% · 표본 25건
        When: 판정하면
        Then: 합산이 -10% 다
        """
        # Given
        summary = _down_summary(mean=0.004, sample=25)

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert float(row[COL_TOTAL_RETURN]) == pytest.approx(-0.10, abs=EXACT_TOLERANCE)

    def test_합산은_게이트_판정을_바꾸지_않는다(self) -> None:
        """
        목적: 합산이 커도 게이트는 적중률과 회당 기대값만 본다.

        Given: 표본이 많아 합산은 큰데 적중률이 하한에 못 미치는 칸
        When: 판정하면
        Then: 제외다
        """
        # Given
        weak = MIN_HIT_RATE - 0.05
        summary = _down_summary(loss_rate=weak, win_rate=1.0 - weak, sample=200)

        # When
        row = screen_candidates(summary, axis_column=AXIS, tradable=True).iloc[0]

        # Then
        assert float(row[COL_TOTAL_RETURN]) > 0.0
        assert row[COL_SCREEN] == SCREEN_EXCLUDED
