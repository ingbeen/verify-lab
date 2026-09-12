"""매매 규칙 계층의 상수

규칙의 확정 근거는 `docs/strategy/역방향_매매_규칙.md` §3 이 SoT다.
**여기 값은 과거 신호를 보고 고른 것**이며, 성적은 과거 재구성이지 예측이 아니다.
**표본 수는 시세 기간에 묶여 있으므로 그 문서의 머리말이 기준이다** — 값을 여기 적으면
재수집할 때마다 두 곳이 갈라진다.
"""

from dataclasses import dataclass
from typing import Final

from verify_lab.common_constants import RATE_TO_PERCENT

# **판정가능은 공통 계층이 소유한다** — 측정의 원칙 17 이 모든 계층에 요구하는 개념이라
# 계층마다 새로 만들면 같은 원칙이 다른 답을 낸다. 여기서는 이름만 다시 내보낸다
from verify_lab.measure.constants import COL_JUDGEABLE, JUDGEABLE_NO, JUDGEABLE_YES, MIN_SAMPLE_PER_CELL
from verify_lab.report.constants import DISPLAY_EXCLUDED, DISPLAY_JUDGEABLE, PERCENT_DECIMALS
from verify_lab.studies.reverse.constants import DATASETS, Dataset

__all__ = [
    "COL_JUDGEABLE",
    "DISPLAY_EXCLUDED",
    "DISPLAY_JUDGEABLE",
    "JUDGEABLE_NO",
    "JUDGEABLE_YES",
    "MIN_SAMPLE_PER_CELL",
]

# ============================================================
# 산출물 파일 이름
# ============================================================

# **매매법이 무엇이든 성적표는 `성적표.csv`, 거래내역은 `거래내역.csv` 다.**
# 전에는 같은 뜻의 표가 `summary_by_target.csv` · `summary_by_cell.csv` · `performance.csv`
# 셋이었고, **이름이 매매 스크립트 세 곳에 흩어진 문자열이어서** 그렇게 갈렸다 — 설계가
# 달라서가 아니라 SoT 가 없어서다. 그래서 CLI 가 아니라 이 계층이 이름을 갖는다
# (`scripts/CLAUDE.md` 가 CLI 에 도메인 로직을 금지하는 것과 같은 방향이다).
#
# **한글인 이유**: CSV 헤더가 이미 전부 한글이라 파일명만 영문일 이유가 없다.
# `git config core.precomposeunicode` 가 `true` 라 두 PC 사이에서 깨지지 않는다.
# **`검증/` 폴더 안은 영문 그대로 둔다** — 같은 이름을 붙이면 오히려 다른 것이 같아 보인다
SUMMARY_FILENAME: Final = "성적표.csv"
TRADES_FILENAME: Final = "거래내역.csv"

# 손절선 격자. **기본 실행과 파일명을 나눈다** — 컬럼 구성은 같지만 기본은 확정 손절선 하나,
# 격자는 무손절 + 19개다. 폴더만 보고 어느 쪽인지 알 수 있어야 한다
STOP_GRID_FILENAME: Final = "손절선_격자.csv"

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

# 코스닥 월말 매매의 손절선 격자 (비율, 0.03 = 3%). **하나를 고르지 않고 전부 산출한다.**
#
# **하한이 -3% 인 이유**: 검증 #7 의 손절 격자에서 **-1.0% 가 4칸의 적중률을 60% 아래로
# 무너뜨렸다.** 그보다 좁은 구간은 이미 쓸모없다고 확인됐다.
# **간격이 1%p 인 이유**: 이 매매는 월별 칸당 표본이 10~11건이라 0.5%p 해상도를 표본이
# 지탱하지 못한다. 값 하나를 옮겼을 때 크게 흔들리면 그것은 「좋은 값을 찾았다」가 아니라
# 「표본이 그 지점을 특정할 만큼 크지 않다」는 신호다 (`.claude/rules/strategy.md`)
MONTH_END_STOP_LEVELS: Final = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10)

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

# 손익비와 그 값을 읽는 데 필요한 것. **「손익비」는 측정 계층과 같은 말을 쓰고**
# (두 산출물을 나란히 읽어야 한다), 나머지 둘만 이 계층의 어휘를 쓴다 —
# `strategy/` 는 방향이 확정된 계층이라 「승률」·「질 때」가 무엇인지 정해져 있다
# (`.claude/rules/docs.md` 용어 대응표의 예외).
#
# **질 때 표본은 손익비의 «분모»가 된 건수다.** 이 값이 없으면 5건으로 만든 1.034 와
# 2건으로 만든 16.822 가 같은 무게로 읽힌다 (측정의 원칙 3)
DISPLAY_PAYOFF_RATIO: Final = "손익비"
DISPLAY_BREAKEVEN_WIN_RATE: Final = "손익분기 승률(%)"
DISPLAY_LOSING_COUNT: Final = "질 때 표본"

# 손익비의 **분자와 분모**. `docs/strategy/투자금_결정.md` §1.2 가 이 두 값의 출처를
# 성적표로 적어 두었는데 실제 표에는 없어서, 계산기 시트를 쓰는 사람이 거래내역에서
# 직접 계산해야 했다.
#
# **`이길 때` 는 양수, `질 때` 는 음수다.** `최악(%)` 이 음수인 것과 같은 관용이고,
# 그 문서의 예시(`0.0138` · `-0.0133`)와도 부호가 맞는다. 둘 다 절대값으로 내면
# 표를 읽는 사람이 어느 쪽이 손실인지 이름으로만 판단해야 한다.
#
# **`이길 때 표본` 은 두지 않는다.** `질 때 표본` 은 손익비의 «분모»라 넣은 것이고
# (측정의 원칙 3), 이긴 건수는 `신호 − 질 때 표본 − 보합` 이라 보합 없이는 유도되지 않는다
DISPLAY_WIN_AMOUNT: Final = "이길 때(%)"
DISPLAY_LOSS_AMOUNT: Final = "질 때(%)"

# 파라미터 표기. `studies` 와 같은 접두사를 쓴다 — 두 산출물을 나란히 놓고 볼 때 갈라지면 안 된다
PARAMETER_PREFIX_RANK_CUT: Final = "K"

# 보유일 평균의 반올림 자릿수. 거래일 수라 소수 둘째 자리면 충분하다
HOLD_DAYS_DECIMALS: Final = 2

# **매매법 이름(slug)을 이 계층이 정의하지 않는다.** `studies/<slug>/constants.py` 의 `TRACK_NAME`
# 하나가 소유하고 측정과 매매가 그것을 함께 본다 — 계층은 산출물의 상위 폴더가 말한다.
# 여기에 두면 같은 매매법이 측정 폴더와 매매 폴더에서 다른 이름으로 불린다


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

# 장중 손절을 **잴 수 없는** 대상의 표기. 고가·저가가 없어 장중 최악을 알 수 없는 지수가 여기 해당한다.
#
# **`NO_STOP_LABEL` 과 갈라 둔다.** 앞은 대조축으로 **걸지 않은** 것이고 이것은 **못 건** 것이라
# 두 행이 서로 다른 규칙으로 만들어진 성적이다. 한 값이 둘을 겸하면 「손절을 걸었는데 한 번도
# 안 걸렸다」와 구별되지 않는다.
#
# **겸용을 없앤 실질 효과는 «한 컬럼으로 고를 수 있게 된 것»이다.** 전에는 한 손절선으로 고정한 행을
# 고르려면 `손절선 = 그 숫자 AND 잴 수 있음` 또는 `손절선 = 무손절 AND 잴 수 없음` 두 조건이
# 필요했는데, 표 도구의 필터는 **열끼리 AND** 라 그 조합을 한 번에 걸 수 없다. 그래서 골라낸
# 표를 파일로 따로 냈다. 한 열 안의 다중선택은 OR 이므로 값이 갈린 지금은 필터 하나로 끝난다.
# **실측(월말 4대상)**: 「−5% 또는 무손절」로 걸면 720행이 나와 ETF 대조축 240행이 섞였고,
# 「−5%」만 걸면 240행이 되어 지수 둘이 통째로 빠졌다. 올바른 집합은 480행이다
STOP_NOT_MEASURABLE_LABEL: Final = "손절불가"


def stop_level_value(stop_level: float | None, *, measurable: bool) -> float | str:
    """손절선을 산출물에 싣는 값으로 바꾼다.

    **이 함수가 `손절선(%)` 값 형식의 소유자다.** 전에는 매매법마다 따로 만들어 월말은
    양수 문자열(`"5.0"`), 옵션 만기일은 음수 실수(`-5.0`)를 냈다. 같은 컬럼명에 두 형식이
    담기면 두 산출물을 한 표에서 읽을 수 없고, 조인도 안 된다.

    **음수 실수로 통일했다.** 컬럼 이름이 `손절선(%)` 이므로 `-5.0` 이 곧 「−5% 손절선」으로
    읽힌다. 양수 문자열은 +5% 인지 −5% 인지 이름만으로 드러나지 않고, 문자열이라 정렬이
    사전순이 되어 `"10.0"` 이 `"3.0"` 앞에 왔다.

    **손절선이 없는 경우가 둘이고 값이 갈린다.** 비워 두면 둘 다 「값을 못 구했다」로 읽히는데
    실제로는 「걸지 않았다」(`무손절`)와 「잴 수 없다」(`손절불가`)이고, 뒤쪽만 못 구한 것이다.

    Args:
        stop_level: 손절선 (비율, 0.05 = 5%). `None` 이면 손절선을 걸지 않은 것이다
        measurable: 그 대상에 장중 손절을 **잴 수 있었는지**. 거짓이면 손절 없는 한 줄만 도는 것이
            규칙이므로 `stop_level` 은 반드시 `None` 이다.
            **기본값을 두지 않는다** — 기본이 「잴 수 있다」면 지수를 받는 호출처가 인자를
            빠뜨렸을 때 `무손절` 이 조용히 나가고, 그 표는 한 컬럼 필터에서 틀린 행 집합을 준다.
            잴 수 있음이 로더로 보장되는 매매법도 그 사실을 호출부에 적게 한다

    Returns:
        음수 백분율 실수, 또는 두 표기 중 하나

    Raises:
        RuntimeError: 잴 수 없는 대상에 손절선이 함께 온 경우
    """
    if not measurable:
        if stop_level is not None:
            raise RuntimeError(f"내부 불변조건 위반: 장중 손절을 잴 수 없는 대상에 손절선이 왔습니다 (stop_level={stop_level})")

        return STOP_NOT_MEASURABLE_LABEL

    if stop_level is None:
        return NO_STOP_LABEL

    return round(-stop_level * RATE_TO_PERCENT, PERCENT_DECIMALS)


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

# **이 매매법만 갖는 두 컬럼**이다. 만기월은 축이고, 청산 목표일은 달력이 지목한 날이라
# 실제 청산일과 갈릴 수 있다 (손절로 먼저 나가면 다르다)
DISPLAY_EXPIRY_MONTH: Final = "만기월"
DISPLAY_TARGET_DATE: Final = "청산 목표일"


# ============================================================
# 표시용 레이블 — 세 매매법이 함께 쓴다
# ============================================================

# **옵션 만기일 절에 있던 것을 옮겼다.** 그 자리에 있으면 섹션 이름이 사실과 달라
# 「이 매매법 전용」으로 읽히는데, 셋 다 쓰는 공통 컬럼이다
# (`src/verify_lab/CLAUDE.md` 「매매 산출물 계약」)
DISPLAY_ENTRY_DATE: Final = "진입일"
DISPLAY_EXIT_DATE: Final = "청산일"
DISPLAY_EXIT_PRICE: Final = "청산가"
DISPLAY_STDEV: Final = "표준편차(%)"
DISPLAY_GAP_STOP_COUNT: Final = "갭손절"
DISPLAY_INTRADAY_STOP_COUNT: Final = "장중손절"

# **「장중 손절을 걸 수 있었는가」를 별도 컬럼으로 두지 않는다.** `DISPLAY_STOP_LEVEL` 의
# `STOP_NOT_MEASURABLE_LABEL` 이 그 사실을 이미 말하므로 완전히 유도되는 값이다.
# **잴 수 없는 «이유»**(지수는 종가만 있다 — `docs/spec/월말_진입_설계.md` §7.6)는 값이 아니라
# `summary.json` 의 `notes` 와 규칙 문서가 담는다


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

PERIODS: Final = (PERIOD_ALL, PERIOD_FIRST_HALF, PERIOD_SECOND_HALF, PERIOD_RECENT_10Y, PERIOD_RECENT_5Y)

# 「최근 N년」 구간의 N. 경계는 **데이터 마지막 거래일 기준**이다 (결정 ㊷) —
# 실행 시각을 쓰면 코드를 안 고쳐도 날짜가 지나면 결과가 바뀌어 재현되지 않는다
RECENT_YEARS: Final = {PERIOD_RECENT_10Y: 10, PERIOD_RECENT_5Y: 5}

# 그 구간으로 판단해도 되는 표본 하한은 **공통 계층이 소유한다** (`MIN_SAMPLE_PER_CELL`).
# **미달이어도 행은 남긴다** — 행이 사라지면 사용자가 그 구간을 못 봤다는 사실 자체를 모른다 (결정 ㊶)

DISPLAY_PERIOD: Final = "구간"

# 그 구간이 **실제로 어느 기간인가.** 구간 이름만으로는 알 수 없다 — 「앞 절반」이
# 30년 지수에서는 1996~2011 이고 11년 ETF 에서는 2015~2020 이다. 대상마다 기간이 다른 행을
# 한 표에 놓고 비교하게 되므로, 그 사실이 **행 안에서** 드러나야 한다.
# 값은 그 구간에 실제로 들어간 **진입일의 최소·최대**이며, 표본이 0건이면 비운다
DISPLAY_PERIOD_START: Final = "구간 시작일"
DISPLAY_PERIOD_END: Final = "구간 종료일"
