#!/usr/bin/env python3
"""월말 매매의 보유 구간에 분배락·배당락이 걸리는지 실측

`.claude/rules/strategy.md` 는 **배당·분배락을 보유 구간에 실제로 걸릴 때만 재고, 걸리지
않으면 「0건 확인」만 적도록** 요구한다. 안 걸리는데 계산에 넣으면 없는 왜곡을 만들기 때문이다.

**방법은 `check_expiry_dividend.py` 와 같다** — 같은 진입·청산 날짜로 원본가와 수정주가의
수익률을 각각 계산해 뺀다. 수정주가는 배당을 되돌려 조정하므로 두 값의 차이가 곧 그 구간에
들어간 분배락의 크기다. 배율의 계단을 찾는 방법과 달리 **임계값을 정할 필요가 없고**,
이 매매가 실제로 잰 구간에만 답한다.

**차이의 부호는 방향에 따라 뜻이 다르다** (루트 `CLAUDE.md` 측정의 원칙 14).
「아래」로 걸면 원본가 성적이 **과대평가**된다 — 원본가에서 보이는 그 하락은 분배금 지급이
만든 것이라 인버스로는 못 먹는다. 「위」로 걸면 반대로 **과소평가**이며 실제로는 분배금을
현금으로 받아 보전된다.

**진입일·청산일은 `studies/month_end/schedule.py` 를 그대로 부른다** — 검증과 같은 날에
들어가지 않으면 이 실측이 다른 매매를 재게 된다 (판정식 단일화).

**지수는 대상이 아니다.** 지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없고
수정주가 파일도 없다.

**국내 수정주가는 전 기간이 없다.** pykrx 가 조회 시점 기준 최근 3,000거래일만 주므로
KODEX 200 은 2014년부터만 대조되며, **덮지 못한 구간이 몇 건인지 함께 보고한다** —
「없음」과 「확인 못 함」을 구별하지 않으면 오염이 없는 것처럼 읽힌다.

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
    RATE_TO_PERCENT,
)
from verify_lab.data.loader import load_market_csv
from verify_lab.studies.month_end.constants import (
    BASE_ENTRY_DAY,
    BASE_EXIT_OFFSET,
    COL_EXIT_DATE,
    COL_MONTH,
    DATASETS,
    Dataset,
)
from verify_lab.studies.month_end.schedule import month_entry_dates, month_exit_schedule
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_MONTH_END_DIVIDEND = "month_end_dividend_probe"

# 분배락이 "걸렸다"고 볼 차이의 하한 (%p). 두 계열의 부동소수점 차이는 1e-4 %p 수준이라
# 이보다 두 자리 위에 둔다. 국내 정수 가격의 반올림 잡음도 이 아래에 들어온다
HIT_THRESHOLD_PERCENT = 0.01

# 차이 표시 자릿수. 백분율 2자리로는 0.05%p 짜리가 뭉개진다
DIFF_DECIMALS = 4

RESULT_COLUMNS = [
    ("시장", 8, Align.LEFT),
    ("종목", 26, Align.LEFT),
    ("월", 5, Align.RIGHT),
    ("진입", 7, Align.RIGHT),
    ("대조 가능", 11, Align.RIGHT),
    ("확인 불가", 11, Align.RIGHT),
    ("걸린 건", 9, Align.RIGHT),
    ("걸린 건 평균(%p)", 18, Align.RIGHT),
    ("합(%p)", 11, Align.RIGHT),
]


def _measure(dataset: Dataset) -> list[dict[str, Any]]:
    """한 종목의 달마다 보유 구간에 들어간 분배락 크기를 잰다.

    Args:
        dataset: 시세 스키마 대상 (지수는 넘기지 않는다)

    Returns:
        달마다 한 줄씩 담은 표

    Raises:
        FileNotFoundError: 수정주가 파일이 없는 경우
    """
    raw_frame = load_market_csv(dataset.path)
    adjusted_frame = load_market_csv(MARKET_DIR / ADJUSTED_FILE_TEMPLATE.format(ticker=dataset.ticker))

    raw = raw_frame.set_index(COL_DATE)[COL_CLOSE]
    adjusted = adjusted_frame.set_index(COL_DATE)[COL_CLOSE]

    trading_days = pd.DatetimeIndex(raw_frame[COL_DATE])
    entries = month_entry_dates(trading_days, calendar_day=BASE_ENTRY_DAY)
    schedule = month_exit_schedule(trading_days, entries, exit_offset=BASE_EXIT_OFFSET)

    usable = schedule.frame[schedule.frame[COL_EXIT_DATE].notna()]

    rows: list[dict[str, Any]] = []
    for month in range(1, 13):
        cell = usable[usable[COL_MONTH].dt.month == month]

        diffs: list[float] = []
        unmeasured = 0
        for _, entry in cell.iterrows():
            entry_date, exit_date = entry[COL_DATE], entry[COL_EXIT_DATE]

            # 수정주가가 덮지 못하는 구간은 **지어내지 않고 센다.** 「없음」과 「확인 못 함」이
            # 구별되지 않으면 오염이 없는 것처럼 읽힌다
            if entry_date not in adjusted.index or exit_date not in adjusted.index:
                unmeasured += 1
                continue

            raw_rate = float(raw[exit_date]) / float(raw[entry_date]) - 1.0
            adjusted_rate = float(adjusted[exit_date]) / float(adjusted[entry_date]) - 1.0
            diffs.append((adjusted_rate - raw_rate) * RATE_TO_PERCENT)

        series = pd.Series(diffs, dtype=float)
        hit = series[series.abs() > HIT_THRESHOLD_PERCENT]

        rows.append(
            {
                "시장": dataset.market,
                "종목": dataset.label,
                "월": month,
                "진입": len(cell),
                "대조 가능": len(series),
                "확인 불가": unmeasured,
                "걸린 건": len(hit),
                "걸린 건 평균(%p)": round(float(hit.mean()), DIFF_DECIMALS) if len(hit) else 0.0,
                "합(%p)": round(float(hit.sum()), DIFF_DECIMALS) if len(hit) else 0.0,
            }
        )

    return rows


@cli_exception_handler
def main() -> int:
    """집행 가능한 종목마다 달별 분배락 영향을 재고 표로 낸다.

    Returns:
        종료 코드 (성공 0)
    """
    rows: list[dict[str, Any]] = []
    for dataset in DATASETS:
        if dataset.is_index:
            continue
        rows.extend(_measure(dataset))

    table = TableLogger(RESULT_COLUMNS, logger)
    table.print_header("보유 구간(20일 → 말일)에 들어간 분배락 — 수정주가 − 원본가 수익률")
    for row in rows:
        if row["걸린 건"] or row["확인 불가"]:
            table.print_row([str(row[name]) for name, _, _ in RESULT_COLUMNS])
    table.print_footer()

    clean = [row for row in rows if not row["걸린 건"] and not row["확인 불가"]]
    logger.debug(f"분배락이 한 건도 없고 전 구간을 대조한 칸: {len(clean)}개 (표에서 생략했습니다)")
    logger.debug("「아래」로 걸면 원본가 성적이 그만큼 과대평가돼 있습니다 — 인버스는 그만큼 오르지 않습니다")
    logger.debug("「확인 불가」는 수정주가 파일이 그 구간을 덮지 못한 것입니다. 「없음」과 다릅니다")

    save_metadata(KEY_META_MONTH_END_DIVIDEND, {"cells": rows})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
