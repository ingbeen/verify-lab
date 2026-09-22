"""네 조합의 진입·청산 일정 조립 — 계산하지 않는다

진입 둘과 청산 둘을 곱해 네 개의 일정표를 만든다. **달력 계산은 전부
`measure/calendar_entry.py`·`calendar_exit.py` 가 소유하고 여기서는 조립만 한다** —
복제하면 같은 달력이 세 매매법에서 조용히 갈라진다 (패키지 절대 원칙 「판정식 단일화」).

**네 조합이 같은 달 집합을 본다.** 진입 규칙이 달라도 다루는 달이 같아야 조합을 견줄 수 있다.
그래서 **데이터의 마지막 달을 양쪽 다 뺀다** — `month_entry_dates` 는 원래 빼는데
`monthly_expiry_dates` 는 빼지 않아, 그대로 두면 만기 진입만 그 달을 갖고 **말일 청산에서
「데이터가 끊긴 날」이 월말로 잡힌 가짜 표본**이 생긴다 (SPY 2026-08-21 진입 → 08-25 청산,
보유 2일). 시작 쪽도 같은 이유로 맞춰진다 — 만기 진입은 데이터가 중간부터 시작한 달을
못 만들고, 그 달은 행으로 남아 사유가 붙는다.

**주 기준일은 진입일이 아니라 «규칙일»이다.**

| 진입 | 주 기준일 |
| --- | --- |
| 셋째 금요일 | 그 달의 셋째 금요일 (달력일. 휴장이어도 그대로) |
| 20일 | 그 달의 20일 (달력일. 휴장이어도 그대로) |

앞당김은 진입 쪽 사정이라 목표 주까지 끌고 가면 연휴가 낀 달의 보유가 무너진다.
둘 다 「규칙일」을 쓰므로 조합 사이에 기준이 갈리지 않는다.

**기준선 모집단은 «그 진입 규칙이 만들 수 있는 날들»이다.**

| 진입 | 기준선 진입일 |
| --- | --- |
| 셋째 금요일 | **모든 금요일** |
| 20일 | **모든 거래일** |

셋째 금요일 진입에 전 거래일을 쓰면 **주 기준 청산에서 보유 길이가 어긋난다** — 신호는
4~5거래일인데 기준선은 1~9거래일이라 드리프트가 더 붙고, 그 차이가 그대로 「기준선 대비
차이」와 우연확률에 실린다. 옵션 만기일이 같은 이유로 기준선을 만기 요일에 묶는다.

[중요] **말일 청산에서는 보유가 그래도 맞지 않으며 그것이 그 기준선의 «정의»다.**
「그 달 아무 날 진입 → 말일 청산」이므로 월초 진입이 섞여 기준선이 **2.8~3.8거래일 길다**
(실측: `KODEX 200` 20일→말일 신호 6.23일 대 기준선 10.04일). 맞추려고 모집단을 좁히면
「그 달이 원래 그런가」를 묻는 질문 자체가 바뀌고 월말 진입 매매의 기준선과도 갈린다.
**그래서 말일 청산 두 칸의 「기준선 대비 차이」는 주 기준 청산 두 칸과 나란히 읽으면 안 된다** —
그 경고는 `docs/검증/만기_말일/결과.md` 가 갖는다.

**제외된 진입은 행으로 남는다.** 진입일을 못 정한 달도 값만 비우고 사유가 붙어
`진입 수 = 유효 + 제외` 가 성립한다 — 행을 지우면 표본이 조용히 줄어 생존편향이 생긴다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.calendar_entry import (
    every_day_entries,
    month_entry_dates,
    monthly_expiry_dates,
    validate_trading_days,
)
from verify_lab.measure.calendar_exit import (
    month_exit_returns,
    month_exit_schedule,
    weekly_exit_returns,
    weekly_exit_schedule,
)
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_ENTRY_CLOSE,
    COL_EXCLUDED_REASON,
    COL_EXIT_CLOSE,
    COL_EXIT_DATE,
    COL_EXPIRY_DATE,
    COL_FORWARD_RETURN,
    COL_HOLD_DAYS,
    COL_HORIZON,
    COL_MONTH,
    COL_RULE_DATE,
    COL_TARGET_DAY,
    REASON_NO_EXPIRY_DAY,
    REASON_NONE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.studies.expiry_monthend.constants import (
    ENTRY_CALENDAR_DAY,
    ENTRY_DAY,
    ENTRY_EXPIRY,
    EXIT_MONTH_END,
    EXIT_NEXT_WEEK,
    EXIT_OFFSET,
    EXIT_WEEKDAY,
    HORIZON_POOLED,
    THIRD_FRIDAY,
    Combo,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 달력일 진입의 주 기준일을 만들 때 그 달 1일에 더하는 일수. 20일이면 19일을 더한다
_DAYS_FROM_MONTH_START = ENTRY_CALENDAR_DAY - 1

# 조합이 어느 청산을 쓰든 같은 컬럼 구성으로 돌려준다. **두 청산 함수의 고유 축
# (`week_reference`·`month_last_date` 등)은 이 검증이 쓰지 않으므로 여기서 잘라 낸다** —
# 조합마다 컬럼이 다르면 호출부가 조합을 알아야 한다
COMBO_RETURN_COLUMNS = [
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

# 청산 단계가 채우는 컬럼. 진입 단계에서 제외된 행은 **이 다섯이 비어 있다.**
# **기준과 구간 축은 여기 없다** — 그 둘은 「무엇을 재는 표인가」를 말하는 스키마라
# 제외된 행에도 값이 있어야 한다. 비우면 말일 청산은 `-1`, 주 기준 청산은 `NaN` 이 되어
# **같은 계약의 표가 조합마다 dtype 이 갈리고**, `groupby` 가 NaN 키를 버려 조용히 행을 잃는다
_EXIT_COLUMNS = [COL_EXIT_DATE, COL_HOLD_DAYS, COL_ENTRY_CLOSE, COL_EXIT_CLOSE, COL_FORWARD_RETURN]


@dataclass(frozen=True)
class ComboEntries:
    """조합 하나의 진입일과 주 기준일

    Attributes:
        frame: 진입일 표. **달마다 한 행**이며 진입일을 못 정한 달도 값만 비운 채 남는다
        week_references: 그 진입에 대응하는 주 기준일. `frame` 과 길이가 같다.
            **진입일이 없는 행에도 값이 있을 수 있다** — 달력일 진입은 그 달 20일을
            언제나 채우고 만기 진입만 `NaT` 를 낸다. **유효 판정은 `usable` 로 한다**
    """

    frame: pd.DataFrame
    week_references: pd.DatetimeIndex

    @property
    def usable(self) -> pd.Series:
        """청산일을 정할 수 있는 행의 마스크.

        Returns:
            진입 단계에서 제외되지 않은 행이면 True
        """
        return self.frame[COL_EXCLUDED_REASON] == REASON_NONE


def combo_entries(trading_days: pd.DatetimeIndex, combo: Combo) -> ComboEntries:
    """조합의 진입 규칙으로 진입일과 주 기준일을 만든다.

    Args:
        trading_days: 거래일 목록
        combo: 진입 × 청산 조합

    Returns:
        진입일 표와 주 기준일

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
        RuntimeError: 모르는 진입 규칙인 경우 (내부 불변조건 위반)
    """
    if combo.entry == ENTRY_EXPIRY:
        return _expiry_entries(trading_days)
    if combo.entry != ENTRY_DAY:
        raise RuntimeError(f"내부 불변조건 위반: 모르는 진입 규칙입니다: {combo.entry!r} (조합 {combo.key})")

    frame = month_entry_dates(trading_days, calendar_day=ENTRY_CALENDAR_DAY)
    week_references = pd.DatetimeIndex(frame[COL_MONTH]) + pd.to_timedelta(_DAYS_FROM_MONTH_START, unit="D")

    return ComboEntries(frame=frame, week_references=week_references)


def baseline_entries(trading_days: pd.DatetimeIndex, combo: Combo) -> ComboEntries:
    """기준선 「그 진입 규칙이 만들 수 있는 아무 날 진입」의 진입일을 만든다.

    **모집단이 진입 규칙을 따른다** — 셋째 금요일 진입의 기준선은 모든 금요일이고,
    20일 진입의 기준선은 모든 거래일이다. 전 거래일로 통일하면 주 기준 청산에서
    **보유 길이가 신호와 어긋나** 그 차이가 기준선 대비 차이와 우연확률에 실린다.

    **주 기준일이 진입일 자신이다.** 기준선에는 앞당김이 없어 규칙일과 진입일이 같다.

    Args:
        trading_days: 거래일 목록
        combo: 진입 × 청산 조합

    Returns:
        기준선 진입 표

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    frame = every_day_entries(trading_days, calendar_day=ENTRY_CALENDAR_DAY)

    if combo.entry == ENTRY_EXPIRY:
        frame = frame[pd.DatetimeIndex(frame[COL_DATE]).dayofweek == THIRD_FRIDAY.weekday].reset_index(drop=True)

    entry_dates = pd.DatetimeIndex(frame[COL_DATE])

    return ComboEntries(frame=frame, week_references=entry_dates)


def combo_returns(
    df: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    entries: ComboEntries,
    combo: Combo,
    *,
    price_column: str,
) -> pd.DataFrame:
    """조합의 청산 규칙을 적용해 long-form 수익률을 낸다.

    **두 청산의 결과 컬럼이 다르므로 `COMBO_RETURN_COLUMNS` 로 좁혀 돌려준다** —
    조합마다 컬럼이 다르면 호출부가 조합을 알아야 한다.

    Args:
        df: 날짜 오름차순 가격 데이터
        trading_days: 거래일 목록
        entries: `combo_entries` 또는 `baseline_entries` 의 결과
        combo: 진입 × 청산 조합
        price_column: 가격 컬럼 이름. ETF 는 `Close`, 지수는 `Value`

    Returns:
        `COMBO_RETURN_COLUMNS` 구성의 long-form. **행 수는 진입 수와 같다** —
        제외된 진입도 값만 비운 채 남는다

    Raises:
        ValueError: 가격 데이터에 필요한 컬럼이 없거나 진입일의 가격이 없는 경우
        RuntimeError: 모르는 청산 규칙인 경우 (내부 불변조건 위반)
    """
    if combo.exit_rule not in (EXIT_NEXT_WEEK, EXIT_MONTH_END):
        raise RuntimeError(f"내부 불변조건 위반: 모르는 청산 규칙입니다: {combo.exit_rule!r} (조합 {combo.key})")

    if combo.exit_rule == EXIT_MONTH_END:
        schedule = month_exit_schedule(trading_days, entries.frame, exit_offset=EXIT_OFFSET)
        priced = month_exit_returns(df, schedule, horizon=HORIZON_POOLED, price_column=price_column)

        return priced[COMBO_RETURN_COLUMNS].reset_index(drop=True)

    # **주 기준 청산은 유효 행만 넘기고 원래 표에 되붙인다.** `weekly_exit_schedule` 은
    # 진입일이 거래일 목록에 있기를 요구하므로 `NaT` 행을 넘길 수 없는데, 그 행을 버리면
    # 「몇 건이 왜 빠졌는지」가 사라진다 (표본 보존)
    usable = entries.usable
    schedule = weekly_exit_schedule(
        trading_days,
        pd.DatetimeIndex(entries.frame.loc[usable, COL_DATE]),
        pd.DatetimeIndex(entries.week_references[usable.to_numpy()]),
        exit_weekday=EXIT_WEEKDAY,
    )
    priced = weekly_exit_returns(df, schedule, horizon=HORIZON_POOLED, price_column=price_column)

    # **`reindex` 로 되붙인다.** 칸에 값을 대입하면 datetime·`Int64` 컬럼의 dtype 이
    # 실수로 뭉개지고(pandas 가 경고 후 에러로 바꿀 예정), `NaT` 가 `NaN` 이 된다
    result = entries.frame[[COL_MONTH, COL_DATE, COL_EXCLUDED_REASON]].copy()
    priced = priced.set_axis(result.index[usable.to_numpy()])

    for column in _EXIT_COLUMNS:
        result[column] = priced[column].reindex(result.index)

    # **스키마 축은 전 행에 채운다** — 말일 청산과 같은 dtype·같은 값이어야 한다
    result[COL_BASIS] = ReturnBasis.CLOSE.value
    result[COL_HORIZON] = HORIZON_POOLED

    # **진입 단계의 사유를 덮지 않는다** — 그 행은 청산을 시도한 적이 없다
    exit_reasons = priced[COL_EXCLUDED_REASON].reindex(result.index)
    result[COL_EXCLUDED_REASON] = exit_reasons.where(exit_reasons.notna(), result[COL_EXCLUDED_REASON])

    return result[COMBO_RETURN_COLUMNS]


def _expiry_entries(trading_days: pd.DatetimeIndex) -> ComboEntries:
    """셋째 금요일 진입 — 진입일은 만기일, 주 기준일은 규칙일이다.

    **달 집합을 `month_entry_dates` 와 맞춘다** — 데이터의 마지막 달을 빼고, 만기일을 확정하지
    못한 달도 행으로 남긴다. 맞추지 않으면 네 조합이 서로 다른 해를 재게 되고, 말일 청산에서는
    「데이터가 끊긴 날」이 월말로 잡힌 가짜 표본이 생긴다.

    Args:
        trading_days: 거래일 목록

    Returns:
        진입일 표와 주 기준일

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    validate_trading_days(trading_days, purpose="만기일 진입")

    months = pd.DatetimeIndex(trading_days).to_period("M").to_timestamp().unique()
    # **마지막 달을 뺀다.** 그 달이 끝났는지는 데이터만으로 알 수 없고, 말일 청산에서
    # 「데이터가 끊긴 지점」을 월말로 삼으면 보유가 짧은 가짜 표본이 된다
    months = pd.DatetimeIndex(sorted(months)[:-1])

    expiries = monthly_expiry_dates(trading_days, THIRD_FRIDAY)
    if expiries.empty:
        entry_dates = pd.DatetimeIndex([pd.NaT] * len(months))
        rule_dates = entry_dates
    else:
        expiry_dates = pd.DatetimeIndex(expiries[COL_EXPIRY_DATE])
        by_month = pd.DataFrame(
            {COL_DATE: expiry_dates, COL_RULE_DATE: pd.DatetimeIndex(expiries[COL_RULE_DATE])},
            index=expiry_dates.to_period("M").to_timestamp(),
        ).reindex(months)
        entry_dates = pd.DatetimeIndex(by_month[COL_DATE])
        rule_dates = pd.DatetimeIndex(by_month[COL_RULE_DATE])

    missing = np.asarray(entry_dates.isna())
    frame = pd.DataFrame(
        {
            COL_MONTH: months,
            # **격자 축을 맞추기 위한 표지다.** 만기 진입은 달력일을 쓰지 않지만 말일 청산이
            # 같은 스키마를 요구하므로 자리를 채운다
            COL_TARGET_DAY: ENTRY_CALENDAR_DAY,
            COL_DATE: entry_dates,
            COL_EXCLUDED_REASON: np.where(missing, REASON_NO_EXPIRY_DAY, REASON_NONE),
        }
    )

    if missing.any():
        logger.debug(f"만기일을 확정하지 못한 달 {int(missing.sum()):,}개를 제외로 남깁니다")

    return ComboEntries(frame=frame, week_references=rule_dates)


def shared_year_counts(by_combo: dict[str, pd.DataFrame], month: int) -> dict[str, tuple[int, int]]:
    """조합마다 「다른 조합과 같은 해」와 「이 조합만 다른 해」를 센다.

    **네 조합이 언제나 네 개의 다른 매매인 것이 아니다** — 실측으로 절반 가까운 해에
    진입·청산이 둘 다 같다. 조합 간 성적 차이가 실제로 몇 건에서 나온 것인지 이 값이 말해 준다.

    Args:
        by_combo: 조합 이름 → 그 조합의 유효 long-form (진입일·청산일이 들어 있다)
        month: 셀 달 (1~12)

    Returns:
        조합 이름 → (다른 조합과 같은 해 수, 이 조합만 다른 해 수)
    """
    pairs: dict[str, dict[int, tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for label, frame in by_combo.items():
        rows = frame[frame[COL_DATE].dt.month == month]
        pairs[label] = {
            int(entry.year): (entry, exit_date)
            for entry, exit_date in zip(rows[COL_DATE], rows[COL_EXIT_DATE], strict=True)
        }

    counts: dict[str, tuple[int, int]] = {}
    for label, own in pairs.items():
        shared = 0
        for year, pair in own.items():
            if any(other.get(year) == pair for name, other in pairs.items() if name != label):
                shared += 1
        counts[label] = (shared, len(own) - shared)

    return counts


__all__ = [
    "COMBO_RETURN_COLUMNS",
    "ComboEntries",
    "baseline_entries",
    "combo_entries",
    "combo_returns",
    "shared_year_counts",
]
