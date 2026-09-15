#!/usr/bin/env python3
"""
통합 품질 검증 스크립트 (Ruff + PyRight + Pytest)

프로젝트의 모든 품질 검증을 단일 진입점으로 실행합니다.
AI가 실행하고 로그를 읽어 문제를 수정할 수 있도록 명확한 출력을 제공합니다.

사용법:
    poetry run python validate_project.py                # 전체 실행 (Ruff + PyRight + Pytest)
    poetry run python validate_project.py --only-lint    # Ruff만 실행
    poetry run python validate_project.py --only-pyright # PyRight만 실행
    poetry run python validate_project.py --only-tests   # Pytest만 실행
    poetry run python validate_project.py --cov          # Pytest + 커버리지만 실행
"""

import argparse
import re
import subprocess
import sys

# 개수를 파싱하지 못했을 때의 표기.
#
# **「몇 개인지 모른다」와 「1개다」는 다른 사실이다.** 전에는 파싱에 실패하면 1 로 채웠고,
# 그러면 도구 출력 형식이 바뀌어 파싱이 통째로 깨져도 「오류 1개」라는 그럴듯한 숫자가 나왔다.
# 이 저장소가 다른 곳에서 일관되게 금지하는 패턴이다 — `measure/screening.py` 가
# 「판정 안 함」과 「제외」를 가르고 `strategy/constants.py` 가 `무손절`·`손절불가` 를 가른 것과 같다.
#
# **성패 판정은 계속 종료코드로 한다.** 이 값은 표시용이며 합계에는 0 으로 들어간다
UNKNOWN_COUNT_DISPLAY = "개수 미상"

# Ruff 요약 줄 — `Found 3 errors.` / `Found 1 error.`
RUFF_SUMMARY_PATTERN = re.compile(r"\bFound (\d+) errors?\b")

# PyRight 요약 줄 — `3 errors, 1 warning, 0 informations`.
#
# **줄 전체의 «모양»을 잡는다.** 진단 줄에도 `warning` 이 들어가므로(`- warning: Import ...`)
# 「errors 라는 단어에 붙은 수」만 찾으면 진단 메시지 안의 숫자를 요약으로 오인할 수 있다.
# 세 항목이 한 줄에 순서대로 오는 것이 요약 줄의 정의다
PYRIGHT_SUMMARY_PATTERN = re.compile(r"\b(\d+) errors?, \d+ warnings?, \d+ informations?\b")

# Pytest 요약 줄 — `======= 3 failed, 1126 passed, 2 skipped in 12.34s =======`.
# **요약 줄로 한정한다** — 전에는 `passed` 가 든 줄이면 무엇이든 봤고,
# `-v` 출력의 테스트 «이름»에 그 단어가 들어가면 엉뚱한 수를 집는다.
#
# **`error` 도 함께 센다** — 수집·픽스처 실패는 `failed` 가 아니라 `errors` 로 나오는데,
# 빼면 「1 failed, 3 errors」에서 합계가 1 이 되어 **그럴듯한 숫자가 실제 손상을 덮는다**
PYTEST_SUMMARY_PATTERN = re.compile(r"^=+ .*\bin [\d.]+s.*=+$")
PYTEST_COUNT_PATTERN = re.compile(r"\b(\d+) (passed|failed|skipped|errors?)\b")

# 위 패턴이 `error` 와 `errors` 를 모두 잡으므로 키를 하나로 모은다
PYTEST_ERROR_KEYS = ("error", "errors")


def print_section(title: str) -> None:
    """섹션 제목을 출력합니다."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def format_count(count: int | None) -> str:
    """개수를 사람이 읽는 표기로 바꿉니다.

    **단위를 붙이지 않습니다** — `passed=1126` 처럼 단위 없이 쓰는 자리가 있고,
    그 표기는 계획서의 품질 검증 기록에 그대로 옮겨진다.

    Args:
        count: 파싱한 개수. 파싱하지 못했으면 None

    Returns:
        `3` 또는 `개수 미상`
    """
    return UNKNOWN_COUNT_DISPLAY if count is None else str(count)


def run_ruff() -> tuple[bool, int | None]:
    """
    Ruff 린트 체크를 실행합니다.

    Returns:
        tuple[bool, int | None]: (성공 여부, 오류 개수). 개수를 파싱하지 못했으면 None
    """
    result = subprocess.run(
        ["poetry", "run", "ruff", "check", "."],
        capture_output=True,
        text=True,
    )

    # Ruff 출력 표시
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Ruff는 문제가 있으면 exit code 1 반환
    success = result.returncode == 0

    if success:
        print("[OK] Ruff 체크 통과")
        return True, 0

    # Ruff 출력에서 오류 개수 파싱: "Found X error." 또는 "Found X errors."
    matched = RUFF_SUMMARY_PATTERN.search(result.stdout or "")
    error_count = int(matched.group(1)) if matched else None

    print(f"[FAIL] Ruff 체크 실패 (오류/경고: {format_count(error_count)}개)")
    return False, error_count


def run_pyright() -> tuple[bool, int | None]:
    """
    PyRight 타입 체크를 실행합니다.

    Returns:
        tuple[bool, int | None]: (성공 여부, 오류 개수). 개수를 파싱하지 못했으면 None
    """
    result = subprocess.run(
        ["poetry", "run", "pyright"],
        capture_output=True,
        text=True,
    )

    # PyRight 출력 표시
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # PyRight는 오류가 있으면 exit code 1 반환
    success = result.returncode == 0

    if success:
        print("[OK] PyRight 체크 통과")
        return True, 0

    # PyRight 출력에서 오류 개수 파싱: "X errors, Y warnings, Z informations"
    error_count: int | None = None
    for line in (result.stdout or "").split("\n"):
        if "warning" in line or "information" in line:
            matched = PYRIGHT_SUMMARY_PATTERN.search(line)
            if matched:
                error_count = int(matched.group(1))
                break

    print(f"[FAIL] PyRight 체크 실패 (오류: {format_count(error_count)}개)")
    return False, error_count


def run_pytest(with_coverage: bool = False) -> tuple[bool, int | None, int | None, int | None, int | None]:
    """
    Pytest 테스트를 실행합니다.

    Returns 의 넷은 **요약 줄을 찾았을 때만** 숫자입니다. 찾지 못하면 넷 다 None 이며,
    「0건」과 「세지 못했다」가 구별됩니다. pytest 는 0인 항목을 요약에서 아예 빼므로,
    요약을 찾은 뒤 없는 항목은 0 입니다.

    Args:
        with_coverage: True일 경우 커버리지 포함 실행

    Returns:
        tuple[bool, int | None, int | None, int | None, int | None]:
            (성공 여부, passed 수, failed 수, skipped 수, error 수)
    """
    if with_coverage:
        cmd = [
            "poetry",
            "run",
            "pytest",
            "--cov=src/verify_lab",
            "--cov-report=term-missing",
            "tests/",
            "-v",
        ]
    else:
        cmd = ["poetry", "run", "pytest", "tests/", "-v"]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    # Pytest 출력 표시
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Pytest는 실패가 있으면 exit code 1 반환
    success = result.returncode == 0

    # Pytest 요약 줄에서 passed/failed/skipped 파싱.
    # **`=` 로 둘러싸인 배너 줄만 본다** — `-v` 출력의 테스트 이름이나
    # "short test summary info" 아래의 `FAILED ...` 줄에 그 단어가 들어가도 섞이지 않는다
    counts: dict[str, int] | None = None
    for line in (result.stdout or "").split("\n"):
        if not PYTEST_SUMMARY_PATTERN.match(line.strip()):
            continue
        found = {keyword: int(number) for number, keyword in PYTEST_COUNT_PATTERN.findall(line)}
        if found:
            counts = found

    passed = counts.get("passed", 0) if counts is not None else None
    failed = counts.get("failed", 0) if counts is not None else None
    skipped = counts.get("skipped", 0) if counts is not None else None
    errors = sum(counts.get(key, 0) for key in PYTEST_ERROR_KEYS) if counts is not None else None

    label = "[OK] Pytest 통과" if success else "[FAIL] Pytest 실패"
    summary = f"passed={format_count(passed)}, failed={format_count(failed)}, skipped={format_count(skipped)}"
    # **0건일 때는 적지 않는다** — 평상시 출력을 바꾸지 않으면서, 실제로 난 수집·픽스처 실패는 드러낸다
    print(f"{label} ({summary})" if errors == 0 else f"{label} ({summary}, errors={format_count(errors)})")

    return success, passed, failed, skipped, errors


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱합니다."""
    parser = argparse.ArgumentParser(
        description="통합 품질 검증 스크립트 (Ruff + PyRight + Pytest)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  poetry run python validate_project.py                # 전체 실행 (Ruff + PyRight + Pytest)
  poetry run python validate_project.py --only-lint    # Ruff만 실행
  poetry run python validate_project.py --only-pyright # PyRight만 실행
  poetry run python validate_project.py --only-tests   # Pytest만 실행
  poetry run python validate_project.py --cov          # Pytest + 커버리지만 실행

참고:
  --only-* 옵션들은 상호 배타적입니다. 하나만 선택할 수 있습니다.
  --cov 옵션은 단독으로 사용하거나 --only-tests와 함께 사용할 수 있습니다.
        """,
    )

    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--only-lint",
        action="store_true",
        help="Ruff 린트 체크만 실행",
    )
    only_group.add_argument(
        "--only-pyright",
        action="store_true",
        help="PyRight 타입 체크만 실행",
    )
    only_group.add_argument(
        "--only-tests",
        action="store_true",
        help="Pytest 테스트만 실행",
    )

    parser.add_argument(
        "--cov",
        action="store_true",
        help="커버리지 포함 테스트만 실행 (단독 사용 시 Ruff, PyRight 제외)",
    )

    return parser.parse_args()


def main() -> int:
    """
    메인 함수: 옵션에 따라 Ruff, PyRight, Pytest를 실행하고 결과를 집계합니다.

    Returns:
        int: 종료 코드 (0=성공, 1=실패)
    """
    args = parse_args()

    # --cov 옵션 검증
    if args.cov and (args.only_lint or args.only_pyright):
        print("오류: --cov 옵션은 --only-lint, --only-pyright와 함께 사용할 수 없습니다.")
        return 1

    # 실행할 도구 결정
    if args.cov:
        # --cov 옵션: 테스트 + 커버리지만 실행
        should_run_lint = False
        should_run_pyright = False
        should_run_tests = True
    else:
        # 전체 실행인지 개별 도구 실행인지 판단
        is_only_mode = args.only_lint or args.only_pyright or args.only_tests

        should_run_lint = args.only_lint or not is_only_mode
        should_run_pyright = args.only_pyright or not is_only_mode
        should_run_tests = args.only_tests or not is_only_mode

    # 타이틀 생성
    tools = []
    if should_run_lint:
        tools.append("Ruff")
    if should_run_pyright:
        tools.append("PyRight")
    if should_run_tests:
        tools.append("Pytest")
    title = f"프로젝트 품질 검증 ({' + '.join(tools)})"

    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

    # 결과 수집
    results = {}
    section_num = 1

    # 1. Ruff 실행
    if should_run_lint:
        print_section(f"{section_num}. Ruff 린트 체크")
        section_num += 1
        ruff_success, ruff_errors = run_ruff()
        results["ruff"] = (ruff_success, ruff_errors)

    # 2. PyRight 실행
    if should_run_pyright:
        print_section(f"{section_num}. PyRight 타입 체크")
        section_num += 1
        pyright_success, pyright_errors = run_pyright()
        results["pyright"] = (pyright_success, pyright_errors)

    # 3. Pytest 실행
    if should_run_tests:
        print_section(f"{section_num}. Pytest 테스트")
        section_num += 1
        pytest_success, passed, failed, skipped, errors = run_pytest(with_coverage=args.cov)
        results["pytest"] = (pytest_success, passed, failed, skipped, errors)

    # 최종 결과 요약
    print_section("최종 결과")

    total_errors = 0
    all_success = True
    # 세지 못한 항목이 있었는지. **합계를 그럴듯한 숫자로 내지 않기 위해** 따로 든다
    has_unknown = False

    if "ruff" in results:
        ruff_success, ruff_errors = results["ruff"]
        total_errors += ruff_errors or 0
        has_unknown |= ruff_errors is None
        all_success &= ruff_success
        print(f"Ruff:    {'[OK] 통과' if ruff_success else f'[FAIL] 실패 (오류/경고: {format_count(ruff_errors)}개)'}")

    if "pyright" in results:
        pyright_success, pyright_errors = results["pyright"]
        total_errors += pyright_errors or 0
        has_unknown |= pyright_errors is None
        all_success &= pyright_success
        print(f"PyRight: {'[OK] 통과' if pyright_success else f'[FAIL] 실패 (오류: {format_count(pyright_errors)}개)'}")

    if "pytest" in results:
        pytest_success, passed, failed, skipped, errors = results["pytest"]
        # **수집·픽스처 실패(`errors`)도 더한다** — 빼면 「1 failed, 3 errors」가 합계 1 로 보인다
        total_errors += (failed or 0) + (errors or 0)
        has_unknown |= failed is None
        all_success &= pytest_success
        counts = f"passed={format_count(passed)}, failed={format_count(failed)}, skipped={format_count(skipped)}"
        if errors != 0:
            counts += f", errors={format_count(errors)}"
        print(f"Pytest:  {'[OK] 통과' if pytest_success else '[FAIL] 실패'} ({counts})")

    # 세지 못한 항목이 있으면 합계를 단정하지 않는다 — 「모른다」를 숫자로 덮으면
    # 도구 출력 형식이 바뀐 것과 실제로 그만큼인 것이 구별되지 않는다
    print(f"\n총 오류/경고: {total_errors}개" + (f" 이상 ({UNKNOWN_COUNT_DISPLAY} 항목 있음)" if has_unknown else ""))

    if all_success:
        print("\n[SUCCESS] 모든 품질 검증 통과!")
        return 0
    else:
        print("\n[FAILED] 품질 검증 실패. 위 오류를 수정해주세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
