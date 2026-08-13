"""forward return — 신호 이후 구간별 수익률 측정

"이 신호 다음에 실제로 무슨 일이 있었나"를 재는 계층이다. 진입가·손절·익절·자금배분을
넣지 않는다. 매매 규칙을 섞으면 결과가 나빠도 신호 탓인지 규칙 탓인지 분리할 수 없다.

두 기준으로 수익률을 낸다. **출구는 같고 입구만 다르다** — 그래야 두 값의 차이가
"갭으로 새는 몫"이라는 해석이 성립한다.

- **이벤트일 종가 기준**: `D+h 종가 ÷ D 종가 − 1` — 신호가 가진 순수한 예측력
- **익일 시가 기준**: `D+h 종가 ÷ D+1 시가 − 1` — 다음 날 시가에 집행해 실제로 잡을 수 있는 구간

측정 구간은 전부 **거래일**이며 이벤트 발생 다음 거래일부터 센다. 달력일을 섞지 않도록
날짜 연산이 아니라 위치 인덱스로만 계산한다.

반환은 **신호일 × 기준 × 구간을 한 줄씩 담은 long-form** 한 장이다. 구간 끝이 데이터 범위를
넘어가는 칸은 값 없이 사유를 달고 그대로 남는다 — 행을 지우면 표본이 조용히 사라져
생존편향이 생긴다. 행 수는 언제나 `신호 수 × 기준 수 × 구간 수`다.

이 모듈은 파일 하나(가격 기준 하나)만 안다. 국내처럼 원본가와 수정주가를 병기해야 하는
경우는 **호출 측이 같은 계산을 두 번 돌려서** 처리한다.
"""

from collections.abc import Sequence
from enum import Enum

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_OPEN
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 측정 구간 (거래일). docs/spec/index_extreme_events.md §4 가 확정한 값이며
# 호출자가 성과를 보며 돌리는 노브가 아니라 상수다
DEFAULT_HORIZONS = (1, 5, 21, 63, 126, 252)

# 계산에 필요한 시세 컬럼. 나머지 컬럼은 보지 않는다
REQUIRED_MARKET_COLUMNS = [COL_DATE, COL_OPEN, COL_CLOSE]

# 반환 컬럼 (내부 계산용 영문 토큰). 신호일은 시세 스키마의 날짜 컬럼을 그대로 쓴다 —
# 새 이름을 만들면 시세와 대조할 때마다 변환이 붙는다
COL_BASIS = "Basis"
COL_HORIZON = "Horizon"
COL_FORWARD_RETURN = "ForwardReturn"
COL_EXCLUDED_REASON = "ExcludedReason"

RESULT_COLUMNS = [COL_DATE, COL_BASIS, COL_HORIZON, COL_FORWARD_RETURN, COL_EXCLUDED_REASON]

# 제외 건수 요약의 컬럼
COL_SIGNAL_COUNT = "SignalCount"
COL_EXCLUDED_COUNT = "ExcludedCount"

EXCLUDED_SUMMARY_COLUMNS = [COL_BASIS, COL_HORIZON, COL_SIGNAL_COUNT, COL_EXCLUDED_COUNT]

# 제외 사유. 유효한 칸은 빈 문자열이다
REASON_NONE = ""
REASON_OUT_OF_RANGE = "구간 끝이 데이터 범위를 넘음"


class ReturnBasis(Enum):
    """수익률 기준점

    Attributes:
        CLOSE: 이벤트일 종가에서 시작 — 신호의 순수한 예측력
        NEXT_OPEN: 다음 거래일 시가에서 시작 — 실제 집행 가능한 구간
    """

    CLOSE = "close"
    NEXT_OPEN = "next_open"


def compute_forward_returns(
    df: pd.DataFrame,
    signals: pd.Series,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """신호일별로 구간·기준별 forward return 을 계산한다.

    구간 끝이 데이터 범위를 넘어가는 칸은 값을 비우고 제외 사유를 채운다. 행 자체는 남으므로
    `신호 수 = 유효 표본 + 제외 표본` 이 모든 (기준, 구간) 칸에서 성립한다.

    구간이 1 이상이므로 출구(`D+h`)가 존재하면 익일 시가(`D+1`)도 반드시 존재한다.
    따라서 두 기준의 제외 조건은 언제나 같다.

    신호가 하나도 없으면 컬럼 구성을 유지한 빈 프레임을 돌려준다 — 계산 실패가 아니라
    "표본 0건"이라는 정상적인 측정 결과다.

    Args:
        df: 날짜 오름차순 시세 (`data/loader.py` 가 검증해 돌려준 형태)
        signals: 신호인 날이 True 인 bool Series. 인덱스가 `df` 와 같아야 한다
        horizons: 측정 구간 목록 (거래일, 모두 1 이상이며 중복 불가)

    Returns:
        `RESULT_COLUMNS` 순서의 long-form DataFrame.
        행 순서는 신호일 → 기준 → 구간 오름차순이며, 행 수는 `신호 수 × 기준 수 × 구간 수` 다.
        입력은 변경하지 않는다

    Raises:
        ValueError: 시세가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            신호의 길이·인덱스·dtype 이 맞지 않는 경우, 측정 구간이 비었거나
            1 미만이거나 중복된 경우
    """
    ordered_horizons = _validated_horizons(horizons)
    _validate_market(df)
    _validate_signals(df, signals)

    close = df[COL_CLOSE].to_numpy(dtype=float)
    open_prices = df[COL_OPEN].to_numpy(dtype=float)
    dates = df[COL_DATE].to_numpy()

    positions = np.flatnonzero(signals.to_numpy())
    last_position = len(df) - 1

    if positions.size == 0:
        logger.debug(f"신호가 없습니다 (구간 {list(ordered_horizons)})")
        return _empty_result()

    # 1. (기준 → 구간) 순서로 블록을 쌓는다. 이 순서가 뒤의 안정 정렬에서 그대로 유지된다
    blocks: list[pd.DataFrame] = []
    for basis in ReturnBasis:
        for horizon in ordered_horizons:
            targets = positions + horizon
            usable = targets <= last_position

            # 2. 출구는 두 기준 모두 D+h 종가다. 입구만 D 종가와 D+1 시가로 갈린다
            entry = close[positions[usable]] if basis is ReturnBasis.CLOSE else open_prices[positions[usable] + 1]
            values = np.full(len(positions), np.nan)
            values[usable] = close[targets[usable]] / entry - 1.0

            blocks.append(
                pd.DataFrame(
                    {
                        COL_DATE: dates[positions],
                        COL_BASIS: basis.value,
                        COL_HORIZON: horizon,
                        COL_FORWARD_RETURN: values,
                        COL_EXCLUDED_REASON: np.where(usable, REASON_NONE, REASON_OUT_OF_RANGE),
                    }
                )
            )

    # 3. 신호일만 안정 정렬한다. 같은 날 안에서는 블록을 쌓은 순서(기준 → 구간)가 보존된다
    result = pd.concat(blocks, ignore_index=True).sort_values(COL_DATE, kind="stable").reset_index(drop=True)
    result = result[RESULT_COLUMNS]

    excluded = int((result[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(
        f"forward return 계산 완료: 신호 {len(positions):,}건, "
        f"{len(result):,}행 (제외 {excluded:,}칸, 구간 {list(ordered_horizons)})"
    )

    return result


def count_excluded(frame: pd.DataFrame) -> pd.DataFrame:
    """(기준, 구간) 칸별로 신호 수와 제외 건수를 센다.

    표본을 줄이는 처리를 했으면 몇 건이 왜 빠졌는지 함께 내야 한다는 원칙을 위한 요약이다.
    제외가 0건인 칸도 빠뜨리지 않으므로 `신호 수 − 제외 수 = 유효 표본` 을 그대로 읽을 수 있다.

    Args:
        frame: `compute_forward_returns` 의 결과

    Returns:
        `EXCLUDED_SUMMARY_COLUMNS` 순서의 요약표. 기준·구간 오름차순으로 정렬된다

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    missing_columns = {COL_BASIS, COL_HORIZON, COL_EXCLUDED_REASON} - set(frame.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    working = frame[[COL_BASIS, COL_HORIZON, COL_EXCLUDED_REASON]].copy()
    working[COL_EXCLUDED_COUNT] = working[COL_EXCLUDED_REASON] != REASON_NONE

    summary = working.groupby([COL_BASIS, COL_HORIZON], as_index=False, sort=True).agg(
        **{
            COL_SIGNAL_COUNT: (COL_EXCLUDED_REASON, "size"),
            COL_EXCLUDED_COUNT: (COL_EXCLUDED_COUNT, "sum"),
        }
    )
    summary[COL_EXCLUDED_COUNT] = summary[COL_EXCLUDED_COUNT].astype(int)

    return summary[EXCLUDED_SUMMARY_COLUMNS]


def _empty_result() -> pd.DataFrame:
    """신호가 0건일 때의 결과를 만든다.

    빈 프레임을 만들 때도 dtype 을 명시한다. 값이 없다는 이유로 dtype 이 흔들리면
    아래 계층의 집계 키(구간)가 신호 유무에 따라 정수와 실수로 갈린다.

    Returns:
        `RESULT_COLUMNS` 구성을 갖춘 0행 DataFrame
    """
    return pd.DataFrame(
        {
            COL_DATE: pd.Series(dtype="datetime64[ns]"),
            COL_BASIS: pd.Series(dtype=object),
            COL_HORIZON: pd.Series(dtype=int),
            COL_FORWARD_RETURN: pd.Series(dtype=float),
            COL_EXCLUDED_REASON: pd.Series(dtype=object),
        }
    )


def _validated_horizons(horizons: Sequence[int]) -> tuple[int, ...]:
    """측정 구간을 검증하고 오름차순으로 정렬해 돌려준다.

    인자 순서를 그대로 쓰면 같은 데이터로 두 번 돌린 결과의 행 순서가 달라진다.

    Args:
        horizons: 측정 구간 목록 (거래일)

    Returns:
        오름차순으로 정렬된 측정 구간

    Raises:
        ValueError: 비었거나, 1 미만이거나, 중복된 구간이 있는 경우
    """
    ordered = tuple(sorted(horizons))

    if not ordered:
        raise ValueError("측정 구간이 비어 있습니다")

    invalid = [horizon for horizon in ordered if horizon < 1]
    if invalid:
        raise ValueError(f"측정 구간은 1 이상이어야 합니다: {invalid}")

    if len(set(ordered)) != len(ordered):
        raise ValueError(f"측정 구간이 중복됩니다: {list(ordered)}")

    return ordered


def _validate_market(df: pd.DataFrame) -> None:
    """시세가 위치 기반 계산의 전제를 만족하는지 확인한다.

    로더가 이미 결측·0 이하 가격·중복 날짜를 막으므로 그것들은 다시 검사하지 않는다.
    다만 입력의 출처를 알 수 없으므로 정렬만은 직접 확인한다 — 날짜가 뒤섞이면
    위치 기반 계산이 예외 없이 조용히 어긋난다.

    Args:
        df: 시세 DataFrame

    Raises:
        ValueError: 비었거나, 필수 컬럼이 없거나, 날짜가 오름차순이 아닌 경우
    """
    if df.empty:
        raise ValueError("시세 데이터가 비어 있습니다")

    missing_columns = set(REQUIRED_MARKET_COLUMNS) - set(df.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)}")

    if not df[COL_DATE].is_monotonic_increasing:
        raise ValueError("시세가 날짜 오름차순이 아닙니다")


def _validate_signals(df: pd.DataFrame, signals: pd.Series) -> None:
    """신호 Series 가 시세와 같은 축을 쓰는지 확인한다.

    길이나 인덱스가 어긋나면 엉뚱한 날이 신호가 되고, 그 사고는 예외 없이 일어난다.

    Args:
        df: 시세 DataFrame
        signals: 신호 bool Series

    Raises:
        ValueError: 길이·인덱스·dtype 이 맞지 않는 경우
    """
    if len(signals) != len(df):
        raise ValueError(f"신호 길이가 시세와 다릅니다: 신호 {len(signals)}개, 시세 {len(df)}행")

    if not signals.index.equals(df.index):
        raise ValueError("신호 인덱스가 시세와 다릅니다")

    if signals.dtype != bool:
        raise ValueError(f"신호는 bool Series 여야 합니다 (현재 dtype: {signals.dtype})")
