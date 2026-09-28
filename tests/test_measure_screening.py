"""후보 판정 게이트(`screen_verdict`)의 계약을 고정한다.

이 계층이 조용히 틀리면 **없는 우위를 있다고 보고한다.** 판정은 **게이트 하나뿐이고
조건도 하나**다 — 방향 기대값이 하한 이상인가 (2026-09-17 사용자 확정).

- **적중률은 게이트가 아니다** — 성적표의 `승률(%)` 로 그대로 나가고, 그것으로 칸을 거를지는
  사용자가 정한다
- **등급은 없다** (2026-09-12 사용자 결정). 기준선 대비 차이·우연확률·시기 안정성·손익비를
  게이트 위에 얹지 않는다 — 얹으면 같은 질문을 다른 기준으로 또 묻게 된다.
  **판단은 사용자가 한다** — 코드는 볼 목록만 만든다

핵심 계약:
- **기대값 하나«만»** 가른다 — 게이트가 받는 값은 기대값·표본 수·판정 대상 여부 셋뿐이라
  적중률·기준선·합산 수익률은 **들어갈 자리가 없다**
- **방향을 정하지 않는다** — 부르는 쪽이 방향을 적용한 기대값을 넘긴다. 성적표는 행마다 방향이
  확정돼 있고, 방향 부호는 체결 계층이 정한다(`tests/test_execution_trade_fill.py`)
- **표본이 1건이어도 판정하고, 0건이면 판정하지 않는다** — 과대평가 가능성은 표본 수를 보고
  사용자가 판단하지만, 0건은 잴 것이 없다
- **살 수 없는 대상은 판정하지 않는다** (측정의 원칙 9) — 값은 내되 「판정 안 함」으로 남는다

**게이트는 기준선을 받지 않는다** (2026-09-16 개편). 기준선은 「이 신호가 시장 전체와 다른가」를
묻는 축이고 판정이 묻는 것은 「걸 만한가」라 **다른 질문**이다. 기준선이 80%인 칸에서 신호도
80%면 **그 신호에 특별함은 없어도 80%로 이기는 매매인 것은 그대로**이고, 이벤트형은 그 성적을
**연 며칠의 노출로** 얻는다.
"""

import ast
import inspect

import pytest

from verify_lab.measure.screening import (
    MIN_EXPECTED_VALUE,
    SCREEN_CANDIDATE,
    SCREEN_EXCLUDED,
    SCREEN_NOT_JUDGED,
    screen_verdict,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 경계와 무관한 표본 수. 게이트에 표본 하한이 없으므로 0 만 아니면 판정에 영향이 없다
SAMPLE_COUNT = 30


class TestGateBoundary:
    """게이트의 경계 — 하한 «이상»이면 후보, 미만이면 제외"""

    def test_기대값이_하한을_넘으면_후보다(self) -> None:
        """
        목적: 게이트 조건 하나를 넘은 칸은 후보로 올린다.

        Given: 방향 기대값이 하한보다 0.5%p 높은 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(expected_value=MIN_EXPECTED_VALUE + 0.005, sample_count=SAMPLE_COUNT, tradable=True)

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_기대값이_하한과_같으면_후보다(self) -> None:
        """
        목적: 경계가 「이상」임을 고정한다 — 「초과」로 바뀌면 하한과 정확히 같은 칸이 통째로 빠진다.

        **판정에 들어가는 값은 반올림 뒤**라(`execution/periods.py`) 표에 하한이 그대로 찍힌 행이
        곧 경계이고, 경계를 어느 쪽으로 여는지가 산출물을 바꾼다.

        Given: 방향 기대값이 하한과 정확히 같은 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(expected_value=MIN_EXPECTED_VALUE, sample_count=SAMPLE_COUNT, tradable=True)

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_기대값이_하한에_아주_조금_못_미치면_제외다(self) -> None:
        """
        목적: 경계의 «반대쪽»을 고정한다. 「이상」이므로 하한 미만은 제외다.

        Given: 방향 기대값이 하한에 아주 조금 못 미치는 칸
        When: 판정하면
        Then: 제외다
        """
        # Given / When
        verdict = screen_verdict(expected_value=MIN_EXPECTED_VALUE - 1e-9, sample_count=SAMPLE_COUNT, tradable=True)

        # Then
        assert verdict == SCREEN_EXCLUDED

    def test_기대값이_양수여도_하한_미만이면_제외된다(self) -> None:
        """
        목적: **「버는데 모자란」 칸을 고정한다.** 하한이 0 이면 존재할 수 없는 칸이라,
              이 테스트가 없으면 하한을 0 으로 되돌려도 아무것도 실패하지 않는다.

        Given: 방향 기대값이 양수이지만 하한의 절반인 칸
        When: 판정하면
        Then: 제외된다
        """
        # Given
        expected_value = MIN_EXPECTED_VALUE / 2.0
        assert expected_value > 0.0, "양수 칸이어야 검사가 성립합니다"

        # When
        verdict = screen_verdict(expected_value=expected_value, sample_count=SAMPLE_COUNT, tradable=True)

        # Then
        assert verdict == SCREEN_EXCLUDED

    def test_자주_맞아도_걸면_손실인_칸은_제외된다(self) -> None:
        """
        목적: **비율만으로는 못 거르는 칸이 실재한다** — 기대값이 거른다.

              실물 사례: SPY 3월 만기 34회. 내린 비율 64.71% 라 「아래」로 걸면 자주 맞지만,
              맞을 때 +1.272% · 틀릴 때 −3.218% 라 회당 −0.312% 였다. 손익분기 승률이 71.7% 인데
              64.7% 만 맞았다 — 적중률로 거르는 게이트였다면 통과했을 칸이다.

        Given: 방향 기대값이 −0.312% 인 칸
        When: 판정하면
        Then: 제외다
        """
        # Given / When
        verdict = screen_verdict(expected_value=-0.00312, sample_count=34, tradable=True)

        # Then
        assert verdict == SCREEN_EXCLUDED


class TestGateInputs:
    """게이트가 «무엇을 보지 않는지»를 입력으로 고정한다"""

    def test_게이트는_기대값_표본_판정대상_셋만_받는다(self) -> None:
        """
        목적: **적중률·기준선·합산 수익률·방향이 판정에 들어가지 않음**을 고정한다.

        게이트가 그 값을 받을 자리가 없으면 그것으로 칸을 가를 수 없다. 적중률이 낮아도,
        기준선과 똑같아도, 합산이 커도 판정은 기대값 하나로만 갈린다 — **인자가 늘어나는 것은
        판정 기준이 바뀌는 일**이므로 여기서 드러나야 한다.

        **셋 다 키워드 전용이고 기본값이 없다.** `tradable` 에 기본이 있으면 참고용 대상을 받는
        호출처가 인자를 빠뜨렸을 때 틀린 판정이 조용히 나간다
        (`src/verify_lab/CLAUDE.md` 「`tradable` 은 인자이고 기본값이 없다」).

        Given: 게이트 함수
        When: 인자 목록을 봤을 때
        Then: 기대값·표본 수·판정 대상 여부 셋이고, 전부 키워드 전용이며 기본값이 없다
        """
        # Given
        parameters = inspect.signature(screen_verdict).parameters

        # When / Then
        assert list(parameters) == ["expected_value", "sample_count", "tradable"]
        for name, parameter in parameters.items():
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, f"{name} 이 키워드 전용이 아닙니다"
            assert parameter.default is inspect.Parameter.empty, f"{name} 에 기본값이 있습니다"


class TestSampleCount:
    """표본 수 — 1건도 판정하고, 0건은 판정하지 않는다"""

    def test_표본이_1건이어도_판정한다(self) -> None:
        """
        목적: 표본 하한을 걸지 않는다 (2026-09-12 사용자 결정).

        과대평가 가능성은 표본 수를 보고 사용자가 판단한다.

        Given: 표본이 1건뿐이고 게이트를 넘는 칸
        When: 판정하면
        Then: 후보다
        """
        # Given / When
        verdict = screen_verdict(expected_value=0.02, sample_count=1, tradable=True)

        # Then
        assert verdict == SCREEN_CANDIDATE

    def test_표본이_0건이면_판정하지_않는다(self) -> None:
        """
        목적: **「재봤더니 아니었다」와 「재본 적이 없다」를 가른다.**

        하한 아래 값이 함께 와도 「제외」로 찍히지 않아야 한다 — 가드가 없으면 그렇게 찍힌다.

        Given: 표본이 0건이고 기대값이 하한 아래인 칸
        When: 판정하면
        Then: 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(expected_value=0.0, sample_count=0, tradable=True)

        # Then
        assert verdict == SCREEN_NOT_JUDGED

    def test_결측_기대값은_판정하지_않는다(self) -> None:
        """
        목적: 표본이 있어도 지표가 결측인 칸이 「제외」로 찍히지 않게 한다.

        `NaN` 과의 비교는 전부 거짓이라 가드가 없으면 조용히 제외가 된다.

        Given: 표본 수는 있는데 기대값이 결측인 칸
        When: 판정하면
        Then: 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(expected_value=float("nan"), sample_count=5, tradable=True)

        # Then
        assert verdict == SCREEN_NOT_JUDGED


class TestNotJudged:
    """살 수 없는 대상은 값만 내고 판정하지 않는다 (측정의 원칙 9)"""

    def test_살_수_없는_대상은_게이트를_넘어도_판정하지_않는다(self) -> None:
        """
        목적: **지수로 「우위가 있다」를 주장하지 않는다.** 긴 시계열은 참고로 쓰되
              그 결과가 살 수 있는 대상의 판정을 대신하면 안 된다.

        Given: 게이트를 넉넉히 넘는 값인데 판정 대상이 아닌 칸
        When: 판정하면
        Then: 후보가 아니라 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(expected_value=0.02, sample_count=SAMPLE_COUNT, tradable=False)

        # Then
        assert verdict == SCREEN_NOT_JUDGED

    def test_살_수_없는_대상은_게이트를_못_넘어도_판정_안_함이다(self) -> None:
        """
        목적: 「판정 안 함」이 「제외」를 덮는다. 살 수 없는 대상에는 합격도 불합격도 없다.

        Given: 기대값이 하한에 못 미치는데 판정 대상이 아닌 칸
        When: 판정하면
        Then: 제외가 아니라 판정 안 함이다
        """
        # Given / When
        verdict = screen_verdict(expected_value=MIN_EXPECTED_VALUE / 2.0, sample_count=SAMPLE_COUNT, tradable=False)

        # Then
        assert verdict == SCREEN_NOT_JUDGED


class TestSingleOwner:
    """판정식은 한 벌이다 (패키지 절대 원칙 5)"""

    # 게이트를 정의하는 파일(`src` 기준 경로). 아래 네 가지가 **전부** 여기 있어야 한다
    GATE_DEFINER = "verify_lab/measure/screening.py"

    # 게이트의 기준값과 판정 값을 써도 되는 파일. 정의 파일 말고는 그중 일부만 써도 된다.
    # **정당한 새 사용처가 생기면 이유를 주석으로 달아 여기 더한다** — 검사가 막는 것은 테스트 실패뿐이다
    GATE_OWNERS = frozenset({GATE_DEFINER})

    # 게이트만 쓰는 이름. 다른 파일이 이것을 가져다 비교하면 그것이 곧 두 번째 게이트다
    GATE_NAMES = frozenset({"MIN_EXPECTED_VALUE", "SCREEN_CANDIDATE", "SCREEN_EXCLUDED"})

    # 「후보」 판정 값. **손으로 박는다** — 상수를 import 하면 그 값을 고치는 순간 검사가 따라온다.
    # 「제외」는 동음이의어라 보지 않는다 (`test_게이트의_기준값과_판정_값을_소유자_밖에서_쓰지_않는다`)
    CANDIDATE_VALUE = "후보"

    def test_성적_산식_계층이_이_게이트를_쓴다(self) -> None:
        """
        목적: 게이트가 두 벌이 되지 않았음을 **소스로** 고정한다.

        값이 우연히 같아도 구현이 둘이면 언젠가 갈라진다 (절대 원칙 5 — 판정식 단일화).
        성적표에 판정을 붙이는 것은 `execution/periods.py` 이고, 거기서 비교식을 다시 쓰면
        같은 칸이 표마다 다르게 판정된다.

        **`MIN_HIT_RATE` 부재는 회귀 가드다** — 걷어낸 적중률 하한이 옛 이름 그대로 성적 산식에
        되살아나는 것을 막는다(`screening` 쪽은 `test_게이트_조건이_하나다` 가 같은 것을 본다).
        기준값을 따로 쓰지 않는지는 아래 테스트가 `src` 전체에서 본다.

        Given: 구간별 성적 산식 모듈의 소스
        When: 판정을 내는 자리를 봤을 때
        Then: 이 모듈의 게이트를 부르고, 걷어낸 적중률 하한을 들고 있지 않다
        """
        # Given
        from pathlib import Path

        from verify_lab.common_constants import BASE_DIR

        source = Path(BASE_DIR / "src" / "verify_lab" / "execution" / "periods.py").read_text(encoding="utf-8")

        # Then
        assert "screen_verdict(" in source, "성적 산식이 게이트를 부르지 않습니다 — 판정식이 두 벌입니다"
        assert "MIN_HIT_RATE" not in source, "성적 산식이 적중률 하한을 되살렸습니다 — 게이트 조건은 하나입니다"

    def test_게이트의_기준값과_판정_값을_소유자_밖에서_쓰지_않는다(self) -> None:
        """
        목적: 게이트가 두 벌이 되는 가장 흔한 모양 — **기준값을 가져다 직접 비교하는 것** — 을 막는다.

        위 테스트의 `MIN_HIT_RATE` 부재 검사는 걷어낸 이름 하나만 막으므로 그것만으로는 **늘 참**이다 —
        `periods.py` 가 `expected >= MIN_EXPECTED_VALUE` 를 다시 써도 통과한다.

        **소스 문자열이 아니라 AST 의 이름·상수 노드를 본다.** 문서 규칙이 「게이트 값은 적지 않고
        상수 이름을 가리킨다」(`.claude/rules/docs.md`)라 주석이 그 이름을 적는 것은 정당한데,
        주석은 AST 에 없다. **`src` 전체를 본다** — 매매법 `trading.py` 가 직접 비교해도 같은 사고다.

        **값 「제외」는 보지 않는다.** 같은 문자열이 제외 건수 컬럼(`report/constants.py`)과 이상치
        라벨(`studies/usdkrw_equivalence/constants.py`)에 **동음이의어**로 있다
        (`tests/test_layer_contracts.py` 의 `_REPORT_LABEL_COLLISIONS`).

        **정의 파일(`screening.py`)에 네 가지가 실제로 있는지도 본다** — 이름이나 값이 바뀌면 이 검사가
        옛 이름을 찾으며 헛돌아 아무것도 막지 못한 채 통과한다. 허용 경로에 더한 다른 파일에는
        이 요구를 걸지 않는다 — 걸면 정당한 사용처를 더하는 순간 이 테스트가 반드시 실패한다.

        Given: `src/verify_lab` 의 파이썬 파일 전부
        When: 게이트 이름과 값 「후보」를 쓰는 파일을 모은다
        Then: 허용 경로 밖에는 하나도 없고, 정의 파일은 네 가지를 전부 쓴다
        """
        # Given
        from verify_lab.common_constants import BASE_DIR

        source_root = BASE_DIR / "src"
        watched = self.GATE_NAMES | {self.CANDIDATE_VALUE}

        # When
        usage = {
            path.relative_to(source_root).as_posix(): self._gate_usage(path.read_text(encoding="utf-8"))
            for path in sorted((source_root / "verify_lab").rglob("*.py"))
        }
        offenders = {path: sorted(used) for path, used in usage.items() if used and path not in self.GATE_OWNERS}

        # Then
        assert offenders == {}, f"게이트의 기준값·판정 값을 소유자 밖에서 씁니다 — 판정식이 두 벌이 됩니다: {offenders}"
        assert (
            usage.get(self.GATE_DEFINER) == watched
        ), f"{self.GATE_DEFINER} 에 게이트 이름·값이 전부 있지 않습니다 — 이 검사가 헛돕니다: {usage.get(self.GATE_DEFINER)}"

    def _gate_usage(self, source: str) -> set[str]:
        """소스가 쓰는 게이트 이름과 값 「후보」를 모은다.

        **docstring 은 따로 빼지 않는다** — 문장 전체가 한 상수라 값이 통째로 「후보」일 수 없다.

        Args:
            source: 파이썬 소스

        Returns:
            쓰인 게이트 이름과 값의 집합
        """
        found: set[str] = set()

        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Name) and node.id in self.GATE_NAMES:
                found.add(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in self.GATE_NAMES:
                found.add(node.attr)
            elif isinstance(node, ast.alias) and node.name in self.GATE_NAMES:
                found.add(node.name)
            elif isinstance(node, ast.Constant) and node.value == self.CANDIDATE_VALUE:
                found.add(self.CANDIDATE_VALUE)

        return found


class TestGateValues:
    """게이트의 «값»을 손으로 박는다 — 나머지 경계 테스트는 상수에서 파생되기 때문이다

    이 파일의 경계 테스트는 전부 `MIN_EXPECTED_VALUE` 에서 값을 끌어온다.
    의도한 설계지만(하한이 올라가도 「경계」를 계속 재려면 그래야 한다) **그 상태에서는
    상수를 바꿔도 아무것도 실패하지 않는다.** 값을 바꾸는 것은 판정 기준을 바꾸는 일이고
    산출물의 `1차 판정` 이 통째로 달라지므로, **의도한 변경일 때만 이 테스트가 실패해야 한다.**

    **값을 바꿀 때는 이 파일을 함께 고치고, 그 사실을 계획서와 문서에 남긴다.**
    """

    def test_게이트_조건이_하나다(self) -> None:
        """
        목적: **조건이 다시 늘어나는 것을 막는다** (2026-09-17 사용자 확정)

        적중률 하한 상수가 없어야 한다 — 되살리면 여기서 걸린다.

        Given: 판정 모듈
        When: 적중률 하한 상수를 찾는다
        Then: 없다
        """
        from verify_lab.measure import screening

        assert not hasattr(screening, "MIN_HIT_RATE"), "적중률 하한이 되살아났습니다 — 게이트 조건은 하나입니다"

    def test_회당_기대값_하한이_1퍼센트다(self) -> None:
        """
        목적: 회당 기대값 하한을 값으로 고정한다 (2026-09-17 사용자 확정)

        [중요] **거래비용 문턱이 아니다.** 왕복 비용과 숫자를 견주어 정한 값이 아니라
        「이만큼은 벌어야 걸겠다」는 사용자의 최소치이며, 비용을 반영하기로 하면 그것은
        이 값 **위에** 더해진다 (루트 `CLAUDE.md` 「매매 수수료와 슬리피지는 사용자가 별도로
        요청할 때만 넣습니다」).

        Given: 게이트 상수
        When: 값을 본다
        Then: 0.01 이다
        """
        assert MIN_EXPECTED_VALUE == pytest.approx(0.01, abs=EXACT_TOLERANCE)
