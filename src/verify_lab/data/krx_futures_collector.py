"""KRX 국내 선물 계약별 시세 수집

코스피200·코스닥150 선물의 **계약별** 일별 시세를 받아 `storage/market/` 에 원시 시세로 남긴다.

**pykrx 는 선물 기간 조회를 구현하지 않았다.** `get_future_ohlcv` 는 `NotImplementedError` 이고
`get_future_ohlcv_by_ticker` 는 하루치만 준다. 그래서 이 모듈은 pykrx 의 KRX 클라이언트(`KrxWebIo`)만
재사용하고 통계 코드를 직접 지정한다. `etn_collector` 와 같은 방식이다.

| 통계 코드 | 내용 | 받는 인자 |
| --- | --- | --- |
| `MDCSTAT12601` | **개별종목 시세 추이** — 한 계약의 기간 시세 | `prodId` · `isuCd`(ISIN) · `strtDd` · `endDd` |
| `MDCSTAT12501` | 전종목 시세 — 하루치 전 계약. 계약 목록을 얻는 경로 | `trdDd` · `prodId` |

**`MDCSTAT12701` 을 쓰지 않는다.** 이름이 비슷하지만 「최근월물 시세 추이」라 하루에 한 행만
주고 원월물이 통째로 빠진다. 차월물이 없으면 롤 계수도 미결제약정 역전도 계산할 수 없다.

**계약 코드를 규칙으로 생성할 수 없다.** 종목코드 체계가 시대별로 다르고(`10166000` →
`101Q9000` → `A0169000`) `MDCSTAT12601` 은 `isuCd` 가 비면 예외 없이 빈 결과를 준다.
그래서 전종목 시세 스냅숏을 훑어 계약 목록을 먼저 만든다.

**거를 것이 넷이다. 넷 다 조용히 틀리게 만든다.**

1. **야간 세션** — 하루에 두 행이 되어 수익률이 두 번 계산된다. 정산가가 0 으로 온다
2. **스프레드 종목** — 정산가 0, 미결제약정 없음. 전종목 시세에만 섞인다.
   **종목명 표기가 시대별로 다르다**(2001~2005 `KOSPI 200 선물 스프레드 191CS`,
   2010~ `코스피200 SP 2609-2812`)라 이름만 보면 놓친다 — 미결제약정 결측을 함께 본다
3. **당일** — 정산가가 아직 0 이다. 거래량이 있어도 그렇다
4. **미개시 구간** — 상장은 됐지만 체결도 미결제약정도 0 인 초기 며칠. 거래소가 아직 정산가를
   매기지 않아 0 으로 온다 (실측: `KOSPI 200 선물 9706` 은 상장일 1996-06-14 부터 9거래일이
   그랬고 1996-06-26 에 정산가 95.00 이 처음 붙었다)

넷을 걸러낸 뒤에도 정산가가 0 이면 **모르는 상황이므로 예외를 던진다.**
「정산가 0 이면 일단 버린다」로 넓히면 당일 행처럼 **버리면 안 되는 것까지 사라진다.**

이상치 판정은 `loader.validate_futures_data()` 를 그대로 재사용한다. 수집기가 자기 판정을
따로 두면 "수집은 통과했는데 로딩에서 막히는" 데이터가 생긴다.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, TypeVar

import pandas as pd

from verify_lab.common_constants import (
    COL_CLOSE,
    COL_CONTRACT,
    COL_CONTRACT_NAME,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_OPEN_INTEREST,
    COL_SETTLE,
    COL_SPOT,
    COL_VOLUME,
    FUTURES_FILE_TEMPLATE,
    FUTURES_REQUIRED_COLUMNS,
    FUTURES_ROW_KEY,
    MARKET_DIR,
)
from verify_lab.data.krx_credentials import load_krx_credentials
from verify_lab.data.loader import validate_futures_data
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# 재시도 헬퍼가 호출 결과의 타입을 그대로 돌려주게 한다
_T = TypeVar("_T")

# KRX 통계 코드. **전종목시세는 pykrx 의 클래스를 그대로 쓰므로 여기 두지 않는다** —
# 감싸지 않은 계약별 시세만 직접 지정한다
BLD_FUTURES_CONTRACT_PRICE: Final = "dbms/MDC/STAT/standard/MDCSTAT12601"

# 상품 코드. 값은 KRX 가 정한 것이라 바꿀 수 없다
PRODUCT_KOSPI200: Final = "KRDRVFUK2I"
PRODUCT_KOSDAQ150: Final = "KRDRVFUKQI"

# 상품별 최초 거래일 (실측). 이보다 앞선 날짜를 조회하면 빈 결과가 온다
PRODUCT_FIRST_TRADING_DAY: Final = {
    PRODUCT_KOSPI200: "19960503",
    PRODUCT_KOSDAQ150: "20151123",
}

# KRX 가 돌려주는 컬럼 → 저장 스키마
FUTURES_COLUMN_MAP: Final = {
    "TDD_OPNPRC": COL_OPEN,
    "TDD_HGPRC": COL_HIGH,
    "TDD_LWPRC": COL_LOW,
    "TDD_CLSPRC": COL_CLOSE,
    "ACC_TRDVOL": COL_VOLUME,
    "SETL_PRC": COL_SETTLE,
    "ACC_OPNINT_QTY": COL_OPEN_INTEREST,
    "SPOT_PRC": COL_SPOT,
}

# 전종목 시세가 계약을 가리키는 컬럼
SNAPSHOT_ISIN_COLUMN: Final = "ISU_CD"
SNAPSHOT_NAME_COLUMN: Final = "ISU_NM"

# KRX 응답의 날짜 컬럼
FUTURES_DATE_COLUMN: Final = "TRD_DD"

# 세션 표기. **개별종목 시세는 날짜에, 전종목 시세는 종목명에 붙는다**
DAY_SESSION_MARK: Final = "(주간)"

# 스프레드 종목을 가리키는 종목명 조각. **표기가 시대별로 다르다** (실측):
#   2001~2005 `KOSPI 200 선물 스프레드 191CS (주간)` / 2010~ `코스피200 SP 1009-1012 (주간)`
# ` SP ` 는 앞뒤 공백까지 포함해야 계약명과 섞이지 않는다
SPREAD_NAME_MARKS: Final = (" SP ", "스프레드")

# 전종목 시세의 미결제약정 컬럼. **스프레드는 이 값이 `-` 로 온다** —
# 선물은 0 이어도 숫자가 있으므로 이 성질이 시대 불문으로 둘을 가른다.
# 종목명 표기가 또 바뀌어도 이쪽이 남아 조용히 통과하는 것을 막는다
SNAPSHOT_OPEN_INTEREST_COLUMN: Final = "ACC_OPNINT_QTY"

# 값이 없는 칸의 표기
KRX_MISSING_MARK: Final = "-"

# 조회 인자의 날짜 형식
KRX_DATE_FORMAT: Final = "%Y%m%d"

# 응답 날짜 형식. 세션 표기를 뗀 뒤의 모양이다
FUTURES_RESPONSE_DATE_FORMAT: Final = "%Y/%m/%d"

# 저장에서 제외할 최근 구간 (달력일). **당일은 정산가가 0 으로 온다** —
# 거래량이 있어도 그렇다. `pykrx_collector`·`etn_collector` 와 같은 기준이다
RECENT_EXCLUSION_DAYS: Final = 1

# 계약 목록 스냅숏의 간격 (달력일). 분기물이라 계약 수명이 보통 1년을 넘지만,
# **상장 첫 분기의 계약은 수명이 두 달**이라(1996-05 상장분) 분기 간격으로는 놓친다.
# 한 달 간격이면 가장 짧은 계약도 두 번 이상 잡힌다
SNAPSHOT_INTERVAL_DAYS: Final = 30

# 스냅숏 날짜가 휴장일일 때 다음 날로 밀어보는 최대 횟수. 연휴를 넘길 만큼만 둔다
SNAPSHOT_RETRY_DAYS: Final = 5

# 계약 시세를 조회할 때 관측 구간의 앞뒤로 넉넉히 잡는 여유 (달력일).
# 스냅숏이 계약의 상장·만기를 정확히 집지 못하므로 여유를 두고 받는다.
# 상장 전 구간을 요청해도 거래소가 상장일부터만 주므로 안전하다
CONTRACT_FETCH_MARGIN_DAYS: Final = 400

# 일시적 실패를 다시 시도하는 횟수와 간격 (초).
# **한 상품을 받는 데 호출이 700회를 넘는다.** 그중 한 번이 실패하면 30분짜리 수집이 통째로
# 날아가므로 몇 번 다시 눌러본다. [실측] 2026-09-04 — 두 상품을 동시에 받다가 KRX 가
# JSON 이 아닌 응답을 돌려줘 코스피200 수집이 계약 목록 단계에서 끊겼다.
#
# **데이터 문제는 재시도하지 않는다.** 스키마가 어긋났거나 값이 이상한 것은 다시 눌러도
# 같으며, 재시도로 덮으면 조용히 틀린 데이터가 들어온다
RETRY_ATTEMPTS: Final = 4
RETRY_BACKOFF_SECONDS: Final = 3.0


# 저장 직전 자릿수. 지수 선물의 호가 단위는 0.05 라 소수 둘째 자리까지만 존재한다
PRICE_DECIMALS_FUTURES: Final = 2


@dataclass(frozen=True)
class FuturesCollectionResult:
    """선물 시세 수집 결과 요약.

    Attributes:
        product_id: 조회한 상품 코드
        path: 저장된 CSV 경로
        row_count: 저장된 행 수
        contract_count: 저장된 계약 수
        start_date: 저장 구간의 첫 거래일
        end_date: 저장 구간의 마지막 거래일
        catalog_count: 스냅숏에서 찾은 계약 수. `contract_count` 와 다르면 시세가 없던 계약이 있다
        excluded_night_count: 야간 세션 제외로 빠진 행 수
        excluded_dormant_count: 미개시 구간 제외로 빠진 행 수 (정산가·체결·미결제약정이 모두 없는 행)
        excluded_recent_count: 최근 구간 제외로 빠진 행 수
        empty_contract_count: 조회했으나 시세가 한 행도 없던 계약 수
        missing_spot_count: 현물가가 비어 있는 행 수. 보조 지표라 막지 않고 세어서 알린다
    """

    product_id: str
    path: Path
    row_count: int
    contract_count: int
    start_date: date
    end_date: date
    catalog_count: int
    excluded_night_count: int
    excluded_dormant_count: int
    excluded_recent_count: int
    empty_contract_count: int
    missing_spot_count: int


def _import_krx_client() -> tuple[Any, Any]:
    """자격증명을 환경 변수에 올린 뒤 pykrx 의 KRX 클라이언트를 가져온다.

    **`import pykrx` 자체가 로그인을 시도한다.** 모듈 최상단에서 import 하면 자격증명이
    올라가기 전에 로그인이 시도되므로, 순서를 지키는 유일한 방법은 import 를 이 함수 안에
    두는 것이다. `etn_collector`·`pykrx_collector` 와 같은 이유다.

    Returns:
        (전종목시세 클래스, KrxWebIo 기반 클래스) 짝
    """
    load_krx_credentials()

    from pykrx.website.krx.future.core import 전종목시세
    from pykrx.website.krx.krxio import KrxWebIo

    return 전종목시세, KrxWebIo


def _retry_krx_call(operation: Callable[[], _T], description: str) -> _T:
    """KRX 호출을 일시적 실패에 한해 다시 시도한다.

    **`ValueError` 는 다시 시도하지 않는다.** 스키마가 어긋났거나 값이 이상한 것은 다시
    눌러도 같으며, 재시도로 덮으면 조용히 틀린 데이터가 들어온다. 다시 누르는 것은
    연결이 끊겼거나 KRX 가 JSON 이 아닌 응답을 준 경우뿐이다.

    Args:
        operation: 호출을 수행하는 함수
        description: 로그에 남길 호출 설명

    Returns:
        호출 결과

    Raises:
        Exception: 마지막 시도까지 실패하면 그 예외를 그대로 올린다
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except ValueError:
            raise
        except Exception as error:  # noqa: BLE001
            if attempt == RETRY_ATTEMPTS:
                raise
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                f"KRX 호출 실패로 다시 시도합니다 ({attempt}/{RETRY_ATTEMPTS - 1}, {wait:.0f}초 뒤) - "
                f"{description}: {type(error).__name__}: {error}"
            )
            time.sleep(wait)

    raise RuntimeError(f"내부 불변조건 위반 - 재시도 루프를 빠져나왔습니다: description={description}")


def _to_numeric(series: pd.Series) -> pd.Series:
    """KRX 가 문자열로 주는 숫자를 실수로 바꾼다.

    천 단위 구분 쉼표가 붙어 있고, 값이 없는 칸은 `-` 로 온다. 쉼표만 떼고 숫자로 바꾸며
    **`-` 는 결측으로 남긴다** — 0 으로 채우면 거래가 없던 날이 「가격 0」이 되어
    이상치 검사를 통과해 버린다.

    Args:
        series: KRX 반환값의 한 컬럼

    Returns:
        실수 Series. 변환할 수 없는 칸은 NaN
    """
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def _validate_date_format(label: str, value: str) -> None:
    """조회 날짜 형식을 검증한다.

    Args:
        label: 예외 메시지에 쓸 인자 이름
        value: 검사할 날짜 문자열 (YYYYMMDD)

    Raises:
        ValueError: 형식이 잘못된 경우
    """
    try:
        datetime.strptime(value, KRX_DATE_FORMAT)
    except ValueError as error:
        raise ValueError(f"{label} 형식이 잘못되었습니다 (YYYYMMDD 여야 합니다): {value}") from error


def _strip_session(value: str) -> tuple[str, bool]:
    """세션 표기가 붙은 문자열에서 표기를 떼고 주간 여부를 함께 돌려준다.

    개별종목 시세는 날짜에(`2020/09/09 (야간)`), 전종목 시세는 종목명에
    (`코스피200 F 202009 (주간)`) 세션이 붙는다. 붙는 자리가 달라 같은 함수로 처리한다.

    Args:
        value: 세션 표기가 붙었을 수 있는 문자열

    Returns:
        (표기를 뗀 문자열, 주간이면 True)
    """
    if "(" not in value:
        return value.strip(), True

    body, _, marker = value.partition("(")
    return body.strip(), f"({marker.strip()}" == DAY_SESSION_MARK


def _is_spread(name: str, open_interest: str) -> bool:
    """스프레드 종목인지 판정한다.

    스프레드는 두 계약의 가격 차이를 거래하는 종목이라 **정산가가 0 이고 미결제약정이 없다.**
    계약 목록에 섞이면 롤 계수가 0 으로 나뉜다.

    **두 축으로 본다.** 종목명 표기는 시대별로 다르고(2001~2005 「스프레드」, 2010~ 「SP」)
    또 바뀔 수 있어서, 표기가 바뀌어도 남는 성질인 **미결제약정 결측**을 함께 본다.
    선물은 미결제약정이 0 이어도 숫자가 오므로 둘이 갈린다.

    Args:
        name: 세션 표기를 뗀 종목명
        open_interest: 전종목 시세의 미결제약정 칸 (문자열 그대로)

    Returns:
        스프레드면 True
    """
    if any(mark in name for mark in SPREAD_NAME_MARKS):
        return True

    return open_interest.strip() in ("", KRX_MISSING_MARK)


def collect_contract_catalog(product_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """전종목 시세 스냅숏을 훑어 그 기간에 존재한 계약 목록을 만든다.

    계약 코드를 규칙으로 생성할 수 없어서 필요한 단계다. 스냅숏 하나가 그 시점에 상장된
    모든 계약(만기가 몇 년 뒤인 것까지)을 보여주므로, 한 달 간격이면 가장 짧은 계약도
    두 번 이상 잡힌다.

    **야간 세션과 스프레드 종목을 뺀다.** 스프레드는 정산가가 0 이고 미결제약정이 없어
    그대로 두면 롤 계수가 0 으로 나뉜다.

    Args:
        product_id: 상품 코드
        start_date: 훑기 시작할 날짜 (YYYYMMDD)
        end_date: 훑기를 끝낼 날짜 (YYYYMMDD)

    Returns:
        `Contract`(ISIN) · `ContractName` · `FirstSeen` · `LastSeen` 컬럼을 갖는 DataFrame.
        `FirstSeen`·`LastSeen` 은 그 계약이 스냅숏에 보인 첫날과 마지막 날이다

    Raises:
        ValueError: 날짜 형식이 잘못됐거나, 한 계약도 찾지 못한 경우
    """
    _validate_date_format("훑기 시작일", start_date)
    _validate_date_format("훑기 종료일", end_date)

    snapshot_class, _ = _import_krx_client()

    first = datetime.strptime(start_date, KRX_DATE_FORMAT).date()
    last = datetime.strptime(end_date, KRX_DATE_FORMAT).date()
    if first > last:
        raise ValueError(f"훑기 시작일이 종료일보다 늦습니다: {start_date} > {end_date}")

    seen: dict[str, dict[str, Any]] = {}
    snapshot_count = 0
    cursor = first

    while cursor <= last:
        # 휴장일이면 빈 결과가 온다. 연휴를 넘길 만큼만 밀어본다
        for offset in range(SNAPSHOT_RETRY_DAYS):
            probe = cursor + timedelta(days=offset)
            if probe > last:
                break

            trade_date = probe.strftime(KRX_DATE_FORMAT)
            snapshot = _retry_krx_call(
                # 기본값으로 묶어 루프 변수를 그때 값으로 고정한다
                lambda day=trade_date: snapshot_class().fetch(trdDd=day, prodId=product_id),
                f"전종목 시세 {product_id} {trade_date}",
            )
            snapshot_count += 1
            if snapshot.empty:
                continue

            for isin, raw_name, raw_interest in zip(
                snapshot[SNAPSHOT_ISIN_COLUMN],
                snapshot[SNAPSHOT_NAME_COLUMN],
                snapshot[SNAPSHOT_OPEN_INTEREST_COLUMN],
                strict=False,
            ):
                name, is_day_session = _strip_session(str(raw_name))
                if not is_day_session or _is_spread(name, str(raw_interest)):
                    continue

                record = seen.get(isin)
                if record is None:
                    seen[isin] = {"name": name, "first": probe, "last": probe}
                else:
                    record["last"] = probe
            break

        cursor += timedelta(days=SNAPSHOT_INTERVAL_DAYS)

    if not seen:
        raise ValueError(f"계약을 한 개도 찾지 못했습니다 - 상품: {product_id}, 구간: {start_date}~{end_date}")

    catalog = pd.DataFrame(
        [
            {
                COL_CONTRACT: isin,
                COL_CONTRACT_NAME: record["name"],
                "FirstSeen": record["first"],
                "LastSeen": record["last"],
            }
            for isin, record in seen.items()
        ]
    ).sort_values("FirstSeen")

    logger.debug(f"계약 목록 확보: {len(catalog)}개 (스냅숏 {snapshot_count}회, 상품 {product_id})")

    return catalog.reset_index(drop=True)


def _fetch_contract_history(product_id: str, isin: str, start_date: str, end_date: str) -> pd.DataFrame:
    """한 계약의 기간 시세를 조회한다.

    pykrx 가 감싸지 않은 통계라 클라이언트만 재사용하고 통계 코드를 직접 지정한다.
    조회 구간이 2년을 넘으면 `KrxWebIo` 가 알아서 나눠 부르고 이어붙인다.

    Args:
        product_id: 상품 코드
        isin: 계약의 ISIN
        start_date: 조회 시작일 (YYYYMMDD)
        end_date: 조회 종료일 (YYYYMMDD)

    Returns:
        KRX 반환값 그대로의 DataFrame

    Raises:
        ValueError: ISIN 이 비어 있는 경우
    """
    if not isin.strip():
        raise ValueError("계약 ISIN 이 비어 있습니다 (이 통계는 빈 ISIN 에 예외 없이 빈 결과를 돌려줍니다)")

    _, web_io_class = _import_krx_client()

    class 파생개별종목시세(web_io_class):  # type: ignore[misc, valid-type]
        @property
        def bld(self) -> str:
            return BLD_FUTURES_CONTRACT_PRICE

        def fetch(self, prodId: str, isuCd: str, strtDd: str, endDd: str) -> pd.DataFrame:  # noqa: N803
            return pd.DataFrame(self.read(prodId=prodId, isuCd=isuCd, strtDd=strtDd, endDd=endDd)["output"])

    return _retry_krx_call(
        lambda: 파생개별종목시세().fetch(product_id, isin, start_date, end_date),
        f"개별종목 시세 {product_id} {isin} {start_date}~{end_date}",
    )


def _normalize_contract(raw: pd.DataFrame, isin: str, name: str) -> tuple[pd.DataFrame, int]:
    """한 계약의 KRX 반환값을 저장 스키마로 정규화하고 야간 제외 건수를 함께 돌려준다.

    **종목 식별 컬럼이 응답에 없다** — 조회 대상이 이미 정해져 있어서다. 그래서 호출 측이
    아는 계약 코드와 이름을 여기서 붙인다.

    Args:
        raw: KRX 반환값
        isin: 이 계약의 ISIN
        name: 이 계약의 이름

    Returns:
        (저장 스키마를 갖춘 DataFrame, 야간 세션으로 빠진 행 수)

    Raises:
        ValueError: 필요한 컬럼이 없는 경우
    """
    required_source_columns = {FUTURES_DATE_COLUMN, *FUTURES_COLUMN_MAP}
    missing_columns = required_source_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(f"필수 컬럼이 누락되었습니다: {sorted(missing_columns)} (반환 컬럼: {list(raw.columns)})")

    df = raw.rename(columns={FUTURES_DATE_COLUMN: COL_DATE, **FUTURES_COLUMN_MAP})

    # 1. 세션을 가른다. 야간은 정산가가 0 이라 남기면 이상치 검사에서 막힌다
    sessions = df[COL_DATE].astype(str).map(_strip_session)
    df[COL_DATE] = [value for value, _ in sessions]
    is_day_session = pd.Series([flag for _, flag in sessions], index=df.index)

    night_count = int((~is_day_session).sum())
    df = df.loc[is_day_session].copy()

    # 2. 숫자 변환. `-` 는 결측으로 남긴다
    for column in FUTURES_COLUMN_MAP.values():
        df[column] = _to_numeric(df[column])

    df[COL_DATE] = pd.to_datetime(df[COL_DATE], format=FUTURES_RESPONSE_DATE_FORMAT).dt.date
    df[COL_CONTRACT] = isin
    df[COL_CONTRACT_NAME] = name

    # 3. KRX 는 최신 날짜를 먼저 준다. 오름차순으로 되돌린다
    return df.sort_values(COL_DATE).reset_index(drop=True)[FUTURES_REQUIRED_COLUMNS], night_count


def _exclude_dormant(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """상장은 됐지만 아직 살아나지 않은 구간을 제외하고 빠진 행 수를 함께 돌려준다.

    **조건을 좁게 잡는다** — 정산가가 없고, 체결도 없고, 미결제약정도 0 인 행만 뺀다.
    이 셋이 동시에 참이면 그 행에는 이 계약에 대한 정보가 한 조각도 없다.

    「정산가가 0 이면 버린다」로 넓히면 **당일 행처럼 버리면 안 되는 것까지 사라진다.**
    당일은 거래량이 있는데도 정산가가 0 이며, 그것은 최근 구간 제외가 다룰 몫이다.

    Args:
        df: 정규화된 선물 시세 DataFrame

    Returns:
        (제외 후 DataFrame, 제외된 행 수)
    """
    settle_absent = df[COL_SETTLE].isna() | (df[COL_SETTLE] <= 0)
    never_traded = df[COL_VOLUME].fillna(0) == 0
    no_interest = df[COL_OPEN_INTEREST].fillna(0) == 0

    dormant = settle_absent & never_traded & no_interest
    dormant_count = int(dormant.sum())

    return df.loc[~dormant].reset_index(drop=True), dormant_count


def _exclude_recent(df: pd.DataFrame, today: date) -> tuple[pd.DataFrame, int]:
    """확정되지 않은 최근 구간을 제외하고 빠진 행 수를 함께 돌려준다.

    Args:
        df: 날짜 컬럼을 가진 DataFrame
        today: 기준일

    Returns:
        (제외 후 DataFrame, 제외된 행 수)
    """
    cutoff_date = today - timedelta(days=RECENT_EXCLUSION_DAYS)
    total_count = len(df)
    trimmed = df.loc[df[COL_DATE] <= cutoff_date].reset_index(drop=True)

    return trimmed, total_count - len(trimmed)


def collect_futures_history(
    product_id: str,
    start_date: str | None = None,
    output_dir: Path = MARKET_DIR,
    today: date | None = None,
) -> FuturesCollectionResult:
    """KRX 에서 선물 계약별 시세를 받아 원시 시세 파일로 저장한다.

    계약 목록 확보 → 계약별 조회 → 스키마 정규화 → 최근 구간 제외 → 이상치 검증 → 저장
    순으로 수행하며, **검증을 통과한 데이터만 저장한다.** 검증에서 걸리면 파일을 만들지 않고
    예외를 던진다 — 부분 성공을 저장하면 다음 실행이 어디까지 받았는지 알 수 없다.

    Args:
        product_id: 상품 코드 (`PRODUCT_KOSPI200` · `PRODUCT_KOSDAQ150`)
        start_date: 조회 시작일 (YYYYMMDD). 생략하면 그 상품의 최초 거래일부터 받는다
        output_dir: 저장 폴더
        today: 기준일. 생략하면 오늘. 최근 구간 제외의 기준이다

    Returns:
        수집 결과 요약

    Raises:
        ValueError: 상품 코드나 날짜 형식이 잘못됐거나, 저장할 행이 남지 않았거나,
            이상치가 발견된 경우
    """
    if product_id not in PRODUCT_FIRST_TRADING_DAY:
        raise ValueError(f"지원하지 않는 상품 코드입니다: {product_id} (가능: {sorted(PRODUCT_FIRST_TRADING_DAY)})")

    reference_day = today or date.today()
    first_trading_day = PRODUCT_FIRST_TRADING_DAY[product_id]
    scan_start = start_date or first_trading_day
    _validate_date_format("조회 시작일", scan_start)

    scan_end = reference_day.strftime(KRX_DATE_FORMAT)
    catalog = collect_contract_catalog(product_id, scan_start, scan_end)

    frames: list[pd.DataFrame] = []
    night_total = 0
    empty_contracts = 0

    for record in catalog.to_dict("records"):
        isin = str(record[COL_CONTRACT])
        name = str(record[COL_CONTRACT_NAME])
        first_seen: date = record["FirstSeen"]
        last_seen: date = record["LastSeen"]
        fetch_start = (first_seen - timedelta(days=CONTRACT_FETCH_MARGIN_DAYS)).strftime(KRX_DATE_FORMAT)
        fetch_end = min(last_seen + timedelta(days=CONTRACT_FETCH_MARGIN_DAYS), reference_day)

        raw = _fetch_contract_history(product_id, isin, fetch_start, fetch_end.strftime(KRX_DATE_FORMAT))
        if raw.empty:
            empty_contracts += 1
            logger.warning(f"시세가 없는 계약을 건너뜁니다 - 계약: {isin} ({name})")
            continue

        normalized, night_count = _normalize_contract(raw, isin, name)
        night_total += night_count
        frames.append(normalized)

    if not frames:
        raise ValueError(f"저장할 시세가 없습니다 - 상품: {product_id}, 계약 {len(catalog)}개를 조회했습니다")

    # 계약별 조회 구간이 겹쳐 같은 (날짜, 계약) 이 두 번 올 수 있다. 유일 키로 정리한다
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=FUTURES_ROW_KEY, keep="first")
    merged = merged.sort_values(FUTURES_ROW_KEY).reset_index(drop=True)

    awake, excluded_dormant = _exclude_dormant(merged)
    trimmed, excluded_recent = _exclude_recent(awake, reference_day)
    if trimmed.empty:
        raise ValueError(f"최근 구간을 제외하니 남는 행이 없습니다 - 상품: {product_id}")

    missing_spot = int(trimmed[COL_SPOT].isna().sum())
    if missing_spot:
        logger.warning(f"현물가가 비어 있는 행 {missing_spot:,}건 (보조 지표라 저장은 진행합니다)")

    validate_futures_data(trimmed)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / FUTURES_FILE_TEMPLATE.format(product_id=product_id)
    saved = trimmed.round(
        {column: PRICE_DECIMALS_FUTURES for column in (COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_SETTLE, COL_SPOT)}
    )
    saved.to_csv(path, index=False)

    logger.debug(
        f"선물 시세 저장 완료: {path.name}, {len(saved):,}행, 계약 {saved[COL_CONTRACT].nunique():,}개, "
        f"야간 제외 {night_total:,}건, 미개시 제외 {excluded_dormant:,}건, 최근 제외 {excluded_recent:,}건"
    )

    return FuturesCollectionResult(
        product_id=product_id,
        path=path,
        row_count=len(saved),
        contract_count=int(saved[COL_CONTRACT].nunique()),
        start_date=saved[COL_DATE].iloc[0],
        end_date=saved[COL_DATE].iloc[-1],
        catalog_count=len(catalog),
        excluded_night_count=night_total,
        excluded_dormant_count=excluded_dormant,
        excluded_recent_count=excluded_recent,
        empty_contract_count=empty_contracts,
        missing_spot_count=missing_spot,
    )
