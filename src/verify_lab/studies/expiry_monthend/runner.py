"""만기_말일 측정 조립 — 네 조합 × 두 달을 한 장으로 낸다

**계산하지 않는다.** 달력은 `measure/calendar_*`, 통계는 `measure/statistics`,
배당락은 `measure/distribution` 이 소유하고 여기서는 조립만 한다.

**축은 (종목 × 조합 × 달) 하나이고 `방향` 은 식별 «라벨»로 붙는다.** 값은 1배 롱 기준
그대로이며 부호를 뒤집지 않는다 — 뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을
가리켜 이름이 거짓이 된다. 라벨이 있어야 성적표의 `시기 = 전체` 행과 **1:1** 로 읽힌다.

**기준선은 「그 달 아무 날 진입」이다.** 계절성이 있는 달은 매매법과 무관하게 방향이 치우치므로,
같은 달과 견주지 않으면 「그 달이 원래 그런 것」과 「그 달의 이 매매가 특별한 것」을 가를 수 없다.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from verify_lab.common_constants import ADJUSTED_FILE_TEMPLATE, COL_CLOSE, COL_DATE
from verify_lab.data.loader import load_market_csv, load_series_csv
from verify_lab.measure.constants import (
    COL_DIVIDEND_HIT_COUNT,
    COL_DIVIDEND_MEAN_IMPACT,
    COL_DIVIDEND_MEASURED,
    COL_EXCLUDED_REASON,
    COL_EXIT_DATE,
    COL_HORIZON,
    COL_JUDGEABLE,
    COL_MEAN_RATE_CONFLICT,
    COL_MONTH,
    DIVIDEND_IMPACT_DECIMALS,
    REASON_NONE,
)
from verify_lab.measure.distribution import dividend_impact
from verify_lab.measure.screening import COL_DIRECTION, DIRECTION_DOWN, DIRECTION_UP
from verify_lab.measure.statistics import (
    COL_BASIS,
    COL_DOWN_RATE_P_VALUE,
    COL_LOSS_RATE_EXCESS,
    COL_MEAN_EXCESS,
    COL_MEAN_P_VALUE,
    COL_MEDIAN_EXCESS,
    COL_MEDIAN_P_VALUE,
    COL_SAMPLE_COUNT,
    COL_TEST_NOTE,
    COL_UP_RATE_P_VALUE,
    COL_WIN_RATE_EXCESS,
    DEFAULT_RANDOM_SEED,
    DEFAULT_REPEAT_COUNT,
    excess,
    judgeable,
    mean_rate_conflict,
    permutation_test,
    summarize,
)
from verify_lab.report.run_summary import KEY_TRACK, dataset_record
from verify_lab.report.tables import to_display_columns
from verify_lab.studies.expiry_monthend.constants import (
    BASELINE_SUFFIX,
    COL_COMBO,
    COL_MONTH_NUMBER,
    COL_SHARED_YEARS,
    COL_TICKER,
    COL_UNIQUE_YEARS,
    COLUMN_LABELS,
    COMBOS,
    DATASETS,
    DEFAULT_BET_DOWN,
    FIELD_STATISTICS,
    KEY_COMBO_ENTRY,
    KEY_COMBO_EXIT,
    KEY_COMBOS,
    KEY_ENTRY_COUNT,
    KEY_EXCLUDED_COUNT,
    KEY_LABEL,
    KEY_MONTHS,
    MONTHS,
    OUTPUT_FILES,
    PERCENT_COLUMNS,
    PROBABILITY_COLUMNS,
    TRACK_NAME,
    Combo,
    Dataset,
)
from verify_lab.studies.expiry_monthend.pairing import (
    baseline_entries,
    combo_entries,
    combo_returns,
    shared_year_counts,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

KEY_PERMUTATION_REPEATS = "permutation_repeats"
KEY_PERMUTATION_SEED = "permutation_seed"
KEY_DATASETS = "datasets"
KEY_ROW_COUNTS = "row_counts"
KEY_IS_INDEX = "is_index"


@dataclass(frozen=True)
class StudyOutputs:
    """측정 산출물

    Attributes:
        statistics: (종목 × 조합 × 달) 마다 한 행. 기준선·차이·우연확률·배당락과
            조합 붕괴 두 컬럼이 들어 있다
        summary: 실행 요약
    """

    statistics: pd.DataFrame
    summary: dict[str, Any]


@dataclass
class _Accumulator:
    """대상마다 나온 표 조각을 쌓는 자리"""

    statistics: list[pd.DataFrame] = field(default_factory=list)


def load_dataset(dataset: Dataset) -> pd.DataFrame:
    """대상의 가격 데이터를 읽는다.

    **측정과 체결이 같은 함수를 쓴다** — 같은 패키지 안에 두 벌을 두면 ETF·지수 분기가
    갈릴 수 있고, 그러면 한 매매법의 두 계층이 다른 스키마를 보게 된다.

    **ETF 와 지수는 로더가 다르다.** 지수는 종가 계열이라 시세 판정(0 이하 가격·급등락)을
    걸 수 없다.

    Args:
        dataset: 검증 대상 정의

    Returns:
        날짜 오름차순 가격 DataFrame
    """
    if dataset.is_index:
        return load_series_csv(dataset.path)

    return load_market_csv(dataset.path)


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    """제외되지 않은 행만 남긴다.

    집계는 유효 표본으로만 한다. **제외 건수는 요약이 담당한다.**

    Args:
        frame: `combo_returns` 의 결과

    Returns:
        유효 행만 남긴 DataFrame
    """
    return frame[frame[COL_EXCLUDED_REASON] == REASON_NONE].copy()


def _aggregate_by_month(
    signal: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    repeats: int,
    seed: int,
) -> pd.DataFrame:
    """달(1~12)별로 쪼개 집계·기준선 대비 차이·우연확률을 한 번에 낸다.

    **구간 축을 달로 빌려 `summarize`·`excess`·`permutation_test` 를 재사용한다** —
    통계량 정의를 여기서 다시 구현하면 두 곳이 조용히 갈라진다 (절대 원칙 5).

    [중요] **제외 행을 포함한 «전체»를 받는다.** 유효 행만 넘기면 `summarize` 의
    `count_excluded` 가 셀 것이 없어 **`제외` 컬럼이 언제나 0** 이 되는데, 이 저장소에서
    0 은 「재서 0」이라는 뜻이라 없는 안전을 보고하게 된다 (패키지 절대 원칙 4 「표본 보존」).
    통계량 자체는 값이 있는 행만 쓰므로 **유효만 넘길 때와 같다** — 실측으로
    40컬럼 중 `기준선 신호`·`기준선 제외` 둘만 달라진다(127/0 대 141/14).

    Args:
        signal: 신호군 long-form. **제외 행을 포함한 전체**다
        baseline: 기준선 long-form. **제외 행을 포함한 전체**다
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        달별 집계. 신호가 있는 달만 낸다
    """
    # **달 축을 「진입 달」로 잡는다** — 진입일이 `NaT` 인 제외 행도 달이 있어야
    # `count_excluded` 가 그 행을 셀 수 있다. 진입일로 세면 그 행의 달이 `NaN` 이라
    # **제외가 통째로 사라지고 `제외` 컬럼이 언제나 0** 이 된다
    signal_by_month = signal.copy()
    signal_by_month[COL_HORIZON] = signal_by_month[COL_MONTH].dt.month
    baseline_by_month = baseline.copy()
    baseline_by_month[COL_HORIZON] = baseline_by_month[COL_MONTH].dt.month

    # 신호가 있는 달만 낸다. 기준선에만 있는 달을 남기면 초과분의 칸 구성이 어긋난다
    months = sorted(set(signal_by_month[COL_HORIZON].tolist()))
    baseline_by_month = baseline_by_month[baseline_by_month[COL_HORIZON].isin(months)]

    signal_summary = summarize(signal_by_month)
    if signal_summary.empty:
        return pd.DataFrame()

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
    merged[COL_JUDGEABLE] = merged[COL_SAMPLE_COUNT].map(lambda count: judgeable(int(count)))

    return merged.rename(columns={COL_HORIZON: COL_MONTH_NUMBER}).drop(columns=[COL_BASIS])


def _dividend_row(dataset: Dataset, valid_signal: pd.DataFrame, month: int) -> dict[str, Any]:
    """그 칸의 보유 구간에 들어간 배당락을 잰다.

    **산식은 `measure/distribution.py` 가 소유한다.**

    [중요] **지수는 비운다.** 지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없고
    수정주가 파일도 없다. **0 으로 채우면 「안 걸림」과 「잴 수 없음」이 구별되지 않는다.**

    **방향은 「위」로 잰다** — 측정 표의 값이 1배 롱 기준 그대로이기 때문이다. 「아래」로 걸
    때의 왜곡은 부호가 반대이며 그 환산은 결과 문서가 적는다.

    Args:
        dataset: 대상 종목
        valid_signal: 그 조합의 유효 신호 long-form
        month: 재는 달

    Returns:
        배당락 세 컬럼. 지수이거나 그 달의 체결이 없으면 값이 비어 있다

    Raises:
        ValueError: ETF 인데 수정주가 파일이 없는 경우
    """
    blank: dict[str, Any] = {
        COL_DIVIDEND_MEASURED: pd.NA,
        COL_DIVIDEND_HIT_COUNT: pd.NA,
        COL_DIVIDEND_MEAN_IMPACT: np.nan,
    }

    if dataset.is_index:
        return blank

    month_rows = valid_signal[valid_signal[COL_DATE].dt.month == month]

    # **0 으로 채우지 않는다.** 체결이 없는 것과 왜곡이 0 인 것은 다른 사실이다
    if month_rows.empty:
        return blank

    adjusted_path = dataset.directory / ADJUSTED_FILE_TEMPLATE.format(ticker=dataset.ticker)
    if not adjusted_path.is_file():
        raise ValueError(f"배당락을 재려면 수정주가 파일이 필요합니다: {adjusted_path}")

    raw_close = load_market_csv(dataset.path).set_index(COL_DATE)[dataset.price_column]
    adjusted_close = load_market_csv(adjusted_path).set_index(COL_DATE)[COL_CLOSE]

    impact = dividend_impact(
        raw_close,
        adjusted_close,
        entry_dates=pd.DatetimeIndex(month_rows[COL_DATE]),
        exit_dates=pd.DatetimeIndex(month_rows[COL_EXIT_DATE]),
        bet_down=False,
    )

    return {
        COL_DIVIDEND_MEASURED: impact.measured_count,
        COL_DIVIDEND_HIT_COUNT: impact.hit_count,
        # **여기서 반올림한다.** 이 값은 이미 %p 단위라 저장 계층의 비율→백분율 변환을 타지
        # 않고, 그대로 두면 `1.78e-05` 같은 과학적 표기로 CSV 에 실려 읽히지 않는다
        COL_DIVIDEND_MEAN_IMPACT: round(impact.mean_percent, DIVIDEND_IMPACT_DECIMALS),
    }


def _run_dataset(
    dataset: Dataset,
    combos: tuple[Combo, ...],
    months: tuple[int, ...],
    accumulator: _Accumulator,
    *,
    bet_down: bool,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """대상 하나를 주어진 조합으로 돌린다.

    Args:
        dataset: 검증 대상 정의
        combos: 돌릴 조합 목록
        months: 재는 달 목록
        accumulator: 결과를 쌓는 자리
        bet_down: 아래로 거는 칸인지 여부. **표시용 라벨일 뿐 값을 바꾸지 않는다**
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        이 대상의 요약 수치

    Raises:
        ValueError: 재는 달의 신호가 없어 칸을 만들 수 없는 경우
        RuntimeError: 어떤 조합의 달별 집계가 통째로 비어 잴 수 없는 경우 (내부 불변조건 위반)
    """
    df = load_dataset(dataset)
    trading_days = pd.DatetimeIndex(df[COL_DATE])

    valid_by_combo: dict[str, pd.DataFrame] = {}
    blocks: dict[str, pd.DataFrame] = {}
    entry_count = 0
    excluded_count = 0

    for combo in combos:
        entries = combo_entries(trading_days, combo)
        signal = combo_returns(df, trading_days, entries, combo, price_column=dataset.price_column)
        # **기준선 모집단은 진입 규칙을 따른다** — 전 거래일로 통일하면 주 기준 청산에서
        # 보유 길이가 신호와 어긋나 그 차이가 기준선 대비 차이와 우연확률에 실린다
        baseline = baseline_entries(trading_days, combo)
        baseline_frame = combo_returns(df, trading_days, baseline, combo, price_column=dataset.price_column)

        valid_signal = _valid(signal)
        valid_by_combo[combo.label] = valid_signal

        # **전체를 넘긴다** — 유효만 넘기면 `제외` 가 언제나 0 이 된다 (위 함수의 설명)
        by_month = _aggregate_by_month(signal, baseline_frame, repeats=repeats, seed=seed)

        # **요약이 「정상으로 보이는 것」이 이 가드의 이유다.** 집계가 비면 그 조합이 통째로
        # 사라지는데 나머지 키는 멀쩡하므로 `summary.json` 만 봐서는 알 수 없다
        if by_month.empty:
            raise RuntimeError(
                f"내부 불변조건 위반: 달별 집계가 비어 조합을 잴 수 없습니다: " f"{dataset.label} / {combo.label} (유효 신호 {len(valid_signal)}건)"
            )

        block = by_month[by_month[COL_MONTH_NUMBER].isin(months)]

        # **재는 달이 통째로 빠지는 것을 여기서 끊는다.** 위 가드는 달 축 «전체» 가 비었는지만
        # 보므로, 신호가 있는 달이 하나라도 있으면 통과한다 — 그 사이 12월 칸이 사라져도
        # `통계.csv` 가 4행으로 나오고 **성적표는 8칸을 그대로 내** 두 표의 조인이 조용히 깨진다
        # **표본이 있는 달만 「쟀다」로 센다.** 달 축이 제외 행에서도 나오므로(위 함수)
        # 그 달의 신호가 전부 제외돼도 칸은 생긴다 — 그때 지표가 전부 비어 나간다
        measured = set(block.loc[block[COL_SAMPLE_COUNT] > 0, COL_MONTH_NUMBER])
        if missing_months := sorted(set(months) - measured):
            raise RuntimeError(
                f"내부 불변조건 위반: 재는 달의 신호가 없어 칸을 만들 수 없습니다: " f"{dataset.label} / {combo.label} (빠진 달 {missing_months})"
            )

        blocks[combo.label] = block

        # **요약의 모집단을 재는 달에 맞춘다.** 집계는 달 축 전체로 돌지만 내는 것은 두 달이라,
        # 진입·제외를 열두 달로 세면 체결 요약과 나란히 놓았을 때 다른 모집단을 가리킨다
        # **진입일이 아니라 «진입 달» 로 거른다.** 진입일을 못 정한 행은 날짜가 `NaT` 라
        # `.dt.month` 가 비고, 그러면 진입에도 제외에도 안 들어가 **몇 건이 왜 빠졌는지가
        # 어디에도 남지 않는다** — 성적표에서 `제외` 컬럼을 없앤 뒤로 요약이 그 유일한 자리다
        in_months = signal[signal[COL_MONTH].dt.month.isin(months)]
        entry_count += len(in_months)
        excluded_count += int((in_months[COL_EXCLUDED_REASON] != REASON_NONE).sum())

    # **조합 붕괴는 달마다 따로 센다** — 같은 조합이 9월에는 갈리고 12월에는 겹칠 수 있다.
    #
    # [중요] **네 조합을 다 돌렸을 때만 이 값이 성립한다.** 부분집합으로 세면 그 안에서만의
    # 붕괴가 되는데 산출물에는 그 사실이 남지 않아 **전체 격자의 값처럼 읽힌다.**
    # 조합이 하나뿐이면 더 분명하다 — 견줄 다른 조합이 없어
    # 「이 조합만 다른 해」가 신호 수와 같아지는데, 그것은 **독립 관측이 그만큼 있다는 뜻이
    # 아니라 비교 대상이 없다는 뜻**이다 — 실측으로 SPY 9월의 실제 값은 넷을 다 돌렸을 때
    # 15해이고 하나만 돌리면 33 으로 나온다. **0 이나 신호 수로 채우면 거짓이 실리므로 비운다**
    # (이 저장소에서 빈칸은 「잴 수 없었다」는 뜻이다)
    comparable = len(combos) == len(COMBOS)
    counts_by_month = {month: shared_year_counts(valid_by_combo, month) for month in months} if comparable else {}

    for combo in combos:
        block = blocks[combo.label].copy()
        if comparable:
            # **루프 변수를 람다에 가두지 않는다** — 늦은 바인딩이면 전 조합이 마지막 조합의 값을
            # 받는데 예외가 나지 않고 숫자만 틀린다. 리스트로 먼저 펼쳐 그 자리에서 읽는다
            counted = [counts_by_month[int(month)][combo.label] for month in block[COL_MONTH_NUMBER]]
            shared = [value for value, _ in counted]
            unique = [value for _, value in counted]
        else:
            shared = [pd.NA] * len(block)
            unique = [pd.NA] * len(block)
        block[COL_SHARED_YEARS] = pd.array(shared, dtype="Int64")
        block[COL_UNIQUE_YEARS] = pd.array(unique, dtype="Int64")

        dividend = pd.DataFrame(
            [_dividend_row(dataset, valid_by_combo[combo.label], int(month)) for month in block[COL_MONTH_NUMBER]],
            index=block.index,
        )
        block = pd.concat([block, dividend], axis=1)

        block.insert(0, COL_COMBO, combo.label)
        block.insert(0, COL_TICKER, dataset.label)

        # **방향은 식별 컬럼이고 값을 바꾸지 않는다.** 측정 표의 수치는 1배 롱 기준 그대로이며,
        # 부호를 뒤집으면 `기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 이름이 거짓이 된다.
        # 이 컬럼이 있어야 성적표의 `시기 = 전체` 행과 1:1 로 읽힌다 (매매 산출물 계약)
        block.insert(3, COL_DIRECTION, DIRECTION_DOWN if bet_down else DIRECTION_UP)

        accumulator.statistics.append(block)

    return {
        # **공통 다섯 키가 먼저, 이 검증의 축이 뒤에 온다**
        **dataset_record(ticker=dataset.ticker, label=dataset.label, file=dataset.path.name, frame=df),
        KEY_IS_INDEX: dataset.is_index,
        KEY_ENTRY_COUNT: entry_count,
        KEY_EXCLUDED_COUNT: excluded_count,
    }


def run_study(
    datasets: tuple[Dataset, ...] = DATASETS,
    *,
    combos: tuple[Combo, ...] = COMBOS,
    months: tuple[int, ...] = MONTHS,
    bet_down: bool = DEFAULT_BET_DOWN,
    repeats: int = DEFAULT_REPEAT_COUNT,
    seed: int = DEFAULT_RANDOM_SEED,
) -> StudyOutputs:
    """만기_말일 측정을 실행하고 산출물을 조립한다.

    Args:
        datasets: 검증 대상 목록
        combos: 돌릴 조합 목록
        months: 재는 달 목록
        bet_down: 아래로 거는 칸인지 여부. **표시용 라벨일 뿐 값을 바꾸지 않는다**
        repeats: 순열 검정 반복 수
        seed: 순열 검정 시드

    Returns:
        실행 산출물

    Raises:
        ValueError: 대상·조합·달 목록이 비었거나, 재는 달의 신호가 없는 경우
    """
    if not datasets:
        raise ValueError("검증 대상이 하나도 없습니다")
    if not combos:
        raise ValueError("조합이 하나도 없습니다")
    if not months:
        raise ValueError("재는 달이 하나도 없습니다")

    accumulator = _Accumulator()
    dataset_summaries = [
        _run_dataset(dataset, combos, months, accumulator, bet_down=bet_down, repeats=repeats, seed=seed)
        for dataset in datasets
    ]

    statistics = pd.concat(accumulator.statistics, ignore_index=True)

    summary: dict[str, Any] = {
        KEY_PERMUTATION_REPEATS: repeats,
        KEY_PERMUTATION_SEED: seed,
        KEY_COMBOS: [
            {KEY_LABEL: combo.label, KEY_COMBO_ENTRY: combo.entry, KEY_COMBO_EXIT: combo.exit_rule} for combo in combos
        ],
        KEY_MONTHS: list(months),
        KEY_TRACK: TRACK_NAME,
        KEY_DATASETS: dataset_summaries,
        KEY_ROW_COUNTS: {OUTPUT_FILES[FIELD_STATISTICS]: len(statistics)},
    }

    logger.debug(f"측정 완료: {len(statistics):,}행 (대상 {len(datasets)} × 조합 {len(combos)} × 달 {len(months)})")

    return StudyOutputs(statistics=statistics, summary=summary)


def display_tables(outputs: StudyOutputs) -> dict[str, pd.DataFrame]:
    """저장할 표를 표시용(한글 헤더·백분율)으로 바꾼다.

    **터미널과 CSV 가 같은 프레임을 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
    CSV 에서 찾지 못한다.

    Args:
        outputs: 실행 산출물

    Returns:
        산출물 필드 이름 → 표시용 DataFrame
    """
    if outputs.statistics.empty:
        return {}

    # **단위 변환을 여기서 다시 구현하지 않는다** — `to_display_columns` 가 헤더와 단위를
    # 한자리에서 정한다. 따로 돌리면 헤더는 `(%)` 인데 값이 비율인 표가 조용히 나올 수 있다
    table = to_display_columns(
        outputs.statistics,
        COLUMN_LABELS,
        percent_columns=[column for column in PERCENT_COLUMNS if column in outputs.statistics.columns],
        probability_columns=[column for column in PROBABILITY_COLUMNS if column in outputs.statistics.columns],
    )

    return {FIELD_STATISTICS: table}


__all__ = ["FIELD_STATISTICS", "StudyOutputs", "display_tables", "load_dataset", "run_study"]
