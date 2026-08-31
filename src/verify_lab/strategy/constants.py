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

# 백테스트 구간의 시작연도. **모든 대상이 이 값을 쓴다** — 종목마다 구간이 갈리면
# 산출물의 시작연도 열을 읽는 사람이 그 차이에 뜻이 있다고 오해한다 (결정 ③).
#
# **성적이 아니라 표본 근거로 고른 값이다.** KODEX 200 기준 축적 550거래일에서 "상위 10위"는
# **상위 1.8%** 라 극단의 뜻이 유지되고(등락률 하한 4.29%, 4% 미만 신호 0건),
# 사건 수가 K=10 은 9→12 · K=20 은 13→20 으로 늘어난다.
#
# 2003 은 축적이 54거래일뿐이라 상위 10위가 **상위 18.5%** 이고 등락률 0.83% 짜리까지 잡혀 탈락했다.
# QQQ 는 첫 신호가 2008-09-29 라 이 값을 앞당겨도 신호 집합이 바뀌지 않는다
START_YEAR: Final = 2005


@dataclass(frozen=True)
class Target:
    """매매 대상 하나

    Attributes:
        dataset: 검증 대상 시세 (`studies` 의 정의를 그대로 쓴다)
        rank_cut: 순위 컷. 이 순위 이내의 등락이면 신호다
        start_year: 이 해부터 신호로 센다. **앞 구간은 순위 축적에만 쓰이므로
            시작연도를 앞당겨도 뒤 구간의 판정은 바뀌지 않는다** — 앞 구간이 더해질 뿐이다
    """

    dataset: Dataset
    rank_cut: int
    start_year: int = START_YEAR


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
#
# **KODEX 200 의 확정 규칙은 K=10 이고 K=20 은 비교축이다** (규칙 문서 §1.1 이 정한다).
# 여기 함께 두는 것은 같은 규칙·같은 산출물로 두 컷을 나란히 놓기 위해서이며, K=20 을 채택한
# 것이 아니다. K=20 은 등락률 하한이 4.79% → 3.63% 로 내려가 약한 신호가 들어온다 —
# 그것이 성적을 희석하는지는 산출물의 두 행을 대조해 판단한다
#
# **시작연도는 전부 기본값이다** — 두 종목 × 두 컷이고 구간 축은 닫혀 있다 (결정 ③).
# 남은 결정은 순위 컷 하나이며 사용자가 판단한다
TARGETS: Final = (
    Target(dataset=_dataset("kodex200"), rank_cut=10),
    Target(dataset=_dataset("kodex200"), rank_cut=20),
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
