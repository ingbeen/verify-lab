#!/usr/bin/env python3
"""비트코인 일별 시세 수집과 크로스체크 CLI

반감기_사이클의 두 소스를 받아 저장하고, **저장한 파일을 로더로 다시 읽어** 같은 날 종가를 대조한다.
「데이터 로드 단계에서 두 소스를 서로 비교해 크로스체크한다 — 초기 로드 때와 최신 데이터를 받을 때마다」
(2026-09-26 사용자 지시)를 이 스크립트 한 번이 지킨다.

- 주 계열: Bitstamp BTC/USD 일봉 → `storage/market/`
- 보완 계열: Coin Metrics 커뮤니티 API 지표 → `storage/series/`

**크로스체크는 값을 바꾸지 않는다** — 허용폭을 넘은 날과 거래가 없던 날을 보여 줄 뿐이다(`docs/검증/반감기_사이클/설계.md` 결정 ②).
인증키가 필요 없다. **같은 이름의 기존 파일을 덮어쓴다.** 실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.common_constants import COL_CLOSE, COL_DATE, RATE_TO_PERCENT
from verify_lab.data.bitstamp_collector import BitstampCollectionResult, collect_bitstamp_history
from verify_lab.data.coinmetrics_collector import (
    BTC_PRICE_SERIES,
    COINMETRICS_SERIES,
    CoinMetricsCollectionResult,
    collect_coinmetrics_series,
)
from verify_lab.data.crosscheck import (
    COL_DIFF_RATE,
    COL_MAX_ABS_DIFF,
    COL_MAX_DIFF_DATE,
    COL_MEDIAN_ABS_DIFF,
    COL_OVER_TOLERANCE_DAYS,
    COL_OVERLAP_DAYS,
    COL_P95_ABS_DIFF,
    COL_PRIMARY,
    COL_SECONDARY,
    COL_YEAR,
    CrosscheckResult,
    crosscheck_closes,
)
from verify_lab.data.crypto_common import load_crypto_market_csv
from verify_lab.data.loader import load_series_csv
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.formatting import Align, TableLogger
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_BTC = "btc_collect"

# 허용폭 초과 표에 보일 행 수. 전부는 실행 이력과 설계 문서가 건수로 갖는다
OVER_TOLERANCE_PREVIEW = 15

# 열 사이에 구분 칸이 없어 **오른쪽 정렬 열 뒤에 왼쪽 정렬 열을 두면 두 값이 붙는다.**
# 그래서 왼쪽 정렬 열을 앞에 모으고, 헤더가 폭을 꽉 채우지 않게 한 칸 이상 남긴다
SOURCE_COLUMNS = [
    ("소스", 26, Align.LEFT),
    ("저장 파일", 20, Align.LEFT),
    ("기간", 26, Align.LEFT),
    ("행 수", 8, Align.RIGHT),
    ("빠진 날", 9, Align.RIGHT),
    ("미완성 제외", 13, Align.RIGHT),
]

YEARLY_COLUMNS = [
    ("연도", 6, Align.LEFT),
    ("겹친 날", 8, Align.RIGHT),
    ("중앙 절대차(%)", 15, Align.RIGHT),
    ("95분위(%)", 10, Align.RIGHT),
    ("최대(%)", 9, Align.RIGHT),
    ("최대인 날", 12, Align.RIGHT),
    ("허용폭 초과", 13, Align.RIGHT),
]

OVER_TOLERANCE_COLUMNS = [
    ("날짜", 12, Align.LEFT),
    ("Bitstamp", 12, Align.RIGHT),
    ("Coin Metrics", 13, Align.RIGHT),
    ("차이(%)", 9, Align.RIGHT),
]

ZERO_VOLUME_COLUMNS = [
    ("날짜", 12, Align.LEFT),
    ("Bitstamp 종가", 14, Align.RIGHT),
]


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다. 고를 것이 없어 인자를 두지 않는다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(
        description=("Bitstamp BTC/USD 일봉과 Coin Metrics 일별 지표를 전 기간으로 받아 저장하고, " "두 소스의 같은 날 종가를 대조합니다. 값은 바꾸지 않습니다.")
    )
    return parser.parse_args()


def _percent(rate: float) -> str:
    return f"{rate * RATE_TO_PERCENT:.2f}"


def _print_sources(bitstamp: BitstampCollectionResult, coinmetrics: list[CoinMetricsCollectionResult]) -> None:
    rows: list[list[str]] = [
        [
            f"Bitstamp {bitstamp.ticker}",
            bitstamp.path.name,
            f"{bitstamp.start_date} ~ {bitstamp.end_date}",
            f"{bitstamp.row_count:,}",
            str(bitstamp.missing_day_count),
            str(bitstamp.excluded_recent_count),
        ]
    ]
    for result in coinmetrics:
        rows.append(
            [
                f"Coin Metrics {result.series_key}",
                result.path.name,
                f"{result.start_date} ~ {result.end_date}",
                f"{result.row_count:,}",
                str(result.missing_day_count),
                str(result.excluded_recent_count),
            ]
        )
    TableLogger(SOURCE_COLUMNS, logger).print_table(rows, title="수집 결과 (빠진 날은 메우지 않았다)")


def _print_crosscheck(result: CrosscheckResult) -> None:
    TableLogger(YEARLY_COLUMNS, logger).print_table(
        [
            [
                str(row[COL_YEAR]),
                f"{row[COL_OVERLAP_DAYS]:,}",
                _percent(row[COL_MEDIAN_ABS_DIFF]),
                _percent(row[COL_P95_ABS_DIFF]),
                _percent(row[COL_MAX_ABS_DIFF]),
                str(row[COL_MAX_DIFF_DATE].date()),
                str(row[COL_OVER_TOLERANCE_DAYS]),
            ]
            for _, row in result.yearly.iterrows()
        ],
        title=(
            f"크로스체크 연도별 요약 — Bitstamp ÷ Coin Metrics − 1, 허용폭 {_percent(result.tolerance)}% "
            f"(Bitstamp 에만 {result.primary_only_count}일 · Coin Metrics 에만 {result.secondary_only_count}일)"
        ),
    )

    worst = result.over_tolerance.reindex(result.over_tolerance[COL_DIFF_RATE].abs().sort_values(ascending=False).index)
    TableLogger(OVER_TOLERANCE_COLUMNS, logger).print_table(
        [
            [
                str(row[COL_DATE].date()),
                f"{row[COL_PRIMARY]:,.2f}",
                f"{row[COL_SECONDARY]:,.4f}",
                _percent(row[COL_DIFF_RATE]),
            ]
            for _, row in worst.head(OVER_TOLERANCE_PREVIEW).iterrows()
        ],
        title=f"허용폭을 넘은 날 {len(result.over_tolerance)}일 중 차이가 큰 {min(OVER_TOLERANCE_PREVIEW, len(worst))}일",
    )

    TableLogger(ZERO_VOLUME_COLUMNS, logger).print_table(
        [[str(row[COL_DATE].date()), f"{row[COL_CLOSE]:,.2f}"] for _, row in result.zero_volume.iterrows()],
        title=f"Bitstamp 에서 거래가 없던 날 {len(result.zero_volume)}일 (가격은 전일값 이월)",
    )


@cli_exception_handler
def main() -> int:
    """수집 · 저장 · 크로스체크를 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    parse_args()

    bitstamp = collect_bitstamp_history()
    coinmetrics = [collect_coinmetrics_series(series) for series in COINMETRICS_SERIES]
    _print_sources(bitstamp, coinmetrics)

    # 저장한 파일을 로더로 다시 읽어 대조한다 — 측정이 읽을 바로 그 파일을 확인하기 위해서다
    primary = load_crypto_market_csv(bitstamp.path)
    price_path = next(result.path for result in coinmetrics if result.series_key == BTC_PRICE_SERIES.key)
    secondary = load_series_csv(price_path)
    crosscheck = crosscheck_closes(primary, secondary)
    _print_crosscheck(crosscheck)

    save_metadata(
        KEY_META_BTC,
        {
            "sources": [
                {
                    "source": "bitstamp",
                    "key": bitstamp.ticker,
                    "path": str(bitstamp.path),
                    "row_count": bitstamp.row_count,
                    "start_date": str(bitstamp.start_date),
                    "end_date": str(bitstamp.end_date),
                    "missing_day_count": bitstamp.missing_day_count,
                    "excluded_recent_count": bitstamp.excluded_recent_count,
                },
                *[
                    {
                        "source": "coinmetrics",
                        "key": result.series_key,
                        "path": str(result.path),
                        "row_count": result.row_count,
                        "start_date": str(result.start_date),
                        "end_date": str(result.end_date),
                        "missing_day_count": result.missing_day_count,
                        "excluded_recent_count": result.excluded_recent_count,
                    }
                    for result in coinmetrics
                ],
            ],
            "crosscheck": {
                "tolerance": crosscheck.tolerance,
                "overlap_days": len(crosscheck.overlap),
                "over_tolerance_days": len(crosscheck.over_tolerance),
                "primary_only_days": crosscheck.primary_only_count,
                "secondary_only_days": crosscheck.secondary_only_count,
                "zero_volume_days": len(crosscheck.zero_volume),
            },
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
