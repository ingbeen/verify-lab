"""시장별 데이터 로더 패키지

**여기 모은 것은 여러 계층이 함께 쓰는 진입점뿐이다.** 선물 로더(`load_futures_csv`)와
ETN·선물 수집기처럼 부르는 계층이 하나뿐인 것은 각 모듈에서 직접 가져간다 —
쓰이지도 않는 이름을 여기 늘어놓으면 무엇이 공용인지가 흐려진다.
"""

from .ecos_collector import EcosCollectionResult, EcosSeries, collect_ecos_series
from .ecos_credentials import load_ecos_api_key, mask_api_key
from .fred_collector import FredCollectionResult, FredSeries, collect_fred_series
from .krx_credentials import load_krx_credentials
from .loader import load_market_csv, load_series_csv, validate_market_data, validate_series_data
from .pykrx_collector import PykrxCollectionResult, collect_pykrx_history
from .yfinance_collector import CollectionResult, collect_yfinance_history

__all__ = [
    "CollectionResult",
    "EcosCollectionResult",
    "EcosSeries",
    "FredCollectionResult",
    "FredSeries",
    "PykrxCollectionResult",
    "collect_ecos_series",
    "collect_fred_series",
    "collect_pykrx_history",
    "collect_yfinance_history",
    "load_ecos_api_key",
    "load_krx_credentials",
    "load_market_csv",
    "load_series_csv",
    "mask_api_key",
    "validate_market_data",
    "validate_series_data",
]
