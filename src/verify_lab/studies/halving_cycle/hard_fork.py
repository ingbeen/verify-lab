"""반감기_사이클 하드포크 몫 — 체결 격자(`trading.py`)와 달력 분할 손절 표(`split_rule.py`)가 함께 쓴다

**원본가에 없는 몫이라 수익률에 더하지 않는다** (`docs/검증/반감기_사이클/설계.md` 결정 ㊲) — 부르는 쪽이 따로 싣는다.

**`trading.py` 에 두지 않는다** — 그 모듈은 측정 `runner` 를 가져오므로, 측정이 이 함수를 그 모듈에서 가져오면 순환이다.
"""

import math
from collections.abc import Sequence

import pandas as pd

from verify_lab.studies.halving_cycle.constants import HardFork


def hard_fork_share(
    entry_day: pd.Timestamp, exit_day: pd.Timestamp, return_rate: float, forks: Sequence[HardFork]
) -> float:
    """체결 하나가 받은 하드포크 몫을 체결 수익률과 같은 단위(비율)로 낸다.

    **포크 코인을 첫 시세일 종가에 팔아 BTC 를 더 샀다고 본다** (결정 ㊲) — 수정주가가 배당을 재투자한 것으로 보는
    것과 같은 가정이다. 그래서 받은 몫도 청산까지 BTC 와 함께 움직이고, 포크가 둘이면 곱으로 쌓인다.
    **「위」로 든 체결의 몫이다** — 이 매매법은 「위」 하나다(결정 ⑰).

    **「품었다」는 진입일 < 포크일 ≤ 청산일이다.** 진입가는 진입일 종가(다음날 00:00 UTC)라 포크일에 들어가면
    스냅샷 뒤이고, 청산은 청산일 종가라 포크일에 나가면 스냅샷 때 들고 있었다. 포크일 장중에 손절로 나간 체결은
    받은 것으로 센다 — 날짜 단위로는 가를 수 없다.

    Args:
        entry_day: 진입일
        exit_day: 실제 청산일 — 손절로 나갔으면 그날이다
        return_rate: 체결 수익률 (비율). 받은 몫이 청산까지 BTC 와 함께 움직인 배수가 `1 + 이 값` 이다
        forks: 하드포크 목록

    Returns:
        몫 (비율, 0.12 = 12%p). 품은 포크가 없으면 0
    """
    growth = math.prod(1.0 + fork.ratio for fork in forks if entry_day < fork.day <= exit_day)

    return (growth - 1.0) * (1.0 + return_rate)


__all__ = ["hard_fork_share"]
