"""KRX 선물 수집기 계약

pykrx 가 감싸지 않은 KRX 통계를 직접 부르는 계층이라 **반환 형태가 바뀌면 조용히 틀리는**
자리가 많다. 이 검증에서 조용히 틀리는 길은 넷이며 전부 「표본이 사라지거나 섞이는」 형태다.

1. 하루에 여러 계약이 오는데 하나만 남는다
2. 야간 세션이 남아 하루에 두 번 수익률이 계산된다
3. 스프레드 종목이 섞여 정산가 0 으로 롤 계수가 나뉜다
4. 거래가 없던 날의 `-` 가 0 으로 채워져 「가격 0」이 된다

외부 호출은 전부 스텁으로 대체한다 (`tests/CLAUDE.md` 외부 의존성 금지).
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_CONTRACT,
    COL_CONTRACT_NAME,
    COL_DATE,
    COL_OPEN_INTEREST,
    COL_SETTLE,
    COL_SPOT,
    COL_VOLUME,
    FUTURES_REQUIRED_COLUMNS,
)
from verify_lab.data import krx_futures_collector
from verify_lab.data.krx_futures_collector import (
    PRODUCT_KOSPI200,
    collect_contract_catalog,
    collect_futures_history,
)

NEAR_CONTRACT = "KR4101Q90009"
FAR_CONTRACT = "KR4101QC0001"
NEAR_NAME = "코스피200 F 202009"
FAR_NAME = "코스피200 F 202012"
SPREAD_CONTRACT = "KR4401S9SCS8"

# 2001~2005년 표기의 스프레드. **이 종목이 실제로 필터를 빠져나가 수집을 실패시켰다** —
# 그때 필터가 ` SP ` 만 봤고 그 시절 표기는 「스프레드」였다
OLD_SPREAD_CONTRACT = "KR4401191CS0"

REFERENCE_DAY = date(2020, 9, 4)


def _snapshot(trade_date: str) -> pd.DataFrame:
    """전종목 시세 응답을 흉내낸다.

    **주간·야간·스프레드가 한 응답에 섞여 온다** — 실제 응답의 성질이며,
    거르지 않으면 계약 목록이 오염된다.

    Args:
        trade_date: 조회 일자 (YYYYMMDD). 휴장일이면 빈 결과를 낸다

    Returns:
        전종목 시세 형태의 DataFrame
    """
    if trade_date.endswith("01"):
        return pd.DataFrame()

    return pd.DataFrame(
        {
            "ISU_CD": [NEAR_CONTRACT, FAR_CONTRACT, NEAR_CONTRACT, SPREAD_CONTRACT, OLD_SPREAD_CONTRACT],
            "ISU_NM": [
                f"{NEAR_NAME} (주간)",
                f"{FAR_NAME} (주간)",
                f"{NEAR_NAME} (야간)",
                "코스피200 SP 2009-2012 (주간)",
                "KOSPI 200 선물 스프레드 191CS (주간)",
            ],
            # 스프레드는 미결제약정이 `-` 다. 선물은 0 이어도 숫자가 온다
            "ACC_OPNINT_QTY": ["3,000", "2,900", "3,000", "-", "-"],
        }
    )


def _contract_response() -> pd.DataFrame:
    """개별종목 시세 응답을 흉내낸다.

    실제 응답의 성질을 그대로 담는다 — **최신 날짜가 먼저 오고, 숫자에 쉼표가 붙고,
    값이 없는 칸은 `-` 이며, 세션 표기가 날짜에 붙는다.** 종목 식별 컬럼은 없다.

    Returns:
        개별종목 시세 형태의 DataFrame
    """
    return pd.DataFrame(
        {
            "TRD_DD": [
                "2020/09/03 (주간)",
                "2020/09/03 (야간)",
                "2020/09/02 (주간)",
                "2020/09/01 (주간)",
            ],
            "TDD_OPNPRC": ["1,010.00", "-", "1,000.00", "-"],
            "TDD_HGPRC": ["1,020.00", "-", "1,005.00", "-"],
            "TDD_LWPRC": ["1,005.00", "-", "995.00", "-"],
            "TDD_CLSPRC": ["1,015.00", "-", "1,000.00", "-"],
            "ACC_TRDVOL": ["1,200", "0", "800", "0"],
            "ACC_TRDVAL": ["1,000,000", "0", "800,000", "0"],
            "SETL_PRC": ["1,015.00", "0.00", "1,000.00", "990.00"],
            "ACC_OPNINT_QTY": ["3,000", "3,000", "2,900", "10"],
            "SPOT_PRC": ["1,012.00", "0.00", "998.00", "988.00"],
        }
    )


@pytest.fixture
def stub_krx(monkeypatch: pytest.MonkeyPatch) -> None:
    """계약 목록 조회와 계약별 시세 조회를 스텁으로 바꾼다.

    Args:
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구
    """

    class _Snapshot:
        def fetch(self, trdDd: str, prodId: str) -> pd.DataFrame:  # noqa: N803
            return _snapshot(trdDd)

    monkeypatch.setattr(krx_futures_collector, "_import_krx_client", lambda: (_Snapshot, object))
    monkeypatch.setattr(
        krx_futures_collector,
        "_fetch_contract_history",
        lambda product_id, isin, start_date, end_date: _contract_response(),
    )


class TestContractCatalog:
    """계약 목록 확보 계약."""

    def test_night_and_spread_are_excluded(self, stub_krx: None) -> None:
        """
        목적: 야간 세션과 스프레드 종목이 계약 목록에 들어오지 않음을 고정한다.

        Given: 주간·야간·스프레드가 섞인 스냅숏 응답
        When: 계약 목록을 만든다
        Then: 주간 선물 계약만 남는다
        """
        # Given / When
        catalog = collect_contract_catalog(PRODUCT_KOSPI200, "20200902", "20200930")

        # Then
        assert set(catalog[COL_CONTRACT]) == {NEAR_CONTRACT, FAR_CONTRACT}
        assert SPREAD_CONTRACT not in set(catalog[COL_CONTRACT])
        assert all("(" not in name for name in catalog[COL_CONTRACT_NAME])

    def test_old_era_spread_naming_is_excluded(self, stub_krx: None) -> None:
        """
        목적: **2001~2005년 표기의 스프레드도 걸러짐**을 고정한다 (회귀).

        실제로 이 종목(`KOSPI 200 선물 스프레드 191CS`)이 필터를 빠져나가 30년 수집이
        정산가 0 으로 실패했다. 그때 필터는 ` SP ` 만 봤다.

        Given: 「스프레드」 표기의 옛 종목이 섞인 스냅숏
        When: 계약 목록을 만든다
        Then: 그 종목이 목록에 없다
        """
        # Given / When
        catalog = collect_contract_catalog(PRODUCT_KOSPI200, "20010903", "20010930")

        # Then
        assert OLD_SPREAD_CONTRACT not in set(catalog[COL_CONTRACT])

    @pytest.mark.parametrize(
        ("name", "open_interest", "expected"),
        [
            ("코스피200 SP 2009-2012", "-", True),
            ("KOSPI 200 선물 스프레드 191CS", "-", True),
            ("코스피200 F 202009", "3,000", False),
            # 선물은 미결제약정이 0 이어도 숫자가 온다. 0 을 결측으로 읽으면 계약이 사라진다
            ("KOSPI 200 선물 9703", "0", False),
            # 종목명 표기가 또 바뀌어도 미결제약정 결측이 남아 잡아낸다
            ("코스피200 알수없는표기 2609-2612", "-", True),
        ],
    )
    def test_spread_is_detected_by_name_or_missing_open_interest(
        self, name: str, open_interest: str, expected: bool
    ) -> None:
        """
        목적: 스프레드 판정이 이름과 미결제약정 두 축으로 이뤄짐을 고정한다.

        Given: 시대별 종목명과 미결제약정 표기
        When: 스프레드인지 판정한다
        Then: 기대대로 갈린다
        """
        # Given / When
        result = krx_futures_collector._is_spread(name, open_interest)

        # Then
        assert result is expected

    def test_holiday_snapshot_is_retried(self, stub_krx: None) -> None:
        """
        목적: 스냅숏 날짜가 휴장일이어도 계약을 놓치지 않음을 고정한다.

        Given: 1일로 끝나는 날짜가 빈 결과를 내는 스텁
        When: 1일부터 훑기 시작한다
        Then: 다음 날로 밀어 계약을 찾아낸다
        """
        # Given / When
        catalog = collect_contract_catalog(PRODUCT_KOSPI200, "20200901", "20200930")

        # Then
        assert len(catalog) == 2

    def test_empty_catalog_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 계약을 못 찾았을 때 조용히 빈 결과를 돌려주지 않음을 고정한다.

        Given: 항상 빈 결과를 내는 스냅숏
        When: 계약 목록을 만든다
        Then: ValueError 를 던진다
        """

        # Given
        class _Empty:
            def fetch(self, trdDd: str, prodId: str) -> pd.DataFrame:  # noqa: N803
                return pd.DataFrame()

        monkeypatch.setattr(krx_futures_collector, "_import_krx_client", lambda: (_Empty, object))

        # When / Then
        with pytest.raises(ValueError, match="계약을 한 개도 찾지 못했습니다"):
            collect_contract_catalog(PRODUCT_KOSPI200, "20200902", "20200930")

    def test_invalid_date_format_raises(self, stub_krx: None) -> None:
        """
        목적: 날짜 형식 오류를 조회 전에 막음을 고정한다.

        Given: 형식이 잘못된 시작일
        When: 계약 목록을 만든다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="형식이 잘못되었습니다"):
            collect_contract_catalog(PRODUCT_KOSPI200, "2020-09-02", "20200930")


class TestCollectFuturesHistory:
    """수집 전체 경로의 계약."""

    def test_multiple_contracts_survive_the_same_date(self, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: **같은 날짜의 여러 계약이 한 행도 사라지지 않음**을 고정한다.

        이 검증이 조용히 틀리는 가장 큰 길이다. 날짜만으로 중복을 지우면 차월물이 통째로
        사라지고, 그러면 롤 계수도 미결제약정 역전도 계산할 수 없다.

        Given: 같은 날짜에 두 계약이 있는 응답
        When: 수집한다
        Then: 날짜마다 두 계약이 모두 남는다
        """
        # Given / When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        saved = pd.read_csv(result.path)
        per_date = saved.groupby(COL_DATE)[COL_CONTRACT].nunique()
        assert set(per_date) == {2}, f"날짜별 계약 수가 2가 아닙니다:\n{per_date}"
        assert result.contract_count == 2

    def test_night_session_is_removed_and_counted(self, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: 야간 세션이 제거되고 **제외 건수가 반환**됨을 고정한다 (표본 보존).

        Given: 주간 3행·야간 1행짜리 계약 응답 두 개
        When: 수집한다
        Then: 저장에 야간이 없고 제외 건수가 계약 수만큼 집계된다
        """
        # Given / When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        assert result.excluded_night_count == 2, "계약마다 야간 1행씩 빠져야 합니다"
        saved = pd.read_csv(result.path)
        assert not saved[COL_DATE].astype(str).str.contains("야간").any()

    def test_sample_count_is_conserved(self, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: 입력 행 수 = 저장 행 수 + 제외 건수 합이 성립함을 고정한다 (표본 보존).

        Given: 계약 2개 × 응답 4행 = 8행
        When: 수집한다
        Then: 저장 + 야간 + 미개시 + 최근 제외가 입력과 맞는다
        """
        # Given
        source_rows = 2 * len(_contract_response())

        # When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        accounted = (
            result.row_count
            + result.excluded_night_count
            + result.excluded_dormant_count
            + result.excluded_recent_count
        )
        assert accounted == source_rows, f"표본이 사라졌습니다: 입력 {source_rows} / 집계 {accounted}"

    def test_no_trade_day_keeps_settlement_and_leaves_price_missing(self, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: 거래가 없던 날의 `-` 가 0 으로 채워지지 않고, 정산가는 남음을 고정한다.

        `-` 를 0 으로 채우면 「가격 0」인 행이 생겨 이상치 검사를 통과해 버린다.

        Given: 종가가 `-` 이고 정산가만 있는 행
        When: 수집한다
        Then: 종가는 결측이고 정산가는 값이 있다
        """
        # Given / When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        saved = pd.read_csv(result.path)
        no_trade = saved[saved[COL_VOLUME] == 0]
        assert not no_trade.empty, "거래 없는 날이 남아 있어야 합니다"
        assert no_trade[COL_CLOSE].isna().all(), "거래 없는 날의 종가는 결측이어야 합니다"
        assert (no_trade[COL_SETTLE] > 0).all(), "거래 없는 날에도 정산가는 있어야 합니다"

    def test_saved_schema_matches_contract(self, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: 저장 스키마와 컬럼 순서를 고정한다.

        Given: 스텁 응답
        When: 수집한다
        Then: 저장 파일의 컬럼이 계약과 정확히 같다
        """
        # Given / When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        saved = pd.read_csv(result.path)
        assert list(saved.columns) == FUTURES_REQUIRED_COLUMNS

    def test_unknown_product_raises(self, tmp_path: Path) -> None:
        """
        목적: 모르는 상품 코드로 조회하지 않음을 고정한다.

        Given: 목록에 없는 상품 코드
        When: 수집한다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="지원하지 않는 상품 코드입니다"):
            collect_futures_history("KRDRVFUUSD", output_dir=tmp_path, today=REFERENCE_DAY)

    def test_missing_source_column_raises(
        self, monkeypatch: pytest.MonkeyPatch, stub_krx: None, tmp_path: Path
    ) -> None:
        """
        목적: KRX 반환 컬럼이 바뀌면 조용히 통과하지 않음을 고정한다.

        Given: 정산가 컬럼이 빠진 응답
        When: 수집한다
        Then: ValueError 를 던진다
        """
        # Given
        broken = _contract_response().drop(columns=["SETL_PRC"])
        monkeypatch.setattr(
            krx_futures_collector,
            "_fetch_contract_history",
            lambda product_id, isin, start_date, end_date: broken,
        )

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼이 누락되었습니다"):
            collect_futures_history(PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY)


class TestRetry:
    """일시적 실패 재시도의 계약 — 데이터 문제는 재시도하지 않는다."""

    def test_transient_failure_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 연결 실패 같은 일시적 오류를 다시 눌러봄을 고정한다.

        한 상품에 호출이 700회를 넘어 그중 한 번이 실패하면 30분짜리 수집이 통째로 날아간다.
        실제로 KRX 가 JSON 이 아닌 응답을 돌려줘 코스피200 수집이 끊긴 적이 있다.

        Given: 두 번 실패한 뒤 성공하는 호출
        When: 재시도 헬퍼로 부른다
        Then: 결과를 돌려준다
        """
        # Given
        monkeypatch.setattr(krx_futures_collector.time, "sleep", lambda seconds: None)
        attempts: list[int] = []

        def _flaky() -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("일시적 오류")
            return "성공"

        # When
        result = krx_futures_collector._retry_krx_call(_flaky, "테스트 호출")

        # Then
        assert result == "성공"
        assert len(attempts) == 3

    def test_value_error_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: **데이터 문제는 다시 시도하지 않음**을 고정한다.

        스키마가 어긋났거나 값이 이상한 것은 다시 눌러도 같다. 재시도로 덮으면
        조용히 틀린 데이터가 들어온다.

        Given: 항상 ValueError 를 던지는 호출
        When: 재시도 헬퍼로 부른다
        Then: 한 번만 부르고 바로 예외를 올린다
        """
        # Given
        monkeypatch.setattr(krx_futures_collector.time, "sleep", lambda seconds: None)
        attempts: list[int] = []

        def _bad_data() -> str:
            attempts.append(1)
            raise ValueError("필수 컬럼이 누락되었습니다")

        # When / Then
        with pytest.raises(ValueError, match="필수 컬럼이 누락되었습니다"):
            krx_futures_collector._retry_krx_call(_bad_data, "테스트 호출")
        assert len(attempts) == 1, "데이터 문제를 다시 시도했습니다"

    def test_exhausted_retries_raise_the_original_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 끝까지 실패하면 원래 예외를 그대로 올림을 고정한다.

        조용히 빈 결과를 돌려주면 그 상품이 통째로 빠진 채 저장된다.

        Given: 항상 실패하는 호출
        When: 재시도 헬퍼로 부른다
        Then: 원래 예외가 올라온다
        """
        # Given
        monkeypatch.setattr(krx_futures_collector.time, "sleep", lambda seconds: None)

        def _always_fails() -> str:
            raise ConnectionError("계속 실패")

        # When / Then
        with pytest.raises(ConnectionError, match="계속 실패"):
            krx_futures_collector._retry_krx_call(_always_fails, "테스트 호출")


class TestDormantExclusion:
    """미개시 구간 제외의 계약 — 조건을 넓히면 버리면 안 되는 것까지 사라진다."""

    def test_dormant_rows_are_excluded_and_counted(self) -> None:
        """
        목적: 정산가·체결·미결제약정이 모두 없는 행만 빠지고 건수가 반환됨을 고정한다.

        Given: 미개시 1행과 정상 1행
        When: 미개시 구간을 제외한다
        Then: 미개시 1행만 빠지고 건수가 1이다
        """
        # Given
        df = pd.DataFrame(
            {
                COL_DATE: [date(1996, 6, 14), date(1996, 6, 26)],
                COL_SETTLE: [0.0, 95.0],
                COL_VOLUME: [0.0, 0.0],
                COL_OPEN_INTEREST: [0.0, 0.0],
            }
        )

        # When
        kept, excluded = krx_futures_collector._exclude_dormant(df)

        # Then
        assert excluded == 1
        assert kept[COL_SETTLE].tolist() == [95.0]

    def test_traded_row_with_zero_settlement_is_kept(self) -> None:
        """
        목적: **거래가 있는데 정산가가 0 인 행을 버리지 않음**을 고정한다.

        당일 행이 여기 해당한다. 정산 전이라 정산가가 0 이지만 거래량은 있으며,
        이것은 최근 구간 제외가 다룰 몫이다. 여기서 버리면 그 사실이 가려진다.

        Given: 정산가 0 이지만 거래량이 있는 행
        When: 미개시 구간을 제외한다
        Then: 그 행이 남는다
        """
        # Given
        df = pd.DataFrame(
            {
                COL_DATE: [date(2026, 9, 4)],
                COL_SETTLE: [0.0],
                COL_VOLUME: [103_413.0],
                COL_OPEN_INTEREST: [147_443.0],
            }
        )

        # When
        kept, excluded = krx_futures_collector._exclude_dormant(df)

        # Then
        assert excluded == 0
        assert len(kept) == 1


class TestSessionParsing:
    """세션 표기 파싱의 계약 — 붙는 자리가 통계마다 다르다."""

    @pytest.mark.parametrize(
        ("value", "expected_body", "expected_day"),
        [
            ("2020/09/03 (주간)", "2020/09/03", True),
            ("2020/09/03 (야간)", "2020/09/03", False),
            ("코스피200 F 202009 (주간)", "코스피200 F 202009", True),
            ("KOSPI 200 선물 9609 (주간)", "KOSPI 200 선물 9609", True),
            ("1996/05/03", "1996/05/03", True),
        ],
    )
    def test_session_mark_is_split(self, value: str, expected_body: str, expected_day: bool) -> None:
        """
        목적: 날짜에 붙든 종목명에 붙든 같게 갈림을 고정한다.

        Given: 세션 표기가 붙은 문자열
        When: 표기를 뗀다
        Then: 본문과 주간 여부가 갈린다
        """
        # Given / When
        body, is_day = krx_futures_collector._strip_session(value)

        # Then
        assert body == expected_body
        assert is_day is expected_day


class TestNumericParsing:
    """숫자 파싱의 계약 — `-` 를 0 으로 채우면 「가격 0」이 생긴다."""

    def test_dash_becomes_missing_not_zero(self) -> None:
        """
        목적: 값이 없는 칸이 결측으로 남고 0 이 되지 않음을 고정한다.

        Given: 쉼표가 붙은 숫자와 `-` 가 섞인 컬럼
        When: 숫자로 바꾼다
        Then: `-` 는 NaN 이고 나머지는 값이 된다
        """
        # Given
        series = pd.Series(["1,015.00", "-", "800"])

        # When
        converted = krx_futures_collector._to_numeric(series)

        # Then
        assert converted.isna().tolist() == [False, True, False]
        assert converted.iloc[0] == pytest.approx(1015.0)
        assert converted.iloc[2] == pytest.approx(800.0)


class TestSpotPrice:
    """현물가는 보조 지표라 막지 않고 세어서 알린다."""

    def test_missing_spot_is_counted(self, monkeypatch: pytest.MonkeyPatch, stub_krx: None, tmp_path: Path) -> None:
        """
        목적: 현물가 결측이 예외가 아니라 건수로 보고됨을 고정한다.

        Given: 현물가가 `-` 인 응답
        When: 수집한다
        Then: 저장은 되고 결측 건수가 반환된다
        """
        # Given
        response = _contract_response()
        response["SPOT_PRC"] = ["-", "-", "-", "-"]
        monkeypatch.setattr(
            krx_futures_collector,
            "_fetch_contract_history",
            lambda product_id, isin, start_date, end_date: response,
        )

        # When
        result = collect_futures_history(
            PRODUCT_KOSPI200, start_date="20200902", output_dir=tmp_path, today=REFERENCE_DAY
        )

        # Then
        assert result.missing_spot_count == result.row_count
        saved = pd.read_csv(result.path)
        assert saved[COL_SPOT].isna().all()
