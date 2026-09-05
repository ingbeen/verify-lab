"""ETN 수집기 계약

pykrx 가 감싸지 않은 KRX 통계를 직접 부르는 계층이라, **반환 형태가 바뀌면 조용히 틀리는**
자리가 많다. KRX 가 최신순으로 준다는 것과 숫자가 쉼표 붙은 문자열로 온다는 것,
값이 없는 칸이 `-` 로 온다는 것을 계약으로 고정한다.

외부 호출은 전부 스텁으로 대체한다 (`tests/CLAUDE.md` 외부 의존성 금지).
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VALUE, COL_VOLUME
from verify_lab.data import etn_collector
from verify_lab.data.etn_collector import collect_etn_history, collect_etn_indicative_value

TEST_TICKER = "530107"
TEST_ISIN = "KRG530001079"


def _krx_response(dates: list[str], closes: list[int]) -> pd.DataFrame:
    """KRX 반환 형태를 흉내낸 DataFrame 을 만든다.

    **최신 날짜가 먼저 오고 숫자에 쉼표가 붙는다** — 실제 응답의 성질이다.

    Args:
        dates: 거래일 목록 (YYYY/MM/DD), 최신순
        closes: 종가 목록

    Returns:
        KRX 응답 형태의 DataFrame
    """
    return pd.DataFrame(
        {
            "TRD_DD": dates,
            "TDD_OPNPRC": [f"{value:,}" for value in closes],
            "TDD_HGPRC": [f"{value:,}" for value in closes],
            "TDD_LWPRC": [f"{value:,}" for value in closes],
            "TDD_CLSPRC": [f"{value:,}" for value in closes],
            "ACC_TRDVOL": [f"{value * 10:,}" for value in closes],
            "PER1SECU_INDIC_VAL": [f"{value + 0.5:,.2f}" for value in closes],
        }
    )


@pytest.fixture
def stub_krx(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISIN 조회와 시세 조회를 스텁으로 바꾼다.

    Args:
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구
    """
    response = _krx_response(
        ["2026/09/02", "2026/09/01", "2026/08/31"],
        [6_910, 6_555, 6_465],
    )

    monkeypatch.setattr(etn_collector, "_resolve_isin", lambda ticker: TEST_ISIN)
    monkeypatch.setattr(etn_collector, "_fetch_daily_price", lambda isin, start, end: response)
    # 최근 구간 제외가 테스트 실행일에 따라 달라지지 않도록 제외 폭을 0 으로 둔다
    monkeypatch.setattr(etn_collector, "DOMESTIC_RECENT_EXCLUSION_DAYS", -3_650)


class TestCollectEtnHistory:
    """시세 수집"""

    def test_최신순_응답을_오름차순으로_저장한다(self, tmp_path: Path, stub_krx: None) -> None:
        """
        목적: KRX 가 최신순으로 준다는 사실을 계약으로 고정한다

        Given: 최신 날짜가 먼저 오는 KRX 응답
        When: 시세를 수집한다
        Then: 저장된 파일이 날짜 오름차순이다
        """
        # When
        result = collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

        # Then
        saved = pd.read_csv(result.path)
        assert saved[COL_DATE].tolist() == ["2026-08-31", "2026-09-01", "2026-09-02"]

    def test_쉼표가_붙은_숫자를_값으로_바꾼다(self, tmp_path: Path, stub_krx: None) -> None:
        """
        목적: 문자열 숫자 변환을 고정한다

        Given: 종가가 `6,910` 처럼 오는 응답
        When: 시세를 수집한다
        Then: 정수 6910 으로 저장된다
        """
        # When
        result = collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

        # Then
        saved = pd.read_csv(result.path)
        assert saved[COL_CLOSE].tolist() == [6_465, 6_555, 6_910]

    def test_공통_스키마로_저장한다(self, tmp_path: Path, stub_krx: None) -> None:
        """
        목적: 로더가 읽을 수 있는 스키마인지 고정한다

        Given: KRX 응답
        When: 시세를 수집한다
        Then: 시세 필수 컬럼이 그 순서로 저장된다
        """
        # When
        result = collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

        # Then
        saved = pd.read_csv(result.path)
        assert list(saved.columns) == [COL_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]

    def test_ISIN_을_결과에_남긴다(self, tmp_path: Path, stub_krx: None) -> None:
        """
        목적: 어느 종목을 조회했는지 되짚을 수 있게 하는지 고정한다

        Given: KRX 응답
        When: 시세를 수집한다
        Then: 결과에 조회에 쓴 ISIN 이 담긴다
        """
        # When
        result = collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

        # Then
        assert result.isin == TEST_ISIN

    def test_필수_컬럼이_없으면_예외(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: KRX 응답 형태가 바뀌면 조용히 통과하지 않는지 고정한다

        Given: 종가 컬럼이 빠진 응답
        When: 시세를 수집한다
        Then: ValueError 가 난다
        """
        # Given
        broken = _krx_response(["2026/09/02"], [6_910]).drop(columns=["TDD_CLSPRC"])
        monkeypatch.setattr(etn_collector, "_resolve_isin", lambda ticker: TEST_ISIN)
        monkeypatch.setattr(etn_collector, "_fetch_daily_price", lambda isin, start, end: broken)

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼"):
            collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

    def test_빈_응답이면_예외(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 빈 파일이 남지 않는지 고정한다

        Given: 빈 응답
        When: 시세를 수집한다
        Then: ValueError 가 나고 파일이 만들어지지 않는다
        """
        # Given
        monkeypatch.setattr(etn_collector, "_resolve_isin", lambda ticker: TEST_ISIN)
        monkeypatch.setattr(etn_collector, "_fetch_daily_price", lambda isin, start, end: pd.DataFrame())

        # When / Then
        with pytest.raises(ValueError, match="비어 있습니다"):
            collect_etn_history(TEST_TICKER, "20220101", output_dir=tmp_path)

        assert not list(tmp_path.glob("*.csv"))

    def test_종목_코드가_비면_예외(self, tmp_path: Path) -> None:
        """
        목적: 입력 검증을 고정한다

        Given: 공백뿐인 종목 코드
        When: 시세를 수집한다
        Then: ValueError 가 난다
        """
        # When / Then
        with pytest.raises(ValueError, match="종목 코드가 비어 있습니다"):
            collect_etn_history("   ", "20220101", output_dir=tmp_path)

    def test_시작일_형식이_틀리면_예외(self, tmp_path: Path) -> None:
        """
        목적: 조회 시작일 형식을 고정한다

        Given: YYYY-MM-DD 형식의 시작일
        When: 시세를 수집한다
        Then: ValueError 가 난다
        """
        # When / Then
        with pytest.raises(ValueError, match="YYYYMMDD"):
            collect_etn_history(TEST_TICKER, "2022-01-01", output_dir=tmp_path)


class TestCollectIndicativeValue:
    """지표가치 수집 — ETF 의 NAV 에 해당한다"""

    def test_단일_값_시계열로_저장한다(self, tmp_path: Path, stub_krx: None) -> None:
        """
        목적: 지표가치가 시세가 아니라 단일 값 스키마로 저장되는지 고정한다

        Given: KRX 응답
        When: 지표가치를 수집한다
        Then: 날짜와 값 두 컬럼만 오름차순으로 저장된다
        """
        # When
        result = collect_etn_indicative_value(TEST_TICKER, "20220101", output_dir=tmp_path)

        # Then
        saved = pd.read_csv(result.path)
        assert list(saved.columns) == [COL_DATE, COL_VALUE]
        assert saved[COL_VALUE].tolist() == [6_465.5, 6_555.5, 6_910.5]

    def test_지표가치_컬럼이_없으면_예외(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 응답 형태 변화를 조용히 넘기지 않는지 고정한다

        Given: 지표가치 컬럼이 빠진 응답
        When: 지표가치를 수집한다
        Then: ValueError 가 난다
        """
        # Given
        broken = _krx_response(["2026/09/02"], [6_910]).drop(columns=["PER1SECU_INDIC_VAL"])
        monkeypatch.setattr(etn_collector, "_resolve_isin", lambda ticker: TEST_ISIN)
        monkeypatch.setattr(etn_collector, "_fetch_daily_price", lambda isin, start, end: broken)

        # When / Then
        with pytest.raises(ValueError, match="지표가치 컬럼이 없습니다"):
            collect_etn_indicative_value(TEST_TICKER, "20220101", output_dir=tmp_path)


class TestToNumeric:
    """숫자 변환 — 값이 없는 칸을 0 으로 채우지 않는다"""

    def test_값이_없는_칸은_결측으로_남는다(self) -> None:
        """
        목적: `-` 를 0 으로 채우지 않는 정책을 고정한다.
        0 으로 채우면 가격이 0 인 날이 생겨 이상치 검사를 통과해 버린다

        Given: `-` 가 섞인 값
        When: 숫자로 바꾼다
        Then: 그 칸이 결측이다
        """
        # Given
        values = pd.Series(["1,234", "-", "5,678"])

        # When
        converted = etn_collector._to_numeric(values)

        # Then
        assert converted.tolist()[0] == 1234.0
        assert pd.isna(converted.tolist()[1])
        assert converted.tolist()[2] == 5678.0
