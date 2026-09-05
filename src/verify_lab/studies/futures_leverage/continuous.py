"""비율 조정 연속 시계열 구성

선물은 계약이 만기마다 갈리므로 **하나의 긴 가격 계열이 존재하지 않는다.** 그대로 이으면
롤 시점에 근월물과 차월물의 가격 차이(베이시스)가 수익률로 잘못 들어간다. 그래서
**비율 조정(ratio·panama)** 으로 이전 구간 전체에 조정계수를 곱해 이음매를 없앤다.

```
롤 집행일 D 에 근월물 A 에서 차월물 B 로 옮긴다면
    조정계수 f = B 의 D일 정산가 ÷ A 의 D일 정산가
D 이전 전 구간의 가격에 f 를 곱하면 D 의 조정가가 B(D) 가 되어 다음 날과 이어진다
```

**차분 조정을 쓰지 않는다** — 30년을 거슬러 가면 과거 가격이 음수가 된다.
**고정만기 합성(두 근월물 가중평균)도 쓰지 않는다** — 실제로 체결할 수 없는 가격이라
측정의 원칙 9 에 어긋난다.

**가격은 종가가 아니라 정산가로 낸다.** 원월물은 체결이 없는 날이 많아 종가가 결측이고,
거래소는 그런 날에도 정산가를 매긴다.

## 롤 규칙 두 벌을 나란히 낸다 (측정의 원칙 1 — 하나를 고르지 않는다)

| 규칙 | 언제 옮기나 | 미래 참조 |
| --- | --- | --- |
| **미결제약정 역전** | 차월물 미결제약정이 근월물을 넘어선 것을 **확인한 다음 거래일** | 없다 |
| **만기 전 고정** | 근월물 최종거래일의 N거래일 전 | 없다 (아래 참고) |

**미결제약정 규칙에서 판정일 종가에 옮기지 않는 것이 핵심이다.** KRX 미결제약정은 장 마감
후에 확정·공표되므로, 역전을 확인한 날의 종가에 주문을 내는 것은 그 시점에 알 수 없는
정보를 쓰는 것이다 (`src/verify_lab/CLAUDE.md` 측정 계층의 절대 원칙 1).

**만기는 계약의 마지막 거래일로 본다.** 둘째 목요일 규칙을 여기서 다시 구현하지 않는다 —
같은 판정을 두 곳에 두면 조용히 갈라진다(절대 원칙 5). 계약의 최종거래일은 상장 시점에
공표되는 값이므로 그것을 쓰는 것은 미래 참조가 아니지만, **구현이 데이터의 마지막 행에서
그 값을 얻으므로 「계약이 통째로 들어 있는 구간」 안에서만 재현된다.** 계약 중간에서 잘린
입력에서는 만기 전 고정 규칙의 롤 날짜가 달라지며, 그것은 미래 참조가 아니라 입력이
계약을 반토막 낸 결과다.
"""

from dataclasses import dataclass

import pandas as pd

from verify_lab.common_constants import (
    COL_CONTRACT,
    COL_CONTRACT_NAME,
    COL_DATE,
    COL_OPEN_INTEREST,
    COL_SETTLE,
    COL_SPOT,
)
from verify_lab.studies.futures_leverage.constants import (
    COL_ADJUSTMENT_FACTOR,
    COL_DECISION_DATE,
    COL_EXECUTION_DATE,
    COL_FALLBACK,
    COL_FROM_CONTRACT,
    COL_FROM_NAME,
    COL_FROM_OPEN_INTEREST,
    COL_ROLL_RULE,
    COL_TO_CONTRACT,
    COL_TO_NAME,
    COL_TO_OPEN_INTEREST,
    ROLL_DAYS_BEFORE_EXPIRY,
    ROLL_RULE_DAYS_BEFORE_EXPIRY,
    ROLL_RULE_OPEN_INTEREST,
    ROLL_RULES,
)
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 계약 달력의 컬럼
COL_FIRST_DATE = "FirstDate"
COL_LAST_DATE = "LastDate"
COL_ROW_COUNT = "RowCount"

# 연속 계열의 컬럼
COL_ADJUSTED_SETTLE = "AdjustedSettle"
COL_SEGMENT = "Segment"

# 롤 이벤트 표의 컬럼과 dtype. 이벤트가 0건이어도 같은 스키마를 유지해 저장 계층이 분기하지 않게 한다.
# **판정일은 결측을 담을 수 있어야 한다** — 규칙대로 못 한 롤에는 판정일이 없다
ROLL_EVENT_DTYPES = {
    COL_ROLL_RULE: "object",
    COL_DECISION_DATE: "datetime64[ns]",
    COL_EXECUTION_DATE: "datetime64[ns]",
    COL_FROM_CONTRACT: "object",
    COL_FROM_NAME: "object",
    COL_TO_CONTRACT: "object",
    COL_TO_NAME: "object",
    COL_ADJUSTMENT_FACTOR: "float64",
    COL_FROM_OPEN_INTEREST: "float64",
    COL_TO_OPEN_INTEREST: "float64",
    COL_FALLBACK: "bool",
}

# 조정계수의 타당 범위. 근월물과 차월물의 가격 차이는 3개월치 캐리라 몇 %를 넘지 않는다.
# 이 밖으로 나가면 계약을 잘못 짝지었거나 정산가가 잘못 들어온 것이다
MIN_ADJUSTMENT_FACTOR = 0.80
MAX_ADJUSTMENT_FACTOR = 1.20


@dataclass(frozen=True)
class RollEvent:
    """한 번의 롤.

    Attributes:
        decision_date: 역전을 확인한 날. 만기 전 고정 규칙에는 판정일이 없어 None 이다
        execution_date: 옮긴 날. **이 날까지는 근월물을 들고 있다**
        from_contract: 근월물 ISIN
        from_name: 근월물 이름
        to_contract: 차월물 ISIN
        to_name: 차월물 이름
        adjustment_factor: `차월물 정산가 ÷ 근월물 정산가` (집행일 기준)
        from_open_interest: 집행일의 근월물 미결제약정
        to_open_interest: 집행일의 차월물 미결제약정
        fallback: **규칙이 정한 날에 롤하지 못한 경우** True. 두 가지가 여기 해당한다 —
            미결제약정이 끝내 역전되지 않아 최종거래일로 밀린 경우와,
            두 계약이 겹치는 날이 모자라 앞당겨진 경우다.
            둘 다 판정일이 없으므로 그 열로는 구별되지 않는다
    """

    decision_date: pd.Timestamp | None
    execution_date: pd.Timestamp
    from_contract: str
    from_name: str
    to_contract: str
    to_name: str
    adjustment_factor: float
    from_open_interest: float
    to_open_interest: float
    fallback: bool


def build_contract_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """계약별 첫 거래일·마지막 거래일·행 수를 만든다.

    **마지막 거래일이 곧 만기다.** 계약이 만기까지 살아 있는 데이터에서는 참이며,
    아직 살아 있는 계약에서는 데이터의 끝을 가리킨다 — 그 계약은 마지막 구간이라
    거기서 롤하지 않으므로 결과에 영향이 없다.

    Args:
        df: 선물 시세 (`load_futures_csv` 가 돌려준 형태)

    Returns:
        `Contract` · `ContractName` · `FirstDate` · `LastDate` · `RowCount` 컬럼을 갖고
        만기 오름차순으로 정렬된 DataFrame

    Raises:
        ValueError: 입력이 비어 있는 경우
    """
    if df.empty:
        raise ValueError("선물 시세가 비어 있습니다")

    calendar = (
        df.groupby(COL_CONTRACT, sort=False)
        .agg(
            **{
                COL_CONTRACT_NAME: (COL_CONTRACT_NAME, "first"),
                COL_FIRST_DATE: (COL_DATE, "min"),
                COL_LAST_DATE: (COL_DATE, "max"),
                COL_ROW_COUNT: (COL_DATE, "size"),
            }
        )
        .reset_index()
    )

    return calendar.sort_values([COL_LAST_DATE, COL_CONTRACT]).reset_index(drop=True)


def _contract_series(df: pd.DataFrame, contract: str, column: str) -> pd.Series:
    """한 계약의 한 컬럼을 날짜 인덱스 Series 로 뽑는다.

    Args:
        df: 선물 시세
        contract: 계약 ISIN
        column: 뽑을 컬럼

    Returns:
        날짜를 인덱스로 하는 Series
    """
    subset = df.loc[df[COL_CONTRACT] == contract, [COL_DATE, column]]
    return subset.set_index(COL_DATE)[column]


def _next_contract(calendar: pd.DataFrame, current: str) -> pd.Series | None:
    """만기가 바로 다음인 계약을 돌려준다.

    Args:
        calendar: `build_contract_calendar` 의 결과
        current: 지금 들고 있는 계약 ISIN

    Returns:
        차월물의 달력 행. 더 없으면 None
    """
    position = calendar.index[calendar[COL_CONTRACT] == current]
    if position.empty:
        raise RuntimeError(f"내부 불변조건 위반 - 달력에 없는 계약입니다: current={current}")

    following = calendar.loc[position[0] + 1 :]
    return None if following.empty else following.iloc[0]


def _decide_execution_date(
    df: pd.DataFrame,
    rule: str,
    current: str,
    following: str,
    segment_start: pd.Timestamp,
    expiry: pd.Timestamp,
) -> tuple[pd.Timestamp | None, pd.Timestamp, bool]:
    """롤 판정일과 집행일을 정한다.

    Args:
        df: 선물 시세
        rule: 롤 규칙
        current: 근월물 ISIN
        following: 차월물 ISIN
        segment_start: 이 계약을 들기 시작한 날
        expiry: 근월물 최종거래일

    Returns:
        (판정일 또는 None, 집행일, **규칙이 정한 날에 롤하지 못했으면 True**)

    Raises:
        ValueError: 두 계약이 겹치는 거래일이 없는 경우
    """
    current_interest = _contract_series(df, current, COL_OPEN_INTEREST)
    following_interest = _contract_series(df, following, COL_OPEN_INTEREST)

    # 두 계약이 함께 존재하고, 이 구간에 속하며, 만기를 넘지 않는 날만 후보다
    common = current_interest.index.intersection(following_interest.index)
    candidates = common[(common >= segment_start) & (common <= expiry)]
    if candidates.empty:
        raise ValueError(f"두 계약이 겹치는 거래일이 없습니다 - 근월물: {current}, 차월물: {following}")

    if rule == ROLL_RULE_DAYS_BEFORE_EXPIRY:
        # 만기에서 N거래일 앞. 구간이 그보다 짧으면 가능한 가장 이른 날로 앞당긴다.
        # **그 경우를 표시한다** — 규칙이 정한 날이 아닌데 산출물에서 정상 롤과 구별되지 않으면
        # 「만기 전 고정」이 실제로 몇 건에서 지켜졌는지 셀 수 없다
        offset = len(candidates) - 1 - ROLL_DAYS_BEFORE_EXPIRY
        return None, candidates[max(offset, 0)], offset < 0

    if rule != ROLL_RULE_OPEN_INTEREST:
        raise ValueError(f"모르는 롤 규칙입니다: {rule} (가능: {list(ROLL_RULES)})")

    # 미결제약정 역전. **확인한 날의 다음 거래일에 집행한다** — 미결제약정은 장 마감 후 공표된다
    crossed = candidates[following_interest[candidates].to_numpy() > current_interest[candidates].to_numpy()]
    if crossed.empty:
        return None, candidates[-1], True

    decision_date = crossed[0]
    later = candidates[candidates > decision_date]
    if later.empty:
        # **마지막 겹치는 날에 역전됐다. 그날 집행하되 「미결제약정이 정한 롤」이 아니다.**
        # 그날 종가에는 그날의 미결제약정을 알 수 없으므로, 이것을 판정으로 기록하면
        # 미래 참조가 된다. 실제로는 계약이 만기라 어차피 옮겨야 하는 «만기가 강제한 롤» 이며
        # 판정일을 비워 그 사실을 남긴다
        return None, candidates[-1], True

    return decision_date, later[0], False


def plan_rolls(df: pd.DataFrame, rule: str) -> list[RollEvent]:
    """롤 일정을 만든다.

    Args:
        df: 선물 시세 (`load_futures_csv` 가 돌려준 형태)
        rule: 롤 규칙

    Returns:
        시간순 롤 이벤트 목록. 계약이 하나뿐이면 빈 목록

    Raises:
        ValueError: 입력이 비었거나, 모르는 규칙이거나, 조정계수가 타당 범위를 벗어난 경우
    """
    if rule not in ROLL_RULES:
        raise ValueError(f"모르는 롤 규칙입니다: {rule} (가능: {list(ROLL_RULES)})")

    calendar = build_contract_calendar(df)

    # 데이터 첫날에 존재하는 계약 중 만기가 가장 이른 것이 그 시점의 근월물이다
    first_date = df[COL_DATE].min()
    present = calendar[calendar[COL_FIRST_DATE] <= first_date]
    if present.empty:
        raise RuntimeError(f"내부 불변조건 위반 - 첫 거래일에 존재하는 계약이 없습니다: first_date={first_date}")

    current = present.iloc[0]
    segment_start = first_date
    last_date = df[COL_DATE].max()
    events: list[RollEvent] = []

    while True:
        expiry = current[COL_LAST_DATE]

        # **아직 만기가 오지 않은 계약에서는 롤하지 않는다.** 데이터가 끝나는 시점에
        # 살아 있는 계약은 «마지막 거래일» 이 곧 데이터의 끝이라, 만기 기준 롤 규칙이
        # 실제 만기가 아니라 데이터의 끝을 만기로 착각해 롤 날짜가 앞으로 당겨진다.
        # 그러면 집행일이 역전돼 구간이 뒤집힌다 (실측: 코스닥150 에서 시작일이 종료일보다
        # 하루 뒤인 구간이 생겼다). 그 계약을 끝까지 들고 있는 것이 실제 경로다
        if expiry >= last_date:
            break

        following = _next_contract(calendar, str(current[COL_CONTRACT]))
        if following is None:
            break

        decision_date, execution_date, fallback = _decide_execution_date(
            df, rule, str(current[COL_CONTRACT]), str(following[COL_CONTRACT]), segment_start, expiry
        )

        current_settle = _contract_series(df, str(current[COL_CONTRACT]), COL_SETTLE)
        following_settle = _contract_series(df, str(following[COL_CONTRACT]), COL_SETTLE)
        factor = float(following_settle[execution_date] / current_settle[execution_date])

        if not MIN_ADJUSTMENT_FACTOR <= factor <= MAX_ADJUSTMENT_FACTOR:
            raise ValueError(
                f"조정계수가 타당 범위를 벗어났습니다 - 집행일: {execution_date.date()}, "
                f"근월물: {current[COL_CONTRACT]}, 차월물: {following[COL_CONTRACT]}, 계수: {factor:.6f} "
                f"(허용: {MIN_ADJUSTMENT_FACTOR}~{MAX_ADJUSTMENT_FACTOR})"
            )

        if events and execution_date <= events[-1].execution_date:
            raise RuntimeError(
                "내부 불변조건 위반 - 롤 집행일이 뒤로 가지 않습니다: "
                f"직전={events[-1].execution_date.date()}, 이번={execution_date.date()}, "
                f"근월물={current[COL_CONTRACT]}"
            )

        current_interest = _contract_series(df, str(current[COL_CONTRACT]), COL_OPEN_INTEREST)
        following_interest = _contract_series(df, str(following[COL_CONTRACT]), COL_OPEN_INTEREST)

        events.append(
            RollEvent(
                decision_date=decision_date,
                execution_date=execution_date,
                from_contract=str(current[COL_CONTRACT]),
                from_name=str(current[COL_CONTRACT_NAME]),
                to_contract=str(following[COL_CONTRACT]),
                to_name=str(following[COL_CONTRACT_NAME]),
                adjustment_factor=factor,
                from_open_interest=float(current_interest[execution_date]),
                to_open_interest=float(following_interest[execution_date]),
                fallback=fallback,
            )
        )

        current = following
        segment_start = execution_date

    logger.debug(f"롤 일정 확보: {len(events)}건 (규칙 {rule})")

    return events


def build_continuous_series(df: pd.DataFrame, rule: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """비율 조정 연속 시계열과 롤 이벤트 표를 만든다.

    **집행일까지는 근월물을 들고 있다.** 그래서 집행일의 활성 계약은 근월물이고,
    다음 거래일부터 차월물이다.

    Args:
        df: 선물 시세 (`load_futures_csv` 가 돌려준 형태)
        rule: 롤 규칙

    Returns:
        (연속 계열, 롤 이벤트 표) 짝. 연속 계열은 `Date` · `Contract` · `ContractName` ·
        `Settle`(원본 정산가) · `AdjustedSettle`(조정 정산가) · `Spot` · `Segment` 를 갖는다

    Raises:
        ValueError: 입력이 비었거나 규칙을 모르는 경우
    """
    events = plan_rolls(df, rule)
    calendar = build_contract_calendar(df)

    first_date = df[COL_DATE].min()
    present = calendar[calendar[COL_FIRST_DATE] <= first_date]

    # `plan_rolls` 가 같은 조건을 이미 막지만 여기서도 본다 — 한 모듈 안에서 방어 수준이
    # 갈리면 나중에 호출 순서가 바뀌었을 때 이쪽만 무방비로 남는다
    if present.empty:
        raise RuntimeError(f"내부 불변조건 위반 - 첫 거래일에 존재하는 계약이 없습니다: first_date={first_date}")

    segment_contracts = [str(present.iloc[0][COL_CONTRACT])] + [event.to_contract for event in events]

    # 구간 경계. 각 구간은 (시작일, 종료일] 이 아니라 [시작일, 집행일] 이다 —
    # 집행일까지 근월물을 들고 있기 때문이다
    boundaries = [event.execution_date for event in events]
    last_date = df[COL_DATE].max()

    frames: list[pd.DataFrame] = []
    segment_start = first_date

    for index, contract in enumerate(segment_contracts):
        segment_end = boundaries[index] if index < len(boundaries) else last_date
        rows = df[(df[COL_CONTRACT] == contract) & (df[COL_DATE] >= segment_start) & (df[COL_DATE] <= segment_end)]
        if rows.empty:
            raise ValueError(
                f"구간에 해당하는 시세가 없습니다 - 계약: {contract}, " f"구간: {segment_start.date()} ~ {segment_end.date()}"
            )

        segment = rows[[COL_DATE, COL_CONTRACT, COL_CONTRACT_NAME, COL_SETTLE, COL_SPOT]].copy()
        segment[COL_SEGMENT] = index
        frames.append(segment)

        if index < len(boundaries):
            # 다음 구간은 집행일 **다음** 거래일부터다
            later = df.loc[df[COL_DATE] > segment_end, COL_DATE]
            if later.empty:
                break
            segment_start = later.min()

    series = pd.concat(frames, ignore_index=True).sort_values(COL_DATE).reset_index(drop=True)

    # 조정계수는 **그 구간 이후의 모든 롤 계수의 곱**이다. 마지막 구간은 1 이다
    cumulative: list[float] = [1.0]
    for event in reversed(events):
        cumulative.append(cumulative[-1] * event.adjustment_factor)
    cumulative.reverse()

    series[COL_ADJUSTED_SETTLE] = series[COL_SETTLE] * series[COL_SEGMENT].map(dict(enumerate(cumulative)))

    logger.debug(
        f"연속 계열 구성 완료: {len(series):,}행, 구간 {len(segment_contracts)}개, "
        f"기간 {series[COL_DATE].min().date()} ~ {series[COL_DATE].max().date()} (규칙 {rule})"
    )

    return series, roll_events_frame(events, rule)


def roll_events_frame(events: list[RollEvent], rule: str) -> pd.DataFrame:
    """롤 이벤트 목록을 원자료 표로 바꾼다.

    사용자가 차트와 대조하는 자리이므로 **판정일과 집행일을 따로 남긴다** — 둘이 같으면
    미래를 참조한 것이고, 하루 벌어져 있어야 정상이다.

    **이벤트가 없어도 컬럼을 유지한다.** 컬럼 없는 빈 표를 내면 저장 계층이
    「한글 이름이 없는 컬럼」 검사도 못 하고 그대로 죽는다.

    Args:
        events: 롤 이벤트 목록
        rule: 롤 규칙 (표에 함께 남긴다)

    Returns:
        롤 이벤트 표. 이벤트가 없으면 같은 컬럼의 0행 표
    """
    if not events:
        return _empty_roll_events_frame()

    return pd.DataFrame(
        [
            {
                COL_ROLL_RULE: rule,
                COL_DECISION_DATE: event.decision_date,
                COL_EXECUTION_DATE: event.execution_date,
                COL_FROM_CONTRACT: event.from_contract,
                COL_FROM_NAME: event.from_name,
                COL_TO_CONTRACT: event.to_contract,
                COL_TO_NAME: event.to_name,
                COL_ADJUSTMENT_FACTOR: event.adjustment_factor,
                COL_FROM_OPEN_INTEREST: event.from_open_interest,
                COL_TO_OPEN_INTEREST: event.to_open_interest,
                COL_FALLBACK: event.fallback,
            }
            for event in events
        ]
    )


def _empty_roll_events_frame() -> pd.DataFrame:
    """롤이 하나도 없을 때 돌려줄 빈 원자료 표를 만든다.

    값이 없다는 이유로 컬럼과 dtype 이 사라지면 저장 계층이 헤더를 한글로 바꾸지 못하고,
    빈 표라는 사실보다 「스키마가 없다」가 먼저 드러난다. 이 저장소의 다른 빈 표와 같은 관용이다.

    Returns:
        롤 이벤트 표와 같은 구성의 0행 DataFrame
    """
    return pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in ROLL_EVENT_DTYPES.items()})
