"""매매 규칙 계층의 상수

규칙의 확정 근거는 `docs/strategy/역방향_매매_규칙.md` §3 이 SoT다.
**여기 값은 44건의 과거 신호에 맞춰 고른 것**이며, 성적은 과거 재구성이지 예측이 아니다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.studies.index_extreme.constants import DATASETS, Dataset

# ============================================================
# 손절
# ============================================================

# 손절선은 진입가 기준이며 보유 기간 내내 바뀌지 않는다 — 매일 갱신하면 손실이 이어질 때
# 최악이 무제한으로 열린다. 비율(0.05 = 5%)로 정의한다.
#
# **-5% 는 성적이 가장 좋아서 고른 값이 아니다.** 실측에서 -4%~-10% 구간은 회당 평균이
# +1.27~+1.46% 로 평평해 값 선택이 결과를 만들지 않는다. 이 값을 고른 근거는
# **갭손절(시가가 이미 손절선 아래여서 더 잃는 체결)이 0건이 되는 첫 지점**이라는 것이다 —
# -4% 에서 2건, -3% 에서 4건, -2% 에서 7건이 발생한다.
# 반대로 -4% 아래로 내려가면 매매법 자체가 무너진다(적중률 56.8%). 근거는
# `docs/strategy/역방향_매매_규칙.md` §3.1 의 손절 방식 격자다
STOP_LOSS_LEVEL: Final = 0.05

# ============================================================
# 보유 한도
# ============================================================

# 이익이 나면 그날 즉시 청산하고, 손실일 때만 한도까지 끈다.
# **D+2 로 고정한다** — 3일 구간은 평균 우연확률이 0.2917 로 근거가 없고, D+3 에서만
# 갭손절이 새로 생긴다(밤을 하나 더 넘기므로). D+1 은 KODEX 200 에서 회당 평균이
# +1.57% → +1.38%, 적중률이 75.00% → 68.18% 로 내려간다
HOLD_LIMIT: Final = 2

# ============================================================
# 대상 신호
# ============================================================

# 신호 집계 시작 연도. KODEX 200 은 2002-10-14 상장이라 2003 시작이면 순위 축적이 54거래일뿐이고,
# 등락률 0.83% 짜리까지 "역대 상위"로 잡힌다. 2008 로 늦추면 하한이 4.79% 가 된다 (결정 ③)
START_YEAR: Final = 2008


@dataclass(frozen=True)
class Target:
    """매매 대상 하나

    Attributes:
        dataset: 검증 대상 시세 (`studies` 의 정의를 그대로 쓴다)
        rank_cut: 순위 컷. 이 순위 이내의 등락이면 신호다
    """

    dataset: Dataset
    rank_cut: int


def _dataset(key: str) -> Dataset:
    """데이터셋 목록에서 이름으로 하나를 찾는다.

    Args:
        key: 데이터셋 이름

    Returns:
        해당 데이터셋

    Raises:
        ValueError: 그 이름의 데이터셋이 없는 경우
    """
    for dataset in DATASETS:
        if dataset.key == key:
            return dataset

    raise ValueError(f"알 수 없는 데이터셋입니다: {key}")


# **같은 순위 컷이 두 종목에서 다른 의미다.** 데이터 시작일이 달라 순위 축적량이 959거래일과
# 54거래일로 갈리며, 2008 기준 등락률 하한이 QQQ K=20 은 6.34% 인데 KODEX 200 K=5 는 4.79% 다.
# QQQ 는 K=10 이 7건이라 검정이 붙지 않으므로 K=20 을 함께 둔다 — K=10 은 K=20 의 부분집합이고,
# 강한 신호와 약한 신호의 대비 자체가 결과다 (결정 ②)
TARGETS: Final = (
    Target(dataset=_dataset("kodex200"), rank_cut=10),
    Target(dataset=_dataset("qqq"), rank_cut=10),
    Target(dataset=_dataset("qqq"), rank_cut=20),
)

# ============================================================
# 청산 사유
# ============================================================

# 갭 청산은 **손절선을 지켜주지 못한다.** 시가가 이미 손절선 아래면 그 시가로 나가므로
# 실제 손실이 손절선보다 크다. 이 사실이 보이도록 사유를 따로 둔다
EXIT_GAP_STOP: Final = "갭손절"
EXIT_INTRADAY_STOP: Final = "장중손절"
EXIT_PROFIT: Final = "수익청산"
EXIT_LIMIT: Final = "기한청산"

# ============================================================
# 표시용 레이블
# ============================================================

DISPLAY_TICKER: Final = "종목"
DISPLAY_PARAMETER: Final = "파라미터"
DISPLAY_START_YEAR: Final = "시작연도"
DISPLAY_HOLD_LIMIT: Final = "보유 한도"
DISPLAY_DATE: Final = "날짜"
DISPLAY_DIRECTION: Final = "방향"
DISPLAY_ENTRY_PRICE: Final = "진입가"
DISPLAY_CHANGE_RATE: Final = "등락률(%)"
DISPLAY_EVENT_ID: Final = "사건 번호"
DISPLAY_STOP_LEVEL: Final = "손절선(%)"
DISPLAY_EXIT_REASON: Final = "청산 사유"
DISPLAY_HOLD_DAYS: Final = "보유일"
DISPLAY_RETURN: Final = "수익률(%)"

DISPLAY_SIGNAL_COUNT: Final = "신호"
DISPLAY_EVENT_COUNT: Final = "사건"
DISPLAY_TOTAL: Final = "합계(%)"
DISPLAY_MEAN: Final = "평균(%)"
DISPLAY_WIN_RATE: Final = "승률(%)"
DISPLAY_MAX: Final = "최고(%)"
DISPLAY_MIN: Final = "최악(%)"
DISPLAY_MEAN_HOLD: Final = "평균 보유일"

# 파라미터 표기. `studies` 와 같은 접두사를 쓴다 — 두 산출물을 나란히 놓고 볼 때 갈라지면 안 된다
PARAMETER_PREFIX_RANK_CUT: Final = "K"

# 보유 한도 표기
HOLD_LIMIT_PREFIX: Final = "D+"

# 보유일 평균의 반올림 자릿수. 거래일 수라 소수 둘째 자리면 충분하다
HOLD_DAYS_DECIMALS: Final = 2

# 결과 폴더 이름 뒤에 붙는 이름
STRATEGY_NAME: Final = "reverse_trading"
