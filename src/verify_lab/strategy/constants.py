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


# ============================================================
# 옵션 만기일 매매 — 손절 격자
# ============================================================

# 확정된 손절선. **진입가 기준이며 보유 기간 내내 바뀌지 않는다.**
#
# **성적이 가장 좋아서 고른 값이 아니다.** 격자 실측에서 무손절이 어느 손절선보다도 나았고
# (7칸 합계 +175.07% 대 최고 +174.43%), 손절의 값은 수익이 아니라 **최악 통제**에 있다.
# 이 값을 고른 근거는 **최악 통제가 포화되는 지점**이라는 것이다 — KODEX 200 9월의
# 2011-09-08 진입 건이 **−5.35% 갭**이라 그보다 좁은 손절선은 전부 그 갭에 뚫리고,
# 최악은 −5.35% 에서 더 줄지 않는데 합계만 계속 깎인다.
# **역방향 매매의 「갭손절 0건의 첫 지점」 논리는 여기서 못 쓴다** — 보유가 5~6거래일이라
# 갭손절 건수가 손절선에 대해 단조롭지 않다. 근거 격자는
# `docs/research/옵션_만기일.md` 12B.2·12B.3·12B.4 에 있다
EXPIRY_STOP_LEVEL: Final = 0.05

# **확정 규칙이 아니라 대조축이다.** 손절선을 다시 고를 때 쓰는 격자이며, 기본 실행에는
# 들어가지 않는다(`--grid` 로만 낸다). **시세를 재수집하면 이 절차를 다시 밟아야 한다** —
# `.claude/rules/strategy.md` 가 「손절선 후보를 격자로 전부 돌려 평평한 구간을 찾는다」를
# 절차로 요구하기 때문이다.
#
# 하한을 -1% 로 연 것은 이 매매의 표준편차가 2.26~3.31% 라 **-1% 대에서 이미 노이즈 손절이
# 나올 것으로 보기 때문**이다. 역방향 매매는 보유가 1~2거래일이라 -2% 부터 열어도 됐지만
# 여기는 5~6거래일이라 손절선이 닿는 빈도가 다르다.
# 상한 -10% 는 전체 월 합계 최악(QQQ -10.65% · SPY -11.16% · DIA -12.14% ·
# KODEX 200 -13.44%)을 다 덮지는 않지만, 그보다 넓히면 손절이 사실상 무손절과 같아진다 —
# 무손절 자체는 `None` 행으로 따로 낸다
EXPIRY_STOP_LEVELS: Final = tuple(round(0.010 + 0.005 * step, 4) for step in range(19))

# 무손절 행의 표기. 격자표에서 손절선 칸에 들어가며, `.claude/rules/strategy.md` 가
# **무손절 성적을 함께 산출하도록** 요구한다 — 손절의 실질 효용은 수익이 아니라 최악 통제라
# 대조 없이는 무엇을 막았는지 보이지 않는다
NO_STOP_LABEL: Final = "무손절"


@dataclass(frozen=True)
class ExpiryCell:
    """옵션 만기일 매매의 대상 칸 하나

    Attributes:
        dataset_key: `studies.option_expiry` 의 데이터셋 이름
        expiry_month: 만기월 (1~12)
        bet_down: 아래로 거는 칸인지 여부. 참이면 원지수가 내려야 이익이다
    """

    dataset_key: str
    expiry_month: int
    bet_down: bool


# `docs/research/옵션_만기일.md` 0장에서 **1차 게이트를 넘은 칸**이다. 전부 금요일 청산이며,
# 앞 일곱은 등급 3/3 이고 **QQQ 12월은 등급 0/3 이지만 게이트를 넘었으므로 함께 둔다.**
#
# **등급으로 칸을 빼지 않는다.** 루트 `CLAUDE.md` 「후보 판정 기준」이
# **"등급은 얼마나 믿을 만한지 알려주되 떨어뜨리지 않는다"** 로 정해져 있다. 등급으로 빼면
# 60칸에서 통계량이 좋은 칸만 고르는 **사후 선택**이 된다 (결정 ㊳).
#
# **미국 9월 세 칸은 같은 날 같은 방향이라 독립된 세 번의 기회가 아니다.** QQQ·SPY·DIA 는
# 같은 시장의 지수 ETF로 상관이 매우 높아 사실상 한 번의 베팅이며, 산출물을 읽을 때
# 세 번의 확인으로 세면 안 된다 (결과 문서 §12A.6). **다만 12월에는 QQQ↔DIA 상관이 0.418 로
# 9월(0.769)보다 훨씬 낮다** — 12월 세 칸은 9월만큼 같이 움직이지 않는다.
#
# **DIA 6월은 뺐다** (2026-09-03, 결정 ㊸). 성적이 낮아서가 아니라 **시기 축이 무너져서**다 —
# 앞 절반 +1.117%(적중 92.9%) → 뒤 절반 **−0.167%**(60.0%) 이고 최근 6년 중 4년이 손실이다.
# `.claude/rules/strategy.md` 의 「시기를 쪼개도 유지되는가」를 판정용 2분할에서 이미 통과하지 못한다
EXPIRY_CELLS: Final = (
    ExpiryCell(dataset_key="dia", expiry_month=12, bet_down=False),
    ExpiryCell(dataset_key="kodex200", expiry_month=9, bet_down=False),
    ExpiryCell(dataset_key="spy", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="dia", expiry_month=9, bet_down=True),
    ExpiryCell(dataset_key="spy", expiry_month=12, bet_down=False),
    ExpiryCell(dataset_key="qqq", expiry_month=9, bet_down=True),
    # 등급 0/3 (우연확률 0.5265 · 기준선 대비 +6.33%p). **통계적 근거가 있어서 넣는 것이
    # 아니라, 뺄 근거가 사후 선택뿐이라 안 빼는 것이다.** 같은 27건으로 맞춰도 적중률이
    # 62.96% 로 DIA(81.48%)·SPY(70.37%)보다 낮아 표본 기간 탓이 아니다
    ExpiryCell(dataset_key="qqq", expiry_month=12, bet_down=False),
)

# 방향 표기. `measure/screening.py` 의 `DIRECTION_UP`·`DIRECTION_DOWN` 과 같은 말을 쓴다 —
# 판정표와 격자표를 나란히 놓고 읽으므로 갈라지면 안 된다
EXPIRY_DIRECTION_DOWN: Final = "아래"
EXPIRY_DIRECTION_UP: Final = "위"

DISPLAY_EXPIRY_MONTH: Final = "만기월"
DISPLAY_ENTRY_DATE: Final = "진입일"
DISPLAY_TARGET_DATE: Final = "청산 목표일"
DISPLAY_EXIT_DATE: Final = "청산일"
DISPLAY_EXIT_PRICE: Final = "청산가"
DISPLAY_EXCLUDED_COUNT: Final = "제외"
DISPLAY_STDEV: Final = "표준편차(%)"
DISPLAY_GAP_STOP_COUNT: Final = "갭손절"
DISPLAY_INTRADAY_STOP_COUNT: Final = "장중손절"

# 결과 폴더 이름 뒤에 붙는 이름
EXPIRY_STRATEGY_NAME: Final = "expiry_trading"


# ============================================================
# 구간 축 (루트 `CLAUDE.md` 측정의 원칙 17)
# ============================================================

# **균등 2분할만으로는 신호가 식는 것을 놓친다.** 실물 사례가 DIA 6월이다 — 2분할에서는
# 앞 92.9% / 뒤 60.0% 로 살아 있어 보였는데 최근 5년만 보면 2/6 이고 회당이 −1.832% 였다.
# 그래서 최근 구간을 함께 낸다.
#
# **3분할과 시장 국면은 넣지 않는다** (결정 ㊵). 33건 3분할은 11건이라 최근 10년과 사실상
# 같은 축이고 5/7칸이 하한 미달이다. 국면은 칸당 하락장 표본이 3~6건이라 성립하지 않는다
PERIOD_ALL: Final = "전체"
PERIOD_FIRST_HALF: Final = "앞 절반"
PERIOD_SECOND_HALF: Final = "뒤 절반"
PERIOD_RECENT_10Y: Final = "최근 10년"
PERIOD_RECENT_5Y: Final = "최근 5년"

EXPIRY_PERIODS: Final = (PERIOD_ALL, PERIOD_FIRST_HALF, PERIOD_SECOND_HALF, PERIOD_RECENT_10Y, PERIOD_RECENT_5Y)

# 「최근 N년」 구간의 N. 경계는 **데이터 마지막 거래일 기준**이다 (결정 ㊷) —
# 실행 시각을 쓰면 코드를 안 고쳐도 날짜가 지나면 결과가 바뀌어 재현되지 않는다
RECENT_YEARS: Final = {PERIOD_RECENT_10Y: 10, PERIOD_RECENT_5Y: 5}

# 그 구간으로 판단해도 되는 표본 하한. 루트 `CLAUDE.md` 측정의 원칙 12 와 같은 값이며,
# **미달이어도 행은 남긴다** — 행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다 (결정 ㊶)
MIN_PERIOD_SAMPLE: Final = 10

DISPLAY_PERIOD: Final = "구간"
DISPLAY_JUDGEABLE: Final = "판정가능"
JUDGEABLE_YES: Final = "예"
JUDGEABLE_NO: Final = "아니오"
