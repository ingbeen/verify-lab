"""거래량 0 인 날의 종가 대체 — 무엇을 바꾸고 무엇을 두는지 고정한다.

거래가 없던 날의 Bitstamp 가격은 체결가가 아니라 **전일값 이월**이다(2015-01-06 ~ 08 은 네 값이 모두
276.80). 측정 계층이 그날의 **종가만** Coin Metrics 값으로 바꾸고 바꾼 날을 표시한다
(`docs/검증/반감기_사이클/설계.md` 결정 ④). **원시 파일은 바꾸지 않는다** — 메모리 안에서만 한다.
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_VALUE, COL_VOLUME
from verify_lab.data.crosscheck import COL_PRIMARY, COL_SECONDARY
from verify_lab.studies.halving_cycle.price_series import replace_zero_volume_closes


def _market() -> pd.DataFrame:
    """넷째 날만 거래가 없던 시세 — 그날 네 값은 전일 종가로 채워져 있다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(["2015-01-04", "2015-01-05", "2015-01-06", "2015-01-07"]),
            COL_OPEN: [270.0, 275.0, 276.8, 276.8],
            COL_HIGH: [280.0, 281.0, 276.8, 276.8],
            COL_LOW: [265.0, 270.0, 276.8, 276.8],
            COL_CLOSE: [275.0, 276.8, 276.8, 276.8],
            COL_VOLUME: [100.0, 120.0, 0.0, 0.0],
        }
    )


def _reference() -> pd.DataFrame:
    """같은 날들의 Coin Metrics 기준가."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime(["2015-01-03", "2015-01-04", "2015-01-05", "2015-01-06", "2015-01-07"]),
            COL_VALUE: [268.0, 276.0, 277.5, 287.55, 297.54],
        }
    )


def test_거래량_0_인_날의_종가만_바뀐다() -> None:
    """
    목적: 대체 범위를 «종가»로 고정한다 — 시가·고가·저가·거래량과 다른 날은 받은 그대로다.

    Given: 셋째·넷째 날 거래량이 0 인 시세
    When: 종가를 대체한다
    Then: 그 이틀의 종가만 Coin Metrics 값이고 나머지 칸은 원래 값이다
    """
    # Given
    market = _market()

    # When
    frame = replace_zero_volume_closes(market, _reference()).frame

    # Then
    assert frame[COL_CLOSE].tolist() == pytest.approx([275.0, 276.8, 287.55, 297.54], abs=0.01)
    for column in (COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME):
        assert frame[column].tolist() == market[column].tolist()
    assert frame[COL_DATE].tolist() == market[COL_DATE].tolist()


def test_바꾼_날의_목록을_함께_돌려준다() -> None:
    """
    목적: 「대체한 날을 표시한다」를 고정한다 — 날짜와 원래 종가, 바꾼 종가가 남는다.

    Given: 거래량 0 인 날이 이틀인 시세
    When: 종가를 대체한다
    Then: 목록이 두 행이고 Bitstamp 종가(이월값)와 Coin Metrics 종가를 담는다
    """
    # Given / When
    replaced = replace_zero_volume_closes(_market(), _reference()).replaced

    # Then
    assert replaced.columns.tolist() == [COL_DATE, COL_PRIMARY, COL_SECONDARY]
    assert replaced[COL_DATE].tolist() == [pd.Timestamp("2015-01-06"), pd.Timestamp("2015-01-07")]
    assert replaced[COL_PRIMARY].tolist() == pytest.approx([276.8, 276.8], abs=0.01)
    assert replaced[COL_SECONDARY].tolist() == pytest.approx([287.55, 297.54], abs=0.01)


def test_대조_계열에_그날이_없으면_예외다() -> None:
    """
    목적: 대체할 값이 없는 날을 이월값 그대로 두고 지나가지 않음을 고정한다.

    Given: 2015-01-07 이 빠진 기준가
    When: 종가를 대체한다
    Then: ValueError 가 발생한다
    """
    # Given
    reference = _reference().iloc[:-1]

    # When / Then
    with pytest.raises(ValueError, match="2015-01-07"):
        replace_zero_volume_closes(_market(), reference)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf")])
def test_대조_값이_유한한_양수가_아니면_예외다(value: float) -> None:
    """
    목적: 바꿔 넣는 값이 시세 검증을 다시 지나지 않는 틈을 막음을 고정한다 (경계 조건).

    단일 값 계열 로더는 부호를 보지 않는다 — 0 이 종가가 되면 그날 청산은 −100%, 그날 진입은 무한대로
    집계에 섞이는데 예외는 나지 않는다.

    Args:
        value: 거래가 없던 날의 대조 값

    Given: 2015-01-07 의 기준가가 0 이하이거나 무한대인 계열
    When: 종가를 대체한다
    Then: ValueError 가 발생한다
    """
    # Given
    reference = _reference()
    reference.loc[reference[COL_DATE] == pd.Timestamp("2015-01-07"), COL_VALUE] = value

    # When / Then
    with pytest.raises(ValueError, match="유한한 양수"):
        replace_zero_volume_closes(_market(), reference)


def test_거래량_0_인_날이_없으면_그대로다() -> None:
    """
    목적: 대체할 날이 없을 때 빈 목록과 같은 시세를 돌려줌을 고정한다 (경계 조건).

    Given: 모든 날 거래가 있는 시세
    When: 종가를 대체한다
    Then: 목록이 비었고(컬럼은 있다) 시세는 입력과 같다
    """
    # Given
    market = _market().assign(**{COL_VOLUME: 50.0})

    # When
    result = replace_zero_volume_closes(market, _reference())

    # Then
    assert result.replaced.empty
    assert result.replaced.columns.tolist() == [COL_DATE, COL_PRIMARY, COL_SECONDARY]
    pd.testing.assert_frame_equal(result.frame, market)


def test_입력을_바꾸지_않는다() -> None:
    """
    목적: 원시 시세를 제자리에서 고치지 않음을 고정한다 (데이터 불변성).

    Given: 시세와 기준가
    When: 종가를 대체한다
    Then: 두 입력이 호출 전과 같다
    """
    # Given
    market = _market()
    reference = _reference()
    market_before = market.copy()
    reference_before = reference.copy()

    # When
    replace_zero_volume_closes(market, reference)

    # Then
    pd.testing.assert_frame_equal(market, market_before)
    pd.testing.assert_frame_equal(reference, reference_before)
