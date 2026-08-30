"""검증 산출물 저장

산출물은 **덮어쓰지 않고 실행 시각으로 구분한다.** 같은 검증을 파라미터만 바꿔 여러 번 돌리는 것이
이 프로젝트의 전제이므로, 덮어쓰면 직전 실행과 무엇이 달랐는지 되짚을 수 없다.

폴더 생성과 저장을 이 계층이 소유한다. 검증 스크립트마다 같은 코드를 두면 경로 규칙이 조용히
갈라지고, 나중에 그 결과들이 같은 검증의 산출물인지 알 수 없게 된다.
"""

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from verify_lab.common_constants import KST, RESULTS_DIR
from verify_lab.report.constants import CSV_ENCODING, RUN_SUMMARY_FILENAME
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 결과 폴더 이름의 시각 부분. 실행 시각은 KST 기준이다
RUN_DIRECTORY_TIME_FORMAT = "%Y%m%d_%H%M%S"


def create_run_directory(study_name: str) -> Path:
    """`storage/results/<실행시각>_<검증명>/` 을 만든다.

    Args:
        study_name: 검증명. 폴더 이름 뒤에 붙어 무엇의 결과인지 알려준다

    Returns:
        만들어진 폴더 경로

    Raises:
        ValueError: 검증명이 비어 있는 경우
    """
    name = study_name.strip()
    if not name:
        raise ValueError("검증명이 비어 있습니다")

    stamp = datetime.now(KST).strftime(RUN_DIRECTORY_TIME_FORMAT)
    directory = RESULTS_DIR / f"{stamp}_{name}"
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
