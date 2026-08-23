"""검증 #1 실행 계층의 계약을 고정한다.

이 계층이 틀리는 방식은 **예외 없이 결과가 그럴듯하게 나오는 것**이다. 조합 하나가 빠지거나
사건 수가 방향별로 잘못 세어져도 산출물은 정상으로 보인다. 그래서 축의 개수와 사건 수 산식,
그리고 "무엇을 잘라 넘기는가"를 손계산으로 박는다.

핵심 계약은 다섯 가지다.
- 신호군 축은 **테스트 × 파라미터 × 시작연도 × 방향 × 시대 구간 × 데이터셋**의 곱이다
- 사건 번호는 **폭등·폭락을 합친 목록**에 매기고, 방향별로는 그 방향이 걸친 사건 수를 센다
- 베이스라인 모집단은 **신호군과 같은 기간**으로 자른다
- 시대 구간은 **신호 선택의 양끝**만 좁힌다. 시세를 자르면 순위 축적이 무너진다
- 신호 0건 신호군은 집계에서 빠지되 **빠졌다는 사실이 남는다**
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    PRICE_DECIMALS,
)
from verify_lab.measure.baseline import DEFAULT_MA_WINDOW
from verify_lab.measure.forward_return import DEFAULT_HORIZONS
from verify_lab.report.constants import (
    DISPLAY_BASELINE,
    DISPLAY_BASELINE_SAMPLE,
    DISPLAY_BASIS,
    DISPLAY_DATE,
    DISPLAY_EXCLUDED,
    DISPLAY_HORIZON,
    DISPLAY_MEAN,
    DISPLAY_REVERSE_RATE,
    DISPLAY_REVERSE_RATE_EXCESS,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SIGNAL_COUNT,
    DISPLAY_WIN_RATE,
)
from verify_lab.studies.index_extreme.constants import (
    CONSECUTIVE_DIRECTION_LABELS,
    CONSECUTIVE_LENGTHS,
    DATASETS,
    DECADE_PERIODS,
    DEFAULT_START_YEAR,
    DISPLAY_BASELINE_ALL,
    DISPLAY_CLOSE,
    DISPLAY_DIRECTION,
    DISPLAY_DIRECTION_REVERSE_ALL,
    DISPLAY_EVENT_COUNT,
    DISPLAY_EVENT_ID,
    DISPLAY_GROUP_SIGNAL_COUNT,
    DISPLAY_PARAMETER,
    DISPLAY_PERIOD,
    DISPLAY_PRICE_BASIS,
    DISPLAY_PRICE_BASIS_RAW,
    DISPLAY_RANK,
    DISPLAY_START_YEAR,
    DISPLAY_TEST,
    DISPLAY_TEST_CONSECUTIVE,
    DISPLAY_TEST_EXTREME,
    DISPLAY_TICKER,
    DISPLAY_ZSCORE,
    EXTREME_DIRECTION_LABELS,
    PERIOD_ALL,
    PRICE_DECIMALS_KRW,
    RANK_CUTS,
    START_YEARS,
    Dataset,
    Direction,
)
from verify_lab.studies.index_extreme.runner import (
    IDENTITY_COLUMNS,
    KEY_BASELINE,
    KEY_DATASETS,
    KEY_DAY_COUNT,
    KEY_DIRECTION,
    KEY_EMA_UNDETERMINED,
    KEY_EMPTY_SIGNAL_GROUPS,
    KEY_EXCESS,
    KEY_PARAMETERS,
    KEY_PERIOD,
    KEY_PERMUTATION,
    KEY_POPULATIONS,
    KEY_PRICE_BASIS,
    KEY_REPEATS,
    KEY_ROW_COUNT,
    KEY_ROW_COUNTS,
    KEY_SEED,
    KEY_SIGNAL_GROUP_COUNT,
    KEY_SIGNALS,
    KEY_SMA_UNDETERMINED,
    KEY_START_YEAR,
    KEY_STATISTICS,
    KEY_TEST_TABLE,
    StudyOutputs,
    run_study,
)

# 합성 시세를 만드는 난수 시드. 시드 없는 난수는 금지이며 값이 흔들리면 계약도 흔들린다
SYNTHETIC_SEED = 20260814

# 순위 축적 구간에 심는 등락의 크기. 집계 구간에서는 이보다 큰 등락만 상위 컷에 든다
ACCUMULATION_SHOCK = 0.08

# 검정 반복 수. 계약을 재는 테스트라 귀무분포의 정밀도는 필요하지 않다
TEST_REPEATS = 5

# 사건이 몰린 시세의 길이와 사건을 심는 위치 (끝에서 이만큼 앞)
CLUSTERED_ROWS = 2_600
CLUSTERED_OFFSET = 400

# 상승 방향 신호군의 표시 이름. 이 방향에서는 **하락이 역방향**이다
UPWARD_DIRECTIONS = (EXTREME_DIRECTION_LABELS[Direction.UP], CONSECUTIVE_DIRECTION_LABELS[Direction.UP])

# 하락 방향 신호군의 표시 이름. 여집합으로 고르면 `역방향 전체` 까지 딸려 들어온다
DOWNWARD_DIRECTIONS = (EXTREME_DIRECTION_LABELS[Direction.DOWN], CONSECUTIVE_DIRECTION_LABELS[Direction.DOWN])

# 백분율 지표의 허용오차 (tests/CLAUDE.md 허용오차 기준)
RATE_TOLERANCE = 0.1

# 측정 구간 하나를 골라 손으로 검산할 때 쓰는 이름. `build_signal_table` 이 기준과 구간
# 이름을 붙여 컬럼을 만들고, 집계표는 구간 이름만 담는다
ONE_DAY_LABEL = "1일"
CLOSE_ONE_DAY_COLUMN = f"종가 {ONE_DAY_LABEL}"


def _quiet_changes(count: int) -> np.ndarray:
    """등락이 작고 서로 겹치지 않는 배경 등락률을 만든다.

    배경이 조용해야 나중에 심는 큰 등락만 상위 순위에 들어와 신호를 손으로 셀 수 있다.
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)

    return rng.normal(0.0004, 0.006, count)


def _market_frame(dates: pd.DatetimeIndex, changes: Sequence[float]) -> pd.DataFrame:
    """등락률 목록으로 시세 프레임을 만든다.

    첫 행은 등락률이 없으므로 `changes` 는 `dates` 보다 하나 짧다. 시가는 전일 종가에서
    살짝 벌려 두 수익률 기준(종가·익일 시가)이 같은 값이 되지 않게 한다.
    """
    closes = 100.0 * np.cumprod(np.concatenate([[1.0], 1.0 + np.asarray(changes, dtype=float)]))
    opens = np.concatenate([[closes[0]], closes[:-1] * 1.001])

    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: opens,
            COL_HIGH: np.maximum(opens, closes) * 1.002,
            COL_LOW: np.minimum(opens, closes) * 0.998,
            COL_CLOSE: closes,
            COL_VOLUME: 1_000_000,
        }
    )


def _clustered_frame() -> pd.DataFrame:
    """한 사건에 폭락 2건과 폭등 1건이 몰려 있고, 뒤에 별개 폭락이 하나 더 있는 시세.

    순위 축적 구간(집계 시작 전)에 상위 컷을 채울 만큼의 등락을 심어, 집계 구간에서는
    그보다 큰 등락만 신호가 되게 한다. 그래야 신호를 손으로 셀 수 있다.
    """
    dates = pd.DatetimeIndex(pd.bdate_range("2003-01-01", periods=CLUSTERED_ROWS))
    changes = _quiet_changes(len(dates) - 1)

    # 1. 순위 축적 구간을 컷보다 많은 등락으로 채운다 (집계 시작 전이라 신호가 아니다)
    for offset in range(max(RANK_CUTS) + 2):
        changes[100 + offset * 10] = ACCUMULATION_SHOCK
        changes[105 + offset * 10] = -ACCUMULATION_SHOCK

    # 2. 집계 구간에 사건 두 개를 심는다.
    #    앞의 셋은 달력 30일 안에 붙어 한 사건, 마지막 하나는 훨씬 뒤라 별개 사건이다
    base = len(dates) - CLUSTERED_OFFSET
    changes[base] = -0.12
    changes[base + 3] = 0.13
    changes[base + 5] = -0.11
    changes[base + 200] = -0.14

    return _market_frame(dates, changes)


def _alternating_changes(count: int) -> np.ndarray:
    """3일 연속이 정확히 세 번만 나오는 등락률을 만든다.

    배경은 하루씩 방향이 바뀌어 연속이 1로 유지되고, 심은 자리에서만 같은 방향이 3일 이어진다.
    날짜가 달력 하루 간격이므로 신호 사이의 달력 간격이 행 간격과 같다 —
    사건 묶기 창(달력 30일)의 경계를 손으로 잡을 수 있다.
    """
    signs = np.where(np.arange(count) % 2 == 0, 1, -1)

    # 상승 → (20일) 하락 → (20일) 상승. 두 상승은 40일 떨어져 방향별로는 다른 사건이다
    for end, sign in ((100, 1), (120, -1), (140, 1)):
        signs[end - 3] = -sign
        signs[end - 2 : end + 1] = sign
        signs[end + 1] = -sign
        signs[end + 2] = sign

    return signs * 0.004


def _write_dataset(
    directory: Path,
    frame: pd.DataFrame,
    *,
    key: str = "synthetic",
    ticker: str = "합성",
    price_basis: str = "원본가",
    price_decimals: int = PRICE_DECIMALS_KRW,
) -> Dataset:
    """시세 프레임을 CSV 로 저장하고 그 파일을 가리키는 데이터셋을 돌려준다.

    실경로 `storage/` 를 건드리지 않도록 언제나 임시 디렉터리에 쓴다.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.csv"
    saved = frame.copy()
    saved[COL_DATE] = pd.to_datetime(saved[COL_DATE]).dt.strftime("%Y-%m-%d")
    saved.to_csv(path, index=False)

    return Dataset(key=key, ticker=ticker, price_basis=price_basis, path=path, price_decimals=price_decimals)


def _single_axis_run(dataset: Dataset, **overrides: object) -> StudyOutputs:
    """축을 하나씩만 남긴 실행. 손으로 셀 수 있는 크기로 줄인다."""
    axes: dict[str, object] = {
        "rank_cuts": (RANK_CUTS[1],),
        "consecutive_lengths": (CONSECUTIVE_LENGTHS[0],),
        "start_years": (DEFAULT_START_YEAR,),
        "repeats": TEST_REPEATS,
    }
    axes.update(overrides)

    return run_study([dataset], **axes)


@pytest.fixture(scope="module")
def wide_outputs(tmp_path_factory: pytest.TempPathFactory) -> StudyOutputs:
    """모든 축을 실제 상수로 도는 실행 결과 (모듈 안에서 한 번만 만든다).

    시작연도 4개와 시대 구간 2개를 모두 덮으려면 20년이 필요하다. 날짜 간격은 계약과
    무관하므로 주 단위로 띄워 행 수를 줄인다 — 측정 구간은 달력이 아니라 위치로 세기 때문이다.
    """
    dates = pd.DatetimeIndex(pd.date_range("2003-01-06", periods=1_000, freq="7D"))
    frame = _market_frame(dates, _quiet_changes(len(dates) - 1))
    dataset = _write_dataset(tmp_path_factory.mktemp("wide"), frame)

    return run_study([dataset], repeats=TEST_REPEATS)


@pytest.fixture(scope="module")
def spanning_outputs(tmp_path_factory: pytest.TempPathFactory) -> StudyOutputs:
    """2010년대와 2020년대에 모두 걸치는 시세로 돈 실행 결과."""
    dates = pd.DatetimeIndex(pd.bdate_range("2003-01-01", periods=5_200))
    dataset = _write_dataset(tmp_path_factory.mktemp("spanning"), _market_frame(dates, _quiet_changes(len(dates) - 1)))

    return _single_axis_run(dataset)


class TestSignalGroupAxes:
    """조합 순회 계약"""

    def test_신호군은_모든_축의_곱만큼_생긴다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 강건성 조합이 한 실행에서 전부 산출되는지 고정한다

        방향 축은 이벤트 정의가 내는 두 방향에 **`역방향 전체` 신호군이 하나 더** 붙는다.

        Given: 시작연도 4개와 시대 구간 2개를 모두 덮는 합성 시세 하나
        When: 실제 상수로 실행했을 때
        Then: 집계된 신호군 수 + 신호 0건이라 빠진 신호군 수 = 축의 곱
        """
        # Given
        summary = wide_outputs.summary
        parameters = len(RANK_CUTS) + len(CONSECUTIVE_LENGTHS)
        windows = len(START_YEARS) + len(DECADE_PERIODS)

        # When
        counted = summary[KEY_SIGNAL_GROUP_COUNT] + len(summary[KEY_EMPTY_SIGNAL_GROUPS])

        # Then
        assert counted == parameters * (len(Direction) + 1) * windows

    def test_시대_구간은_기본_시작연도에만_붙는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 시대 구간이 모든 시작연도에 곱해지지 않는지 고정한다

        Given: 실제 상수로 돈 실행 결과
        When: 시대 구간이 "전체" 가 아닌 행만 골랐을 때
        Then: 시작연도가 전부 기본 시작연도다
        """
        # Given / When
        decades = wide_outputs.statistics[wide_outputs.statistics[DISPLAY_PERIOD] != PERIOD_ALL.label]

        # Then
        assert set(decades[DISPLAY_START_YEAR]) == {DEFAULT_START_YEAR}
        assert set(decades[DISPLAY_PERIOD]) == {period.label for period in DECADE_PERIODS}

    def test_식별_컬럼이_네_표에_모두_앞에_붙는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 어느 산출물을 열어도 어떤 신호군의 값인지 알 수 있는지 고정한다

        Given: 실행 결과의 표 4개
        When: 각 표의 앞쪽 컬럼을 봤을 때
        Then: 식별 컬럼이 순서대로 맨 앞에 있다
        """
        # Given
        tables = (wide_outputs.signals, wide_outputs.statistics, wide_outputs.excess, wide_outputs.test)

        # When / Then
        for table in tables:
            assert list(table.columns[: len(IDENTITY_COLUMNS)]) == list(IDENTITY_COLUMNS)

    def test_식별_컬럼은_여섯_개이고_가격기준을_담지_않는다(self) -> None:
        """
        목적: 식별 컬럼의 구성을 상수가 아니라 값으로 고정한다

        위의 `test_식별_컬럼이_네_표에_모두_앞에_붙는다` 는 `IDENTITY_COLUMNS` 를 그대로 참조하므로
        **상수를 바꾸면 테스트도 따라가 구성이 고정되지 않는다.**

        `가격기준` 은 이 프로젝트에서 **축이 아니라 상수**다(전 시장 원본가). 값이 하나뿐인 컬럼을
        행마다 반복하면 대조할 때 고를 것이 없는 필터가 하나 끼어든다. 가격 기준은 **행 단위가 아니라
        데이터셋 단위 속성**이므로 `summary.json` 이 제 자리다.

        Given: 식별 컬럼 정의
        When: 구성을 봤을 때
        Then: 종목·테스트·파라미터·시작연도·방향·시대 구간 여섯 개다
        """
        # Given / When / Then
        assert IDENTITY_COLUMNS == ("종목", "테스트", "파라미터", "시작연도", "방향", "시대 구간")

    def test_테스트별로_파라미터_접두사가_갈린다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 한 컬럼에 담긴 K 와 N 이 서로 구분되는지 고정한다

        Given: 실행 결과의 집계표
        When: 테스트별 파라미터 값을 모았을 때
        Then: 테스트 A 는 순위 컷, 테스트 B 는 연속 일수만 담는다
        """
        # Given
        statistics = wide_outputs.statistics

        # When
        extreme = set(statistics.loc[statistics[DISPLAY_TEST] == DISPLAY_TEST_EXTREME, DISPLAY_PARAMETER])
        consecutive = set(statistics.loc[statistics[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE, DISPLAY_PARAMETER])

        # Then
        assert extreme == {f"K={cut}" for cut in RANK_CUTS}
        assert consecutive == {f"N={length}" for length in CONSECUTIVE_LENGTHS}

    def test_각_신호군은_종가_구간만큼의_집계_칸을_낸다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 칸 구성이 신호군마다 달라지지 않는지 고정한다

        집계는 **종가 기준만** 받는다 (스펙 §7 결정 ㉓). 익일시가는 `signals.csv` 의
        원자료로만 남고 평균·승률로 집계되지 않는다.

        Given: 실행 결과의 집계표
        When: 신호군별 행 수를 셌을 때
        Then: 전부 종가 구간 수만큼이다
        """
        # Given / When
        rows_per_group = wide_outputs.statistics.groupby(list(IDENTITY_COLUMNS), sort=False).size()

        # Then
        assert set(rows_per_group) == {len(DEFAULT_HORIZONS)}

    def test_집계_세_표에_기준_컬럼이_없다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: `기준` 이 상수가 됐으므로 식별 컬럼에서 뺀다 (스펙 §7 결정 ㉔)

        고를 것이 없는 필터는 대조를 방해하기만 한다. 무엇으로 쟀는지는
        `summary.json` 이 데이터셋 단위로 기록한다.

        Given: 실행 결과의 집계·초과분·검정표
        When: 컬럼 구성을 확인했을 때
        Then: 어느 표에도 `기준` 컬럼이 없다
        """
        # Given / When
        tables = (wide_outputs.statistics, wide_outputs.excess, wide_outputs.test)

        # Then
        assert all(DISPLAY_BASIS not in table.columns for table in tables)

    def test_신호일_목록에는_익일시가_1일이_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 익일시가를 집계에서 뺐어도 **원자료는 남는다** (스펙 §7 결정 ㉓)

        갭으로 새는 몫의 직접 관측치이자, 갭 배수를 역산해 나머지 구간을 복원하는 수단이다.

        Given: 실행 결과의 신호일 목록
        When: 컬럼 구성을 확인했을 때
        Then: 익일시가 1일 컬럼이 하나 있고 다른 익일시가 구간은 없다
        """
        # Given / When
        next_open_columns = [column for column in wide_outputs.signals.columns if column.startswith("익일시가")]

        # Then
        assert next_open_columns == ["익일시가 1일"]

    def test_상승_방향_신호군의_역방향_비율은_하락_비율이다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 방향에 따라 무엇이 "역방향"인지 갈린다 (스펙 §7 결정 ㉒)

        폭등 신호는 인버스로 들어가므로 **가격이 내려야** 맞은 것이고, 폭락 신호는
        그대로 사므로 **올라야** 맞은 것이다. 승률 하나로는 폭등 쪽에서 정반대를 잰다.

        Given: 상승 방향(폭등·연속 상승) 신호군의 집계
        When: 역방향 비율과 승률을 비교했을 때
        Then: 둘의 합이 100% 를 넘지 않는다 (여집합 관계이며 보합이 남을 수 있다)
        """
        # Given
        upward = wide_outputs.statistics[wide_outputs.statistics[DISPLAY_DIRECTION].isin(UPWARD_DIRECTIONS)]

        # When
        total = upward[DISPLAY_WIN_RATE] + upward[DISPLAY_REVERSE_RATE]

        # Then
        assert not upward.empty
        assert bool((total <= 100.0 + RATE_TOLERANCE).all())

    def test_하락_방향_신호군의_역방향_비율은_승률과_같다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 폭락·연속 하락 신호는 **오르는 것이 곧 역방향**이라 두 값이 일치한다

        Given: 하락 방향 신호군의 집계
        When: 역방향 비율과 승률을 비교했을 때
        Then: 두 값이 모든 칸에서 같다
        """
        # Given
        downward = wide_outputs.statistics[wide_outputs.statistics[DISPLAY_DIRECTION].isin(DOWNWARD_DIRECTIONS)]

        # When / Then
        assert not downward.empty
        assert downward[DISPLAY_REVERSE_RATE].tolist() == downward[DISPLAY_WIN_RATE].tolist()

    def test_초과분표에도_역방향_비율_초과가_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: "평소보다 더 자주 반대로 갔는가"가 이 검증이 답하려는 질문이다

        절대 비율만으로는 "원래 그 정도 자주 내린다"와 구별되지 않는다.

        Given: 실행 결과의 초과분표
        When: 컬럼 구성을 확인했을 때
        Then: 역방향 비율 초과 컬럼이 있다
        """
        assert DISPLAY_REVERSE_RATE_EXCESS in wide_outputs.excess.columns


class TestEventCount:
    """사건 수 병기 계약"""

    @pytest.fixture
    def clustered_outputs(self, tmp_path: Path) -> StudyOutputs:
        """사건 두 개가 심긴 시세로 돈 실행 결과."""
        dataset = _write_dataset(tmp_path, _clustered_frame())

        return _single_axis_run(dataset, rank_cuts=(max(RANK_CUTS),))

    def _extreme_rows(self, table: pd.DataFrame, direction: Direction) -> pd.DataFrame:
        """테스트 A · 시대 구간 전체 · 해당 방향의 행만 고른다."""
        return table[
            (table[DISPLAY_TEST] == DISPLAY_TEST_EXTREME)
            & (table[DISPLAY_PERIOD] == PERIOD_ALL.label)
            & (table[DISPLAY_DIRECTION] == EXTREME_DIRECTION_LABELS[direction])
        ]

    def test_방향별_사건_수는_그_방향_신호가_걸친_사건_수다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 사건 번호를 방향별로 따로 매기지 않는지 고정한다

        Given: 한 사건에 폭락 2건·폭등 1건이 몰려 있고 뒤에 별개 폭락이 하나 더 있는 시세
        When: 방향별 집계표의 사건 수를 봤을 때
        Then: 폭락은 2개, 폭등은 1개다 (합친 목록에서 매긴 번호를 방향별로 센 값)
        """
        # Given / When
        plunge = self._extreme_rows(clustered_outputs.statistics, Direction.DOWN)
        surge = self._extreme_rows(clustered_outputs.statistics, Direction.UP)

        # Then
        assert set(plunge[DISPLAY_EVENT_COUNT]) == {2}
        assert set(surge[DISPLAY_EVENT_COUNT]) == {1}

    def test_사건_번호는_폭등과_폭락에_이어서_매겨진다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 같은 충격에서 나온 급락과 급반등이 한 사건으로 묶이는지 고정한다

        Given: 폭락 → 폭등 → 폭락이 달력 30일 안에 붙어 있는 시세
        When: 신호일 목록의 사건 번호를 날짜순으로 봤을 때
        Then: 몰려 있는 세 신호가 같은 번호를 받고, 뒤의 폭락만 다른 번호를 받는다
        """
        # Given
        signals = clustered_outputs.signals
        rows = signals[(signals[DISPLAY_TEST] == DISPLAY_TEST_EXTREME) & (signals[DISPLAY_PERIOD] == PERIOD_ALL.label)]

        # When
        event_ids = rows.sort_values(DISPLAY_DATE)[DISPLAY_EVENT_ID].tolist()

        # Then
        assert event_ids == [1, 1, 1, 2]

    def test_테스트_B_의_사건_수는_반대_방향_신호에_묶이지_않는다(self, tmp_path: Path) -> None:
        """
        목적: 사건 번호의 기준이 테스트마다 다르다는 결정을 고정한다

        Given: 연속 상승 → (20일 뒤) 연속 하락 → (20일 뒤) 연속 상승 이 한 번씩 있는 시세.
            두 상승은 40일 떨어져 있어 방향별로는 다른 사건이지만, 하락을 사이에 끼워 합치면
            20일씩 이어져 한 사건이 된다
        When: 연속 상승 신호군의 사건 수를 봤을 때
        Then: 2개다 (방향별로 매겼다). 합집합으로 매겼다면 1개가 나온다
        """
        # Given
        dates = pd.DatetimeIndex(pd.date_range("2011-01-03", periods=300, freq="D"))
        dataset = _write_dataset(tmp_path, _market_frame(dates, _alternating_changes(len(dates) - 1)))

        # When
        outputs = _single_axis_run(dataset)
        statistics = outputs.statistics
        rows = statistics[
            (statistics[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE) & (statistics[DISPLAY_PERIOD] == PERIOD_ALL.label)
        ]
        up = rows[rows[DISPLAY_DIRECTION] == "연속 상승"]
        down = rows[rows[DISPLAY_DIRECTION] == "연속 하락"]

        # Then
        assert set(up[DISPLAY_SIGNAL_COUNT]) == {2}
        assert set(down[DISPLAY_SIGNAL_COUNT]) == {1}
        assert set(up[DISPLAY_EVENT_COUNT]) == {2}
        assert set(down[DISPLAY_EVENT_COUNT]) == {1}

    def test_신호_수와_사건_수가_초과분표와_검정표에도_함께_남는다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 표본이 겉보기 건수만큼 독립적이지 않다는 사실이 모든 집계표에 남는지 고정한다

        Given: 폭락 신호 3건이 사건 2개에 걸친 실행 결과
        When: 초과분표와 검정표의 폭락 행을 봤을 때
        Then: 신호 3건 · 사건 2개가 함께 적혀 있다
        """
        # Given / When
        for table in (clustered_outputs.excess, clustered_outputs.test):
            plunge = self._extreme_rows(table, Direction.DOWN)

            # Then
            assert set(plunge[DISPLAY_GROUP_SIGNAL_COUNT]) == {3}
            assert set(plunge[DISPLAY_EVENT_COUNT]) == {2}


class TestBaselinePopulation:
    """베이스라인 모집단 계약"""

    def test_모집단이_신호군의_집계_시작연도로_잘린다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 신호군과 베이스라인이 같은 기간을 보는지 고정한다

        Given: 시작연도 4개를 모두 돈 실행 결과
        When: 단순 보유 모집단의 일수를 시작연도별로 봤을 때
        Then: 시작연도가 늦을수록 모집단이 작다 (전 기간 한 벌을 돌려쓰지 않았다)
        """
        # Given
        populations = [
            row
            for row in wide_outputs.summary[KEY_POPULATIONS]
            if row[KEY_BASELINE] == DISPLAY_BASELINE_ALL and row[KEY_PERIOD] == PERIOD_ALL.label
        ]

        # When
        by_start_year = {row[KEY_START_YEAR]: row[KEY_DAY_COUNT] for row in populations}
        counts = [by_start_year[year] for year in sorted(by_start_year)]

        # Then
        assert len(counts) == len(START_YEARS)
        assert counts == sorted(counts, reverse=True)
        assert len(set(counts)) == len(counts)

    def test_단순_보유_표본이_시작연도_이후_거래일에서_나온다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 모집단 크기를 손계산 값으로 박는다

        `역방향 전체` 는 대칭 모집단(원본 + 부호 반전)을 쓰므로 표본이 두 배다. 그쪽 계약은
        `TestReverseAllDirection` 이 따로 고정한다.

        Given: 실행 결과의 초과분표
        When: 기본 시작연도·구간 전체·단순 보유 베이스라인의 1일 표본 수를 봤을 때
        Then: 시작연도 이후 거래일 중 다음 날이 있는 날의 수와 같다
        """
        # Given
        total_rows = wide_outputs.summary[KEY_DATASETS][0][KEY_ROW_COUNT]
        dates = pd.DatetimeIndex(pd.date_range("2003-01-06", periods=total_rows, freq="7D"))
        expected = int((dates >= pd.Timestamp(f"{DEFAULT_START_YEAR}-01-01")).sum()) - 1

        # When
        excess = wide_outputs.excess
        rows = excess[
            (excess[DISPLAY_START_YEAR] == DEFAULT_START_YEAR)
            & (excess[DISPLAY_PERIOD] == PERIOD_ALL.label)
            & (excess[DISPLAY_BASELINE] == DISPLAY_BASELINE_ALL)
            & (excess[DISPLAY_HORIZON] == ONE_DAY_LABEL)
            & (excess[DISPLAY_DIRECTION] != DISPLAY_DIRECTION_REVERSE_ALL)
        ]

        # Then
        assert not rows.empty
        assert set(rows[DISPLAY_BASELINE_SAMPLE]) == {expected}

    def test_이동평균_판정_불가_일수가_요약에_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 창이 차기 전 구간이 조용히 사라지지 않는지 고정한다

        Given: 실행 결과의 요약
        When: 데이터셋 정보를 봤을 때
        Then: 이동평균 판정 불가 일수가 창 크기 − 1 로 남아 있다
        """
        # Given / When
        dataset_info = wide_outputs.summary[KEY_DATASETS][0]

        # Then
        assert dataset_info[KEY_SMA_UNDETERMINED] == DEFAULT_MA_WINDOW - 1
        assert dataset_info[KEY_EMA_UNDETERMINED] == DEFAULT_MA_WINDOW - 1

    def test_이동평균_창이_차지_않으면_조건부_베이스라인이_빠지고_사유가_남는다(self, tmp_path: Path) -> None:
        """
        목적: 표본이 0건인 모집단에서 예외로 죽지 않고 사유를 남기는지 고정한다 (경계 조건)

        Given: 200일 이동평균 창이 한 번도 차지 않는 짧은 시세
        When: 실행했을 때
        Then: 초과분표에 단순 보유만 남고, 모집단 일수 0 이 요약에 남는다
        """
        # Given
        dates = pd.DatetimeIndex(pd.bdate_range("2011-01-03", periods=DEFAULT_MA_WINDOW - 20))
        dataset = _write_dataset(tmp_path, _market_frame(dates, _quiet_changes(len(dates) - 1)))

        # When
        outputs = _single_axis_run(dataset)

        # Then
        assert set(outputs.excess[DISPLAY_BASELINE]) == {DISPLAY_BASELINE_ALL}
        assert [row for row in outputs.summary[KEY_POPULATIONS] if row[KEY_DAY_COUNT] == 0]


class TestPeriodFilter:
    """시대 구간 계약"""

    def test_시대_구간은_신호_선택의_양끝만_좁힌다(self, spanning_outputs: StudyOutputs) -> None:
        """
        목적: 구간 필터가 시세가 아니라 신호 선택에 걸리는지 고정한다

        Given: 2010년대와 2020년대에 걸치는 시세
        When: 구간별 신호일을 봤을 때
        Then: 두 구간의 신호일이 각 구간 안에 있고, 합치면 전체 구간의 신호일과 같다
        """
        # Given
        signals = spanning_outputs.signals
        consecutive = signals[signals[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE]

        # When
        by_period = {
            label: set(consecutive.loc[consecutive[DISPLAY_PERIOD] == label, DISPLAY_DATE])
            for label in (PERIOD_ALL.label, *(period.label for period in DECADE_PERIODS))
        }

        # Then
        assert all(date <= "2019-12-31" for date in by_period["2010년대"])
        assert all(date >= "2020-01-01" for date in by_period["2020년대"])
        assert by_period["2010년대"] | by_period["2020년대"] == by_period[PERIOD_ALL.label]

    def test_구간을_좁혀도_신호_판정_자체는_달라지지_않는다(self, spanning_outputs: StudyOutputs) -> None:
        """
        목적: 시세를 먼저 잘라 순위 축적이 무너지는 사고를 막는다

        Given: 같은 실행의 전체 구간과 2010년대 구간
        When: 2010년대에 속하는 신호일의 당시 순위를 두 구간에서 비교했을 때
        Then: 값이 같다 (구간을 좁혔다고 순위가 다시 매겨지지 않았다)
        """
        # Given
        signals = spanning_outputs.signals
        consecutive = signals[signals[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE]
        whole = consecutive[consecutive[DISPLAY_PERIOD] == PERIOD_ALL.label]
        decade = consecutive[consecutive[DISPLAY_PERIOD] == "2010년대"]

        # When
        merged = decade.merge(whole, on=[DISPLAY_DATE, DISPLAY_DIRECTION], suffixes=("_decade", "_whole"))

        # Then
        assert not merged.empty
        assert merged[f"{DISPLAY_RANK}_decade"].tolist() == merged[f"{DISPLAY_RANK}_whole"].tolist()


class TestEmptySignalGroup:
    """표본 보존 계약"""

    def test_신호_0건_신호군은_집계에서_빠지고_요약에_남는다(self, tmp_path: Path) -> None:
        """
        목적: 표본이 조용히 사라지지 않는지 고정한다 (경계 조건)

        Given: 하루도 빠짐없이 오르기만 하는 시세 — 연속 하락 신호가 나올 수 없다
        When: 연속 하락을 포함한 축으로 실행했을 때
        Then: 연속 하락 신호군이 집계표에 없고, 빠졌다는 사실이 요약에 남는다
        """
        # Given
        dates = pd.DatetimeIndex(pd.bdate_range("2003-01-01", periods=CLUSTERED_ROWS))
        rng = np.random.default_rng(SYNTHETIC_SEED)
        dataset = _write_dataset(tmp_path, _market_frame(dates, rng.uniform(0.0005, 0.004, len(dates) - 1)))

        # When
        outputs = _single_axis_run(dataset)

        # Then
        statistics = outputs.statistics
        down = statistics[
            (statistics[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE) & (statistics[DISPLAY_DIRECTION] == "연속 하락")
        ]
        assert down.empty
        assert any(row[KEY_DIRECTION] == "연속 하락" for row in outputs.summary[KEY_EMPTY_SIGNAL_GROUPS])

    def test_측정_구간_끝이_데이터를_넘는_신호의_제외_건수가_보존된다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 구간이 데이터를 넘어간 칸이 표본에서 빠지되 세어지는지 고정한다 (경계 조건)

        Given: 실행 결과의 집계표
        When: 칸마다 신호 수 − 제외 수 와 표본 수를 비교했을 때
        Then: 모든 칸에서 같고, 제외가 실제로 발생한 칸이 있다
        """
        # Given / When
        statistics = wide_outputs.statistics

        # Then
        assert (statistics[DISPLAY_SIGNAL_COUNT] - statistics[DISPLAY_EXCLUDED]).tolist() == statistics[
            DISPLAY_SAMPLE_COUNT
        ].tolist()
        assert (statistics[DISPLAY_EXCLUDED] > 0).any()


class TestLookAhead:
    """look-ahead 감시 계약"""

    @pytest.fixture
    def truncation_runner(self, tmp_path: Path) -> Callable[[pd.DataFrame], pd.DataFrame]:
        """시세 프레임을 받아 한 신호군의 신호일 목록만 돌려주는 실행기."""

        def _run(df: pd.DataFrame) -> pd.DataFrame:
            dataset = _write_dataset(tmp_path / f"cut_{len(df)}", df, key="cut")
            signals = _single_axis_run(dataset, rank_cuts=(max(RANK_CUTS),)).signals
            selected = signals[
                (signals[DISPLAY_TEST] == DISPLAY_TEST_EXTREME)
                & (signals[DISPLAY_PERIOD] == PERIOD_ALL.label)
                & (signals[DISPLAY_DIRECTION] == EXTREME_DIRECTION_LABELS[Direction.DOWN])
            ]

            return selected[[DISPLAY_DATE, DISPLAY_RANK, DISPLAY_EVENT_ID, DISPLAY_ZSCORE]].reset_index(drop=True)

        return _run

    @pytest.mark.parametrize("value_column", [DISPLAY_RANK, DISPLAY_EVENT_ID, DISPLAY_ZSCORE])
    def test_뒤를_잘라내도_신호일_목록의_부가_컬럼이_같다(
        self,
        truncation_runner: Callable[[pd.DataFrame], pd.DataFrame],
        assert_stable_under_truncation: Callable[..., None],
        value_column: str,
    ) -> None:
        """
        목적: 부가 컬럼이 미래 데이터를 참조하지 않는지 고정한다

        Given: 사건이 심긴 시세와, 뒤쪽 사건을 잘라낸 같은 시세
        When: 같은 신호군의 신호일 목록을 각각 냈을 때
        Then: 겹치는 신호일의 부가 컬럼 값이 같다
        """
        # Given
        frame = _clustered_frame()

        # When / Then
        assert_stable_under_truncation(
            truncation_runner,
            frame,
            len(frame) - 300,
            key_columns=[DISPLAY_DATE],
            value_column=value_column,
        )


class TestDeterminism:
    """재현성 계약"""

    def test_같은_시드로_두_번_돌리면_결과가_완전히_같다(self, tmp_path: Path) -> None:
        """
        목적: 측정 결과의 재현성을 고정한다

        Given: 같은 시세와 같은 시드
        When: 두 번 실행했을 때
        Then: 검정표가 값까지 완전히 같다
        """
        # Given
        dataset = _write_dataset(tmp_path, _clustered_frame())

        # When
        first = _single_axis_run(dataset, repeats=50, seed=7)
        second = _single_axis_run(dataset, repeats=50, seed=7)

        # Then
        pd.testing.assert_frame_equal(first.test, second.test)

    def test_요약에_시드와_반복_수와_파라미터가_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 산출물만 보고 어떤 설정의 결과인지 재구성할 수 있는지 고정한다

        Given: 실행 결과의 요약
        When: 파라미터 블록을 봤을 때
        Then: 시드·반복 수와 모든 축의 값이 남아 있다
        """
        # Given
        summary = wide_outputs.summary

        # When
        parameters = summary[KEY_PARAMETERS]

        # Then
        assert summary[KEY_PERMUTATION] == {KEY_REPEATS: TEST_REPEATS, KEY_SEED: 0}
        assert parameters["rank_cuts"] == list(RANK_CUTS)
        assert parameters["consecutive_lengths"] == list(CONSECUTIVE_LENGTHS)
        assert parameters["start_years"] == list(START_YEARS)
        assert parameters["horizons"] == list(DEFAULT_HORIZONS)

    def test_산출물_행_수가_요약에_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 요약이 실제 산출물과 어긋나지 않는지 고정한다

        Given: 실행 결과
        When: 요약의 행 수와 실제 표의 행 수를 비교했을 때
        Then: 네 표 모두 같다
        """
        # Given / When
        row_counts = wide_outputs.summary[KEY_ROW_COUNTS]

        # Then
        assert row_counts[KEY_SIGNALS] == len(wide_outputs.signals)
        assert row_counts[KEY_STATISTICS] == len(wide_outputs.statistics)
        assert row_counts[KEY_EXCESS] == len(wide_outputs.excess)
        assert row_counts[KEY_TEST_TABLE] == len(wide_outputs.test)


class TestMultipleDatasets:
    """여러 데이터셋을 한 실행에 담는 계약"""

    def test_요약에_데이터셋의_가격_기준이_남는다(self, wide_outputs: StudyOutputs) -> None:
        """
        목적: 식별 컬럼에서 뺀 가격 기준이 요약에는 남는지 고정한다

        `가격기준` 은 산출물 CSV 의 컬럼에서 빠졌다. 그렇다고 **"무엇으로 쟀는지"의 기록까지
        사라지면 안 된다** — 결과를 나중에 다시 열었을 때 어떤 가격으로 계산한 값인지 알 수 없게 된다.
        가격 기준은 행 단위가 아니라 데이터셋 단위 속성이므로 요약이 제 자리다.

        Given: 실행 결과의 요약
        When: 데이터셋 목록을 봤을 때
        Then: 모든 항목이 비어 있지 않은 가격 기준을 담고 있다
        """
        # Given / When
        bases = [row[KEY_PRICE_BASIS] for row in wide_outputs.summary[KEY_DATASETS]]

        # Then
        assert bases and all(bases)

    def test_두_데이터셋이_같은_실행에서_같은_파라미터로_계산된다(self, tmp_path: Path) -> None:
        """
        목적: 대조의 전제("파라미터가 같았다")가 산출물에 남는지 고정한다

        산출물에서 데이터셋을 가르는 것은 **`종목` 하나뿐**이다. 가격 기준은 식별 컬럼이 아니라
        요약에만 남으므로, 두 축을 나눠 확인한다.

        Given: 표시 이름과 가격 기준이 다른 시세 두 개
        When: 한 번의 실행으로 돌렸을 때
        Then: 산출물이 종목으로 갈리고, 요약에 두 가격 기준이 함께 남는다
        """
        # Given
        dates = pd.DatetimeIndex(pd.bdate_range("2003-01-01", periods=CLUSTERED_ROWS))
        changes = _quiet_changes(len(dates) - 1)
        raw = _write_dataset(tmp_path, _market_frame(dates, changes), key="raw", ticker="합성 원본")
        adjusted = _write_dataset(
            tmp_path,
            _market_frame(dates, changes * 1.01),
            key="adjusted",
            ticker="합성 수정",
            price_basis="수정주가",
        )

        # When
        outputs = run_study(
            [raw, adjusted],
            rank_cuts=(RANK_CUTS[1],),
            consecutive_lengths=(CONSECUTIVE_LENGTHS[0],),
            start_years=(DEFAULT_START_YEAR,),
            repeats=TEST_REPEATS,
        )

        # Then
        assert set(outputs.statistics[DISPLAY_TICKER]) == {"합성 원본", "합성 수정"}
        assert DISPLAY_PRICE_BASIS not in outputs.statistics.columns
        assert {row[KEY_PRICE_BASIS] for row in outputs.summary[KEY_DATASETS]} == {"원본가", "수정주가"}

    def test_종가_반올림_자릿수는_데이터셋이_정한다(self, tmp_path: Path) -> None:
        """
        목적: 원화 가격에 없는 소수 자리가 붙지 않는지 고정한다

        Given: 반올림 자릿수가 0 인 데이터셋
        When: 신호일 목록의 종가를 봤을 때
        Then: 전부 정수값이다
        """
        # Given
        dataset = _write_dataset(tmp_path, _clustered_frame())

        # When
        outputs = _single_axis_run(dataset)

        # Then
        closes = outputs.signals[DISPLAY_CLOSE].to_numpy(dtype=float)
        assert closes.tolist() == np.round(closes).tolist()

    def test_소수_종가는_4자리를_넘지_않는다(self, tmp_path: Path) -> None:
        """
        목적: 소수가 나오는 시장의 종가 자릿수 정책(4자리)을 고정한다

        4자리보다 깊은 자리는 실제 시세에 없는 부동소수점 잡음이다
        (`169.300003` 처럼 꼬리가 남는다). 사용자가 `signals.csv` 를 차트와 대조하는 것이
        이 프로젝트의 전제이므로, **표기가 차트와 어긋나면 원자료를 제공하는 의미가 준다.**

        Given: 소수 자릿수를 쓰는 데이터셋
        When: 신호일 목록의 종가를 봤을 때
        Then: 소수 4자리를 넘는 값이 없다
        """
        # Given
        dataset = _write_dataset(tmp_path, _clustered_frame(), price_decimals=PRICE_DECIMALS)

        # When
        outputs = _single_axis_run(dataset)

        # Then
        closes = outputs.signals[DISPLAY_CLOSE].to_numpy(dtype=float)
        assert closes.tolist() == np.round(closes, 4).tolist()


class TestInputValidation:
    """입력 검증 계약"""

    def test_데이터셋이_비면_예외를_던진다(self) -> None:
        """
        목적: 아무것도 재지 않은 결과를 정상으로 돌려주지 않는지 고정한다

        Given: 빈 데이터셋 목록
        When: 실행했을 때
        Then: ValueError 가 발생한다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="데이터셋"):
            run_study([])

    def test_축이_비면_예외를_던진다(self, tmp_path: Path) -> None:
        """
        목적: 조합이 하나도 없는 실행을 조용히 넘기지 않는지 고정한다

        Given: 시작연도 목록이 빈 축
        When: 실행했을 때
        Then: ValueError 가 발생한다
        """
        # Given
        dates = pd.DatetimeIndex(pd.bdate_range("2011-01-03", periods=300))
        dataset = _write_dataset(tmp_path, _market_frame(dates, _quiet_changes(len(dates) - 1)))

        # When / Then
        with pytest.raises(ValueError, match="집계 시작 연도"):
            run_study([dataset], start_years=())


class TestDatasetsInvariant:
    """검증 대상 시세 목록의 불변조건"""

    def test_수정주가_데이터셋은_남아있지_않다(self) -> None:
        """
        목적: 산출물에 `가격기준 = 수정주가` 가 다시 섞이지 않도록 고정한다

        이 프로젝트의 전제는 **사용자가 결과를 차트와 직접 대조한다**는 것이고,
        보통의 차트는 배당 미포함이다. 수정주가 데이터셋이 하나라도 남으면
        `signals.csv` 의 종가가 차트와 어긋나는 행이 다시 생기는데,
        **표는 정상으로 보이므로 눈으로 발견되지 않는다.**

        Given: 검증 대상 시세 목록
        When: 가격 기준을 모았을 때
        Then: 전부 원본가다
        """
        # Given / When
        price_bases = {dataset.price_basis for dataset in DATASETS}

        # Then
        assert price_bases == {DISPLAY_PRICE_BASIS_RAW}

    def test_수정주가_파일을_가리키는_데이터셋이_없다(self) -> None:
        """
        목적: 표시 이름만 원본가로 바꾸고 파일은 수정주가를 가리키는 사고를 막는다

        `price_basis` 는 표시용 문자열이라 파일과 어긋나도 예외가 나지 않는다.
        **라벨과 실제 소스가 갈라지면 결과 전체가 조용히 틀린다.**

        Given: 검증 대상 시세 목록
        When: 파일 경로를 모았을 때
        Then: 수정주가 파일명 규칙(`_adjusted_`)을 쓰는 경로가 없다
        """
        # Given / When
        names = [dataset.path.name for dataset in DATASETS]

        # Then
        assert [name for name in names if "adjusted" in name] == []

    def test_데이터셋은_QQQ_와_KODEX_200_두_종이다(self) -> None:
        """
        목적: 데이터셋이 조용히 늘거나 줄지 않는지 고정한다

        신호군 수는 데이터셋 수에 그대로 곱해진다. 하나가 빠지면 조합이 통째로 사라지는데
        실행은 정상으로 끝난다.

        Given: 검증 대상 시세 목록
        When: 실행 인자로 쓰는 이름을 모았을 때
        Then: QQQ 와 KODEX 200 두 종이다
        """
        # Given / When
        keys = {dataset.key for dataset in DATASETS}

        # Then
        assert keys == {"qqq", "kodex200"}

    def test_종가_자릿수는_소수_4자리와_원화_정수다(self) -> None:
        """
        목적: 데이터셋에 배정된 종가 자릿수를 값으로 고정한다

        저장은 4자리인데 출력만 다른 값으로 갈라지면 **없는 정밀도를 만들어 내거나
        저장해 둔 값을 버리는데, 표는 정상으로 보인다.** 원화에 소수 자리를 붙이면
        실제 호가에 없는 자리가 생겨 차트 대조가 나빠진다.

        Given: 검증 대상 시세 목록
        When: 종목별 자릿수를 봤을 때
        Then: QQQ 는 4자리, KODEX 200 은 정수다
        """
        # Given / When
        decimals = {dataset.key: dataset.price_decimals for dataset in DATASETS}

        # Then
        assert decimals == {"qqq": 4, "kodex200": 0}

    def test_데이터셋의_종목_이름은_서로_다르다(self) -> None:
        """
        목적: 산출물에서 데이터셋이 뒤섞이지 않는지 고정한다

        식별 컬럼에서 `가격기준` 이 빠진 뒤로 **산출물의 데이터셋 구분자는 `종목` 하나뿐**이다.
        표시 이름이 겹치는 데이터셋을 넣으면 서로 다른 시세의 행이 같은 신호군으로 읽히는데,
        **행 수도 컬럼도 정상이라 눈으로는 발견되지 않는다.**

        Given: 검증 대상 시세 목록
        When: 표시 이름을 모았을 때
        Then: 데이터셋 수만큼 서로 다른 이름이 있다
        """
        # Given / When
        tickers = [dataset.ticker for dataset in DATASETS]

        # Then
        assert len(set(tickers)) == len(DATASETS)


class TestReverseAllDirection:
    """방향 `역방향 전체` 신호군 계약

    폭등이든 폭락이든 **구분 없이 역방향으로 진입**하는 매매를 한 줄로 재기 위한 신호군이다.
    두 방향의 신호일을 한 표본으로 묶되, 상승 방향 신호의 수익률에 **−1 을 곱해**
    "역방향으로 들어갔을 때"의 부호로 통일한다. 그냥 합치면 폭등 뒤 하락(이 매매에서는 이익)이
    마이너스로 들어가 폭락 쪽 이익과 상쇄돼 평균이 해석 불가능해진다.

    이것은 **이벤트 정의가 아니라 집계 단계의 합성**이다. 어느 날이 신호인지는 바뀌지 않는다.
    """

    @pytest.fixture
    def clustered_outputs(self, tmp_path: Path) -> StudyOutputs:
        """폭락 3건·폭등 1건이 심긴 시세로 돈 실행 결과."""
        dataset = _write_dataset(tmp_path, _clustered_frame())

        return _single_axis_run(dataset, rank_cuts=(max(RANK_CUTS),))

    def _extreme_rows(self, table: pd.DataFrame, direction_label: str) -> pd.DataFrame:
        """테스트 A · 시대 구간 전체 · 해당 방향의 행만 고른다."""
        return table[
            (table[DISPLAY_TEST] == DISPLAY_TEST_EXTREME)
            & (table[DISPLAY_PERIOD] == PERIOD_ALL.label)
            & (table[DISPLAY_DIRECTION] == direction_label)
        ]

    def test_역방향_전체_레이블은_시대_구간_전체와_다르다(self) -> None:
        """
        목적: 두 축이 같은 문자열을 쓰지 않는지 값으로 고정한다

        같은 행의 `방향` 과 `시대 구간` 이 모두 `전체` 가 되면, 대조할 때 어느 축의 값인지
        구분되지 않는다. **표는 정상으로 보이므로 눈으로는 발견되지 않는다.**

        Given: 방향 레이블과 시대 구간 레이블
        When: 두 값을 비교했을 때
        Then: 서로 다르고, 방향 쪽은 `역방향 전체` 다
        """
        # Given / When / Then
        assert DISPLAY_DIRECTION_REVERSE_ALL == "역방향 전체"
        assert DISPLAY_DIRECTION_REVERSE_ALL != PERIOD_ALL.label

    def test_방향_축의_값은_세_가지다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 방향 축이 조용히 늘거나 줄지 않는지 값으로 고정한다

        Given: 테스트 A 로 돈 실행 결과
        When: 집계표의 방향 값을 모았을 때
        Then: 폭등·폭락·역방향 전체 세 가지다
        """
        # Given
        statistics = clustered_outputs.statistics
        extreme = statistics[statistics[DISPLAY_TEST] == DISPLAY_TEST_EXTREME]

        # When / Then
        assert set(extreme[DISPLAY_DIRECTION]) == {"폭등", "폭락", "역방향 전체"}

    def test_역방향_전체의_신호_수는_두_방향의_합이다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 표본이 조용히 새거나 중복되지 않는지 고정한다

        Given: 폭락 3건·폭등 1건이 심긴 실행 결과
        When: 역방향 전체 신호군의 신호 수를 봤을 때
        Then: 4건이다 (두 방향의 합)
        """
        # Given
        statistics = clustered_outputs.statistics
        surge = self._extreme_rows(statistics, "폭등")
        plunge = self._extreme_rows(statistics, "폭락")

        # When
        combined = self._extreme_rows(statistics, DISPLAY_DIRECTION_REVERSE_ALL)

        # Then
        assert set(surge[DISPLAY_SIGNAL_COUNT]) == {1}
        assert set(plunge[DISPLAY_SIGNAL_COUNT]) == {3}
        assert set(combined[DISPLAY_SIGNAL_COUNT]) == {4}

    def test_상승_방향_수익률은_부호가_뒤집혀_들어간다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 부호 정규화 산식을 신호일 원자료에서 손으로 검산해 고정한다

        이 계약이 깨지면 평균이 상쇄돼 값이 작아지는데, **표는 정상으로 보인다.**

        Given: 신호일 목록의 종가 1일 수익률
        When: 폭등 행에 −1 을 곱하고 폭락 행은 그대로 두어 평균을 냈을 때
        Then: 역방향 전체 신호군의 1일 평균과 같다
        """
        # Given
        signals = clustered_outputs.signals
        rows = signals[(signals[DISPLAY_TEST] == DISPLAY_TEST_EXTREME) & (signals[DISPLAY_PERIOD] == PERIOD_ALL.label)]
        surge = rows.loc[rows[DISPLAY_DIRECTION] == "폭등", CLOSE_ONE_DAY_COLUMN]
        plunge = rows.loc[rows[DISPLAY_DIRECTION] == "폭락", CLOSE_ONE_DAY_COLUMN]

        # When
        expected = pd.concat([-surge, plunge]).mean()
        combined = self._extreme_rows(clustered_outputs.statistics, DISPLAY_DIRECTION_REVERSE_ALL)
        actual = combined.loc[combined[DISPLAY_HORIZON] == ONE_DAY_LABEL, DISPLAY_MEAN].iloc[0]

        # Then
        assert actual == pytest.approx(expected, abs=RATE_TOLERANCE)

    def test_역방향_전체의_역방향_비율은_승률과_같다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 부호를 뒤집은 뒤에는 "수익률 > 0" 이 곧 "역방향 성공" 임을 고정한다

        두 값이 같은 것은 중복이 아니라 정의상의 일치다. **빈칸으로 두지 않는다** —
        빈칸은 "계산 불가"로 읽힌다.

        Given: 역방향 전체 신호군의 집계
        When: 역방향 비율과 승률을 비교했을 때
        Then: 모든 칸에서 같다
        """
        # Given / When
        combined = self._extreme_rows(clustered_outputs.statistics, DISPLAY_DIRECTION_REVERSE_ALL)

        # Then
        assert not combined.empty
        assert combined[DISPLAY_REVERSE_RATE].tolist() == combined[DISPLAY_WIN_RATE].tolist()

    def test_베이스라인_표본이_원본_모집단의_두_배다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 대칭 모집단(원본 + 부호 반전)을 쓴다는 사실을 고정한다

        신호군의 부호를 뒤집었으면 베이스라인도 같은 규칙으로 뒤집어야 비교가 성립한다.
        베이스라인은 방향이 없으므로 **"방향을 미리 모르고 동전 던지기로 정했다면"** 의
        모집단을 쓴다 — 같은 기간 전 거래일을 원본 한 벌과 부호 반전 한 벌로 만든다.

        Given: 같은 신호군의 방향별 초과분표와 역방향 전체 초과분표
        When: 베이스라인 표본 수를 비교했을 때
        Then: 역방향 전체 쪽이 정확히 두 배다
        """
        # Given
        excess = clustered_outputs.excess
        plunge = self._extreme_rows(excess, "폭락")
        combined = self._extreme_rows(excess, DISPLAY_DIRECTION_REVERSE_ALL)

        # When
        by_baseline = plunge.groupby([DISPLAY_BASELINE, DISPLAY_HORIZON])[DISPLAY_BASELINE_SAMPLE].first()
        combined_by_baseline = combined.groupby([DISPLAY_BASELINE, DISPLAY_HORIZON])[DISPLAY_BASELINE_SAMPLE].first()

        # Then
        assert not combined.empty
        assert (combined_by_baseline == by_baseline * 2).all()

    def test_테스트_A_의_사건_수는_두_방향_합집합의_사건_수다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 결정 ⑭ 이 테스트 A 에 매긴 합집합 사건 번호를 그대로 잇는지 고정한다

        Given: 한 사건에 폭락 2건·폭등 1건이 몰려 있고 뒤에 별개 폭락이 하나 더 있는 시세
        When: 역방향 전체 신호군의 사건 수를 봤을 때
        Then: 2개다 (방향별 사건 수 2 + 1 을 더한 3이 아니다)
        """
        # Given / When
        combined = self._extreme_rows(clustered_outputs.statistics, DISPLAY_DIRECTION_REVERSE_ALL)

        # Then
        assert set(combined[DISPLAY_EVENT_COUNT]) == {2}

    def test_테스트_B_의_사건_수는_방향별_사건_수의_합이다(self, tmp_path: Path) -> None:
        """
        목적: 테스트 B 에서 두 방향을 한 사건으로 묶지 않는지 고정한다

        결정 ⑭ 가 테스트 B 를 방향별로 나눈 이유가 그대로 남는다 — 합집합에 새로 번호를
        매기면 신호가 촘촘해 30일 체인이 끊기지 않고 **사건 하나가 수년에 걸친다.**

        Given: 연속 상승 2건(사건 2개)과 연속 하락 1건(사건 1개)이 있는 시세
        When: 역방향 전체 신호군의 사건 수를 봤을 때
        Then: 3개다 (2 + 1). 합집합으로 매겼다면 1개가 나온다
        """
        # Given
        dates = pd.DatetimeIndex(pd.date_range("2011-01-03", periods=300, freq="D"))
        dataset = _write_dataset(tmp_path, _market_frame(dates, _alternating_changes(len(dates) - 1)))

        # When
        statistics = _single_axis_run(dataset).statistics
        combined = statistics[
            (statistics[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE)
            & (statistics[DISPLAY_PERIOD] == PERIOD_ALL.label)
            & (statistics[DISPLAY_DIRECTION] == DISPLAY_DIRECTION_REVERSE_ALL)
        ]

        # Then
        assert set(combined[DISPLAY_SIGNAL_COUNT]) == {3}
        assert set(combined[DISPLAY_EVENT_COUNT]) == {3}

    def test_신호일_목록에는_역방향_전체_행이_없다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 원자료에 같은 날이 두 줄로 실리지 않는지 고정한다

        `signals.csv` 는 사용자가 차트와 직접 대조하는 파일이고, 중복 행은 그 대조를 방해한다.
        **정보 손실은 없다** — 방향별 두 블록을 합치면 그대로 복원되고, 부호 정규화는
        상승 방향 행의 부호만 뒤집으면 된다.

        Given: 실행 결과의 신호일 목록
        When: 방향 값을 모았을 때
        Then: 역방향 전체가 없다
        """
        # Given / When / Then
        assert DISPLAY_DIRECTION_REVERSE_ALL not in set(clustered_outputs.signals[DISPLAY_DIRECTION])

    def test_초과분표와_검정표에도_역방향_전체가_있다(self, clustered_outputs: StudyOutputs) -> None:
        """
        목적: 절대 성적만 내고 끝나지 않는지 고정한다

        `statistics` 만으로는 "평소보다 나은가"를 판단할 수 없다. 이 매매에서 폭락 뒤 상승은
        평소에도 절반 넘게 일어나므로, 베이스라인 비교 없이는 신호를 기다린 값어치를 알 수 없다.

        Given: 실행 결과의 초과분표와 검정표
        When: 방향 값을 확인했을 때
        Then: 두 표 모두에 역방향 전체가 있다
        """
        # Given / When / Then
        for table in (clustered_outputs.excess, clustered_outputs.test):
            assert DISPLAY_DIRECTION_REVERSE_ALL in set(table[DISPLAY_DIRECTION])

    def test_한_방향만_0건이면_역방향_전체는_남는다(self, tmp_path: Path) -> None:
        """
        목적: 신호 0건 판정의 경계를 고정한다 (엣지 케이스)

        Given: 연속 하락이 한 번도 없어 그 방향이 0건인 시세
        When: 신호 0건으로 기록된 신호군을 봤을 때
        Then: 연속 하락만 빠지고 역방향 전체는 집계에 남는다
        """
        # Given
        dates = pd.DatetimeIndex(pd.date_range("2011-01-03", periods=300, freq="D"))
        changes = _alternating_changes(len(dates) - 1)
        changes[118:122] = 0.004  # 심어 둔 연속 하락을 상승으로 덮어 그 방향을 0건으로 만든다

        # When
        dataset = _write_dataset(tmp_path, _market_frame(dates, changes))
        outputs = _single_axis_run(dataset)
        empty_directions = {record[KEY_DIRECTION] for record in outputs.summary[KEY_EMPTY_SIGNAL_GROUPS]}
        statistics = outputs.statistics
        combined = statistics[
            (statistics[DISPLAY_TEST] == DISPLAY_TEST_CONSECUTIVE)
            & (statistics[DISPLAY_PERIOD] == PERIOD_ALL.label)
            & (statistics[DISPLAY_DIRECTION] == DISPLAY_DIRECTION_REVERSE_ALL)
        ]

        # Then
        assert "연속 하락" in empty_directions
        assert DISPLAY_DIRECTION_REVERSE_ALL not in empty_directions
        assert not combined.empty

    def test_뒤를_잘라내도_역방향_전체는_방향별_신호의_합이다(self, tmp_path: Path) -> None:
        """
        목적: 합성이 새로운 판정을 만들어내지 않는지 고정한다

        역방향 전체는 **이벤트 정의가 아니라 집계 합성**이므로, 어느 날이 신호인지는
        기존 경로가 그대로 정한다. 입력의 뒤를 잘라 신호 수가 달라져도 "두 방향의 합"
        관계는 그대로여야 한다 — 깨진다면 합성 과정에서 판정이 새로 일어난 것이다.

        Given: 사건이 심긴 시세와, 뒤쪽 사건을 잘라낸 같은 시세
        When: 각각에서 테스트 A 의 방향별·역방향 전체 신호 수를 봤을 때
        Then: 두 입력 모두에서 역방향 전체 = 폭등 + 폭락이다
        """
        # Given
        frame = _clustered_frame()

        # When / Then
        for index, cut in enumerate((len(frame) - 300, len(frame))):
            dataset = _write_dataset(tmp_path / f"cut_{index}", frame.iloc[:cut], key="cut")
            statistics = _single_axis_run(dataset, rank_cuts=(max(RANK_CUTS),)).statistics
            counts = {
                label: set(self._extreme_rows(statistics, label)[DISPLAY_SIGNAL_COUNT])
                for label in ("폭등", "폭락", DISPLAY_DIRECTION_REVERSE_ALL)
            }

            surge = counts["폭등"].pop() if counts["폭등"] else 0
            plunge = counts["폭락"].pop() if counts["폭락"] else 0
            assert counts[DISPLAY_DIRECTION_REVERSE_ALL] == {surge + plunge}
