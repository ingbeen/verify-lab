#!/usr/bin/env python3
"""옵션 만기일 매매의 보유 구간에 배당락·분배락이 걸리는지 실측

`.claude/rules/strategy.md` 는 **배당·분배락을 보유 구간에 실제로 걸릴 때만 재고, 걸리지
않으면 「0건 확인」만 적도록** 요구한다. 안 걸리는데 계산에 넣으면 없는 왜곡을 만들기 때문이다.

**방법은 같은 진입·청산 날짜로 원본가와 수정주가의 수익률을 각각 계산해 빼는 것이다.**
수정주가는 배당을 되돌려 조정하므로, 두 값의 차이가 곧 그 구간에 들어간 배당락의 크기다.
`check_kodex_distribution.py` 처럼 배율의 계단을 찾는 방법과 달리 **임계값을 정할 필요가 없고**,
이 매매가 실제로 잰 구간에만 답한다.

**차이의 부호는 방향에 따라 뜻이 다르다** (루트 `CLAUDE.md` 측정의 원칙 14).
「아래」 칸에서 차이가 양수면 원본가 성적이 **과대평가**돼 있다는 뜻이다 — 원본가에서 보이는
그 하락은 배당락이 만든 것이라 인버스로도 공매도로도 못 먹는다. 「위」 칸이면 반대로
**과소평가**이며 실제로는 배당을 받아 보전된다.

**국내 수정주가는 전 기간이 없다.** pykrx 가 조회 시점 기준 최근 3,000거래일만 주므로
KODEX 200 은 2014년부터만 대조되며, 덮지 못한 구간이 몇 건인지 함께 보고한다.

외부 서버에 요청하지 않는다. 이미 받아 둔 원본가·수정주가 파일만 읽는다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

from typing import Any

import pandas as pd

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    RATE_TO_PERCENT,
)
from verify_lab.data.loader import load_market_csv
from verify_lab.strategy.constants import (
    EXPIRY_CELLS,
    EXPIRY_DIRECTION_DOWN,
    EXPIRY_DIRECTION_UP,
    ExpiryCell,
)
from verify_lab.strategy.expiry_runner import collect_entries
from verify_lab.studies.option_expiry.constants import DATASETS, Dataset
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_EXPIRY_DIVIDEND = "expiry_dividend_probe"

# 원본가 파일 이름에서 수정주가 파일 이름을 만드는 접미사.
# **공통 템플릿에서 파생시킨다** — 문자열을 다시 적으면 규칙이 바뀔 때 여기만 낡는다
RAW_SUFFIX = MARKET_FILE_TEMPLATE.format(ticker="")
ADJUSTED_SUFFIX = ADJUSTED_FILE_TEMPLATE.format(ticker="")

# 배당락이 "걸렸다"고 볼 차이의 하한 (%p). 두 계열의 부동소수점 차이는 1e-4 %p 수준이라
# 이보다 두 자리 위에 둔다. 국내 정수 가격의 반올림 잡음도 이 아래에 들어온다
HIT_THRESHOLD_PERCENT = 0.01

# 차이 표시 자릿수. 백분율 2자리로는 0.05%p 짜리가 뭉개진다
DIFF_DECIMALS = 4

RESULT_COLUMNS = [
    ("종목", 12, Align.LEFT),
    ("만기월", 9, Align.RIGHT),
    ("방향", 8, Align.LEFT),
    ("진입", 7, Align.RIGHT),
    ("대조 가능", 11, Align.RIGHT),
    ("걸린 건", 9, Align.RIGHT),
    ("전체 평균(%p)", 15, Align.RIGHT),
    ("걸린 건 평균(%p)", 18, Align.RIGHT),
    ("최대(%p)", 11, Align.RIGHT),
]


def _dataset(key: str) -> Dataset:
    """데이터셋 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 데이터셋 이름

    Returns:
        해당 데이터셋

    Raises:
        ValueError: 그 이름의 데이터셋이 없는 경우
    """
    for dataset in DATASETS:
        if dataset.key == key:
            return dataset

    raise ValueError(f"알 수 없는 데이터셋입니다: {key}")


def _measure_cell(cell: ExpiryCell) -> dict[str, Any]:
    """한 칸의 보유 구간에 들어간 배당락 크기를 잰다.

    Args:
        cell: 대상 칸

    Returns:
        표 한 줄

    Raises:
        FileNotFoundError: 수정주가 파일이 없는 경우
    """
    dataset = _dataset(cell.dataset_key)
    entries = collect_entries(dataset, cell)

    raw = entries.frame.set_index(COL_DATE)[COL_CLOSE]
    adjusted = load_market_csv(MARKET_DIR / dataset.file_name.replace(RAW_SUFFIX, ADJUSTED_SUFFIX))
    adjusted = adjusted.set_index(COL_DATE)[COL_CLOSE]

    dates = pd.DatetimeIndex(entries.frame[COL_DATE])
    sign = -1.0 if cell.bet_down else 1.0
    diffs: list[float] = []

    for order in range(len(entries.entry_positions)):
        entry_date = dates[entries.entry_positions[order]]
        exit_date = dates[entries.exit_positions[order]]

        # 수정주가가 덮지 못하는 구간은 **지어내지 않고 건너뛴다.** 몇 건을 못 쟀는지는
        # 「대조 가능」 열이 진입 수와의 차이로 보여 준다
        if entry_date not in adjusted.index or exit_date not in adjusted.index:
            continue

        raw_rate = (float(raw[exit_date]) / float(raw[entry_date]) - 1.0) * sign
        adjusted_rate = (float(adjusted[exit_date]) / float(adjusted[entry_date]) - 1.0) * sign
        diffs.append((raw_rate - adjusted_rate) * RATE_TO_PERCENT)

    series = pd.Series(diffs, dtype=float)
    hit = series[series.abs() > HIT_THRESHOLD_PERCENT]

    return {
        "종목": dataset.ticker,
        "만기월": cell.expiry_month,
        "방향": EXPIRY_DIRECTION_DOWN if cell.bet_down else EXPIRY_DIRECTION_UP,
        "진입": len(entries.entry_positions),
        "대조 가능": len(series),
        "걸린 건": len(hit),
        "전체 평균(%p)": round(float(series.mean()), DIFF_DECIMALS) if len(series) else 0.0,
        "걸린 건 평균(%p)": round(float(hit.mean()), DIFF_DECIMALS) if len(hit) else 0.0,
        "최대(%p)": round(float(series.abs().max()), DIFF_DECIMALS) if len(series) else 0.0,
    }


@cli_exception_handler
def main() -> int:
    """대상 칸마다 배당락 영향을 재고 표로 낸다.

    Returns:
        종료 코드 (성공 0)
    """
    rows = [_measure_cell(cell) for cell in EXPIRY_CELLS]

    table = TableLogger(RESULT_COLUMNS, logger)
    table.print_header("보유 구간에 들어간 배당락 (원본가 − 수정주가 수익률)")
    for row in rows:
        table.print_row([str(row[name]) for name, _, _ in RESULT_COLUMNS])
    table.print_footer()

    logger.debug("「아래」 칸에서 차이가 양수면 원본가 성적이 그만큼 과대평가돼 있습니다")
    logger.debug("대조 가능이 진입보다 적은 칸은 수정주가 파일이 그 구간을 덮지 못한 것입니다")

    save_metadata(KEY_META_EXPIRY_DIVIDEND, {"cells": rows})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
