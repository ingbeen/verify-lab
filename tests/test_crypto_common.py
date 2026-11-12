"""비트코인 시세를 읽는 로더를 고정한다.

비트코인은 주식 · ETF 보다 정상 변동 폭이 커서 공용 급등락 임계값으로는 실제 시세(2011-10-28 +56.1%)가 막힌다.
그래서 비트코인 시세는 그 자산군의 임계값을 넘기는 로더 하나로 읽는다.
"""

from pathlib import Path

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VOLUME
from verify_lab.data.crypto_common import load_crypto_market_csv
from verify_lab.data.loader import load_market_csv


def _write_market(path: Path, closes: list[float]) -> Path:
    """종가 목록으로 시세 스키마 CSV 를 쓴다 — 시가·고가·저가는 종가와 같다.

    Args:
        path: 저장할 파일
        closes: 날마다의 종가

    Returns:
        저장한 경로
    """
    days = pd.date_range("2011-10-26", periods=len(closes), freq="D").strftime("%Y-%m-%d")
    pd.DataFrame(
        {
            COL_DATE: days,
            COL_OPEN: closes,
            COL_HIGH: closes,
            COL_LOW: closes,
            COL_CLOSE: closes,
            COL_VOLUME: [1.0] * len(closes),
        }
    ).to_csv(path, index=False)

    return path


class TestCryptoMarketLoader:
    """비트코인 시세는 «한 로더»로 읽는다 — 급등락 임계값을 호출마다 넘기지 않는다

    공용 로더에 임계값을 호출마다 넘기면 **같은 값을 넘긴다는 약속이 기억에만 걸린다** —
    측정 runner 가 평소처럼 `load_market_csv(path)` 로 부르면 2011-10-28 +56.1% 에서 막힌다
    (2026-09-29 사용자 결정 d · `docs/매매/반감기_사이클/설계.md`).
    """

    def test_실제로_있었던_큰_변동은_통과한다(self, tmp_path: Path) -> None:
        """
        목적: 비트코인 임계값이 실제 최대 변동(+56.1%)을 막지 않음을 고정한다.

        Given: 하루 +56% 가 한 번 있는 시세 파일
        When: 비트코인 로더로 읽는다
        Then: 예외 없이 네 행이 읽힌다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 15.6, 15.0])

        # When
        frame = load_crypto_market_csv(path)

        # Then
        assert len(frame) == 4

    def test_공용_로더는_같은_파일을_막는다(self, tmp_path: Path) -> None:
        """
        목적: 위 통과가 비트코인 로더의 «임계값» 덕분임을 대조로 고정한다 — 공용 값(0.50)이면 막힌다.

        Given: 같은 시세 파일
        When: 공용 로더를 인자 없이 부른다
        Then: 급등락으로 ValueError 가 발생한다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 15.6, 15.0])

        # When / Then
        with pytest.raises(ValueError, match="급등락"):
            load_market_csv(path)

    def test_자릿수_오류_모양의_변동은_여전히_막는다(self, tmp_path: Path) -> None:
        """
        목적: 임계값을 넓혀도 데이터 오류(÷10 = −90%)는 걸림을 고정한다 (경계 조건).

        Given: 하루 −90% 가 있는 시세 파일
        When: 비트코인 로더로 읽는다
        Then: ValueError 가 발생한다
        """
        # Given
        path = _write_market(tmp_path / "BTCUSD_max.csv", [10.0, 10.0, 1.0, 1.0])

        # When / Then
        with pytest.raises(ValueError, match="급등락"):
            load_crypto_market_csv(path)
