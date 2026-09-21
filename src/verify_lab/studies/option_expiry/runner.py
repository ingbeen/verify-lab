"""검증 #7 실행 — 확정 칸의 «해석 재료»를 한 장으로 조립한다

이 모듈은 **계산 규칙을 새로 만들지 않는다.** 만기일 달력(`studies`), forward return·통계·
배당락(`measure`)이 이미 있으므로, 하는 일은 그것을 조합해 돌리고 사람이 읽을 형태로 쌓는 것이다.

**산출물은 `측정.csv` 한 장이다** (2026-09-21). 성적표가 「걸 만한가」에 답한다면 이 표는
**「그 값을 어떻게 읽나」**에 답한다 — 중앙값(측정의 원칙 4) · 평균-비율 어긋남(원칙 13) ·
기준선 · 우연확률 · 배당락이며, **성적표에는 그중 어느 것도 없다.**
무엇을 없앴고 왜인지는 `constants.OUTPUT_FILES` 의 주석이 표로 갖는다.

[중요] **값은 1배 롱 기준 그대로 담는다.** 「아래」 칸이라고 부호를 뒤집지 않는다 — 뒤집으면
`기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 **이름이 거짓이 된다.** `방향` 컬럼은
어느 쪽으로 거는지를 표시만 하고, 그래서 **성적표의 평균과 이 표의 평균은 부호가 다를 수 있다** —
대조 대상이 아니다.

**가격 기준은 원본가 하나다.** 사용자가 증권앱·차트에서 보는 가격이 곧 신호를 판정하고 주문을
거는 가격이기 때문이다 (루트 `CLAUDE.md` 측정의 원칙 14). **배당락을 잴 때만 수정주가를
함께 읽으며**, 그것은 원본가로 재서 생기는 왜곡의 크기를 보고하기 위해서다.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
    COL_CLOSE,
    COL_DATE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
)
from verify_lab.data.loader import load_market_csv
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    COL_MEAN_RATE_CONFLICT,
    REASON_NONE,
)
from verify_lab.measure.distribution import dividend_impact
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    mean_rate_conflict,
    permutation_test,
    summarize,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record
from verify_lab.studies.option_expiry.constants import (
    BASELINE_SUFFIX,
    COL_ADVANCED_DAYS,
    COL_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT,
    COL_DIVIDEND_MEASURED,
    COL_EXIT_DATE,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH_NUMBER,
    COL_HOLD_DAYS,
    COL_RULE_DATE,
    COL_TICKER,
    DATASETS,
    EXIT_WEEKDAY,
    KEY_CELLS,
    KEY_DIRECTION,
    KEY_EXCLUDED_COUNT,
    KEY_EXPIRY_MONTH,
    KEY_LABEL,
    OUTPUT_FILES,
    TRACK_NAME,
    WEEKDAY_LABELS,
    Dataset,
    ExpiryCell,
    trading_cells,
)
from verify_lab.studies.option_expiry.expiry_calendar import monthly_expiry_dates
from verify_lab.studies.option_expiry.weekly_exit import (
    weekly_exit_returns,
    weekly_exit_schedule,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# summary.json 키 (영문 snake_case — `reverse` 와 같은 관용)
# ============================================================

KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"

# 데이터셋 한 줄의 공통 다섯 키는 **`report/run_summary.py` 가 소유한다.** 여기서 다시
# 정의하지 않는다 — 이름을 한 벌 더 두면 옛 경로가 살아남아 소유자를 옮겨도 검사가 통과한다
KEY_EXPIRY_COUNT = "expiry_count"
KEY_ADVANCED_COUNT = "advanced_count"
KEY_EXPIRY_WEEKDAYS = "expiry_weekdays"
KEY_WEEKLY_TRADE = "weekly_trade"

KEY_ENTRY_COUNT = "entry_count"
KEY_HOLD_DAYS = "hold_days"
KEY_BASELINE_ENTRY_COUNT = "baseline_entry_count"

# 어느 기준선과 견줬는지 밝히는 이름 (`docs/매매/옵션_만기일/설계.md` §3.7)
BASELINE_WEEKLY = "같은 요일 주간 보유"

# 배당락 왜곡의 표시 자릿수. **백분율 2자리로는 뭉개진다** — 실측 왜곡이 0.05%p 대라
# 2자리면 걸린 칸과 안 걸린 칸이 똑같이 `0.0` 으로 나온다
DIVIDEND_IMPACT_DECIMALS = 4


@dataclass(frozen=True)
class StudyOutputs:
    """실행 산출물

    Attributes:
        measure: 확정 칸의 해석 재료 — 칸마다 한 행
        summary: 실행 파라미터와 핵심 수치
    """

    measure: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """표별로 행을 모으는 자리"""

    measure: list[pd.DataFrame] = field(default_factory=list)


def _count_labels(values: np.ndarray, labels: tuple[str, ...] | None = None) -> dict[str, int]:
    """정수 배열의 값별 건수를 세어 요약용 dict 로 만든다.

    `summary.json` 에 그대로 실리는 값이라 키는 문자열이고 정렬이 고정돼야 한다.
    `labels` 를 주면 값을 그 이름으로 바꾼다 (요일 번호 → 요일 이름).

    Args:
        values: 셀 정수 배열
        labels: 값을 이름으로 바꿀 목록. `None` 이면 숫자를 문자열로 쓴다

    Returns:
        값(또는 이름)별 건수. 값 오름차순
    """
    found, counts = np.unique(values, return_counts=True)

    return {
        (labels[int(value)] if labels is not None else str(int(value))): int(count)
        for value, count in zip(found, counts, strict=True)
    }


def _identify(frame: pd.DataFrame, **values: Any) -> pd.DataFrame:
    """표 앞머리에 식별 컬럼을 붙인다.

    Args:
        frame: 대상 표
        **values: 식별 컬럼 이름과 값

    Returns:
        식별 컬럼이 앞에 붙은 새 DataFrame
    """
    identified = frame.copy()
    for column, value in reversed(list(values.items())):
        identified.insert(0, column, value)

    return identified


def _weekly_trade_frames(
    df: pd.DataFrame,
    dataset: Dataset,
    expiries: pd.DataFrame,
    exit_weekday: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """매매 신호군과 「같은 요일 주간 보유」 베이스라인의 long-form 을 만든다.

    베이스라인은 **만기 규칙 요일에 해당하는 모든 거래일**(미국 금요일)에서 같은 달력 규칙으로
    청산한 것이다. 보유 길이 분포가 신호와 같은 달력 구조에서 나오므로 묶음 비교에 가중치를
    지어낼 필요가 없다 (`docs/매매/옵션_만기일/설계.md` 결정 ㉑).

    Args:
        df: 날짜 오름차순 시세
        dataset: 검증 대상 정의
        expiries: 만기일 표
        exit_weekday: 청산 목표 요일

    Returns:
        (신호군 long-form, 베이스라인 long-form)
    """
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    signal_schedule = weekly_exit_schedule(
        trading_days,
        pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]),
        pd.DatetimeIndex(expiries[COL_RULE_DATE]),
        exit_weekday=exit_weekday,
    )

    # 베이스라인은 만기가 아니므로 규칙일이 따로 없다. 진입일 자신이 주 기준일이다
    weekday_days = trading_days[trading_days.dayofweek == dataset.rule.weekday]
    baseline_schedule = weekly_exit_schedule(trading_days, weekday_days, weekday_days, exit_weekday=exit_weekday)

    signal = weekly_exit_returns(df, signal_schedule)
    baseline = weekly_exit_returns(df, baseline_schedule)

    return signal, baseline


def _per_length(frame: pd.DataFrame) -> pd.DataFrame:
    """묶음 표지를 실제 보유 거래일 수로 바꾼 유효 행만 남긴다.

    제외된 행은 보유일수가 없어 어느 칸에도 속하지 못하므로 여기서 빠진다 —
    **제외 건수는 `summary.json` 의 `rule` 이 담당한다.**

    Args:
        frame: `weekly_exit_returns` 의 결과

    Returns:
        보유일수를 구간 축으로 갖는 long-form
    """
    valid = frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()
    valid[COL_HORIZON] = valid[COL_HOLD_DAYS].astype(int)

    return valid


def _aggregate_by_month(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """만기월(1~12)별로 신호군과 같은 달 베이스라인을 나란히 낸다.

    **구간 축을 만기월로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다.**
    통계량 정의를 두 곳에서 구현하면 두 곳이 조용히 갈라지기 때문이다. 축 이름은 돌려주기
    직전에 만기월로 바꾼다.

    같은 달 베이스라인이 반드시 필요하다 — 만기월별로 쪼개면 미국 ETF 가 9월에 크게 음수인데,
    9월 약세는 옵션 만기와 무관하게 알려진 계절성이라 **같은 달과 견주지 않으면 만기 효과와
    가를 수 없다** (`docs/매매/옵션_만기일/설계.md` 결정 ㉓).

    **검정을 함께 붙인다.** 귀무분포는 **같은 달의 베이스라인**에서 뽑으므로 검정이 묻는 것도
    "그 달 안에서 만기 주가 특별한가" 이다.

    Args:
        signal: 신호군 long-form (유효 행)
        baseline: 같은 요일 주간 보유 베이스라인 long-form (유효 행)
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        만기월별 신호·베이스라인 집계와 초과분, 순열 검정
    """
    signal_by_month = signal.copy()
    signal_by_month[COL_HORIZON] = signal_by_month[COL_DATE].dt.month
    baseline_by_month = baseline.copy()
    baseline_by_month[COL_HORIZON] = baseline_by_month[COL_DATE].dt.month

    # 신호가 있는 달만 낸다. 베이스라인에만 있는 달을 남기면 초과분의 칸 구성이 어긋난다
    months = sorted(set(signal_by_month[COL_HORIZON].tolist()))
    baseline_by_month = baseline_by_month[baseline_by_month[COL_HORIZON].isin(months)]

    signal_summary = summarize(signal_by_month)
    baseline_summary = summarize(baseline_by_month)
    month_excess = excess(signal_summary, baseline_summary)
    month_test = permutation_test(signal_by_month, baseline_by_month, repeats=repeats, seed=seed)

    merged = (
        signal_summary.merge(baseline_summary, on=[COL_BASIS, COL_HORIZON], suffixes=("", BASELINE_SUFFIX))
        .merge(
            month_excess[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_EXCESS,
                    COL_MEDIAN_EXCESS,
                    COL_WIN_RATE_EXCESS,
                    COL_LOSS_RATE_EXCESS,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
        .merge(
            month_test[
                [
                    COL_BASIS,
                    COL_HORIZON,
                    COL_MEAN_P_VALUE,
                    COL_MEDIAN_P_VALUE,
                    COL_UP_RATE_P_VALUE,
                    COL_DOWN_RATE_P_VALUE,
                    COL_TEST_NOTE,
                ]
            ],
            on=[COL_BASIS, COL_HORIZON],
        )
    )
    merged[COL_MEAN_RATE_CONFLICT] = mean_rate_conflict(merged)

    return merged.rename(columns={COL_HORIZON: COL_EXPIRY_MONTH_NUMBER}).drop(columns=[COL_BASIS])


def _dividend_row(
    valid_signal: pd.DataFrame,
    raw_close: pd.Series,
    adjusted_close: pd.Series,
    cell: ExpiryCell,
) -> dict[str, Any]:
    """그 칸의 보유 구간에 들어간 배당락을 잰다.

    **산식은 `measure/distribution.py` 가 소유한다** — 여기서 다시 계산하면 실측 스크립트와
    조용히 갈라진다 (패키지 절대 원칙 5).

    Args:
        valid_signal: 그 대상의 유효 신호 long-form
        raw_close: 원본가 종가 (날짜 인덱스)
        adjusted_close: 수정주가 종가 (날짜 인덱스)
        cell: 대상 칸

    Returns:
        배당락 세 컬럼. 그 달의 체결이 없으면 값이 비어 있다
    """
    month_rows = valid_signal[valid_signal[COL_DATE].dt.month == cell.expiry_month]

    # **0 으로 채우지 않는다.** 체결이 없는 것과 왜곡이 0 인 것은 다른 사실이다
    if month_rows.empty:
        return {
            COL_DIVIDEND_MEASURED: pd.NA,
            COL_DIVIDEND_HIT_COUNT: pd.NA,
            COL_DIVIDEND_MEAN_IMPACT: np.nan,
        }

    impact = dividend_impact(
        raw_close,
        adjusted_close,
        entry_dates=pd.DatetimeIndex(month_rows[COL_DATE]),
        exit_dates=pd.DatetimeIndex(month_rows[COL_EXIT_DATE]),
        bet_down=cell.bet_down,
    )

    return {
        COL_DIVIDEND_MEASURED: impact.measured_count,
        COL_DIVIDEND_HIT_COUNT: impact.hit_count,
        # **여기서 반올림한다.** 이 값은 이미 %p 단위라 저장 계층의 비율→백분율 변환을 타지
        # 않고, 그대로 두면 `1.78e-05` 같은 과학적 표기로 CSV 에 실려 읽히지 않는다.
        # **백분율 2자리가 아니라 4자리다** — 실측 왜곡이 0.05%p 대라 2자리로는 전부 `0.0` 이 된다
        COL_DIVIDEND_MEAN_IMPACT: round(impact.mean_percent, DIVIDEND_IMPACT_DECIMALS),
    }


def _measure_block(
    by_month: pd.DataFrame,
    valid_signal: pd.DataFrame,
    raw_close: pd.Series,
    adjusted_close: pd.Series,
    cells: tuple[ExpiryCell, ...],
) -> pd.DataFrame:
    """확정 칸마다 한 행을 만든다.

    **칸이 축이고 만기월이 아니다.** 같은 달을 두 방향으로 걸면 두 행이 되며, 그 구별은
    `방향` 컬럼이 한다.

    Args:
        by_month: 만기월별 집계
        valid_signal: 그 대상의 유효 신호 long-form
        raw_close: 원본가 종가
        adjusted_close: 수정주가 종가
        cells: 이 대상의 확정 칸

    Returns:
        칸마다 한 행인 표. 종목 컬럼은 호출 측이 붙인다
    """
    wanted = pd.DataFrame(
        [
            {
                COL_EXPIRY_MONTH_NUMBER: cell.expiry_month,
                COL_DIRECTION: DIRECTION_DOWN if cell.bet_down else DIRECTION_UP,
                **_dividend_row(valid_signal, raw_close, adjusted_close, cell),
            }
            for cell in cells
        ]
    )

    # **`how="left"` 다.** 확정 칸인데 그 달의 신호가 없으면 행이 조용히 사라지는 대신
    # 지표가 빈 채로 남는다 — 「잴 수 없었다」가 산출물에서 드러나야 한다 (표본 보존)
    merged = wanted.merge(by_month, on=COL_EXPIRY_MONTH_NUMBER, how="left")

    missing = merged[merged[COL_MEAN_RATE_CONFLICT].isna()]
    if not missing.empty:
        logger.debug(f"확정 칸의 만기월에 신호가 없습니다: {missing[COL_EXPIRY_MONTH_NUMBER].tolist()}")

    # 배당락 세 컬럼을 맨 뒤로 보낸다 — 식별 축과 집계 사이에 끼면 표가 읽히지 않는다
    dividend_columns = [COL_DIVIDEND_MEASURED, COL_DIVIDEND_HIT_COUNT, COL_DIVIDEND_MEAN_IMPACT]
    ordered = [column for column in merged.columns if column not in dividend_columns] + dividend_columns

    return merged[ordered]


def _run_dataset(
    dataset: Dataset,
    cells: tuple[ExpiryCell, ...],
    accumulator: _Accumulator,
    *,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """종목 하나를 전부 돌린다.

    Args:
        dataset: 검증 대상 정의
        cells: 이 대상의 확정 칸
        accumulator: 결과를 쌓는 자리
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 종목의 요약 수치

    Raises:
        ValueError: 수정주가 파일이 없는 경우
    """
    df = load_market_csv(MARKET_DIR / dataset.file_name)
    trading_days = pd.DatetimeIndex(df[COL_DATE])
    expiries = monthly_expiry_dates(trading_days, dataset.rule)

    signal, baseline = _weekly_trade_frames(df, dataset, expiries, EXIT_WEEKDAY)
    valid_signal = _per_length(signal)
    by_month = _aggregate_by_month(valid_signal, _per_length(baseline), repeats=repeats, seed=seed)

    # **수정주가가 없으면 예외다.** 배당락을 0 으로 채우면 「안 걸림」과 「못 쟀다」가
    # 구별되지 않고, 그것이 `.claude/rules/trading.md` 가 경고한 바로 그 사고다
    adjusted_name = dataset.file_name.replace(
        MARKET_FILE_TEMPLATE.format(ticker=""), ADJUSTED_FILE_TEMPLATE.format(ticker="")
    )
    adjusted_path = MARKET_DIR / adjusted_name
    if not adjusted_path.is_file():
        raise ValueError(f"배당락을 재려면 수정주가 파일이 필요합니다: {adjusted_path}")

    raw_close = df.set_index(COL_DATE)[COL_CLOSE]
    adjusted_close = load_market_csv(adjusted_path).set_index(COL_DATE)[COL_CLOSE]

    block = _measure_block(by_month, valid_signal, raw_close, adjusted_close, cells)
    accumulator.measure.append(_identify(block, **{COL_TICKER: dataset.label}))

    expiry_weekdays = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE]).dayofweek

    return {
        # 공통 다섯 키는 **한 함수가 만든다.** 순서까지 그 함수가 정하므로 갈릴 수 없다
        **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.file_name, frame=df),
        KEY_EXPIRY_COUNT: len(expiries),
        KEY_ADVANCED_COUNT: int((expiries[COL_ADVANCED_DAYS] > 0).sum()),
        # 만기일이 실제로 무슨 요일이었나. 미국은 셋째 금요일이 규칙이지만 휴장 앞당김으로
        # 벗어나는 달이 있어 그 비율 자체가 보고 대상이다
        KEY_EXPIRY_WEEKDAYS: _count_labels(np.asarray(expiry_weekdays), WEEKDAY_LABELS),
        KEY_WEEKLY_TRADE: {
            KEY_ENTRY_COUNT: len(signal),
            KEY_EXCLUDED_COUNT: len(signal) - len(valid_signal),
            KEY_HOLD_DAYS: _count_labels(valid_signal[COL_HOLD_DAYS].to_numpy(dtype=int)),
            KEY_BASELINE_ENTRY_COUNT: len(baseline),
        },
    }


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    cells: tuple[ExpiryCell, ...] | None = None,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """검증 #7 을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        cells: 확정 칸. `None` 이면 `trading_cells(datasets)` 가 정한다
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상 목록이 빈 경우, 또는 어느 대상에도 해당하지 않는 칸이 있는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")

    targets = trading_cells(datasets) if cells is None else cells

    keys = {dataset.key for dataset in datasets}
    orphan = sorted({cell.dataset_key for cell in targets} - keys)
    if orphan:
        raise ValueError(f"칸이 가리키는 대상이 목록에 없습니다: {orphan}")

    accumulator = _Accumulator()
    dataset_summaries: list[dict[str, Any]] = []
    for dataset in datasets:
        dataset_cells = tuple(cell for cell in targets if cell.dataset_key == dataset.key)
        if not dataset_cells:
            logger.debug(f"확정 칸이 없어 건너뜁니다: {dataset.label}")
            continue

        dataset_summaries.append(_run_dataset(dataset, dataset_cells, accumulator, repeats=repeats, seed=seed))

    measure = _concat(accumulator.measure)
    summary: dict[str, Any] = {
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_TRACK: TRACK_NAME,
        KEY_DATASETS: dataset_summaries,
        # **무엇을 냈는지 요약이 말한다.** 확정 칸을 코드가 갖게 된 뒤로는 이 목록이
        # 「이번 실행이 어느 칸을 잰 것인가」의 유일한 기록이다
        KEY_CELLS: [
            {
                KEY_LABEL: _label_of(datasets, cell.dataset_key),
                KEY_EXPIRY_MONTH: cell.expiry_month,
                KEY_DIRECTION: DIRECTION_DOWN if cell.bet_down else DIRECTION_UP,
            }
            for cell in targets
        ],
        KEY_ROW_COUNTS: {OUTPUT_FILES["measure"]: len(measure)},
    }

    return StudyOutputs(measure=measure, summary=summary)


def _label_of(datasets: tuple[Dataset, ...], key: str) -> str:
    """데이터셋 이름으로 표시 이름을 찾는다.

    Args:
        datasets: 대상 목록
        key: 데이터셋 이름

    Returns:
        표시 이름

    Raises:
        RuntimeError: 그 이름의 대상이 없는 경우. 호출 전에 걸러지므로 도달할 수 없다
    """
    for dataset in datasets:
        if dataset.key == key:
            return dataset.label

    raise RuntimeError(f"내부 불변조건 위반 - 대상 목록에 없는 이름입니다: {key}")


def _concat(blocks: list[pd.DataFrame]) -> pd.DataFrame:
    """모아둔 표 조각을 하나로 잇는다.

    Args:
        blocks: 표 조각 목록

    Returns:
        이어붙인 DataFrame (조각이 없으면 빈 DataFrame)
    """
    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, ignore_index=True)


__all__ = ["StudyOutputs", "run_study"]
