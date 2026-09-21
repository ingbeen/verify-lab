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
| 칸당 표본 하한 | `measure/constants.py` | 원칙 12·17이 같은 하한을 쓰므로 소유자가 하나다. 값은 `MIN_SAMPLE_PER_CELL` 이 갖는다 |
| 체결 판정식 | `execution/trade_fill.py` | 시가·장중 순서가 뒤바뀌면 손실이 실제보다 작게 나오고, 두 곳에 두면 그 함정을 두 번 관리한다 |
| 구간별 성적 산식 | `execution/periods.py` | 구간 5행은 세 매매법에 공통이다 (측정의 원칙 17) |
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
import contextlib
import importlib.util
import io
import re
import sys
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

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
_EXECUTION_SHARED = ("trade_fill", "periods", "constants", "run_summary")

# 측정과 체결의 요약을 합치는 공유 함수. **이 함수에서 온 이름만 허용한다** —
# 「`summary` 라는 이름이면 통과」로 두면 사전 리터럴을 그 이름에 담는 우회가 열린다
_MERGE_FUNCTION = "merge_run_summary"

# 평균-비율 어긋남 판정과 판정가능 식을 소유한 파일. `_files_defining` 은 `_OWNER` 하나만
# 빼므로 이 이름이 결과에 그대로 남는 것이 정상이다
_MEASURE_STATISTICS = "verify_lab/measure/statistics.py"

# 값의 소유자를 이름으로 지목할 때 쓴다. `_files_with_literal`·`_files_defining_value` 는
# 아무 파일도 빼지 않으므로 소유자 자신이 결과에 들어 있어야 정상이다
_MEASURE_CONSTANTS = "verify_lab/measure/constants.py"
_MEASURE_SCREENING = "verify_lab/measure/screening.py"
_REPORT_CONSTANTS = "verify_lab/report/constants.py"

# `report/constants.py` 의 표시 문자열인데 **다른 파일도 같은 문자열을 정의하는** 것들.
# 값 → 정의해도 되는 파일 집합이며, 검사는 **부분집합**이다 — 목록에 없는 «새» 충돌만 실패시키고,
# 나중에 통합해서 사라지는 것은 막지 않는다.
#
# **이 목록이 비어 있지 않은 것이 정상이다.** 같은 한글 단어가 계층마다 다른 것을 가리키는 자리가
# 실재하고, 그 사실은 `src/verify_lab/CLAUDE.md` 「매매 산출물 계약」이 이미 명시했다
_REPORT_LABEL_COLLISIONS = {
    # `pykrx` 가 돌려주는 인덱스 이름이라 표시 레이블이 아니라 **데이터 소스의 사실**이다
    "날짜": frozenset({"verify_lab/data/pykrx_collector.py", "verify_lab/studies/usdkrw_equivalence/constants.py"}),
    # **표마다 지시 대상이 다르다** — 역방향 성적표는 신호군 종류, 거래내역은 신호 방향,
    # 배수 검증은 기초지수가 오른 날인지다. 계약 표가 이 갈림을 의도로 적어 두었다
    "방향": frozenset(
        {
            "verify_lab/execution/constants.py",
            "verify_lab/studies/leverage_tracking/constants.py",
            "verify_lab/studies/reverse/constants.py",
        }
    ),
    "신호": frozenset({"verify_lab/studies/reverse/constants.py"}),
    # 뜻이 다르다 — `screening` 은 1차 판정의 «값», `usdkrw` 는 이상치 라벨,
    # `report` 는 제외 «건수» 컬럼의 머리다
    "제외": frozenset({"verify_lab/measure/screening.py", "verify_lab/studies/usdkrw_equivalence/constants.py"}),
    "표본": frozenset({"verify_lab/studies/usdkrw_equivalence/constants.py"}),
}

# 매매 계층이 이미 내고 있는 다섯 키. **손으로 박는다** — `run_summary` 의 상수를 가져다
# 비교하면 그 상수를 고치는 순간 테스트가 함께 따라와 아무것도 고정하지 못한다
# (`tests/CLAUDE.md`). 매매 쪽의 「정확히 이 다섯」은 `test_strategy_output_contract.py` 가
# 런타임으로 보고, 여기서는 **검증 셋이 그 다섯을 빠짐없이 갖는지**를 본다 —
# 검증은 `expiry_count` 처럼 자기 축을 더 갖는 것이 정상이라 부분집합으로 검사한다
_DATASET_MINIMUM_KEYS = frozenset({"ticker", "label", "file", "period", "rows"})

# 데이터셋 한 줄의 소유자. 검증도 매매도 여기서 가져온다 — `report` 는 두 계층이 이미
# 의존하는 아래쪽이라 방향이 뒤집히지 않는다
_REPORT_RUN_SUMMARY = "verify_lab/report/run_summary.py"

# 산출물 파일 목록을 소유하는 사전. **검증마다 하나씩 있어야 한다** — 전에는 CLI 가
# 파일 이름을 들고 요약의 별칭 키와 손으로 짝지었다
# (`run_usdkrw_equivalence_study.py` 가 `counts['equivalence']` 로 되짚었다)
_OUTPUT_FILES = "OUTPUT_FILES"

# 기간 표기의 구분자. **손으로 박는다** — 소유자의 상수를 가져다 비교하면 그 상수를 고치는
# 순간 테스트가 함께 따라와 아무것도 고정하지 못한다 (`tests/CLAUDE.md`)
_PERIOD_SEPARATOR = " ~ "

# 「파일 이름 하나로만 이루어진 문자열」. 짝마다 이름이 갈리는 틀(`windows_{pair}.csv`)과
# **한글 이름**(`성적표.csv`)도 포함한다 — 매매 산출물이 한글이라 라틴 문자만 보면 통째로 샌다.
# **산문은 공백이 있어 걸리지 않는다** — 도움말이 산출물을 언급하는 것은 정의가 아니다
_FILENAME_SHAPE = re.compile(r"[^\s/\\]+\.csv")


def _study_packages() -> list[Path]:
    """검증 패키지 폴더를 모은다.

    Returns:
        `studies/<slug>/` 목록 (정렬됨)
    """
    return sorted(path for path in (_SOURCE_ROOT / "studies").iterdir() if (path / "constants.py").is_file())


def _runner_scripts() -> list[Path]:
    """매매법·조사의 실행 스크립트를 모은다.

    **매매법당 하나다.** 등급(검증·매매)은 분류일 뿐이라 실행을 가르지 않으므로, 한 스크립트가
    측정 표와 체결 산출물을 함께 낸다 — 둘로 나누면 같은 시세를 두 번 읽고 **나중에 돈 쪽이
    앞의 산출물을 지운다**(산출물 폴더가 매매법당 하나다).

    Returns:
        `scripts/run_*.py` 목록 (정렬됨)
    """
    return sorted((BASE_DIR / "scripts").glob("run_*.py"))


def _load_script(script: Path) -> ModuleType:
    """실행 스크립트를 모듈로 읽어 온다.

    [주의] **모듈 본문이 실제로 실행된다.** 지금 여섯 스크립트는 최상단이 import 와 상수뿐이라
    안전하지만, 거기에 시세 로딩이나 외부 호출을 넣으면 **이 테스트가 실 storage 를 읽거나
    네트워크를 탄다**(`tests/CLAUDE.md` 5·6절). 실행 스크립트의 최상단은 부작용이 없어야 한다.

    Args:
        script: `scripts/run_*.py` 경로

    Returns:
        읽어 온 모듈
    """
    spec = importlib.util.spec_from_file_location(script.stem, script)
    assert spec is not None and spec.loader is not None, f"{script.name} 을 읽을 수 없습니다"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _merged_summary_names(path: Path) -> set[str]:
    """그 스크립트에서 **합치기 함수의 반환값을 받은** 지역변수 이름을 모은다.

    **이름만 보고 허용하면 우회가 열린다** — `summary = {...}` 로 사전을 조립해 같은 이름에
    담으면 「CLI 가 요약을 조립하지 않는다」는 계약이 이름 하나로 뚫린다. 그래서 그 이름이
    실제로 `merge_run_summary(...)` 에서 왔는지를 AST 로 본다.

    Args:
        path: 검사할 실행 스크립트

    Returns:
        허용되는 지역변수 이름 집합
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        called = node.value.func
        label = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", "")
        if label != _MERGE_FUNCTION:
            continue
        names.update(target.id for target in node.targets if isinstance(target, ast.Name))

    return names


def _trading_modules() -> list[Path]:
    """매매법 하나씩에 대응하는 실행 모듈을 찾는다.

    **매매법 코드는 그 매매법의 검증 패키지 안에 있다.** 등급(검증·매매)은 분류일 뿐이라
    코드를 가르지 않으므로, 승격해도 파일이 움직이지 않는다.

    Returns:
        `studies/<slug>/trading.py` 목록 (정렬됨)
    """
    return sorted((_SOURCE_ROOT / "studies").glob("*/trading.py"))


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


def _files_with_literal(value: str) -> list[str]:
    """`src` 안에서 그 문자열을 **소스 어디에든 적은** 파일을 찾는다 (docstring 제외).

    `_files_defining` 이 「이 이름으로 정의하는가」를 보는 것과 달리 여기서는 **값**을 본다.
    **이름은 계층마다 다르고 산출물에 나가는 것은 값이다.** 이름으로 찾으면 세 벌이 있어도
    한 건도 안 걸린다.

    **상수 대입만 보지 않는다.** 원칙이 요구하는 값이 되살아나는 가장 흔한 모양은 상수를 새로
    만드는 것이 아니라 **호출부에 리터럴을 바로 적는 것**이다 — 실제로 두 runner 가
    `masks = [(라벨, ...), (라벨, ...)]` 꼴로 쓰고 있어 그 자리에 문자열을 직접 적으면 그대로 산다.
    주석은 AST 에 없으므로 애초에 안 걸린다.

    **아무 파일도 빼지 않는다.** 소유자가 결과 목록에 이름으로 드러나야 그 자리가 어디인지
    테스트만 읽고 알 수 있다.

    Args:
        value: 찾을 문자열 값

    Returns:
        그 값을 적은 파일의 저장소 상대 경로 목록 (정렬됨, 중복 없음)
    """
    return sorted(
        {str(path.relative_to(_SOURCE_ROOT.parent)) for path in _SOURCE_ROOT.rglob("*.py") if value in _literals(path)}
    )


def _files_defining_value(value: str) -> list[str]:
    """`src` 안에서 그 문자열을 **모듈 최상단 상수 값으로** 정의하는 파일을 찾는다.

    위 `_files_with_literal` 보다 좁게 본다. **표시 레이블에는 좁은 쪽이 맞다** — 같은 한글
    단어가 예외 메시지 조각으로도 쓰이기 때문이다(`measure/statistics.py` 가 「신호 집계에
    필수 컬럼이 누락되었습니다」를 만들며 `"신호"`·`"베이스라인"` 을 f-string 재료로 쓴다).
    그것은 레이블의 두 번째 정의가 아니라 문장의 일부다.

    Args:
        value: 찾을 문자열 값

    Returns:
        그 값을 상수로 정의한 파일의 저장소 상대 경로 목록 (정렬됨)
    """
    return sorted(
        str(path.relative_to(_SOURCE_ROOT.parent))
        for path in _SOURCE_ROOT.rglob("*.py")
        if value in _module_constants(path).values()
    )


@cache
def _literals(path: Path) -> frozenset[str]:
    """그 파일에 적힌 문자열을 **docstring 만 빼고** 모은다.

    Args:
        path: 검사할 소스 파일

    Returns:
        문자열 값의 집합
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    documented = _docstring_ids(tree)

    return frozenset(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in documented
    )


def _docstring_ids(tree: ast.Module) -> set[int]:
    """docstring 노드의 `id` 를 모은다.

    설명하는 문장은 정의가 아니다 — 값 검사가 docstring 을 세면 **그 값을 설명한 파일이
    전부 「정의처」로 잡힌다.**

    Args:
        tree: 검사할 모듈의 AST

    Returns:
        docstring 노드의 `id` 집합
    """
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }


@cache
def _module_constants(path: Path) -> dict[str, str]:
    """그 파일의 모듈 최상단 문자열 상수를 이름 → 값으로 모은다.

    **결과를 캐시한다.** 레이블 소유자 검사가 `report` 의 레이블마다 소스 트리를 통째로 훑어
    같은 파일을 수십 번 파싱한다.

    Args:
        path: 검사할 소스 파일

    Returns:
        상수 이름 → 문자열 값
    """
    return _string_constants(ast.parse(path.read_text(encoding="utf-8")))


def _module_assignments(tree: ast.Module) -> Iterator[tuple[list[str], ast.expr]]:
    """모듈 최상단 대입문을 (만들어지는 이름들, 대입되는 값)으로 편다.

    **이름을 목록으로 내는 이유는 `COL_A = COL_B = "x"` 때문이다.** 하나만 돌려주면 그렇게
    정의된 상수가 「이 패키지가 정의한 것」 목록에서 빠지고, 그 이름의 죽은 레이블은
    「다른 계층에서 가져온 것」으로 잘못 분류돼 영영 안 잡힌다.

    Args:
        tree: 검사할 모듈의 AST

    Returns:
        (이름 목록, 값 노드) 순회자. 값이 없는 선언(`x: int`)은 내지 않는다
    """
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                yield [node.target.id], node.value
        elif isinstance(node, ast.Assign):
            if names := [target.id for target in node.targets if isinstance(target, ast.Name)]:
                yield names, node.value


def _package_trees(package: Path) -> dict[Path, ast.Module]:
    """패키지의 모든 소스를 **한 번씩만** 파싱해 돌려준다.

    같은 파일을 두 번 파싱하면 노드 객체가 새로 생겨 **`id()` 로 하는 「이 노드는 사전 안이다」
    판정이 헛돈다** — 실제로 그렇게 만들었더니 죽은 레이블을 한 건도 잡지 못했다.

    Args:
        package: 검증 패키지 폴더

    Returns:
        파일 경로 → 그 파일의 AST
    """
    return {module: ast.parse(module.read_text(encoding="utf-8")) for module in sorted(package.rglob("*.py"))}


def _rename_dicts(tree: ast.Module) -> list[tuple[str, ast.Dict]]:
    """모듈 최상단의 **컬럼 이름표 사전**을 모은다 — `COL_* → DISPLAY_*` 모양의 것.

    **이름이 아니라 «구조»로 찾는다: 키에 상수 이름이 오는 사전.** 처음에는 `*_LABELS` 라는
    이름으로 찾았는데, 그러면 사전 이름을 `COLUMN_MAP` 으로 바꾸는 것만으로 그 검증이 감시에서
    통째로 빠지면서 **검사는 초록으로 남는다** — 막으려는 실패 방식과 정확히 같다.

    구조로 거르면 값-사전(`HORIZON_LABELS`·`MODEL_LABELS`·`EXTREME_DIRECTION_LABELS`)이
    자연히 빠진다. 키가 정수·실수·열거형이라 이름이 아니기 때문이다. **그것들이 섞이면 해롭다** —
    그 사전 «안»의 노드까지 「사전 안이라 참조로 세지 않는다」에 걸려, 값 자리에 쓰인 살아 있는
    이름이 죽은 것으로 뒤집힌다.

    Args:
        tree: 검사할 모듈의 AST

    Returns:
        (사전 이름, 사전 노드) 목록
    """
    return [
        (names[0], value)
        for names, value in _module_assignments(tree)
        if isinstance(value, ast.Dict) and any(isinstance(key, ast.Name) for key in value.keys)
    ]


def _absolute_module(path: Path, node: ast.ImportFrom) -> str:
    """`from ... import` 의 대상 모듈을 **절대 경로로 펴서** 돌려준다.

    상대 import 를 그대로 두면 `from ..option_expiry import x` 가 모듈명 `option_expiry` 로만
    보여 어느 패키지인지 판정할 수 없다. **`level` 을 파일 위치에 적용해야** 절대 경로가 나온다.

    **`src` 밖의 파일은 상대 경로를 펼 수 없다.** 이 헬퍼는 `tests/`·`scripts/` 의 파일에도
    불리는데 거기서 `relative_to(_SOURCE_ROOT)` 는 `ValueError` 를 던진다 — 그러면 계약 테스트가
    **단언 대신 예외로 죽어** 무엇이 깨졌는지 메시지가 엉뚱해진다. 그쪽에 상대 import 가
    하나 생기는 날 터지므로 지금은 조용하다. 그런 파일은 **모듈명을 그대로** 돌려준다.

    Args:
        path: import 문이 들어 있는 소스 파일
        node: 검사할 import 노드

    Returns:
        `verify_lab.` 으로 시작하는 절대 모듈 경로. `src` 밖의 상대 import 는 적힌 그대로
    """
    if not node.level or not path.is_relative_to(_SOURCE_ROOT):
        return node.module or ""

    # 마지막 segment 는 모듈 이름이므로 떼면 그 파일이 속한 패키지가 된다.
    # `__init__.py` 도 같다 — 그 이름이 마지막 segment 자리를 차지한다
    package = ["verify_lab", *path.relative_to(_SOURCE_ROOT).with_suffix("").parts][:-1]
    base = package[: len(package) - (node.level - 1)]

    return ".".join([*base, *((node.module or "").split(".") if node.module else [])])


def _imported_study_packages(path: Path) -> set[str]:
    """그 파일이 가져오는 **검증 패키지 이름**을 모은다 (자기 것 포함).

    Args:
        path: 검사할 소스 파일

    Returns:
        `verify_lab.studies.` 바로 다음 segment 의 집합
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    prefix = "verify_lab.studies."
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = _absolute_module(path, node)
            if module == "verify_lab.studies":
                found.update(alias.name for alias in node.names)
            elif module.startswith(prefix):
                found.add(module[len(prefix) :].split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(
                alias.name[len(prefix) :].split(".")[0] for alias in node.names if alias.name.startswith(prefix)
            )

    return found


def _names_borrowed_from_common(tree: ast.Module) -> set[str]:
    """`measure`·`report` 에서 가져온 이름을 모은다.

    Args:
        tree: 파싱된 모듈

    Returns:
        그 모듈이 공통 계층에서 import 한 이름의 집합 (별칭이 있으면 별칭)
    """
    common = ("verify_lab.measure", "verify_lab.report")

    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(common)
        for alias in node.names
    }


def _declared_all(tree: ast.Module) -> set[str]:
    """모듈이 선언한 `__all__` 의 이름을 모은다.

    **네 가지 모양을 모두 본다** — `__all__ = [...]` · `__all__: Final = [...]`(이 저장소의
    지배적 표기다) · 튜플 · 두 목록의 이어붙임. 한 모양만 보면 다른 모양으로 쓴 모듈이
    **검사를 통과하고**, 그때 계약은 초록인데 재노출은 살아 있다.

    Args:
        tree: 파싱된 모듈

    Returns:
        `__all__` 에 실린 문자열 집합. 선언이 없으면 빈 집합
    """
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue

        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue

        return {
            item.value for item in ast.walk(value) if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }

    return set()


def _passthrough_names(path: Path) -> set[str]:
    """그 모듈을 **거쳐 가기만 하는** 공통 계층 이름을 모은다.

    `measure`·`report` 에서 가져온 이름은 그 모듈이 자기 안에서 쓰려고 가져온 것이다.
    **그런데 다른 모듈이 그것을 «이 모듈에서» 가져가면 옛 경로가 생긴다** — 소유자를 옮겨도
    그 경로로 들어오는 코드가 그대로 통과해 이동이 실제로 일어났는지 확인할 방법이 없다.

    Args:
        path: 검사할 소스 파일

    Returns:
        그 모듈이 공통 계층에서 가져온 이름의 집합
    """
    return _names_borrowed_from_common(ast.parse(path.read_text(encoding="utf-8")))


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


def _dataset_record_calls() -> list[tuple[str, dict[str, str]]]:
    """`dataset_record` **호출부**와 넘긴 인자의 출처를 모은다.

    소유자를 옮긴 뒤로 사전 리터럴은 한 곳뿐이라, 「`ticker` 에 표시 이름을 넣는」 원래 버그가
    되살아날 수 있는 자리는 **호출부**다. `dataset_record(ticker=dataset.label, ...)` 로 써도
    **둘 다 `str` 이라 타입 검사가 못 잡고**, 미국 ETF 는 코드와 이름이 같아(`QQQ`) 산출물을
    눈으로 봐도 드러나지 않는다.

    Returns:
        (저장소 상대 경로, {인자 이름: 값 표현식의 소스}) 목록
    """
    calls: list[tuple[str, dict[str, str]]] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = str(path.relative_to(_SOURCE_ROOT.parent))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "dataset_record":
                continue
            calls.append(
                (relative, {item.arg: ast.unparse(item.value) for item in node.keywords if item.arg is not None})
            )

    return calls


def _files_building_dataset_record() -> list[str]:
    """데이터셋 한 줄을 **직접 조립하는** 파일을 찾는다.

    **함수 이름으로 찾지 않는다.** 이름은 파일마다 달랐고(`_dataset_record`·`_run_dataset`)
    이름을 바꾸는 것만으로 검사에서 빠진다. 대신 **다섯 키를 다 가진 사전 리터럴**을 찾는다 —
    그것이 곧 「이 파일이 그 줄을 만든다」는 사실이다.

    Returns:
        다섯 키를 가진 사전 리터럴이 있는 파일의 저장소 상대 경로 목록 (정렬됨)
    """
    found: list[str] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _string_constants(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Dict) and _DATASET_MINIMUM_KEYS <= _dict_string_keys(node, constants):
                found.append(str(path.relative_to(_SOURCE_ROOT.parent)))
                break

    return found


def _dict_string_keys(node: ast.Dict, constants: dict[str, str]) -> set[str]:
    """사전 리터럴의 키를 **문자열 값으로** 읽는다.

    키가 `KEY_TICKER` 같은 이름이면 그 모듈의 최상단 상수를 뒤져 값으로 바꾼다.
    값을 알 수 없는 키(계산식·펼침)는 건너뛴다.

    Args:
        node: 사전 리터럴 노드
        constants: 그 모듈의 문자열 상수 (이름 → 값)

    Returns:
        키 문자열의 집합
    """
    keys: set[str] = set()

    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
        elif isinstance(key, ast.Name) and key.id in constants:
            keys.add(constants[key.id])

    return keys


def _output_files_mapping(package: Path) -> dict[str, str]:
    """그 검증이 선언한 「산출물 필드 → 파일 이름」 사전을 읽는다.

    **값이 이름인 것도 푼다.** 파일 이름을 이미 상수로 갖고 있던 검증은 그 상수를 값에 쓰므로
    (`"comparison": COMPARISON_FILENAME`), 리터럴만 보면 그 검증이 통째로 검사에서 빠진다.

    Args:
        package: 검증 패키지 폴더

    Returns:
        필드 이름 → 파일 이름. 선언이 없으면 빈 사전
    """
    module = package / "constants.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))

    # 공통 네 파일과 판정표는 `report/constants.py` 가 소유하므로 그쪽도 함께 본다
    constants = {**_module_constants(_SOURCE_ROOT / "report" / "constants.py"), **_module_constants(module)}

    for names, value in _module_assignments(tree):
        if _OUTPUT_FILES not in names or not isinstance(value, ast.Dict):
            continue

        mapping: dict[str, str] = {}
        for key, item in zip(value.keys, value.values, strict=True):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                mapping[key.value] = item.value
            elif isinstance(item, ast.Name):
                mapping[key.value] = constants.get(item.id, item.id)

        return mapping

    return {}


def _files_formatting_period() -> list[str]:
    """기간 표기(`시작 ~ 종료`)를 **산출물 값으로** 만드는 파일을 찾는다.

    **사람이 읽는 문장은 뺀다.** 로그와 예외 메시지에도 `~` 로 구간을 적는 자리가 많은데
    (`f"조회 구간이 뒤집혔습니다: {start} ~ {end}"`), 그것은 산출물 형식이 아니라 문장의
    일부다. 거기까지 상수를 강제하면 **수집기가 출력 계층의 상수를 가져오게 된다.**

    Returns:
        기간 표기를 값으로 만드는 파일의 저장소 상대 경로 목록 (정렬됨)
    """
    found: list[str] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        narrated = _docstring_ids(tree)
        narrated |= {id(inner) for root in _narration_nodes(tree) for inner in ast.walk(root)}

        for node in ast.walk(tree):
            if id(node) in narrated:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _PERIOD_SEPARATOR in node.value:
                found.append(str(path.relative_to(_SOURCE_ROOT.parent)))
                break

    return found


def _narration_nodes(tree: ast.Module) -> list[ast.AST]:
    """사람이 읽는 문장을 만드는 노드를 모은다 — 로그 호출과 `raise` 문.

    Args:
        tree: 검사할 모듈의 AST

    Returns:
        그 노드들 (안쪽 전체가 「문장」으로 취급된다)
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        or (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _is_logger(node.func.value))
    ]


def _is_logger(node: ast.expr) -> bool:
    """그 표현식이 로거를 가리키는지 본다.

    Args:
        node: 호출 대상의 앞부분

    Returns:
        로거면 참
    """
    return isinstance(node, ast.Name) and node.id == "logger"


def _run_summary_payloads(path: Path) -> list[str]:
    """`save_run_summary` 에 넘기는 **요약 값**의 소스를 모은다.

    **문자열 검사 대신 AST 로 본다.** 소스에 한 줄이 맞게 적혀 있어도 그 앞에서
    `summary["output_dir"] = ...` 로 한 칸을 끼우면 문자열 검사는 통과한다. 넘기는 값이
    **산출물의 속성 하나**인지를 보면 그 우회가 막힌다.

    Args:
        path: 검사할 스크립트

    Returns:
        호출마다 두 번째 인자의 소스 (키워드로 넘긴 경우 그 값)
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    payloads: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name != "save_run_summary":
            continue

        keyword = next((item.value for item in node.keywords if item.arg == "payload"), None)
        if keyword is not None:
            payloads.append(ast.unparse(keyword))
        elif len(node.args) >= 2:
            payloads.append(ast.unparse(node.args[1]))

    return payloads


def _filename_constants(tree: ast.Module) -> dict[str, str]:
    """`*_FILENAME` 모양의 문자열 상수를 모은다.

    Args:
        tree: 검사할 모듈의 AST

    Returns:
        상수 이름 → 값
    """
    return {name: value for name, value in _string_constants(tree).items() if name.endswith("_FILENAME")}


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
        `month_end`·`option_expiry`·`leverage_tracking`·`futures_leverage`·`execution/periods`
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


class TestPrincipleValueOwnership:
    """「측정의 원칙」이 요구하는 값은 공통 계층 하나가 소유한다

    **이름이 아니라 값으로 검사한다.** 세 계층이 같은 문자열을 각자 다른 이름으로 들 수 있어
    이름으로 찾으면 세 벌이 있어도 한 건도 안 걸린다. 산출물에 나가는 것은 값이다.
    """

    def test_방향_표기를_한_곳에서만_정의한다(self) -> None:
        """
        목적: 측정의 원칙 11 의 두 방향이 갈라지지 않게 한다.

        **같은 컬럼의 같은 값이 두 경로로 들어오고 있었다** — 월말 매매는 `measure.screening`
        에서, 옵션 만기일 매매는 `strategy.constants` 에서 가져왔다.

        Given: `src/verify_lab` 전체
        When: `위`·`아래` 를 상수 값으로 정의하는 파일을 찾는다
        Then: `measure/screening.py` 하나뿐이다
        """
        # When / Then
        for value in ("위", "아래"):
            assert _files_with_literal(value) == [_MEASURE_SCREENING], f"{value!r} 을 자체 정의한 파일이 있습니다"

    def test_어긋남_컬럼과_레이블을_검증마다_두지_않는다(self) -> None:
        """
        목적: 측정의 원칙 13 의 **절반만 통합된 상태**를 닫는다.

        판정 함수는 `measure/statistics` 로 올라갔는데 **컬럼 이름과 표시 레이블은 두 검증에
        한 벌씩 남아 있었다.** 같은 원칙이 요구하는 것을 검증마다 두면 두 산출물의 같은 컬럼이
        조용히 갈라진다.

        Given: `src/verify_lab` 전체
        When: 컬럼 토큰과 표시 레이블을 정의하는 파일을 각각 찾는다
        Then: 컬럼은 `measure/constants.py`, 레이블은 `report/constants.py` 하나뿐이다
        """
        # When / Then
        assert _files_with_literal("mean_rate_conflict") == [_MEASURE_CONSTANTS]
        assert _files_with_literal("평균-비율 어긋남") == [_REPORT_CONSTANTS]

    def test_절반_구간_이름을_한_곳에서만_정의한다(self) -> None:
        """
        목적: 측정의 원칙 17 의 구간 이름이 **세 벌**이던 것을 닫는다.

        원칙 17 은 모든 매매법에 이 축을 요구한다. 매매 계층과 두 검증이 각자 이름을 두면
        한쪽만 바뀌어도 예외가 나지 않고, 두 산출물의 `구간`/`시기` 열이 다른 말을 갖는다.

        **`measure/constants.py` 가 소유하는 이유**: `JUDGEABLE_YES`(값이면서 표에 그대로 실리는
        문자열)가 이미 같은 이유로 거기 있다. 표시 전용 레이블이 아니라 **데이터 칸에 들어가는 값**이다.

        Given: `src/verify_lab` 전체
        When: `앞 절반`·`뒤 절반` 을 상수 값으로 정의하는 파일을 찾는다
        Then: `measure/constants.py` 하나뿐이다
        """
        # When / Then
        for value in ("앞 절반", "뒤 절반"):
            assert _files_with_literal(value) == [_MEASURE_CONSTANTS], f"{value!r} 을 자체 정의한 파일이 있습니다"


class TestReportLabelOwnership:
    """`measure`·`report` 가 내는 공통 컬럼의 한글 레이블은 `report/constants.py` 가 소유한다

    계약이 「검증마다 다른 말을 쓰면 두 결과를 나란히 읽을 수 없다」로 정한 자리다.
    **이미 알려진 충돌은 목록으로 고정하고 그 밖의 새 충돌만 막는다** — 같은 한글 단어가
    계층마다 다른 것을 가리키는 자리가 실재하기 때문이다(`구간`·`방향`·`제외`).
    """

    def test_알려진_것_말고는_report_레이블을_재정의하지_않는다(self) -> None:
        """
        목적: `평균(%)`·`최고(%)`·`최악(%)`·`표준편차(%)`·`신호` 가 매매 계층에 한 벌 더 있던
        상태로 되돌아가지 않게 하고, **새 재정의가 조용히 늘어나는 것**을 막는다.

        검사는 **부분집합**이다. 허용목록에 적힌 자리가 나중에 통합돼 사라지는 것은 막지 않는다 —
        막으면 다음 계획서가 중복을 줄일 때마다 이 테스트가 실패한다.

        Given: `report/constants.py` 의 `DISPLAY_*` 문자열 전부
        When: 같은 문자열을 정의하는 다른 파일을 찾는다
        Then: 허용목록에 적힌 파일뿐이다
        """
        # Given
        labels = {
            value
            for name, value in _module_constants(_SOURCE_ROOT / "report" / "constants.py").items()
            if name.startswith("DISPLAY_")
        }
        assert labels, "report 레이블을 하나도 찾지 못했습니다"

        # When / Then
        for label in sorted(labels):
            offenders = set(_files_defining_value(label)) - {_REPORT_CONSTANTS}
            allowed = _REPORT_LABEL_COLLISIONS.get(label, frozenset())

            assert offenders <= allowed, f"{label!r} 을 재정의한 파일이 있습니다: {sorted(offenders - allowed)}"


class TestDisplayLabelLiveness:
    """이름표 사전에 **죽은 레이블**이 쌓이지 않는다

    **[중요] 런타임 가드로는 못 막는다.** `report.tables.to_display_columns` 는 표마다 컬럼 구성이
    달라 사전이 언제나 **상위집합**이어야 하고, 그래서 검사가 「표 → 사전」 한 방향뿐이다 —
    사전에 있는데 아무 표에도 안 나오는 키는 그냥 통과한다. 양방향으로 막으면 정상 호출이
    전부 막힌다. **그 반대 방향을 여기서 본다.**

    그렇게 쌓인 죽은 레이블은 **미사용 전수 스캔에도 안 잡힌다** — 사전에 키로 한 번 얹히는
    것만으로 「쓰인다」가 되기 때문이다. 한 검증이 두 쌍을 그렇게 이고 있던 것이 실물 사례다.
    """

    def test_사전의_키_중_그_검증이_정의한_것은_사전_밖에서도_쓰인다(self) -> None:
        """
        목적: 컬럼을 만드는 코드는 사라졌는데 이름표만 남는 상태를 막는다.

        **자기가 정의한 키만 판정한다.** `measure`·`common` 에서 가져온 키(`COL_SIGNAL_COUNT` 등)는
        **다른 계층이 그 컬럼을 프레임에 넣으므로** 검증 패키지 안에서는 사전이 유일한 등장처인
        것이 정상이다. 그 구별을 빼면 살아 있는 레이블이 무더기로 걸린다.

        Given: `studies/` 각 패키지의 컬럼 이름표 사전
        When: 키 중 그 패키지가 «정의한» 이름이 사전 밖에서 참조되는지 본다
        Then: 한 건도 빠짐없이 참조된다
        """
        # Given
        packages = sorted(path for path in (_SOURCE_ROOT / "studies").iterdir() if path.is_dir())
        assert packages, "검증 패키지를 하나도 찾지 못했습니다"

        judged = 0
        for package in packages:
            trees = _package_trees(package)
            dicts = [(module, name, node) for module, tree in trees.items() for name, node in _rename_dicts(tree)]
            if not dicts:
                continue

            owned = {name for tree in trees.values() for names, _ in _module_assignments(tree) for name in names}
            loads = [
                node
                for tree in trees.values()
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            ]

            # When / Then
            for module, name, labels in dicts:
                # **판정 중인 사전 «하나»만 뺀다.** 발견한 사전을 전부 빼면 스키마 사전
                # (`SCHEDULE_DTYPES` 등)에도 들어 있는 살아 있는 컬럼이 죽은 것으로 뒤집힌다 —
                # 그 사전에 실린다는 것이 곧 「그 컬럼이 프레임에 만들어진다」는 뜻이다
                inside = {id(node) for node in ast.walk(labels)}
                referenced = {node.id for node in loads if id(node) not in inside}

                keys = {key.id for key in labels.keys if isinstance(key, ast.Name)}
                dead = sorted(key for key in keys & owned if key not in referenced)
                judged += len(keys & owned)

                relative = module.relative_to(_SOURCE_ROOT)
                assert dead == [], f"{relative} 의 {name} 에 죽은 레이블이 있습니다: {dead}"

        # **검사가 조용히 아무것도 안 보게** 되는 것을 막는다. 사전을 구조로 찾으므로 이름을
        # 바꿔서는 빠져나갈 수 없고, 여기 걸린다면 사전이 리터럴이 아니게 된 것이다
        assert judged > 0, "판정한 키가 하나도 없습니다 — 사전 발견 규칙이 깨졌습니다"


class TestStudyPackageComposition:
    """검증 패키지는 자기 값을 한 파일에서만 정의하고 다른 검증을 모른다"""

    def test_같은_접두사의_같은_값을_두_파일에_두지_않는다(self) -> None:
        """
        목적: 한 검증 안에서 같은 컬럼 토큰이 두 벌이던 상태로 되돌아가지 않게 한다.

        `studies/futures_leverage` 가 `COL_PRICE`·`COL_INTEREST` 를 `constants.py` 와
        `position.py` **양쪽에** 갖고 있었다. **값이 우연히 같아서 동작했고**, 한쪽만 바뀌면
        `runner` 와 `position` 이 다른 컬럼을 가리키는데 예외는 나지 않는다.

        **접두사가 같을 때만 본다.** `COL_HOLD_DAYS`(DataFrame 컬럼)와 `KEY_HOLD_DAYS`(JSON 키)는
        **다른 이름공간**이라 같은 토큰을 써도 충돌이 아니다.

        Given: `studies/` 의 검증 패키지 전부
        When: 한 패키지 안에서 접두사가 같은 이름이 같은 문자열을 두 파일에 정의하는지 본다
        Then: 한 건도 없다
        """
        # Given
        packages = sorted(path for path in (_SOURCE_ROOT / "studies").iterdir() if path.is_dir())
        assert packages, "검증 패키지를 하나도 찾지 못했습니다"

        # When / Then
        for package in packages:
            # **파일 이름이 아니라 경로로 센다.** 하위 폴더가 생기면 같은 이름의 모듈이 둘이 되고,
            # 이름으로 세면 그 둘이 한 파일로 뭉개져 중복이 조용히 통과한다
            seen: dict[tuple[str, str], str] = {}
            for module in sorted(package.rglob("*.py")):
                relative = str(module.relative_to(package))
                for name, value in _module_constants(module).items():
                    key = (name.split("_")[0], value)
                    previous = seen.setdefault(key, relative)

                    assert (
                        previous == relative
                    ), f"{package.name} 의 {value!r} 이 {previous} 와 {relative} 양쪽에 정의돼 있습니다 ({name})"

    def test_검증끼리_서로를_가져오지_않는다(self) -> None:
        """
        목적: 매매 계층에서 겪은 사슬이 검증 계층에 생기지 않게 **미리** 고정한다.

        공유 함수가 특정 검증 파일의 소유가 되면, 그 검증 사정으로 고칠 때 빌려 쓰는 쪽이
        조용히 함께 바뀐다. 공통으로 올릴 것은 `measure`·`report` 로 가야 한다.

        Given: `studies/` 의 모든 소스 파일
        When: 각 파일이 가져오는 검증 패키지를 본다 (상대 import 도 절대 경로로 펴서)
        Then: 자기 패키지만 가져온다
        """
        # Given / When / Then
        for package in sorted(path for path in (_SOURCE_ROOT / "studies").iterdir() if path.is_dir()):
            for module in sorted(package.rglob("*.py")):
                borrowed = _imported_study_packages(module) - {package.name}

                assert borrowed == set(), f"{package.name}/{module.name} 이 다른 검증을 가져옵니다: {sorted(borrowed)}"


class TestCommonLayerReexport:
    """공통 계층의 이름은 **소유자에서 직접** 가져온다

    `src/verify_lab/CLAUDE.md` 「매매 계층 구성 계약」이 **기각안으로 명시한 패턴**이다 —
    그 경로가 지원되는 한 옛 사슬이 언제든 되살아나고, 실제로 테스트 하나가 그 경로로 들어와
    소유자가 바뀌어도 통과하는 상태였다.

    [중요] **`__all__` 을 지우는 것으로는 옛 경로가 닫히지 않는다.** `__all__` 은 `import *` 에만
    걸리고 `from verify_lab.execution.constants import PERIOD_FIRST_HALF` 는 그대로 동작한다.
    그래서 선언이 아니라 **실제 import 문**을 본다.
    """

    def test_아래_계층을_거쳐_공통_이름을_가져오지_않는다(self) -> None:
        """
        목적: 소유자를 옮겼는데 옛 경로로 들어오는 코드가 남는 것을 막는다.

        `tests/test_studies_leverage_breakdown.py` 가 `max_non_overlapping` 을
        **`studies.leverage_tracking.breakdown` 에서** 가져오고 있었다. 소유자가
        `measure.statistics` 로 옮겨간 뒤에도 그 테스트는 통과했고, 그래서 이동이 실제로
        일어났는지 확인할 방법이 없었다.

        Given: `studies/`·`execution/` 가 공통 계층에서 가져온 이름
        When: `src`·`tests`·`scripts` 전체에서 그 이름을 **그 모듈에서** 가져오는 곳을 찾는다
        Then: 한 곳도 없다
        """
        # Given
        passthrough = {
            f"verify_lab.{'.'.join(path.relative_to(_SOURCE_ROOT).with_suffix('').parts)}": _passthrough_names(path)
            for folder in ("studies", "execution")
            for path in (_SOURCE_ROOT / folder).rglob("*.py")
        }
        assert any(passthrough.values()), "공통 계층에서 이름을 가져오는 모듈을 하나도 찾지 못했습니다"

        # When / Then
        for folder in ("src", "tests", "scripts"):
            for consumer in sorted((BASE_DIR / folder).rglob("*.py")):
                for node in ast.walk(ast.parse(consumer.read_text(encoding="utf-8"))):
                    if not isinstance(node, ast.ImportFrom):
                        continue
                    source = _absolute_module(consumer, node) if node.level else node.module or ""
                    leaked = {alias.name for alias in node.names} & passthrough.get(source, set())

                    assert leaked == set(), (
                        f"{consumer.relative_to(BASE_DIR)}:{node.lineno} 가 공통 계층의 이름을 "
                        f"{source} 를 거쳐 가져옵니다: {sorted(leaked)}"
                    )

    def test_공통_이름을_import_별표로_내보내지_않는다(self) -> None:
        """
        목적: `__all__` 이 되살아나 **Ruff 의 미사용 import 검사를 잠재우는** 것을 막는다.

        위 테스트가 실제 경로를 막으므로 순수 통과용 import 는 미사용이 되어 Ruff 가 잡는다.
        **그런데 `__all__` 에 이름을 얹으면 그 검사가 꺼진다** — 전에 네 모듈이 정확히
        그 상태였다. 두 장치가 함께 있어야 통과 경로가 다시 열리지 않는다.

        Given: `studies/`·`execution/` 의 모든 소스 파일
        When: `__all__` 과 공통 계층에서 가져온 이름을 겹쳐 본다
        Then: 겹치는 이름이 없다
        """
        # Given
        modules = sorted(path for folder in ("studies", "execution") for path in (_SOURCE_ROOT / folder).rglob("*.py"))
        assert modules, "검사할 모듈을 하나도 찾지 못했습니다"

        # When / Then
        for module in modules:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            reexported = _declared_all(tree) & _names_borrowed_from_common(tree)

            assert reexported == set(), f"{module.name} 이 공통 계층의 이름을 재노출합니다: {sorted(reexported)}"


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


class TestExecutionLayerComposition:
    """공유 실행 계층은 매매법을 모르고, 매매법마다 실행 모듈이 하나다

    **등급(검증·매매)은 분류일 뿐이라 코드를 가르지 않는다.** 승격해도 파일이 움직이지
    않으므로, 매매법 코드는 그 매매법의 검증 패키지 안에 함께 있고 공유 로직만
    `execution/` 에 남는다.
    """

    def test_공유_모듈이_매매법을_가져오지_않는다(self) -> None:
        """
        목적: 매매법-중립 모듈이 특정 매매법의 값을 알게 되는 것을 막는다.

        **`trade_fill.simulate_signal` 의 `stop_level` 기본값이 역방향의 −5% 였다.** 다른
        매매법은 자기 값을 넘기므로 드러나지 않았지만, 인자를 빠뜨리는 순간 **다른
        매매법의 손절선이 조용히 적용된다** — 예외가 나지 않고 성적만 달라진다.
        공유 `constants.py` 가 `studies.reverse.constants` 를 가져오던 시절에는
        **월말 매매를 돌려도 역방향의 `DATASETS` 정의가 딸려 왔다.**

        **매매 파라미터가 검증 패키지 안으로 들어가면서 두 금지가 하나가 됐다** — 전에는
        「매매법별 상수 모듈」과 「검증 패키지」를 따로 막아야 했는데, 이제 후자 하나로 닫힌다.

        Given: 매매법 이름이 없는 공유 실행 모듈
        When: 각 파일이 가져오는 검증 패키지를 본다
        Then: 하나도 없다
        """
        # Given
        shared = [(_SOURCE_ROOT / "execution" / f"{name}.py") for name in _EXECUTION_SHARED]

        # When / Then
        for path in shared:
            assert path.is_file(), f"공유 실행 모듈이 없습니다: {path}"
            borrowed = _imported_study_packages(path)
            assert borrowed == set(), f"{path.name} 가 검증 패키지를 가져옵니다: {sorted(borrowed)}"

    def test_체결_판정식이_매매법_기본값을_갖지_않는다(self) -> None:
        """
        목적: 「기본값을 두지 않는다」를 `trade_fill` 에도 건다.

        `measure.screening.screen_candidates` 의 `tradable` 과
        `execution.constants.stop_level_value` 의 `measurable` 이 **같은 이유로 이미 기본값을 두지 않는다** —
        기본이 있으면 인자를 빠뜨린 호출이 조용히 틀린 성적을 낸다. 그 관용을 따른다.

        Given: `execution/trade_fill.py`
        When: 두 진입점의 손절선 인자를 본다
        Then: 기본값이 없다
        """
        # Given
        tree = ast.parse((_SOURCE_ROOT / "execution" / "trade_fill.py").read_text(encoding="utf-8"))
        entries = {"simulate_signal", "simulate_scheduled_trade"}

        # When
        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in entries:
                continue
            arguments = node.args
            defaulted = {
                argument.arg
                for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
                if default is not None
            }
            defaulted |= {argument.arg for argument in arguments.args[len(arguments.args) - len(arguments.defaults) :]}

            # Then
            assert "stop_level" not in defaulted, f"{node.name} 의 stop_level 에 기본값이 있습니다"
            checked += 1

        assert checked == len(entries), f"체결 진입점을 다 찾지 못했습니다 ({checked}/{len(entries)})"

    def test_매매법마다_실행_모듈이_하나다(self) -> None:
        """
        목적: 매매법 이름을 알면 파일 이름을 알 수 있게 고정한다 (목표 1·2).

        **파일 이름이 아니라 «폴더»가 매매법을 말한다.** 매매 코드가 그 매매법의 검증
        패키지 안에 있으므로 `studies/<slug>/trading.py` 하나이고, 승격해도 움직이지 않는다.

        Given: `studies/` 폴더
        When: 실행 모듈이 든 패키지 이름을 본다
        Then: 확정 이름표의 세 매매법이 각각 하나씩 있다
        """
        # When
        slugs = {path.parent.name for path in _trading_modules()}

        # Then
        assert slugs == {"reverse", "option_expiry", "month_end"}

    def test_체결_판정식을_공유_모듈_밖에서_정의하지_않는다(self) -> None:
        """
        목적: 판정식 단일화(절대 원칙 5)를 기계로 건다.

        월말에 체결 파일을 만들려면 계산을 복사해야 했고, 그러면 **같은 매매법의 손익비가
        산출물마다 달라지는데 어느 쪽이 맞는지 판별할 방법이 없다.**

        Given: `src/verify_lab` 전체
        When: 체결 결과 타입을 직접 정의하는 파일을 찾는다
        Then: `execution/trade_fill.py` 말고는 하나도 없다
        """
        # When
        offenders = _files_defining(r"^\s*class\s+TradeResult\b")

        # Then
        assert offenders == ["verify_lab/execution/trade_fill.py"], f"체결 결과 타입을 자체 정의한 파일이 있습니다: {offenders}"


class TestDatasetRecordKeys:
    """`summary.json` 의 `datasets` 한 줄은 계층을 가리지 않고 같은 키를 쓴다

    **소유자를 옮기면서 검사할 자리가 바뀌었다.** 전에는 검증마다 사전을 손으로 조립해서
    「그 사전의 키」를 봤는데, 이제 리터럴은 `report/run_summary.py` 한 곳뿐이다
    (`TestDatasetRecordOwnership` 가 그것을 고정한다). 되살아날 수 있는 실수는 **호출부**로
    옮겨갔으므로 여기서는 그쪽을 본다.
    """

    def test_여섯_산출_지점이_모두_공통_함수를_쓴다(self) -> None:
        """
        목적: 「범위의 SoT 는 `summary.json` 의 `datasets`」를 여섯 산출 지점이 같은 말로 이행한다.

        **월말만 계약대로였다.** 역방향은 `ticker` 에 «표시 이름»을 담고 `label` 이 아예 없었으며
        기간을 `start_date`+`end_date`, 행 수를 `row_count` 로 불렀다.

        Given: `src/verify_lab` 전체
        When: `dataset_record` 를 부르는 파일을 모은다
        Then: 검증 셋과 매매 셋이 전부 들어 있다
        """
        # Given
        expected = {
            "verify_lab/studies/reverse/runner.py",
            "verify_lab/studies/option_expiry/runner.py",
            "verify_lab/studies/month_end/runner.py",
            "verify_lab/studies/reverse/trading.py",
            "verify_lab/studies/option_expiry/trading.py",
            "verify_lab/studies/month_end/trading.py",
        }

        # When
        callers = {relative for relative, _ in _dataset_record_calls()}

        # Then
        assert expected <= callers, f"공통 함수를 쓰지 않는 산출 지점이 있습니다: {sorted(expected - callers)}"

    def test_코드와_이름과_파일이_제_출처에서_온다(self) -> None:
        """
        목적: 키 이름만 맞고 **값이 엉뚱한 데서 오는** 상태를 막는다.

        [중요] **함수를 하나로 줄이는 것만으로는 이 버그가 안 닫힌다.** 호출부에서
        `dataset_record(ticker=dataset.label, ...)` 로 쓰면 키 이름은 그대로 `ticker` 다.
        **미국 ETF 는 코드와 이름이 같아(`QQQ`) 산출물을 눈으로 봐도 드러나지 않고**,
        둘 다 `str` 이라 타입 검사도 못 잡는다 — 그래서 출처를 직접 본다.

        Given: `dataset_record` 호출부 전부
        When: 세 인자의 값 표현식을 봤을 때
        Then: 코드는 `.ticker`, 이름은 `.label`, 파일은 파일 이름에서 온다
        """
        # Given
        expected_suffixes = {
            "ticker": (".ticker",),
            "label": (".label",),
            # 경로를 통째로 넣지 못하게 한다 — `path.name` 이거나 애초에 이름인 필드여야 한다
            "file": (".name", ".file_name"),
        }

        # When
        calls = _dataset_record_calls()
        assert calls, "`dataset_record` 호출을 하나도 찾지 못했습니다"

        # Then
        for relative, arguments in calls:
            for key, suffixes in expected_suffixes.items():
                source = arguments[key]
                assert source.endswith(suffixes), f"{relative} 의 {key} 가 {source!r} 에서 옵니다"


class TestRunSummaryOwnership:
    """실행 요약을 만드는 것은 runner 이고 CLI 는 그대로 넘기기만 한다

    **여기는 `datasets` 키가 아니라 「누가 요약을 조립하는가」를 본다.** 규칙을 다른
    스크립트로 넓힐 때 이 클래스가 그 자리다.
    """

    def test_CLI_가_요약에_값을_끼워_넣지_않는다(self) -> None:
        """
        목적: 요약의 소유자를 runner 하나로 되돌린다 (`scripts/CLAUDE.md` 「CLI 에 도메인 로직 금지」).

        CLI 가 `{**outputs.summary, "output_dir": str(directory)}` 로 한 칸을 얹고 있었고,
        그 값이 **이 PC 의 절대경로**였다. `output_dir` 은 그 파일이 놓인 폴더 자신이라
        값 자체가 잉여이기도 하다 — `meta.json` 쪽은 「최근 실행이 어디 있나」를 찾는 용도라 남긴다.

        Given: 실행 스크립트 전부
        When: 요약을 저장하는 줄을 봤을 때
        Then: 사전 리터럴을 조립한 흔적이 없다
        """
        # Given
        scripts = _runner_scripts()
        assert scripts, "실행 스크립트를 하나도 찾지 못했습니다"

        # When / Then
        for path in scripts:
            source = path.read_text(encoding="utf-8")
            assert "save_run_summary(\n" not in source, f"{path.name} 가 요약을 조립합니다"

    def test_CLI_가_요약을_runner_에서_그대로_받는다(self) -> None:
        """
        목적: 「CLI 에 도메인 로직 금지」를 **실행 스크립트 전체**로 넓힌다.

        실제로 배수 검증 둘이 `run_info`·`summary` 를 **CLI 에서 리터럴 키로 조립**하고
        있었고, 그래서 그 둘만 `row_counts` 가 별칭이었다.

        **문자열이 아니라 AST 로 본다.** 소스 문자열 검사는 앞줄에 한 칸을 끼워 넣는 것으로
        우회되는데(`summary["output_dir"] = ...`), 넘기는 «값의 모양»을 보면 그 우회가 막힌다.

        **매매법 셋은 한 실행이 측정과 체결을 함께 내므로 요약도 합쳐 넘긴다.** 합치는 것은
        CLI 가 아니라 공유 모듈(`execution/run_summary.merge_run_summary`)이 하며, 그 이름을
        거친 지역변수만 허용한다 — 사전 리터럴을 조립하면 이름이 달라 걸린다.

        Given: 실행 스크립트 전부
        When: `save_run_summary` 호출의 두 번째 인자를 본다
        Then: runner 산출물의 속성이거나, 공유 모듈이 합친 요약이다
        """
        # Given
        scripts = _runner_scripts()
        assert scripts, "실행 스크립트를 하나도 찾지 못했습니다"

        # When / Then
        for path in scripts:
            payloads = _run_summary_payloads(path)
            merged = _merged_summary_names(path)

            assert payloads, f"{path.name} 가 요약을 저장하지 않습니다"
            for payload in payloads:
                allowed = payload.endswith(".summary") or payload in merged
                assert allowed, f"{path.name} 가 요약을 조립해 넘깁니다: {payload}"


class TestStudyOutputFiles:
    """산출물 파일 이름의 소유자는 그 검증의 `constants.py` 이고, 요약은 그 이름으로 키잉한다

    **전에는 CLI 가 파일 이름을 들고 요약의 별칭 키와 손으로 짝지었다.**
    `run_usdkrw_equivalence_study.py` 가 `[EQUIVALENCE_FILENAME, counts['equivalence']]` 로
    둘을 잇고 있었다 — 한쪽만 고치면 표가 엉뚱한 숫자를 보여주는데 예외는 나지 않는다.

    매매 계층은 `build_run_summary` 가 이미 런타임으로 이것을 거부한다
    (`row_counts` 의 키가 `.csv` 로 끝나지 않으면 `ValueError`). 여기서는 **검증 계층**을 본다.
    """

    def test_검증마다_산출물_파일_목록을_선언한다(self) -> None:
        """
        목적: 「이 검증이 무슨 파일을 내는가」의 자리를 하나로 정한다.

        Given: 검증 패키지 전부
        When: `constants.py` 의 `OUTPUT_FILES` 를 읽는다
        Then: 선언돼 있고 값이 전부 파일 이름이다
        """
        # Given
        packages = _study_packages()
        assert packages, "검증 패키지를 하나도 찾지 못했습니다"

        # When / Then
        for package in packages:
            mapping = _output_files_mapping(package)

            assert mapping, f"{package.name} 에 {_OUTPUT_FILES} 선언이 없습니다"
            offenders = sorted(name for name in mapping.values() if not name.endswith(".csv"))
            assert offenders == [], f"{package.name} 의 산출물 이름이 파일 이름이 아닙니다: {offenders}"

            # **이름이 겹치면 한 표가 다른 표를 덮는다.** CLI 는 이 사전을 돌며 저장하고
            # runner 는 이것으로 `row_counts` 를 키잉하므로, 겹치면 **파일 하나가 사라지고
            # 요약의 칸도 하나 줄어드는데 예외가 나지 않는다**
            duplicates = sorted({name for name in mapping.values() if list(mapping.values()).count(name) > 1})
            assert duplicates == [], f"{package.name} 에 같은 파일 이름이 둘 이상 있습니다: {duplicates}"

    def test_CLI_가_산출물_파일_이름을_정의하지_않는다(self) -> None:
        """
        목적: 파일 이름이 CLI 로 흩어지는 것을 막는다 (`scripts/CLAUDE.md`).

        매매 계층은 이미 `execution/constants.py` 가 네 이름을 소유한다. 전에는 **매매
        스크립트 세 곳에 흩어진 문자열**이었고 그래서 같은 뜻의 표가 세 이름으로 갈렸다.

        Given: 검증 실행 스크립트 전부
        When: `*_FILENAME` 상수를 찾는다
        Then: 하나도 없다
        """
        # When / Then
        for path in _runner_scripts():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defined = sorted(_filename_constants(tree))

            assert defined == [], f"{path.name} 가 파일 이름을 정의합니다: {defined}"

    def test_CLI_가_파일_이름을_직접_적지_않는다(self) -> None:
        """
        목적: 「스크립트가 그 문자열을 되짚는다」를 막는다 — `.csv` 규약이 생긴 이유다.

        `run_month_end_study.py` 가 `save_table(directory, f"{name}.csv", table)` 로
        요약의 별칭 키에 확장자를 붙여 파일 이름을 만들고 있었다. **그러면 파일 이름의 SoT 가
        사실상 요약 키가 되고**, 그 키를 바꾸는 순간 산출물 파일 이름이 함께 바뀐다.

        **「조립 금지」가 아니라 「확장자를 적지 마라」로 건다.** 짝마다 파일을 내는 검증은
        `WINDOWS_FILENAME_TEMPLATE.format(...)` 로 이름을 만드는 것이 정당한데, 그때 확장자를
        포함한 **틀은 그 검증의 `constants.py` 가 소유한다.** 조립 자체를 막으면 그것까지 막힌다.

        **산문은 뺀다.** 도움말 문구가 산출물을 가리키며 파일 이름을 언급하는 것은 설명이지
        정의가 아니다(`execution.csv 가 「아래」를 인버스 실물로 재기 때문이다`).
        **「파일 이름 «하나»로만 이루어진 문자열」**만 정의로 본다 — 산문은 공백이 있어 갈린다.

        Given: 검증 실행 스크립트 전부
        When: 파일 이름 모양의 문자열 리터럴을 찾는다 (docstring 제외)
        Then: 하나도 없다
        """
        # When / Then
        for path in _runner_scripts():
            written = sorted(value for value in _literals(path) if _FILENAME_SHAPE.fullmatch(value))

            assert written == [], f"{path.name} 가 파일 이름을 직접 적습니다: {written}"


class TestDatasetRecordOwnership:
    """데이터셋 한 줄을 만드는 구현은 한 벌이다

    계약이 「검증 셋은 각자 만든다 — `studies → strategy` 의존이 계층 방향을 뒤집기
    때문」이라고 적어 두었는데, **`report` 로 옮기면 그 이유가 사라진다.**
    `studies` 도 `strategy` 도 이미 `report` 에 의존하므로 방향이 뒤집히지 않는다.
    """

    def test_정의처가_하나다(self) -> None:
        """
        목적: 판정식 단일화(절대 원칙 5)를 데이터셋 한 줄에도 적용한다.

        **키를 맞추는 것만으로는 갈라짐이 안 닫힌다.** 다섯 키와 값의 출처를 맞춰도
        구현이 여러 벌로 남으면 한 벌만 고쳐도 예외가 나지 않는다.

        Given: `src/verify_lab` 전체
        When: 다섯 키를 가진 사전 리터럴이 있는 파일을 찾는다
        Then: `report/run_summary.py` 하나뿐이다
        """
        # When
        builders = _files_building_dataset_record()

        # Then
        assert builders == [_REPORT_RUN_SUMMARY], f"데이터셋 한 줄을 직접 조립한 파일이 있습니다: {builders}"

    def test_기간_구분자를_한_곳에서만_정의한다(self) -> None:
        """
        목적: 기간 구분자가 여러 곳에 박히는 것을 막는다.

        `PERIOD_SEPARATOR` 가 매매 계층에 있으면 **`studies` 가 가져올 수 없어**(계층 방향)
        검증 runner 가 f-string 에 `" ~ "` 를 직접 적게 된다. **형식을 고정하는 것이 없으면
        한 곳만 `" - "` 로 바뀌어도 예외가 나지 않는다.**

        **로그·예외 문장은 뺀다.** 거기에도 `~` 로 구간을 적지만 그것은 산출물 형식이 아니라
        문장의 일부이고, 강제하면 수집기가 출력 계층의 상수를 가져오게 된다.

        Given: `src/verify_lab` 전체
        When: 그 구분자를 **산출물 값으로** 적은 파일을 찾는다
        Then: 소유자 하나뿐이다
        """
        # When
        offenders = _files_formatting_period()

        # Then
        assert offenders == [_REPORT_RUN_SUMMARY], f"기간 구분자를 직접 적은 파일이 있습니다: {offenders}"


class TestDirectionNameOwnership:
    """`DIRECTION_*` 이라는 **이름**은 측정 계층 하나가 갖는다

    값 검사(`TestPrincipleValueOwnership`)는 `위`·`아래` 가 한 곳에만 있는지 본다.
    그런데 배수 검증이 **같은 이름에 다른 값**(`오름`·`내림`)을 두고 있어 값 검사를 그대로
    통과한다 — 잘못된 모듈에서 가져와도 문자열이 나오므로 **조용히 다른 축이 된다.**

    두 값은 **동음이의어가 아니라 다른 개념**이다. `measure` 의 것은 신호를 «어느 쪽으로
    거는가»(원칙 11)이고 배수 검증의 것은 «기초지수가 오른 날인가»다. 그래서 통합하지 않고
    **이름을 가른다.**
    """

    def test_방향_이름을_측정_계층_밖에서_쓰지_않는다(self) -> None:
        """
        Given: `src/verify_lab` 전체
        When: `DIRECTION_*` 이름과 `Direction` 이라는 **값**을 정의하는 파일을 찾는다
        Then: 둘 다 `measure/screening.py` 하나뿐이다
        """
        # When / Then
        for name in ("DIRECTION_UP", "DIRECTION_DOWN", "COL_DIRECTION"):
            offenders = _files_defining(rf"^{name}\s*[:=]")

            assert offenders == [_MEASURE_SCREENING], f"{name} 을 자체 정의한 파일이 있습니다: {offenders}"

        # **이름만 갈라서는 안 닫힌다.** 컬럼 토큰이 같으면 그 프레임이 측정 계층의 헬퍼를
        # 지날 때 값이 조용히 다른 축으로 읽힌다 — 둘 다 `str` 이라 타입 검사도 못 잡는다
        assert _files_defining_value("Direction") == [_MEASURE_SCREENING], "`Direction` 을 자체 정의한 파일이 있습니다"


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


class TestKrxCommonOwnership:
    """KRX 공통 판정을 수집기가 다시 만들지 않는다"""

    # 소유자와 검사 대상. **`scripts/data/` 까지 본다** — CLI 도 같은 규격을 상대하므로
    # 거기 복사본이 생기면 똑같이 갈라지고, `scripts/CLAUDE.md` 가 그것을 이미 금지한다
    _OWNER_FILE = "krx_common.py"
    _SHARED_NAMES = ("to_numeric", "exclude_recent", "validate_krx_date")

    @staticmethod
    def _scanned_modules() -> list[Path]:
        """검사 대상 파일 목록을 만든다.

        Returns:
            `data/` 와 `scripts/data/` 의 파이썬 파일
        """
        return sorted((_SOURCE_ROOT / "data").glob("*.py")) + sorted((BASE_DIR / "scripts" / "data").glob("*.py"))

    def test_최근_구간_제외를_인라인으로_다시_만들지_않는다(self) -> None:
        """
        목적: 저장 경계가 수집기마다 갈리는 것을 막는다.

        `exclude_recent` 가 한 벌이 되기 전에는 `etn`·`krx_futures` 가 **바이트 단위로 같은
        복사본**을 갖고 `pykrx_collector` 는 같은 로직을 세 함수에 인라인으로 갖고 있었다.
        **한 곳만 고쳐도 예외가 나지 않는다** — 저장 범위만 하루 달라진 파일이 만들어진다.

        **이 검사는 한 가지 «표기»만 본다.** 공백을 바꾸거나 키워드를 빼서 다시 인라인하면
        걸리지 않는다 — 함께 있는 정의처 검사가 그 몫을 맡는다.

        Given: `data/` 와 `scripts/data/` 의 모듈들
        When: 제외 경계를 직접 만드는 식(`DOMESTIC_RECENT_EXCLUSION_DAYS` 로 날짜를 빼는 것)을 찾는다
        Then: 소유자인 `krx_common.py` 밖에는 없다
        """
        # Given
        modules = self._scanned_modules()
        assert modules, "검사할 모듈을 하나도 찾지 못했습니다"

        # When
        offenders = [
            path.name
            for path in modules
            if path.name != self._OWNER_FILE
            and "timedelta(days=DOMESTIC_RECENT_EXCLUSION_DAYS)" in path.read_text(encoding="utf-8")
        ]

        # Then
        assert offenders == [], f"최근 구간 제외를 직접 만드는 모듈이 있습니다: {offenders}"

    def test_공통_판정의_정의처가_하나다(self) -> None:
        """
        목적: 같은 판정이 두 곳에서 구현되는 것을 막는다 (절대 원칙 5).

        **`scripts/data/` 도 본다** — 날짜 형식 검증이 실제로 거기 네 번째 벌로 남아 있었고,
        `data/` 만 훑는 검사는 그것을 초록으로 통과시켰다.

        Given: `data/` 와 `scripts/data/` 의 모듈들
        When: 세 함수를 **정의하는** 파일을 센다
        Then: 각각 `krx_common.py` 하나뿐이다
        """
        # Given
        modules = self._scanned_modules()
        assert modules, "검사할 모듈을 하나도 찾지 못했습니다"

        # When · Then
        for name in self._SHARED_NAMES:
            definers = [path.name for path in modules if f"def {name}(" in path.read_text(encoding="utf-8")]
            assert definers == [self._OWNER_FILE], f"`{name}` 을 정의하는 파일이 여럿입니다: {definers}"

    def test_날짜_형식_오류_메시지를_다시_적지_않는다(self) -> None:
        """
        목적: 판정을 공유해도 **메시지를 따로 적으면** 같은 드리프트가 남는 것을 막는다.

        Given: `data/` 와 `scripts/data/` 의 모듈들
        When: 형식 오류 문장을 직접 적은 파일을 찾는다
        Then: 소유자 밖에는 없다
        """
        # Given
        modules = self._scanned_modules()
        assert modules, "검사할 모듈을 하나도 찾지 못했습니다"

        # When
        offenders = [
            path.name
            for path in modules
            if path.name != self._OWNER_FILE and "형식이 잘못되었습니다 (YYYYMMDD" in path.read_text(encoding="utf-8")
        ]

        # Then
        assert offenders == [], f"날짜 형식 오류 메시지를 직접 적은 모듈이 있습니다: {offenders}"


# ============================================================
# 산출물 레이블의 유일성과 측정 구간 축의 소유자
# ============================================================

# **이미 있는 겹침만 허용목록으로 고정하고 그 밖의 새 겹침을 막는다.** 전면 금지로 두면
# 정당한 겹침까지 막힌다 — 아래 대부분은 `src/verify_lab/CLAUDE.md` 「어디까지가 공통이고
# 어디부터 그 검증의 것인가」가 **일부러 뽑지 않기로 한** 달력형·배수형 어휘다(2026-09-14 결정).
#
# 성격은 셋이다.
#   ㉮ 달력형 두 검증이 공유하는 어휘 — `진입 종가` · `청산 종가` · `보유 거래일` · `제외 사유`
#   ㉯ 배수형 두 검증이 공유하는 어휘 — `배수` · `지수` · `1배 종목` · `비중첩 표본` · `시작일` · `종료일`
#   ㉰ 같은 매매법의 «검증과 매매»가 같은 말을 쓰는 것 — `사건` · `파라미터` · `만기월` · `청산일`
#
# **여기 적힌 자리가 나중에 통합돼 사라지는 것은 막지 않는다**(부분집합 검사) —
# 막으면 중복을 줄이는 계획서마다 이 테스트가 실패한다.
_KNOWN_LABEL_DUPLICATES: dict[str, frozenset[str]] = {
    "1배 종목": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "날짜": frozenset({"verify_lab/report/constants.py", "verify_lab/studies/usdkrw_equivalence/constants.py"}),
    "등락률(%)": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/reverse/constants.py"}),
    # 배수형 두 검증이 **같은 금리 경계**로 가른 같은 축이다(검증 #9 가 #8 의 경계를 따른다).
    # `배수`·`지수` 와 같은 성격이라 여기 둔다 — 값까지 같지만 공통으로 뽑지 않는 것이 결정이다
    "금리 환경": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "방향": frozenset(
        {
            "verify_lab/report/constants.py",
            "verify_lab/execution/constants.py",
            "verify_lab/studies/leverage_tracking/constants.py",
            "verify_lab/studies/reverse/constants.py",
        }
    ),
    "배당 보정분(%p)": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "배수": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "보유 거래일": frozenset({"verify_lab/studies/month_end/constants.py", "verify_lab/studies/option_expiry/constants.py"}),
    "비중첩 표본": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "사건": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "사건 번호": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "수익률(%)": frozenset(
        {
            "verify_lab/execution/constants.py",
            "verify_lab/studies/futures_leverage/constants.py",
            "verify_lab/studies/month_end/constants.py",
            "verify_lab/studies/option_expiry/constants.py",
        }
    ),
    "시작연도": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "시작일": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "신호": frozenset({"verify_lab/report/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "실제(%)": frozenset(
        {"verify_lab/studies/leverage_tracking/constants.py", "verify_lab/studies/usdkrw_equivalence/constants.py"}
    ),
    "제외 사유": frozenset(
        {
            "verify_lab/studies/futures_leverage/constants.py",
            "verify_lab/studies/month_end/constants.py",
            "verify_lab/studies/option_expiry/constants.py",
        }
    ),
    "종가": frozenset({"verify_lab/studies/option_expiry/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "종료일": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "종목": frozenset(
        {
            "verify_lab/execution/constants.py",
            "verify_lab/studies/option_expiry/constants.py",
            "verify_lab/studies/reverse/constants.py",
            "verify_lab/studies/usdkrw_equivalence/constants.py",
        }
    ),
    "지수": frozenset(
        {"verify_lab/studies/futures_leverage/constants.py", "verify_lab/studies/leverage_tracking/constants.py"}
    ),
    "진입 종가": frozenset({"verify_lab/studies/month_end/constants.py", "verify_lab/studies/option_expiry/constants.py"}),
    "청산 종가": frozenset({"verify_lab/studies/month_end/constants.py", "verify_lab/studies/option_expiry/constants.py"}),
    "청산일": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/month_end/constants.py"}),
    "파라미터": frozenset({"verify_lab/execution/constants.py", "verify_lab/studies/reverse/constants.py"}),
    "표본": frozenset({"verify_lab/report/constants.py", "verify_lab/studies/usdkrw_equivalence/constants.py"}),
}


@cache
def _display_label_owners() -> dict[str, list[str]]:
    """`src` 안의 `DISPLAY_*` 상수를 **값 → 그 값을 정의한 파일들**로 모은다.

    `_files_defining_value` 는 값 하나를 받아 트리를 통째로 훑는다. 여기서는 반대 방향이
    필요해 한 번에 모은다 — 217종을 각각 훑으면 같은 파일을 수백 번 파싱한다.

    Returns:
        레이블 값 → 저장소 상대 경로 목록 (정렬됨)
    """
    owners: dict[str, set[str]] = {}
    for path in _SOURCE_ROOT.rglob("*.py"):
        relative = str(path.relative_to(_SOURCE_ROOT.parent))
        for name, value in _module_constants(path).items():
            if name.startswith("DISPLAY_"):
                owners.setdefault(value, set()).add(relative)

    return {value: sorted(files) for value, files in owners.items()}


class TestOutputLabelUniqueness:
    """산출물 헤더로 나가는 한글 레이블은 **뜻 하나에 이름 하나**다

    `TestReportLabelOwnership` 은 **`report` 가 정의한 레이블의 재정의**만 본다. 그래서
    `report` 가 모르는 겹침은 한 건도 걸리지 않았다 — 같은 `시기` 가 한쪽에서는 측정의 원칙 17
    의 시기 축(`앞 절반`·`최근 5년`), 다른 쪽에서는 금리 환경(`저금리(~2021)`)을 가리키는
    상태가 그렇게 남았다. **두 뜻이 같은 파일 안에 나란히 있기도 했다** — 배수 검증의
    `windows_*.csv` 가 4열에 측정 구간, 16열에 금리 환경을 담았고 둘 다 이름이 그 단어였다.
    """

    def test_알려진_것_말고는_같은_레이블을_두_곳에서_정의하지_않는다(self) -> None:
        """
        목적: 「같은 이름이 다른 것을 가리키는」 상태가 **새로 생기는 것**을 막는다.

        허용목록은 **이미 있는 겹침**을 고정한다. 대부분은 달력형·배수형 어휘를 일부러 뽑지
        않기로 한 결정의 결과이고, 그 판단의 SoT 는 `src/verify_lab/CLAUDE.md` 다.

        Given: `src` 안의 모든 `DISPLAY_*` 상수
        When: 같은 값을 두 파일 이상이 정의하는 경우를 찾는다
        Then: 허용목록에 적힌 자리뿐이다
        """
        # Given
        owners = _display_label_owners()
        assert owners, "표시 레이블을 하나도 찾지 못했습니다"

        # When — **전부 모아 한 번에 알린다.** 첫 위반에서 멈추면 고칠 때마다 다음 것이
        # 하나씩 드러나 같은 실행을 여러 번 해야 하고, 무엇이 남았는지 한눈에 보이지 않는다
        offenders = {
            value: sorted(set(files) - _KNOWN_LABEL_DUPLICATES.get(value, frozenset()))
            for value, files in owners.items()
            if len(files) > 1 and not set(files) <= _KNOWN_LABEL_DUPLICATES.get(value, frozenset())
        }

        # Then
        listed = "\n".join(f"  {value!r}: {files}" for value, files in sorted(offenders.items()))

        assert not offenders, (
            f"허용목록에 없는 레이블 겹침이 {len(offenders)}종 있습니다:\n{listed}\n" "뜻이 같으면 소유자를 하나로 두고, 뜻이 다르면 이름을 가르세요"
        )

    def test_허용목록이_실제_겹침만_담는다(self) -> None:
        """
        목적: 허용목록이 **조용히 낡는 것**을 막는다.

        검사 자체는 부분집합이라 통합돼 사라진 항목이 남아 있어도 통과한다. 그러면 목록이
        「지금 무엇이 겹쳐 있는가」의 기록 구실을 못 하게 되므로, **한 곳에서만 정의하는 값이
        목록에 남아 있으면** 알린다.

        Given: 허용목록
        When: 각 항목의 실제 정의처 수를 센다
        Then: 전부 둘 이상이다
        """
        # Given
        owners = _display_label_owners()

        # When
        stale = sorted(value for value in _KNOWN_LABEL_DUPLICATES if len(owners.get(value, [])) < 2)

        # Then
        assert stale == [], f"겹침이 해소됐는데 허용목록에 남아 있습니다: {stale}"


class TestHorizonLabelOwnership:
    """측정 구간(보유 기간)의 표시 이름은 `report/constants.py` 하나가 소유한다

    **공통 계층의 사전이 자기 축을 다 덮지 못하면 검증이 사본을 만든다.** 실제로 그 사전이
    네 칸(`1·5·10·21`)뿐이라, 같은 `(5, 10, 21, 63, 126, 252, 756)` 격자를 두고
    한 검증은 일곱 칸짜리 사본을 만들어 `1주 · 3개월 · 3년` 을 내고, 다른 검증은 라벨을 거치지
    않아 `5 · 63 · 756` 을 그대로 냈다. **두 결과를 나란히 읽을 수 없고 예외는 나지 않는다.**
    """

    _DICT_NAME = "HORIZON_LABELS"

    def test_구간_이름표가_한_곳에만_있다(self) -> None:
        """
        목적: 사본이 다시 생기는 것을 막는다.

        Given: `src` 안의 모든 모듈
        When: `HORIZON_LABELS` 를 **정의하는** 파일을 찾는다
        Then: `report/constants.py` 하나다
        """
        # Given / When
        definers = sorted(
            str(path.relative_to(_SOURCE_ROOT.parent))
            for path in _SOURCE_ROOT.rglob("*.py")
            for names, _ in _module_assignments(ast.parse(path.read_text(encoding="utf-8")))
            if self._DICT_NAME in names
        )

        # Then
        assert definers == [_REPORT_CONSTANTS], f"{self._DICT_NAME} 을 정의하는 파일이 여럿입니다: {definers}"

    def test_구간_축을_내는_검증은_이름표를_거친다(self) -> None:
        """
        목적: **원값이 그대로 나가는 경로**를 막는다.

        `COL_HORIZON` 을 표시 레이블로 rename 만 하고 값을 바꾸지 않으면 사용자가 여는 CSV 에
        거래일 수가 그대로 찍힌다. 같은 축을 다른 검증은 한글로 내므로 **두 산출물이 어긋난다.**

        Given: `COL_HORIZON` 을 출력 레이블로 내보내는 검증 패키지
        When: 그 패키지가 이름표(또는 `horizon_label`)를 쓰는지 본다
        Then: 전부 쓴다
        """
        # Given
        renamers = [
            package
            for package in _study_packages()
            for path in package.rglob("*.py")
            if "COL_HORIZON: DISPLAY_HORIZON" in path.read_text(encoding="utf-8")
        ]
        assert renamers, "구간 축을 내보내는 검증을 하나도 찾지 못했습니다"

        # When / Then
        for package in sorted(set(renamers), key=lambda item: item.name):
            sources = "\n".join(path.read_text(encoding="utf-8") for path in package.rglob("*.py"))

            assert (
                self._DICT_NAME in sources or "horizon_label" in sources
            ), f"{package.name} 이 구간 축을 이름표 없이 내보냅니다 — 거래일 수가 원값으로 나갑니다"


class TestCliHelpRenders:
    """`--help` 가 실제로 렌더링되는가

    [중요] **`scripts/` 는 이 저장소의 다른 테스트가 닿지 않는 자리다**(`scripts/CLAUDE.md`).
    그래서 CLI 가 깨져도 Ruff·PyRight·계약 테스트를 전부 통과한다 — 실측으로
    `--stop-grid` 의 help 문자열에 `%` 를 escape 하지 않아 `--help` 가 `ValueError` 로
    죽는 동안 **1,276건이 통과했다.**

    argparse 는 help 문자열에 `%` 포매팅을 걸므로 `-1.0%~-10.0%` 처럼 적으면
    **파서를 만들 때가 아니라 help 를 «그릴 때»** 터진다. 그래서 여기서 실제로 그려 본다.
    """

    @pytest.mark.parametrize("script", _runner_scripts(), ids=lambda path: path.stem)
    def test_실행_스크립트의_help_가_그려진다(self, script: Path) -> None:
        """
        목적: help 문자열의 `%` 미escape 같은 고장을 잡는다

        Given: 매매법 실행 스크립트
        When: `--help` 로 인자를 파싱했을 때
        Then: help 를 그리고 정상 종료한다 (`ValueError` 가 아니다)
        """
        # Given
        module = _load_script(script)
        assert hasattr(module, "parse_args"), f"{script.name} 에 parse_args 가 없습니다"

        # When
        original = sys.argv
        sys.argv = [script.name, "--help"]
        try:
            with contextlib.redirect_stdout(io.StringIO()) as rendered:
                with pytest.raises(SystemExit) as exit_info:
                    module.parse_args()
        finally:
            sys.argv = original

        # Then
        assert exit_info.value.code == 0
        assert "--help" in rendered.getvalue()


class TestStopGridWiring:
    """`--stop-grid` 가 격자를, 기본이 확정 손절선을 고르는가

    [중요] **이 배선이 뒤집혀도 ruff·pyright·pytest 가 전부 통과한다.** 성적표가 조용히
    15행에서 300행이 되고, 유일한 신호는 `storage/results/` 의 git diff 다
    (`scripts/CLAUDE.md` 「동작은 여전히 아무도 보지 않습니다」).

    **동작(플래그 파싱)과 구조(어느 상수를 고르는가)를 함께 본다** — 플래그만 보면
    삼항이 뒤집힌 것을 못 잡고, 구조만 보면 플래그 이름이 바뀐 것을 못 잡는다.
    """

    _SCRIPT = BASE_DIR / "scripts" / "run_option_expiry.py"

    def test_stop_grid_는_기본이_꺼짐이다(self) -> None:
        """
        목적: 기본 실행이 격자를 내지 않는다는 것을 플래그 층에서 고정한다

        Given: 옵션 만기일 실행 스크립트
        When: 인자 없이 파싱했을 때와 `--stop-grid` 로 파싱했을 때
        Then: 각각 거짓과 참이다
        """
        # Given
        module = _load_script(self._SCRIPT)

        # When
        original = sys.argv
        try:
            sys.argv = [self._SCRIPT.name]
            default = module.parse_args()
            sys.argv = [self._SCRIPT.name, "--stop-grid"]
            enabled = module.parse_args()
        finally:
            sys.argv = original

        # Then
        assert default.stop_grid is False
        assert enabled.stop_grid is True

    def test_플래그가_격자를_기본이_확정_손절선을_고른다(self) -> None:
        """
        목적: 삼항이 뒤집히는 것을 막는다

        **CLI 가 목록을 조립하지 않고 이름 둘 중 하나를 고른다**는 계약도 함께 고정한다 —
        조립하면 `constants.py` 의 소유자와 갈리고 `meta.json` 이 돌지 않은 격자를 적는다.

        **소스 문자열로 보지 않는다** — 같은 문장이 주석에 있어도 통과하고(이 스크립트에는
        바로 그 내용의 주석 블록이 있다), 이름을 바꾸거나 포매터가 줄을 접으면 실패한다.

        Given: 옵션 만기일 실행 스크립트의 구문 트리
        When: `stop_levels` 에 대입하는 삼항을 찾았을 때
        Then: 조건이 `args.stop_grid` 이고 참일 때 격자, 거짓일 때 확정 손절선이다
        """
        # Given
        tree = ast.parse(self._SCRIPT.read_text(encoding="utf-8"))

        # When
        chosen = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "stop_levels" for target in node.targets)
        ]

        # Then
        assert len(chosen) == 1, f"`stop_levels` 에 대입하는 자리가 하나가 아닙니다 ({len(chosen)}곳)"
        ternary = chosen[0]
        assert isinstance(ternary, ast.IfExp), "손절선을 삼항으로 고르지 않습니다 — 상수 이름 둘 중 하나여야 합니다"
        assert isinstance(ternary.test, ast.Attribute) and ternary.test.attr == "stop_grid", "`--stop-grid` 로 가르지 않습니다"
        assert isinstance(ternary.body, ast.Name) and ternary.body.id == "EXPIRY_STOP_GRID", "플래그가 참일 때 격자가 아닙니다"
        assert isinstance(ternary.orelse, ast.Name) and ternary.orelse.id == "EXPIRY_STOP_DEFAULT", "기본이 확정 손절선이 아닙니다"

    def test_고른_손절선이_체결과_화면에_실제로_넘어간다(self) -> None:
        """
        목적: **고르기만 하고 넘기지 않는** 상태를 막는다

        삼항은 그대로 두고 `run_option_expiry_trading(cells)` 로 되돌리면 `--stop-grid` 가
        조용히 기본 15행을 내면서 **화면은 「손절선 20종 · 성적표 300행」을 외친다.**

        [중요] **인자의 «값»까지 본다.** 이름만 보면 `stop_levels=EXPIRY_STOP_DEFAULT` 로 박아
        플래그를 무시하는 것을 못 잡는다 — 그것도 같은 고장이다.

        Given: 옵션 만기일 실행 스크립트의 구문 트리
        When: 체결 함수와 범위 출력 함수의 호출을 찾았을 때
        Then: 둘 다 고른 목록(`stop_levels` 변수)을 그대로 받는다
        """
        # Given
        tree = ast.parse(self._SCRIPT.read_text(encoding="utf-8"))

        def _is_chosen(node: ast.expr | None) -> bool:
            """고른 목록을 담은 변수 그대로인지 본다."""
            return isinstance(node, ast.Name) and node.id == "stop_levels"

        # When
        passed: dict[str, bool] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "run_option_expiry_trading":
                passed["체결"] = any(
                    keyword.arg == "stop_levels" and _is_chosen(keyword.value) for keyword in node.keywords
                )
            if node.func.id == "_print_scope":
                passed["화면"] = len(node.args) >= 2 and _is_chosen(node.args[1])

        # Then
        assert passed.get("체결"), "체결 함수가 고른 손절선 목록을 그대로 받지 않습니다 — 플래그가 무시될 수 있습니다"
        assert passed.get("화면"), "범위 출력이 고른 손절선 목록을 그대로 받지 않습니다 — 돌지 않은 행 수를 적게 됩니다"
