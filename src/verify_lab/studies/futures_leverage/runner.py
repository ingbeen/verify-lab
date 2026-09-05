"""검증 #9 실행 — 세 방식을 나란히 재고 차이를 분해한다

한 실행에서 **2지수 × 짝 6개 × 배수 × 4방식 × 7격자 × 2롤규칙 × 2이자가정** 을 전부 낸다.
방식 넷은 레버리지 ETF · 선물 매일 · 선물 월 1회 · **선물 그대로 두기**다.
배수·격자·리밸런싱 주기·롤 규칙은 CLI 인자로 열지 않는다 — 노브가 되면 결과를 보고 고르게 되며
그것은 측정이 아니라 과최적화다 (측정의 원칙 1).

## 산출물

| 파일 | 내용 |
| --- | --- |
| `comparison.csv` | 지수 × 배수 × 방식 × 구간 집계. **가장 먼저 볼 표** |
| `decomposition.csv` | 차이 분해 — 롤·베이시스 비용 · 리밸런싱 오차 · 이자 · 잔여 |
| `roll_events.csv` | 롤 이벤트 원자료 (판정일·집행일·계약·조정계수·미결제약정) |
| `breakeven.csv` | 배수·롤규칙별로 «몇 거래일부터 선물이 앞서는가» |
| `wipeouts.csv` | 자기자본이 0 이하가 된 시점 |
| `leverage_drift.csv` | 구간 최대 유효 레버리지 |
| `integer_contracts.csv` | 자기자본 규모별 정수 계약 대조 — **여기서만 규모가 결과를 만든다** |
| `windows_<지수>_<짝 종목>.csv` | 시작일 전체 목록 원자료. 사용자가 차트와 대조하는 자리다 |

## 방식마다 적용되는 축이 다르다

ETF 는 롤 규칙·이자 가정과 무관하다. 그냥 곱하면 같은 값이 네 번 복제돼 나오고
사용자가 그것을 서로 다른 값으로 읽는다. **해당 없는 축은 칸을 비운다**
(0 으로 채우지 않는다 — 측정의 원칙 17).
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_SETTLE,
    COL_SPOT,
    FUTURES_FILE_TEMPLATE,
    MARKET_DIR,
    MARKET_FILE_TEMPLATE,
    SERIES_DIR,
)
from verify_lab.common_constants import COL_VALUE as COL_SERIES_VALUE
from verify_lab.data.loader import load_futures_csv, load_market_csv, load_series_csv
from verify_lab.measure.constants import (
    COL_EXCLUDED_REASON,
    COL_HORIZON,
    COL_JUDGEABLE,
    JUDGEABLE_NO,
    JUDGEABLE_YES,
    MIN_SAMPLE_PER_CELL,
    REASON_NONE,
)
from verify_lab.measure.distribution import dividend_adjustment, measure_distribution_share
from verify_lab.measure.statistics import max_non_overlapping
from verify_lab.studies.futures_leverage.comparison import (
    build_interest_factor,
    build_window_table,
    decompose,
    horizons_or_default,
    leveraged_window_returns,
    plain_window_returns,
)
from verify_lab.studies.futures_leverage.constants import (
    BASELINE_METHOD,
    COL_ACTUAL_MULTIPLE,
    COL_AHEAD_HORIZON_COUNT,
    COL_AS_OF_DATE,
    COL_BREAKEVEN_HORIZON,
    COL_CONTRACT_MULTIPLIER,
    COL_DIVIDEND_ADJUSTMENT,
    COL_END_DATE,
    COL_EQUITY_SIZE,
    COL_EXECUTABLE,
    COL_FIRST_WIPEOUT_DATE,
    COL_INDEX_NAME,
    COL_INTEGER_CONTRACTS,
    COL_INTEREST,
    COL_MAX_LEVERAGE_DAILY,
    COL_MAX_LEVERAGE_MONTHLY,
    COL_MEAN_RETURN,
    COL_MEDIAN_RETURN,
    COL_METHOD,
    COL_MULTIPLE,
    COL_NON_OVERLAPPING,
    COL_NOTIONAL,
    COL_PERIOD,
    COL_PRICE,
    COL_ROLL_RULE,
    COL_SAMPLE_COUNT,
    COL_START_DATE,
    COL_TARGET_TICKER,
    COL_TESTED_HORIZON_COUNT,
    COL_WINDOW_COUNT,
    COL_WIPEOUT_COUNT,
    DISPLAY_PERIOD_HIGH_RATE,
    DISPLAY_PERIOD_LOW_RATE,
    HIGH_RATE_START_YEAR,
    INTEGER_CONTRACT_EQUITIES,
    INTEREST_ASSUMPTIONS,
    INTEREST_SERIES_NAME,
    METHOD_BY_REBALANCE,
    METHOD_ETF,
    METHOD_FUTURES_DAILY,
    METHOD_FUTURES_HOLD,
    METHOD_FUTURES_MONTHLY,
    PAIRS,
    REASON_NOT_EXECUTABLE,
    REBALANCE_DAILY,
    REBALANCE_INTERVAL_DAYS,
    REBALANCE_MONTHLY,
    REBALANCE_NONE,
    ROLL_RULES,
    FuturesPair,
)
from verify_lab.studies.futures_leverage.continuous import (
    COL_ADJUSTED_SETTLE,
    build_continuous_series,
)
from verify_lab.studies.futures_leverage.contracts import contract_multiplier_on, integer_contract_position
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 이자 가정의 표시값. 참·거짓 대신 사람이 읽는 말을 쓴다
DISPLAY_INTEREST_ON = "이자 있음"
DISPLAY_INTEREST_OFF = "이자 없음"

# 단일 값 시계열 파일명. **이 파일에서만 쓰므로 여기 둔다** — 시세·선물 파일명과 달리
# 이름이 곧 계열 이름이라 공유할 규칙이 없다 (`src/verify_lab/CLAUDE.md` 「상수 관리」)
SERIES_FILE_TEMPLATE = "{name}.csv"


@dataclass(frozen=True)
class PairOutputs:
    """한 짝의 산출물 조각."""

    comparison: pd.DataFrame
    decomposition: pd.DataFrame
    windows: pd.DataFrame
    leverage_drift: pd.DataFrame
    wipeouts: pd.DataFrame


@dataclass(frozen=True)
class StudyOutputs:
    """검증 전체의 산출물.

    Attributes:
        comparison: 지수 × 배수 × 방식 × 구간 집계
        decomposition: 차이 분해
        roll_events: 롤 이벤트 원자료
        breakeven: 선물이 앞서기 시작하는 보유 기간
        wipeouts: 자기자본 소진 시점
        leverage_drift: 구간 최대 유효 레버리지
        integer_contracts: 자기자본 규모별 정수 계약 대조
        windows_by_pair: 짝별 시작일 원자료
        pair_count: 실제로 잰 짝 수
        skipped_pairs: 데이터가 없어 건너뛴 짝과 사유
    """

    comparison: pd.DataFrame
    decomposition: pd.DataFrame
    roll_events: pd.DataFrame
    breakeven: pd.DataFrame
    wipeouts: pd.DataFrame
    leverage_drift: pd.DataFrame
    integer_contracts: pd.DataFrame
    windows_by_pair: dict[str, pd.DataFrame]
    pair_count: int
    skipped_pairs: list[tuple[str, str]]


def _non_overlapping_count(usable: np.ndarray, horizon: int) -> int:
    """겹치지 않게 고를 수 있는 최대 구간 수를 센다.

    **정의는 `measure.statistics.max_non_overlapping` 하나이며 검증 #8 도 같은 함수를 쓴다.**
    여기서는 「시작일마다 쓸 수 있는지」라는 이 검증의 표현을 위치 목록으로 바꿔 넘기기만 한다.

    Args:
        usable: 시작일마다 그 구간을 쓸 수 있는지
        horizon: 보유 기간 (거래일)

    Returns:
        겹치지 않는 최대 구간 수
    """
    return max_non_overlapping(np.flatnonzero(usable).tolist(), horizon)


def _period_labels(dates: pd.Series) -> pd.Series:
    """시작일을 저금리·고금리로 가른다. 검증 #8 과 같은 경계다."""
    return pd.Series(
        np.where(dates.dt.year >= HIGH_RATE_START_YEAR, DISPLAY_PERIOD_HIGH_RATE, DISPLAY_PERIOD_LOW_RATE),
        index=dates.index,
    )


def _summarize(values: np.ndarray, horizon: int) -> dict[str, object]:
    """구간 수익률 배열을 집계 한 줄로 만든다.

    **평균과 중앙값을 반드시 병기한다** (측정의 원칙 4). 두 값이 벌어지면 소수 사건이
    결과를 만들고 있다는 신호다.

    Args:
        values: 구간 수익률 배열 (못 잰 칸은 NaN)
        horizon: 보유 기간 (거래일)

    Returns:
        집계 dict
    """
    usable = ~np.isnan(values)
    sample_count = int(usable.sum())

    return {
        COL_SAMPLE_COUNT: sample_count,
        COL_NON_OVERLAPPING: _non_overlapping_count(usable, horizon),
        COL_MEAN_RETURN: float(np.mean(values[usable])) if sample_count else np.nan,
        COL_MEDIAN_RETURN: float(np.median(values[usable])) if sample_count else np.nan,
        # **불린이 아니라 문자열이다.** 네 계층이 같은 어휘를 써야 산출물을 나란히 읽을 수 있고,
        # `screening` 이 「예」로 거르므로 불린을 담으면 그 표는 전 칸이 조용히 제외된다
        COL_JUDGEABLE: JUDGEABLE_YES if sample_count >= MIN_SAMPLE_PER_CELL else JUDGEABLE_NO,
    }


def _load_interest(series_dir: Path) -> pd.Series:
    """여유현금 이자율 시계열을 읽는다.

    Args:
        series_dir: 단일 값 시계열 폴더

    Returns:
        날짜를 인덱스로 하는 연율 금리(%) Series
    """
    path = series_dir / SERIES_FILE_TEMPLATE.format(name=INTEREST_SERIES_NAME)
    frame = load_series_csv(path)

    return frame.set_index(COL_DATE)[COL_SERIES_VALUE]


def _align(frames: dict[str, pd.DataFrame], value_columns: dict[str, str]) -> pd.DataFrame:
    """여러 계열을 공통 거래일로 맞춘다.

    **보간하지 않는다.** 한쪽에만 있는 날은 빼며, 그러면 그날의 비교가 성립하지 않는다.

    Args:
        frames: 이름 → DataFrame (`Date` 와 값 컬럼을 갖는다)
        value_columns: 이름 → 값 컬럼 이름

    Returns:
        공통 거래일만 담은 DataFrame. 컬럼 이름은 `frames` 의 키다

    Raises:
        ValueError: 겹치는 거래일이 없는 경우
    """
    merged: pd.DataFrame | None = None
    for name, frame in frames.items():
        part = frame[[COL_DATE, value_columns[name]]].rename(columns={value_columns[name]: name})
        merged = part if merged is None else merged.merge(part, on=COL_DATE, how="inner")

    if merged is None or merged.empty:
        raise ValueError(f"겹치는 거래일이 없습니다 - 계열: {sorted(frames)}")

    return merged.sort_values(COL_DATE).reset_index(drop=True)


def _run_pair(
    pair: FuturesPair,
    futures: pd.DataFrame,
    interest: pd.Series,
    horizons: list[int],
    market_dir: Path,
) -> PairOutputs:
    """한 짝을 재고 산출물 조각을 만든다.

    Args:
        pair: 선물과 배수 상품의 짝
        futures: 그 상품의 선물 시세
        interest: 연율 금리(%) Series
        horizons: 보유 기간 목록
        market_dir: 원시 시세 폴더

    Returns:
        이 짝의 산출물 조각
    """
    base = load_market_csv(market_dir / MARKET_FILE_TEMPLATE.format(ticker=pair.base_ticker))
    target = load_market_csv(market_dir / MARKET_FILE_TEMPLATE.format(ticker=pair.target_ticker))

    base_share = measure_distribution_share(pair.base_ticker, market_dir=market_dir)
    target_share = measure_distribution_share(pair.target_ticker, market_dir=market_dir)

    comparison_rows: list[dict[str, object]] = []
    decomposition_rows: list[dict[str, object]] = []
    window_frames: list[pd.DataFrame] = []
    drift_rows: list[dict[str, object]] = []
    wipeout_rows: list[dict[str, object]] = []

    for roll_rule in ROLL_RULES:
        series, _ = build_continuous_series(futures, roll_rule)

        aligned = _align(
            {"futures": series, "spot": series, "base": base, "target": target},
            {"futures": COL_ADJUSTED_SETTLE, "spot": COL_SPOT, "base": COL_CLOSE, "target": COL_CLOSE},
        )

        dates = aligned[COL_DATE]
        futures_prices = aligned["futures"].to_numpy(dtype=float)
        spot_prices = aligned["spot"].to_numpy(dtype=float)
        base_prices = aligned["base"].to_numpy(dtype=float)
        target_prices = aligned["target"].to_numpy(dtype=float)
        interest_factor = build_interest_factor(dates, interest)
        periods = _period_labels(dates)

        for horizon in horizons:
            etf_return = plain_window_returns(target_prices, horizon)
            base_return = plain_window_returns(base_prices, horizon)
            spot_return = plain_window_returns(spot_prices, horizon)
            continuous_return = plain_window_returns(futures_prices, horizon)

            leveraged = {
                (rebalance, with_interest): leveraged_window_returns(
                    futures_prices,
                    pair.multiple,
                    horizon,
                    rebalance,
                    interest_factor=interest_factor if with_interest else None,
                )
                for rebalance in (REBALANCE_DAILY, REBALANCE_MONTHLY, REBALANCE_NONE)
                for with_interest in INTEREST_ASSUMPTIONS
            }
            futures_returns = {key: values for key, (values, _) in leveraged.items()}

            # 자기자본이 소진된 구간은 수익률이 정의되지 않는다. **건수를 남긴다** —
            # 예외로 멈추면 그런 구간이 몇 개였는지가 산출물에서 사라진다
            for (rebalance, with_interest), (_, wiped) in leveraged.items():
                if with_interest:
                    continue
                wipeout_rows.append(
                    {
                        COL_INDEX_NAME: pair.index_name,
                        COL_TARGET_TICKER: pair.target_ticker,
                        COL_MULTIPLE: pair.multiple,
                        COL_METHOD: METHOD_BY_REBALANCE[rebalance],
                        COL_ROLL_RULE: roll_rule,
                        COL_HORIZON: horizon,
                        COL_WIPEOUT_COUNT: int(wiped.sum()),
                        COL_WINDOW_COUNT: int((~np.isnan(base_return)).sum()),
                        COL_FIRST_WIPEOUT_DATE: dates.iloc[int(np.flatnonzero(wiped)[0])] if wiped.any() else None,
                    }
                )

            method_returns = {
                METHOD_ETF: etf_return,
                METHOD_FUTURES_DAILY: futures_returns[(REBALANCE_DAILY, False)],
                METHOD_FUTURES_MONTHLY: futures_returns[(REBALANCE_MONTHLY, False)],
                METHOD_FUTURES_HOLD: futures_returns[(REBALANCE_NONE, False)],
            }

            # 1. 방식별 집계. **ETF 행은 롤 규칙·이자 축이 없다** — 첫 규칙에서만 낸다
            for method, values in method_returns.items():
                if method == METHOD_ETF and roll_rule != ROLL_RULES[0]:
                    continue

                comparison_rows.append(
                    {
                        COL_INDEX_NAME: pair.index_name,
                        COL_TARGET_TICKER: pair.target_ticker,
                        COL_MULTIPLE: pair.multiple,
                        COL_METHOD: method,
                        COL_ROLL_RULE: None if method == METHOD_ETF else roll_rule,
                        COL_INTEREST: None if method == METHOD_ETF else DISPLAY_INTEREST_OFF,
                        COL_HORIZON: horizon,
                        COL_START_DATE: dates.iloc[0],
                        COL_END_DATE: dates.iloc[-1],
                        **_summarize(values, horizon),
                    }
                )

            # 2. 이자 있음 벌은 선물에만 붙는다
            for rebalance, method in METHOD_BY_REBALANCE.items():
                comparison_rows.append(
                    {
                        COL_INDEX_NAME: pair.index_name,
                        COL_TARGET_TICKER: pair.target_ticker,
                        COL_MULTIPLE: pair.multiple,
                        COL_METHOD: method,
                        COL_ROLL_RULE: roll_rule,
                        COL_INTEREST: DISPLAY_INTEREST_ON,
                        COL_HORIZON: horizon,
                        COL_START_DATE: dates.iloc[0],
                        COL_END_DATE: dates.iloc[-1],
                        **_summarize(futures_returns[(rebalance, True)], horizon),
                    }
                )

            # 3. 분해. 기준선은 「선물 매일·이자 없음」 하나로 고정한다
            parts = decompose(
                etf_return,
                futures_returns[(REBALANCE_DAILY, False)],
                futures_returns[(REBALANCE_MONTHLY, False)],
                futures_returns[(REBALANCE_NONE, False)],
                futures_returns[(REBALANCE_DAILY, True)],
                continuous_return,
                spot_return,
                pair.multiple,
            )
            usable = ~np.isnan(etf_return)
            decomposition_rows.append(
                {
                    COL_INDEX_NAME: pair.index_name,
                    COL_TARGET_TICKER: pair.target_ticker,
                    COL_MULTIPLE: pair.multiple,
                    COL_ROLL_RULE: roll_rule,
                    COL_HORIZON: horizon,
                    COL_SAMPLE_COUNT: int(usable.sum()),
                    COL_NON_OVERLAPPING: _non_overlapping_count(usable, horizon),
                    **{column: float(parts.loc[usable, column].mean()) for column in parts.columns},
                    COL_DIVIDEND_ADJUSTMENT: dividend_adjustment(base_share, target_share, pair.multiple, horizon),
                }
            )

            # 4. 시작일 원자료. 첫 롤 규칙만 남긴다 — 두 벌을 다 남기면 파일이 두 배가 된다.
            #    **표 만들기는 `comparison` 이 소유한다** — 여기서 다시 조립하면 제외 사유
            #    문자열이 두 곳에서 나와 갈라진다. 시기 축만 덧붙인다
            if roll_rule == ROLL_RULES[0]:
                window = build_window_table(
                    dates,
                    {
                        METHOD_ETF: etf_return,
                        METHOD_FUTURES_DAILY: futures_returns[(REBALANCE_DAILY, False)],
                        METHOD_FUTURES_MONTHLY: futures_returns[(REBALANCE_MONTHLY, False)],
                        METHOD_FUTURES_HOLD: futures_returns[(REBALANCE_NONE, False)],
                    },
                    horizon,
                )
                # 시기 축은 구간 바로 뒤에 둔다 — 「무엇으로 나눴는가」가 수치보다 왼쪽에 있어야 읽힌다.
                # `Index.get_loc` 은 슬라이스도 돌려줄 수 있어 위치 계산에 쓰지 않는다
                window.insert(list(window.columns).index(COL_HORIZON) + 1, COL_PERIOD, periods.to_numpy())
                window_frames.append(window)

            # 5. 최대 유효 레버리지. 월 1회에서 배수가 얼마나 표류하는지 보여준다
            drift = _max_effective_leverage(futures_prices, pair.multiple, horizon)
            drift_rows.append(
                {
                    COL_INDEX_NAME: pair.index_name,
                    COL_TARGET_TICKER: pair.target_ticker,
                    COL_MULTIPLE: pair.multiple,
                    COL_ROLL_RULE: roll_rule,
                    COL_HORIZON: horizon,
                    COL_MAX_LEVERAGE_DAILY: abs(pair.multiple),
                    COL_MAX_LEVERAGE_MONTHLY: drift,
                }
            )

    return PairOutputs(
        comparison=pd.DataFrame(comparison_rows),
        decomposition=pd.DataFrame(decomposition_rows),
        windows=pd.concat(window_frames, ignore_index=True) if window_frames else pd.DataFrame(),
        leverage_drift=pd.DataFrame(drift_rows),
        wipeouts=pd.DataFrame(wipeout_rows),
    )


def _integer_contract_table(pair: FuturesPair, series: pd.DataFrame) -> pd.DataFrame:
    """자기자본 규모별로 정수 계약이 만드는 실제 배수를 낸다.

    **본선(소수 계약)과 달리 여기서는 규모가 결과를 만든다** — 계약 하나를 살 수 있는지가
    자기자본에 달렸기 때문이다. 「얼마부터 선물이 실용적인가」에 답하는 자리다.

    기준일은 **데이터의 마지막 거래일**이고 가격은 그날의 **원본 정산가**다.
    비율 조정 계열을 쓰면 가격 수준이 실제 체결가가 아니라 명목금액이 어긋난다
    (`docs/spec/futures_leverage.md` §4 ③).

    Args:
        pair: 선물과 배수 상품의 짝
        series: 연속 계열 (원본 정산가 컬럼을 갖는다)

    Returns:
        자기자본 규모마다 한 행인 대조표
    """
    last = series.iloc[-1]
    as_of = pd.Timestamp(last[COL_DATE]).date()
    price = float(last[COL_SETTLE])
    multiplier = contract_multiplier_on(pair.product_id, as_of)

    rows: list[dict[str, object]] = []
    for equity in INTEGER_CONTRACT_EQUITIES:
        position = integer_contract_position(float(equity), pair.multiple, price, multiplier)
        rows.append(
            {
                COL_INDEX_NAME: pair.index_name,
                COL_TARGET_TICKER: pair.target_ticker,
                COL_MULTIPLE: pair.multiple,
                COL_AS_OF_DATE: last[COL_DATE],
                COL_PRICE: price,
                COL_CONTRACT_MULTIPLIER: multiplier,
                COL_NOTIONAL: position.notional,
                COL_EQUITY_SIZE: float(equity),
                COL_INTEGER_CONTRACTS: position.contracts,
                COL_ACTUAL_MULTIPLE: position.actual_multiple,
                COL_EXECUTABLE: position.executable,
                COL_EXCLUDED_REASON: REASON_NONE if position.executable else REASON_NOT_EXECUTABLE,
            }
        )

    return pd.DataFrame(rows)


def _max_effective_leverage(prices: np.ndarray, multiple: float, horizon: int) -> float:
    """월 1회 리밸런싱에서 구간 안 최대 유효 레버리지를 낸다.

    리밸런싱 사이에 계약 수가 고정되므로 `노출 ÷ 자기자본` 이 표류한다.
    **증거금률 가정 없이** 위험이 얼마나 커졌는지를 보여주는 값이다.

    Args:
        prices: 가격 배열
        multiple: 목표 배수
        horizon: 보유 기간 (거래일)

    Returns:
        모든 시작일에 걸친 최대 유효 레버리지.
        **잴 수 있는 칸이 하나도 없으면 `0.0` 이 아니라 NaN** 이다 — 0 은 「위험이 전혀 없었다」로
        읽히지만 실제로는 「잰 적이 없다」이다 (측정의 원칙 17 과 같은 이유)
    """
    row_count = len(prices)
    positions = np.arange(row_count)
    usable = positions + horizon <= row_count - 1
    if not usable.any():
        return float("nan")

    # **0.0 에서 시작하지 않는다.** `max(0.0, nan)` 은 파이썬에서 `0.0` 을 돌려주므로
    # (`nan > 0.0` 이 False), 전 구간이 소진돼 잴 값이 하나도 없는 칸이 「레버리지 0」으로
    # 나간다. 잰 값만 모았다가 마지막에 최대를 취해 그 사고를 구조로 막는다
    observed: list[float] = []
    for offset in range(1, horizon + 1):
        anchor_offset = (offset // REBALANCE_INTERVAL_DAYS) * REBALANCE_INTERVAL_DAYS
        anchors = np.where(usable, positions + anchor_offset, 0)
        current = np.where(usable, positions + offset, 0)

        segment_return = prices[current] / prices[anchors] - 1.0
        equity_factor = 1.0 + multiple * segment_return
        exposure_factor = 1.0 + segment_return

        with np.errstate(divide="ignore", invalid="ignore"):
            leverage = np.abs(multiple * exposure_factor / equity_factor)

        # 자기자본이 0 이하가 된 시작일은 그 시점에 끝난 것이라 유효 레버리지가 정의되지 않는다
        measurable = leverage[usable & (equity_factor > 0) & np.isfinite(leverage)]
        if measurable.size:
            observed.append(float(measurable.max()))

    return max(observed) if observed else float("nan")


def run_study(
    index_filter: str | None = None,
    horizons: list[int] | None = None,
    market_dir: Path = MARKET_DIR,
    series_dir: Path = SERIES_DIR,
) -> StudyOutputs:
    """검증 #9 를 실행한다.

    Args:
        index_filter: 지수 이름으로 좁힌다 (예: `KOSPI200`). None 이면 전부
        horizons: 보유 기간 목록. None 이면 이 검증의 격자
        market_dir: 원시 시세 폴더
        series_dir: 단일 값 시계열 폴더

    Returns:
        검증 산출물

    Raises:
        ValueError: 잰 짝이 하나도 없는 경우
    """
    grid = horizons_or_default(horizons)
    interest = _load_interest(series_dir)

    futures_cache: dict[str, pd.DataFrame] = {}
    contract_parts: list[pd.DataFrame] = []
    comparison_parts: list[pd.DataFrame] = []
    decomposition_parts: list[pd.DataFrame] = []
    drift_parts: list[pd.DataFrame] = []
    wipeout_parts: list[pd.DataFrame] = []
    roll_parts: list[pd.DataFrame] = []
    windows_by_pair: dict[str, pd.DataFrame] = {}
    skipped: list[tuple[str, str]] = []

    for pair in PAIRS:
        if index_filter is not None and pair.index_name != index_filter:
            continue

        futures_path = market_dir / FUTURES_FILE_TEMPLATE.format(product_id=pair.product_id)
        if not futures_path.is_file():
            skipped.append((pair.target_ticker, f"선물 시세 파일이 없습니다: {futures_path.name}"))
            logger.warning(f"선물 시세가 없어 짝을 건너뜁니다 - {pair.target_ticker}: {futures_path.name}")
            continue

        if pair.product_id not in futures_cache:
            futures_cache[pair.product_id] = load_futures_csv(futures_path)
            for roll_rule in ROLL_RULES:
                _, events = build_continuous_series(futures_cache[pair.product_id], roll_rule)
                events.insert(0, COL_INDEX_NAME, pair.index_name)
                roll_parts.append(events)

        # 정수 계약 대조는 롤 규칙과 무관하다 — 마지막 거래일의 실제 정산가만 쓴다
        series, _ = build_continuous_series(futures_cache[pair.product_id], ROLL_RULES[0])
        contract_parts.append(_integer_contract_table(pair, series))

        outputs = _run_pair(pair, futures_cache[pair.product_id], interest, grid, market_dir)
        comparison_parts.append(outputs.comparison)
        decomposition_parts.append(outputs.decomposition)
        drift_parts.append(outputs.leverage_drift)
        wipeout_parts.append(outputs.wipeouts)
        windows_by_pair[f"{pair.index_name}_{pair.target_ticker}"] = outputs.windows

    if not comparison_parts:
        raise ValueError(f"잰 짝이 하나도 없습니다 - 지수 필터: {index_filter}, 건너뛴 짝: {len(skipped)}개")

    comparison = pd.concat(comparison_parts, ignore_index=True)
    decomposition = pd.concat(decomposition_parts, ignore_index=True)

    logger.debug(f"검증 실행 완료: 짝 {len(comparison_parts)}개, 집계 {len(comparison):,}행, 건너뜀 {len(skipped)}개")

    return StudyOutputs(
        comparison=comparison,
        decomposition=decomposition,
        roll_events=pd.concat(roll_parts, ignore_index=True) if roll_parts else pd.DataFrame(),
        breakeven=_build_breakeven(comparison),
        wipeouts=pd.concat(wipeout_parts, ignore_index=True),
        leverage_drift=pd.concat(drift_parts, ignore_index=True),
        integer_contracts=pd.concat(contract_parts, ignore_index=True),
        windows_by_pair=windows_by_pair,
        pair_count=len(comparison_parts),
        skipped_pairs=skipped,
    )


def _build_breakeven(comparison: pd.DataFrame) -> pd.DataFrame:
    """배수·롤규칙별로 선물이 ETF 를 앞서기 시작하는 보유 기간을 찾는다.

    **격자 상한(3년) 안에서 뒤집히지 않으면 그 사실을 적는다.** 없는 경계를 만들지 않는다.

    Args:
        comparison: 방식별 집계

    Returns:
        `IndexName` · `TargetTicker` · `Multiple` · `Method` · `RollRule` · `BreakevenHorizon` 표
    """
    etf = comparison[comparison[COL_METHOD] == METHOD_ETF]
    rows: list[dict[str, object]] = []

    # **두 방식을 각각 ETF 와 견준다.** 매일 리밸런싱은 「선물로 ETF 를 복제할 수 있는가」에,
    # 그대로 두기는 「그냥 사서 들고 있으면 같은가」에 답한다
    for method in (BASELINE_METHOD, METHOD_FUTURES_HOLD):
        selected = comparison[(comparison[COL_METHOD] == method) & (comparison[COL_INTEREST] == DISPLAY_INTEREST_OFF)]

        for keys, group in selected.groupby([COL_INDEX_NAME, COL_TARGET_TICKER, COL_MULTIPLE, COL_ROLL_RULE]):
            index_name, ticker, multiple, roll_rule = keys
            etf_group = etf[(etf[COL_INDEX_NAME] == index_name) & (etf[COL_TARGET_TICKER] == ticker)]
            merged = group.merge(etf_group, on=COL_HORIZON, suffixes=("_futures", "_etf")).sort_values(COL_HORIZON)

            ahead = merged[merged[f"{COL_MEAN_RETURN}_futures"] > merged[f"{COL_MEAN_RETURN}_etf"]]
            rows.append(
                {
                    COL_INDEX_NAME: index_name,
                    COL_TARGET_TICKER: ticker,
                    COL_MULTIPLE: multiple,
                    COL_METHOD: method,
                    COL_ROLL_RULE: roll_rule,
                    COL_BREAKEVEN_HORIZON: int(ahead[COL_HORIZON].iloc[0]) if not ahead.empty else None,
                    COL_AHEAD_HORIZON_COUNT: len(ahead),
                    COL_TESTED_HORIZON_COUNT: len(merged),
                }
            )

    return pd.DataFrame(rows)
