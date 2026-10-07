"""이동평균 — 이 저장소의 이동평균은 이 모듈이 낸다

**단순 이동평균(SMA)만 쓴다.** 지수 이동평균은 쓰지 않는다 — 과최적화를 막으려면 보통 쓰는 것 하나로
고정해야 하고, 둘을 나란히 내면 "어느 쪽이 유리한가"를 고를 여지가 생긴다 (루트 `CLAUDE.md` 측정의 원칙 15).
이격도처럼 평균을 쓰는 계산이 같은 산식을 보게 하려고 평균 값 자체를 이 모듈이 소유한다.
"""

import pandas as pd

# 이동평균 창 (거래일). 200일 SMA 를 쓰기로 한 근거는 `docs/조사/역방향.md` 「확정된 설계 결정」 ⑦ 이다
DEFAULT_MA_WINDOW = 200

# 이동평균을 낼 수 있는 최소 창. 값이 하나면 그 값 자신이라 「평균 아래」가 정의되지 않는다
MIN_MA_WINDOW = 2


def simple_moving_average(values: pd.Series, window: int) -> pd.Series:
    """**단순 이동평균(SMA)** 을 낸다 — 그날을 포함한 직전 `window` 개 값의 평균.

    **이 저장소의 이동평균은 이 함수 하나가 낸다** (루트 `CLAUDE.md` 측정의 원칙 15).
    지표마다 각자 평균을 계산하면 같은 원칙이 두 곳에서 다른 답을 낼 수 있다.

    **창이 차기 전은 비운다** — 첫 값이나 0 으로 채우면 초기 구간이 평균처럼 읽힌다.

    Args:
        values: 날짜 오름차순 값 계열 (종가 또는 지수 값)
        window: 이동평균 창 (거래일, `MIN_MA_WINDOW` 이상). **기본값을 두지 않는다** —
            기본값이 있으면 한 매매법의 창이 모든 호출의 창이 된다

    Returns:
        입력과 인덱스가 같은 이동평균 계열. 입력은 변경하지 않는다

    Raises:
        ValueError: 창이 하한 미만인 경우
    """
    if window < MIN_MA_WINDOW:
        raise ValueError(f"이동평균 창은 {MIN_MA_WINDOW} 이상이어야 합니다: {window}")

    return values.astype(float).rolling(window=window).mean()
