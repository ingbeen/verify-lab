"""월물 옵션 만기일 산출

만기일은 시세가 아니라 **달력 규칙**이다 — 미국은 셋째 금요일, 한국은 둘째 목요일.
따라서 외부에서 만기일 목록을 받아올 필요가 없고, 필요한 것은 규칙일이 거래일인지 판정할
**거래일 목록** 하나뿐이다. 그 목록은 시세 파일의 날짜 인덱스에서 온다
(`docs/spec/option_expiry.md` 결정 ⑤).

**규칙일이 휴장이면 직전 거래일로 앞당긴다.** 달력상 하루 전이 아니다 — 연휴가 걸리면
직전 거래일이 일주일 넘게 떨어진 달이 실제로 있다(같은 문서 §7.1). 그래서 앞당김 간격은
거래일 수가 아니라 **달력일 수**로 기록한다. 거래일 수로는 언제나 1 이라 정보가 없다.

거래소 휴장일은 사전에 공표되므로 이 판정은 미래를 참조하지 않는다. 다만 구현이 판정일 이후의
데이터에 의존하지 않는지는 look-ahead 감시 테스트로 고정한다.
"""

from datetime import timedelta

import pandas as pd

from verify_lab.studies.option_expiry.constants import (
    COL_ADVANCED_DAYS,
    COL_EXPIRY_DATE,
    COL_EXPIRY_MONTH,
    COL_RULE_DATE,
    ExpiryRule,
)

# 만기일 표에서 만기월을 나타내는 표기. 월 단위 문자열로 두어 CSV 로 나가도 뜻이 유지된다
EXPIRY_MONTH_FORMAT = "%Y-%m"

# 만기일 표의 컬럼과 dtype. 빈 결과에서도 같은 스키마를 유지해 호출 측이 분기하지 않게 한다
EXPIRY_FRAME_DTYPES = {
    COL_EXPIRY_MONTH: "object",
    COL_RULE_DATE: "datetime64[ns]",
    COL_EXPIRY_DATE: "datetime64[ns]",
    COL_ADVANCED_DAYS: "int64",
}


def nth_weekday_of_month(year: int, month: int, weekday: int, ordinal: int) -> pd.Timestamp:
    """그 달의 N번째 지정 요일을 돌려준다.

    Args:
        year: 연도
        month: 월 (1~12)
        weekday: 요일 (월=0 ~ 일=6)
        ordinal: 몇 번째인가 (1부터)

    Returns:
        해당 날짜

    Raises:
        ValueError: 요일·순번이 범위를 벗어났거나, 그 달에 해당 순번이 없는 경우
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"요일은 0(월)~6(일) 이어야 합니다: {weekday}")
    if ordinal < 1:
        raise ValueError(f"순번은 1 이상이어야 합니다: {ordinal}")

    first = pd.Timestamp(year=year, month=month, day=1)
    days_ahead = (weekday - first.dayofweek) % 7 + 7 * (ordinal - 1)
    target = first + timedelta(days=days_ahead)

    # 5번째 요일처럼 그 달에 없는 순번을 요구하면 다음 달로 넘어간다. 이 검증은 2~3번째만 쓰므로
    # 도달하지 않지만, 넘어간 값을 그대로 돌려주면 만기월과 만기일의 달이 어긋난 채 흘러간다
    if target.month != month:
        raise ValueError(f"{year}-{month:02d} 에는 {ordinal}번째 요일 {weekday} 가 없습니다")

    return target


def _validate_trading_days(trading_days: pd.DatetimeIndex) -> None:
    """거래일 목록이 만기일 산출의 전제를 만족하는지 검사한다.

    Args:
        trading_days: 검사할 거래일 목록

    Raises:
        ValueError: 비었거나 정렬·중복 조건을 어긴 경우
    """
    if len(trading_days) == 0:
        raise ValueError("거래일 목록이 비어 있어 만기일을 산출할 수 없습니다")
    if not trading_days.is_monotonic_increasing:
        raise ValueError("거래일 목록이 오름차순으로 정렬되어 있어야 합니다")
    if trading_days.has_duplicates:
        raise ValueError("거래일 목록에 중복된 날짜가 있습니다")


def monthly_expiry_dates(trading_days: pd.DatetimeIndex, rule: ExpiryRule) -> pd.DataFrame:
    """거래일 목록의 전 구간에 대해 월물 만기일을 산출한다.

    규칙일이 거래일이면 그날이 만기일이고, 휴장이면 **직전 거래일**이 만기일이다.
    직전 거래일이 그 달을 벗어나면 그 달은 제외한다 — 데이터가 그 달 중간부터 시작해
    앞 구간이 없는 경우이며, 값을 지어내지 않는다.

    Args:
        trading_days: 거래일 목록. 오름차순 정렬된 중복 없는 인덱스여야 한다
        rule: 만기일 달력 규칙

    Returns:
        만기월·규칙일·만기일·앞당김 달력일수를 담은 DataFrame (만기일 오름차순)

    Raises:
        ValueError: 거래일 목록이 비었거나 정렬·중복 조건을 어긴 경우
    """
    _validate_trading_days(trading_days)

    first_day = trading_days[0]
    last_day = trading_days[-1]

    rows: list[dict[str, object]] = []
    for period in pd.period_range(first_day, last_day, freq="M"):
        rule_date = nth_weekday_of_month(period.year, period.month, rule.weekday, rule.ordinal)

        # 1. 규칙일이 데이터 범위를 벗어나면 만기일을 확정할 수 없다
        if rule_date < first_day or rule_date > last_day:
            continue

        # 2. 규칙일보다 큰 첫 거래일의 위치. 규칙일 자체가 거래일이면 그 위치가 나온다
        position = int(trading_days.searchsorted(rule_date, side="left"))

        if position < len(trading_days) and trading_days[position] == rule_date:
            expiry_date = rule_date
        elif position > 0:
            # 3. 휴장이면 직전 거래일이 만기일이다
            expiry_date = trading_days[position - 1]
        else:
            continue

        # 4. 앞당긴 결과가 그 달을 벗어나면 그 달의 만기일을 확정할 수 없다
        if (expiry_date.year, expiry_date.month) != (period.year, period.month):
            continue

        rows.append(
            {
                COL_EXPIRY_MONTH: period.strftime(EXPIRY_MONTH_FORMAT),
                COL_RULE_DATE: rule_date,
                COL_EXPIRY_DATE: expiry_date,
                COL_ADVANCED_DAYS: int((rule_date - expiry_date).days),
            }
        )

    if not rows:
        return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in EXPIRY_FRAME_DTYPES.items()})

    return pd.DataFrame(rows).sort_values(COL_EXPIRY_DATE, ignore_index=True)
