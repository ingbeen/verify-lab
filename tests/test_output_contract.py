"""매매 산출물의 «공통 컬럼과 파일 이름» 계약을 매매법 전부에서 한꺼번에 고정한다.

같은 뜻의 표가 매매법마다 **다른 파일명·다른 컬럼·다른 값 형식**으로 나오고 있었다.
성적표가 `summary_by_target.csv`(15컬럼) · `summary_by_cell.csv`(21) · `performance.csv`(23)
셋이었고, `손절선(%)` 은 한쪽이 `"5.0"`(문자열·양수) 다른 쪽이 `-5.0`(실수·음수)이었다.
**SoT 가 없어서 갈린 것**이지 설계가 달라서가 아니다.

고정하는 계약은 일곱이다.

- 성적표는 `성적표.csv`, 거래내역은 `거래내역.csv` 이고 **이름은 상수 한 곳에서 온다**
- 매매법마다 성적표가 **같은 공통 컬럼을 같은 순서로** 갖는다. 매매법 고유 컬럼만 뒤에 붙는다
- `손절선(%)` 값은 **음수 실수**이고 문자열은 둘이다 — **`무손절`(걸지 않았다)과 `손절불가`(잴 수 없다)**.
  두 문자열이 갈려 있어야 **한 컬럼만으로** 한 손절선으로 고정한 행을 고를 수 있다
- 역방향 성적표의 `방향` 은 **`역방향 전체` 한 값**이다 — 그 행이 폭등·폭락을 합친 성적이다
- 역방향 성적표도 **구간 5행**이고, 표본이 하한에 못 미쳐도 행이 남는다 (측정의 원칙 17)
- `사건` 은 **구간별**로 나오고 구간 분할은 `execution/periods.py` 하나가 소유한다
- **구현 못하는 칸은 `0` 이 아니라 빈칸**이다 — 0 은 「손절이 걸리지 않았다」로 읽힌다

**기대 컬럼 목록을 손으로 박아 둔다.** 프로덕션 상수를 import 해서 비교하면 그 상수를 고치는
순간 테스트가 함께 따라와 아무것도 고정하지 못한다
(`tests/CLAUDE.md` 「픽스처가 코드와 같은 가정을 하면 그 버그는 영원히 안 잡힙니다」).
"""

import importlib
import io
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import (
    BASE_DIR,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VALUE,
    COL_VOLUME,
    INDEX_FILE_TEMPLATE,
    MARKET_FILE_TEMPLATE,
    PRICE_DECIMALS,
    PRICE_DECIMALS_KRW,
)
from verify_lab.execution import periods
from verify_lab.execution.constants import (
    DISPLAY_DIRECTION,
    DISPLAY_EVENT_COUNT,
    DISPLAY_GAP_STOP_COUNT,
    DISPLAY_INTRADAY_STOP_COUNT,
    DISPLAY_LOSS_AMOUNT,
    DISPLAY_STOP_LEVEL,
    DISPLAY_TICKER,
    DISPLAY_TOTAL,
    DISPLAY_WIN_AMOUNT,
    NO_STOP_LABEL,
    PERIOD_RECENT_5Y,
    PERIODS,
    STOP_NOT_MEASURABLE_LABEL,
    SUMMARY_FILENAME,
    TRADES_FILENAME,
)
from verify_lab.execution.periods import period_rows
from verify_lab.execution.run_summary import (
    COST_NOTE,
    KEY_COST,
    KEY_DATASETS,
    KEY_NOTES,
    KEY_ROW_COUNTS,
    KEY_RULE,
)
from verify_lab.measure.constants import JUDGEABLE_NO
from verify_lab.report.constants import (
    DISPLAY_EXCLUDED,
    DISPLAY_JUDGEABLE,
    DISPLAY_PERIOD,
    DISPLAY_SIGNAL_COUNT,
)
from verify_lab.report.run_summary import (
    KEY_DATASET_FILE,
    KEY_DATASET_LABEL,
    KEY_DATASET_PERIOD,
    KEY_DATASET_ROWS,
    KEY_DATASET_TICKER,
    KEY_TRACK,
)
from verify_lab.studies.halving_cycle.constants import Dataset as HalvingCycleDataset
from verify_lab.studies.halving_cycle.trading import KEY_TARGETS as HALVING_CYCLE_KEY_TARGETS
from verify_lab.studies.halving_cycle.trading import TradingOutputs as HalvingCycleOutputs
from verify_lab.studies.halving_cycle.trading import run_halving_cycle_trading
from verify_lab.studies.midterm_cycle.constants import Dataset as MidtermCycleDataset
from verify_lab.studies.midterm_cycle.trading import KEY_TARGETS as MIDTERM_CYCLE_KEY_TARGETS
from verify_lab.studies.midterm_cycle.trading import TradingOutputs as MidtermCycleOutputs
from verify_lab.studies.midterm_cycle.trading import run_midterm_cycle_trading
from verify_lab.studies.reverse.constants import (
    DISPLAY_DIRECTION_REVERSE_ALL,
    EXTREME_DIRECTION_LABELS,
    STOP_LOSS_LEVEL,
    Target,
)
from verify_lab.studies.reverse.constants import Dataset as ReverseDataset
from verify_lab.studies.reverse.trading import KEY_TARGETS as REVERSE_KEY_TARGETS
from verify_lab.studies.reverse.trading import StrategyOutputs, run_reverse_trading
from verify_lab.tracks import KIND_METHOD, tracks_of_kind

# ============================================================
# 계약 — 손으로 박아 둔 기대 컬럼
# ============================================================

# 성적표의 공통 컬럼. **종목과 매매법 축 다음에 이 순서로 온다.**
# 순서까지 계약이다 — 이름만 비교하면 재배열이 조용히 통과한다.
# 앞 세 개가 식별 컬럼이고 `시기` 부터가 `periods.period_rows` 의 소유다
SUMMARY_COMMON_COLUMNS = (
    "방향",
    "손절선(%)",
    "시기",
    "신호",
    "합계(%)",
    "평균(%)",
    "승률(%)",
    "손익비",
    "손익분기 승률(%)",
    # **손익분기 승률 바로 뒤에 그 «차이»를 둔다.** 두 값이 나란히 있어도 사람이 매번 빼야
    # 했고, 그 차이가 「이 칸이 얼마나 여유 있게 버는가」를 말한다.
    # **이름을 「여유」·「초과」로 하지 않는다** — 음수가 될 수 있어 그 말이 어색해진다
    # (`.claude/rules/docs.md` 가 「초과분」을 「기준선 대비 차이」로 바꾼 것과 같은 이유)
    "손익분기 대비(%p)",
    # **손익비 바로 뒤에 그 분자·분모를 둔다.** `이길 때(%)` 는 양수,
    # `질 때(%)` 는 **음수**다 — `최악(%)` 과 같은 관용이다
    "이길 때(%)",
    "질 때(%)",
    "질 때 표본",
    "최고(%)",
    "최악(%)",
    # **「최악」이 둘이고 뜻이 다르다.** 앞은 «청산 시점»의 가장 나쁜 결과, 이것은 «보유 중»에
    # 가장 깊이 밀린 지점이다. 매도할 때 -5% 로 끝난 체결과 중간에 -20% 까지 밀렸다가
    # -5% 로 끝난 체결은 감당해야 할 손실이 전혀 다른데, 결과만 보면 같아 보인다.
    # 바로 뒤에 두는 것은 두 값을 같은 눈높이에서 견주기 위해서다
    "보유 중 최악(%)",
    "표준편차(%)",
    "갭손절",
    "장중손절",
    "평균 보유일",
    "판정가능",
    "시기 시작일",
    "시기 종료일",
    # **판정은 성적표 안에 있다** (2026-09-16 통합). 별도 판정표를 내지 않는다 —
    # 맨몸 판정과 손절 판정이 갈리는 칸이 실재해(96칸 중 3칸) 두 파일로 두면 대조가 끊긴다.
    # 맨 뒤에 두는 것은 앞의 공통 컬럼 순서를 흔들지 않기 위해서다
    "1차 판정",
)

# 거래내역의 공통 컬럼. 종목과 매매법 축 다음에 이 순서로 온다.
# **`보유 중 최악(%)` 이 `수익률(%)` 바로 뒤에 온다.** 성적표에서 `최악(%)` 뒤에 오는 것과
# 같은 자리이며, **집계값만 있고 원자료가 없으면 어느 체결이 그 값을 만들었는지 되짚을 수 없다**
# (측정의 원칙 8 — 사용자가 직접 검증할 수 있어야 한다)
TRADE_COMMON_COLUMNS = (
    "방향",
    "손절선(%)",
    "진입일",
    "진입가",
    "청산일",
    "보유일",
    "청산가",
    "수익률(%)",
    "보유 중 최악(%)",
    "청산 사유",
)

# 매매법 축 — 종목 바로 다음에 온다. **역방향만 두 칸**이다
AXIS_REVERSE = ("파라미터", "시작연도")
# 중간선거_사이클 — 성적표는 사이클 위치 하나, **거래내역은 진입 연도가 더 붙는다**
# (신호가 4년에 한 번이라 어느 사이클의 체결인지 날짜만으로는 바로 읽히지 않는다)
AXIS_MIDTERM_CYCLE = ("사이클 위치",)
AXIS_MIDTERM_CYCLE_TRADES = ("사이클 위치", "진입 연도")
# 반감기_사이클 — 성적표는 격자 두 축(진입 시점 × 청산 시점), **거래내역은 반감기 날짜가 더 붙는다**
# (한 칸에 사이클마다 한 체결이라 어느 사이클의 체결인지가 날짜만으로 바로 읽히지 않는다)
AXIS_HALVING_CYCLE = ("반감기 뒤 진입(개월)", "반감기 뒤 청산(개월)")
AXIS_HALVING_CYCLE_TRADES = ("반감기 뒤 진입(개월)", "반감기 뒤 청산(개월)", "반감기")

# 합성 지수 대상의 표시 이름. **살 수 없어 판정하지 않는 행**을 고르는 데 쓴다
INDEX_LABEL = "합성 지수"

# 매매법 고유 컬럼 — 맨 뒤에 붙는다. 역방향은 두 표에, 반감기_사이클은 거래내역에만 있다
TAIL_REVERSE_SUMMARY = ("사건",)
TAIL_REVERSE_TRADES = ("등락률(%)", "사건 번호")
# 원본가에 없는 하드포크 몫 — 체결마다 청산가가 달라 체결마다 잰다
TAIL_HALVING_CYCLE_TRADES = ("하드포크 몫(%p)",)

# 실행 요약의 대상별 기록에 제외 건수를 담는 키. **계약이 키 이름 자체를 정한다**(`src/verify_lab/CLAUDE.md`
# 「매매 산출물 계약」). 한 매매법의 상수를 빌리면 그 매매법이 이름을 바꾸는 순간 검사가 따라가, 틀린 쪽은
# 통과하고 맞는 쪽이 실패한다
EXCLUDED_COUNT_KEY = "excluded_count"

# 종목코드의 모양 — 숫자와 영문 대문자뿐이다(국내 `069500` · 미국 `QQQ` · 지수 `GSPC`).
# 표시 이름(`KODEX 200`)이 `ticker` 에 들어가면 공백·한글·소문자 때문에 여기서 걸린다.
# **새 종목코드가 이 모양을 벗어나면 그 종목과 이유를 적고 넓힌다**
TICKER_SHAPE = re.compile(r"[0-9A-Z]+")

# ============================================================
# 합성 시세
# ============================================================

# 합성 시세 구간. 12개월이 다 차고 만기일이 해마다 나오려면 몇 해가 필요하다
SYNTHETIC_START = "2016-01-04"
SYNTHETIC_END = "2025-12-31"

# 반감기_사이클의 합성 시세 시작. **첫 반감기(2012-11-28) 앞이어야** 네 사이클이 모두 든다
HALVING_SYNTHETIC_START = "2012-01-01"

# 합성 시세를 만드는 난수 시드. 시드 없는 난수는 금지다
SYNTHETIC_SEED = 20260911

# 순위 축적 구간에 심는 등락의 크기. 집계 구간에서는 이보다 큰 등락만 신호가 된다
ACCUMULATION_SHOCK = 0.05

# 집계 구간에 심는 등락의 크기. 순위 컷 안에 들어와 역방향 신호가 된다
SIGNAL_SHOCK = 0.09

# 역방향 집계 시작연도. **축적 구간이 끝난 다음 해**여야 축적분이 신호로 세어지지 않는다
REVERSE_START_YEAR = 2017

# 신호를 심는 위치. 구간 전체에 퍼뜨려 다섯 구간 모두에 표본이 들어가게 한다
SIGNAL_POSITIONS = tuple(400 + order * 150 for order in range(14))

# **앞쪽에만 심은 위치.** 데이터가 2025년까지 가므로 최근 5년 구간의 표본이 0건이 된다 —
# 「표본 0건이면 0 이 아니라 빈칸」 계약을 스킵 없이 검사하려고 둔다
EARLY_SIGNAL_POSITIONS = tuple(range(400, 700, 40))


def _closes(count: int, positions: Sequence[int]) -> np.ndarray:
    """순위 축적분과 신호가 심긴 종가 계열을 만든다.

    Args:
        count: 거래일 수
        positions: 신호를 심을 위치. **구간마다 표본을 조절하는 손잡이다** —
            앞쪽에만 심으면 최근 구간이 0건이 된다

    Returns:
        종가 배열
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)
    changes = rng.normal(0.0003, 0.006, count - 1)

    # 1. 집계 시작 전에 순위 컷을 채운다 (신호가 아니다)
    for offset in range(25):
        changes[offset * 8] = ACCUMULATION_SHOCK if offset % 2 else -ACCUMULATION_SHOCK

    # 2. 집계 구간에 더 큰 등락을 심는다 — 이쪽이 역방향 신호가 된다
    for order, position in enumerate(positions):
        changes[position] = SIGNAL_SHOCK if order % 2 else -SIGNAL_SHOCK

    return 10_000.0 * np.cumprod(np.concatenate([[1.0], 1.0 + changes]))


def _market_frame(positions: Sequence[int] = SIGNAL_POSITIONS) -> pd.DataFrame:
    """장중 등락이 있는 합성 ETF 시세를 만든다.

    **고가·저가를 벌려 둔다** — 장중 손절이 실제로 걸리는지 보려면 일중 범위가 있어야 한다.

    Args:
        positions: 신호를 심을 위치

    Returns:
        시세 스키마 DataFrame
    """
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    closes = _closes(len(days), positions)
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(opens),
            COL_HIGH: np.round(np.maximum(opens, closes) * 1.01),
            COL_LOW: np.round(np.minimum(opens, closes) * 0.99),
            COL_CLOSE: np.round(closes),
            COL_VOLUME: 1_000_000,
        }
    )


def _write_market(directory: Path, ticker: str, positions: Sequence[int] = SIGNAL_POSITIONS) -> Path:
    """합성 ETF 시세를 임시 폴더에 쓴다.

    Args:
        directory: 저장할 폴더
        ticker: 종목 코드
        positions: 신호를 심을 위치

    Returns:
        저장된 파일 경로
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MARKET_FILE_TEMPLATE.format(ticker=ticker)
    _market_frame(positions).to_csv(path, index=False)

    return path


def _reverse_target(path: Path, *, rank_cut: int = 10) -> Target:
    """합성 시세를 가리키는 역방향 대상을 만든다.

    Args:
        path: 시세 파일 경로
        rank_cut: 순위 컷

    Returns:
        매매 대상
    """
    return Target(
        dataset=ReverseDataset(
            key="synthetic",
            ticker="SYN",
            label="합성 ETF",
            price_basis="원본가",
            path=path,
            price_decimals=PRICE_DECIMALS_KRW,
        ),
        rank_cut=rank_cut,
        start_year=REVERSE_START_YEAR,
    )


def _write_index(directory: Path, ticker: str) -> Path:
    """합성 지수 계열을 임시 폴더에 쓴다.

    **시가·고가·저가가 없다.** 실제 코스닥150 지수가 그렇고, 그래서 장중 손절을 잴 수 없다.

    Args:
        directory: 저장할 폴더
        ticker: 지수 코드

    Returns:
        저장된 파일 경로
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / INDEX_FILE_TEMPLATE.format(ticker=ticker)
    frame = _market_frame()
    pd.DataFrame({COL_DATE: frame[COL_DATE], COL_VALUE: frame[COL_CLOSE] / 10.0}).to_csv(path, index=False)

    return path


# ============================================================
# 실행 결과 픽스처 — 모듈마다 한 번만 돈다
# ============================================================


@dataclass(frozen=True)
class MethodSpec:
    """이 파일이 매매법 하나에 거는 계약의 재료.

    Attributes:
        fixture: 그 매매법의 실행 결과를 내는 픽스처 이름
        summary_axis: 성적표에서 종목 다음에 오는 매매법 축
        summary_tail: 성적표 맨 뒤의 매매법 고유 컬럼
        trade_axis: 거래내역에서 종목 다음에 오는 매매법 축
        trade_tail: 거래내역 맨 뒤의 매매법 고유 컬럼
        targets_key: 실행 요약 `rule` 안에서 대상별 기록을 담는 키
    """

    fixture: str
    summary_axis: tuple[str, ...]
    summary_tail: tuple[str, ...]
    trade_axis: tuple[str, ...]
    trade_tail: tuple[str, ...]
    targets_key: str


# 이 파일이 산출물 계약을 거는 매매법(slug) → 그 계약의 재료.
# **레지스트리의 매매법 목록과 같아야 한다** — `TestCoverage` 가 `tracks_of_kind(KIND_METHOD)` 와 대조한다.
# 「매매법 전부」를 보는 검사는 전부 이 표를 돈다(`_BY_METHOD`) — 매매법을 손으로 적으면 새 매매법을
# 등록해도 그 검사가 **조용히 건너뛴다.** 표가 둘이면 한쪽만 늘어도 새므로 픽스처 이름까지 한 표에 둔다
METHOD_SPECS = {
    "reverse": MethodSpec(
        fixture="reverse_outputs",
        summary_axis=AXIS_REVERSE,
        summary_tail=TAIL_REVERSE_SUMMARY,
        trade_axis=AXIS_REVERSE,
        trade_tail=TAIL_REVERSE_TRADES,
        targets_key=REVERSE_KEY_TARGETS,
    ),
    "midterm_cycle": MethodSpec(
        fixture="midterm_cycle_outputs",
        summary_axis=AXIS_MIDTERM_CYCLE,
        summary_tail=(),
        trade_axis=AXIS_MIDTERM_CYCLE_TRADES,
        trade_tail=(),
        targets_key=MIDTERM_CYCLE_KEY_TARGETS,
    ),
    "halving_cycle": MethodSpec(
        fixture="halving_cycle_outputs",
        summary_axis=AXIS_HALVING_CYCLE,
        summary_tail=(),
        trade_axis=AXIS_HALVING_CYCLE_TRADES,
        trade_tail=TAIL_HALVING_CYCLE_TRADES,
        targets_key=HALVING_CYCLE_KEY_TARGETS,
    ),
}

# 「매매법 전부」 검사에 붙이는 매개변수화. 값은 slug 이고 결과는 `_outputs` 로 꺼낸다
_BY_METHOD = pytest.mark.parametrize("slug", sorted(METHOD_SPECS))


def _outputs(request: pytest.FixtureRequest, slug: str) -> StrategyOutputs | MidtermCycleOutputs | HalvingCycleOutputs:
    """그 매매법의 실행 결과를 픽스처에서 꺼낸다.

    Args:
        request: pytest 요청 객체
        slug: 매매법 이름

    Returns:
        실행 결과 — 매매법이 무엇이든 `performance` · `trades` · `summary` 를 갖는다
    """
    return request.getfixturevalue(METHOD_SPECS[slug].fixture)


def _method_constants(slug: str) -> ModuleType:
    """그 매매법 패키지의 `constants` 모듈을 slug 로 찾는다.

    **대상 목록·산출물 목록을 사양 표에 손으로 짝짓지 않는다** — 새 매매법의 사양을 옆 줄에서 복사하고
    안 고치면 남의 목록을 검사하고도 초록이다. 패키지 이름이 곧 slug 이고(`tracks.py`),
    찾은 모듈의 `TRACK_NAME` 으로 한 번 더 확인한다.

    Args:
        slug: 매매법 이름

    Returns:
        `studies/<slug>/constants.py` 모듈
    """
    module = importlib.import_module(f"verify_lab.studies.{slug}.constants")
    assert module.TRACK_NAME == slug, f"{slug} 패키지의 TRACK_NAME 이 다릅니다: {module.TRACK_NAME}"

    return module


@pytest.fixture(scope="module")
def reverse_outputs(tmp_path_factory: pytest.TempPathFactory) -> StrategyOutputs:
    """합성 시세로 돈 역방향 매매 결과."""
    directory = tmp_path_factory.mktemp("reverse")

    return run_reverse_trading([_reverse_target(_write_market(directory, "SYN"))], stop_levels=(STOP_LOSS_LEVEL,))


@pytest.fixture(scope="module")
def midterm_cycle_outputs(tmp_path_factory: pytest.TempPathFactory) -> MidtermCycleOutputs:
    """합성 시세와 합성 지수로 **인자 없이** 돈 중간선거_사이클 결과.

    **매매법마다 픽스처가 하나씩 있어야 한다.** 이 파일이 매매법 전부를 검사한다고
    `src/verify_lab/CLAUDE.md` 가 적어 두었는데 새 매매법을 넣고 여기 픽스처를 안 만들면
    **그 문장이 거짓이 되고, 성적표·거래내역의 컬럼이 비어 나가도 통과한다** — 그래서
    `TestCoverage` 가 레지스트리의 매매법과 `METHOD_SPECS` 를 대조한다.

    **지수를 함께 넣는다** — 장중 손절을 못 거는 대상이 있어야 `손절불가` 표기가 검사된다.

    합성 시세가 2016-01 ~ 2025-12 라 **중간선거해 9월 마지막 거래일 진입이 2018 · 2022 두 번**
    생긴다 — 대상마다 사이클 위치 한 칸에 표본 둘이다.
    """
    return run_midterm_cycle_trading(_midterm_cycle_datasets(tmp_path_factory.mktemp("midterm_cycle")))


@pytest.fixture(scope="module")
def midterm_cycle_grid_outputs(tmp_path_factory: pytest.TempPathFactory) -> MidtermCycleOutputs:
    """같은 합성 입력으로 **손절선 격자를 켜고** 돈 중간선거_사이클 결과.

    **무손절과 숫자 손절선에 지수의 `손절불가` 까지 한 성적표에 함께 내는 실행이 이것뿐이다** — 기본 실행은
    확정 규칙의 무손절 한 종이고 역방향은 −5% 한 종이며, 반감기_사이클은 격자 전부를 내지만 지수 대상이 없다.
    그래서 한 컬럼 필터 계약(`TestSingleColumnStopFilter`)의 두 실패 방식이 이 결과로만 재현된다.
    판정이 「후보」·「제외」로 갈리는 행도 이 실행에 있다.

    [주의] **공유 계약이 한 매매법의 실행을 빌려 쓴다** (`tests/CLAUDE.md` 「공유 계층의 테스트는
    «자기 픽스처»를 갖는다」). 중간선거의 손절선 격자를 코드에서 지우는 날에는 이 픽스처를
    합성 성적표로 바꿔야 한다.
    """
    return run_midterm_cycle_trading(
        _midterm_cycle_datasets(tmp_path_factory.mktemp("midterm_cycle_grid")), stop_grid=True
    )


@pytest.fixture(scope="module")
def halving_cycle_outputs(tmp_path_factory: pytest.TempPathFactory) -> HalvingCycleOutputs:
    """매일 거래하는 합성 시세로 **인자 없이** 돈 반감기_사이클 결과.

    **다른 매매법의 합성 시세(영업일)를 쓰지 않는다** — 반감기 날(2016-07-09 는 토요일)이 영업일에 없어
    진입일을 만들지 못한다. 비트코인 시세처럼 휴장 없는 달력일로 만들고, 네 반감기가 모두 들도록
    첫 반감기(2012-11-28) 앞에서 시작한다.
    """
    return run_halving_cycle_trading((_halving_cycle_dataset(tmp_path_factory.mktemp("halving_cycle")),))


def _halving_cycle_dataset(directory: Path) -> HalvingCycleDataset:
    """매일 거래하는 합성 시세와 합성 기준가를 파일로 쓰고 반감기_사이클 대상을 만든다.

    Args:
        directory: 시세를 쓸 폴더

    Returns:
        합성 대상
    """
    days = pd.date_range(HALVING_SYNTHETIC_START, SYNTHETIC_END, freq="D")
    closes = _closes(len(days), SIGNAL_POSITIONS)
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])
    dates = days.strftime("%Y-%m-%d")

    pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: np.round(opens, PRICE_DECIMALS),
            COL_HIGH: np.round(np.maximum(opens, closes) * 1.01, PRICE_DECIMALS),
            COL_LOW: np.round(np.minimum(opens, closes) * 0.99, PRICE_DECIMALS),
            COL_CLOSE: np.round(closes, PRICE_DECIMALS),
            COL_VOLUME: 1_000.0,
        }
    ).to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker="SYN"), index=False)
    reference_path = directory / "SYN_PriceUSD.csv"
    pd.DataFrame({COL_DATE: dates, COL_VALUE: np.round(closes * 1.001, PRICE_DECIMALS)}).to_csv(
        reference_path, index=False
    )

    # 온체인 두 계열은 측정(2단계)만 읽고 체결은 읽지 않는다 — 파일을 만들지 않는다
    return HalvingCycleDataset(
        ticker="SYN",
        label="합성 비트코인",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        reference_path=reference_path,
        mvrv_path=directory / "SYN_CapMVRVCur.csv",
        market_cap_path=directory / "SYN_CapMrktCurUSD.csv",
        price_decimals=PRICE_DECIMALS,
        is_judged=True,
    )


def _midterm_cycle_datasets(directory: Path) -> tuple[MidtermCycleDataset, MidtermCycleDataset]:
    """합성 ETF 와 합성 지수를 파일로 쓰고 중간선거_사이클 대상 둘을 만든다.

    Args:
        directory: 시세를 쓸 폴더

    Returns:
        (합성 ETF, 합성 지수)
    """
    _write_market(directory, "SYN")
    _write_index(directory, "SYNIDX")

    etf = MidtermCycleDataset(
        ticker="SYN",
        label="합성 ETF",
        symbol="SYN",
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
    )
    index = MidtermCycleDataset(
        ticker="SYNIDX",
        label=INDEX_LABEL,
        symbol="^SYNIDX",
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    )

    return (etf, index)


def _expected_summary(axis: tuple[str, ...], tail: tuple[str, ...] = ()) -> list[str]:
    """그 매매법의 성적표 기대 컬럼을 만든다.

    Args:
        axis: 매매법 축 컬럼
        tail: 맨 뒤에 붙는 고유 컬럼

    Returns:
        기대 컬럼 목록
    """
    return ["종목", *axis, *SUMMARY_COMMON_COLUMNS, *tail]


def _expected_trades(axis: tuple[str, ...], tail: tuple[str, ...] = ()) -> list[str]:
    """그 매매법의 거래내역 기대 컬럼을 만든다.

    Args:
        axis: 매매법 축 컬럼
        tail: 맨 뒤에 붙는 고유 컬럼

    Returns:
        기대 컬럼 목록
    """
    return ["종목", *axis, *TRADE_COMMON_COLUMNS, *tail]


class TestCoverage:
    """이 파일이 매매법 «전부»를 검사한다 — 목록은 레지스트리를 따라간다"""

    def test_레지스트리의_매매법마다_픽스처가_있다(self) -> None:
        """
        목적: 「매매법이면 성적표를 낸다」 계약이 **새 매매법에도 걸리게** 한다.

        레지스트리(`tracks.py`)에 매매법을 등록하고 여기 사양을 올리지 않으면 그 매매법의
        성적표·거래내역은 이 파일의 어떤 검사도 받지 않는데 **아무것도 실패하지 않는다.**
        반대로 매매법에서 내려간 이름이 남아 있으면 없는 계약을 검사하는 척한다.
        「매매법 전부」 검사는 전부 이 표를 돌므로(`_BY_METHOD`) **이 대조와 아래 연결 검사가 함께
        그 검사들의 범위를 닫는다.**

        Given: 레지스트리의 매매법 목록과 이 파일의 사양 표
        When: 두 목록을 견준다
        Then: 같다
        """
        # Given
        registered = {track.slug for track in tracks_of_kind(KIND_METHOD)}

        # When / Then
        assert set(METHOD_SPECS) == registered, (
            f"레지스트리의 매매법과 이 파일의 사양 표가 어긋납니다 — 레지스트리 {sorted(registered)} · "
            f"사양 {sorted(METHOD_SPECS)}. 새 매매법이면 실행 결과 픽스처를 만들고 METHOD_SPECS 에 올리세요"
        )

    @_BY_METHOD
    def test_사양의_픽스처가_그_매매법을_돈다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 사양 표의 픽스처 이름이 **그 매매법**의 실행 결과를 가리키는지 고정한다

        위 대조는 slug 집합만 본다. 새 매매법의 사양을 옆 줄에서 복사하고 픽스처 이름을 안 고치면
        그 slug 의 검사가 전부 **다른 매매법의 산출물**을 보고 통과한다 — 새 매매법은 한 번도 검사받지
        않는데 초록이다. 실행 요약의 `track` 이 그 매매법의 `TRACK_NAME` 이라 slug 와 견주면 연결이 닫힌다.

        Given: 사양 표가 그 slug 에 붙인 픽스처의 실행 결과
        When: 실행 요약의 매매법 이름을 봤을 때
        Then: slug 와 같다
        """
        # Given / When
        track = _outputs(request, slug).summary[KEY_TRACK]

        # Then
        assert track == slug, f"사양 표의 {slug} 픽스처가 다른 매매법({track})을 돌립니다 — METHOD_SPECS 의 fixture 를 고치세요"


class TestSummaryColumns:
    """성적표의 공통 컬럼 — 이름과 «순서»"""

    @_BY_METHOD
    def test_성적표가_공통_컬럼을_순서대로_쓴다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 매매법마다 성적표가 공통 형식을 쓰는지 고정한다

        **매매법끼리 공통 부분이 한 벌인 것도 여기서 함께 고정된다** — 모든 매매법이 같은
        `SUMMARY_COMMON_COLUMNS` 와 견주므로, 공통 부분만 떼어 다시 비교하는 검사는 두지 않는다.

        Given: 합성 시세로 돈 그 매매법의 결과
        When: 성적표의 컬럼을 봤을 때
        Then: 종목 · 매매법 축 · 공통 컬럼 · 매매법 고유 컬럼 순이다
              (매매법 축과 고유 컬럼은 `METHOD_SPECS` 의 그 매매법 사양이 정한다)
        """
        # Given
        spec = METHOD_SPECS[slug]

        # When / Then
        assert list(_outputs(request, slug).performance.columns) == _expected_summary(
            spec.summary_axis, spec.summary_tail
        )


class TestTradeColumns:
    """거래내역의 공통 컬럼"""

    @_BY_METHOD
    def test_거래내역이_공통_컬럼을_순서대로_쓴다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 매매법마다 거래내역 컬럼과 «순서»를 고정한다 — 청산일·청산가가 있고 `날짜` 가 `진입일` 이다

        청산 지점이 없으면 사용자가 차트로 대조할 수 없다 (측정의 원칙 8).

        Given: 합성 시세로 돈 그 매매법의 결과
        When: 거래내역의 컬럼을 봤을 때
        Then: 종목 · 매매법 축 · 공통 컬럼 · 매매법 고유 컬럼 순이다
              (매매법 축과 고유 컬럼은 `METHOD_SPECS` 의 그 매매법 사양이 정한다)
        """
        # Given
        spec = METHOD_SPECS[slug]

        # When / Then
        assert list(_outputs(request, slug).trades.columns) == _expected_trades(spec.trade_axis, spec.trade_tail)


class TestStopLevelFormat:
    """`손절선(%)` 의 값 형식 — 음수 실수 하나"""

    @staticmethod
    def _levels(table: pd.DataFrame) -> set[object]:
        """손절선 컬럼의 서로 다른 값을 모은다."""
        return set(table[DISPLAY_STOP_LEVEL].tolist())

    def test_역방향_손절선은_음수_실수다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 그 표에 걸린 손절선이 행 안에서 읽히는지 고정한다

        산출물만 보고 −5% 성적인지 무손절인지 판별할 수 없으면 그 표는 근거가 못 된다.

        Given: 합성 시세로 돈 역방향 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: −5.0 하나뿐이다
        """
        # Given / When / Then
        assert self._levels(reverse_outputs.performance) == {-5.0}

    def test_중간선거_기본_실행은_무손절과_손절불가뿐이다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 인자 없이 돌린 산출물이 **확정 규칙의 칸만** 담는지 고정한다

        확정 규칙이 기간 손절(가격 손절 없음)이라 ETF 는 `무손절` 행을 내고, 그중 대상 QQQ 의 행이
        그 규칙의 1배 측정 기준이다.
        격자 값이 섞이면 확정 칸을 고르려고 매번 필터를 걸어야 하고, 격자는 스위치로만 켠다.

        Given: 합성 시세와 합성 지수로 인자 없이 돈 중간선거_사이클 결과
        When: 성적표의 손절선 값을 봤을 때
        Then: ETF 의 `무손절` 과 지수의 `손절불가` 둘뿐이다
        """
        # Given / When / Then
        assert self._levels(midterm_cycle_outputs.performance) == {NO_STOP_LABEL, STOP_NOT_MEASURABLE_LABEL}

    def test_잴_수_없는_대상만_손절불가다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 두 문자열이 대상에 따라 정확히 갈리는지 고정한다

        섞이면 필터가 조용히 240행을 잃거나 더한다.

        Given: 합성 시세와 합성 지수로 돈 중간선거_사이클 결과
        When: 손절선이 `손절불가` 인 행의 종목을 봤을 때
        Then: 지수뿐이고, ETF 는 `무손절` 을 갖되 `손절불가` 는 갖지 않는다
        """
        # Given
        table = midterm_cycle_outputs.performance
        index_label = INDEX_LABEL
        etf_label = "합성 ETF"

        # When
        not_measurable = set(table.loc[table[DISPLAY_STOP_LEVEL] == STOP_NOT_MEASURABLE_LABEL, DISPLAY_TICKER])
        etf_levels = set(table.loc[table[DISPLAY_TICKER] == etf_label, DISPLAY_STOP_LEVEL])

        # Then
        assert not_measurable == {index_label}
        assert NO_STOP_LABEL in etf_levels
        assert STOP_NOT_MEASURABLE_LABEL not in etf_levels

    def test_거래내역의_손절선도_같은_형식이다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 두 표의 값이 갈리면 조인이 안 된다는 것을 고정한다

        Given: 합성 시세와 합성 지수로 돈 중간선거_사이클 결과
        When: 성적표와 거래내역의 손절선 값 집합을 비교했을 때
        Then: 같다
        """
        # Given / When / Then
        assert self._levels(midterm_cycle_outputs.trades) == self._levels(midterm_cycle_outputs.performance)

    def test_형식_변환기가_세_값을_낸다(self) -> None:
        """
        목적: `손절선(%)` 값 형식의 **소유자가 하나**임을 함수 단위로 고정한다

        매매법마다 포매터를 두면 조인이 안 된다. 세 갈래는 각각 다른 사실이다 —
        손절선을 걸었다 / 걸지 않았다(대조축) / 잴 수 없다(고가·저가 없음).

        Given: 매매 계층의 형식 변환기
        When: 세 경우를 넘겼을 때
        Then: 음수 실수 · 무손절 · 손절불가가 나온다
        """
        # Given
        from verify_lab.execution.constants import stop_level_value

        # When / Then
        assert stop_level_value(0.05, measurable=True) == -5.0
        assert stop_level_value(None, measurable=True) == NO_STOP_LABEL
        assert stop_level_value(None, measurable=False) == STOP_NOT_MEASURABLE_LABEL

    def test_잴_수_없는데_손절선이_있으면_내부_불변조건_위반이다(self) -> None:
        """
        목적: 있을 수 없는 조합을 **조용히 통과시키지 않음**을 고정한다

        잴 수 없는 대상에는 무손절 한 줄만 도는 것이 규칙이다. 손절선이 함께 오면 호출 측이
        그 규칙을 깬 것이므로, 기본값을 돌려주면 그 성적이 표에 그대로 실린다.

        Given: 매매 계층의 형식 변환기
        When: 잴 수 없는데 손절선이 있는 조합을 넘겼을 때
        Then: `RuntimeError` 를 던진다
        """
        # Given
        from verify_lab.execution.constants import stop_level_value

        # When / Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            stop_level_value(0.05, measurable=False)


class TestReverseDirection:
    """역방향의 `방향` — 성적표와 거래내역이 다른 것을 가리킨다"""

    def test_성적표의_방향은_역방향_전체_하나다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 합친 성적에 `위`·`아래` 를 적지 않는다는 것을 고정한다

        그 행은 폭등 신호와 폭락 신호를 한 표본으로 묶은 것이라 어느 쪽도 아니다.

        Given: 합성 시세로 돈 역방향 결과
        When: 성적표의 방향 값을 봤을 때
        Then: `역방향 전체` 하나뿐이다
        """
        # Given / When / Then
        assert set(reverse_outputs.performance[DISPLAY_DIRECTION]) == {DISPLAY_DIRECTION_REVERSE_ALL}

    def test_거래내역의_방향은_신호_방향_그대로다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 거래내역의 `폭등`/`폭락` 을 거는 방향으로 환산하지 않았음을 고정한다

        환산하면 기존 컬럼의 **뜻이 조용히 바뀌고** 규칙 문서 §5 원자료 표와 어긋난다.

        Given: 합성 시세로 돈 역방향 결과
        When: 거래내역의 방향 값을 봤을 때
        Then: 폭등·폭락 안에 든다
        """
        # Given / When / Then
        assert set(reverse_outputs.trades[DISPLAY_DIRECTION]) <= set(EXTREME_DIRECTION_LABELS.values())


class TestReversePeriods:
    """역방향 성적표의 구간 축 (측정의 원칙 17)"""

    def test_대상마다_구간_다섯_행이다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 역방향도 구간으로 쪼개진다는 것을 고정한다

        균등 2분할만으로는 신호가 식는 것을 놓친다.
        **행 수만 세는 검사를 매매법 테스트에 따로 두지 않는다** — 이것이 순서까지 보므로 그 상위집합이다.

        Given: 대상 하나로 돈 역방향 결과
        When: 성적표의 구간 컬럼을 봤을 때
        Then: `PERIODS` 순서 그대로 다섯 행이다
        """
        # Given / When / Then
        assert reverse_outputs.performance[DISPLAY_PERIOD].tolist() == list(PERIODS)

    def test_표본이_하한에_못_미쳐도_행이_남는다(self, tmp_path: Path) -> None:
        """
        목적: 행이 사라지면 그 구간을 못 봤다는 사실 자체를 모른다는 것을 고정한다

        Given: 신호가 적게 심긴 합성 시세
        When: 성적표를 봤을 때
        Then: 다섯 행이 모두 있고 하한 미달 구간은 `판정가능` 이 「아니오」다
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "sparse", "SYN", EARLY_SIGNAL_POSITIONS))

        # When
        summary = run_reverse_trading([target], stop_levels=(STOP_LOSS_LEVEL,)).performance

        # Then
        assert summary[DISPLAY_PERIOD].tolist() == list(PERIODS)
        assert (summary.loc[summary[DISPLAY_SIGNAL_COUNT] < 10, DISPLAY_JUDGEABLE] == JUDGEABLE_NO).all()

    @_BY_METHOD
    def test_성적표에_제외_컬럼을_두지_않는다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: **제외의 SoT 를 성적표에서 `summary.json` 으로 옮긴 것을 고정한다** (2026-09-12).

        제외된 신호는 보유 구간이 데이터 끝을 넘어간 것이라 **언제나 가장 최근**이고, 구간 행에
        귀속시킬 규칙이 없어 전체 행에만 적히는 열이었다. 판정에도 성적에도 쓰이지 않으므로
        성적표에서 걷어냈다 — **사실이 사라진 것이 아니라 자리를 옮긴 것**이며,
        아래 테스트가 요약이 그 값을 계속 담는지 검사한다.
        매매법 전부를 한 번에 보므로 **매매법 테스트에 같은 검사를 따로 두지 않는다.**

        Given: 그 매매법의 성적표
        When: 컬럼을 봤을 때
        Then: 「제외」가 없다
        """
        # Given / When / Then
        assert DISPLAY_EXCLUDED not in _outputs(request, slug).performance.columns, f"{slug} 성적표에 제외 컬럼이 남아 있습니다"

    @_BY_METHOD
    def test_제외_건수는_요약이_대상마다_담는다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: **표본 보존은 그대로다** (패키지 절대 원칙). 컬럼을 없앤 대신 요약이 담아야 하며,
              둘 다 없으면 몇 건이 왜 빠졌는지가 **어디에도 남지 않는다.**

        **각 매매법이 실제로 쓰는 키를 지목해 검사한다.** `rule` 안은 고정하지 않는 것이
        계약이므로(`src/verify_lab/CLAUDE.md`), 「사전이 든 목록」을 훑으면 나중에 다른
        목록이 하나 생기는 것만으로 이 테스트가 엉뚱하게 깨진다.

        Given: 그 매매법의 실행 요약
        When: 대상별 기록을 봤을 때
        Then: 모든 항목에 `excluded_count` 가 있다
        """
        # Given
        group = _outputs(request, slug).summary[KEY_RULE][METHOD_SPECS[slug].targets_key]

        # When / Then
        assert group, f"{slug} 요약의 대상별 목록이 비어 있습니다"
        for record in group:
            assert EXCLUDED_COUNT_KEY in record, f"{slug} 요약에 제외 건수가 없습니다: {record}"

    def test_표본이_0건인_구간은_지표를_비운다(self, tmp_path: Path) -> None:
        """
        목적: 구현 못하는 칸이 0 이 아니라 빈칸임을 고정한다

        0 은 「손절이 걸리지 않았다」·「손실도 이익도 없었다」로 읽히는데 실제로는 「잰 적이 없다」다.

        Given: 신호를 앞쪽에만 심은 합성 시세 (최근 5년 구간이 0건이 된다)
        When: 표본이 0건인 구간 행을 봤을 때
        Then: 합계·갭손절·장중손절이 비어 있다
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "early", "SYN", EARLY_SIGNAL_POSITIONS))

        # When
        summary = run_reverse_trading([target], stop_levels=(STOP_LOSS_LEVEL,)).performance
        empty = summary[summary[DISPLAY_SIGNAL_COUNT] == 0]

        # Then
        assert not empty.empty, "표본 0건 구간이 없어 계약을 검사하지 못했습니다 — 신호 위치를 앞으로 옮기세요"
        for column in (DISPLAY_TOTAL, DISPLAY_GAP_STOP_COUNT, DISPLAY_INTRADAY_STOP_COUNT):
            assert empty[column].isna().all()


class TestEventCount:
    """`사건` — 구간별로 나오고 분할은 공유 모듈이 소유한다"""

    def test_사건이_구간마다_따로_세어진다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 전체 구간의 사건 수를 모든 행에 복사하지 않았음을 고정한다

        같은 사건에서 파생된 신호를 묶어 세는 것이 측정의 원칙 5 이며, 구간을 쪼개면
        그 수도 구간마다 달라야 한다.

        Given: 합성 시세로 돈 역방향 결과
        When: 전체 행과 앞 절반 행의 사건 수를 비교했을 때
        Then: 앞 절반이 전체보다 작다
        """
        # Given
        summary = reverse_outputs.performance.set_index(DISPLAY_PERIOD)

        # When
        whole = int(summary.loc[PERIODS[0], TAIL_REVERSE_SUMMARY[0]])
        first_half = int(summary.loc[PERIODS[1], TAIL_REVERSE_SUMMARY[0]])

        # Then
        assert first_half < whole

    def test_사건을_주지_않은_매매법에는_그_컬럼이_없다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 잴 수 없는 것을 빈칸으로 싣지 않고 **컬럼을 내지 않는다**는 정책을 고정한다

        중간선거_사이클은 신호가 4년에 한 번이라 신호 = 사건이다.

        Given: 중간선거_사이클의 성적표
        When: 사건 컬럼을 찾았을 때
        Then: 없다
        """
        # Given / When / Then
        assert TAIL_REVERSE_SUMMARY[0] not in midterm_cycle_outputs.performance.columns

    def test_구간_분할은_periods_가_소유한다(self) -> None:
        """
        목적: runner 가 구간 마스크를 다시 만들지 않았음을 고정한다

        복제하면 구간 분할이 두 벌이 되어 같은 원칙이 다른 답을 낸다 (절대 원칙 5).

        Given: 매매법마다 하나씩인 매매 실행 모듈 소스
        When: 구간 경계를 만드는 표현을 찾았을 때
        Then: `periods.py` 밖에는 없다
        """
        # Given
        runners = sorted((BASE_DIR / "src" / "verify_lab" / "studies").glob("*/trading.py"))
        assert runners, "매매 실행 모듈을 찾지 못했습니다"

        # When / Then
        for runner in runners:
            source = runner.read_text(encoding="utf-8")
            where = f"{runner.parent.name}/{runner.name}"
            assert "DateOffset" not in source, f"{where} 이 최근 N년 경계를 직접 만듭니다"
            assert "PERIOD_FIRST_HALF" not in source, f"{where} 이 절반 분할을 직접 만듭니다"


class TestSingleColumnStopFilter:
    """한 손절선으로 고정한 행을 **`손절선(%)` 한 컬럼만으로** 고를 수 있다

    고르는 데 두 컬럼이 필요하면(`손절선` AND `손절적용`) 표를 따로 내야 한다 — 엑셀 자동
    필터는 **열끼리 AND** 라 그 조건을 한 번에 걸 수 없다. 무손절과 손절불가를 다른 문자열로
    가르면 **한 열 안의 다중선택(OR)** 으로 끝난다.
    """

    # 필터에 거는 손절선 하나. 중간선거_사이클 손절선 격자에 든 값이면 된다(여기서는 −5%).
    # **프로덕션 상수를 import 하지 않고 손으로 박는다** — 상수를 고치면 테스트가 따라와
    # 아무것도 고정하지 못한다 (이 모듈 머리말)
    FIXED_LEVEL = -5.0

    def test_한_컬럼_필터가_모든_칸을_한_번씩_준다(self, midterm_cycle_grid_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 지수를 잃지도, ETF 무손절을 더하지도 않는다는 것을 고정한다

        Given: 합성 시세와 합성 지수로 손절선 격자를 켜고 돈 중간선거_사이클 결과
        When: `손절선(%)` 이 그 숫자이거나 `손절불가` 인 행만 걸렀을 때
        Then: (종목 × 사이클 위치 × 방향 × 구간) 칸마다 정확히 한 행이고 두 대상이 다 있다
        """
        # Given
        table = midterm_cycle_grid_outputs.performance
        # **축 컬럼을 빠짐없이 넣는다.** 하나라도 빠지면 서로 다른 칸이 같은 키로 묶여
        # 「한 칸이 두 행」으로 읽힌다 — 이 매매법의 축은 (종목 × 사이클 위치 × 방향) 이다
        cells = [DISPLAY_TICKER, *AXIS_MIDTERM_CYCLE, DISPLAY_DIRECTION, DISPLAY_PERIOD]

        # When
        picked = table[table[DISPLAY_STOP_LEVEL].isin([self.FIXED_LEVEL, STOP_NOT_MEASURABLE_LABEL])]

        # Then
        assert not picked.duplicated(subset=cells).any(), "한 칸이 두 행으로 나왔습니다"
        assert len(picked) == len(table.drop_duplicates(subset=cells)), "칸 하나가 빠졌습니다"
        assert set(picked[DISPLAY_TICKER]) == set(table[DISPLAY_TICKER]), "대상 하나가 필터에서 사라졌습니다"

    def test_무손절을_같이_걸면_ETF_행이_섞인다(self, midterm_cycle_grid_outputs: MidtermCycleOutputs) -> None:
        """
        목적: **왜 두 문자열을 갈랐는지**를 실패 모드로 고정한다

        `무손절` 은 ETF 의 대조축 행이라 그 손절선 행과 함께 걸리면 대상이 두 번 실린다.
        에러가 나지 않으므로 표를 보는 사람은 알아채지 못한다.

        Given: 합성 시세와 합성 지수로 손절선 격자를 켜고 돈 중간선거_사이클 결과
        When: `무손절` 까지 포함해 걸렀을 때
        Then: 칸이 중복돼 위 필터보다 행이 많다
        """
        # Given
        table = midterm_cycle_grid_outputs.performance
        # **축 컬럼을 빠짐없이 넣는다.** 하나라도 빠지면 서로 다른 칸이 같은 키로 묶여
        # 「한 칸이 두 행」으로 읽힌다 — 이 매매법의 축은 (종목 × 사이클 위치 × 방향) 이다
        cells = [DISPLAY_TICKER, *AXIS_MIDTERM_CYCLE, DISPLAY_DIRECTION, DISPLAY_PERIOD]

        # When
        naive = table[table[DISPLAY_STOP_LEVEL].isin([self.FIXED_LEVEL, STOP_NOT_MEASURABLE_LABEL, NO_STOP_LABEL])]

        # Then
        assert naive.duplicated(subset=cells).any()
        assert len(naive) > len(table.drop_duplicates(subset=cells))

    def test_숫자값만_걸면_지수가_통째로_사라진다(self, midterm_cycle_grid_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 반대쪽 실패 모드를 고정한다 — 지수를 잃으면 긴 기간 축이 없어진다

        Given: 합성 시세와 합성 지수로 손절선 격자를 켜고 돈 중간선거_사이클 결과
        When: 숫자 손절선 값만으로 걸렀을 때
        Then: 지수 행이 하나도 없다
        """
        # Given
        table = midterm_cycle_grid_outputs.performance

        # When
        numeric_only = table[table[DISPLAY_STOP_LEVEL] == self.FIXED_LEVEL]

        # Then
        assert set(numeric_only[DISPLAY_TICKER]) == {"합성 ETF"}


class TestFilenames:
    """파일 이름은 상수 한 곳에서 온다"""

    def test_사용자가_보는_이름이_상수로_정의돼_있다(self) -> None:
        """
        목적: 이름이 코드 여러 곳에 흩어진 문자열이 되지 않게 한다

        **경계는 「중요도」가 아니라 「종류」다.** 사용자가 판정에 쓰는 종류만 한글이고
        원자료·검정 표는 영문으로 남는다 — 중요도로 가르면 새 표가 생길 때마다 다시 물어야 하고,
        판정이 갈리면 이름이 뒤섞인다.

        **판정표는 이름이 없다** — 1차 판정은 성적표 안의 컬럼이다.
        **`통계.csv` 와 `측정.csv` 는 담는 축이 다른 두 표다** — 측정 격자를 확정 칸으로 좁힌
        매매법이 `측정.csv` 를, 좁히지 않은 매매법이 `통계.csv` 를 낸다
        (`src/verify_lab/CLAUDE.md` 「`측정.csv`」).

        Given: 체결 계층과 출력 계층의 상수 모듈
        When: 파일명 상수를 읽었을 때
        Then: 사용자가 보는 이름이 한글로 정의돼 있다
        """
        # Given
        from verify_lab.execution.constants import SUMMARY_FILENAME, TRADES_FILENAME
        from verify_lab.report.constants import MEASURE_FILENAME, STATISTICS_FILENAME

        # When / Then
        assert SUMMARY_FILENAME == "성적표.csv"
        assert TRADES_FILENAME == "거래내역.csv"
        assert STATISTICS_FILENAME == "통계.csv"
        assert MEASURE_FILENAME == "측정.csv"

    def test_역방향은_통계_이름을_낸다(self) -> None:
        """
        목적: **같은 질문에 답하는 표가 매매법마다 다른 이름으로 불리던 상태를 닫는다.**

        판정표가 `candidates.csv`·`month_candidates.csv` 였고 집계표가 `statistics.csv`·
        `months.csv`·`weekly_trade_by_month.csv` 였다. 매매법을 바꿔 열 때마다 어느 파일인지
        다시 찾아야 했고, **이름이 갈려 있어 계약으로 고정할 수도 없었다.**

        축을 이름에 넣지 않는다(`만기월별_통계` 가 아니라 `통계`) — 폴더가 매매법을 말하므로
        이름에 또 넣으면 중복이고, 넣는 순간 이름이 다시 갈린다.

        **측정 격자를 확정 칸으로 좁힌 매매법(중간선거_사이클)은 여기서 빠진다** — 측정 표를
        `측정.csv` 한 장으로 합친다. **격자를 재는 매매법만 축별 집계표가 필요하다.**

        Given: 역방향의 산출물 파일 목록과 체결 산출물 이름
        When: 사용자가 보는 이름을 찾는다
        Then: 그 이름을 그대로 낸다
        """
        # Given
        from verify_lab.execution.constants import SUMMARY_FILENAME, TRADES_FILENAME
        from verify_lab.report.constants import STATISTICS_FILENAME
        from verify_lab.studies.reverse.constants import OUTPUT_FILES as REVERSE_FILES

        # When / Then
        assert STATISTICS_FILENAME in set(REVERSE_FILES.values()), f"역방향의 산출물에 사용자가 보는 이름이 없습니다: {STATISTICS_FILENAME}"

        # 체결 둘은 `execution/constants.py` 가 소유하므로 매매법 전부가 자동으로 같다
        assert {SUMMARY_FILENAME, TRADES_FILENAME} == {"성적표.csv", "거래내역.csv"}


class TestBreakevenMargin:
    """`손익분기 대비(%p)` — 승률이 손익분기 승률보다 얼마나 위인가

    두 값이 표에 나란히 있어도 **사람이 매번 빼야 했다.** 그 차이가 「이 칸이 얼마나 여유 있게
    버는가」를 말하는데, 손으로 빼면 행마다 다시 계산해야 하고 표를 정렬할 수도 없다.

    [중요] **표에 실린 «반올림 뒤» 값끼리 뺀다.** 원값으로 계산하면 승률 `72.73` · 손익분기
    `43.10` 이 찍힌 행에 `29.62` 가 나올 수 있다 — **표가 자기 자신과 어긋난다.**
    매매 산출물 계약의 「판정에 넣는 값은 반올림 뒤」와 같은 이유다.
    """

    # 컬럼 이름을 **손으로 박는다.** 프로덕션 상수를 import 하면 그 상수를 고치는 순간
    # 테스트가 함께 따라와 아무것도 고정하지 못한다 (이 모듈 머리말)
    MARGIN_COLUMN = "손익분기 대비(%p)"
    WIN_RATE_COLUMN = "승률(%)"
    BREAKEVEN_COLUMN = "손익분기 승률(%)"

    @_BY_METHOD
    def test_매매법_모두_승률에서_손익분기를_뺀_값이다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 산식을 계약으로 고정한다 — **표에 실린 값끼리** 뺀 것이어야 한다

        Given: 그 매매법의 성적표
        When: 값이 있는 행에서 승률 − 손익분기 승률을 계산했을 때
        Then: `손익분기 대비(%p)` 와 같다
        """
        # Given
        table = _outputs(request, slug).performance
        filled = table[table[self.MARGIN_COLUMN].notna()]
        assert not filled.empty, f"{slug} 성적표에 값이 있는 행이 없습니다"

        # When
        expected = (filled[self.WIN_RATE_COLUMN] - filled[self.BREAKEVEN_COLUMN]).round(2)

        # Then
        assert filled[self.MARGIN_COLUMN].tolist() == pytest.approx(
            expected.tolist(), abs=1e-9
        ), f"{slug} 성적표의 손익분기 대비가 두 컬럼의 차이와 다릅니다"

    def test_손익분기_승률_바로_뒤에_온다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: **자리**를 계약으로 고정한다

        재료 바로 옆에 있어야 사용자가 셋을 한눈에 견준다. 표 끝에 붙이면 스크롤해야 한다.

        Given: 합성 시세로 돈 중간선거_사이클 결과
        When: 두 컬럼의 위치를 봤을 때
        Then: 손익분기 승률 다음 칸이다
        """
        # Given
        columns = list(midterm_cycle_outputs.performance.columns)

        # When
        breakeven = columns.index(self.BREAKEVEN_COLUMN)

        # Then
        assert columns[breakeven + 1] == self.MARGIN_COLUMN

    def test_손익분기가_비면_대비도_빈다(self) -> None:
        """
        목적: 「잰 적이 없다」를 0 으로 채우지 않는다 (측정의 원칙 17)

        전승 칸은 손익비가 무한대라 손익분기 승률을 숫자로 못 적는다. 그때 대비를
        `승률 − 0` 으로 계산하면 **「손익분기를 승률만큼 앞선다」는 거짓이 나온다.**

        Given: 전부 이익인 체결 목록 (진 거래 0건 → 손익분기 승률이 결측)
        When: 구간 행을 만들었을 때
        Then: 손익분기 승률과 손익분기 대비가 둘 다 비어 있다
        """
        # Given
        dates = pd.DatetimeIndex(["2020-01-02", "2020-02-03", "2020-03-02"])

        # When
        overall = period_rows(dates, [0.01, 0.02, 0.03], last_day=pd.Timestamp("2020-03-31"), tradable=True)[0]

        # Then
        assert pd.isna(overall[self.BREAKEVEN_COLUMN]), "진 거래가 0건인데 손익분기 승률에 값이 있습니다"
        assert pd.isna(overall[self.MARGIN_COLUMN]), "손익분기 승률이 비었는데 대비에 값이 있습니다"

    def test_표본이_0건인_구간은_빈다(self) -> None:
        """
        목적: 표본이 없는 칸을 0 으로 채우지 않는다

        Given: 체결이 하나도 없는 목록
        When: 구간 행을 만들었을 때
        Then: 손익분기 대비가 비어 있다
        """
        # Given
        empty_dates = pd.DatetimeIndex([])

        # When
        overall = period_rows(empty_dates, [], last_day=pd.Timestamp("2020-03-31"), tradable=True)[0]

        # Then
        assert pd.isna(overall[self.MARGIN_COLUMN])


class TestPayoffAmountColumns:
    """`이길 때(%)` · `질 때(%)` — 부호와 결측"""

    def test_이길_때는_양수이고_질_때는_음수다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 두 열의 부호를 계약으로 고정한다.

        **`최악(%)` 이 음수인 것과 같은 관용**이다. 둘 다 절대값으로 내면 표를 읽는 사람이
        어느 쪽이 손실인지 이름으로만 판단해야 한다.

        Given: 합성 시세로 돈 중간선거_사이클 결과
        When: 값이 있는 행의 두 열을 봤을 때
        Then: 이길 때는 0 초과, 질 때는 0 미만이다
        """
        # Given
        summary = midterm_cycle_outputs.performance
        wins = summary[DISPLAY_WIN_AMOUNT].dropna()
        losses = summary[DISPLAY_LOSS_AMOUNT].dropna()
        assert not wins.empty and not losses.empty, "두 열에 값이 하나도 없습니다"

        # When / Then
        assert (wins > 0).all(), "이길 때가 양수가 아닌 행이 있습니다"
        assert (losses < 0).all(), "질 때가 음수가 아닌 행이 있습니다"

    def test_전승_칸은_질_때만_비고_이길_때는_값이_있다(self) -> None:
        """
        목적: 「진 적이 없다」와 「못 쟀다」를 가른다.

        전승 칸은 손익비가 수학적으로 무한대라 숫자로 못 적지만, **이길 때 평균은 존재한다.**
        둘을 함께 비우면 그 칸의 성적을 읽을 수 없다.

        Given: 전부 이익인 체결 목록
        When: 구간 행을 만들었을 때
        Then: 질 때는 비고 이길 때는 값이 있다
        """
        # Given
        dates = pd.DatetimeIndex(["2020-01-02", "2020-02-03", "2020-03-02"])

        # When
        rows = period_rows(dates, [0.01, 0.02, 0.03], last_day=pd.Timestamp("2020-03-31"), tradable=True)
        overall = rows[0]

        # Then
        assert pd.isna(overall[DISPLAY_LOSS_AMOUNT]), "진 거래가 0건인데 질 때에 값이 있습니다"
        assert overall[DISPLAY_WIN_AMOUNT] == pytest.approx(2.0, abs=1e-9)

    def test_표본이_0건인_구간은_두_열이_모두_빈다(self) -> None:
        """
        목적: 표본이 없는 것을 0 으로 채우지 않는다 (측정의 원칙 17).

        0 은 「이익도 손실도 없었다」로 읽히는데 실제로는 「잰 적이 없다」이다.

        Given: 최근 5년에 진입이 하나도 없는 체결 목록
        When: 구간 행을 만들었을 때
        Then: 그 구간의 두 열이 비어 있다
        """
        # Given — 마지막 거래일보다 10년 넘게 앞선 진입만 둔다
        dates = pd.DatetimeIndex(["2000-01-03", "2000-02-01"])

        # When
        rows = period_rows(dates, [0.01, -0.02], last_day=pd.Timestamp("2020-12-30"), tradable=True)
        recent = next(row for row in rows if row[DISPLAY_PERIOD] == PERIOD_RECENT_5Y)

        # Then
        assert recent[DISPLAY_SIGNAL_COUNT] == 0
        assert pd.isna(recent[DISPLAY_WIN_AMOUNT])
        assert pd.isna(recent[DISPLAY_LOSS_AMOUNT])


class TestWorstHoldColumn:
    """매매법 전부가 `보유 중 최악(%)` 을 실제로 «채운다»

    **컬럼 이름만 검사하면 이 계약이 닫히지 않는다.** 값을 넘기는 인자가 선택형이라
    (`hold_days`·`reasons` 와 같은 관용) 매매법이 그것을 빠뜨리면 **컬럼은 그대로 있고
    내용만 비어 나간다** — 앞의 컬럼 순서 테스트는 통과한다.
    그래서 「이름이 있는가」가 아니라 **「표본이 있는 행에 값이 있는가」**를 본다.
    """

    COLUMN = "보유 중 최악(%)"
    RESULT_COLUMN = "최악(%)"

    @_BY_METHOD
    def test_성적표가_값을_채운다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 매매법마다 체결 모듈이 값 넘기기(선택 인자)를 빠뜨리지 않았는지 고정한다

        Given: 합성 시세로 돈 그 매매법의 성적표
        When: 표본이 있는 행을 봤을 때
        Then: 보유 중 최악이 비어 있지 않다
        """
        self._assert_filled(_outputs(request, slug).performance)

    def test_지수_행도_값을_갖는다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 「손절불가」 행이 조용히 빠지지 않는지 고정한다 (엣지 케이스)

        Given: 중간선거_사이클 성적표의 지수 행 (`손절선(%)` 이 `손절불가`)
        When: 표본이 있는 행을 봤을 때
        Then: 보유 중 최악이 비어 있지 않다
        """
        # Given
        table = midterm_cycle_outputs.performance
        index_rows = table[table["손절선(%)"] == STOP_NOT_MEASURABLE_LABEL]
        assert not index_rows.empty, "지수 행이 없어 계약을 검사하지 못했습니다"

        # When / Then
        self._assert_filled(index_rows)

    @_BY_METHOD
    def test_보유_중_최악이_결과_최악보다_나쁘거나_같다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 두 컬럼이 **같은 체결 목록**을 보고 있음을 고정한다

        청산가는 보유 중에 실제로 지난 가격이므로 보유 중 최악은 언제나 그보다 나쁘거나 같다.
        이 부등식이 깨지면 구간(진입 다음 날 ~ 청산일)이나 방향 부호가 틀린 것이다.
        **매매법 전부에 한꺼번에 건다** — 한 곳만 틀려도 잡힌다.

        Given: 합성 시세로 돈 성적표
        When: 표본이 있는 행의 두 컬럼을 견줬을 때
        Then: 보유 중 최악 <= 최악 이다
        """
        # Given
        table = _outputs(request, slug).performance
        measured = table[table["신호"] > 0]
        assert not measured.empty, "표본이 있는 행이 없어 계약을 검사하지 못했습니다"

        # When / Then
        violations = measured[measured[self.COLUMN] > measured[self.RESULT_COLUMN]]
        assert violations.empty, f"보유 중 최악이 결과 최악보다 낫습니다:\n{violations.head()}"

    def _assert_filled(self, table: pd.DataFrame) -> None:
        """표본이 있는 행에 보유 중 최악이 채워져 있는지 본다.

        Args:
            table: 성적표
        """
        measured = table[table["신호"] > 0]
        assert not measured.empty, "표본이 있는 행이 없어 계약을 검사하지 못했습니다"
        assert not measured[self.COLUMN].isna().any(), "표본이 있는 행에 보유 중 최악이 비어 있습니다 — 매매법이 값을 넘기지 않았습니다"


class TestIntegerCounts:
    """건수 컬럼은 정수로 나간다 — 빈칸은 빈칸으로 둔 채"""

    # 건수 컬럼. **`제외` 가 `0.0` 으로 나가고 있었다** — 전체 구간엔 정수, 나머지엔 결측이라
    # pandas 열이 실수가 됐다. 같은 구조가 나머지 넷에도 있어 0건 구간이 하나만 생기면
    # 그 열 전체가 `11.0` 로 바뀐다
    COUNT_COLUMNS = ("신호", "질 때 표본", "갭손절", "장중손절")

    def test_박아_둔_건수_목록이_프로덕션과_어긋나지_않는다(self) -> None:
        """
        목적: 건수 컬럼이 하나 늘었을 때 **검사에서 조용히 빠지는 것**을 막는다

        **목록을 `periods.COUNT_COLUMNS` 로 대체하지 않는다** — 이 파일의 규율은 기대값을
        손으로 박는 것이고(머리말), 상수를 가져오면 그 상수를 고치는 순간 테스트가 따라와
        아무것도 고정하지 못한다. **대신 두 벌이 어긋나면 여기서 실패하게 한다.**

        Given: 손으로 박은 목록과 정수화의 소유자가 아는 목록
        When: 둘을 비교한다
        Then: `사건`(역방향 전용, 별도 테스트가 본다)을 빼면 같다
        """
        # Given
        owned = set(periods.COUNT_COLUMNS)

        # When / Then
        assert set(self.COUNT_COLUMNS) | {DISPLAY_EVENT_COUNT} == owned, (
            f"건수 컬럼이 어긋납니다 — 손으로 박은 목록 {sorted(self.COUNT_COLUMNS)} · " f"프로덕션 {sorted(owned)}"
        )

    def test_역방향_사건도_정수형이다(self, reverse_outputs: StrategyOutputs) -> None:
        """
        목적: 매매법 고유 건수 컬럼도 같은 규칙을 받는다

        Given: 합성 시세로 돈 역방향 결과
        When: `사건` 컬럼의 dtype 을 봤을 때
        Then: 결측을 담을 수 있는 정수형이다
        """
        # Given / When / Then
        assert str(reverse_outputs.performance[DISPLAY_EVENT_COUNT].dtype) == "Int64"

    def test_정수형이어도_빈칸은_빈칸으로_저장된다(self, tmp_path: Path) -> None:
        """
        목적: 정수화가 빈칸을 `0` 으로 바꾸지 않는지 확인한다 — 그러면 원래 문제가 뒤집혀 재발한다

        표본이 0건인 구간은 **잰 적이 없는 것**이라 건수도 빈칸이다.
        `0` 을 적으면 「손절이 한 번도 안 걸렸다」로 읽혀 정반대의 사실이 된다.

        **`,,` 가 문자열에 있는지만 보면 안 된다** — 표본 0건 행은 실수 지표 칸이 원래 줄줄이 비어
        있어, 건수 칸이 `0` 으로 채워져도 그 검사는 통과한다. 그래서 건수 칸을 이름으로 읽는다.

        Given: 신호를 앞쪽에만 심은 합성 시세 (최근 5년 구간이 0건이 된다)
        When: 그 구간 행을 CSV 문자열로 뽑아 문자열 그대로 다시 읽었을 때
        Then: 건수 칸이 빈칸이고, `신호` 는 정수 `0` 이다 (0건인 것은 잰 사실이다)
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "early", "SYN", EARLY_SIGNAL_POSITIONS))
        summary = run_reverse_trading([target], stop_levels=(STOP_LOSS_LEVEL,)).performance
        empty = summary[summary[DISPLAY_SIGNAL_COUNT] == 0]
        assert not empty.empty, "표본 0건 구간이 없어 계약을 검사하지 못했습니다 — 신호 위치를 앞으로 옮기세요"

        # When
        text = empty.head(1).to_csv(index=False)
        cells = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False).iloc[0]

        # Then
        blank_columns = [
            *(column for column in self.COUNT_COLUMNS if column != DISPLAY_SIGNAL_COUNT),
            DISPLAY_EVENT_COUNT,
        ]
        filled = {column: cells[column] for column in blank_columns if cells[column] != ""}
        assert filled == {}, f"잰 적이 없는 건수 칸이 값으로 채워졌습니다: {filled}"
        assert cells[DISPLAY_SIGNAL_COUNT] == "0", f"표본 수가 정수 0 이 아닙니다: {cells[DISPLAY_SIGNAL_COUNT]!r}"


class TestRunSummary:
    """`summary.json` — 매매법 전부가 같은 틀을 쓴다"""

    @pytest.fixture
    def summaries(self, request: pytest.FixtureRequest) -> dict[str, dict[str, object]]:
        """매매법 전부의 실행 요약 (slug → 요약). 목록은 `METHOD_SPECS` 를 따른다."""
        return {slug: _outputs(request, slug).summary for slug in sorted(METHOD_SPECS)}

    def test_요약이_같은_최상위_키를_갖는다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 만드는 자리·키가 매매법마다 갈리지 않게 한다

        매매법이 각자 요약을 만들면 같은 질문(무엇을 어느 기간으로 돌렸나)에 요약마다 다른 키로
        답하게 되고, 만드는 자리가 CLI 로 새면 키가 스크립트마다 갈린다.

        Given: 매매법 전부의 실행 요약
        When: 최상위 키를 봤을 때
        Then: 여섯 키가 전부 있다
        """
        # Given
        expected = {KEY_TRACK, KEY_DATASETS, KEY_RULE, KEY_ROW_COUNTS, KEY_COST, KEY_NOTES}

        # When / Then
        for name, summary in summaries.items():
            assert set(summary) == expected, f"{name} 의 요약 키가 다릅니다: {sorted(summary)}"

    def test_대상_범위와_기간이_datasets_에_있다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 「범위의 SoT 는 `summary.json` 의 `datasets`」를 매매법 전부가 실제로 이행한다

        그 키가 없는 매매법이 하나라도 있으면 그 매매법의 종목코드가 어디에도 남지 않는다.

        Given: 매매법 전부의 실행 요약
        When: `datasets` 의 한 줄을 봤을 때
        Then: 코드·이름·파일·기간·행 수가 전부 있다
        """
        # Given
        expected = {KEY_DATASET_TICKER, KEY_DATASET_LABEL, KEY_DATASET_FILE, KEY_DATASET_PERIOD, KEY_DATASET_ROWS}

        # When / Then
        for name, summary in summaries.items():
            records = summary[KEY_DATASETS]
            assert isinstance(records, list) and records, f"{name} 의 datasets 가 비었습니다"
            for record in records:
                assert set(record) == expected, f"{name} 의 datasets 한 줄이 다릅니다: {sorted(record)}"

    def test_요약에_절대경로가_없다(
        self,
        summaries: dict[str, dict[str, object]],
        assert_no_absolute_paths: Callable[[object, str], None],
    ) -> None:
        """
        목적: 두 PC 를 오가는 산출물에 그 PC 의 절대경로가 박히지 않게 한다

        `dataset_record` 가 `file` 에 이름만 담는 것은 그 함수의 docstring 이 말하지만,
        **`rule` 과 `notes` 는 매매법이 각자 채운다** — 거기로 경로가 들어와도 아무도 안 본다.
        요약 전체를 재귀로 훑어야 그 자리까지 닫힌다.

        Given: 매매법 전부의 실행 요약
        When: 요약 전체를 재귀로 훑었을 때
        Then: 절대경로로 읽히는 문자열이 하나도 없다
        """
        # Given / When / Then
        for name, summary in summaries.items():
            assert_no_absolute_paths(summary, name)

    def test_row_counts_의_키가_파일_이름이다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: `"performance"` 같은 별칭을 막는다 — 별칭은 그 이름의 파일이 사라져도 남는다

        파일 이름으로 키잉하면 스크립트가 `summary[row_counts][SUMMARY_FILENAME]` 로 읽으므로
        별칭을 따로 관리할 필요가 없어진다.

        Given: 매매법 전부의 실행 요약
        When: `row_counts` 의 키를 봤을 때
        Then: 전부 `.csv` 로 끝나고 성적표·거래내역이 들어 있다
        """
        # Given / When / Then
        for name, summary in summaries.items():
            counts = summary[KEY_ROW_COUNTS]
            assert isinstance(counts, dict)
            assert all(key.endswith(".csv") for key in counts), f"{name} 의 row_counts 키가 파일 이름이 아닙니다: {sorted(counts)}"
            assert SUMMARY_FILENAME in counts, f"{name} 에 성적표 행 수가 없습니다"
            assert TRADES_FILENAME in counts, f"{name} 에 거래내역 행 수가 없습니다"

    def test_비용_표기가_매매법_모두에_있다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: `.claude/rules/trading.md` 의 맨몸 성적 표기를 매매법 전부가 갖는지 고정한다

        빠뜨린 것과 일부러 뺀 것을 구별할 수 없으면 다음 사람이 다시 계산한다.

        Given: 매매법 전부의 실행 요약
        When: `cost` 를 봤을 때
        Then: 모두 같은 문장이다
        """
        # Given / When / Then
        for name, summary in summaries.items():
            assert summary[KEY_COST] == COST_NOTE, f"{name} 의 비용 표기가 다릅니다"

    def test_요약에_옛_slug_가_값으로_남아_있지_않다(self, summaries: dict[str, dict[str, object]]) -> None:
        """
        목적: 옛 slug 가 **데이터 값**으로 되살아나는 것을 막는다

        요약이 `"strategy": "reverse_trading"` 이라고 적으면 폴더 이름(`reverse`)과 갈린다 —
        slug 의 정의처는 `studies/<slug>/constants.py` 의 `TRACK_NAME` 하나다.

        Given: 매매법 전부의 실행 요약
        When: 요약 전체를 문자열로 봤을 때
        Then: 옛 이름이 하나도 없다
        """
        # Given
        stale = ("reverse_trading", "expiry_trading", "index_extreme", "kosdaq_month_end")

        # When / Then
        for name, summary in summaries.items():
            text = json.dumps(summary, ensure_ascii=False)
            for word in stale:
                assert word not in text, f"{name} 의 요약에 옛 이름 {word} 이 남아 있습니다"


class TestDatasetFields:
    """`Dataset` 의 필드 뜻 — 매매법마다 같다"""

    @_BY_METHOD
    def test_Dataset_이_코드와_이름을_따로_갖는다(self, slug: str) -> None:
        """
        목적: 필드 이름이 모듈마다 다른 것을 가리키던 상태를 닫는다

        한때 `ticker` 에 **표시 이름**이 들어 있고 종목코드가 어디에도 없는 매매법이 있었다.
        미국 ETF 는 둘이 같아(`QQQ`) 드러나지 않았고, 국내에서만 `"ticker": "KODEX 200"` 으로
        새어 나왔다 — **둘 다 `str` 이라 타입 검사가 못 잡는다.**

        **「둘이 다르다」가 아니라 `ticker` 의 모양으로 잰다** — 미국 ETF 는 코드와 이름이 같아(`QQQ`)
        다름을 단언할 수 없다. 표시 이름이 `ticker` 에 들어가면 공백·한글·소문자 때문에 모양에서 걸린다.

        Given: 그 매매법의 데이터셋 목록
        When: 각 데이터셋의 필드를 봤을 때
        Then: `label` 이 있고, `ticker` 가 종목코드 모양(`TICKER_SHAPE`)이다
        """
        # Given
        datasets = _method_constants(slug).DATASETS
        assert datasets, f"{slug} 의 데이터셋 목록이 비어 있습니다"

        # When / Then
        for dataset in datasets:
            assert TICKER_SHAPE.fullmatch(
                dataset.ticker
            ), f"{slug} 의 데이터셋 ticker {dataset.ticker!r} 가 종목코드 모양이 아닙니다 — 표시 이름이 들어갔는지 보세요"
            assert dataset.label, f"{slug} 의 데이터셋에 표시 이름이 없습니다"


class TestScreenColumn:
    """`1차 판정` — 성적표 안의 판정 (2026-09-16 통합)

    **판정표를 따로 내지 않는다.** 맨몸(무손절) 판정과 확정 손절선 판정이 갈리는 칸이
    실재하고(실측 사례: 옵션 만기일 96칸 중 3칸, 그중 둘은 기대값 부호까지 뒤집혔다), 두 파일로 두면
    사용자가 범위를 좁힐 때 그 차이가 보이지 않는다.

    **게이트는 「전체」 구간 하나만 본다** (루트 `CLAUDE.md` 2026-09-12 개정). 쪼개면 칸당
    표본이 5~6건까지 줄어 한 건이 20%p 를 움직이므로, 그 값으로 칸을 떨어뜨리면 멀쩡한
    매매법이 우연으로 죽는다. 나머지 네 구간은 **「판정 안 함」**이다 — 빈칸으로 두면
    「잴 수 없었다」로 읽히는데 실제로는 **「묻지 않았다」**이다.
    """

    # 판정 값 셋. **손으로 박아 둔다** — 프로덕션 상수를 import 하면 그 상수를 고치는 순간
    # 테스트가 따라와 아무것도 고정하지 못한다 (이 모듈 머리말)
    VERDICTS = frozenset({"후보", "제외", "판정 안 함"})
    NOT_JUDGED = "판정 안 함"
    PERIOD_ALL_LABEL = "전체"
    SCREEN_COLUMN = "1차 판정"

    @_BY_METHOD
    def test_성적표가_판정_값_셋만_쓴다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 값 집합이 매매법마다 갈리면 성적표들을 한 필터로 읽을 수 없다.

        Given: 그 매매법의 성적표
        When: 판정 컬럼의 값을 모았을 때
        Then: 모두 정해진 세 값 안에 든다
        """
        # Given / When / Then
        values = set(_outputs(request, slug).performance[self.SCREEN_COLUMN])
        assert values <= self.VERDICTS, f"{slug} 성적표에 정의되지 않은 판정 값이 있습니다: {values - self.VERDICTS}"

    @_BY_METHOD
    def test_시기가_전체가_아닌_행은_판정하지_않는다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: **게이트를 시기 행에 걸지 않는다**는 2026-09-12 개정을 고정한다.

        걸면 「최근 5년 → 제외」가 표에 찍히고, 그걸로 거르는 순간 표본 5~6건짜리 구간이
        멀쩡한 칸을 떨어뜨린다.

        Given: 그 매매법의 성적표
        When: 시기가 「전체」가 아닌 행의 판정을 봤을 때
        Then: 전부 「판정 안 함」이다
        """
        # Given / When / Then
        table = _outputs(request, slug).performance
        split = table[table[DISPLAY_PERIOD] != self.PERIOD_ALL_LABEL]
        assert not split.empty, f"{slug} 성적표에 시기 행이 없어 계약을 검사하지 못했습니다"
        assert (split[self.SCREEN_COLUMN] == self.NOT_JUDGED).all(), f"{slug} 성적표의 시기 행에 게이트가 걸렸습니다"

    @_BY_METHOD
    def test_전체_행에서는_실제로_판정한다(self, slug: str, request: pytest.FixtureRequest) -> None:
        """
        목적: 전 행이 「판정 안 함」이 되어 컬럼이 무의미해지는 것을 막는다.

        **살 수 있는 대상의 행만 본다** — 지수를 함께 재는 매매법(중간선거_사이클)은 그 행이
        「판정 안 함」이 정상이고(아래 테스트가 그것을 따로 고정한다), 섞어 세면 이 검사가
        **없는 버그를 가리킨다.** 합성 지수 행이 없는 매매법에서는 거를 것이 없다.

        Given: 합성 시세로 돈 그 매매법의 결과
        When: 시기가 「전체」이고 살 수 있는 대상인 행의 판정을 봤을 때
        Then: 「판정 안 함」이 아니다
        """
        # Given
        table = _outputs(request, slug).performance
        tradable = table[table[DISPLAY_TICKER] != INDEX_LABEL]

        # When / Then
        whole = tradable[tradable[DISPLAY_PERIOD] == self.PERIOD_ALL_LABEL]
        assert not whole.empty, f"{slug} 성적표에 전체 구간 행이 없습니다"
        assert (whole[self.SCREEN_COLUMN] != self.NOT_JUDGED).all(), f"{slug} 성적표가 아무것도 판정하지 않았습니다"

    def test_살_수_없는_대상은_전체_행에서도_판정하지_않는다(self, midterm_cycle_outputs: MidtermCycleOutputs) -> None:
        """
        목적: 지수로 「우위가 있다」를 주장하면 **집행할 수 없는 성적이 근거**가 된다
              (측정의 원칙 9).

        Given: 합성 시세와 합성 지수로 돈 중간선거_사이클 결과
        When: 지수 행의 판정을 봤을 때
        Then: 시기와 무관하게 전부 「판정 안 함」이다
        """
        # Given
        table = midterm_cycle_outputs.performance
        index_rows = table[table[DISPLAY_TICKER] == INDEX_LABEL]
        assert not index_rows.empty, "지수 행이 없어 계약을 검사하지 못했습니다"

        # When / Then
        assert (index_rows[self.SCREEN_COLUMN] == self.NOT_JUDGED).all()

    def test_표본이_0건인_구간은_판정_안_함이다(self, tmp_path: Path) -> None:
        """
        목적: 「재봤더니 아니었다」와 「재본 적이 없다」를 가른다.

        0건 칸은 지표가 결측이라 비교가 전부 거짓이 되고, 가드가 없으면 「제외」로 찍힌다.

        Given: 신호를 앞쪽에만 심어 최근 5년이 0건이 되는 합성 시세
        When: 표본 0건 행의 판정을 봤을 때
        Then: 「판정 안 함」이다
        """
        # Given
        target = _reverse_target(_write_market(tmp_path / "empty", "SYN", EARLY_SIGNAL_POSITIONS))

        # When
        summary = run_reverse_trading([target], stop_levels=(STOP_LOSS_LEVEL,)).performance
        empty = summary[summary[DISPLAY_SIGNAL_COUNT] == 0]

        # Then
        assert not empty.empty, "표본 0건 구간이 없어 계약을 검사하지 못했습니다"
        assert (empty[self.SCREEN_COLUMN] == self.NOT_JUDGED).all()

    def test_판정이_승률과_평균에서_그대로_유도된다(self, midterm_cycle_grid_outputs: MidtermCycleOutputs) -> None:
        """
        목적: **같은 행의 값으로 다시 세지 않는다** (절대 원칙 5 — 판정식 단일화).

        성적표가 판정을 따로 계산하면 같은 행 안에서 승률·평균과 판정이 어긋날 수 있다.
        **격자를 켠 실행을 쓴다** — 기본 실행(무손절 한 종)은 합성 입력에서 판정이 「후보」와
        「판정 안 함」뿐이라 「제외」 쪽 분기를 한 번도 지나지 않는다.

        Given: 합성 시세로 손절선 격자를 켜고 돈 중간선거_사이클 성적표의 전체 구간 행
        When: 그 행의 승률·평균으로 게이트를 직접 걸었을 때
        Then: 행에 실린 판정과 같다
        """
        # Given
        from verify_lab.measure.screening import SCREEN_CANDIDATE, SCREEN_EXCLUDED

        table = midterm_cycle_grid_outputs.performance
        whole = table[table[DISPLAY_PERIOD] == self.PERIOD_ALL_LABEL]
        assert not whole.empty, "전체 구간 행이 없습니다"
        assert set(whole[self.SCREEN_COLUMN]) >= {
            SCREEN_CANDIDATE,
            SCREEN_EXCLUDED,
        }, "「후보」와 「제외」가 함께 있어야 두 분기를 모두 검사합니다"

        # When / Then — 게이트는 **회당 기대값 1.0% 이상 하나뿐**이다 (손으로 박아 둔다).
        # 여기서 상수를 가져오면 게이트가 바뀌어도 이 검사가 함께 따라와 **독립 검증이 아니게
        # 된다** — 그래서 일부러 숫자를 박는다.
        # **승률은 판정에 들어가지 않는다** (2026-09-17). 조건이 다시 늘면 여기서 걸린다.
        # **판정은 세 값이다** — 표본이 0건이거나 평균이 결측인 행은 「판정 안 함」이며,
        # 두 값만 기대하면 그 행에서 없는 게이트 버그를 가리키게 된다
        for _, row in whole.iterrows():
            if row[DISPLAY_TICKER] == INDEX_LABEL or row[DISPLAY_SIGNAL_COUNT] == 0 or pd.isna(row["평균(%)"]):
                # 살 수 없는 대상은 게이트 결과와 «무관하게» 판정 안 함이다 (측정의 원칙 9)
                expected = self.NOT_JUDGED
            elif row["평균(%)"] >= 1.0:
                expected = SCREEN_CANDIDATE
            else:
                expected = SCREEN_EXCLUDED
            assert row[self.SCREEN_COLUMN] == expected, f"판정이 같은 행의 평균과 어긋납니다: {dict(row)}"


class TestNoCandidatesFile:
    """판정표 파일을 더 이상 내지 않는다

    「1차 판정」이라는 개념이 성적표로 통합됐으므로, 같은 판정을 담은 **두 번째 파일**이
    남아 있으면 어느 쪽이 현재인지 매번 판별해야 한다.

    **값이 사라지는 것이 아니다** — 판정표의 축과 값은 축별 집계표(`통계.csv`·`측정.csv`)가
    담고, `적중률 = 오른/내린 비율` · `방향 기대값 = ±평균` 으로 그 자리에서 다시 계산된다.
    """

    @_BY_METHOD
    def test_매매법_산출물에_판정표가_없다(self, slug: str) -> None:
        """
        목적: 산출물 목록에서 판정표가 빠졌는지 고정한다.

        Given: 그 매매법의 산출물 파일 목록
        When: 판정표 이름을 찾았을 때
        Then: 하나도 없다
        """
        # Given
        files = _method_constants(slug).OUTPUT_FILES
        assert files, f"{slug} 의 산출물 파일 목록이 비어 있습니다"

        # When / Then
        leftovers = [value for value in files.values() if "판정" in value]
        assert not leftovers, f"{slug} 이 아직 판정표를 냅니다: {leftovers}"

    def test_판정표_이름과_표_생성기가_저장소에서_사라졌다(self) -> None:
        """
        목적: 상수와 헬퍼가 남아 있으면 그 경로로 판정표가 되살아난다.

        Given: 패키지와 스크립트 소스 전체
        When: 판정표 이름 상수와 표 생성기를 찾았을 때
        Then: 하나도 없다
        """
        # Given
        sources = [
            *(BASE_DIR / "src" / "verify_lab").rglob("*.py"),
            *(BASE_DIR / "scripts").rglob("*.py"),
        ]
        assert sources, "소스를 찾지 못했습니다"

        # When / Then
        for path in sources:
            text = path.read_text(encoding="utf-8")
            where = path.relative_to(BASE_DIR)
            assert "CANDIDATES_FILENAME" not in text, f"{where} 에 판정표 이름 상수가 남아 있습니다"
            assert "build_candidates_table" not in text, f"{where} 에 판정표 생성기가 남아 있습니다"
