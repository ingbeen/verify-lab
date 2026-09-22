"""만기_말일 측정 조립 계약

**조립만 검사한다.** 통계량은 `measure/statistics`, 달력은 `measure/calendar_*` 가 소유하고
그쪽 테스트가 이미 본다. 여기서는 **축이 맞는가 · 칸이 조용히 사라지지 않는가 ·
표본이 보존되는가**를 본다.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from verify_lab.common_constants import (
    ADJUSTED_FILE_TEMPLATE,
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
from verify_lab.report.constants import MEASURE_FILENAME
from verify_lab.studies.expiry_monthend.constants import (
    COMBOS,
    DATASETS,
    MARKET_KOSDAQ,
    MONTHS,
    OUTPUT_FILES,
    TRADING_CELLS,
    Dataset,
)
from verify_lab.studies.expiry_monthend.runner import display_tables, run_study

# 합성 시세 구간. 두 해를 덮어 9월·12월이 각각 두 번 들어온다
SYNTHETIC_START = "2022-01-03"
SYNTHETIC_END = "2023-12-29"

# 무작위 뽑기 대조를 가볍게 돈다 — 이 파일이 보는 것은 조립이지 검정값이 아니다
FAST_REPEATS = 20


def _market_frame(days: pd.DatetimeIndex) -> pd.DataFrame:
    """장중 등락이 있는 합성 ETF 시세를 만든다.

    Args:
        days: 거래일 목록

    Returns:
        시세 스키마 DataFrame
    """
    closes = 10_000.0 + np.arange(len(days), dtype=float) * 3.0

    return pd.DataFrame(
        {
            COL_DATE: days.strftime("%Y-%m-%d"),
            COL_OPEN: np.round(closes),
            COL_HIGH: np.round(closes * 1.01),
            COL_LOW: np.round(closes * 0.99),
            COL_CLOSE: np.round(closes),
            COL_VOLUME: 1_000_000,
        }
    )


def _write_market(directory: Path, ticker: str, days: pd.DatetimeIndex) -> None:
    """합성 시세와 **수정주가**를 파일로 쓴다.

    **수정주가를 함께 쓴다** — 배당락을 재려면 그 파일이 있어야 하고, 없으면 `ValueError` 다.
    분배가 없는 종목을 흉내 내려고 원본가와 **같은 값**을 쓴다 (왜곡 0).

    Args:
        directory: 저장 폴더
        ticker: 종목코드
        days: 거래일 목록
    """
    frame = _market_frame(days)
    frame.to_csv(directory / MARKET_FILE_TEMPLATE.format(ticker=ticker), index=False)
    frame.to_csv(directory / ADJUSTED_FILE_TEMPLATE.format(ticker=ticker), index=False)


def _write_index(directory: Path, ticker: str, days: pd.DatetimeIndex) -> None:
    """합성 지수 계열을 파일로 쓴다.

    Args:
        directory: 저장 폴더
        ticker: 지수 코드
        days: 거래일 목록
    """
    values = 300.0 + np.arange(len(days), dtype=float) * 0.1
    frame = pd.DataFrame({COL_DATE: days.strftime("%Y-%m-%d"), COL_VALUE: np.round(values, 2)})
    frame.to_csv(directory / INDEX_FILE_TEMPLATE.format(ticker=ticker), index=False)


def _etf(directory: Path, days: pd.DatetimeIndex, ticker: str = "SYN") -> Dataset:
    """합성 ETF 대상을 만든다.

    Args:
        directory: 저장 폴더
        days: 거래일 목록
        ticker: 종목코드

    Returns:
        검증 대상 정의
    """
    _write_market(directory, ticker, days)

    return Dataset(
        ticker=ticker,
        label=f"합성 ETF {ticker}",
        market=MARKET_KOSDAQ,
        directory=directory,
        file_template=MARKET_FILE_TEMPLATE,
        price_column=COL_CLOSE,
        price_decimals=PRICE_DECIMALS_KRW,
        is_index=False,
    )


def _index(directory: Path, days: pd.DatetimeIndex, ticker: str = "SYNIDX") -> Dataset:
    """합성 지수 대상을 만든다.

    Args:
        directory: 저장 폴더
        days: 거래일 목록
        ticker: 지수 코드

    Returns:
        검증 대상 정의
    """
    _write_index(directory, ticker, days)

    return Dataset(
        ticker=ticker,
        label=f"합성 지수 {ticker}",
        market=MARKET_KOSDAQ,
        directory=directory,
        file_template=INDEX_FILE_TEMPLATE,
        price_column=COL_VALUE,
        price_decimals=PRICE_DECIMALS,
        is_index=True,
    )


def _days(start: str = SYNTHETIC_START, end: str = SYNTHETIC_END) -> pd.DatetimeIndex:
    """합성 거래일 목록을 만든다.

    Args:
        start: 시작일
        end: 종료일

    Returns:
        거래일 인덱스
    """
    return pd.DatetimeIndex(pd.bdate_range(start, end))


class TestDatasetInvariants:
    """대상 정의의 불변조건 — 산출물의 구분자가 겹치면 행이 조용히 섞인다"""

    def test_종목명이_겹치지_않는다(self) -> None:
        """
        목적: **종목명이 산출물의 데이터셋 구분자**이므로 겹치면 서로 다른 대상의 행이
            한 값 아래로 합쳐진다 (`src/verify_lab/CLAUDE.md` 출력 계약).

        Given: 선언된 대상 전부
        When: 표시 이름을 모은다
        Then: 중복이 없다
        """
        # When
        labels = [dataset.label for dataset in DATASETS]

        # Then
        assert len(labels) == len(set(labels)), f"종목명이 겹칩니다: {labels}"

    def test_종목코드가_겹치지_않는다(self) -> None:
        """
        목적: 코드가 겹치면 같은 파일을 두 번 읽고 요약의 데이터셋 줄이 어긋난다.

        Given: 선언된 대상 전부
        When: 종목코드를 모은다
        Then: 중복이 없다
        """
        # When
        tickers = [dataset.ticker for dataset in DATASETS]

        # Then
        assert len(tickers) == len(set(tickers)), f"종목코드가 겹칩니다: {tickers}"

    def test_지수는_판정하지_않는다(self) -> None:
        """
        목적: 살 수 없는 것으로 「우위가 있다」를 주장하지 않는다 (측정의 원칙 9).

        Given: 선언된 대상 전부
        When: 판정 대상 여부를 본다
        Then: 지수는 전부 거짓이고 ETF 는 전부 참이다
        """
        # When / Then
        for dataset in DATASETS:
            assert dataset.is_judged is not dataset.is_index, f"{dataset.label} 의 판정 여부가 지수 여부와 어긋납니다"


class TestTradingCells:
    """확정 칸 — 기본 실행이 내는 범위를 고정한다

    **근거는 코드가 아니라 `docs/매매/만기_말일/규칙.md` §3 이 갖는다.** 여기서 고정하는 것은
    「그 결론이 코드에 이렇게 옮겨졌다」이며, 목록만 보고 근거를 짐작하면 사후 선택과
    구별되지 않는다 (`.claude/rules/trading.md`).
    """

    def test_확정_칸이_넷이다(self) -> None:
        """
        목적: 칸이 늘거나 줄면 산출물의 범위가 조용히 달라진다 —
            좁혀 돌린 실행이 전체 실행을 덮는데 **예외가 나지 않는다.**

        Given: 확정 칸 목록
        When: 개수를 본다
        Then: 넷이다 (SPY · DIA · KODEX 코스닥150 · 코스닥150 지수)
        """
        # Given / When / Then
        assert len(TRADING_CELLS) == 4

    def test_모든_칸이_같은_조합과_달과_방향이다(self) -> None:
        """
        목적: 확정 규칙이 **하나**라는 것을 고정한다 — 9월 · C2(만기→말일) · 아래.
            칸마다 조합이 갈리면 그것은 확정이 아니라 격자다.

        Given: 확정 칸 목록
        When: 조합·달·방향을 모은다
        Then: 각각 한 값뿐이다
        """
        # Given / When
        combos = {cell.combo_key for cell in TRADING_CELLS}
        months = {cell.month for cell in TRADING_CELLS}
        directions = {cell.bet_down for cell in TRADING_CELLS}

        # Then
        assert combos == {"c2"}, f"조합이 하나가 아닙니다: {sorted(combos)}"
        assert months == {9}, f"달이 하나가 아닙니다: {sorted(months)}"
        assert directions == {True}, "방향이 「아래」 하나가 아닙니다"

    def test_확정_칸의_대상이_선언된_대상_안에_있다(self) -> None:
        """
        목적: 칸이 `DATASETS` 밖의 코드를 가리키면 **측정이 다 끝난 뒤에야** 드러난다.

        Given: 확정 칸과 선언된 대상
        When: 종목코드를 견준다
        Then: 칸의 코드가 전부 선언돼 있고 순서도 그대로다
        """
        # Given
        known = [dataset.ticker for dataset in DATASETS]

        # When
        picked = [cell.ticker for cell in TRADING_CELLS]

        # Then
        assert picked == ["SPY", "DIA", "229200", "2203"]
        unknown = [ticker for ticker in picked if ticker not in known]
        assert not unknown, f"선언되지 않은 종목입니다: {unknown}"

    def test_격자_상수를_지우지_않는다(self) -> None:
        """
        목적: **재수집하면 칸 목록을 다시 판단해야 한다** (`.claude/rules/trading.md`).
            격자 상수를 지우면 그 판단의 수단이 사라진다.

        Given: 선언된 축
        When: 대상·조합·달의 개수를 본다
        Then: 좁히기 전의 격자가 그대로 남아 있다
        """
        # Given / When / Then
        assert len(DATASETS) == 6, "대상 격자가 줄었습니다 — 재판단 수단이 사라집니다"
        assert len(COMBOS) == 4, "조합 격자가 줄었습니다"
        assert MONTHS == (9, 12), "달 격자가 줄었습니다"


class TestOutputContract:
    """산출물 파일 이름 — 좁힌 매매법은 `측정.csv` 다"""

    def test_측정_표의_이름이_측정_csv다(self) -> None:
        """
        목적: `src/verify_lab/CLAUDE.md` 「매매 산출물 계약」이 **`통계.csv` 는 축 전체,
            `측정.csv` 는 확정 칸만**으로 두 이름을 갈랐다. 좁혔는데 옛 이름으로 내면
            **담는 축이 다른 두 표가 같은 이름으로 불린다.**

        Given: 산출물 사전
        When: 값을 본다
        Then: `측정.csv` 하나다
        """
        # Given / When
        names = sorted(OUTPUT_FILES.values())

        # Then
        assert names == [MEASURE_FILENAME]


class TestStudyAxis:
    """측정 표의 축 — (종목 × 조합 × 달) 셋이고 방향이 «표시»로 붙는다"""

    def test_칸마다_한_행이다(self, tmp_path: Path) -> None:
        """
        목적: 행 수 산식을 고정한다.

        Given: 합성 ETF 하나
        When: 네 조합 × 두 달로 돌린다
        Then: 8행이다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When
        outputs = run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS)

        # Then
        assert len(outputs.statistics) == len(COMBOS) * len(MONTHS)

    def test_방향이_식별_컬럼으로_붙는다(self, tmp_path: Path) -> None:
        """
        목적: `측정.csv` 계약이 `종목 · <매매법 축> · 방향` 을 앞에 요구한다 —
            성적표의 `시기 = 전체` 행과 **1:1** 로 읽히게 하기 위해서다.
            방향이 없으면 평균 −2.96% 가 이 매매에서 **+2.96%** 라는 것이 표에 없다.

        [중요] **값은 1배 롱 기준 그대로이고 방향은 표시일 뿐이다** — 부호를 뒤집으면
        `기준선 오른 비율` 이 실제로는 내린 비율을 가리켜 이름이 거짓이 된다.

        Given: 합성 ETF 하나
        When: 표시용 표의 컬럼을 본다
        Then: 앞 넷이 종목·조합·월·방향이다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When
        table = display_tables(run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS))["statistics"]

        # Then
        assert list(table.columns[:4]) == ["종목", "조합", "월", "방향"]
        assert set(table["방향"]) == {"아래"}, "확정 방향이 「아래」 하나가 아닙니다"

    def test_조합_붕괴_두_컬럼이_신호_수로_나뉜다(self, tmp_path: Path) -> None:
        """
        목적: 「다른 조합과 같은 해 + 이 조합만 다른 해 = 신호」를 고정한다 —
            이 검증의 고유 지표이고, 어긋나면 조합 비교의 표본을 잘못 읽는다.

        Given: 합성 ETF 하나
        When: 두 컬럼과 신호 수를 견준다
        Then: 행마다 합이 신호 수와 같다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When
        table = run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS).statistics

        # Then
        total = table["shared_years"].astype("int64") + table["unique_years"].astype("int64")
        assert list(total) == list(table["SignalCount"].astype("int64"))

    def test_조합이_하나면_붕괴_두_컬럼을_비운다(self, tmp_path: Path) -> None:
        """
        목적: **견줄 다른 조합이 없으면 그 값을 잴 수 없다.** 채우면 「이 조합만 다른 해」가
            신호 수와 같아지는데, 그것은 독립 관측이 그만큼 있다는 뜻이 아니라
            **비교 대상이 없다**는 뜻이다 — 실측으로 SPY 9월은 넷을 다 돌리면 15해다.

        이 저장소에서 빈칸은 「잴 수 없었다」이고 0 은 「재서 0」이다.

        Given: 합성 ETF 하나
        When: 조합 하나만 돌린다
        Then: 붕괴 두 컬럼이 전부 비어 있다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When
        table = run_study((dataset,), combos=COMBOS[:1], months=MONTHS, repeats=FAST_REPEATS).statistics

        # Then
        assert table["shared_years"].isna().all(), "다른 조합과 같은 해가 비어 있지 않습니다"
        assert table["unique_years"].isna().all(), "이 조합만 다른 해가 비어 있지 않습니다"


class TestMissingCell:
    """재는 달의 신호가 없으면 **조용히 빠지지 않는다**"""

    def test_재는_달이_없으면_예외다(self, tmp_path: Path) -> None:
        """
        목적: 칸이 사라지는 것을 끊는다.

        **달 축 전체가 비었는지만 보면 이 사고가 통과한다** — 신호가 있는 달이 하나라도
        있으면 집계가 비지 않으므로, 그 사이 12월 칸이 사라져도 `통계.csv` 가 4행으로
        나오고 **성적표는 8칸을 그대로 내** 두 표의 조인이 조용히 깨진다.

        Given: 10월에서 끊긴 합성 시세
        When: 9월·12월로 돌린다
        Then: `RuntimeError` 이고 빠진 달이 메시지에 있다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days("2022-01-03", "2022-10-31")
        dataset = _etf(tmp_path, days)

        # When / Then
        with pytest.raises(RuntimeError, match="빠진 달"):
            run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS)


class TestSummary:
    """실행 요약이 무엇을 돌았는지 남긴다"""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [("track", "expiry_monthend"), ("permutation_repeats", FAST_REPEATS)],
    )
    def test_요약이_실행_조건을_담는다(self, tmp_path: Path, field: str, expected: object) -> None:
        """
        목적: 좁혀 돌린 실행이 전체 실행 폴더를 덮으므로 **요약이 유일한 기록**이다.

        Given: 합성 ETF 하나
        When: 요약을 본다
        Then: 그 값이 실제로 돈 조건이다

        Args:
            tmp_path: 격리된 임시 폴더
            field: 볼 키
            expected: 기대값
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When
        summary = run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS).summary

        # Then
        assert summary[field] == expected

    def test_대상마다_진입과_제외를_남긴다(self, tmp_path: Path) -> None:
        """
        목적: 표본 보존 — 성적표에서 `제외` 컬럼을 없앤 뒤로 요약이 그 유일한 자리다.

        Given: 합성 ETF 와 합성 지수
        When: 요약의 데이터셋 줄을 본다
        Then: 대상마다 진입·제외가 있고 진입이 0 이 아니다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        datasets = (_etf(tmp_path, days), _index(tmp_path, days))

        # When
        records = run_study(datasets, combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS).summary["datasets"]

        # Then
        assert len(records) == len(datasets)
        for record in records:
            assert record["entry_count"] > 0
            assert record["excluded_count"] >= 0

    def test_지수는_배당락을_비운다(self, tmp_path: Path) -> None:
        """
        목적: 「안 걸림」과 「잴 수 없음」을 가른다 — 0 으로 채우면 없는 안전을 보고한다.

        지수는 상품이 아니라 계산값이라 분배금을 지급할 일이 없고 수정주가 파일도 없다.

        Given: 합성 지수 하나
        When: 배당락 세 컬럼을 본다
        Then: 전부 비어 있다

        Args:
            tmp_path: 격리된 임시 폴더
        """
        # Given
        days = _days()
        dataset = _index(tmp_path, days)

        # When
        table = run_study((dataset,), combos=COMBOS, months=MONTHS, repeats=FAST_REPEATS).statistics

        # Then
        for column in ("dividend_measured", "dividend_hit", "dividend_mean_impact"):
            assert table[column].isna().all(), f"{column} 이 비어 있지 않습니다"


class TestInputValidation:
    """빈 목록은 조용히 전부로 넓히지 않는다"""

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"combos": ()}, "조합이 하나도 없습니다"),
            ({"months": ()}, "재는 달이 하나도 없습니다"),
        ],
    )
    def test_빈_목록을_거부한다(self, tmp_path: Path, kwargs: dict[str, Sequence[object]], message: str) -> None:
        """
        목적: 「전부」와 「고른 결과가 없다」는 다른 사실이다.

        Given: 합성 ETF 하나
        When: 빈 목록으로 돌린다
        Then: `ValueError`

        Args:
            tmp_path: 격리된 임시 폴더
            kwargs: 비울 인자
            message: 기대 메시지
        """
        # Given
        days = _days()
        dataset = _etf(tmp_path, days)

        # When / Then
        with pytest.raises(ValueError, match=message):
            run_study((dataset,), repeats=FAST_REPEATS, **kwargs)  # type: ignore[arg-type]

    def test_대상이_없으면_거부한다(self) -> None:
        """
        목적: 같은 이유로 대상도 막는다.

        Given: 빈 대상 목록
        When: 돌린다
        Then: `ValueError`
        """
        # When / Then
        with pytest.raises(ValueError, match="검증 대상이 하나도 없습니다"):
            run_study(())
