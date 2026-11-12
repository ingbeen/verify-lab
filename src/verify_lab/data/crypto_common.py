"""비트코인 시세를 읽는 임계값

비트코인은 주식 · ETF 보다 정상 변동 폭이 커서 공용 급등락 임계값으로는 실제 시세가 막힌다.
그래서 **비트코인 시세를 읽는 자리를 여기 하나로 두고** 그 자산군의 임계값을 함께 둔다
(`docs/매매/반감기_사이클/설계.md` 결정 ③ · ⑮).

받기 쪽 판정(UTC 하루 경계 · 첫 날 · 끝 · 빈틈)은 사본을 만드는 quant-data 가 갖는다.
"""

from pathlib import Path
from typing import Final

import pandas as pd

from verify_lab.data.loader import load_market_csv

# 비트코인 시세를 데이터 오류로 볼 일간 변동 임계 (비율, 0.75 = 75%).
#
# 공용 값(`loader.MAX_DAILY_CHANGE_RATE` 50%)을 쓰면 **Bitstamp 2011-10-28 +56.1% 가 막혀 전 기간을
# 읽을 수 없다.** 실제로 있었던 가장 큰 변동(Bitstamp +56.1% · Coin Metrics +54.8%)보다 위이고,
# **자릿수 오류(×10 = +900% · ÷10 = −90%)는 여전히 걸린다.** 데이터 오류 판정값이지 측정 파라미터가 아니다
CRYPTO_MAX_DAILY_CHANGE_RATE: Final = 0.75


def load_crypto_market_csv(path: Path) -> pd.DataFrame:
    """비트코인 시세 CSV 를 비트코인의 급등락 임계값으로 읽는다.

    **임계값을 넘기는 자리를 여기 하나로 둔다.** 공용 로더에 호출마다 넘기면 넘기지 않은 호출이
    2011-10-28 +56.1% 에서 막힌다 (`docs/매매/반감기_사이클/설계.md` 결정 ③ · 2026-09-29 사용자 결정).

    Args:
        path: 시세 CSV 경로

    Returns:
        날짜 오름차순의 검증된 시세 DataFrame

    Raises:
        ValueError: `load_market_csv` 가 거부하는 모든 경우
    """
    return load_market_csv(path, max_daily_change_rate=CRYPTO_MAX_DAILY_CHANGE_RATE)


__all__ = [
    "CRYPTO_MAX_DAILY_CHANGE_RATE",
    "load_crypto_market_csv",
]
