"""계층을 가로지르는 상수 계약을 고정한다.

개별 모듈 테스트는 **자기 모듈이 무엇을 내는지**만 본다. 그래서 같은 개념이 검증마다
따로 정의돼도 각자의 테스트는 전부 통과한다 — 실제로 `판정가능` 이 그렇게 갈렸다.
세 계층은 `예`/`아니오` 를 내고 한 계층만 `True`/`False` 를 냈는데, 세 계층의 테스트는
자기 값만 확인하므로 아무도 실패하지 않았다.

**여기서 보는 것은 「어디에 정의돼 있는가」다.** 값이 우연히 같아도 정의가 흩어져 있으면
한쪽이 바뀌는 날 조용히 갈라진다.

| 개념 | 소유자 | 왜 하나여야 하나 |
| --- | --- | --- |
| `판정가능` 과 그 값 | `measure/constants.py` | 측정의 원칙 17이 모든 검증에 요구한다 |
| 칸당 표본 하한 | `measure/constants.py` | 원칙 12가 「10건」을 명시하고 원칙 17이 「원칙 12의 10건」이라며 같은 값임을 선언한다 |
| 체결 판정식 | `strategy/trade_fill.py` | 시가·장중 순서가 뒤바뀌면 손실이 실제보다 작게 나오고, 두 곳에 두면 그 함정을 두 번 관리한다 |
| 구간별 성적 산식 | `strategy/periods.py` | 구간 5행은 세 매매법에 공통이다 (측정의 원칙 17) |

**매매 계층은 「매매법끼리 서로를 모른다」도 함께 본다.** 예전에는 월말이 옵션 만기일을 거쳐
역방향을 부르는 사슬이었고, 그래서 사슬의 끝인 월말에는 자기 체결 로직이 하나도 없었다.
공유 로직을 매매법-중립 모듈로 뺀 뒤에도 **다음 매매법이 남의 runner 에서 가져다 쓰면 사슬이
다시 생긴다** — 그때 그 함수는 두 매매법의 것이 되고, 한쪽 사정으로 고치면 다른 쪽이 조용히 바뀐다.
"""

import ast
import re
from pathlib import Path

from verify_lab.measure import constants as measure_constants

# 검사 대상 소스 트리. 테스트와 스크립트는 정의처가 아니라 사용처다
_SOURCE_ROOT = Path(measure_constants.__file__).resolve().parents[1]

# 이 개념을 소유한 파일. 나머지는 전부 여기서 가져와야 한다
_OWNER = Path(measure_constants.__file__).resolve()

# 수집 계층의 공유 상수를 소유한 파일. `_files_defining` 은 소유자를 빼지 않으므로
# 이 이름이 결과에 그대로 남는 것이 정상이다
_DATA_CONSTANTS = "verify_lab/data/constants.py"

# 매매 계층의 공유 로직을 소유한 모듈. 매매법 모듈은 여기서만 가져온다
_STRATEGY_SHARED = ("trade_fill", "periods", "constants")


def _strategy_runner_modules() -> list[Path]:
    """매매법 하나씩에 대응하는 실행 모듈을 찾는다.

    Returns:
        `strategy/*_runner.py` 목록 (정렬됨)
    """
    return sorted((_SOURCE_ROOT / "strategy").glob("*_runner.py"))


def _imported_strategy_modules(path: Path) -> set[str]:
    """그 파일이 `strategy` 안에서 가져오는 모듈 이름을 모은다.

    **네 가지 import 형태를 모두 본다.** 한 형태만 보면 다른 형태로 쓴 코드가 검사를 통과하며,
    그때 계약은 초록인데 사슬은 되살아난다.

    | 형태 | 예 |
    | --- | --- |
    | 절대 `from ... import` | `from verify_lab.strategy.periods import period_rows` |
    | 패키지에서 모듈을 | `from verify_lab.strategy import periods` |
    | 모듈 `import` | `import verify_lab.strategy.periods` |
    | 상대 `from` | `from .periods import period_rows` |

    Args:
        path: 검사할 소스 파일

    Returns:
        모듈 이름 집합 (`verify_lab.strategy.` 접두어를 뗀 것)
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = "verify_lab.strategy"
    prefix = f"{package}."
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                # 상대 import — `from .periods import x` 는 같은 패키지의 모듈을 가리킨다.
                # 모듈명이 비면(`from . import x`) 가져온 이름 자체가 모듈이다
                found.update({alias.name for alias in node.names} if not module else {module.split(".")[0]})
            elif module == package:
                found.update(alias.name for alias in node.names)
            elif module.startswith(prefix):
                found.add(module[len(prefix) :].split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(
                alias.name[len(prefix) :].split(".")[0] for alias in node.names if alias.name.startswith(prefix)
            )

    return found


def _functions_importing_pykrx(path: Path) -> list[ast.FunctionDef]:
    """파일 안에서 **본문에 pykrx import 를 가진** 함수를 찾는다.

    Args:
        path: 검사할 소스 파일

    Returns:
        해당 함수 노드 목록
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(inner, ast.ImportFrom) and (inner.module or "").startswith("pykrx") for inner in ast.walk(node)
        )
    ]


def _files_defining(pattern: str) -> list[str]:
    """`src` 안에서 그 패턴으로 **값을 직접 정의하는** 파일을 찾는다.

    `from ... import NAME` 형태의 재노출은 정의가 아니므로 걸리지 않는다.
    소유자 파일 자신은 결과에서 뺀다.

    Args:
        pattern: 정의 한 줄을 통째로 매칭하는 정규식

    Returns:
        소유자 밖에서 정의한 파일의 저장소 상대 경로 목록 (정렬됨)
    """
    expression = re.compile(pattern, re.MULTILINE)
    found: list[str] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        if path.resolve() == _OWNER:
            continue
        if expression.search(path.read_text(encoding="utf-8")):
            found.append(str(path.relative_to(_SOURCE_ROOT.parent)))

    return found


class TestJudgeableOwnership:
    """`판정가능` 컬럼과 그 값은 공통 계층 하나가 소유한다"""

    def test_컬럼_이름을_다른_곳에서_정의하지_않는다(self) -> None:
        """
        목적: `COL_JUDGEABLE` 의 정의처가 하나임을 고정한다.

        Given: `src/verify_lab` 전체
        When: `= "Judgeable"` 로 값을 직접 정의하는 파일을 찾는다
        Then: `measure/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r'^\s*COL_JUDGEABLE(?:\s*:\s*\w+)?\s*=\s*["\']')

        # Then
        assert offenders == [], f"판정가능 컬럼을 자체 정의한 파일이 있습니다: {offenders}"

    def test_값을_다른_곳에서_정의하지_않는다(self) -> None:
        """
        목적: `예`/`아니오` 문자열의 정의처가 하나임을 고정한다.

        Given: `src/verify_lab` 전체
        When: `JUDGEABLE_YES`·`JUDGEABLE_NO` 를 직접 정의하는 파일을 찾는다
        Then: `measure/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r'^\s*JUDGEABLE_(?:YES|NO)(?:\s*:\s*\w+)?\s*=\s*["\']')

        # Then
        assert offenders == [], f"판정가능 값을 자체 정의한 파일이 있습니다: {offenders}"


class TestSampleThresholdOwnership:
    """칸당 표본 하한은 공통 계층 하나가 소유한다"""

    def test_하한을_다른_곳에서_정의하지_않는다(self) -> None:
        """
        목적: 같은 값 10이 네 곳에 흩어져 있던 상태로 되돌아가지 않게 한다.

        검정 하한·축 분해 하한·구간 하한은 **이름만 다를 뿐 같은 것을 잰다** — 전부
        (기준 × 구간) 칸의 유효 표본이다. 계층마다 다른 이름으로 두면 값이 갈라져도
        예외가 나지 않고, 두 산출물의 `판정가능` 이 다른 기준으로 찍힌다.

        Given: `src/verify_lab` 전체
        When: `MIN_...SAMPLE...` 이름으로 숫자를 직접 정의하는 파일을 찾는다
        Then: `measure/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r"^\s*MIN_\w*SAMPLE\w*(?:\s*:\s*\w+)?\s*=\s*\d")

        # Then
        assert offenders == [], f"표본 하한을 자체 정의한 파일이 있습니다: {offenders}"

    def test_공통_계층이_하한을_노출한다(self) -> None:
        """
        목적: 소유자가 실제로 그 상수를 갖고 있음을 고정한다.

        위 테스트만으로는 "아무 데도 정의가 없다"도 통과하므로 짝으로 둔다.

        Given: 공통 계층 상수 모듈
        When: 칸당 표본 하한을 읽는다
        Then: 1 이상의 정수다
        """
        # When
        threshold = measure_constants.MIN_SAMPLE_PER_CELL

        # Then
        assert isinstance(threshold, int)
        assert threshold >= 1


class TestDataConstantsOwnership:
    """수집 계층이 공유하는 값은 `data/constants.py` 가 소유한다"""

    def test_국내_제외_일수를_수집기가_정의하지_않는다(self) -> None:
        """
        목적: 세 국내 수집기가 같은 값을 각자 두던 상태로 되돌아가지 않게 한다.

        셋 다 「장중에도 당일 행이 반환되므로 당일은 뺀다」는 같은 이유로 같은 값을 썼고,
        주석이 서로를 "같은 기준"이라 가리키고 있었다. 값이 갈라져도 예외는 나지 않는다.

        **미국 제외 일수는 검사 대상이 아니다** — 쓰는 곳이 `yfinance_collector` 하나뿐이라
        「1개 파일에서만 사용 → 해당 파일 상단」 규칙에 따라 제자리에 있는 것이 맞다.

        Given: `src/verify_lab` 전체
        When: 국내 제외 일수를 직접 정의하는 파일을 찾는다
        Then: `data/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r"^\s*DOMESTIC_RECENT_EXCLUSION_DAYS(?:\s*:\s*\w+)?\s*=\s*\d")

        # Then
        assert offenders == [_DATA_CONSTANTS], f"국내 제외 일수를 자체 정의한 파일이 있습니다: {offenders}"

    def test_KRX_날짜_포맷을_수집기가_정의하지_않는다(self) -> None:
        """
        목적: KRX 요청·응답 날짜 규격의 정의처를 하나로 유지한다.

        Given: `src/verify_lab` 전체
        When: KRX 날짜 포맷을 직접 정의하는 파일을 찾는다
        Then: `data/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r'^\s*KRX_(?:REQUEST|RESPONSE)_DATE_FORMAT(?:\s*:\s*\w+)?\s*=\s*["\']')

        # Then
        assert offenders == [_DATA_CONSTANTS], f"KRX 날짜 포맷을 자체 정의한 파일이 있습니다: {offenders}"


class TestStrategyLayerComposition:
    """매매 계층은 공유 로직을 중립 모듈에 두고 매매법끼리 서로를 모른다"""

    def test_매매법_모듈이_서로를_가져오지_않는다(self) -> None:
        """
        목적: 월말 → 옵션 만기일 → 역방향 사슬로 되돌아가지 않게 한다.

        사슬이 생기면 **공유 함수가 특정 매매법 파일의 소유가 되고**, 그 매매법 사정으로
        고칠 때 빌려 쓰는 쪽이 조용히 함께 바뀐다. 실제로 그 상태에서 월말은 자기 체결
        로직이 하나도 없었고, 초안 계획서는 그것을 「체결 모듈이 없다」고 잘못 읽었다.

        Given: `strategy/*_runner.py` 전부
        When: 각 파일이 `strategy` 안에서 가져오는 모듈을 본다
        Then: 공유 모듈만 가져오고 다른 매매법의 모듈은 가져오지 않는다
        """
        # Given
        runners = _strategy_runner_modules()
        assert runners, "매매 실행 모듈을 하나도 찾지 못했습니다"

        # When / Then
        for path in runners:
            borrowed = _imported_strategy_modules(path) - set(_STRATEGY_SHARED)
            assert borrowed == set(), f"{path.name} 가 다른 매매법의 모듈을 가져옵니다: {sorted(borrowed)}"

    def test_매매법마다_실행_모듈이_하나다(self) -> None:
        """
        목적: 매매법 이름을 알면 파일 이름을 알 수 있게 고정한다 (목표 1·2).

        **이름에 slug 가 없던 `runner.py` 가 문제의 출발점이었다.** 폴더 목록만 봐서는
        어느 매매법의 것인지 알 수 없었다.

        Given: `strategy/` 폴더
        When: 실행 모듈 이름을 본다
        Then: 확정 이름표의 세 매매법이 각각 하나씩 있다
        """
        # When
        names = {path.name for path in _strategy_runner_modules()}

        # Then
        assert names == {"reverse_runner.py", "option_expiry_runner.py", "month_end_runner.py"}

    def test_체결_판정식을_공유_모듈_밖에서_정의하지_않는다(self) -> None:
        """
        목적: 판정식 단일화(절대 원칙 5)를 기계로 건다.

        월말에 체결 파일을 만들려면 계산을 복사해야 했고, 그러면 **같은 매매법의 손익비가
        산출물마다 달라지는데 어느 쪽이 맞는지 판별할 방법이 없다.**

        Given: `src/verify_lab` 전체
        When: 체결 결과 타입을 직접 정의하는 파일을 찾는다
        Then: `strategy/trade_fill.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r"^\s*class\s+TradeResult\b")

        # Then
        assert offenders == ["verify_lab/strategy/trade_fill.py"], f"체결 결과 타입을 자체 정의한 파일이 있습니다: {offenders}"


class TestCredentialsBeforeImport:
    """pykrx 를 가져오기 전에 자격증명을 올린다"""

    def test_지연_import_헬퍼가_자격증명을_먼저_부른다(self) -> None:
        """
        목적: 새 KRX 수집기가 순서를 빠뜨리는 것을 막는다.

        **`import pykrx` 자체가 로그인을 시도한다.** 자격증명이 환경 변수에 올라가기 전에
        import 하면 실패하므로, 세 수집기가 전부 `load_krx_credentials()` 를 먼저 부르고
        그 다음에 pykrx 를 가져온다. **지금은 각 docstring 이 설명할 뿐 아무도 검사하지 않는다** —
        네 번째 수집기가 생길 때 순서를 빠뜨려도 테스트가 통과한다.

        Given: pykrx 를 함수 안에서 가져오는 `data/` 모듈
        When: 각 함수 본문에서 두 호출의 순서를 본다
        Then: 자격증명 호출이 pykrx import 보다 앞에 있다
        """
        # Given
        modules = sorted((_SOURCE_ROOT / "data").glob("*.py"))

        # When · Then
        checked = 0
        for path in modules:
            for function in _functions_importing_pykrx(path):
                body = ast.unparse(function)
                credential_at = body.find("load_krx_credentials()")
                import_at = body.find("from pykrx")
                assert credential_at >= 0, f"{path.name}:{function.name} 가 자격증명을 부르지 않습니다"
                assert credential_at < import_at, f"{path.name}:{function.name} 가 자격증명보다 먼저 import 합니다"
                checked += 1

        # 검사할 함수가 하나도 없으면 위 루프가 통째로 비어 통과한다 — 그것을 막는다
        assert checked >= 1, "pykrx 를 함수 안에서 가져오는 곳을 하나도 찾지 못했습니다"
