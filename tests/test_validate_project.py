"""품질 검증 스크립트의 출력 파싱 (`validate_project.py`)

**파서가 조용히 틀리면 아무도 모른다.** 도구의 출력 형식이 바뀌어도 종료코드로 성패는
갈리지만 개수는 그럴듯한 숫자로 남고, 그 숫자가 계획서의 품질 검증 기록에 그대로 옮겨진다.
그래서 「세지 못했다」가 숫자로 덮이지 않는 것을 여기서 고정한다.

`validate_project.py` 는 패키지가 아니라 저장소 루트의 스크립트라 경로로 직접 읽어 온다.
"""

import importlib.util
import sys
from types import ModuleType

import pytest

from verify_lab.common_constants import BASE_DIR


def _load_validate_project() -> ModuleType:
    """루트의 품질 검증 스크립트를 모듈로 읽어 온다.

    Returns:
        불러온 모듈
    """
    path = BASE_DIR / "validate_project.py"
    spec = importlib.util.spec_from_file_location("validate_project_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"내부 불변조건 위반 - 스크립트를 불러올 수 없습니다: path={path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


validate_project = _load_validate_project()


def _pytest_counts(stdout: str) -> dict[str, int] | None:
    """`run_pytest` 의 파싱 부분만 따로 재현한다.

    실제 함수는 `subprocess` 로 pytest 를 부르므로 그대로 쓸 수 없다.
    **패턴 두 개는 프로덕션 것을 그대로 쓴다** — 여기에 다시 적으면 두 벌이 된다.

    Args:
        stdout: pytest 표준 출력

    Returns:
        키워드 → 개수. 요약 줄을 찾지 못하면 None
    """
    counts: dict[str, int] | None = None
    for line in stdout.split("\n"):
        if not validate_project.PYTEST_SUMMARY_PATTERN.match(line.strip()):
            continue
        found = {keyword: int(number) for number, keyword in validate_project.PYTEST_COUNT_PATTERN.findall(line)}
        if found:
            counts = found

    return counts


class TestFormatCount:
    """개수 표기 — 「모른다」를 숫자로 덮지 않는다"""

    def test_숫자는_단위_없이_그대로_낸다(self) -> None:
        """
        목적: `passed=1126` 처럼 단위 없이 쓰는 자리를 고정한다.

        Given · When · Then
        """
        assert validate_project.format_count(0) == "0"
        assert validate_project.format_count(27) == "27"

    def test_세지_못하면_숫자를_만들지_않는다(self) -> None:
        """
        목적: 전에 「파싱 실패 시 1」이던 자리를 고정한다.
        「몇 개인지 모른다」와 「1개다」는 다른 사실이다.

        Given: 파싱하지 못한 개수
        When: 표기로 바꾼다
        Then: 숫자가 아니라 미상 표기가 나온다
        """
        assert validate_project.format_count(None) == validate_project.UNKNOWN_COUNT_DISPLAY


class TestRuffParsing:
    """Ruff 요약 파싱"""

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("Found 1 error.", 1),
            ("Found 27 errors.", 27),
            ("Found 0 errors.", 0),
        ],
    )
    def test_요약_줄에서_개수를_읽는다(self, line: str, expected: int) -> None:
        """
        목적: 단수·복수·0 을 모두 읽는지 고정한다.

        Given: Ruff 요약 줄
        When: 패턴으로 찾는다
        Then: 그 수가 나온다
        """
        # When
        matched = validate_project.RUFF_SUMMARY_PATTERN.search(line)

        # Then
        assert matched is not None
        assert int(matched.group(1)) == expected

    def test_요약_줄이_없으면_찾지_못한다(self) -> None:
        """
        목적: 출력 형식이 바뀌면 **미상**이 되는 것을 고정한다. 숫자를 지어내면 안 된다.

        Given: 요약이 없는 출력
        When: 패턴으로 찾는다
        Then: 아무것도 나오지 않는다
        """
        assert validate_project.RUFF_SUMMARY_PATTERN.search("checked 3 files") is None


class TestPyrightParsing:
    """PyRight 요약 파싱 — 진단 줄을 요약으로 오인하지 않는다"""

    def test_요약_줄에서_오류_수를_읽는다(self) -> None:
        """
        목적: 세 항목이 한 줄에 오는 요약 줄을 고정한다.

        Given: PyRight 요약 줄
        When: 패턴으로 찾는다
        Then: 첫 수가 오류 개수다
        """
        # When
        matched = validate_project.PYRIGHT_SUMMARY_PATTERN.search("3 errors, 1 warning, 0 informations")

        # Then
        assert matched is not None
        assert int(matched.group(1)) == 3

    def test_오류가_0_이어도_읽는다(self) -> None:
        """
        목적: 전에 「첫 정수가 0 이면 fallback 이 1 로 덮던」 경로를 고정한다.

        Given: 오류가 0인 요약 줄
        When: 패턴으로 찾는다
        Then: 0 을 그대로 읽는다
        """
        # When
        matched = validate_project.PYRIGHT_SUMMARY_PATTERN.search("0 errors, 1 warning, 0 informations")

        # Then
        assert matched is not None
        assert int(matched.group(1)) == 0

    def test_진단_줄은_요약으로_보지_않는다(self) -> None:
        """
        목적: `warning` 이 든 진단 줄이 요약으로 오인되는 것을 막는다.
        오인하면 진단 메시지 안의 숫자가 오류 개수로 굳는다.

        Given: 경고 진단 한 줄
        When: 패턴으로 찾는다
        Then: 아무것도 나오지 않는다
        """
        # Given
        line = '  /x.py:12:5 - warning: Import "y" could not be resolved (7 errors in cache)'

        # When · Then
        assert validate_project.PYRIGHT_SUMMARY_PATTERN.search(line) is None


class TestPytestParsing:
    """Pytest 요약 파싱 — `-v` 출력의 테스트 이름과 섞이지 않는다"""

    def test_통과만_있는_요약을_읽는다(self) -> None:
        """
        목적: 평상시 출력을 고정한다. pytest 는 0인 항목을 요약에서 아예 뺀다.

        Given: 통과만 있는 출력
        When: 요약을 읽는다
        Then: passed 만 잡힌다
        """
        # Given
        stdout = "tests/x.py::test_a PASSED  [ 50%]\n===== 1148 passed in 12.34s ====="

        # When · Then
        assert _pytest_counts(stdout) == {"passed": 1148}

    def test_실패와_건너뜀을_함께_읽는다(self) -> None:
        """
        목적: 세 항목이 섞인 요약을 고정한다.

        Given: 실패·통과·건너뜀이 섞인 출력
        When: 요약을 읽는다
        Then: 셋 다 잡힌다
        """
        # Given
        stdout = (
            "=========================== short test summary info ============================\n"
            "FAILED tests/x.py::test_b\n"
            "=========== 3 failed, 1145 passed, 2 skipped in 9.90s ==========="
        )

        # When · Then
        assert _pytest_counts(stdout) == {"failed": 3, "passed": 1145, "skipped": 2}

    def test_수집_실패도_센다(self) -> None:
        """
        목적: `errors` 를 빼면 합계가 실제 손상을 덮는 것을 막는다.
        수집·픽스처 실패는 `failed` 가 아니라 `errors` 로 나온다.

        Given: 실패와 수집 실패가 섞인 출력
        When: 요약을 읽는다
        Then: errors 도 잡힌다
        """
        # Given
        stdout = "===== 1 failed, 3 errors, 100 passed in 2.10s ====="

        # When
        counts = _pytest_counts(stdout)

        # Then
        assert counts is not None
        assert sum(counts.get(key, 0) for key in validate_project.PYTEST_ERROR_KEYS) == 3

    def test_테스트_이름에_든_단어를_세지_않는다(self) -> None:
        """
        목적: 전에 「`passed` 가 든 줄이면 무엇이든 보던」 경로를 고정한다.

        Given: 이름에 `passed` 가 든 `-v` 줄이 앞에 오는 출력
        When: 요약을 읽는다
        Then: 요약 줄의 수만 잡힌다
        """
        # Given
        stdout = "tests/x.py::test_12_passed_rows PASSED  [ 50%]\n===== 7 passed in 1.00s ====="

        # When · Then
        assert _pytest_counts(stdout) == {"passed": 7}

    def test_요약_줄이_없으면_세지_못한다(self) -> None:
        """
        목적: 형식이 바뀌면 **미상**이 되는 것을 고정한다. 0 으로 채우면
        「한 건도 안 돌았다」와 「세지 못했다」가 구별되지 않는다.

        Given: 요약이 없는 출력
        When: 요약을 읽는다
        Then: 아무것도 나오지 않는다
        """
        assert _pytest_counts("무언가 크게 잘못됐다") is None
