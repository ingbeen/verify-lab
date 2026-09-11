#!/usr/bin/env python3
"""코스닥 월말 매매의 손절 격자 실행 CLI

검증 #10이 낸 「매월 20일 종가 매수 → 그 달 말일 종가 매도」에 손절선을 걸어
**손절이 무엇을 막았는가**를 수치로 낸다.

**12개월 × 두 방향 × (손절선 8종 + 무손절)** 을 전부 돈다. 눈에 띄는 달만 돌리면
그 선택이 손절 결과에도 그대로 실린다.

**맨몸 성적이다** — 수수료·슬리피지·세금을 넣지 않는다 (루트 `CLAUDE.md` 2026-09-06 확정).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse

from verify_lab.common_constants import RESULT_LAYER_STRATEGY
from verify_lab.report.tables import print_dataframe
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.strategy.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_MEAN,
    DISPLAY_MIN,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_RATE,
    PERIOD_ALL,
    SUMMARY_FILENAME,
    SUMMARY_FIXED_STOP_FILENAME,
    TRADES_FILENAME,
)
from verify_lab.strategy.month_end_runner import (
    DISPLAY_MONTH,
    KEY_FIXED_STOP_LEVEL,
    KEY_STOP_LEVELS,
    run_month_end_trading,
)
from verify_lab.strategy.run_summary import KEY_COST, KEY_ROW_COUNTS, KEY_RULE
from verify_lab.studies.month_end.constants import DATASETS_KOSDAQ, TRACK_NAME, Dataset
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키.
# **폴더 이름과 달리 계층을 이름에 담는다** — 메타는 한 파일 안의 평평한 사전이라
# 계층을 가를 상위 폴더가 없고, 같은 매매법의 검증 이력과 키가 겹치면 한쪽이 덮인다
KEY_META_STRATEGY = "month_end_trading"

# 그 안의 키. 나머지는 요약이 쓰는 이름을 그대로 재사용한다 — 두 벌이 되면 한쪽이 낡는다
KEY_META_DIRECTORY = "directory"
KEY_META_TICKERS = "tickers"

# **산출물 폴더 이름을 여기서 만들지 않는다.** slug 는 `studies/month_end/constants.py` 의
# `TRACK_NAME` 하나가 소유하고 계층은 `create_run_directory` 가 붙인다 — CLI 에 두면
# 같은 매매법이 측정 폴더와 매매 폴더에서 다른 이름으로 불린다.
#
# **[주의] 이 매매는 아직 코스닥 4대상뿐이다** (`DATASETS_KOSDAQ`). 검증 계층은 코스피까지
# 8대상으로 늘었지만 매매는 따라가지 않았다. slug 은 매매법당 하나라 두 계층이 `month_end` 를
# 공유하므로, **폴더 이름만 보고 대상 범위를 추측하면 안 된다** — 범위는 `summary.json` 의
# `datasets` 가 말한다

# 화면에 낼 컬럼. 전 컬럼을 내면 가로로 넘쳐 읽을 수 없다
HEADLINE_COLUMNS = [
    DISPLAY_TICKER,
    DISPLAY_MONTH,
    DISPLAY_DIRECTION,
    DISPLAY_STOP_LEVEL,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_TOTAL,
    DISPLAY_MEAN,
    DISPLAY_WIN_RATE,
    DISPLAY_MIN,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
]

# 화면에 낼 달. **산출물에는 12개월이 다 있고** 화면만 좁힌다 — 검증 #10에서
# 1차 게이트를 통과한 달이라 지금 볼 것이 그쪽이다
HEADLINE_MONTHS = (4, 6, 9, 12)


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="코스닥 월말 매매(20일 매수 → 말일 매도)에 손절 격자를 걸어 성적을 냅니다.")
    parser.add_argument(
        "--ticker",
        action="append",
        help="측정할 종목 또는 지수 코드. 여러 번 줄 수 있다 (기본값: ETF 둘 + 지수 둘). " "지수는 장중 손절을 잴 수 없어 무손절 성적으로만 나온다",
    )
    return parser.parse_args()


def _selected_datasets(tickers: list[str] | None) -> tuple[Dataset, ...]:
    """인자로 고른 대상만 남긴다.

    **지수도 기본 대상에 든다.** 장중 손절은 못 걸지만 무손절 성적은 낼 수 있고,
    ETF 11년으로는 볼 수 없는 기간(코스닥 종합 30년)이 거기 있다.

    Args:
        tickers: 종목 또는 지수 코드 목록. `None` 이면 전부

    Returns:
        고른 대상 목록

    Raises:
        ValueError: 알 수 없는 코드를 지목한 경우
    """
    if not tickers:
        return DATASETS_KOSDAQ

    known = {dataset.ticker: dataset for dataset in DATASETS_KOSDAQ}
    unknown = [ticker for ticker in tickers if ticker not in known]
    if unknown:
        raise ValueError(f"알 수 없는 대상입니다: {unknown} (가능한 값: {sorted(known)})")

    return tuple(known[ticker] for ticker in tickers)


@cli_exception_handler
def main() -> int:
    """손절 격자를 돌리고 결과를 저장한 뒤 요약을 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    datasets = _selected_datasets(args.ticker)

    outputs = run_month_end_trading(datasets)

    directory = create_run_directory(TRACK_NAME, layer=RESULT_LAYER_STRATEGY)
    save_table(directory, TRADES_FILENAME, outputs.trades)
    save_table(directory, SUMMARY_FILENAME, outputs.performance)
    save_table(directory, SUMMARY_FIXED_STOP_FILENAME, outputs.performance_fixed_stop)
    save_run_summary(directory, outputs.summary)

    # 화면은 **저장한 표에서 발췌**한다 — 따로 가공하면 화면에서 본 숫자를 CSV 에서 찾지 못한다
    overall = outputs.performance[
        (outputs.performance[DISPLAY_PERIOD] == PERIOD_ALL) & (outputs.performance[DISPLAY_MONTH].isin(HEADLINE_MONTHS))
    ]
    if not overall.empty:
        print_dataframe(
            overall[HEADLINE_COLUMNS],
            logger,
            title=f"손절 격자 — 전체 구간, {', '.join(str(month) for month in HEADLINE_MONTHS)}월 (전 12개월은 CSV 에)",
        )

    logger.debug(f"산출물 저장 위치: {directory}")

    # **요약의 키를 문자열로 되짚지 않는다.** runner 가 키를 바꾸면 실행 시점에야 터진다
    rule: dict[str, object] = outputs.summary[KEY_RULE]
    save_metadata(
        KEY_META_STRATEGY,
        {
            KEY_META_DIRECTORY: str(directory),
            KEY_META_TICKERS: [dataset.ticker for dataset in datasets],
            KEY_STOP_LEVELS: rule[KEY_STOP_LEVELS],
            KEY_FIXED_STOP_LEVEL: rule[KEY_FIXED_STOP_LEVEL],
            KEY_COST: outputs.summary[KEY_COST],
            KEY_ROW_COUNTS: outputs.summary[KEY_ROW_COUNTS],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
