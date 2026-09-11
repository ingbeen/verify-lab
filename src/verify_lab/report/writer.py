"""검증 산출물 저장

산출물은 **덮어쓰지 않고 실행 시각으로 구분한다.** 같은 검증을 파라미터만 바꿔 여러 번 돌리는 것이
이 프로젝트의 전제이므로, 덮어쓰면 직전 실행과 무엇이 달랐는지 되짚을 수 없다.

폴더 생성과 저장을 이 계층이 소유한다. 검증 스크립트마다 같은 코드를 두면 경로 규칙이 조용히
갈라지고, 나중에 그 결과들이 같은 검증의 산출물인지 알 수 없게 된다. **실제로 갈라졌다** —
실측 스크립트 둘이 폴더 이름을 직접 조립하고 있어 계층 폴더를 도입할 때 그 둘만 옛 자리에
남을 상태였다.
"""

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from verify_lab.common_constants import KST, RESULT_LAYERS, RESULTS_DIR
from verify_lab.report.constants import CSV_ENCODING, RUN_SUMMARY_FILENAME
from verify_lab.utils.logger import get_logger
from verify_lab.utils.result_citations import TRACK_NAME_PATTERN

logger = get_logger(__name__)

# 결과 폴더 이름의 시각 부분. 실행 시각은 KST 기준이다
RUN_DIRECTORY_TIME_FORMAT = "%Y%m%d_%H%M%S"

# 폴더 이름에 쓸 수 있는 매매법 이름. **모양의 정의처는 인용 스캐너 하나다** —
# 거기서 못 찾는 이름으로 폴더를 만들면 문서가 인용해도 「없는 것」이 되고 정리 후보로 올라간다
VALID_TRACK_NAME = re.compile(rf"^{TRACK_NAME_PATTERN}$")


def create_run_directory(track_name: str, *, layer: str) -> Path:
    """`storage/results/<계층>/<실행시각>_<매매법>/` 을 만든다.

    **계층은 경로가 말하고 폴더 이름에는 넣지 않는다.** 매매법 이름이 측정과 매매에서 같아야
    한다는 것이 이 저장소의 규약이므로(목표 1), 둘을 가르는 것은 상위 폴더뿐이다. 이름에
    접미사를 또 붙이면 중복이고, 전에는 그 접미사가 계층마다 달라 같은 매매법이 다른 이름으로
    불렸다 (`index_extreme` 과 `reverse_trading`).

    Args:
        track_name: 매매법 이름(slug). `studies/<slug>/constants.py` 의 `TRACK_NAME` 을 넘긴다
        layer: 산출물 계층. `common_constants.RESULT_LAYERS` 의 값 하나여야 한다

    Returns:
        만들어진 폴더 경로

    Raises:
        ValueError: 매매법 이름이 비어 있거나 모양이 맞지 않거나, 선언되지 않은 계층인 경우
    """
    name = track_name.strip()
    if not name:
        raise ValueError("매매법 이름이 비어 있습니다")

    # **인용 스캐너가 못 찾는 이름을 막는다.** 대문자나 숫자가 섞이면 폴더는 멀쩡히 생기지만
    # 결과 문서가 그 폴더를 인용해도 인용으로 세지 않아, 정리 도구가 근거물을 삭제 후보로 낸다
    if not VALID_TRACK_NAME.match(name):
        raise ValueError(f"매매법 이름은 영소문자와 밑줄로만 이루어져야 합니다 (인용 판정이 못 찾습니다): {name}")

    # 오타를 통과시키면 **예외 없이 새 상위 폴더가 생긴다.** 그 폴더는 인용 판정기의 탐색
    # 대상이 아니라 산출물이 조용히 시야에서 사라지고, 정리 도구도 보지 못한다
    if layer not in RESULT_LAYERS:
        raise ValueError(f"알 수 없는 산출물 계층입니다: {layer} (가능한 값: {list(RESULT_LAYERS)})")

    stamp = datetime.now(KST).strftime(RUN_DIRECTORY_TIME_FORMAT)
    directory = RESULTS_DIR / layer / f"{stamp}_{name}"
    directory.mkdir(parents=True, exist_ok=True)
    logger.debug(f"결과 폴더 생성: {directory}")

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


def save_run_summary(directory: Path, payload: Mapping[str, Any]) -> Path:
    """실행 파라미터와 핵심 통계를 JSON 으로 남긴다.

    남기지 않으면 산출물만 보고 어떤 설정의 결과인지 재구성할 수 없다.
    난수를 쓴 계산은 **시드가 여기 남아야 재현된다.**

    Args:
        directory: 저장할 폴더
        payload: 실행 정보

    Returns:
        저장된 파일 경로
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / RUN_SUMMARY_FILENAME

    with path.open("w", encoding="utf-8") as file:
        json.dump(dict(payload), file, indent=2, ensure_ascii=False)

    logger.debug(f"실행 정보 저장: {path}")

    return path
