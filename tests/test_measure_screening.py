"""후보 판정의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 판정은 **게이트 하나뿐**이다.

- **게이트** (적중률 · 방향 기대값) — 볼 목록에 올릴지를 가른다. 이것 말고는 아무것도 떨어뜨리지 않는다

**등급은 없다** (2026-09-12 개편). 전에는 기준선 대비 차이·우연확률·시기 안정성·손익비 넷을
「충족/물음」으로 셌는데, 같은 것을 구간 게이트가 다른 기준(55% 대 60%)으로 또 묻고 있었다.
**판단은 사용자가 한다** — 코드는 볼 목록만 만든다.

핵심 계약은 다섯이다.
- 게이트 두 축**만** 가른다 — 우연확률이 1 이어도, 기준선과 같아도 후보로 남는다
- 방향 기대값은 **방향 부호를 적용한 평균**이다 — 「아래」 칸은 평균이 양수면 기대값이 음수다
- 방향은 **두 방향 비율 중 큰 쪽**이다. 기준선은 방향에도 게이트에도 쓰지 않는다
  (2026-09-15 개편 — 기준선 방식은 156칸에서 **더해 주는 칸 0개**에 5칸을 빼기만 했다)
- **표본이 1건이어도 판정한다** — 과대평가 가능성은 표본 수를 보고 사용자가 판단한다
- **참고용 대상은 판정하지 않는다** — 지수(살 수 없다)와 인버스 실물(1배 롱이 같은 질문에
  이미 답한다). 값은 내되 「판정 안 함」으로 남는다

**판정표에 기준선 컬럼을 두지 않는다** (2026-09-16 개편). 기준선은 「이 신호가 시장 전체와
다른가」를 묻는 축이고 판정이 묻는 것은 「걸 만한가」라 **다른 질문**이다. 판정에 쓰지 않는 축을
판정표에 두면 읽는 사람이 그걸로 거른다 — 실제로 「기준선과 같으니 그냥 들고 있는 것과 다를 바
없다」는 잘못된 탈락 근거로 읽혔다. 기준선이 80%인 칸에서 신호도 80%면 **그 신호에 특별함은
없어도 80%로 이기는 매매인 것은 그대로**이고, 이벤트형은 그 성적을 **연 며칠의 노출로** 얻는다.
값은 `통계.csv` 계열이 그대로 담는다.
"""

import pandas as pd
import pytest

from verify_lab.measure.screening import (
    COL_DIRECTION,
    COL_EXPECTED_VALUE,
    COL_HIT_RATE,
    COL_SCREEN,
    COL_TOTAL_RETURN,
    DIRECTION_COLUMNS,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MIN_EXPECTED_VALUE,
    MIN_HIT_RATE,
    SCREEN_CANDIDATE,
    SCREEN_EXCLUDED,
    SCREEN_NOT_JUDGED,
    direction_profile,
    screen_verdict,
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

    **평균을 기대값 하한에서 파생시킨다.** 손으로 박으면 하한이 올라갈 때 기본 픽스처가
    조용히 경계에 걸터앉고, 「게이트를 넘는 칸」을 전제한 테스트들이 무더기로 의미를 잃는다
    (tests/CLAUDE.md 「픽스처가 코드와 같은 가정을 하면 그 버그는 영원히 안 잡힌다」).
    """
    values: dict[str, float] = {
        "win_rate": 0.27,
        "loss_rate": 0.73,
        "win_excess": -0.23,
        "loss_excess": 0.23,
        "mean": -(MIN_EXPECTED_VALUE + 0.005),
    }
    values.update(overrides)

    return _summary(**values)  # type: ignore[arg-type]


def _verdict(profile: pd.DataFrame, *, tradable: bool = True, index: int = 0) -> str:
    """방향 표 한 행에 게이트를 걸어 판정을 낸다.

    **방향 표는 판정을 담지 않는다** — 1차 판정이 나가는 자리는 `성적표.csv` 뿐이므로
    (`src/verify_lab/CLAUDE.md` 「매매 산출물 계약」), 이 헬퍼가 `execution/periods.py` 가
    프로덕션에서 하는 조립을 테스트에서 그대로 재현한다.
    """
    row = profile.iloc[index]

    return screen_verdict(
        hit_rate=float(row[COL_HIT_RATE]),
        expected_value=float(row[COL_EXPECTED_VALUE]),
        sample_count=int(row[COL_SAMPLE_COUNT]),
        tradable=tradable,
    )


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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE
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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_EXCLUDED

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_EXCLUDED
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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE

    def test_기대값이_하한과_같으면_후보다(self) -> None:
        """
        목적: 기대값 경계가 **이상**임을 고정한다. 적중률 경계와 같은 방향이다 —
              두 게이트의 경계가 서로 다르면 표를 읽을 때마다 어느 쪽인지 되짚어야 한다.

              **판정에 들어가는 값은 반올림 뒤**라(`execution/periods.py`) 표에 `0.50` 이
              찍힌 행이 곧 경계다. 실측으로 옵션 만기일 13행 · 월말 2행이 여기 걸리므로
              경계를 어느 쪽으로 여는지가 산출물을 바꾼다.

              **부호를 뒤집어 넘긴다.** 「아래」 칸의 기대값은 평균의 부호를 뒤집은 값이므로,
              평균에 하한을 그대로 넣으면 기대값이 **음수**가 되어 경계가 아니라 한참 아래를
              재게 된다 — 테스트는 통과하면서 고정하려던 계약만 사라진다.

        Given: 아래로 걸었을 때의 기대값이 하한과 정확히 같은 칸
        When: 판정하면
        Then: 후보다
        """
        # Given
        summary = _down_summary(mean=-MIN_EXPECTED_VALUE)

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) == pytest.approx(MIN_EXPECTED_VALUE, abs=EXACT_TOLERANCE)
        assert _verdict(result) == SCREEN_CANDIDATE

    def test_기대값이_양수여도_하한_미만이면_제외된다(self) -> None:
        """
        목적: **하한이 0 보다 커진 뒤 생긴 칸을 고정한다** — 「버는데 모자란」 칸이다.
              하한이 0 이던 시절에는 존재할 수 없었고, 이 테스트가 없으면 하한을 되돌려도
              아무것도 실패하지 않는다.

        Given: 아래로 걸었을 때의 기대값이 양수이지만 하한에 못 미치는 칸
        When: 판정하면
        Then: 제외된다
        """
        # Given
        summary = _down_summary(mean=-(MIN_EXPECTED_VALUE / 2.0))

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert float(result[COL_EXPECTED_VALUE].iloc[0]) > 0.0
        assert _verdict(result) == SCREEN_EXCLUDED

    def test_기준선과_똑같아도_게이트를_넘으면_후보다(self) -> None:
        """
        목적: **이 개편의 핵심 계약이다.** 게이트는 두 축뿐이므로 기준선과 성적이 같아도
              후보로 남는다. 실물 사례가 SPY 11월 — 적중률 66.7% 인데 기준선도 66.7% 다.

              **「기준선과 같다」는 「걸 가치가 없다」가 아니다.** 그 신호에 특별함이 없을 뿐
              66.7% 로 이기는 매매인 것은 그대로이고, 이벤트형은 그 성적을 **연 며칠의 노출로**
              얻는다 — 365일 묶여서 같은 성적을 내는 것과 자본 효율이 다르다.

        Given: SPY 11월 그대로 — 오른 비율 66.7% 인데 기준선도 66.7% 라 차이가 0 인 칸
        When: 판정하면
        Then: 후보다
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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE
        assert int(result[COL_SAMPLE_COUNT].iloc[0]) == 1

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_NOT_JUDGED

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert sorted(result[AXIS].tolist()) == [3, 9]
        verdicts = [_verdict(result, index=order) for order in range(len(result))]
        assert sorted(verdicts) == sorted([SCREEN_CANDIDATE, SCREEN_EXCLUDED])


class TestBaselineIsNotInTheVerdict:
    """판정표는 **판정에 쓰는 축만** 담는다 (2026-09-16 개편).

    기준선은 「이 신호가 시장 전체와 다른가」를 묻고, 판정은 「걸 만한가」를 묻는다.
    **다른 질문이라 같은 표에 두면 읽는 사람이 판정에 안 쓰는 축으로 거른다** —
    실제로 「기준선과 같으니 그냥 들고 있는 것과 다를 바 없다」는 잘못된 탈락 근거로 읽혔다.

    **값이 사라지는 것이 아니다** — 같은 폴더의 `통계.csv` 계열이 기준선 14컬럼과
    차이 4컬럼을 그대로 담는다.
    """

    def test_판정표에_기준선_컬럼이_없다(self) -> None:
        """
        목적: 스키마에서 두 축을 빼는 것을 고정한다.

        Given: 한 칸짜리 집계표
        When: 판정하면
        Then: 결과 컬럼 어디에도 「기준선」이 들어간 이름이 없다
        """
        # Given
        summary = _down_summary()

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        leftover = [column for column in result.columns if "기준선" in column or "Baseline" in column]
        assert leftover == [], f"판정표에 기준선 컬럼이 남아 있습니다: {leftover}"

    def test_기준선_초과분_없이도_판정된다(self) -> None:
        """
        목적: **입력 계약에서도 뺀다.** 쓰지 않는 값을 계속 요구하면 호출하는 쪽이
              그것을 계산해 넘겨야 하고, 그러면 「빼지 않은 것」과 같아진다.

        Given: 기준선 초과분 두 컬럼이 없는 집계표
        When: 판정하면
        Then: 예외 없이 후보로 판정된다
        """
        # Given
        summary = _down_summary().drop(columns=[COL_WIN_RATE_EXCESS, COL_LOSS_RATE_EXCESS])

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE

    def test_기준선을_빼도_판정_값이_그대로다(self) -> None:
        """
        목적: **표시를 바꾸는 것이지 판정을 바꾸는 것이 아니다.**

              기준선이 유리한 칸과 불리한 칸이 «같은 판정»을 받아야 그 축이 게이트에
              관여하지 않는다는 것이 증명된다.

        Given: 다른 값은 같고 기준선 초과분 부호만 반대인 두 칸
        When: 각각 판정하면
        Then: 판정·방향·적중률·기대값이 전부 같다
        """
        # Given
        favourable = _down_summary(win_excess=-0.23, loss_excess=0.23)
        unfavourable = _down_summary(win_excess=0.23, loss_excess=-0.23)

        # When
        first = direction_profile(favourable, axis_column=AXIS)
        second = direction_profile(unfavourable, axis_column=AXIS)

        # Then
        pd.testing.assert_frame_equal(first, second)


class TestNotJudged:
    """살 수 없는 대상은 값만 내고 판정하지 않는다 (측정의 원칙 9).

    **방향 표는 `tradable` 을 받지 않는다** — 방향과 크기는 살 수 있든 없든 사실이고,
    「이 대상으로 판정하는가」는 게이트의 질문이다. 그래서 이 클래스는 게이트를 직접 본다.
    """

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result, tradable=False) == SCREEN_NOT_JUDGED

    def test_판정_안_해도_값은_그대로_실린다(self) -> None:
        """
        목적: 판정을 막는 것이지 **값을 지우는 것이 아니다.** 참고하려면 숫자가 있어야 한다.

        **방향 표 자체가 판정을 모른다** — 같은 표에 게이트만 다르게 걸리므로
        「살 수 있는가」가 값을 바꿀 길이 구조적으로 없다.

        Given: 같은 칸
        When: 방향 표를 내고 두 대상으로 게이트를 각각 걸면
        Then: 값은 한 벌이고 판정만 갈린다
        """
        # Given
        summary = _down_summary()

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result, tradable=True) == SCREEN_CANDIDATE
        assert _verdict(result, tradable=False) == SCREEN_NOT_JUDGED
        assert COL_SCREEN not in result.columns, "방향 표에 판정이 실렸습니다 — 판정의 자리는 성적표입니다"

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result, tradable=False) == SCREEN_NOT_JUDGED


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
        result = direction_profile(summary, axis_column=AXIS)

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
        result = direction_profile(summary, axis_column=AXIS)

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP

    def test_방향은_두_비율_중_큰_쪽이다(self) -> None:
        """
        목적: **기준선이 방향을 정하지 않는다** (2026-09-15 개편).

              기준선 대비 초과분으로 정하면 **칸마다 다른 허들**이 서고(월말 기준선
              24.9~73.2%), 기준선이 높은 칸에서 멀쩡한 우위가 뒤집힌다. 실측으로 두 검증
              156칸에서 기준선 방식이 **더해 주는 칸은 0개**이고 5칸을 빼기만 했다.

              **회당 기대값을 하한 위에 둔다.** 하한 미만이면 방향이 「위」든 「아래」든
              어차피 제외라 **판정 단언이 공허해지고**, 「기준선보다 낮아도 후보로 남는다」는
              회귀 가드가 함께 사라진다 — 방향이 뒤집혔을 때 실패해야 이 테스트가 일을 한다.

        Given: 오른 비율(62.5%)이 내린 비율(37.5%)보다 크지만 기준선(66.3%)보다는 «낮은» 칸
               — 옵션 만기일 KODEX 200 12월의 실물 모양에 기대값만 하한 위로 올린 것이다
        When: 판정하면
        Then: 방향이 「위」이고 후보다. **기준선 방식으로 뒤집혀 「아래」가 되면 기대값이
              음수가 되어 제외로 떨어지므로, 이 단언이 방향 회귀를 잡는다**
        """
        # Given
        summary = _summary(
            win_rate=0.625,
            loss_rate=0.375,
            win_excess=-0.0383,
            loss_excess=0.0383,
            mean=MIN_EXPECTED_VALUE + 0.001,
        )

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP
        assert _verdict(result) == SCREEN_CANDIDATE

    def test_기준선보다_낮아도_적중률이_높으면_후보다(self) -> None:
        """
        목적: **「그냥 들고 있는 것보다 못하다」가 탈락 사유가 아니다.**

              이벤트형 매매는 자본이 99% 이상 놀고 있어 비교 대상이 상시 보유가 아니라
              현금이다. 기준선을 넘는지는 **다른 질문**이고 판정은 그것을 묻지 않는다.

        Given: 월말 KODEX 코스닥150 8월의 실물 모양 — 오른 63.6% · 기준선 66.2% · 회당 +2.11%
        When: 판정하면
        Then: 후보이고 방향이 「위」다
        """
        # Given
        summary = _summary(
            win_rate=0.636,
            loss_rate=0.364,
            win_excess=-0.026,
            loss_excess=0.026,
            mean=0.0211,
            sample=11,
        )

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert _verdict(result) == SCREEN_CANDIDATE
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_UP

    def test_보합이_커도_여집합으로_방향을_정하지_않는다(self) -> None:
        """
        목적: 두 방향 비율은 여집합이 아니다 — 보합이 어느 쪽에도 들어가지 않는다.
              실측으로 월말에 두 비율의 합이 90.0% 인 칸이 있다(보합 10.00%p).
              「오른 비율 40% 아래면 아래」로 쓰면 그 칸에서 답이 갈린다.

        Given: 오른 40% · 내린 50% · 보합 10% 인 칸
        When: 판정하면
        Then: 방향은 큰 쪽인 「아래」이고, 적중률이 «내린 비율 그대로»(50%)라
              60% 게이트를 못 넘어 제외된다
        """
        # Given
        summary = _summary(
            win_rate=0.40,
            loss_rate=0.50,
            win_excess=-0.05,
            loss_excess=0.05,
            mean=-0.004,
        )

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN
        assert result[COL_HIT_RATE].iloc[0] == pytest.approx(0.50, abs=EXACT_TOLERANCE)
        assert _verdict(result) == SCREEN_EXCLUDED

    def test_자주_맞아도_걸면_손실인_칸은_기대값이_거른다(self) -> None:
        """
        목적: **비율만으로는 못 거르는 칸이 실재한다.** 적중률 게이트만 두면 통과한다.

              실물: SPY 3월 만기 34회 — 내린 비율 64.71% 라 「아래」로 걸면 자주 맞지만,
              맞을 때 +1.27% · 틀릴 때 −3.22% 라 합계가 −10.70%(회당 −0.315%)다.
              손익분기 승률이 71.7% 인데 64.7% 만 맞는다.

        Given: 내린 비율 64.71% 인데 평균이 «양수»인 칸
        When: 판정하면
        Then: 방향은 「아래」이고 적중률은 게이트를 넘지만, 기대값이 음수라 제외된다
        """
        # Given
        summary = _summary(
            win_rate=0.3529,
            loss_rate=0.6471,
            win_excess=-0.10,
            loss_excess=0.10,
            mean=0.00315,
            sample=34,
        )

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert result[COL_DIRECTION].iloc[0] == DIRECTION_DOWN
        assert result[COL_HIT_RATE].iloc[0] >= MIN_HIT_RATE
        assert result[COL_EXPECTED_VALUE].iloc[0] == pytest.approx(-0.00315, abs=EXACT_TOLERANCE)
        assert _verdict(result) == SCREEN_EXCLUDED


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
        result = direction_profile(summary, axis_column=axis)

        # Then
        assert result[axis].iloc[0] == 9
        assert _verdict(result) == SCREEN_CANDIDATE

    def test_결과_컬럼이_계약대로다(self) -> None:
        """
        목적: 판정표 스키마를 고정한다. **판정에 쓰이지 않는 컬럼을 두지 않는다.**

        Given: 한 칸짜리 집계표
        When: 판정하면
        Then: 축 컬럼 뒤에 `DIRECTION_COLUMNS` 가 그 순서로 붙는다
        """
        # Given
        summary = _down_summary()

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert result.columns.tolist() == [AXIS, *DIRECTION_COLUMNS]

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
        result = direction_profile(summary, axis_column=AXIS)

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
            direction_profile(summary, axis_column=AXIS)

    def test_같은_축_값이_두_행이면_예외다(self) -> None:
        """
        목적: **축 값당 첫 행만 쓰고 나머지를 조용히 버리던 것**을 막는다.

        판정은 축으로 묶어 칸마다 한 행을 낸다. 한 축 값에 행이 둘 이상이면 두 번째부터
        **사라지는데 예외도 경고도 없다** — 로그마저 「1칸 중 후보 1」로 정상처럼 찍힌다.
        축을 하나 더 붙이거나 기준을 둘로 늘리는 날 없는 우위를 보고하게 된다.

        같은 저장소의 `report/tables.py` 는 같은 종류의 사고에 이미 `ValueError` 를 던진다.

        Given: 축 값이 9 로 같은 행 둘
        When: 판정하면
        Then: `ValueError` 이고 메시지에 축 이름·축 값·행 수가 담긴다
        """
        # Given
        blocks = [_down_summary(), _down_summary(mean=-0.009)]
        summary = pd.concat(blocks, ignore_index=True)

        # When · Then
        with pytest.raises(ValueError, match="축 값") as caught:
            direction_profile(summary, axis_column=AXIS)

        message = str(caught.value)
        assert f"{AXIS}=9" in message
        assert "(2행)" in message

    def test_축_값이_비어_있으면_예외다(self) -> None:
        """
        목적: **「축당 한 행」 검사가 못 잡는 다른 구멍**을 막는다.

        `groupby` 는 기본이 `dropna=True` 라 축이 비어 있는 행을 **그룹째 버린다.**
        남은 그룹만 보는 검사로는 그 행이 사라진 것을 알 수 없고, 로그는 그대로
        정상처럼 찍힌다 — 이 모듈이 막으려던 것과 같은 형태의 사고다.

        Given: 축 값이 결측인 행이 섞인 집계표
        When: 판정하면
        Then: `ValueError` 다
        """
        # Given
        blocks = [_down_summary().assign(**{AXIS: 9}), _down_summary().assign(**{AXIS: None})]
        summary = pd.concat(blocks, ignore_index=True)

        # When · Then
        with pytest.raises(ValueError, match="축 값이 비어"):
            direction_profile(summary, axis_column=AXIS)

    def test_축_값이_서로_다르면_통과한다(self) -> None:
        """
        목적: 중복 거부가 **정상 입력을 막지 않는지** 고정한다 (엣지 케이스).

        현재 호출처 넷은 전부 축당 1행이다 — 이 가드는 값을 바꾸지 않아야 한다.

        Given: 축 값이 9·3 으로 다른 행 둘
        When: 판정하면
        Then: 두 행이 모두 나온다
        """
        # Given
        blocks = [_down_summary().assign(**{AXIS: 9}), _down_summary().assign(**{AXIS: 3})]
        summary = pd.concat(blocks, ignore_index=True)

        # When
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert result[AXIS].tolist() == [3, 9]

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
            direction_profile(summary, axis_column=AXIS)


class TestFormula:
    """적중률·기준선·표본이 방향에 맞게 실리는지 실측값으로 박는다."""

    def test_적중률이_방향에_맞게_실린다(self) -> None:
        """
        목적: 「아래」 칸은 **내린 비율**을 적중률로 읽는다.

        Given: 내린 비율 73% 인 아래 방향 칸
        When: 판정하면
        Then: 적중률이 0.73 이다
        """
        # Given
        summary = _down_summary()

        # When
        row = direction_profile(summary, axis_column=AXIS).iloc[0]

        # Then
        assert float(row[COL_HIT_RATE]) == pytest.approx(0.73, abs=EXACT_TOLERANCE)

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
        row = direction_profile(summary, axis_column=AXIS).iloc[0]

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
        row = direction_profile(summary, axis_column=AXIS).iloc[0]

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
        row = direction_profile(summary, axis_column=AXIS).iloc[0]

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
        result = direction_profile(summary, axis_column=AXIS).set_index(AXIS)

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
        row = direction_profile(summary, axis_column=AXIS).iloc[0]

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
        result = direction_profile(summary, axis_column=AXIS)

        # Then
        assert float(result[COL_TOTAL_RETURN].iloc[0]) > 0.0
        assert _verdict(result) == SCREEN_EXCLUDED


class TestScalarVerdict:
    """스칼라 진입점 — 성적표가 쓰는 자리

    **판정식은 한 벌이어야 한다** (패키지 절대 원칙 5). 성적표는 방향이 이미 확정돼 있고
    승률·평균을 자기가 들고 있어 집계표를 만들 수 없으므로, 같은 게이트를 **값으로** 묻는
    진입점이 따로 필요하다. 손익비가 `payoff_profile`(스칼라)·`payoff_from_returns`(목록)
    두 진입점으로 같은 계산을 쓰는 것과 같은 구조다.

    **이 진입점은 방향을 정하지 않는다.** 부르는 쪽이 이미 방향을 알고 있고, 그 방향으로
    적중률과 기대값을 계산해 넘긴다.
    """

    def test_방향_표의_값으로_게이트가_걸린다(self) -> None:
        """
        목적: **방향 표와 게이트가 맞물리는 것**을 고정한다.

        방향 표는 거는 방향과 크기만 내고 판정하지 않는다 — 그 값을 그대로 게이트에 넣으면
        판정이 나오며, 이것이 `execution/periods.py` 가 성적표 행마다 하는 일이다.

        Given: 게이트를 넘는 「아래」 칸 하나
        When: 방향 표를 내고 그 행의 값으로 게이트를 걸었을 때
        Then: 후보이고, 방향 표 자체에는 판정 컬럼이 없다
        """
        # Given
        summary = _down_summary()

        # When
        result = direction_profile(summary, axis_column=AXIS)
        row = result.iloc[0]
        scalar = screen_verdict(
            hit_rate=float(row[COL_HIT_RATE]),
            expected_value=float(row[COL_EXPECTED_VALUE]),
            sample_count=int(row[COL_SAMPLE_COUNT]),
            tradable=True,
        )

        # Then
        assert scalar == SCREEN_CANDIDATE
        assert COL_SCREEN not in result.columns

    def test_적중률이_하한과_같으면_후보다_스칼라(self) -> None:
        """
        목적: 경계가 「이상」임을 고정한다 — 「초과」로 바뀌면 60.0% 칸이 통째로 빠진다.

        Given: 적중률이 정확히 하한이고 기대값이 하한을 넘는 칸
               — 기대값은 **상수에서 파생**시킨다. 손으로 박으면 하한이 올라갈 때 조용히
               「적중률 경계」가 아니라 「기대값 경계」를 재게 된다
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(
            hit_rate=MIN_HIT_RATE,
            expected_value=MIN_EXPECTED_VALUE + 0.001,
            sample_count=30,
            tradable=True,
        )

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_기대값이_하한과_같으면_후보다_스칼라(self) -> None:
        """
        목적: 기대값 경계가 「이상」임을 고정한다 — 적중률 경계와 같은 방향이다.

        Given: 적중률은 넘고 기대값이 하한과 정확히 같은 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(
            hit_rate=MIN_HIT_RATE + 0.1,
            expected_value=MIN_EXPECTED_VALUE,
            sample_count=30,
            tradable=True,
        )

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_기대값이_하한에_한_칸_못_미치면_제외다_스칼라(self) -> None:
        """
        목적: 경계의 «반대쪽»을 고정한다. 「이상」이므로 하한 미만은 제외다.

        Given: 적중률은 넘는데 기대값이 하한에 아주 조금 못 미치는 칸
        When: 판정하면
        Then: 제외다
        """
        # Given / When
        verdict = screen_verdict(
            hit_rate=MIN_HIT_RATE + 0.1,
            expected_value=MIN_EXPECTED_VALUE - 1e-9,
            sample_count=30,
            tradable=True,
        )

        # Then
        assert verdict == SCREEN_EXCLUDED

    def test_표본이_1건이어도_판정한다(self) -> None:
        """
        목적: 표본 하한을 걸지 않는다 (2026-09-12 사용자 결정).

        과대평가 가능성은 표본 수를 보고 사용자가 판단한다.

        Given: 표본이 1건뿐이고 게이트를 넘는 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(hit_rate=1.0, expected_value=0.02, sample_count=1, tradable=True)

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_표본이_0건이면_판정하지_않는다(self) -> None:
        """
        목적: 「재봤더니 아니었다」와 「재본 적이 없다」를 가른다.

        0건 칸의 적중률·기대값은 결측이라 비교가 전부 거짓이 되고, 가만히 두면 「제외」로 찍힌다.

        Given: 표본이 0건인 칸
        When: 판정하면
        Then: 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(hit_rate=0.0, expected_value=0.0, sample_count=0, tradable=True)

        # Then
        assert verdict == SCREEN_NOT_JUDGED

    def test_살_수_없는_대상은_판정하지_않는다(self) -> None:
        """
        목적: 게이트를 넘어도 「판정 안 함」이 그 결과를 덮는다 (측정의 원칙 9).

        Given: 게이트를 넘는 값인데 판정 대상이 아닌 칸
        When: 판정하면
        Then: 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(hit_rate=0.9, expected_value=0.02, sample_count=30, tradable=False)

        # Then
        assert verdict == SCREEN_NOT_JUDGED

    def test_결측_적중률은_판정하지_않는다(self) -> None:
        """
        목적: 표본이 있어도 지표가 결측인 칸이 「제외」로 찍히지 않게 한다.

        `NaN` 과의 비교는 전부 거짓이라 가드가 없으면 조용히 제외가 된다.

        Given: 표본 수는 있는데 적중률이 결측인 칸
        When: 판정하면
        Then: 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(hit_rate=float("nan"), expected_value=0.02, sample_count=5, tradable=True)

        # Then
        assert verdict == SCREEN_NOT_JUDGED

    def test_성적_산식_계층이_이_게이트를_쓴다(self) -> None:
        """
        목적: 게이트가 두 벌이 되지 않았음을 **소스로** 고정한다.

        값이 우연히 같아도 구현이 둘이면 언젠가 갈라진다 (절대 원칙 5 — 판정식 단일화).
        성적표에 판정을 붙이는 것은 `execution/periods.py` 이고, 거기서 비교식을 다시 쓰면
        같은 칸이 표마다 다르게 판정된다.

        Given: 구간별 성적 산식 모듈의 소스
        When: 판정을 내는 자리를 봤을 때
        Then: 이 모듈의 게이트를 부르고, 기준값을 직접 적지 않는다
        """
        # Given
        from pathlib import Path

        from verify_lab.common_constants import BASE_DIR

        source = Path(BASE_DIR / "src" / "verify_lab" / "execution" / "periods.py").read_text(encoding="utf-8")

        # Then
        assert "screen_verdict(" in source, "성적 산식이 게이트를 부르지 않습니다 — 판정식이 두 벌입니다"
        assert "MIN_HIT_RATE" not in source, "성적 산식이 게이트 기준값을 따로 들고 있습니다"
