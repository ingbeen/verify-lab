"""공통 상수의 경로 기준점과 시세 스키마 계약을 고정한다.

경로가 실행 디렉터리에 따라 달라지면 같은 검증을 어디서 실행하느냐로 결과 저장 위치가
갈린다. 컬럼명이 흔들리면 이미 저장된 원시 시세를 읽지 못한다. 둘 다 여기서 고정한다.
"""

from verify_lab import common_constants


def test_base_dir_is_repository_root() -> None:
    """
    목적: 경로 기준점이 실행 디렉터리(CWD)가 아니라 저장소 루트임을 고정한다.

    Given: 설치된 verify_lab 패키지
    When: BASE_DIR 이 가리키는 위치를 확인한다
    Then: pyproject.toml 이 있는 디렉터리다
    """
    assert (common_constants.BASE_DIR / "pyproject.toml").is_file()


def test_storage_dir_is_under_base_dir() -> None:
    """
    목적: 데이터 저장소가 저장소 루트 아래에 있음을 고정한다.

    Given: 공통 상수
    When: STORAGE_DIR 을 확인한다
    Then: BASE_DIR / "storage" 와 같다
    """
    assert common_constants.STORAGE_DIR == common_constants.BASE_DIR / "storage"


def test_market_dir_holds_raw_prices() -> None:
    """
    목적: 수집한 원시 시세의 위치 계약을 고정한다 (git 동기화 대상).

    Given: 공통 상수
    When: MARKET_DIR 을 확인한다
    Then: STORAGE_DIR / "market" 과 같다
    """
    assert common_constants.MARKET_DIR == common_constants.STORAGE_DIR / "market"


def test_results_dir_holds_study_outputs() -> None:
    """
    목적: 검증 산출물의 위치 계약을 고정한다 (git 제외, 재생성 가능).

    Given: 공통 상수
    When: RESULTS_DIR 을 확인한다
    Then: STORAGE_DIR / "results" 와 같다
    """
    assert common_constants.RESULTS_DIR == common_constants.STORAGE_DIR / "results"


def test_meta_json_lives_in_results_dir() -> None:
    """
    목적: 실행 이력 파일의 위치를 고정한다.

    Given: 공통 상수
    When: META_JSON_PATH 를 확인한다
    Then: RESULTS_DIR 아래의 meta.json 이다
    """
    assert common_constants.META_JSON_PATH == common_constants.RESULTS_DIR / "meta.json"


def test_required_columns_match_stored_schema() -> None:
    """
    목적: 시세 파일의 필수 컬럼 목록과 순서를 고정한다.

    이미 저장된 원시 시세가 이 헤더를 쓰고 있고, 원시 시세 파일은 분석 코드가
    덮어쓰지 않는 불변 자산이므로 이 목록이 스키마의 기준이 된다.

    Given: 공통 상수
    When: REQUIRED_COLUMNS 를 확인한다
    Then: 날짜와 OHLCV 6개가 이 순서로 들어 있다
    """
    assert common_constants.REQUIRED_COLUMNS == ["Date", "Open", "High", "Low", "Close", "Volume"]


def test_price_columns_are_subset_of_required() -> None:
    """
    목적: 가격 컬럼이 필수 컬럼에서 파생됨을 고정한다 (중복 정의 방지).

    Given: 공통 상수
    When: PRICE_COLUMNS 와 REQUIRED_COLUMNS 를 비교한다
    Then: 가격 컬럼은 필수 컬럼의 부분집합이다
    """
    assert set(common_constants.PRICE_COLUMNS) <= set(common_constants.REQUIRED_COLUMNS)


def test_price_columns_exclude_date_and_volume() -> None:
    """
    목적: 가격 검증(양수 확인 등)의 대상이 OHLC 4개임을 고정한다.

    Given: 공통 상수
    When: PRICE_COLUMNS 를 확인한다
    Then: 날짜와 거래량은 포함되지 않는다
    """
    assert common_constants.COL_DATE not in common_constants.PRICE_COLUMNS
    assert common_constants.COL_VOLUME not in common_constants.PRICE_COLUMNS


def test_market_file_templates_produce_stored_names() -> None:
    """
    목적: 파일명 규칙이 **이미 저장된 원시 시세의 실제 이름**과 같음을 고정한다.

    이 규칙은 수집기 4곳·측정 1곳·검증 2곳·스크립트 1곳에 흩어져 있었다. 한 곳으로 모으면서
    문자열이 한 글자라도 달라지면 **기존 파일을 못 읽는데 예외는 파일 없음으로만 뜬다.**
    그래서 값 자체를 여기에 박아 둔다.

    Given: 파일명 템플릿 상수
    When: 종목 코드로 채우면
    Then: 저장소에 실제로 있는 이름이 나온다
    """
    assert common_constants.MARKET_FILE_TEMPLATE.format(ticker="QQQ") == "QQQ_max.csv"
    assert common_constants.MARKET_FILE_TEMPLATE.format(ticker="069500") == "069500_max.csv"
    assert common_constants.ADJUSTED_FILE_TEMPLATE.format(ticker="QQQ") == "QQQ_adjusted_max.csv"


def test_futures_file_template_uses_product_id() -> None:
    """
    목적: 선물은 **종목이 아니라 상품 코드**로 파일이 갈린다는 사실을 이름에 남긴다.

    같은 `{ticker}` 템플릿을 쓰면 선물 파일을 종목 파일로 착각해 로더를 잘못 고르게 된다 —
    선물은 날짜만으로 행이 유일해지지 않아 전용 로더가 필요하다.

    Given: 선물 파일명 템플릿
    When: 상품 코드로 채우면
    Then: 저장소에 실제로 있는 이름이 나온다
    """
    assert common_constants.FUTURES_FILE_TEMPLATE.format(product_id="KRDRVFUK2I") == "KRDRVFUK2I_max.csv"


def test_series_file_templates_are_distinct() -> None:
    """
    목적: 시세와 단일 값 시계열의 파일명이 서로 섞이지 않음을 고정한다 (경계 조건).

    Given: 세 종류의 파일명 템플릿
    When: 같은 종목 코드로 채우면
    Then: 셋이 모두 다른 이름이다
    """
    names = {
        common_constants.MARKET_FILE_TEMPLATE.format(ticker="261240"),
        common_constants.ADJUSTED_FILE_TEMPLATE.format(ticker="261240"),
        common_constants.NAV_FILE_TEMPLATE.format(ticker="261240"),
    }
    assert len(names) == 3
