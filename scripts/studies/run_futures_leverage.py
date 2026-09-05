#!/usr/bin/env python3
"""검증 #9 실행 CLI — 선물 대 레버리지 ETF

같은 자기자본·같은 목표 배수를 **① 레버리지 ETF ② 선물 매일 리밸런싱 ③ 선물 월 1회
리밸런싱** 세 방식으로 굴렸을 때 어느 쪽이 싼지를 잰다.

**인자는 지수로 좁히는 것 하나뿐이다.** 배수·격자·리밸런싱 주기·롤 규칙은 상수로 고정돼 있고
인자로 열지 않는다 — 노브가 되면 결과를 보고 고르게 되며 그것은 측정이 아니라 과최적화다
(루트 `CLAUDE.md` 측정의 원칙 1).

실행 명령어는 `docs/COMMANDS.md` 를 참고한다.
"""

import argparse
from pathlib import Path

import pandas as pd

from verify_lab.report.constants import DISPLAY_HORIZON, DISPLAY_SAMPLE_COUNT
from verify_lab.report.tables import print_dataframe, to_display_columns
from verify_lab.report.writer import create_run_directory, save_run_summary, save_table
from verify_lab.studies.futures_leverage.constants import (
    BREAKEVEN_FILENAME,
    COMPARISON_FILENAME,
    DECOMPOSITION_FILENAME,
    DISPLAY_ACTUAL_MULTIPLE,
    DISPLAY_ADJUSTMENT_FACTOR,
    DISPLAY_BREAKEVEN_HORIZON,
    DISPLAY_CONTRACT_NOTIONAL,
    DISPLAY_DECISION_DATE,
    DISPLAY_DIVIDEND_ADJUSTMENT,
    DISPLAY_END_DATE,
    DISPLAY_EQUITY_SIZE,
    DISPLAY_EXECUTABLE,
    DISPLAY_EXECUTION_DATE,
    DISPLAY_HOLD_ERROR,
    DISPLAY_INDEX_NAME,
    DISPLAY_INTEGER_CONTRACTS,
    DISPLAY_INTEREST,
    DISPLAY_INTEREST_GAIN,
    DISPLAY_JUDGEABLE,
    DISPLAY_METHOD,
    DISPLAY_MULTIPLE,
    DISPLAY_NEAR_CONTRACT,
    DISPLAY_NEAR_OPEN_INTEREST,
    DISPLAY_NEXT_CONTRACT,
    DISPLAY_NEXT_OPEN_INTEREST,
    DISPLAY_NON_OVERLAPPING,
    DISPLAY_REBALANCE_ERROR,
    DISPLAY_RESIDUAL,
    DISPLAY_ROLL_COST,
    DISPLAY_ROLL_RULE,
    DISPLAY_START_DATE,
    DISPLAY_TARGET_MULTIPLE,
    DISPLAY_TARGET_TICKER,
    DISPLAY_WIPEOUT_DATE,
    INTEGER_CONTRACTS_FILENAME,
    LEVERAGE_DRIFT_FILENAME,
    METHOD_ETF,
    METHOD_FUTURES_DAILY,
    METHOD_FUTURES_HOLD,
    METHOD_FUTURES_MONTHLY,
    PAIRS,
    ROLL_EVENTS_FILENAME,
    STUDY_NAME,
    WIPEOUTS_FILENAME,
)
from verify_lab.studies.futures_leverage.runner import StudyOutputs, run_study
from verify_lab.utils.cli_helpers import cli_exception_handler
from verify_lab.utils.logger import get_logger
from verify_lab.utils.meta_manager import save_metadata

logger = get_logger(__name__)

# 실행 이력을 쌓는 meta.json 의 최상위 키
KEY_META_FUTURES_LEVERAGE_STUDY = "futures_leverage_study"

# 시작일 원자료 파일명. 짝마다 하나씩 나온다
WINDOWS_FILENAME_TEMPLATE = "windows_{pair}.csv"

# 화면에 먼저 띄울 보유 기간 (거래일). 전 격자를 찍으면 화면을 넘긴다
SCREEN_HORIZON = 252

# ============================================================
# 산출물 헤더 — 영문 계산 컬럼을 한글 레이블로 바꾼다
#
# **`DISPLAY_*` 를 정의만 하고 rename 에 연결하지 않으면 규칙을 지킨 것이 아니다.**
# 공통 컬럼(구간·표본·제외)은 `report/constants.py` 의 것을 재사용해
# 검증마다 다른 말을 쓰지 않게 한다
# ============================================================

# 여러 표가 함께 쓰는 식별 컬럼
COMMON_LABELS = {
    "IndexName": DISPLAY_INDEX_NAME,
    "TargetTicker": DISPLAY_TARGET_TICKER,
    "Multiple": DISPLAY_MULTIPLE,
    "RollRule": DISPLAY_ROLL_RULE,
    "Horizon": DISPLAY_HORIZON,
}

COMPARISON_LABELS = {
    **COMMON_LABELS,
    "Method": DISPLAY_METHOD,
    "Interest": DISPLAY_INTEREST,
    "StartDate": DISPLAY_START_DATE,
    "EndDate": DISPLAY_END_DATE,
    "SampleCount": DISPLAY_SAMPLE_COUNT,
    "NonOverlapping": DISPLAY_NON_OVERLAPPING,
    "MeanReturn": "평균 수익률(%)",
    "MedianReturn": "중앙 수익률(%)",
    "Judgeable": DISPLAY_JUDGEABLE,
}
COMPARISON_PERCENTS = ("MeanReturn", "MedianReturn")

DECOMPOSITION_LABELS = {
    **COMMON_LABELS,
    "SampleCount": DISPLAY_SAMPLE_COUNT,
    "NonOverlapping": DISPLAY_NON_OVERLAPPING,
    "RollCost": DISPLAY_ROLL_COST,
    "RebalanceError": DISPLAY_REBALANCE_ERROR,
    "HoldError": DISPLAY_HOLD_ERROR,
    "InterestGain": DISPLAY_INTEREST_GAIN,
    "Residual": DISPLAY_RESIDUAL,
    "FuturesMinusEtf": "선물 − ETF(%p)",
    "HoldMinusEtf": "선물 그대로 − ETF(%p)",
    "DividendAdjustment": DISPLAY_DIVIDEND_ADJUSTMENT,
}
DECOMPOSITION_PERCENTS = (
    "RollCost",
    "RebalanceError",
    "HoldError",
    "InterestGain",
    "Residual",
    "FuturesMinusEtf",
    "HoldMinusEtf",
    "DividendAdjustment",
)

ROLL_EVENT_LABELS = {
    "IndexName": DISPLAY_INDEX_NAME,
    "RollRule": DISPLAY_ROLL_RULE,
    "DecisionDate": DISPLAY_DECISION_DATE,
    "ExecutionDate": DISPLAY_EXECUTION_DATE,
    "FromContract": DISPLAY_NEAR_CONTRACT,
    "FromName": "근월물 이름",
    "ToContract": DISPLAY_NEXT_CONTRACT,
    "ToName": "차월물 이름",
    "AdjustmentFactor": DISPLAY_ADJUSTMENT_FACTOR,
    "FromOpenInterest": DISPLAY_NEAR_OPEN_INTEREST,
    "ToOpenInterest": DISPLAY_NEXT_OPEN_INTEREST,
    "Fallback": "만기가 강제한 롤",
}

BREAKEVEN_LABELS = {
    "IndexName": DISPLAY_INDEX_NAME,
    "TargetTicker": DISPLAY_TARGET_TICKER,
    "Multiple": DISPLAY_MULTIPLE,
    "Method": DISPLAY_METHOD,
    "RollRule": DISPLAY_ROLL_RULE,
    "BreakevenHorizon": DISPLAY_BREAKEVEN_HORIZON,
    "AheadHorizonCount": "선물이 앞선 구간 수",
    "TestedHorizonCount": "잰 구간 수",
}

LEVERAGE_DRIFT_LABELS = {
    **COMMON_LABELS,
    "MaxEffectiveLeverageDaily": "매일 리밸런싱 최대 유효 레버리지",
    "MaxEffectiveLeverageMonthly": "월 1회 최대 유효 레버리지",
}

WIPEOUT_LABELS = {
    **COMMON_LABELS,
    "Method": DISPLAY_METHOD,
    "WipeoutCount": "자기자본 소진 구간 수",
    "WindowCount": "잰 구간 수",
    "FirstWipeoutDate": DISPLAY_WIPEOUT_DATE,
}

WINDOW_LABELS = {
    "Date": DISPLAY_START_DATE,
    "Horizon": DISPLAY_HORIZON,
    "Period": "시기",
    METHOD_ETF: f"{METHOD_ETF}(%)",
    METHOD_FUTURES_DAILY: f"{METHOD_FUTURES_DAILY}(%)",
    METHOD_FUTURES_MONTHLY: f"{METHOD_FUTURES_MONTHLY}(%)",
    METHOD_FUTURES_HOLD: f"{METHOD_FUTURES_HOLD}(%)",
    "ExcludedReason": "제외 사유",
}
WINDOW_PERCENTS = (METHOD_ETF, METHOD_FUTURES_DAILY, METHOD_FUTURES_MONTHLY, METHOD_FUTURES_HOLD)

# 정수 계약 대조표. **본선과 달리 자기자본 규모가 결과를 만든다** —
# 계약 하나를 살 수 있는지가 규모에 달렸기 때문이다
INTEGER_CONTRACT_LABELS = {
    "IndexName": DISPLAY_INDEX_NAME,
    "TargetTicker": DISPLAY_TARGET_TICKER,
    "Multiple": DISPLAY_TARGET_MULTIPLE,
    "AsOfDate": "기준일",
    "Price": "정산가",
    "ContractMultiplier": "거래승수",
    "Notional": DISPLAY_CONTRACT_NOTIONAL,
    "EquitySize": DISPLAY_EQUITY_SIZE,
    "IntegerContracts": DISPLAY_INTEGER_CONTRACTS,
    "ActualMultiple": DISPLAY_ACTUAL_MULTIPLE,
    "Executable": DISPLAY_EXECUTABLE,
    "ExcludedReason": "제외 사유",
}


def parse_args() -> argparse.Namespace:
    """명령행 인자를 파싱한다.

    Returns:
        파싱된 인자
    """
    parser = argparse.ArgumentParser(description="선물과 레버리지 ETF 중 어느 쪽이 레버리지를 싸게 구현하는지 잽니다.")
    parser.add_argument(
        "--index",
        default=None,
        choices=sorted({pair.index_name for pair in PAIRS}),
        help="지수로 좁힌다 (기본값: 전부)",
    )
    return parser.parse_args()


def _display(table: pd.DataFrame, labels: dict[str, str], percent_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    """저장 직전에 헤더를 한글로 바꾸고 비율을 백분율로 맞춘다.

    사전에 없는 컬럼이 하나라도 있으면 `to_display_columns` 가 예외를 던진다 —
    컬럼을 새로 만들고 한글 이름을 빠뜨리면 영문 토큰이 그대로 사용자에게 나간다.

    Args:
        table: 저장할 표 (영문 헤더)
        labels: 영문 → 한글 사전
        percent_columns: 비율(0~1)로 들어와 백분율로 내보낼 컬럼

    Returns:
        헤더가 한글이고 단위가 맞춰진 표
    """
    return to_display_columns(table, labels, percent_columns=percent_columns)


def _save_outputs(outputs: StudyOutputs) -> str:
    """산출물을 결과 폴더에 저장하고 폴더 경로를 돌려준다.

    **CSV 는 사용자가 여는 파일이라 헤더가 한글이어야 한다.** 영문 토큰이 그대로 나가면
    무슨 값인지 알 수 없다 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).

    Args:
        outputs: 검증 산출물

    Returns:
        결과 폴더 경로 문자열
    """
    directory = create_run_directory(STUDY_NAME)

    save_table(directory, COMPARISON_FILENAME, _display(outputs.comparison, COMPARISON_LABELS, COMPARISON_PERCENTS))
    save_table(
        directory, DECOMPOSITION_FILENAME, _display(outputs.decomposition, DECOMPOSITION_LABELS, DECOMPOSITION_PERCENTS)
    )
    save_table(directory, ROLL_EVENTS_FILENAME, _display(outputs.roll_events, ROLL_EVENT_LABELS))
    save_table(directory, BREAKEVEN_FILENAME, _display(outputs.breakeven, BREAKEVEN_LABELS))
    save_table(directory, LEVERAGE_DRIFT_FILENAME, _display(outputs.leverage_drift, LEVERAGE_DRIFT_LABELS))
    save_table(directory, WIPEOUTS_FILENAME, _display(outputs.wipeouts, WIPEOUT_LABELS))
    save_table(directory, INTEGER_CONTRACTS_FILENAME, _display(outputs.integer_contracts, INTEGER_CONTRACT_LABELS))

    for pair_name, windows in outputs.windows_by_pair.items():
        save_table(
            directory,
            WINDOWS_FILENAME_TEMPLATE.format(pair=pair_name),
            _display(windows, WINDOW_LABELS, WINDOW_PERCENTS),
        )

    return str(directory)


@cli_exception_handler
def main() -> int:
    """검증을 실행하고 결과를 표로 표시한다.

    Returns:
        종료 코드 (성공 0)
    """
    args = parse_args()
    outputs = run_study(index_filter=args.index)

    directory = _save_outputs(outputs)
    summary = {
        "index_filter": args.index,
        "pair_count": outputs.pair_count,
        "skipped_pairs": [{"ticker": ticker, "reason": reason} for ticker, reason in outputs.skipped_pairs],
        "comparison_rows": len(outputs.comparison),
        "decomposition_rows": len(outputs.decomposition),
        "roll_event_rows": len(outputs.roll_events),
        "breakeven_rows": len(outputs.breakeven),
        "wipeout_window_total": int(outputs.wipeouts["WipeoutCount"].sum()),
        "integer_contract_rows": len(outputs.integer_contracts),
        "window_files": sorted(outputs.windows_by_pair),
    }
    # **결과 폴더 안에도 요약을 남긴다.** 실행 이력(`meta.json`)은 최근 N개만 순환 저장하므로
    # 오래된 실행은 그 폴더만 남고 「무슨 조건으로 돌렸는지」를 잃는다
    save_run_summary(Path(directory), summary)

    screen = outputs.comparison[outputs.comparison["Horizon"] == SCREEN_HORIZON]
    if not screen.empty:
        print_dataframe(
            _display(screen, COMPARISON_LABELS, COMPARISON_PERCENTS),
            logger,
            title=f"보유 {SCREEN_HORIZON}거래일 — 방식별 성적",
        )

    if not outputs.breakeven.empty:
        print_dataframe(_display(outputs.breakeven, BREAKEVEN_LABELS), logger, title="선물이 앞서기 시작하는 보유 기간")

    if not outputs.integer_contracts.empty:
        print_dataframe(
            _display(outputs.integer_contracts, INTEGER_CONTRACT_LABELS),
            logger,
            title="정수 계약 대조 — 자기자본 규모별 실제 배수",
        )

    for ticker, reason in outputs.skipped_pairs:
        logger.warning(f"건너뛴 짝 - {ticker}: {reason}")

    save_metadata(KEY_META_FUTURES_LEVERAGE_STUDY, {"directory": directory, **summary})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
