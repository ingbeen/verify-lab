"""암호화폐 두 수집기가 공유하는 판정

`bitstamp_collector`·`coinmetrics_collector` 는 **같은 하루**를 상대한다 — 비트코인 일봉과
Coin Metrics 일별 값은 둘 다 **UTC 00:00 ~ 24:00** 이 하루이고, 날짜는 그 하루를 가리킨다
(`docs/매매/반감기_사이클/설계.md` 「데이터 실측 기록」). 한국 시각으로는 09:00 에 하루가 바뀐다.

그래서 「아직 끝나지 않은 봉」의 경계 · 「받은 이력의 양 끝이 제자리인가」 · 「빈 날이 있는가」를 **한 벌만** 둔다
(`src/verify_lab/CLAUDE.md` 「측정 계층의 절대 원칙」 5). 두 수집기가 따로 계산하면 한쪽만
하루 밀려도 예외가 나지 않고 저장 범위만 갈린다 — `krx_common.py` 가 국내 세 수집기에 대해 두는 것과 같은 이유다.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final

import pandas as pd

from verify_lab.common_constants import COL_DATE
from verify_lab.data.loader import load_market_csv

# 비트코인 시세를 데이터 오류로 볼 일간 변동 임계 (비율, 0.75 = 75%).
#
# 공용 값(`loader.MAX_DAILY_CHANGE_RATE` 50%)을 쓰면 **Bitstamp 2011-10-28 +56.1% 가 막혀 전 기간을
# 저장할 수 없다** — 원시 시세는 받을 수 있는 전 기간을 남긴다는 계약과 부딪힌다. 실제로 있었던
# 가장 큰 변동(Bitstamp +56.1% · Coin Metrics +54.8%)보다 위이고, **자릿수 오류(×10 = +900% ·
# ÷10 = −90%)는 여전히 걸린다.** 데이터 오류 판정값이지 측정 파라미터가 아니다.
# 수집기와 로더가 **같은 값**을 넘겨야 「저장은 됐는데 읽을 때 막히는」 파일이 생기지 않는다
CRYPTO_MAX_DAILY_CHANGE_RATE: Final = 0.75


def load_crypto_market_csv(path: Path) -> pd.DataFrame:
    """비트코인 시세 CSV 를 비트코인의 급등락 임계값으로 읽는다.

    **임계값을 넘기는 자리를 여기 하나로 둔다.** 공용 로더에 호출마다 넘기면 「수집기와 로더가 같은 값을
    넘긴다」는 약속이 기억에만 걸리고, 넘기지 않은 호출은 2011-10-28 +56.1% 에서 막힌다
    (`docs/매매/반감기_사이클/설계.md` 결정 ③ · 2026-09-29 사용자 결정).

    Args:
        path: 시세 CSV 경로

    Returns:
        날짜 오름차순의 검증된 시세 DataFrame

    Raises:
        ValueError: `load_market_csv` 가 거부하는 모든 경우
    """
    return load_market_csv(path, max_daily_change_rate=CRYPTO_MAX_DAILY_CHANGE_RATE)


def unfinished_utc_day(now: datetime) -> date:
    """아직 끝나지 않은 UTC 날짜를 돌려준다. 그날과 그 뒤의 봉은 확정값이 아니다.

    Args:
        now: 기준 시각. **시간대가 있어야 한다** — 수집기는 `datetime.now(KST)` 를 넘긴다

    Returns:
        `now` 가 속한 UTC 날짜

    Raises:
        ValueError: 시간대가 없는 시각인 경우. 실행 PC 의 시간대로 읽히면 PC 마다 경계가 하루 갈린다
    """
    if now.tzinfo is None:
        raise ValueError(f"시간대가 없는 시각입니다 (KST 처럼 시간대를 붙여 넘기십시오): {now}")

    return now.astimezone(UTC).date()


def exclude_unfinished_days(df: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, int]:
    """UTC 로 끝나지 않은 날의 행을 빼고 뺀 행 수를 함께 돌려준다.

    건수를 함께 내는 것은 표본 보존 때문이다 — 조용히 줄어든 표본은 생존편향을 만든다.

    Args:
        df: 날짜 컬럼(`date` 객체)을 가진 DataFrame. 바꾸지 않는다
        now: 기준 시각 (시간대 필수)

    Returns:
        (제외 후 DataFrame, 제외된 행 수)

    Raises:
        ValueError: `now` 에 시간대가 없는 경우
    """
    cutoff = unfinished_utc_day(now)
    trimmed = df.loc[df[COL_DATE] < cutoff].reset_index(drop=True)

    return trimmed, len(df) - len(trimmed)


def require_complete_range(dates: pd.Series, *, first_day: date, now: datetime, publication_lag_days: int) -> None:
    """받은 이력이 양 끝과 그 사이까지 빈틈없는지 확인한다. **잘린 이력이 전체 파일을 덮지 않게** 저장 전에 부른다.

    세 가지를 본다 — 첫 날이 소스의 첫 날인가, 마지막 날이 끝난 마지막 날에서 허용 지연 안인가,
    그 사이에 빠진 날이 없는가. 빠진 날 수만으로는 양 끝이 잘린 것을 잡지 못하고(사이만 본다), 양 끝만으로는
    중간이 빠진 것을 잡지 못한다 — 서버가 한 번에 주는 개수를 줄이거나 한 페이지를 건너뛰면 **에러 없이**
    그런 파일이 만들어진다. 비트코인은 휴장이 없어 빠진 날은 곧 소스의 결함이다(2026-09-29 사용자 결정 —
    `docs/매매/반감기_사이클/설계.md` 결정 ⑪).

    Args:
        dates: 저장하려는 날짜 목록 (끝나지 않은 날을 뺀 뒤)
        first_day: 그 소스가 주는 첫 날. 받은 첫 날이 이와 달라야 할 이유가 없다
        now: 기준 시각 (시간대 필수). 조회를 시작하기 **전에** 잰 값을 넘긴다
        publication_lag_days: 끝난 날의 값이 소스에 올라오기까지 허용하는 일수. 거래소 봉은 0 이다

    Raises:
        ValueError: 날짜가 없거나, 지연 일수가 음수이거나, 첫 날이 다르거나, 마지막 날이 허용 지연보다 이르거나,
            사이에 빠진 날이 있는 경우
    """
    if publication_lag_days < 0:
        raise ValueError(f"공개 지연 일수는 0 이상이어야 합니다: {publication_lag_days}")
    if dates.empty:
        raise ValueError("날짜 목록이 비어 있어 받은 범위를 확인할 수 없습니다")

    days = pd.to_datetime(dates)
    first = days.min().date()
    last = days.max().date()

    if first != first_day:
        raise ValueError(f"받은 이력의 시작이 {first} 로 소스의 첫 날 {first_day} 와 다릅니다 — 앞이 잘렸거나 소스가 바뀌었습니다. 저장하지 않았습니다")

    latest_finished = unfinished_utc_day(now) - timedelta(days=1)
    if last < latest_finished - timedelta(days=publication_lag_days):
        raise ValueError(
            f"받은 이력의 끝이 {last} 로, 끝난 마지막 날 {latest_finished} 에서 허용 지연 {publication_lag_days}일보다 멉니다 "
            "— 뒤가 잘렸습니다. 저장하지 않았습니다"
        )

    missing = pd.date_range(days.min(), days.max(), freq="D").difference(pd.DatetimeIndex(days))
    if len(missing) > 0:
        raise ValueError(
            f"받은 이력 사이에 빠진 날이 {len(missing)}일 있습니다 — 소스가 날을 빠뜨렸거나 페이지를 건너뛰었습니다. "
            f"메우지 않고 저장하지 않았습니다 (예시: {[day.date() for day in missing[:5]]})"
        )


def count_missing_days(dates: pd.Series) -> int:
    """첫 날과 마지막 날 사이에서 행이 없는 달력일 수를 센다. **메우지 않는다.**

    비트코인은 휴장이 없어 이 값이 0 이 아니면 소스가 날을 빠뜨린 것이다.
    **행 수가 아니라 날짜 종류 수로 센다** — 같은 날이 두 번 있으면 행 수가 빠진 날을 가린다.

    Args:
        dates: 날짜 목록 (`date` 객체 또는 날짜로 바꿀 수 있는 값)

    Returns:
        빠진 달력일 수

    Raises:
        ValueError: 날짜가 하나도 없는 경우
    """
    if dates.empty:
        raise ValueError("날짜 목록이 비어 있어 빠진 날을 셀 수 없습니다")

    days = pd.to_datetime(dates)
    span = (days.max() - days.min()).days + 1

    return span - days.nunique()


__all__ = [
    "CRYPTO_MAX_DAILY_CHANGE_RATE",
    "count_missing_days",
    "exclude_unfinished_days",
    "load_crypto_market_csv",
    "require_complete_range",
    "unfinished_utc_day",
]
