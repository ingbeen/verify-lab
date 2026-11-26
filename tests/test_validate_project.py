"""품질 검증 스크립트의 출력 파싱과 단계 연결 (`validate_project.py`)

**파서가 조용히 틀리면 아무도 모른다.** 도구의 출력 형식이 바뀌어도 종료코드로 성패는
갈리지만 개수는 그럴듯한 숫자로 남고, 그 숫자가 작업 보고의 품질 검증 줄에 그대로 옮겨진다.
그래서 「세지 못했다」가 숫자로 덮이지 않는 것을 여기서 고정한다.

`validate_project.py` 는 패키지가 아니라 저장소 루트의 스크립트라 경로로 직접 읽어 온다.
"""

import ast
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
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
        목적: 파싱에 실패했을 때 1 같은 숫자로 채우지 않는다.
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
        목적: 오류 0 을 「못 읽음」으로 보고 다른 값으로 덮지 않는다.

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
        목적: `passed` 가 든 줄이면 무엇이든 보는 경로를 막는다.

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


def _write_copy_and_result(tmp_path: Path, *, copy_rows: int, result_rows: int) -> tuple[Path, Path]:
    manifest = tmp_path / "manifest.json"
    entry = {"첫날": "1993-01-29", "끝날": "2026-11-10", "행 수": copy_rows}
    manifest.write_text(json.dumps({"파일": {"SPY_adjusted.csv": entry}}, ensure_ascii=False), encoding="utf-8")
    folder = tmp_path / "results" / "매매" / "중간선거_사이클"
    folder.mkdir(parents=True)
    record = {"file": "SPY_adjusted.csv", "period": "1993-01-29 ~ 2026-11-10", "rows": result_rows}
    (folder / "summary.json").write_text(json.dumps({"measure": {"datasets": [record]}}), encoding="utf-8")
    return tmp_path / "results", manifest


def test_copy_check_passes_when_results_match_the_copy(tmp_path: Path) -> None:
    results, manifest = _write_copy_and_result(tmp_path, copy_rows=8504, result_rows=8504)

    assert validate_project.run_copy_check(results, manifest) == (True, 0)


def test_copy_check_fails_with_the_mismatch_count(tmp_path: Path) -> None:
    results, manifest = _write_copy_and_result(tmp_path, copy_rows=8504, result_rows=8503)

    assert validate_project.run_copy_check(results, manifest) == (False, 1)


def test_copy_check_fails_without_a_count_when_the_manifest_cannot_be_read(tmp_path: Path) -> None:
    results, _ = _write_copy_and_result(tmp_path, copy_rows=8504, result_rows=8504)

    assert validate_project.run_copy_check(results, tmp_path / "missing.json") == (False, None)


def test_copy_check_fails_without_a_count_when_the_manifest_has_an_unexpected_shape(tmp_path: Path) -> None:
    results, manifest = _write_copy_and_result(tmp_path, copy_rows=8504, result_rows=8504)
    manifest.write_text(json.dumps({"파일": []}), encoding="utf-8")

    assert validate_project.run_copy_check(results, manifest) == (False, None)


def _record_step(calls: list[str], name: str, result: tuple[object, ...]) -> Callable[..., tuple[object, ...]]:
    def step(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        calls.append(name)
        return result

    return step


def _run_main_with_fake_steps(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], *, copies: tuple[bool, int | None]
) -> tuple[int, list[str]]:
    calls: list[str] = []
    monkeypatch.setattr(validate_project, "run_ruff", _record_step(calls, "ruff", (True, 0)))
    monkeypatch.setattr(validate_project, "run_pyright", _record_step(calls, "pyright", (True, 0)))
    monkeypatch.setattr(validate_project, "run_pytest", _record_step(calls, "pytest", (True, 1, 0, 0, 0)))
    monkeypatch.setattr(validate_project, "run_copy_check", _record_step(calls, "copies", copies))
    monkeypatch.setattr(sys, "argv", ["validate_project.py", *argv])

    exit_code = validate_project.main()

    return exit_code, calls


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ["ruff", "pyright", "pytest", "copies"]),
        (["--only-lint"], ["ruff"]),
        (["--only-pyright"], ["pyright"]),
        (["--only-tests"], ["pytest"]),
        (["--cov"], ["pytest"]),
    ],
)
def test_copy_check_runs_only_in_the_full_run(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: list[str]
) -> None:
    _, calls = _run_main_with_fake_steps(monkeypatch, argv, copies=(True, 0))

    assert calls == expected


def test_failed_copy_check_fails_the_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, _ = _run_main_with_fake_steps(monkeypatch, [], copies=(False, 1))

    assert exit_code == 1


def test_script_does_not_import_the_package_at_the_top() -> None:
    tree = ast.parse((BASE_DIR / "validate_project.py").read_text(encoding="utf-8"))

    top_modules = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names} | {
        node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)
    }

    assert not any(module.split(".")[0] == "verify_lab" for module in top_modules)
