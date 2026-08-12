#!/usr/bin/env python3
"""pykrx 수정주가 구간 이어붙이기 실측

`get_market_ohlcv(adjusted=True)` 는 분배락을 조정하지만 **한 번에 3,000행까지만** 돌려준다
(`docs/spec/index_extreme_events.md` §8 결론 2). 상장일부터 전 기간을 얻으려면 조회를 나눠
이어붙여야 하는데, **나눠 받은 구간들이 같은 가격 축 위에 있는지는 확인된 적이 없다.**
이 스크립트는 그것 하나를 잰다.

방법은 **시작일을 고정하고 종료일만 다르게** 여러 번 호출하는 것이다. 상한에 걸리면 서버는
종료일에서 거슬러 올라간 3,000행을 주므로, 종료일이 이른 호출일수록 과거 구간이 나온다.
이때 두 호출은 겹치는 구간을 갖게 되고, **그 구간의 값이 같은지가 곧 이어붙이기의 성립 여부다.**

**모든 호출은 한 번의 실행 안에서 이뤄져야 한다.** `reference/pykrx_실측기록.md` §0 이
수정계수는 조회 종료일이 아니라 **조회 시점** 기준으로 계산됨을 확정했으므로, 어제 받은 결과와
오늘 받은 결과를 비교하면 가격 축이 달라 판정이 성립하지 않는다.

값 비교는 **정확히 같은가**로 한다. 가격은 정수로 오므로 허용오차를 둘 이유가 없고,
"거의 같다"로 넘기면 미세하게 어긋난 축을 통과시키게 된다.

외부 서버(KRX)에 실제 요청을 보내므로 **사용자만 실행한다.**

> **로그 주의**: pykrx 는 로그인 시 **로그인 ID 를 표준 출력에 찍는다**(비밀번호는 찍지 않는다).
> 실행 로그를 공유하거나 문서에 붙일 때 그 줄을 뺀다.
"""

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from verify_lab.common_constants import RESULTS_DIR
from verify_lab.data.krx_credentials import load_krx_credentials
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 검증 #1 의 국내 대상과 그 상장일. 스펙 §2 가 지정한 값이다
DEFAULT_TICKER = "069500"
DEFAULT_START_DATE = "20021014"

# 기본 분할 종료일. 실행일이 마지막 종료일로 자동 추가되므로 기본값은 2분할을 뜻한다.
# 앞 구간이 상장일까지 닿지 못하면 이 인자에 종료일을 더해 3분할 이상으로 재실행한다
DEFAULT_END_DATES = "20141231"

DATE_FORMAT = "%Y%m%d"

# KRX 호출 간 지연 (초). 20년 넘는 구간을 훑는 무거운 질의라 간격을 둔다
CALL_INTERVAL_SECONDS = 1.0

# pykrx 가 돌려주는 한글 컬럼 중 이 스크립트가 직접 이름으로 다루는 것.
# 나머지 컬럼은 이름을 알 필요 없이 "두 응답에 공통으로 있는 컬럼"으로 비교한다
KRX_COL_CLOSE = "종가"
KRX_COL_VOLUME = "거래량"

# 표에 예시로 나열할 최대 행 수
MAX_EXAMPLE_ROWS = 5

# 산출물 폴더 접미사와 실행 이력 키
PROBE_DIR_SUFFIX = "pykrx_splice_probe"
KEY_META_PYKRX_SPLICE = "pykrx_splice_probe"

SUMMARY_COLUMNS = [("항목", 30, Align.LEFT), ("값", 76, Align.LEFT)]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="pykrx 수정주가를 구간별로 나눠 받아 이어붙일 수 있는지 실측합니다 (KRX 계정 필요).")
    parser.add_argument("--ticker", default=DEFAULT_TICKER, help=f"종목 티커 (기본값: {DEFAULT_TICKER})")
    parser.add_argument(
        "--start", default=DEFAULT_START_DATE, help=f"모든 호출의 조회 시작일 YYYYMMDD (기본값: {DEFAULT_START_DATE})"
    )
    parser.add_argument(
        "--ends",
        default=DEFAULT_END_DATES,
        help=f"분할 종료일을 쉼표로 구분해 오름차순 지정 YYYYMMDD (기본값: {DEFAULT_END_DATES}). 실행일이 마지막 종료일로 자동 추가됩니다",
    )
    return parser.parse_args()


def _kst_now() -> datetime:
    """현재 시각을 KST 로 돌려준다."""
    return datetime.now(UTC).astimezone(ZoneInfo("Asia/Seoul"))


def _validate_date(value: str, label: str) -> str:
    """YYYYMMDD 형식인지 확인하고 그대로 돌려준다.

    Args:
        value: 검사할 날짜 문자열
        label: 오류 메시지에 쓸 인자 이름

    Returns:
        검증을 통과한 날짜 문자열

    Raises:
        ValueError: 형식이 YYYYMMDD 가 아닌 경우
    """
    try:
        datetime.strptime(value, DATE_FORMAT)
    except ValueError as error:
        raise ValueError(f"{label} 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {value}") from error
    return value


def _parse_end_dates(raw: str, final_end: str) -> list[str]:
    """분할 종료일 목록을 만든다.

    실행일을 마지막 종료일로 덧붙인다. 마지막 세그먼트는 항상 현재까지 와야 하기 때문이다.

    Args:
        raw: 쉼표로 구분된 종료일 문자열
        final_end: 마지막 종료일 (실행일)

    Returns:
        오름차순으로 정렬된 종료일 목록

    Raises:
        ValueError: 형식이 잘못됐거나, 중복이 있거나, 오름차순이 아닌 경우
    """
    end_dates = [_validate_date(token.strip(), "--ends") for token in raw.split(",") if token.strip()]
    end_dates.append(final_end)

    if len(set(end_dates)) != len(end_dates):
        raise ValueError(f"조회 종료일이 중복됩니다: {end_dates}")
    if end_dates != sorted(end_dates):
        raise ValueError(f"조회 종료일은 오름차순이어야 합니다: {end_dates}")

    return end_dates


def _make_output_dir() -> Path:
    """실행 시각으로 구분되는 산출물 폴더를 만든다.

    Returns:
        생성된 폴더 경로
    """
    output_dir = RESULTS_DIR / f"{_kst_now().strftime('%Y%m%d_%H%M%S')}_{PROBE_DIR_SUFFIX}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _save(df: pd.DataFrame, output_dir: Path, name: str) -> Path:
    """조회 결과를 받는 즉시 CSV 로 남긴다.

    뒤쪽 호출이 실패해도 앞선 원자료가 남아야 재실행 없이 분석을 이어갈 수 있다.

    Args:
        df: 저장할 DataFrame (pykrx 반환값 그대로)
        output_dir: 저장 폴더
        name: 파일 이름 (확장자 제외)

    Returns:
        저장된 경로
    """
    path = output_dir / f"{name}.csv"
    df.to_csv(path, encoding="utf-8-sig")
    logger.debug(f"원자료 저장: {path} ({len(df):,}행)")
    return path


def _to_float(series: pd.Series) -> pd.Series:
    """비교 전에 `float64` 로 변환한다.

    pykrx 의 가격은 `uint32`, 거래량은 `uint64` 다. **부호 없는 정수라 뺄셈에서 언더플로우가 나서**
    작은 값에서 큰 값을 빼면 40억 근처의 거대한 양수가 된다. 비교·차분 전에 반드시 변환한다.

    Args:
        series: 변환할 시리즈

    Returns:
        `float64` 시리즈. 숫자가 아닌 값은 NaN 이 된다
    """
    return pd.to_numeric(series, errors="coerce").astype(float)


def _mismatch_mask(left: pd.Series, right: pd.Series) -> pd.Series:
    """두 시리즈가 다른 위치를 True 로 표시한다.

    양쪽 모두 결측인 자리는 다르다고 보지 않는다. `등락률` 의 첫 행처럼 원래 값이 없는 칸을
    불일치로 세면 판정이 흐려진다.

    Args:
        left: 비교 대상 1
        right: 비교 대상 2 (인덱스가 left 와 같아야 한다)

    Returns:
        불일치 여부 bool 시리즈
    """
    left_values = _to_float(left)
    right_values = _to_float(right)
    both_missing = left_values.isna() & right_values.isna()
    return (left_values != right_values) & ~both_missing


def _report_segments(table: TableLogger, segments: dict[str, pd.DataFrame], requested_start: str) -> None:
    """세그먼트별 반환 형태와 상한 도달 여부를 낸다.

    요청 시작일보다 늦게 시작하는 응답은 **행 수 상한에 걸렸다**는 뜻이다. 그 구간을 덮으려면
    더 이른 종료일로 한 번 더 호출해야 한다.

    Args:
        table: 출력에 쓸 표 로거
        segments: 종료일 → 조회 결과
        requested_start: 모든 호출에 넘긴 조회 시작일
    """
    start_date = pd.Timestamp(datetime.strptime(requested_start, DATE_FORMAT))

    for end_date, df in segments.items():
        if df.empty:
            table.print_row([f"세그먼트 ~{end_date}", "0행 — 조회 결과가 비어 있다"])
            continue

        index = pd.DatetimeIndex(df.index)
        capped = "상한 도달 (시작일이 밀렸다)" if index.min() > start_date else "요청 시작일부터 옴"
        table.print_row([f"세그먼트 ~{end_date}", f"{len(df):,}행, {index.min().date()} ~ {index.max().date()} — {capped}"])
        table.print_row(["  컬럼", ", ".join(str(column) for column in df.columns)])
        table.print_row(["  dtype", ", ".join(f"{column}={df[column].dtype}" for column in df.columns)])


def _report_overlap(table: TableLogger, older: pd.DataFrame, newer: pd.DataFrame, label: str) -> int:
    """인접한 두 세그먼트의 겹치는 구간을 컬럼별로 비교한다.

    종가만 보지 않는다. forward return 은 종가와 익일 시가를 모두 쓰므로(스펙 §4),
    종가만 맞고 시가가 어긋나면 그 결과는 쓸 수 없다.

    Args:
        table: 출력에 쓸 표 로거
        older: 종료일이 이른 세그먼트
        newer: 종료일이 늦은 세그먼트
        label: 표에 표시할 이름

    Returns:
        전체 컬럼을 합친 불일치 건수. 겹치는 구간이 없으면 -1
    """
    common_dates = older.index.intersection(newer.index)
    if len(common_dates) == 0:
        table.print_row([label, "겹치는 날이 없어 이어붙이기를 검증할 수 없다 — 종료일 간격을 좁혀 재실행"])
        return -1

    table.print_row([label, f"겹치는 날 {len(common_dates):,}일"])

    total_mismatch = 0
    for column in [column for column in older.columns if column in newer.columns]:
        mismatch = _mismatch_mask(older.loc[common_dates, column], newer.loc[common_dates, column])
        count = int(mismatch.sum())
        total_mismatch += count

        if count == 0:
            table.print_row([f"  {column}", f"일치 ({len(common_dates):,}일 전부)"])
            continue

        first_date = pd.Timestamp(common_dates[mismatch.to_numpy()][0])
        older_value = older.loc[first_date, column]
        newer_value = newer.loc[first_date, column]
        table.print_row([f"  {column}", f"불일치 {count:,}일 — 첫 사례 {first_date.date()}: {older_value} vs {newer_value}"])

    return total_mismatch


def _splice(segments: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """세그먼트들을 하나의 시계열로 이어붙인다.

    같은 날짜가 여러 세그먼트에 있으면 **종료일이 가장 늦은 조회의 값**을 남긴다.
    이어붙이기가 성립하면 어느 쪽을 남기든 값이 같으므로 결과가 달라지지 않는다.

    Args:
        segments: 종료일 오름차순으로 담긴 종료일 → 조회 결과

    Returns:
        날짜 오름차순으로 정렬되고 중복이 제거된 DataFrame

    Raises:
        ValueError: 모든 세그먼트가 비어 있는 경우
    """
    frames = [df for df in segments.values() if not df.empty]
    if not frames:
        raise ValueError("모든 세그먼트가 비어 있어 이어붙일 수 없습니다")

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index()


def _report_coverage(table: TableLogger, spliced: pd.DataFrame, reference: pd.DataFrame) -> int:
    """이어붙인 결과가 전 기간 거래일을 덮는지 확인한다.

    기준은 상장일부터 전 기간을 한 번에 주는 `get_etf_ohlcv_by_date` 의 날짜 목록이다.

    Args:
        table: 출력에 쓸 표 로거
        spliced: 이어붙인 결과
        reference: 기준이 되는 전 기간 조회 결과

    Returns:
        기준에 있는데 이어붙인 결과에 없는 날짜 수
    """
    spliced_index = pd.DatetimeIndex(spliced.index)
    reference_index = pd.DatetimeIndex(reference.index)

    table.print_row(
        ["이어붙인 결과", f"{len(spliced_index):,}행, {spliced_index.min().date()} ~ {spliced_index.max().date()}"]
    )
    table.print_row(
        ["기준 (ETF 전 기간)", f"{len(reference_index):,}행, {reference_index.min().date()} ~ {reference_index.max().date()}"]
    )

    missing = reference_index.difference(spliced_index)
    extra = spliced_index.difference(reference_index)

    table.print_row(["덮지 못한 거래일", f"{len(missing):,}일"])
    if len(missing) > 0:
        examples = ", ".join(str(date.date()) for date in missing[:MAX_EXAMPLE_ROWS])
        table.print_row(["  앞선 예시", f"{examples} … (가장 이른 날 {missing.min().date()})"])

    table.print_row(["기준에 없는 날", f"{len(extra):,}일"])
    if len(extra) > 0:
        examples = ", ".join(str(date.date()) for date in extra[:MAX_EXAMPLE_ROWS])
        table.print_row(["  앞선 예시", examples])

    return len(missing)


def _report_seams(table: TableLogger, spliced: pd.DataFrame, seam_dates: list[pd.Timestamp]) -> None:
    """이음매와 최대 일간 변동을 낸다.

    세그먼트마다 가격 축이 다르면 이어붙인 자리에서 하루 변동이 튄다. 겹치는 구간 비교가
    통과해도 이 표가 정상이어야 이어붙인 시계열을 그대로 쓸 수 있다.

    Args:
        table: 출력에 쓸 표 로거
        spliced: 이어붙인 결과
        seam_dates: 각 세그먼트가 처음 값을 제공하는 날짜 (첫 세그먼트 제외)
    """
    change = _to_float(spliced[KRX_COL_CLOSE]).pct_change() * 100

    table.print_row([f"최대 일간 변동 상위 {MAX_EXAMPLE_ROWS}", "날짜 — 변동률"])
    top = change.reindex(change.abs().nlargest(MAX_EXAMPLE_ROWS).index)
    for date, value in zip(pd.DatetimeIndex(top.index), top.to_numpy(), strict=True):
        table.print_row([f"  {date.date()}", f"{value:+.2f}%"])

    table.print_row(["이음매 날의 전일 대비", "날짜 — 변동률"])
    for seam in seam_dates:
        if seam not in change.index:
            table.print_row([f"  {seam.date()}", "이어붙인 결과에 없음"])
            continue
        table.print_row([f"  {seam.date()}", f"{float(change.loc[seam]):+.2f}%"])


def _report_volume_gap(table: TableLogger, spliced: pd.DataFrame, reference: pd.DataFrame) -> None:
    """두 함수가 같은 날에 서로 다른 거래량을 주는지 확인한다.

    가격 검증에는 영향이 없지만, 어느 함수를 수집에 쓰느냐로 저장되는 거래량이 달라진다.

    Args:
        table: 출력에 쓸 표 로거
        spliced: 이어붙인 결과
        reference: 기준이 되는 전 기간 조회 결과
    """
    if KRX_COL_VOLUME not in spliced.columns or KRX_COL_VOLUME not in reference.columns:
        table.print_row(["거래량 비교", f"{KRX_COL_VOLUME} 컬럼이 없어 확인 불가"])
        return

    common_dates = spliced.index.intersection(reference.index)
    if len(common_dates) == 0:
        table.print_row(["거래량 비교", "겹치는 날짜 없음"])
        return

    mismatch = _mismatch_mask(spliced.loc[common_dates, KRX_COL_VOLUME], reference.loc[common_dates, KRX_COL_VOLUME])
    count = int(mismatch.sum())
    table.print_row(["거래량 비교", f"겹치는 {len(common_dates):,}일 중 {count:,}일 불일치"])

    if count > 0:
        last_date = pd.Timestamp(common_dates[mismatch.to_numpy()][-1])
        spliced_value = spliced.loc[last_date, KRX_COL_VOLUME]
        reference_value = reference.loc[last_date, KRX_COL_VOLUME]
        table.print_row(["  가장 최근 사례", f"{last_date.date()}: 수정주가 조회 {spliced_value} vs ETF 조회 {reference_value}"])


@cli_exception_handler
def main() -> int:
    """실측을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    ticker = args.ticker
    start_date = _validate_date(args.start, "--start")
    today = _kst_now().strftime(DATE_FORMAT)
    end_dates = _parse_end_dates(args.ends, today)

    # 1. 자격증명을 환경 변수로 올린다. pykrx import 보다 반드시 먼저다
    load_krx_credentials()

    # 2. 여기서 import 한다. `import pykrx` 자체가 로그인을 시도하므로 모듈 최상단에 두면
    #    자격증명이 올라가기 전에 로그인이 시도된다 (설치본에서 실측 확인).
    #    최상단 import 는 순서를 구조로 보장하지 못한다 — 누군가 줄을 옮기면 조용히 깨진다
    from pykrx import stock

    output_dir = _make_output_dir()
    logger.debug(f"이어붙이기 실측 시작: {ticker}, 시작일 {start_date}, 종료일 {end_dates}")

    # 3. 종료일만 바꿔가며 수정주가를 받는다. 받는 즉시 저장해 뒤쪽 호출이 실패해도 원자료가 남게 한다.
    #    모든 호출이 한 실행 안에 있어야 수정계수 기준 시점이 같다
    segments: dict[str, pd.DataFrame] = {}
    for end_date in end_dates:
        segments[end_date] = stock.get_market_ohlcv(start_date, end_date, ticker, adjusted=True)
        _save(segments[end_date], output_dir, f"adjusted_to_{end_date}")
        time.sleep(CALL_INTERVAL_SECONDS)

    # 4. 커버리지 판정의 기준. 상장일부터 전 기간을 한 번에 주는 유일한 경로다
    reference = stock.get_etf_ohlcv_by_date(start_date, today, ticker)
    _save(reference, output_dir, "etf_ohlcv")

    spliced = _splice(segments)
    _save(spliced, output_dir, "spliced")

    # 5. 결과 표시
    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_header(f"pykrx 이어붙이기 실측 — {ticker} ({start_date} 시작, 종료일 {', '.join(end_dates)})")

    _report_segments(table, segments, start_date)

    overlap_mismatches: list[int] = []
    ordered = list(segments.items())
    for (older_end, older_df), (newer_end, newer_df) in zip(ordered, ordered[1:], strict=False):
        if older_df.empty or newer_df.empty:
            table.print_row([f"겹침 ~{older_end} vs ~{newer_end}", "한쪽이 비어 있어 비교 불가"])
            continue
        overlap_mismatches.append(_report_overlap(table, older_df, newer_df, f"겹침 ~{older_end} vs ~{newer_end}"))

    missing_count = _report_coverage(table, spliced, reference)

    seam_dates = [pd.DatetimeIndex(df.index).min() for df in list(segments.values())[1:] if not df.empty]
    _report_seams(table, spliced, seam_dates)
    _report_volume_gap(table, spliced, reference)

    table.print_row(["원자료 저장 위치", str(output_dir)])
    table.print_footer()

    save_metadata(
        KEY_META_PYKRX_SPLICE,
        {
            "ticker": ticker,
            "start_date": start_date,
            "end_dates": end_dates,
            "output_dir": str(output_dir),
            "segment_row_counts": {end_date: len(df) for end_date, df in segments.items()},
            "spliced_row_count": len(spliced),
            "reference_row_count": len(reference),
            "overlap_mismatch_counts": overlap_mismatches,
            "missing_trading_days": missing_count,
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
