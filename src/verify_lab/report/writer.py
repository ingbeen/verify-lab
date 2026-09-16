"""검증 산출물 저장

산출물은 **매매법당 한 폴더에만 쌓이고 재실행이 그 자리를 덮는다.** 같은 소스로 다시 돌리면
결과가 바이트 단위로 같으므로, 실행마다 폴더를 새로 만들면 **내용이 같고 이름만 다른 사본**이
무한히 쌓인다. 어느 실행의 값인지는 폴더 이름이 아니라 `summary.json` 의 `datasets`·`rule` 이 말한다.

[주의] **실측 프로브에는 그 요약이 없다.** 프로브 스크립트는 `save_run_summary` 를 부르지 않아
CSV 만 남으므로, **폴더만 봐서는 어느 대상을 잰 것인지 알 수 없다.** 남겨야 할 값은
설계 문서의 「데이터 실측 기록」이 담는다.

**등급 폴더는 `tracks.py` 가 정하고 이 모듈이 묻는다.** 호출 측이 등급을 넘기면 레지스트리가
SoT 가 아니게 되어, 폴더를 손으로 옮겨도 다음 실행이 원래 자리에 다시 만든다.

폴더 생성과 저장을 이 계층이 소유한다. 스크립트마다 같은 코드를 두면 경로 규칙이 조용히
갈라지고, 나중에 그 결과들이 같은 매매법의 산출물인지 알 수 없게 된다. **스크립트가 폴더 이름을
직접 조립하면 경로 규칙을 바꿀 때 그 스크립트만 옛 자리에 남는다** — 등급 폴더를 도입할 때
실측 스크립트 둘이 그 상태였다.
"""

import json
import re
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from verify_lab.common_constants import RESULTS_DIR
from verify_lab.report.constants import CSV_ENCODING, RUN_SUMMARY_FILENAME
from verify_lab.tracks import GRADES, track_of
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 코드에서 매매법을 부르는 이름(slug)의 모양. 레지스트리를 찾는 키이며 영소문자와 밑줄만 쓴다
# (`docs/INDEX.md` §3 이름표).
#
# [중요] **`$` 가 아니라 `fullmatch` 로 잰다.** `$` 는 문자열 끝뿐 아니라 **끝의 개행 바로 앞에서도**
# 맞으므로 `"reverse\n"` 이 통과한다 — 그 값이 폴더 이름이 되고 그 폴더를 `rmtree` 로 비운다
TRACK_NAME_PATTERN = r"[a-z][a-z_]*"
VALID_TRACK_NAME = re.compile(TRACK_NAME_PATTERN)

# **폴더 이름이 되는 한글 이름의 모양.** slug 와 요구가 다르다 — 한글과 대문자를 써야 하므로
# (`원달러_ETF_등가성` · `pykrx_ETF_실측`) 위 패턴을 그대로 쓸 수 없다.
#
# [중요] **모양 검사가 경로 탈출을 막는다.** 이 값이 폴더 이름 «전체» 이고 그 폴더를 비우므로,
# `../` 나 `/` 가 섞이면 산출물 루트 밖을 겨눠 지운다. 그래서 검사는 «비우기보다 먼저» 한다.
# 공백을 막는 것은 안전이 아니라 쓰임새 때문이다 — 셸·마크다운 링크에서 매번 따옴표가 필요해진다
TRACK_LABEL_PATTERN = r"[A-Za-z가-힣][0-9A-Za-z가-힣_]*"
VALID_TRACK_LABEL = re.compile(TRACK_LABEL_PATTERN)

# 절대경로로 읽히는 문자열의 머리. **손으로 박는다** — `BASE_DIR` 에서 파생시키면 이 PC 의
# 경로만 보게 되어 **다른 PC 가 쓴** 경로를 못 잡는다. 실제로 커밋된 산출물에
# mac(`/Users/`)과 WSL(`/home/`) 두 벌이 섞여 있었고 **둘 다 `/` 로 시작한다.**
# `~/` 를 함께 보는 것은 홈 표기도 PC 를 타기 때문이다.
# 윈도우 드라이브 문자를 넣지 않는 것은 이 저장소의 두 PC 가 모두 POSIX 이기 때문이다 —
# 오지 않은 경우를 상상해 넣으면 `D:`·UNC 경로는 어차피 빠져 반쪽짜리 안심만 준다
ABSOLUTE_PATH_PREFIXES = ("/", "~/")


def create_run_directory(track_name: str) -> Path:
    """`storage/results/<등급>/<한글 이름>/` 을 **비우고** 만든다.

    **폴더 이름은 slug 가 아니라 한글 이름이다.** 사용자가 여는 것이 이 폴더인데 이름이 코드
    식별자면 문서와 대조할 때마다 번역해야 한다. 한글 이름을 쓰면 `docs/<등급>/<한글 이름>/` 과
    자리가 그대로 맞는다.

    **등급은 경로가 말하고 폴더 이름에는 넣지 않는다.** 이름에 접미사를 또 붙이면 중복이고,
    접미사가 등급마다 갈리면 **같은 매매법이 두 이름으로 불려** 사용자가 두 산출물 폴더를
    옛것/새것으로 오해한다.

    [중요] **등급을 인자로 받지 않는다.** 호출 측이 넘기면 `tracks.py` 가 SoT 가 아니게 되고,
    폴더를 손으로 옮겨도 다음 실행이 원래 자리에 다시 만든다. 승격·강등이 레지스트리 한 줄로
    끝나려면 등급을 묻는 자리가 여기 하나여야 한다.

    [중요] **비우는 이유**: 덮어쓰기는 파일 단위라 이번 실행이 내지 않는 파일은 남는다.
    손절선 격자처럼 옵션에서만 나오는 파일이 있으므로, 비우지 않으면 **한 폴더에 두 실행의
    파일이 섞이고 예외는 나지 않는다.** 비우는 범위는 이 매매법 폴더 안뿐이다 —
    등급 폴더까지 비우면 여럿을 잇달아 돌릴 때 **마지막 하나만 남는다.**

    Args:
        track_name: 매매법 이름(slug). `studies/<slug>/constants.py` 의 `TRACK_NAME` 을 넘긴다

    Returns:
        만들어진 빈 폴더 경로

    Raises:
        ValueError: slug 가 비어 있거나, 모양이 맞지 않거나, 레지스트리에 없거나,
            그 줄의 한글 이름이 폴더 이름으로 쓸 수 없는 모양인 경우
    """
    name = track_name.strip()
    if not name:
        raise ValueError("매매법 이름이 비어 있습니다")

    if not VALID_TRACK_NAME.fullmatch(name):
        raise ValueError(f"매매법 이름은 영소문자와 밑줄로만 이루어져야 합니다: {name}")

    # 등록되지 않은 이름을 통과시키면 **예외 없이 새 상위 폴더가 생긴다.** 산출물이 선언된
    # 등급 밖으로 조용히 흩어지고, 그 자리는 아무도 보지 않는다
    track = track_of(name)

    # [중요] **검사는 반드시 비우기보다 먼저다.** 폴더 이름이 되는 것은 slug 가 아니라 이 값이라
    # 위 slug 검사가 여기를 덮지 못한다 — `../` 나 `/` 가 섞이면 산출물 루트 밖을 겨눠 지운다.
    # **앞뒤 공백을 먼저 턴다** — slug 는 위에서 `strip()` 을 거치는데 이 값은 레지스트리에서
    # 바로 오므로, 털지 않으면 `" 역방향"` 같은 값이 그대로 폴더 이름이 된다
    label = track.label.strip()
    if not VALID_TRACK_LABEL.fullmatch(label):
        raise ValueError(f"폴더 이름으로 쓸 수 없는 한글 이름입니다: {track.label!r} (등록처: src/verify_lab/tracks.py)")

    # **등급도 경로 한 조각이라 같은 강도로 본다.** 위 검사가 `label` 만 보면
    # `grade` 에 `..` 이 든 줄 하나로 산출물 루트 밖을 겨눠 지운다 — 테스트만으로는
    # 실행 시점을 막지 못한다
    if track.grade not in GRADES:
        raise ValueError(f"선언되지 않은 등급입니다: {track.grade!r} (가능한 값: {list(GRADES)})")

    directory = RESULTS_DIR / track.grade / label

    # 심볼릭 링크는 `rmtree` 가 거부하고, 끊어진 링크는 `exists()` 가 False 라 아래 `mkdir` 에서
    # 죽는다. 링크 자체만 지우면 둘 다 평범한 「자리 비우기」가 된다
    if directory.is_symlink():
        directory.unlink()
    elif directory.exists():
        shutil.rmtree(directory)

    # `exist_ok` 는 **등급 폴더 때문에 필요하다** — 같은 등급의 다른 매매법이 동시에 돌면
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
