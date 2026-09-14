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
| 평균-비율 어긋남 판정과 그 임계값 | `measure/statistics.py` · `measure/constants.py` | 원칙 13이 모든 검증에 요구한다. **실제로 두 검증에 docstring까지 같은 함수가 두 벌 있었다** |
| 판정가능 «식» | `measure/statistics.py` | 값(하한)만 공통이고 식은 다섯 곳에 있었다 — 하한을 바꿔도 한 곳이 안 따라오면 드러나지 않는다 |

**「무엇이 여기 들어오는가」의 판단 기준은 하나다** — 루트 `CLAUDE.md` 의 「이것이 「측정의
원칙」에 적혀 있는가」. 적혀 있으면 공통 계층이 소유해야 하고, 적혀 있지 않은 조립 유틸
(`_identify`·`_concat`)은 검증마다 두는 것이 맞다. 공통 계층에 올리면 `report` 가
「검증이 쓰는 조립 순서」를 알게 된다.

**매매 계층은 「매매법끼리 서로를 모른다」도 함께 본다.** 예전에는 월말이 옵션 만기일을 거쳐
역방향을 부르는 사슬이었고, 그래서 사슬의 끝인 월말에는 자기 체결 로직이 하나도 없었다.
공유 로직을 매매법-중립 모듈로 뺀 뒤에도 **다음 매매법이 남의 runner 에서 가져다 쓰면 사슬이
다시 생긴다** — 그때 그 함수는 두 매매법의 것이 되고, 한쪽 사정으로 고치면 다른 쪽이 조용히 바뀐다.
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from verify_lab.common_constants import BASE_DIR
from verify_lab.measure import constants as measure_constants

# 검사 대상 소스 트리. 테스트와 스크립트는 정의처가 아니라 사용처다
_SOURCE_ROOT = Path(measure_constants.__file__).resolve().parents[1]

# 이 개념을 소유한 파일. 나머지는 전부 여기서 가져와야 한다
_OWNER = Path(measure_constants.__file__).resolve()

# 수집 계층의 공유 상수를 소유한 파일. `_files_defining` 은 소유자를 빼지 않으므로
# 이 이름이 결과에 그대로 남는 것이 정상이다
_DATA_CONSTANTS = "verify_lab/data/constants.py"

# 매매 계층의 공유 로직을 소유한 모듈. 매매법 모듈은 여기서만 가져온다
_STRATEGY_SHARED = ("trade_fill", "periods", "constants", "run_summary")

# 평균-비율 어긋남 판정과 판정가능 식을 소유한 파일. `_files_defining` 은 `_OWNER` 하나만
# 빼므로 이 이름이 결과에 그대로 남는 것이 정상이다
_MEASURE_STATISTICS = "verify_lab/measure/statistics.py"

# `summary.json` 의 `datasets` 한 줄을 만드는 자리. 검증은 셋이 각자 만들고 매매 셋은
# `strategy/run_summary.dataset_record` 하나를 공유한다 — **검증이 그것을 쓸 수 없다.**
# `studies → strategy` 의존이 생겨 계층 방향이 뒤집히기 때문이다. 소유자를 중립 자리로
# 옮기는 것은 별도 작업이고, 그때까지는 **키 「집합」만** 같은지 본다
_DATASET_RECORD_SITES = (
    ("studies/reverse/runner.py", "_dataset_record"),
    ("studies/option_expiry/runner.py", "_run_dataset"),
    ("studies/month_end/runner.py", "_run_dataset"),
)

# 매매 계층이 이미 내고 있는 다섯 키. **손으로 박는다** — `run_summary` 의 상수를 가져다
# 비교하면 그 상수를 고치는 순간 테스트가 함께 따라와 아무것도 고정하지 못한다
# (`tests/CLAUDE.md`). 매매 쪽의 「정확히 이 다섯」은 `test_strategy_output_contract.py` 가
# 런타임으로 보고, 여기서는 **검증 셋이 그 다섯을 빠짐없이 갖는지**를 본다 —
# 검증은 `expiry_count` 처럼 자기 축을 더 갖는 것이 정상이라 부분집합으로 검사한다
_DATASET_MINIMUM_KEYS = frozenset({"ticker", "label", "file", "period", "rows"})


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


def _string_constants(tree: ast.Module) -> dict[str, str]:
    """모듈 최상단의 문자열 상수를 이름 → 값으로 모은다.

    `KEY_TICKER = "ticker"` 와 `KEY_TICKER: Final = "ticker"` 를 모두 본다 —
    한 형태만 보면 다른 형태로 쓴 모듈의 키가 통째로 안 잡힌다.

    Args:
        tree: 파싱된 모듈

    Returns:
        상수 이름 → 문자열 값
    """
    found: dict[str, str] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue

        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue

        found.update({target.id: value.value for target in targets if isinstance(target, ast.Name)})

    return found


def _own_nodes(function: ast.FunctionDef) -> Iterator[ast.AST]:
    """중첩 함수·람다 본문을 빼고 그 함수 «자신»의 노드만 낸다.

    `ast.walk` 는 중첩 함수 안까지 내려간다. 거기서 나온 반환문은 이 함수의 산출물이 아니므로
    섞이면 검사가 엉뚱한 사전을 보게 된다.

    Args:
        function: 검사할 함수 노드

    Yields:
        그 함수 본문의 노드
    """
    stack: list[ast.AST] = list(function.body)

    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _returned_records(relative: str, function: str) -> list[dict[str, str]]:
    """그 함수가 돌려주는 사전 리터럴을 **반환문마다 하나씩** 낸다.

    키가 `KEY_TICKER` 같은 이름이라 최상단 상수를 먼저 읽어 값으로 바꾼다. **값으로 봐야 한다** —
    상수 이름이 모듈마다 달라도(`KEY_ROWS` 대 `KEY_ROW_COUNT`) 실제 `summary.json` 에 나가는 것은
    값이고, 이름만 맞춰 보면 산출물이 갈린 것을 못 잡는다. 각 키가 **어디서 온 값인지**도
    함께 담는다 — 키 이름만 보면 `ticker` 에 표시 이름을 넣던 원래 버그가 그대로 통과한다.

    **반환문끼리 합치지 않는다.** 합치면 「어느 경로로 나가도 다섯 키가 다 있다」가 아니라
    「어딘가에는 있다」를 검사하게 되어, 두 키만 내는 이른 반환이 끼어도 통과한다.
    **중첩 함수의 반환도 보지 않는다** — 그것은 이 함수의 산출물이 아니다.

    `**base_record` 처럼 펼친 것은 키가 없어 건너뛴다. 최소 집합 검사는 「적어도 이만큼은 있다」
    이므로 펼친 쪽에 더 있는 것은 문제가 아니다.

    Args:
        relative: `src/verify_lab` 기준 상대 경로
        function: 검사할 함수 이름

    Returns:
        반환문마다 `{키 값: 값 표현식의 소스}` 사전
    """
    tree = ast.parse((_SOURCE_ROOT / relative).read_text(encoding="utf-8"))
    constants = _string_constants(tree)

    definitions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function]
    assert len(definitions) == 1, f"{relative} 에서 {function} 을 하나로 특정하지 못했습니다 ({len(definitions)}개)"

    records: list[dict[str, str]] = []
    for node in _own_nodes(definitions[0]):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        record: dict[str, str] = {}
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                record[key.value] = ast.unparse(value)
            elif isinstance(key, ast.Name) and key.id in constants:
                record[constants[key.id]] = ast.unparse(value)
        records.append(record)

    assert records, f"{relative} 의 {function} 에서 사전 리터럴을 찾지 못했습니다"

    return records


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


class TestPrincipleThirteenOwnership:
    """평균-비율 어긋남 판정(원칙 13)과 그 임계값은 공통 계층 하나가 소유한다"""

    def test_어긋남_판정을_검증마다_두지_않는다(self) -> None:
        """
        목적: **docstring 까지 바이트 단위로 같은 함수가 두 벌** 있던 상태로 되돌아가지 않게 한다.

        `studies/month_end/runner.py` 와 `studies/option_expiry/runner.py` 가 둘 다
        `_mean_rate_conflict` 를 갖고 있었고 **자기 docstring 에 「측정의 원칙 13」이라고
        적어 두었다.** 원칙이 모든 검증에 요구하는 것을 검증마다 구현하면 같은 원칙이 다른 답을 낸다.

        Given: `src/verify_lab` 전체
        When: 어긋남 판정 함수를 정의하는 파일을 찾는다
        Then: `measure/statistics.py` 하나뿐이다
        """
        # When
        offenders = _files_defining(r"^\s*def\s+_?mean_rate_conflict\b")

        # Then
        assert offenders == [_MEASURE_STATISTICS], f"어긋남 판정을 자체 정의한 파일이 있습니다: {offenders}"

    def test_절반_임계값을_검증마다_두지_않는다(self) -> None:
        """
        목적: 위 판정의 임계값이 두 `studies/*/constants.py` 에 흩어져 있던 것을 닫는다.

        Given: `src/verify_lab` 전체
        When: `HALF_RATE` 를 직접 정의하는 파일을 찾는다
        Then: `measure/constants.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r"^\s*HALF_RATE(?:\s*:\s*\w+)?\s*=")

        # Then
        assert offenders == [], f"절반 임계값을 자체 정의한 파일이 있습니다: {offenders}"

    def test_판정가능_식을_손으로_쓰지_않는다(self) -> None:
        """
        목적: 하한(값)만 공통이고 **식**은 다섯 곳에 있던 것을 닫는다.

        `JUDGEABLE_YES if count >= MIN_SAMPLE_PER_CELL else JUDGEABLE_NO` 가
        `month_end`·`option_expiry`·`leverage_tracking`·`futures_leverage`·`strategy/periods`
        다섯 곳에 있었다. 하한을 바꿔도 한 곳이 안 따라오면 **예외 없이** 두 산출물의
        `판정가능` 이 다른 기준으로 찍힌다.

        Given: `src/verify_lab` 전체
        When: 판정가능 값을 삼항식으로 만드는 파일을 찾는다
        Then: `measure/statistics.py` 하나뿐이다
        """
        # When
        offenders = _files_defining(r"JUDGEABLE_YES\s+if\b")

        # Then
        assert offenders == [_MEASURE_STATISTICS], f"판정가능 식을 손으로 쓴 파일이 있습니다: {offenders}"


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


class TestDatasetRecordKeys:
    """`summary.json` 의 `datasets` 한 줄은 계층을 가리지 않고 같은 키를 쓴다"""

    def test_세_검증이_매매와_같은_최소_키를_낸다(self) -> None:
        """
        목적: 「범위의 SoT 는 `summary.json` 의 `datasets`」를 여섯 산출 지점이 같은 말로 이행한다.

        **월말만 이 형태였다.** 역방향은 `ticker` 에 «표시 이름»을 담고 `label` 이 아예 없었으며
        기간을 `start_date`+`end_date`, 행 수를 `row_count` 로 불렀다. 옵션 만기일도 `ticker` 에
        표시 이름이 들어 있었다.

        Given: 검증 셋의 데이터셋 한 줄을 만드는 함수
        When: 그 함수가 돌려주는 사전의 키를 값으로 읽었을 때
        Then: 반환문마다 매매가 내는 다섯 키를 빠짐없이 갖는다
        """
        # Given / When / Then
        for relative, function in _DATASET_RECORD_SITES:
            for record in _returned_records(relative, function):
                missing = _DATASET_MINIMUM_KEYS - set(record)

                assert missing == set(), f"{relative} 의 datasets 한 줄에 키가 없습니다: {sorted(missing)}"

    def test_코드와_이름과_파일이_제_출처에서_온다(self) -> None:
        """
        목적: 키 이름만 맞고 **값이 엉뚱한 데서 오는** 상태를 막는다.

        [중요] **키 집합 검사만으로는 이 계약의 원래 버그를 못 잡는다.** `ticker` 의 값을
        `dataset.label` 로 되돌려도 키 이름 `ticker` 는 그대로라 위 테스트가 통과한다.
        **미국 ETF 는 코드와 이름이 같아(`QQQ`) 산출물을 눈으로 봐도 드러나지 않고**,
        둘 다 `str` 이라 타입 검사도 못 잡는다 — 그래서 출처를 직접 본다.

        Given: 검증 셋의 데이터셋 한 줄을 만드는 함수
        When: 세 키의 값 표현식을 봤을 때
        Then: 코드는 `.ticker`, 이름은 `.label`, 파일은 파일 이름에서 온다
        """
        # Given
        expected_suffixes = {
            "ticker": (".ticker",),
            "label": (".label",),
            # 경로를 통째로 넣지 못하게 한다 — `path.name` 이거나 애초에 이름인 필드여야 한다
            "file": (".name", ".file_name"),
        }

        # When / Then
        for relative, function in _DATASET_RECORD_SITES:
            for record in _returned_records(relative, function):
                for key, suffixes in expected_suffixes.items():
                    source = record[key]
                    assert source.endswith(suffixes), f"{relative} 의 {key} 가 {source!r} 에서 옵니다"


class TestRunSummaryOwnership:
    """실행 요약을 만드는 것은 runner 이고 CLI 는 그대로 넘기기만 한다

    **여기는 `datasets` 키가 아니라 「누가 요약을 조립하는가」를 본다.** 규칙을 다른
    스크립트로 넓힐 때 이 클래스가 그 자리다.
    """

    def test_옵션_만기일_검증_CLI_가_요약에_값을_끼워_넣지_않는다(self) -> None:
        """
        목적: 요약의 소유자를 runner 하나로 되돌린다 (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」).

        CLI 가 `{**outputs.summary, "output_dir": str(directory)}` 로 한 칸을 얹고 있었고,
        그 값이 **이 PC 의 절대경로**였다. `output_dir` 은 그 파일이 놓인 폴더 자신이라
        값 자체가 잉여이기도 하다 — `meta.json` 쪽은 「최근 실행이 어디 있나」를 찾는 용도라 남긴다.

        **두 줄로 검사하는 것은 매매 쪽 쌍둥이 테스트와 같은 관용이다**
        (`tests/test_strategy_output_contract.py`) — 넘기는 줄이 맞는지와, 사전 리터럴을
        조립한 흔적이 없는지를 함께 본다.

        Given: 옵션 만기일 검증 실행 스크립트
        When: 요약을 저장하는 줄을 봤을 때
        Then: runner 가 낸 요약을 그대로 넘기고 조립부가 없다
        """
        # Given
        script = BASE_DIR / "scripts" / "studies" / "run_option_expiry_study.py"

        # When
        source = script.read_text(encoding="utf-8")

        # Then
        assert "save_run_summary(directory, outputs.summary)" in source, "CLI 가 요약을 runner 에서 받지 않습니다"
        assert "save_run_summary(\n" not in source, "CLI 가 요약을 조립합니다"


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
