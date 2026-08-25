"""원달러 그리드의 파라미터 상수

값의 출처는 `docs/spec/usdkrw_grid_rules.md` §12 파라미터 표와 부록 A 이며,
그것을 해석·확정한 결과는 `docs/spec/usdkrw_grid.md` §4 가 SoT다.

**사양서 §12 의 파라미터를 한 번에 다 옮기지 않는다.** 쓰는 계층이 생길 때 그 값을 추가한다 —
소비자가 없는 상수는 "이 값이 어디에 쓰이는가"를 코드에서 답할 수 없고,
사양서가 개정되면 아무도 안 보는 채로 낡는다.
"""

from typing import Final

# ============================================================
# 격자
# ============================================================

# 등비 격자의 앵커. `레벨_k = 앵커 × (1+g)^k` 에서 k=0 인 레벨의 가격이다 (사양서 §3.1).
# **임의 상수이지만 "바꿔도 동일"이 가격표가 같다는 뜻은 아니다** — 500 은 1000 격자 위에
# 있지 않으므로 앵커를 바꾸면 레벨 가격이 전부 이동한다. 성적이 크게 달라지지 않을 뿐이다
GRID_ANCHOR_PRICE: Final = 1000.0

# 익절폭 g 의 기본값 (비율, 0.008 = 0.8%). 사양서 §2.5 의 이론 최적값 `g* = 2c` 에서 왔으며
# 환전 경로 왕복비용 0.40% 의 두 배다. **격자 자체를 바꾸는 파라미터**라 값이 다르면
# 레벨 가격표가 통째로 달라진다
DEFAULT_GROWTH_RATE: Final = 0.008

# 익절폭의 검사 범위 (사양서 §12). **최적값을 고르는 노브가 아니라 결론이 뒤집히는지 보는 축**이다
GROWTH_RATE_CHOICES: Final = (0.008, 0.012, 0.016, 0.024)


# ============================================================
# 동적 범위
# ============================================================

# 룩백 N (년). 범위는 과거 **12N개** 월평균의 min~max 로 잡는다 (사양서 §4.1)
DEFAULT_LOOKBACK_YEARS: Final = 3

# 룩백의 검사 범위 (사양서 §12). 결론이 N 에 의존하는지 보는 축이며,
# **N 에 따라 경로 순위가 뒤집히면 전략이 아니라 N 을 맞춘 것**이다 (§14 축 3)
LOOKBACK_YEAR_CHOICES: Final = (1, 3, 5, 7)

# 한 해에 들어가는 월 수. 룩백을 개월 수로 바꿀 때 쓴다
MONTHS_PER_YEAR: Final = 12

# 최소 범위폭 (비율, 0.20 = 20%). 장기 횡보로 범위가 좁아져 활성 레벨이 과도하게 줄고
# **슬롯 하나가 거대해지는 것**을 막는다 (사양서 §4.2).
# 룩어헤드는 아니지만 원달러 변동폭에 대한 **사전 지식**이 반영된 값이라 발동 여부를 결과에 남긴다
DEFAULT_MIN_RANGE_WIDTH: Final = 0.20

# 최소 범위폭의 검사 범위 (사양서 §12)
MIN_RANGE_WIDTH_CHOICES: Final = (0.15, 0.20, 0.25, 0.30)

# 매매 시작일. 가장 긴 N=7 의 워밍업(12×7=84개월)에 맞춰 통일한다 —
# 그래야 네 개의 N 이 **같은 기간을 겪어** 비교가 성립한다 (사양서 §11.4)
TRADING_START_DATE: Final = "2005-01-01"

# ============================================================
# 범위표 컬럼 (내부 계산용 영문 토큰)
# ============================================================

COL_RANGE_LOW: Final = "RangeLow"
COL_RANGE_HIGH: Final = "RangeHigh"

# 최소폭 강제 **이전**의 원본 범위. 강제가 얼마나 관여했는지는 이 값과의 차이로만 알 수 있다
COL_RAW_RANGE_LOW: Final = "RawRangeLow"
COL_RAW_RANGE_HIGH: Final = "RawRangeHigh"

COL_RANGE_WIDENED: Final = "RangeWidened"
COL_REBALANCED: Final = "Rebalanced"

# 격자를 어디까지 아래로 늘릴지의 **목표 가격**. A안이면 정식 하단과 같고, B안이면
# 직전 재조정 이후 관측된 최저 종가까지 내려간다. **어느 레벨이 켜지는지는 격자 계층이 정하며**
# 이 계층은 가격만 낸다 (결정 C82) — 범위 산출은 익절폭 g 와 무관해야 하기 때문이다
COL_EXTENDED_LOW: Final = "ExtendedLow"


# ============================================================
# 하단 이탈 대응
# ============================================================

# 사양서 §7 의 두 안. **파라미터가 아니라 설계 대안**이라 하나를 고르지 않고 **둘 다 실행해 비교**한다 —
# §12 의 파라미터 표에서도 하단 이탈만 기본값이 「—」이고 검사 방식이 「A / B 병행」이다.
# 그래서 축별 단독 검사 25회에 들어가지 않고 `--path` 처럼 실행을 가른다 (결정 C83)
LOWER_BREACH_HOLD: Final = "A"
LOWER_BREACH_EXTEND: Final = "B"

LOWER_BREACH_CHOICES: Final = (LOWER_BREACH_HOLD, LOWER_BREACH_EXTEND)

# 기본은 A안이다. 지금까지 나온 성적이 전부 A안이라 기본값을 옮기면 **과거 결과와 비교가 끊긴다**
DEFAULT_LOWER_BREACH: Final = LOWER_BREACH_HOLD


# ============================================================
# 자금 배분
# ============================================================

# 3구간 차등의 폭 (비율, 0.5 → 배수 1.5 / 1.0 / 0.5). 비쌀 때 적게, 쌀 때 많이 산다.
# **±s 대칭이라 자유 파라미터가 하나로 줄어든다** — 1.5/1.0/0.7 같은 비대칭은
# 두 숫자를 각각 정당화해야 한다 (사양서 §5.1)
DEFAULT_ALLOCATION_SPREAD: Final = 0.5

# 차등의 검사 범위 (사양서 §12)
ALLOCATION_SPREAD_CHOICES: Final = (0.3, 0.5, 0.7)

# 3구간의 경계 (위치, 0=하단 ~ 1=상단). **정확한 3등분**이며 사양서 §5.1 의 0.33·0.67 은
# 이 값의 소수 둘째 자리 반올림 표기다. 문자 그대로 쓰면 중간부 0.34·상단부 0.33 으로
# 의도하지 않은 비대칭이 생긴다. 경계값은 **위 구간**에 들어간다
LOWER_BAND_LIMIT: Final = 1.0 / 3.0
UPPER_BAND_LIMIT: Final = 2.0 / 3.0

# 슬롯 하나에 넣을 수 있는 총자산 대비 상한 (비율, 0.08 = 8%).
# 범위가 좁아졌을 때 슬롯 하나가 거대해지는 것을 막는다 (사양서 §5.3).
# **상한이 걸리면 하단부와 중간부가 같은 금액이 되어 차등이 소멸**하지만, 좁은 범위에서
# 노출을 줄이는 것이 주목적이므로 그 퇴화는 수용하고 **발동 횟수를 기록**한다
DEFAULT_SLOT_CAP_RATIO: Final = 0.08

# 슬롯 상한의 검사 범위 (사양서 §12)
SLOT_CAP_RATIO_CHOICES: Final = (0.06, 0.08, 0.10, 0.12)


# ============================================================
# 거래비용
# ============================================================

# 환전 스프레드 편도 (비율, 0.0008 = 0.08%). 실계좌 환전 영수증에서 역산한 기본 스프레드
# **0.783%** 에 우대 90% 를 적용한 값이며, 사양서 §10.1 의 「기본 1.0% → 편도 0.10%」를 대체한다.
# 우대율은 프로모션·금액·시간대로 변하고 21년 백테스트에 오늘의 우대율을 소급하는 것 자체가
# 반사실적이므로, **비용은 전 기간에 걸쳐 낙관적으로 잡혀 있다**
DEFAULT_EXCHANGE_SPREAD_RATE: Final = 0.0008

# 환전 스프레드의 검사 범위. 우대 95% 실측 그대로 / 확정값 / 사양서 원안 순이다.
# **성적이 좋아지는 값을 고르는 노브가 아니라** 결론이 스프레드 가정에 의존하는지 보는 축이다
EXCHANGE_SPREAD_RATE_CHOICES: Final = (0.00039, 0.0008, 0.0010)

# 슬리피지 편도 (비율, 0.0010 = 0.10%). **전 경로 공통**이며 사양서 §6.6 의
# 「15:20 판정과 종가의 차이」를 흡수한 **실측되지 않은 가정**이다. 스프레드를 낮출수록
# 남는 왕복비용에서 이 몫이 커지므로, 한 항만 정밀하게 다듬어도 전체 정밀도는 올라가지 않는다.
# 사양서 §12 의 파라미터 표에 없어 검사 축이 아니다.
# **ETF 의 낮은 유동성과 LP 호가 스프레드도 이 가정 안에 흡수된 것으로 본다** (사양서 §10.2)
DEFAULT_SLIPPAGE_RATE: Final = 0.0010

# ETF 위탁수수료 편도 (비율, 0.00015 = 0.015%). 왕복 0.03% 이며 사양서 §10 과 부록 B 의
# 토스증권 기준이다. **환전 경로에는 붙지 않는다**
DEFAULT_BROKERAGE_RATE: Final = 0.00015


# ============================================================
# 집행 경로
# ============================================================

# 경로 식별자. CLI 인자와 결과 표시에 그대로 쓴다
PATH_EXCHANGE: Final = "환전"
PATH_ETF_1X: Final = "261240"
PATH_ETF_2X: Final = "261250"

PATH_CHOICES: Final = (PATH_EXCHANGE, PATH_ETF_1X, PATH_ETF_2X)

# ETF 경로가 읽는 시세 파일. **수정 종가가 본검증 기준**이다 (사양서 §11.3) —
# 원본가를 쓰면 분배락이 손실로 잡히며, 261240 은 2,366일 중 2,208일의 종가가 원본가와 다르다
ETF_MARKET_FILENAMES: Final = {
    PATH_ETF_1X: "261240_adjusted_max.csv",
    PATH_ETF_2X: "261250_adjusted_max.csv",
}

# 경로별 기본 매매 시작일. ETF 는 2016-12-27 상장이라 완전한 해가 2017 부터다 (사양서 §11.4).
# **두 기간이 다르므로 직접 비교하면 안 되며**, 같은 기간 비교는 `--start-date` 로 만든 대조군으로 한다
PATH_START_DATES: Final = {
    PATH_EXCHANGE: TRADING_START_DATE,
    PATH_ETF_1X: "2017-01-01",
    PATH_ETF_2X: "2017-01-01",
}


# ============================================================
# 이자와 세금
# ============================================================

# 달러 RP 금리의 하한 (연%). 사양서 §11.2 — 국내 증권사는 해외주식 결제·파생 헤지로 달러가
# 상시 부족하고 원달러 스왑베이시스가 만성 마이너스라, 미국 금리가 0이어도 프리미엄을 얹을 여력이 있다.
# **이 하한이 실제로 절반의 날을 지배한다** — 2005 이후 5,340 거래일 중 2,605일(48.8%)에서
# T-bill 에서 스프레드를 뺀 값이 하한보다 낮다
DEFAULT_RP_FLOOR_RATE: Final = 0.40

# RP 하한의 검사 범위 (사양서 §12). **절반의 날을 정하는 값**이라 이 트랙에서 비중이 큰 견고성 검사다
RP_FLOOR_RATE_CHOICES: Final = (0.10, 0.40, 0.70)

# 원화 파킹 금리의 하한 (연%). 파킹통장·CMA 는 기준금리 0.5% 시기에도 연 0.5~1.0% 를 지급했다.
# RP 하한과 달리 거의 걸리지 않는다 — 같은 기간 306일(5.7%)뿐이다
DEFAULT_PARKING_FLOOR_RATE: Final = 0.50

# 파킹 하한의 검사 범위 (사양서 §12)
PARKING_FLOOR_RATE_CHOICES: Final = (0.25, 0.50, 0.75)

# 원화 파킹 금리를 만들 때 CD91 에서 빼는 폭 (연%p). 사양서 §11.2
PARKING_RATE_DISCOUNT: Final = 0.30

# 달러 RP 금리를 만들 때 T-bill 에서 빼는 폭. `(하한 T-bill, 빼는 폭)` 을 **내림차순**으로 둔다 —
# 위에서부터 처음 만족하는 칸이 답이라 `x < 0.5%` 는 마지막 칸으로 떨어지며, DTB3 에 실재하는
# 음수 값(최저 −0.050%)도 그 칸으로 간다 (사양서 §11.2)
RP_RATE_SPREAD_STEPS: Final = ((4.0, 1.00), (2.0, 0.60), (0.5, 0.30), (float("-inf"), 0.10))

# 이자 소득의 원천징수율 (비율, 0.154 = 15.4%). **법정 세율이라 검사 축이 아니다** —
# 사양서 §12 의 파라미터 표에도 없다
INTEREST_TAX_RATE: Final = 0.154

# ETF 매매 차익의 과세율 (비율). 이자와 같은 15.4% 이지만 **부과 대상이 다르다** —
# 이자는 발생액에, 이것은 매도 차익에 붙는다. **환차익은 비과세**라 환전 경로는 0 이다 (사양서 §10)
ETF_GAIN_TAX_RATE: Final = 0.154

# 이자 일할의 분모 (일). **365 달력일**이며 연환산 계수(250 거래일)와 다르다 (결정 C14).
# 실제 거래일 밀도(약 261일)와 몇 % 어긋나지만 250 은 사양서가 정한 값이라 그 오차가 사실이다
DAYS_PER_YEAR: Final = 365

# 연 % 로 표기된 금리를 비율로 바꾸는 나눗수 (1.547% → 0.01547)
PERCENT_TO_RATE: Final = 100.0


# ============================================================
# 실행
# ============================================================

# 초기 자본금 (원). 사양서에 값이 없어 확정한 것이다 (결정 C3) — §6.5 가 ETF 정수 주식 수를
# 요구하므로 자본금이 결과를 바꾼다. 1천만원이면 261250 기준 반올림 오차가 수 % 대다
INITIAL_CAPITAL: Final = 100_000_000.0

# 결과 폴더 이름 뒤에 붙는 이름
STRATEGY_NAME: Final = "usdkrw_grid"

# ============================================================
# 일별 곡선 컬럼 (내부 계산용 영문 토큰)
# ============================================================

COL_CLOSE_RATE: Final = "CloseRate"
COL_CASH: Final = "Cash"
COL_USD_VALUE: Final = "UsdValue"

# 매매법의 **공통 산출물**이다 (결정 B1). 표준 지표는 이 곡선 하나만 받는 함수에서 계산한다
COL_TOTAL_ASSETS: Final = "TotalAssets"

COL_ACTIVE_LEVELS: Final = "ActiveLevels"
COL_HELD_SLOTS: Final = "HeldSlots"
COL_BUY_COUNT: Final = "BuyCount"
COL_SELL_COUNT: Final = "SellCount"

# 하향 돌파했지만 현금이 모자라 체결하지 못한 레벨 수. 자금 소진은 버그가 아니라
# 측정 대상이다 (사양서 §6.5·§13.2)
COL_BLOCKED_COUNT: Final = "BlockedCount"

# 그날 발생한 거래비용 합계 (매도분 + 매수분). 총자산은 **비용만큼만** 줄어들므로
# 곡선의 하루치 변화를 이 값과 환율 변동으로 분해할 수 있다
COL_COST: Final = "Cost"

# 그날 적용한 실수령 금리 (연%). 원지표가 아니라 하한·스프레드를 반영한 값이다
COL_RP_RATE: Final = "RpRate"
COL_PARKING_RATE: Final = "ParkingRate"

# 그날 발생한 세전 이자
COL_RP_INTEREST: Final = "RpInterest"
COL_PARKING_INTEREST: Final = "ParkingInterest"

# 아직 인출되지 않고 쌓여 있는 이자 (세전). 총자산에 즉시 반영되므로 항등식에 들어간다
COL_ACCRUED_INTEREST: Final = "AccruedInterest"

# 그날 월말 정산으로 뗀 이자 원천징수액
COL_TAX_PAID: Final = "TaxPaid"

# 그날 매도에서 뗀 매매 차익 과세액. 환전 경로는 언제나 0 이다
COL_GAIN_TAX: Final = "GainTax"

# 집행 가격. 환전 경로는 판정 가격(원달러 종가)과 같고 ETF 경로는 수정 종가다
COL_EXEC_PRICE: Final = "ExecPrice"

# 그날 하단 이탈로 **정식 하단 아래에 켜진 레벨 수**. A안은 언제나 0 이다.
# 사양서 §7 이 B안의 필수 측정 항목으로 「연장 발생 횟수 / 최대 연장 칸 수」를 요구한다
COL_EXTENDED_LEVELS: Final = "ExtendedLevels"

# 그날 마감 시점 보유 슬롯에 들어가 있는 원화 합계 (**비용 포함**).
# 평가액(`COL_USD_VALUE`)과 짝을 이뤄 **미실현 평가손익률**을 만든다 —
# 사양서 §7 이 요구하는 「소진 시점의 평가손실률」이 이 둘로만 계산된다
COL_HELD_INVESTED: Final = "HeldInvested"


# ============================================================
# 표시용 레이블 (일별 곡선)
# ============================================================

DISPLAY_DATE: Final = "날짜"
DISPLAY_CLOSE_RATE: Final = "종가(원)"
DISPLAY_RANGE_LOW: Final = "범위 하단"
DISPLAY_RANGE_HIGH: Final = "범위 상단"
DISPLAY_REBALANCED: Final = "재조정"
DISPLAY_ACTIVE_LEVELS: Final = "활성 레벨"
DISPLAY_HELD_SLOTS: Final = "보유 슬롯"
DISPLAY_BUY_COUNT: Final = "매수"
DISPLAY_SELL_COUNT: Final = "매도"
DISPLAY_BLOCKED_COUNT: Final = "자금부족"
DISPLAY_COST: Final = "거래비용"
DISPLAY_RP_RATE: Final = "RP금리(%)"
DISPLAY_PARKING_RATE: Final = "파킹금리(%)"
DISPLAY_RP_INTEREST: Final = "RP이자"
DISPLAY_PARKING_INTEREST: Final = "파킹이자"
DISPLAY_ACCRUED_INTEREST: Final = "미인출이자"
DISPLAY_TAX_PAID: Final = "원천징수"
DISPLAY_GAIN_TAX: Final = "매매과세"
DISPLAY_EXEC_PRICE: Final = "집행가"
DISPLAY_EXTENDED_LEVELS: Final = "연장 레벨"
DISPLAY_HELD_INVESTED: Final = "보유 투입액"
DISPLAY_CASH: Final = "원화현금"
DISPLAY_USD_VALUE: Final = "달러 평가액"
DISPLAY_TOTAL_ASSETS: Final = "총자산"

# ============================================================
# 표시용 레이블 (체결 내역)
# ============================================================

DISPLAY_LEVEL_INDEX: Final = "레벨"
DISPLAY_LEVEL_PRICE: Final = "레벨가"
DISPLAY_TARGET_PRICE: Final = "목표가"
DISPLAY_ENTRY_DATE: Final = "매수일"
DISPLAY_ENTRY_RATE: Final = "매수 판정환율"
DISPLAY_ENTRY_PRICE: Final = "매수 집행가"
DISPLAY_EXIT_DATE: Final = "매도일"
DISPLAY_EXIT_RATE: Final = "매도 판정환율"
DISPLAY_EXIT_PRICE: Final = "매도 집행가"
DISPLAY_INVESTED: Final = "투입액"
DISPLAY_BUY_COST: Final = "매수비용"
DISPLAY_PROCEEDS: Final = "회수액"
DISPLAY_SELL_COST: Final = "매도비용"
DISPLAY_SELL_TAX: Final = "매도과세"
DISPLAY_REALIZED: Final = "실현손익"

# 종가 체결 가정의 기여분. 지정가 운용이었다면 얻지 못했을 몫이라 반드시 따로 본다 (사양서 §6.4)
DISPLAY_GRID_EXCESS: Final = "이탈 보너스"
DISPLAY_HOLD_DAYS: Final = "보유일"
