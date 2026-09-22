"""사이클 달력 — 그 달 «마지막» 거래일 진입, N개월 뒤 달의 «마지막» 거래일 청산

[중요] **두 규칙의 휴장 처리 방향이 같다 — 둘 다 «앞당김»이다.**

| | 목표일이 휴장이면 | 왜 |
| --- | --- | --- |
| 진입 (9월 마지막 거래일) | **앞당긴다** | 미루면 10월로 넘어가 3분기 밖에서 사게 된다 |
| 청산 (다음해 6월 마지막 거래일) | **앞당긴다** | 미루면 7월로 넘어가 2분기 밖에서 팔게 된다 |

진입이 9월 말이라 **보유가 4분기·1분기·2분기에 정확히 맞아떨어지고**, 그 위에서
분기 분해가 성립한다 (`quarters.py`).

**`measure/calendar_*` 의 기존 함수를 쓸 수 없다.**

- `month_entry_dates` 는 달력일을 목표로 삼아 앞당기므로 **말일이 30일인 달과 31일인 달을
  한 인자로 겨눌 수 없다.** 「그 달의 마지막 거래일」은 달마다 목표일이 다르다
- `month_exit_schedule` 은 **진입 달의** 마지막 거래일을 기준점으로 삼는다.
  이 매매법의 청산은 9개월 뒤 달이라 그 기준점으로는 겨눌 수 없다

**그래서 이 매매법이 자기 달력을 갖는다.** 공통 계층으로 올리지 않는 것은
`src/verify_lab/CLAUDE.md` 가 「공통 계층은 확정 후 · 세 번째가 올 때 정한다」로 정했고
**이것이 첫 번째**이기 때문이다.

**신호와 기준선이 같은 청산 규칙을 쓴다.** 진입만 갈린다 — 신호는 9월 마지막 거래일,
기준선은 **모든 달의** 마지막 거래일이다. 청산을 달리하면 보유 길이가 어긋나 그 차이가
그대로 「기준선 대비 차이」와 우연확률에 실린다.

**끝이 잘린 «마지막» 달을 양쪽에서 뺀다.**

| 뺀 달 | 왜 |
| --- | --- |
| 데이터의 **마지막** 달 (진입) | 그 달이 끝났는지 데이터만으로 알 수 없다 — 「데이터가 끊긴 날」을 그 달의 마지막 거래일로 삼으면 진입일이 실제와 다른 가짜 표본이 된다 |
| 데이터의 **마지막** 달 (청산) | 같은 이유이며, 그때는 보유가 짧아진다 |

**첫 달은 빼지 않는다.** 달 중간부터 시작한 데이터라도 그 달의 **마지막** 거래일은 진짜다 —
진입이 「첫 거래일」이던 시절과 방향이 뒤집힌 자리이므로 되돌리지 않는다.

**제외된 진입은 행으로 남는다.** 값만 비우고 사유가 붙어 `진입 수 = 유효 + 제외` 가
성립한다 — 행을 지우면 표본이 조용히 줄어 생존편향이 생긴다.

거래소 휴장일은 사전에 공표되고 미국 선거 달력은 법으로 고정돼 있으므로 이 판정은
미래를 참조하지 않는다. 다만 구현이 판정일 이후의 데이터에 의존하지 않는지는
look-ahead 감시 테스트로 고정한다.
"""

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_CLOSE, COL_DATE
from verify_lab.data.loader import validate_market_frame
from verify_lab.measure.calendar_entry import validate_trading_days
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_MONTH,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.midterm_cycle.constants import (
    COL_CYCLE_POSITION,
    COL_CYCLE_YEAR,
    CYCLE_POSITION_BY_REMAINDER,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 사이클 한 바퀴의 햇수. 진입 연도를 이 값으로 나눈 나머지가 사이클 위치를 정한다
CYCLE_LENGTH_YEARS = 4

# 달의 허용 범위
MIN_MONTH = 1
MAX_MONTH = 12

# 진입일 표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
CYCLE_ENTRY_DTYPES = {
    COL_CYCLE_YEAR: "int64",
    COL_MONTH: "datetime64[ns]",
    COL_DATE: "datetime64[ns]",
    COL_EXCLUDED_REASON: "object",
}

# 청산 일정표의 컬럼과 dtype
CYCLE_SCHEDULE_DTYPES = {
    COL_CYCLE_YEAR: "int64",
    COL_MONTH: "datetime64[ns]",
    COL_DATE: "datetime64[ns]",
    COL_EXIT_DATE: "datetime64[ns]",
    COL_HOLD_DAYS: "Int64",
    COL_EXCLUDED_REASON: "object",
}

# 수익률 표에 함께 남기는 가격. 사용자가 차트로 직접 대조하는 원자료다 (측정의 원칙 8)
CYCLE_RETURN_COLUMNS = [
    COL_CYCLE_YEAR,
    COL_CYCLE_POSITION,
    COL_MONTH,
    COL_DATE,
    COL_EXIT_DATE,
    COL_HOLD_DAYS,
    COL_ENTRY_CLOSE,
    COL_EXIT_CLOSE,
    # **기준과 구간 축은 남긴다** — `measure.statistics.summarize` 가 요구하는 스키마다
    COL_BASIS,
    COL_HORIZON,
    COL_FORWARD_RETURN,
    COL_EXCLUDED_REASON,
]


def cycle_position(year: int) -> str:
    """진입 연도가 4년 사이클의 어느 자리인지 돌려준다.

    **미국 중간선거는 4로 나눈 나머지가 2인 해**이고 그 달력은 법으로 고정돼 있어
    수십 년 전부터 알 수 있다 — 미래를 참조하는 판정이 아니다 (측정의 원칙 6).

    **진입 연도로 정한다.** 창이 해를 걸치므로 「중간선거해」는 「중간선거 해 10월에 들어가
    다음해 6월에 나온다」는 뜻이며, 청산 연도로 정하면 축이 한 해씩 밀린다.

    Args:
        year: 진입 연도

    Returns:
        `CYCLE_POSITION_BY_REMAINDER` 의 네 값 중 하나

    Raises:
        RuntimeError: 나머지가 넷 중 어디에도 없는 경우 (내부 불변조건 위반)
    """
    remainder = year % CYCLE_LENGTH_YEARS
    position = CYCLE_POSITION_BY_REMAINDER.get(remainder)
    if position is None:
        raise RuntimeError(f"내부 불변조건 위반: 사이클 위치를 정할 수 없습니다 (연도 {year}, 나머지 {remainder})")

    return position


def month_last_entries(trading_days: pd.DatetimeIndex, *, month: int | None = None) -> pd.DataFrame:
    """달마다 **마지막 거래일**을 진입일로 삼는다.

    목표일(그 달 말일)이 휴장이면 **앞당긴다** — 그 달의 마지막 거래일이 곧 진입일이다.
    미루면 익월로 넘어가 다른 매매가 된다.

    **데이터의 마지막 달은 뺀다.** 그 달이 끝났는지 데이터만으로 알 수 없어,
    「데이터가 끊긴 날」을 마지막 거래일로 삼으면 진입일이 실제와 다른 가짜 표본이 된다.
    **첫 달은 빼지 않는다** — 달 중간부터 시작했어도 그 달의 마지막 거래일은 진짜다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        month: 남길 달 (1~12). `None` 이면 모든 달 — **기준선이 이 경로를 쓴다**

    Returns:
        `CYCLE_ENTRY_DTYPES` 구성의 DataFrame. **달마다 한 행**이며 진입 달 오름차순이다

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우,
            달이 범위를 벗어난 경우
    """
    if month is not None and not MIN_MONTH <= month <= MAX_MONTH:
        raise ValueError(f"달은 {MIN_MONTH}~{MAX_MONTH} 이어야 합니다: {month}")
    validate_trading_days(trading_days, purpose="진입일")

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    # **데이터의 마지막 달을 뺀다.** 그 달의 마지막 거래일을 데이터만으로는 알 수 없다
    last_month = days[COL_MONTH].iloc[-1]
    days = days[days[COL_MONTH] < last_month]

    if days.empty:
        logger.debug(f"데이터가 한 달치뿐이라 진입일이 없습니다 (달 {month})")
        return empty_entries()

    # 그 달의 거래일 중 가장 늦은 것이 진입일이다. 목표일이 거래일이면 그날 자신이고
    # 휴장이면 그 이전 마지막 거래일이 된다 — 같은 달 안에서만 고르므로 익월로 넘어가지 않는다
    entry_by_month = days.groupby(COL_MONTH, sort=True)[COL_DATE].max()

    months = pd.DatetimeIndex(entry_by_month.index)
    frame = pd.DataFrame(
        {
            COL_CYCLE_YEAR: months.year,
            COL_MONTH: months,
            COL_DATE: pd.DatetimeIndex(entry_by_month.to_numpy()),
            COL_EXCLUDED_REASON: REASON_NONE,
        }
    )

    if month is not None:
        frame = frame[months.month == month]

    logger.debug(f"진입일 산출: 달 {month}, {len(frame):,}건")

    # **선언한 dtype 으로 맞춘다.** `DatetimeIndex.year` 가 `int32` 라 그대로 두면
    # 빈 표(`int64`)와 dtype 이 갈리는데, 「빈 결과에서도 같은 스키마」가 이 사전의 목적이다 —
    # 어긋나면 한 대상만 그 달에 진입이 없을 때 concat 에서야 드러난다
    return frame[list(CYCLE_ENTRY_DTYPES)].astype(CYCLE_ENTRY_DTYPES).reset_index(drop=True)


def select_positions(entries: pd.DataFrame, positions: tuple[str, ...]) -> pd.DataFrame:
    """산출 축에 있는 사이클 위치의 진입만 남긴다.

    **축 축소를 진입 단계에서 한다** (`설계.md` 결정 ⑬). 뒤에서 거르면 쓰지도 않을 해의
    체결과 시기 5행이 먼저 쌓이고, 「제외 건수」가 산출 축 밖의 진입까지 세게 된다.

    **기준선은 이 함수를 지나지 않는다** — 기준선을 신호와 같은 축으로 좁히는 것은
    집계 단계가 하며(신호에 있는 위치만 남긴다), 그래서 「그 해의 아무 달」 12달이 유지된다.

    Args:
        entries: `month_last_entries` 가 낸 진입일 표
        positions: 남길 사이클 위치

    Returns:
        같은 스키마의 DataFrame. **컬럼 구성과 dtype 이 입력과 같다** —
        아래 계층이 진입 유무에 따라 분기하지 않게 한다. 입력은 변경하지 않는다

    Raises:
        ValueError: 진입일 표에 필요한 컬럼이 없는 경우
    """
    if COL_CYCLE_YEAR not in entries.columns:
        raise ValueError(f"진입일 표에 필수 컬럼이 없습니다: ['{COL_CYCLE_YEAR}']")

    if entries.empty:
        return entries.copy()

    keep = entries[COL_CYCLE_YEAR].map(lambda year: cycle_position(int(year))).isin(positions)

    return entries[keep].reset_index(drop=True)


def month_offset_exit_schedule(
    trading_days: pd.DatetimeIndex,
    entries: pd.DataFrame,
    *,
    month_offset: int,
) -> pd.DataFrame:
    """진입 달로부터 `month_offset` 개월 뒤 달의 **마지막 거래일**에 청산한다.

    목표일(그 달 말일)이 휴장이면 **앞당긴다** — 그 달의 마지막 거래일이 곧 청산일이다.
    미루면 익월로 넘어가 다른 매매가 된다.

    **데이터의 마지막 달은 청산 달로 쓰지 않는다.** 그 달이 끝났는지 데이터만으로 알 수 없어,
    「데이터가 끊긴 날」을 월말로 삼으면 보유가 짧은 가짜 표본이 된다.

    Args:
        trading_days: 거래일 목록. 진입일을 만들 때 넘긴 것과 같아야 한다
        entries: `month_last_entries` 가 낸 진입일 표
        month_offset: 진입 달에서 청산 달까지의 개월 수

    Returns:
        `CYCLE_SCHEDULE_DTYPES` 구성의 DataFrame. **행 수는 진입 수와 같다** —
        청산일을 확정하지 못한 진입도 값만 비운 채 남는다

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우, 진입일 표에 필요한
            컬럼이 없는 경우, 개월 수가 1 미만인 경우, 진입일이 거래일 목록에 없는 경우
    """
    if month_offset < 1:
        raise ValueError(f"개월 수는 1 이상이어야 합니다: {month_offset}")
    validate_trading_days(trading_days, purpose="청산일")

    missing_columns = set(CYCLE_ENTRY_DTYPES) - set(entries.columns)
    if missing_columns:
        raise ValueError(f"진입일 표에 필수 컬럼이 없습니다: {sorted(missing_columns)}")

    if entries.empty:
        return empty_schedule()

    days = pd.DataFrame({COL_DATE: trading_days})
    days[COL_MONTH] = days[COL_DATE].dt.to_period("M").dt.to_timestamp()

    # 1. 달마다 마지막 거래일의 «위치»를 구한다. `days` 의 인덱스가 곧 거래일 위치다
    last_positions = days.groupby(COL_MONTH, sort=True)[COL_DATE].idxmax()
    last_month = days[COL_MONTH].iloc[-1]

    frame = entries.copy()
    entry_months = pd.DatetimeIndex(frame[COL_MONTH])
    exit_months = entry_months + pd.DateOffset(months=month_offset)

    exit_month_position = last_positions.reindex(exit_months).to_numpy()
    has_exit_month = ~pd.isna(exit_month_position)

    # 2. **데이터의 마지막 달은 청산 달로 쓰지 않는다.** 그 달이 끝났는지 알 수 없으므로
    #    그 달의 「마지막 거래일」은 실제 월말이 아니라 데이터가 끊긴 지점이다
    month_complete = np.asarray(exit_months < last_month)
    usable_month = has_exit_month & month_complete

    # 3. 진입일 위치. 진입일은 `month_last_entries` 가 거래일에서 골랐으므로 반드시 있다
    entry_positions = np.asarray(trading_days.get_indexer(pd.DatetimeIndex(frame[COL_DATE])), dtype=np.int64)
    if entry_positions.min() < 0:
        unknown = frame.loc[entry_positions < 0, COL_DATE]
        raise ValueError(f"진입일이 거래일 목록에 없습니다: {[day.date().isoformat() for day in unknown]}")

    exit_positions = np.where(usable_month, exit_month_position, 0).astype(np.int64)

    # 4. 청산이 진입보다 뒤여야 한다. 개월 수가 1 이상이라 정상 경로에서는 언제나 참이지만,
    #    데이터에 달째로 구멍이 있으면 어긋날 수 있으므로 값을 지어내지 않고 제외한다
    usable = usable_month & (exit_positions > entry_positions)

    reasons = np.where(usable, REASON_NONE, REASON_OUT_OF_RANGE)
    frame[COL_EXCLUDED_REASON] = reasons

    frame[COL_EXIT_DATE] = pd.DatetimeIndex(
        np.where(usable, trading_days.to_numpy()[exit_positions], np.datetime64("NaT", "ns"))
    )
    hold_days = np.where(usable, exit_positions - entry_positions, np.nan)
    frame[COL_HOLD_DAYS] = pd.array(hold_days, dtype="Float64").astype("Int64")

    frame = frame[list(CYCLE_SCHEDULE_DTYPES)].reset_index(drop=True)

    excluded = int((frame[COL_EXCLUDED_REASON] != REASON_NONE).sum())
    logger.debug(
        f"청산 일정 산출: 진입 {len(frame):,}건, 제외 {excluded:,}건, 개월 수 {month_offset}, "
        f"보유 분포 {frame[COL_HOLD_DAYS].describe().to_dict()}"
    )

    return frame


def cycle_returns(
    df: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    horizon: int,
    price_column: str = COL_CLOSE,
) -> pd.DataFrame:
    """청산 일정에 가격을 붙여 long-form 수익률을 낸다.

    구간 축(`COL_HORIZON`)에는 실제 보유 거래일 수가 아니라 **표지 하나**를 넣는다.
    보유일수를 넣으면 한 매매가 길이별 여러 칸으로 쪼개져 묶음 값이 나오지 않는다.

    기준은 **종가**뿐이다. 이 매매의 정의가 "진입일 종가 매수 → 청산일 종가 매도"이며
    익일 시가 진입은 다른 매매다.

    **사이클 위치를 여기서 붙인다.** 축이 행 안에 있어야 집계가 그 축으로 묶인다.

    Args:
        df: 날짜 오름차순 가격 데이터. ETF 는 시세 스키마, 지수는 단일 값 계열이다
        schedule: `month_offset_exit_schedule` 의 결과
        horizon: 구간 축에 넣을 묶음 표지. **매매법이 정한다**
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 `Value`

    Returns:
        `CYCLE_RETURN_COLUMNS` 순서의 long-form DataFrame. 행 수는 **진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다. 입력은 변경하지 않는다

    Raises:
        ValueError: 가격 데이터가 비었거나 필수 컬럼이 없는 경우, 날짜가 오름차순이 아닌 경우,
            진입일의 가격이 없는 경우
        RuntimeError: 제외되지 않은 진입의 수익률이 비어 있는 경우 (내부 불변조건 위반)
    """
    validate_market_frame(df, [COL_DATE, price_column])

    if schedule.empty:
        logger.debug("진입이 없습니다")
        return _empty_returns()

    prices = df.set_index(COL_DATE)[price_column]
    frame = schedule.copy()

    entry_price = frame[COL_DATE].map(prices)
    valid = frame[COL_EXCLUDED_REASON] == REASON_NONE
    if entry_price[valid].isna().any():
        unknown = frame.loc[valid & entry_price.isna(), COL_DATE]
        raise ValueError(f"진입일의 가격이 없습니다: {[day.date().isoformat() for day in unknown]}")

    # 제외된 행은 청산일이 비어 있으므로 가격도 비어 있다. `map` 이 그대로 NaN 을 돌려준다
    exit_price = frame[COL_EXIT_DATE].map(prices)

    frame[COL_ENTRY_CLOSE] = entry_price
    frame[COL_EXIT_CLOSE] = exit_price
    frame[COL_BASIS] = ReturnBasis.CLOSE.value
    frame[COL_HORIZON] = horizon
    frame[COL_FORWARD_RETURN] = exit_price / entry_price - 1.0
    frame[COL_CYCLE_POSITION] = [cycle_position(int(year)) for year in frame[COL_CYCLE_YEAR]]

    if not frame.loc[valid, COL_FORWARD_RETURN].notna().all():
        raise RuntimeError("내부 불변조건 위반: 제외되지 않은 진입의 수익률이 비어 있습니다")

    logger.debug(f"수익률 계산 완료: 진입 {len(frame):,}건, 유효 {int(valid.sum()):,}건")

    return frame[CYCLE_RETURN_COLUMNS]


def empty_entries() -> pd.DataFrame:
    """진입일이 하나도 없을 때 돌려줄 빈 표를 만든다.

    Returns:
        진입일 표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in CYCLE_ENTRY_DTYPES.items()})


def empty_schedule() -> pd.DataFrame:
    """진입이 하나도 없을 때 돌려줄 빈 일정표를 만든다.

    Returns:
        일정표와 같은 스키마의 빈 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in CYCLE_SCHEDULE_DTYPES.items()})


def _empty_returns() -> pd.DataFrame:
    """진입이 하나도 없을 때 돌려줄 빈 수익률 표를 만든다.

    값이 없다는 이유로 dtype 이 흔들리면 아래 계층의 집계 키가 진입 유무에 따라 갈린다.

    Returns:
        `CYCLE_RETURN_COLUMNS` 구성의 0행 DataFrame
    """
    empty = empty_schedule()
    empty[COL_CYCLE_POSITION] = pd.Series(dtype=object)
    empty[COL_ENTRY_CLOSE] = pd.Series(dtype="float64")
    empty[COL_EXIT_CLOSE] = pd.Series(dtype="float64")
    empty[COL_BASIS] = pd.Series(dtype=object)
    empty[COL_HORIZON] = pd.Series(dtype="int64")
    empty[COL_FORWARD_RETURN] = pd.Series(dtype="float64")

    return empty[CYCLE_RETURN_COLUMNS]


__all__ = [
    "CYCLE_ENTRY_DTYPES",
    "CYCLE_RETURN_COLUMNS",
    "CYCLE_SCHEDULE_DTYPES",
    "cycle_position",
    "cycle_returns",
    "empty_entries",
    "empty_schedule",
    "month_last_entries",
    "month_offset_exit_schedule",
    "select_positions",
]
