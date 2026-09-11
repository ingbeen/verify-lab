"""구간별 성적 산식 — 매매법을 가리지 않는 공유 계층

체결 목록을 구간으로 갈라 성적 행을 만든다. 구간은 **전체 · 앞 절반 · 뒤 절반 · 최근 10년 ·
최근 5년** 다섯이며, 루트 `CLAUDE.md` 측정의 원칙 17 이 모든 매매법에 요구하는 축이다.

**원칙이 요구하는 것이므로 매매법마다 구현하지 않는다.** 전에는 이 산식이
`expiry_runner.py` 안에 있어 월말이 옵션 만기일 모듈에서 가져다 썼고, 그러면 옵션 만기일
사정으로 고칠 때 월말 성적이 조용히 함께 바뀐다.

**표본이 모자란 구간도 행을 남긴다.** 0건이어도 행이 있고 `판정가능` 이 「아니오」다 —
행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다.

**`사건` 은 번호를 넘긴 매매법만 받는다.** 한 달에 몰린 폭락일을 묶어 세야 하는 매매법
(역방향)은 구간마다 사건 수가 달라지므로 여기서 센다. 신호가 연 1회씩인 매매법
(옵션 만기일·월말)은 신호가 곧 사건이라 **컬럼 자체를 내지 않는다** — 빈칸으로 두면
「세지 못했다」로 읽히고, 같은 값을 두 열에 싣는 것도 대조를 방해한다.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.measure.statistics import judgeable, payoff_from_returns
from verify_lab.report.constants import DATE_FORMAT, PAYOFF_DECIMALS, PERCENT_DECIMALS
from verify_lab.strategy.constants import (
    DISPLAY_BREAKEVEN_WIN_RATE,
    DISPLAY_EVENT_COUNT,
    DISPLAY_EXCLUDED,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_JUDGEABLE,
    DISPLAY_LOSING_COUNT,
    DISPLAY_LOSS_AMOUNT,
    DISPLAY_MAX,
    DISPLAY_MEAN,
    DISPLAY_MEAN_HOLD,
    DISPLAY_MIN,
    DISPLAY_PAYOFF_RATIO,
    DISPLAY_PERIOD,
    DISPLAY_PERIOD_END,
    DISPLAY_PERIOD_START,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_STDEV,
    DISPLAY_TOTAL,
    DISPLAY_WIN_AMOUNT,
    DISPLAY_WIN_RATE,
    EXIT_GAP_STOP,
    EXIT_INTRADAY_STOP,
    HOLD_DAYS_DECIMALS,
    PERIOD_ALL,
    PERIOD_FIRST_HALF,
    PERIOD_SECOND_HALF,
    PERIODS,
    RECENT_YEARS,
)

# 건수 컬럼. **결측을 담을 수 있는 정수형**으로 저장해야 `0.0` 이 아니라 `0` 으로 나간다.
# pandas 의 기본 정수형은 결측을 못 담아 한 행이라도 비면 열 전체가 실수가 된다
NULLABLE_INTEGER: Final = "Int64"

COUNT_COLUMNS: Final = (
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_EXCLUDED,
    DISPLAY_LOSING_COUNT,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_EVENT_COUNT,
)


def period_rows(
    entry_dates: pd.DatetimeIndex,
    returns: Sequence[float],
    *,
    last_day: pd.Timestamp,
    hold_days: Sequence[int] | None = None,
    reasons: Sequence[str] | None = None,
    event_ids: Sequence[int] | None = None,
    excluded_count: int = 0,
) -> list[dict[str, Any]]:
    """체결 목록을 구간별로 갈라 성적 행들을 만든다.

    구간은 `PERIODS` 다 — 전체 · 앞 절반 · 뒤 절반 · 최근 10년 · 최근 5년.
    **균등 2분할만으로는 신호가 식는 것을 놓친다** (루트 `CLAUDE.md` 측정의 원칙 17).

    **표본이 모자란 구간도 행을 남긴다.** 0건이어도 행이 있고 `판정가능` 이 「아니오」다 —
    행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다 (패키지 절대 원칙 「표본 보존」).

    **최근 N년의 경계는 `last_day` 기준이다.** 실행 시각을 쓰면 코드를 안 고쳐도 날짜가
    지나면 결과가 바뀌어 재현되지 않는다.

    Args:
        entry_dates: 신호별 진입일 (시간순)
        returns: 신호별 수익률 (비율). `entry_dates` 와 길이가 같아야 한다
        last_day: 시세의 마지막 거래일. 「최근 N년」의 기준점이다
        hold_days: 신호별 보유 거래일 수. 없으면 평균 보유일을 비운다
        reasons: 신호별 청산 사유. 없으면 손절 건수를 비운다
        event_ids: 신호별 사건 번호. **주면 `사건` 컬럼이 구간마다 따로 세어지고,
            주지 않으면 그 컬럼 자체가 나오지 않는다** — 신호가 연 1회씩인 매매법은
            신호가 곧 사건이라 같은 값이 두 열에 실리고, 빈칸으로 두면 「세지 못했다」로 읽힌다
        excluded_count: 청산일을 확정하지 못해 빠진 진입 수. **전체 행에만 적고
            나머지 구간 행은 비운다** — 구간별 귀속 규칙이 없으므로 `0` 은 거짓이 된다

    Returns:
        구간마다 한 줄씩. 순서는 `PERIODS` 와 같다

    Raises:
        ValueError: 진입일과 수익률의 길이가 다른 경우
    """
    if len(entry_dates) != len(returns):
        raise ValueError(f"진입일과 수익률의 길이가 다릅니다: 진입일 {len(entry_dates)}개, 수익률 {len(returns)}개")

    # **선택 인자도 나란한 배열이다.** 길이가 어긋나면 아래 마스크 적용에서 numpy 가
    # 영문 `IndexError` 를 내고 어느 인자가 잘못됐는지 말해 주지 않는다
    for name, values in (("보유일", hold_days), ("청산 사유", reasons), ("사건 번호", event_ids)):
        if values is not None and len(values) != len(returns):
            raise ValueError(f"{name}의 길이가 수익률과 다릅니다: {name} {len(values)}개, 수익률 {len(returns)}개")

    total = len(returns)
    half = total // 2
    values = np.asarray(returns, dtype=float)
    days = np.asarray(hold_days, dtype=float) if hold_days is not None else None
    labels = np.asarray(reasons, dtype=object) if reasons is not None else None
    events = np.asarray(event_ids, dtype=np.int64) if event_ids is not None else None

    # 홀수면 뒤 절반이 하나 많다. `studies` 의 시기 2등분과 같은 규칙이라 두 산출물이 어긋나지 않는다
    masks: dict[str, np.ndarray] = {
        PERIOD_ALL: np.ones(total, dtype=bool),
        PERIOD_FIRST_HALF: np.arange(total) < half,
        PERIOD_SECOND_HALF: np.arange(total) >= half,
    }
    for period, years in RECENT_YEARS.items():
        masks[period] = np.asarray(entry_dates > last_day - pd.DateOffset(years=years), dtype=bool)

    return [
        _period_row(
            period,
            values[masks[period]],
            days[masks[period]] if days is not None else None,
            labels[masks[period]] if labels is not None else None,
            # **제외는 전체 행에만 적고 나머지는 비운다.** 제외된 신호는 보유 구간이 데이터 끝을
            # 넘어간 것이라 **언제나 가장 최근**인데, 구간 행에 `0` 을 적으면 뒤 절반·최근 N년이
            # 「제외 0건」이라고 **거짓으로 주장한다.** 어느 구간에 귀속되는지는 귀속 규칙을
            # 정해야 알 수 있고(절반 경계는 «위치» 로 정의돼 제외 신호에는 적용되지 않는다)
            # 그것은 별건이므로, 여기서는 「귀속시키지 않았다」를 빈칸으로 남긴다
            excluded_count if period == PERIOD_ALL else np.nan,
            entry_dates[masks[period]],
            events[masks[period]] if events is not None else None,
        )
        for period in PERIODS
    ]


def _period_row(
    period: str,
    values: np.ndarray,
    days: np.ndarray | None,
    labels: np.ndarray | None,
    excluded_count: float,
    entry_dates: pd.DatetimeIndex,
    events: np.ndarray | None,
) -> dict[str, Any]:
    """구간 하나의 집계를 만든다.

    **합계는 「매 신호 같은 금액을 투입」한 수익률의 단순 합이다** (측정의 원칙 16).
    회당 평균만 적으면 크기 감각이 없으므로 둘을 나란히 둔다.

    **표본이 0건이면 지표를 비운다.** 0 으로 채우면 「손실도 이익도 없었다」로 읽히는데
    실제로는 「잰 적이 없다」이다.

    **구간 기간을 함께 낸다.** 구간 이름만으로는 어느 기간인지 알 수 없다 —
    「앞 절반」이 30년 지수에서는 1996~2011 이고 11년 ETF 에서는 2015~2020 이다.
    기간이 다른 행을 한 표에 놓고 비교하게 되므로 그 사실이 행 안에서 드러나야 한다.

    Args:
        period: 구간 이름
        values: 그 구간의 수익률 (비율)
        days: 그 구간의 보유 거래일 수
        labels: 그 구간의 청산 사유
        excluded_count: 제외 건수. 전체 구간이 아니면 `NaN` 이다
        entry_dates: 그 구간의 진입일. 기간의 양 끝을 여기서 낸다
        events: 그 구간의 사건 번호. `None` 이면 `사건` 컬럼을 내지 않는다

    Returns:
        성적표 한 줄
    """
    count = len(values)
    percent = values * RATE_TO_PERCENT
    empty = count == 0
    payoff = payoff_from_returns(values)

    row: dict[str, Any] = {
        DISPLAY_PERIOD: period,
        DISPLAY_SIGNAL_COUNT: count,
        DISPLAY_EXCLUDED: excluded_count,
        DISPLAY_TOTAL: np.nan if empty else round(float(percent.sum()), PERCENT_DECIMALS),
        DISPLAY_MEAN: np.nan if empty else round(float(percent.mean()), PERCENT_DECIMALS),
        DISPLAY_WIN_RATE: np.nan if empty else round(float((values > 0).mean()) * RATE_TO_PERCENT, PERCENT_DECIMALS),
        # **산식은 `measure` 가 소유한다.** 여기서 다시 계산하면 판정 계층과 조용히 갈라진다.
        # 표본이 있는데 진 거래가 0 건인 것은 «사실»이므로 그때는 손익비만 비고 표본은 0 을 적는다
        DISPLAY_PAYOFF_RATIO: np.nan if empty else round(payoff.payoff_ratio, PAYOFF_DECIMALS),
        DISPLAY_BREAKEVEN_WIN_RATE: (
            np.nan if empty else round(payoff.breakeven_hit_rate * RATE_TO_PERCENT, PERCENT_DECIMALS)
        ),
        # **손익비의 분자와 분모를 그대로 낸다.** `docs/strategy/투자금_결정.md` §1.2 가 이 두
        # 값의 출처를 성적표로 적어 두었는데 실제로는 없어서, 계산기 시트를 쓰는 사람이
        # 거래내역에서 직접 계산해야 했다. **`measure` 가 이미 구한 값이라 다시 세지 않는다.**
        #
        # **질 때는 부호를 뒤집어 음수로 낸다** — `측정` 계층은 방향을 모르므로 절대값을 주고,
        # 부호는 방향이 확정된 이 계층이 붙인다. `최악(%)` 이 음수인 것과 같은 관용이다
        DISPLAY_WIN_AMOUNT: np.nan if empty else round(payoff.winning_mean * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_LOSS_AMOUNT: np.nan if empty else round(-payoff.losing_mean * RATE_TO_PERCENT, PERCENT_DECIMALS),
        DISPLAY_LOSING_COUNT: np.nan if empty else payoff.losing_count,
        DISPLAY_MAX: np.nan if empty else round(float(percent.max()), PERCENT_DECIMALS),
        DISPLAY_MIN: np.nan if empty else round(float(percent.min()), PERCENT_DECIMALS),
        # 표본이 하나뿐인 칸에서 표본표준편차는 정의되지 않는다. 0 으로 채우면 "흔들림이 없다"로
        # 읽히므로 비워 둔다
        DISPLAY_STDEV: round(float(percent.std(ddof=1)), PERCENT_DECIMALS) if count > 1 else np.nan,
        # **표본이 없으면 0 이 아니라 빈칸이다.** 0 은 「손절이 걸리지 않았다」로 읽히는데
        # 실제로는 「잰 적이 없다」이며, 같은 행의 다른 지표가 전부 비어 있는 것과 어긋난다.
        # 표본이 있는데 0 건인 것은 사실이므로 그때는 0 을 적는다 (측정의 원칙 17)
        DISPLAY_GAP_STOP_COUNT: np.nan if (empty or labels is None) else int((labels == EXIT_GAP_STOP).sum()),
        DISPLAY_INTRADAY_STOP_COUNT: (
            np.nan if (empty or labels is None) else int((labels == EXIT_INTRADAY_STOP).sum())
        ),
        DISPLAY_MEAN_HOLD: np.nan if (empty or days is None) else round(float(days.mean()), HOLD_DAYS_DECIMALS),
        # **미달이어도 행은 남는다.** 이 컬럼이 「판정에 쓰지 말라」를 표에 남기는 자리다.
        # 식은 `measure` 가 소유한다 — 하한을 바꿔도 한 곳이 안 따라오면 예외 없이 갈라진다
        DISPLAY_JUDGEABLE: judgeable(count),
        # **표본이 없으면 비운다.** 임의의 날짜로 채우면 잰 적이 없는 구간이 잰 것처럼 읽힌다
        DISPLAY_PERIOD_START: np.nan if empty else entry_dates.min().strftime(DATE_FORMAT),
        DISPLAY_PERIOD_END: np.nan if empty else entry_dates.max().strftime(DATE_FORMAT),
    }

    # **사건 수는 번호를 넘긴 매매법만 낸다.** 같은 사건에서 파생된 신호를 묶어 세는 것이
    # 측정의 원칙 5 이고, 구간을 쪼개면 그 수도 구간마다 달라야 한다.
    # 맨 뒤에 붙는 것은 매매법 고유 컬럼이기 때문이다
    if events is not None:
        row[DISPLAY_EVENT_COUNT] = np.nan if empty else int(np.unique(events).size)

    return row


def to_summary_frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """구간 행들을 성적표 프레임으로 만든다.

    **건수 컬럼을 결측을 견디는 정수형으로 바꾼다.** 전체 구간에만 값이 있고 나머지는
    결측인 컬럼(`제외`)이 있어 pandas 가 열을 실수로 만들었고, **세 성적표 전부 `제외` 가
    `0.0` 으로 저장됐다** — 같은 행의 `신호` 는 `51` 인데 말이다. 표본이 0건인 구간이
    하나만 생기면 `질 때 표본`·`갭손절`·`장중손절`·`사건` 도 같은 길로 간다.

    **빈칸은 빈칸으로 남는다.** `0` 으로 채우면 뒤 절반·최근 N년이 「제외 0건」이라고
    거짓으로 주장하게 되고(측정의 원칙 17), 그것이 원래 문제가 뒤집혀 재발하는 것이다.

    **세 매매법이 전부 이 함수를 지난다** — 한 곳에서만 캐스팅해야 매매법마다 갈리지 않는다.

    Args:
        rows: 식별 컬럼이 앞에 붙은 구간 행들

    Returns:
        성적표 프레임. 비어 있으면 빈 DataFrame
    """
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return frame

    for column in COUNT_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].astype(NULLABLE_INTEGER)

    return frame


__all__ = ["COUNT_COLUMNS", "period_rows", "to_summary_frame"]
