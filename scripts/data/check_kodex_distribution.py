#!/usr/bin/env python3
"""KODEX 200 분배락일이 월물 만기일 주변에 몰려 있는지 실측

검증 #7 은 만기일 앞뒤 상대 거래일의 수익률을 잰다. 이때 **분배락이 만기일 근처에 고정돼 있으면
원본가로 잰 결과에 한 방향 편향이 들어간다** — 분배락이 신호군에만 들어가고 베이스라인에는
들어가지 않기 때문이다. 미국 QQQ 에서는 실제로 그런 구조가 확인됐다
(`docs/spec/option_expiry.md` §7.2).

국내도 같은지를 재는 것이 이 스크립트다. 방법은 **원본가와 수정주가의 종가 배율**을 보는 것이다.
수정주가는 분배락 이전 구간을 낮춰 조정하므로 배율은 분배락일에 계단처럼 내려가며,
그 계단이 생긴 날이 곧 분배락일이다.

**배율은 깨끗한 계단이 아니다.** 두 종가가 모두 정수라 매일 반올림 잡음이 실리고, 실측하면
분배락이 없는 구간에서도 배율의 고유값이 거래일 수만큼 나온다. 그래서 하루치 차분이 아니라
앞뒤 며칠의 **중앙값**을 비교해 계단을 찾고, 창이 계단을 걸치는 동안 연속으로 잡히는 날들을
한 사건으로 묶는다.

**국내 수정주가는 전 기간이 존재하지 않는다.** pykrx 는 조회 시점 기준 최근 3,000거래일만
돌려주므로(`docs/spec/index_extreme_events.md` §8 결론 2·4), 이 실측이 덮는 구간도 거기까지다.
덮지 못한 구간이 얼마인지를 함께 보고한다.

외부 서버에 요청하지 않는다. 이미 받아 둔 두 원시 시세 파일만 읽는다.
실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, MARKET_DIR
from verify_lab.data.loader import load_market_csv
from verify_lab.studies.option_expiry.constants import COL_EXPIRY_DATE, COL_OFFSET, KR_MONTHLY_EXPIRY, MAX_OFFSET
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.offsets import expiry_offsets
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 검증 #7 의 국내 대상. 원본가와 수정주가가 같은 종목의 두 파일로 나뉘어 있다
DEFAULT_TICKER = "069500"

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_KODEX_DISTRIBUTION = "kodex_distribution_probe"

# 계단을 판정할 때 앞뒤로 볼 거래일 수. 중앙값을 내는 창이며, 분배 간격(분기)보다 훨씬 짧아야
# 두 분배락이 한 창에 함께 들어오지 않는다
STEP_WINDOW_DAYS = 5

# 반올림 잡음 대비 안전 계수. 두 파일 모두 정수 가격이라 배율에 반올림 오차가 있고 그 크기는
# 가격에 반비례한다. 고정 역치를 쓰면 가격이 낮던 과거 구간에서 잡음을 분배락으로 잡는다.
# 그래서 역치를 상수로 두지 않고 그날의 가격에서 계산하며, 이 계수만큼 여유를 둔다
ROUNDING_SAFETY_FACTOR = 3.0

# 분배락 표의 컬럼명
COL_DISTRIBUTION_RATE = "distribution_rate"

# 분배율 표시 자릿수. 백분율이지만 반올림 규칙표의 2자리로는 작은 분배가 0.00 으로 뭉개진다
DISTRIBUTION_RATE_DECIMALS = 4

# 요약 표의 컬럼 정의 (컬럼명, 폭, 정렬)
SUMMARY_COLUMNS = [("항목", 28, Align.LEFT), ("값", 66, Align.LEFT)]

# 분배락 목록 표의 컬럼 정의
DISTRIBUTION_COLUMNS = [
    ("분배락일", 12, Align.LEFT),
    ("분배율(%)", 11, Align.RIGHT),
    ("그달 만기일", 13, Align.LEFT),
    ("상대 거래일", 12, Align.RIGHT),
]

# offset 분포 표의 컬럼 정의
OFFSET_COLUMNS = [("상대 거래일", 12, Align.RIGHT), ("건수", 6, Align.RIGHT), ("분배율 합(%)", 14, Align.RIGHT)]

# 만기 창 밖을 나타내는 표시 문구
DISPLAY_OUTSIDE_WINDOW = "창 밖"


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="KODEX 200 분배락일이 만기일 주변에 몰려 있는지 실측합니다.")
    parser.add_argument(
        "--ticker",
        default=DEFAULT_TICKER,
        help=f"종목 코드 (기본값: {DEFAULT_TICKER})",
    )
    return parser.parse_args()


def _find_distribution_dates(raw: pd.DataFrame, adjusted: pd.DataFrame) -> pd.DataFrame:
    """원본가와 수정주가의 종가 배율에 계단이 생긴 날을 찾는다.

    Args:
        raw: 원본가 시세
        adjusted: 수정주가 시세

    Returns:
        분배락일과 그날의 분배율(비율)을 담은 DataFrame

    Raises:
        ValueError: 두 파일에 겹치는 거래일이 없는 경우
    """
    merged = raw.merge(adjusted, on=COL_DATE, suffixes=("_raw", "_adjusted")).sort_values(COL_DATE, ignore_index=True)
    if merged.empty:
        raise ValueError("원본가와 수정주가에 겹치는 거래일이 없습니다")

    adjusted_close = merged[f"{COL_CLOSE}_adjusted"]
    ratio = merged[f"{COL_CLOSE}_raw"] / adjusted_close

    # 1. 앞뒤 며칠의 중앙값을 비교해 계단을 찾는다. 중앙값은 정수 반올림이 만드는 ±1틱 잡음에
    #    흔들리지 않는다. 배율은 분배락에서만 내려가므로 내려간 방향만 본다
    before = ratio.rolling(STEP_WINDOW_DAYS).median().shift(1)
    after = ratio[::-1].rolling(STEP_WINDOW_DAYS).median()[::-1]
    step_drop = 1 - after / before

    # 2. 반올림 잡음의 상한. 정수 종가를 나눈 배율에는 하루 최대 0.5원어치 오차가 실린다
    noise_bound = ROUNDING_SAFETY_FACTOR * (0.5 / adjusted_close + 0.5 / adjusted_close.shift(1))
    flagged = (step_drop > noise_bound).fillna(value=False)

    if not flagged.any():
        return pd.DataFrame(
            {COL_DATE: pd.Series(dtype="datetime64[ns]"), COL_DISTRIBUTION_RATE: pd.Series(dtype="float64")}
        )

    # 3. 중앙값 창이 계단을 걸치는 동안 여러 날이 연속으로 잡힌다. 한 사건으로 묶고,
    #    그 안에서 **하루치 낙폭이 가장 큰 날**을 분배락일로 본다 — 실제로 가격이 떨어진 날이다
    daily_drop = 1 - ratio / ratio.shift(1)
    run_id = (~flagged).cumsum()

    events: list[dict[str, object]] = []
    for _, run in merged[flagged].groupby(run_id[flagged]):
        peak = daily_drop.loc[run.index].idxmax()
        events.append(
            {COL_DATE: merged.at[peak, COL_DATE], COL_DISTRIBUTION_RATE: float(step_drop.loc[run.index].max())}
        )

    return pd.DataFrame(events)


def _report_coverage(table: TableLogger, raw: pd.DataFrame, adjusted: pd.DataFrame) -> int:
    """수정주가가 덮지 못한 구간을 보고한다.

    Args:
        table: 출력 표
        raw: 원본가 시세
        adjusted: 수정주가 시세

    Returns:
        수정주가가 덮지 못한 거래일 수
    """
    raw_dates = pd.DatetimeIndex(raw[COL_DATE])
    adjusted_dates = pd.DatetimeIndex(adjusted[COL_DATE])
    uncovered = raw_dates.difference(adjusted_dates)

    table.print_row(["원본가 기간", f"{raw_dates.min().date()} ~ {raw_dates.max().date()} ({len(raw_dates):,}거래일)"])
    table.print_row(
        [
            "수정주가 기간",
            f"{adjusted_dates.min().date()} ~ {adjusted_dates.max().date()} ({len(adjusted_dates):,}거래일)",
        ]
    )
    table.print_row(["수정주가가 덮지 못한 구간", f"{len(uncovered):,}거래일 — 이 구간은 분배락을 알 수 없다"])

    return len(uncovered)


def _print_offset_distribution(annotated: pd.DataFrame) -> None:
    """분배락이 만기 기준 어느 상대 거래일에 몰려 있는지 표로 표시한다.

    Args:
        annotated: 분배락일에 offset 이 붙은 DataFrame
    """
    table = TableLogger(OFFSET_COLUMNS, logger)
    table.print_header("만기일 기준 상대 거래일 분포 (0 = 만기일 당일, 음수 = 만기 전)")

    inside = annotated[annotated[COL_OFFSET].notna()]
    grouped = inside.groupby(inside[COL_OFFSET].astype(int))
    for offset, rows in grouped:
        table.print_row(
            [
                f"{offset:+d}",
                f"{len(rows)}",
                f"{rows[COL_DISTRIBUTION_RATE].sum() * 100:.{DISTRIBUTION_RATE_DECIMALS}f}",
            ]
        )

    outside = annotated[annotated[COL_OFFSET].isna()]
    table.print_row(
        [
            DISPLAY_OUTSIDE_WINDOW,
            f"{len(outside)}",
            f"{outside[COL_DISTRIBUTION_RATE].sum() * 100:.{DISTRIBUTION_RATE_DECIMALS}f}",
        ]
    )
    table.print_footer()


@cli_exception_handler
def main() -> int:
    """실측을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    ticker = args.ticker

    raw = load_market_csv(MARKET_DIR / f"{ticker}_max.csv")
    adjusted = load_market_csv(MARKET_DIR / f"{ticker}_adjusted_max.csv")
    logger.debug(f"분배락 실측 시작: {ticker}, 원본가 {len(raw):,}행, 수정주가 {len(adjusted):,}행")

    distributions = _find_distribution_dates(raw, adjusted)

    # 만기일은 원본가 전 구간에서 산출한다. 수정주가 구간으로 자르면 그 경계의 만기 간격이
    # 실제와 달라져 offset 이 어긋난다
    trading_days = pd.DatetimeIndex(raw[COL_DATE])
    expiries = monthly_expiry_dates(trading_days, KR_MONTHLY_EXPIRY)
    assignment = expiry_offsets(trading_days, pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]), MAX_OFFSET)

    annotated = distributions.merge(assignment.frame, on=COL_DATE, how="left")
    inside = annotated[annotated[COL_OFFSET].notna()]

    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_header(f"KODEX 200 분배락 실측 — {ticker} (만기 규칙: {KR_MONTHLY_EXPIRY.label})")
    uncovered_count = _report_coverage(table, raw, adjusted)
    table.print_row(["만기일 수", f"{len(expiries):,}개"])
    table.print_row(["분배락 건수", f"{len(annotated):,}건"])
    table.print_row([f"만기 창(±{MAX_OFFSET} 거래일) 안", f"{len(inside):,}건 — 0건이면 원본가로 재도 만기 측정에 편향이 없다"])
    if len(annotated):
        table.print_row(["분배율 최대", f"{annotated[COL_DISTRIBUTION_RATE].max() * 100:.{DISTRIBUTION_RATE_DECIMALS}f}%"])
    table.print_footer()

    _print_offset_distribution(annotated)

    detail = TableLogger(DISTRIBUTION_COLUMNS, logger)
    detail.print_header("분배락일 전체 목록")
    for row in annotated.itertuples(index=False):
        offset = getattr(row, COL_OFFSET)
        expiry_date = getattr(row, COL_EXPIRY_DATE)
        detail.print_row(
            [
                str(pd.Timestamp(getattr(row, COL_DATE)).date()),
                f"{getattr(row, COL_DISTRIBUTION_RATE) * 100:.{DISTRIBUTION_RATE_DECIMALS}f}",
                DISPLAY_OUTSIDE_WINDOW if pd.isna(expiry_date) else str(pd.Timestamp(expiry_date).date()),
                DISPLAY_OUTSIDE_WINDOW if pd.isna(offset) else f"{int(offset):+d}",
            ]
        )
    detail.print_footer()

    save_metadata(
        KEY_META_KODEX_DISTRIBUTION,
        {
            "ticker": ticker,
            "raw_rows": len(raw),
            "adjusted_rows": len(adjusted),
            "uncovered_days": uncovered_count,
            "expiry_count": len(expiries),
            "distribution_count": len(annotated),
            "inside_window_count": len(inside),
            "max_offset": MAX_OFFSET,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
