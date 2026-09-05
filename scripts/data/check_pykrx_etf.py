#!/usr/bin/env python3
"""pykrx ETF 사전 실측

`docs/spec/index_extreme_events.md` §9 가 요구하는 KODEX 200 미확인 항목을
**한 번의 실행으로** 확인한다. KRX 호출은 5회이며 각 호출 결과를 받는 즉시 CSV 로 남기므로,
뒤쪽 호출이 실패해도 앞선 원자료는 보존된다.

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

# 검증 #1 의 국내 대상. 상장일은 스펙 §2 가 지정한 값이다
DEFAULT_TICKER = "069500"
DEFAULT_START_DATE = "20021014"

# 비교 기준이 되는 가격지수. 분배금이 포함되지 않으므로, ETF 가 이보다 더 오른 몫이 분배금이다
KOSPI_200_INDEX_TICKER = "1028"

# KRX 호출 간 지연 (초). 24년 구간을 훑는 무거운 질의라 간격을 둔다
CALL_INTERVAL_SECONDS = 1.0

# pykrx 가 돌려주는 한글 컬럼. 정규화하지 않고 그대로 본다 — 무엇이 오는지가 실측 대상이다
KRX_COL_OPEN = "시가"
KRX_COL_HIGH = "고가"
KRX_COL_LOW = "저가"
KRX_COL_CLOSE = "종가"
KRX_COL_VOLUME = "거래량"
KRX_COL_VALUE = "거래대금"
KRX_COL_NAV = "NAV"
KRX_COL_DEVIATION = "괴리율"

KRX_PRICE_COLUMNS = [KRX_COL_OPEN, KRX_COL_HIGH, KRX_COL_LOW, KRX_COL_CLOSE]

# 산출물 폴더 접미사와 실행 이력 키
PROBE_DIR_SUFFIX = "pykrx_etf_probe"
KEY_META_PYKRX_PROBE = "pykrx_etf_probe"

SUMMARY_COLUMNS = [("항목", 26, Align.LEFT), ("값", 74, Align.LEFT)]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="pykrx 로 국내 ETF 의 데이터 성질을 실측합니다 (KRX 계정 필요).")
    parser.add_argument("--ticker", default=DEFAULT_TICKER, help=f"ETF 티커 (기본값: {DEFAULT_TICKER})")
    parser.add_argument("--start", default=DEFAULT_START_DATE, help=f"조회 시작일 YYYYMMDD (기본값: {DEFAULT_START_DATE})")
    return parser.parse_args()


def _kst_now() -> datetime:
    """현재 시각을 KST 로 돌려준다."""
    return datetime.now(UTC).astimezone(ZoneInfo("Asia/Seoul"))


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


def _report_schema(table: TableLogger, df: pd.DataFrame, label: str) -> None:
    """반환 형태(컬럼·dtype·인덱스·기간)를 표로 낸다.

    Args:
        table: 출력에 쓸 표 로거
        df: 확인할 DataFrame
        label: 표에 표시할 이름
    """
    table.print_row([f"{label} 행 수", f"{len(df):,}"])
    table.print_row([f"{label} 인덱스명", str(df.index.name)])
    table.print_row([f"{label} 인덱스 dtype", str(df.index.dtype)])
    table.print_row([f"{label} 컬럼", ", ".join(str(column) for column in df.columns)])
    table.print_row([f"{label} dtype", ", ".join(f"{column}={df[column].dtype}" for column in df.columns)])
    if len(df) > 0:
        table.print_row([f"{label} 기간", f"{df.index.min()} ~ {df.index.max()}"])


def _compare_close(table: TableLogger, left: pd.DataFrame, right: pd.DataFrame, label: str) -> None:
    """두 시계열의 종가가 겹치는 날짜에서 같은지 비교한다.

    같으면 두 소스가 같은 가격 축을 쓴다는 뜻이고, 다르면 한쪽에 수정계수가 적용됐다는 뜻이다.

    Args:
        table: 출력에 쓸 표 로거
        left: 비교 대상 1
        right: 비교 대상 2
        label: 표에 표시할 이름
    """
    common = left.index.intersection(right.index)
    if len(common) == 0:
        table.print_row([f"{label} 비교", "겹치는 날짜 없음"])
        return

    left_close = left.loc[common, KRX_COL_CLOSE].astype(float)
    right_close = right.loc[common, KRX_COL_CLOSE].astype(float)
    diff = (left_close - right_close).abs()
    mismatch = diff > 0

    table.print_row([f"{label} 겹치는 날", f"{len(common):,}일"])
    table.print_row([f"{label} 종가 불일치", f"{int(mismatch.sum()):,}일"])

    if bool(mismatch.any()):
        first_date = common[mismatch][0]
        ratio = float(left_close[first_date]) / float(right_close[first_date])
        table.print_row(
            [f"{label} 첫 불일치", f"{first_date} — {left_close[first_date]} vs {right_close[first_date]} (배율 {ratio:.6f})"]
        )


def _report_close_vs_nav(table: TableLogger, df: pd.DataFrame) -> None:
    """연도별로 종가가 NAV 에서 얼마나 떨어져 있는지 낸다.

    NAV 는 그날의 순자산가치다. 종가가 **그날의 실제 시장가**라면 둘의 차이는 괴리율 수준(수십 bp)에
    머문다. 반대로 종가가 **분배락을 반영해 과거를 낮춘 값**이라면, 과거로 갈수록 종가가 NAV 보다
    체계적으로 낮아진다. 즉 이 표의 모양이 조정 여부를 가른다.

    Args:
        table: 출력에 쓸 표 로거
        df: NAV 와 종가를 담은 ETF OHLCV
    """
    if KRX_COL_NAV not in df.columns:
        table.print_row(["종가 vs NAV", f"{KRX_COL_NAV} 컬럼이 없어 확인 불가"])
        return

    work = df[[KRX_COL_CLOSE, KRX_COL_NAV]].astype(float)
    work = work[work[KRX_COL_NAV] > 0]
    if work.empty:
        table.print_row(["종가 vs NAV", "NAV 가 모두 0 이하여서 확인 불가"])
        return

    gap_pct = (work[KRX_COL_CLOSE] / work[KRX_COL_NAV] - 1) * 100
    by_year = gap_pct.groupby(pd.DatetimeIndex(work.index).year)

    table.print_row(["종가 vs NAV (연도별 평균 %)", "아래 연도별 값 참고"])
    for year, value in by_year.mean().items():
        table.print_row([f"  {year}", f"{value:+.3f}%"])


def _report_total_return(table: TableLogger, etf: pd.DataFrame, index: pd.DataFrame) -> None:
    """ETF 와 가격지수의 누적 상승률을 비교한다.

    KOSPI 200 은 분배금이 빠진 가격지수다. ETF 종가가 분배락을 반영해 조정된 값이라면
    ETF 누적 상승률이 지수보다 **누적 분배금만큼 높게** 나온다. 둘이 거의 같으면 미조정이다.

    Args:
        table: 출력에 쓸 표 로거
        etf: ETF OHLCV
        index: 가격지수 OHLCV
    """
    common = etf.index.intersection(index.index)
    if len(common) < 2:
        table.print_row(["누적 상승률 비교", "겹치는 날짜가 부족해 확인 불가"])
        return

    etf_close = etf.loc[common, KRX_COL_CLOSE].astype(float)
    index_close = index.loc[common, KRX_COL_CLOSE].astype(float)

    etf_return = (float(etf_close.iloc[-1]) / float(etf_close.iloc[0]) - 1) * 100
    index_return = (float(index_close.iloc[-1]) / float(index_close.iloc[0]) - 1) * 100
    years = (common[-1] - common[0]).days / 365.25

    table.print_row(["비교 구간", f"{common[0]} ~ {common[-1]} ({years:.1f}년)"])
    table.print_row(["ETF 누적 상승률", f"{etf_return:+.2f}%"])
    table.print_row(["KOSPI 200 누적 상승률", f"{index_return:+.2f}%"])
    table.print_row(["차이 (ETF - 지수)", f"{etf_return - index_return:+.2f}%p"])


def _report_liquidity(table: TableLogger, df: pd.DataFrame) -> None:
    """연도별 거래량·거래대금 중앙값을 낸다.

    거래가 극히 적은 구간의 가격 변동은 실제 시장 움직임이 아닐 수 있고, 순위 축적 구간을 오염시킨다.

    Args:
        table: 출력에 쓸 표 로거
        df: ETF OHLCV
    """
    years = pd.DatetimeIndex(df.index).year
    source = pd.DataFrame({KRX_COL_VOLUME: df[KRX_COL_VOLUME].astype(float)})
    has_value = KRX_COL_VALUE in df.columns
    if has_value:
        source[KRX_COL_VALUE] = df[KRX_COL_VALUE].astype(float)

    by_year = source.groupby(years).median()

    table.print_row(["연도별 유동성 (중앙값)", "거래량 / 거래대금"])
    for year, row in by_year.iterrows():
        value_text = f"{row[KRX_COL_VALUE] / 1e8:,.1f}억" if has_value else "—"
        table.print_row([f"  {year}", f"{row[KRX_COL_VOLUME]:,.0f}주 / {value_text}"])


def _report_gaps(table: TableLogger, df: pd.DataFrame) -> None:
    """결측·거래정지로 보이는 날을 센다.

    Args:
        table: 출력에 쓸 표 로거
        df: ETF OHLCV
    """
    price_columns = [column for column in KRX_PRICE_COLUMNS if column in df.columns]
    prices = df[price_columns].astype(float)

    table.print_row(["가격 결측", f"{int(prices.isna().sum().sum()):,}건"])
    table.print_row(["거래량 0인 날", f"{int((df[KRX_COL_VOLUME].astype(float) == 0).sum()):,}일"])
    table.print_row(["가격 0 이하인 날", f"{int((prices <= 0).any(axis=1).sum()):,}일"])
    table.print_row(["중복 날짜", f"{int(df.index.duplicated().sum()):,}건"])
    table.print_row(["날짜 오름차순", str(bool(df.index.is_monotonic_increasing))])


def _print_dated_percentages(table: TableLogger, series: pd.Series) -> None:
    """날짜 인덱스를 가진 백분율 시리즈를 한 줄씩 낸다.

    Args:
        table: 출력에 쓸 표 로거
        series: 날짜 인덱스와 백분율 값을 가진 시리즈
    """
    for date, value in zip(pd.DatetimeIndex(series.index), series.to_numpy(), strict=True):
        table.print_row([f"  {date.date()}", f"{value:+.2f}%"])


def _report_extremes(table: TableLogger, df: pd.DataFrame) -> None:
    """일간 등락 상위 10을 낸다.

    국내에도 "역대급 사건이 소수"인 문제가 있는지 확인하는 자료다.

    Args:
        table: 출력에 쓸 표 로거
        df: ETF OHLCV
    """
    change = df[KRX_COL_CLOSE].astype(float).pct_change().dropna() * 100

    table.print_row(["폭등 상위 10", "날짜 — 등락률"])
    _print_dated_percentages(table, change.nlargest(10))

    table.print_row(["폭락 상위 10", "날짜 — 등락률"])
    _print_dated_percentages(table, change.nsmallest(10))


def _report_deviation(table: TableLogger, df: pd.DataFrame) -> None:
    """괴리율이 크게 벌어진 날을 낸다.

    극단적 괴리가 발생한 날이 이벤트로 잡히면, 시장 움직임이 아니라 ETF 가격 형성 문제를 재게 된다.

    Args:
        table: 출력에 쓸 표 로거
        df: 괴리율 조회 결과
    """
    if KRX_COL_DEVIATION not in df.columns:
        table.print_row(["괴리율", f"{KRX_COL_DEVIATION} 컬럼이 없어 확인 불가"])
        return

    deviation = df[KRX_COL_DEVIATION].astype(float).dropna()
    table.print_row(["괴리율 절대값 평균", f"{deviation.abs().mean():.3f}%"])
    table.print_row(["괴리율 절대값 상위 10", "날짜 — 괴리율"])
    _print_dated_percentages(table, deviation.reindex(deviation.abs().nlargest(10).index))


@cli_exception_handler
def main() -> int:
    """실측을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()

    # 1. 자격증명을 환경 변수로 올린다. pykrx import 보다 반드시 먼저다
    load_krx_credentials()

    # 2. 여기서 import 한다. `import pykrx` 자체가 로그인을 시도하므로 모듈 최상단에 두면
    #    자격증명이 올라가기 전에 로그인이 시도된다 (설치본에서 실측 확인).
    #    최상단 import 는 순서를 구조로 보장하지 못한다 — 누군가 줄을 옮기면 조용히 깨진다
    from pykrx import stock

    end_date = _kst_now().strftime("%Y%m%d")
    output_dir = _make_output_dir()
    logger.debug(f"실측 시작: {args.ticker}, {args.start} ~ {end_date}")

    # 3. KRX 조회. 받는 즉시 저장해 뒤쪽 호출이 실패해도 원자료가 남게 한다
    etf_ohlcv = stock.get_etf_ohlcv_by_date(args.start, end_date, args.ticker)
    _save(etf_ohlcv, output_dir, "etf_ohlcv")
    time.sleep(CALL_INTERVAL_SECONDS)

    deviation = stock.get_etf_price_deviation(args.start, end_date, args.ticker)
    _save(deviation, output_dir, "etf_price_deviation")
    time.sleep(CALL_INTERVAL_SECONDS)

    index_ohlcv = stock.get_index_ohlcv_by_date(args.start, end_date, KOSPI_200_INDEX_TICKER)
    _save(index_ohlcv, output_dir, "kospi200_index_ohlcv")
    time.sleep(CALL_INTERVAL_SECONDS)

    # 개별종목용 함수가 ETF 티커에도 통하는지 확인한다. 통한다면 수정 종가를 직접 얻을 수 있다
    market_adjusted = stock.get_market_ohlcv(args.start, end_date, args.ticker, adjusted=True)
    _save(market_adjusted, output_dir, "market_ohlcv_adjusted")
    time.sleep(CALL_INTERVAL_SECONDS)

    market_raw = stock.get_market_ohlcv(args.start, end_date, args.ticker, adjusted=False)
    _save(market_raw, output_dir, "market_ohlcv_raw")

    # 4. 결과 표시
    table = TableLogger(SUMMARY_COLUMNS, logger)
    table.print_header(f"pykrx ETF 실측 — {args.ticker} ({args.start} ~ {end_date})")

    _report_schema(table, etf_ohlcv, "get_etf_ohlcv_by_date")
    _report_schema(table, market_adjusted, "get_market_ohlcv(adj=True)")
    _report_schema(table, market_raw, "get_market_ohlcv(adj=False)")

    _compare_close(table, market_adjusted, market_raw, "수정 vs 원본")
    _compare_close(table, etf_ohlcv, market_raw, "ETF함수 vs 원본")

    _report_close_vs_nav(table, etf_ohlcv)
    _report_total_return(table, etf_ohlcv, index_ohlcv)
    _report_liquidity(table, etf_ohlcv)
    _report_gaps(table, etf_ohlcv)
    _report_extremes(table, etf_ohlcv)
    _report_deviation(table, deviation)

    table.print_row(["원자료 저장 위치", str(output_dir)])
    table.print_footer()

    save_metadata(
        KEY_META_PYKRX_PROBE,
        {
            "ticker": args.ticker,
            "start_date": args.start,
            "end_date": end_date,
            "output_dir": str(output_dir),
            "etf_row_count": len(etf_ohlcv),
            "market_adjusted_row_count": len(market_adjusted),
            "market_raw_row_count": len(market_raw),
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
