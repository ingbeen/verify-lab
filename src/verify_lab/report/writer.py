"""검증 산출물 저장

산출물은 **매매법당 한 폴더에만 쌓이고 재실행이 그 자리를 덮는다.** 같은 소스로 다시 돌리면
결과가 바이트 단위로 같으므로, 실행마다 폴더를 새로 만들면 **내용이 같고 이름만 다른 사본**이
무한히 쌓인다. 어느 실행의 값인지는 폴더 이름이 아니라 `summary.json` 의 `datasets`·`rule` 이 말한다.

[주의] **`실측` 계층에는 그 요약이 없다.** 프로브 스크립트는 `save_run_summary` 를 부르지 않아
CSV 만 남으므로, **폴더만 봐서는 어느 대상을 잰 것인지 알 수 없다.** 남겨야 할 값은
`docs/spec/` 의 「데이터 실측 기록」이 담는다.

폴더 생성과 저장을 이 계층이 소유한다. 검증 스크립트마다 같은 코드를 두면 경로 규칙이 조용히
갈라지고, 나중에 그 결과들이 같은 검증의 산출물인지 알 수 없게 된다. **스크립트가 폴더 이름을
직접 조립하면 경로 규칙을 바꿀 때 그 스크립트만 옛 자리에 남는다** — 계층 폴더를 도입할 때
실측 스크립트 둘이 그 상태였다.
"""

import json
import re
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from verify_lab.common_constants import RESULT_LAYERS, RESULTS_DIR
from verify_lab.report.constants import CSV_ENCODING, RUN_SUMMARY_FILENAME
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 폴더 이름에 쓸 수 있는 매매법 이름. **폴더 이름이 곧 이 값이므로 정의처가 여기다** —
# 코드에서 매매법은 영문 slug 하나로 불린다(`docs/INDEX.md` §3 이름표).
#
# [중요] **모양 검사가 경로 탈출도 막는다.** 이름이 폴더 이름 «전체» 이고 그 폴더를 비우므로,
# `../` 나 `/` 가 섞이면 산출물 루트 밖을 겨눠 지운다. 그래서 검사는 «비우기보다 먼저» 한다
TRACK_NAME_PATTERN = r"[a-z][a-z_]*"
VALID_TRACK_NAME = re.compile(rf"^{TRACK_NAME_PATTERN}$")

# 절대경로로 읽히는 문자열의 머리. **손으로 박는다** — `BASE_DIR` 에서 파생시키면 이 PC 의
# 경로만 보게 되어 **다른 PC 가 쓴** 경로를 못 잡는다. 실제로 커밋된 산출물에
# mac(`/Users/`)과 WSL(`/home/`) 두 벌이 섞여 있었고 **둘 다 `/` 로 시작한다.**
# `~/` 를 함께 보는 것은 홈 표기도 PC 를 타기 때문이다.
# 윈도우 드라이브 문자를 넣지 않는 것은 이 저장소의 두 PC 가 모두 POSIX 이기 때문이다 —
# 오지 않은 경우를 상상해 넣으면 `D:`·UNC 경로는 어차피 빠져 반쪽짜리 안심만 준다
ABSOLUTE_PATH_PREFIXES = ("/", "~/")


def create_run_directory(track_name: str, *, layer: str) -> Path:
    """`storage/results/<계층>/<매매법>/` 을 **비우고** 만든다.

    **계층은 경로가 말하고 폴더 이름에는 넣지 않는다.** 매매법 이름이 측정과 매매에서 같아야
    한다는 것이 이 저장소의 규약이므로, 둘을 가르는 것은 상위 폴더뿐이다. 이름에 접미사를
    또 붙이면 중복이고, 접미사가 계층마다 갈리면 **같은 매매법이 두 이름으로 불려** 사용자가
    두 산출물 폴더를 옛것/새것으로 오해한다.

    [중요] **비우는 이유**: 덮어쓰기는 파일 단위라 이번 실행이 내지 않는 파일은 남는다.
    옵션 만기일의 손절선 격자가 `--grid` 실행에서만 나오므로, 비우지 않으면 **한 폴더에 두
    실행의 파일이 섞이고 예외는 나지 않는다.** 비우는 범위는 이 매매법 폴더 안뿐이다 —
    계층 폴더까지 비우면 검증 여섯을 잇달아 돌릴 때 **마지막 하나만 남는다.**

    Args:
        track_name: 매매법 이름(slug). `studies/<slug>/constants.py` 의 `TRACK_NAME` 을 넘긴다
        layer: 산출물 계층. `common_constants.RESULT_LAYERS` 의 값 하나여야 한다

    Returns:
        만들어진 빈 폴더 경로

    Raises:
        ValueError: 매매법 이름이 비어 있거나 모양이 맞지 않거나, 선언되지 않은 계층인 경우
    """
    name = track_name.strip()
    if not name:
        raise ValueError("매매법 이름이 비어 있습니다")

    # [중요] **검사는 반드시 비우기보다 먼저다.** 이름이 폴더 이름 전체라
    # `../` 나 `/` 가 섞이면 산출물 루트 밖을 겨눠 지운다
    if not VALID_TRACK_NAME.match(name):
        raise ValueError(f"매매법 이름은 영소문자와 밑줄로만 이루어져야 합니다: {name}")

    # 오타를 통과시키면 **예외 없이 새 상위 폴더가 생긴다.** 산출물이 선언된 세 계층 밖으로
    # 조용히 흩어지고, 그 자리는 아무도 보지 않는다
    if layer not in RESULT_LAYERS:
        raise ValueError(f"알 수 없는 산출물 계층입니다: {layer} (가능한 값: {list(RESULT_LAYERS)})")

    directory = RESULTS_DIR / layer / name

    # 심볼릭 링크는 `rmtree` 가 거부하고, 끊어진 링크는 `exists()` 가 False 라 아래 `mkdir` 에서
    # 죽는다. 링크 자체만 지우면 둘 다 평범한 「자리 비우기」가 된다
    if directory.is_symlink():
        directory.unlink()
    elif directory.exists():
        shutil.rmtree(directory)

    # `exist_ok` 는 **계층 폴더 때문에 필요하다** — 같은 계층의 다른 매매법이 동시에 돌면
    # 상위 폴더 생성이 겹친다. 매매법 폴더 자체는 바로 위에서 비워 두었다
    directory.mkdir(parents=True, exist_ok=True)
    logger.debug(f"결과 폴더 준비: {directory}")

    return directory


def save_table(directory: Path, filename: str, table: pd.DataFrame) -> Path:
    """표를 CSV 로 저장한다.

    인덱스는 저장하지 않는다 — 사용자가 여는 표에 의미 없는 열이 생긴다.

    Args:
        directory: 저장할 폴더
        filename: 파일 이름 (`report/constants.py` 의 상수를 쓴다)
        table: 표시용 표

    Returns:
        저장된 파일 경로

    Raises:
        ValueError: 표가 비어 있는 경우
    """
    if table.empty:
        raise ValueError(f"표가 비어 있습니다: {filename}")

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    table.to_csv(path, index=False, encoding=CSV_ENCODING)
    logger.debug(f"표 저장: {path} ({len(table):,}행)")

    return path


def _strings_in(value: Any, trail: str = "") -> Iterator[tuple[str, str]]:
    """중첩된 자료구조의 문자열을 **자리 표시와 함께** 편다.

    [중요] **사전의 키도 값과 똑같이 본다.** `row_counts` 는 파일 이름으로 키잉되므로 경로가
    키 쪽에 박힐 수 있고, 값만 보면 절반을 놓친다.

    Args:
        value: 검사할 값 (사전·목록·문자열이 섞인 중첩 구조)
        trail: 지금까지의 자리 표시

    Yields:
        (자리 표시, 문자열)
    """
    if isinstance(value, str):
        yield trail, value
    elif isinstance(value, Mapping):
        for key, inner in value.items():
            here = f"{trail}.{key}" if trail else str(key)
            if isinstance(key, str):
                yield f"{here} (키)", key
            yield from _strings_in(inner, here)
    elif isinstance(value, list | tuple):
        for index, inner in enumerate(value):
            yield from _strings_in(inner, f"{trail}[{index}]")


def absolute_paths_in(payload: Any) -> list[tuple[str, str]]:
    """실행 요약 안의 절대경로를 **자리와 함께** 찾는다.

    **중첩을 재귀로 훑는다.** 결함이 최상위 키에만 있지 않았다 — 등가성 검증의 것은
    `inputs.spot.close` 처럼 두 단계 아래에 있어 얕게 보면 그대로 지나간다.

    Args:
        payload: 실행 요약

    Returns:
        (자리 표시, 그 문자열) 목록. 없으면 빈 목록
    """
    return [(trail, text) for trail, text in _strings_in(payload) if text.startswith(ABSOLUTE_PATH_PREFIXES)]


def save_run_summary(directory: Path, payload: Mapping[str, Any]) -> Path:
    """실행 파라미터와 핵심 통계를 JSON 으로 남긴다.

    남기지 않으면 산출물만 보고 어떤 설정의 결과인지 재구성할 수 없다.
    난수를 쓴 계산은 **시드가 여기 남아야 재현된다.**

    **절대경로가 든 요약은 거부한다.** 요약이 담는 것은 경로가 아니라 파일 이름이라는 것이
    계약이고(`src/verify_lab/CLAUDE.md` 실행 요약), 이 함수가 `summary.json` 을 쓰는 유일한
    자리라 여기서 막으면 검증과 매매가 한꺼번에 덮인다. 검사를 검증마다 두면 **한 곳만 빠져도
    아무 신호가 없다** — 실제로 그렇게 커밋된 요약 11개에 mac 과 WSL 두 PC 의 경로가 섞였다.

    Args:
        directory: 저장할 폴더
        payload: 실행 정보

    Returns:
        저장된 파일 경로

    Raises:
        ValueError: 요약 어딘가에 절대경로가 든 경우
    """
    found = absolute_paths_in(payload)
    if found:
        listed = ", ".join(f"{trail}={text!r}" for trail, text in found)
        raise ValueError(f"실행 요약에 절대경로가 있습니다 (파일 이름만 담으세요): {listed}")

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / RUN_SUMMARY_FILENAME

    with path.open("w", encoding="utf-8") as file:
        json.dump(dict(payload), file, indent=2, ensure_ascii=False)

    logger.debug(f"실행 정보 저장: {path}")

    return path
