"""정수 계약 제약의 계약 — 계약은 쪼갤 수 없다

본선 측정은 소수 계약으로 굴린다. 자기자본이 `E × (1 + 배수 × 수익률)` 로 닫혀 규모가
결과에 들어오지 않기 때문이며, 그래야 ETF 와 같은 조건에서 비교할 수 있다.

**그러나 실제로는 계약을 0.78 개 살 수 없다.** 코스피200 선물 1계약이 2억 원대라
자기자본이 작으면 목표 배수를 만들 수 없고, 그 크기를 이 계층이 낸다.

여기서 고정하는 것은 셋이다 — **반올림 규칙이 일관되는가**, **0계약을 집행 가능으로
착각하지 않는가**, **거래승수 이력을 날짜로 올바르게 고르는가**.
"""

import math
from datetime import date

import pytest

from verify_lab.data.krx_futures_collector import PRODUCT_KOSDAQ150, PRODUCT_KOSPI200
from verify_lab.studies.futures_leverage import contracts
from verify_lab.studies.futures_leverage.contracts import (
    contract_multiplier_on,
    integer_contract_position,
)

# 코스피200 선물의 최근 정산가와 승수. 실측값이며 1계약이 2억 5,750만 원이다
KOSPI200_PRICE = 1030.0
KOSPI200_MULTIPLIER = 250_000.0


class TestIntegerContracts:
    """계약 수는 정수여야 하고, 그 제약이 실제 배수를 목표에서 떼어놓는다."""

    def test_one_hundred_million_cannot_hit_two_times(self) -> None:
        """
        목적: **자기자본 1억으로는 코스피200 2배를 만들 수 없음**을 실측값으로 고정한다.

        목표 노출 2억을 만들려면 계약이 0.78 개 필요한데 1계약을 사면 노출이 2억 5,750만이
        되어 실제 배수가 2.58 배가 된다. 사용자가 «1억을 넣으면» 을 물었으므로 이 칸이
        결과 문서의 답이 된다.

        Given: 자기자본 1억, 목표 배수 2
        When: 정수 계약으로 포지션을 잡는다
        Then: 1계약이고 실제 배수가 2.58 배다
        """
        # Given
        equity = 100_000_000.0

        # When
        result = integer_contract_position(equity, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert result.contracts == 1
        assert result.actual_multiple == pytest.approx(2.575)
        assert result.executable is True

    def test_small_equity_cannot_take_a_position_at_all(self) -> None:
        """
        목적: 계약 하나도 못 사는 자기자본이 **「집행 불가」로 표시**됨을 고정한다.

        0계약을 그냥 0 으로 두면 「손실도 이익도 없었다」로 읽힌다. 실제로는 그 규모에서
        이 매매를 **할 수 없다**는 뜻이므로 값을 비우고 사유를 남긴다 (측정의 원칙 17).

        Given: 자기자본 1,000만원, 목표 배수 2
        When: 정수 계약으로 포지션을 잡는다
        Then: 0계약이고 집행 불가다
        """
        # Given
        equity = 10_000_000.0

        # When
        result = integer_contract_position(equity, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert result.contracts == 0
        assert result.executable is False

    def test_not_executable_leaves_the_multiple_empty(self) -> None:
        """
        목적: 집행 불가인 칸의 실제 배수가 **0 이 아니라 비어 있음**을 고정한다.

        0 으로 채우면 「배수 0 으로 굴렸다」로 읽히지만, 실제 뜻은 «그 규모에서는 이
        매매를 할 수 없다» 다. 둘은 전혀 다른 사실이다 (측정의 원칙 17).

        Given: 계약 하나도 못 사는 자기자본
        When: 정수 계약으로 포지션을 잡는다
        Then: 실제 배수가 NaN 이고 노출이 0 이다
        """
        # Given
        equity = 10_000_000.0

        # When
        result = integer_contract_position(equity, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert math.isnan(result.actual_multiple)
        assert result.exposure == 0.0

    def test_large_equity_lands_close_to_the_target(self) -> None:
        """
        목적: 자기자본이 커지면 정수 제약의 영향이 줄어듦을 고정한다.

        Given: 자기자본 5억, 목표 배수 2
        When: 정수 계약으로 포지션을 잡는다
        Then: 4계약이고 실제 배수가 2.06 배다
        """
        # Given
        equity = 500_000_000.0

        # When
        result = integer_contract_position(equity, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert result.contracts == 4
        assert result.actual_multiple == pytest.approx(2.06)

    def test_inverse_keeps_the_sign(self) -> None:
        """
        목적: 인버스에서 **계약 수가 음수로 유지**됨을 고정한다.

        부호를 잃으면 매도 포지션이 매수가 되어 방향이 뒤집힌다.

        Given: 자기자본 5억, 목표 배수 −2
        When: 정수 계약으로 포지션을 잡는다
        Then: 계약 수가 −4 이고 실제 배수가 음수다
        """
        # Given
        equity = 500_000_000.0

        # When
        result = integer_contract_position(equity, -2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert result.contracts == -4
        assert result.actual_multiple == pytest.approx(-2.06)

    def test_rounding_is_half_up_not_bankers(self) -> None:
        """
        목적: 반올림이 **정확히 0.5 에서도 위로** 감을 고정한다.

        파이썬 기본 `round` 는 짝수로 붙이므로(`round(0.5) == 0`) 그대로 쓰면 경계에서
        계약이 사라진다. 규칙을 하나로 못박지 않으면 같은 자기자본이 실행마다 다른
        계약 수를 낸다.

        Given: 목표 계약 수가 정확히 0.5 가 되는 자기자본
        When: 정수 계약으로 포지션을 잡는다
        Then: 1계약이다
        """
        # Given
        equity = 0.5 * KOSPI200_PRICE * KOSPI200_MULTIPLIER / 2.0

        # When
        result = integer_contract_position(equity, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)

        # Then
        assert result.contracts == 1

    def test_non_positive_equity_raises(self) -> None:
        """
        목적: 0 이하 자기자본을 막음을 고정한다.

        Given: 자기자본 0
        When: 정수 계약으로 포지션을 잡는다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="자기자본은 0보다 커야 합니다"):
            integer_contract_position(0.0, 2.0, KOSPI200_PRICE, KOSPI200_MULTIPLIER)


class TestContractMultiplierHistory:
    """거래승수는 날짜로 갈린다 — 이력을 잘못 고르면 명목금액이 두 배로 틀린다."""

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (date(1996, 5, 3), 500_000.0),
            (date(2017, 3, 24), 500_000.0),
            (date(2017, 3, 27), 250_000.0),
            (date(2026, 9, 3), 250_000.0),
        ],
    )
    def test_kospi200_multiplier_changes_on_the_measured_date(self, target: date, expected: float) -> None:
        """
        목적: 코스피200 승수가 **2017-03-27 을 경계로** 갈림을 고정한다.

        이 경계는 거래대금으로 역산해 확정한 값이다 (`docs/spec/futures_leverage.md` §5.5).
        경계를 하루 잘못 잡으면 그날의 명목금액이 두 배로 틀린다.

        Given: 경계 앞뒤의 날짜
        When: 그날의 거래승수를 고른다
        Then: 확정된 값이 나온다
        """
        # Given / When
        result = contract_multiplier_on(PRODUCT_KOSPI200, target)

        # Then
        assert result == expected

    def test_kosdaq150_has_a_single_multiplier(self) -> None:
        """
        목적: 코스닥150 이 전 구간 1만원임을 고정한다.

        Given: 상장일과 최근 날짜
        When: 그날의 거래승수를 고른다
        Then: 둘 다 1만원이다
        """
        # Given / When / Then
        assert contract_multiplier_on(PRODUCT_KOSDAQ150, date(2015, 11, 23)) == 10_000.0
        assert contract_multiplier_on(PRODUCT_KOSDAQ150, date(2026, 9, 2)) == 10_000.0

    def test_date_before_listing_raises(self) -> None:
        """
        목적: 상장 전 날짜를 조용히 넘기지 않음을 고정한다.

        조용히 첫 승수를 돌려주면 존재하지 않던 계약의 명목금액이 계산된다.

        Given: 코스피200 선물 상장 전날
        When: 그날의 거래승수를 고른다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="거래승수 이력이 시작되기 전"):
            contract_multiplier_on(PRODUCT_KOSPI200, date(1996, 5, 2))

    def test_unknown_product_raises(self) -> None:
        """
        목적: 모르는 상품 코드를 막음을 고정한다.

        Given: 이력에 없는 상품 코드
        When: 거래승수를 고른다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="거래승수 이력이 없는 상품"):
            contract_multiplier_on("KRDRVFUXXX", date(2026, 9, 3))


class TestMultiplierHistoryInvariant:
    """이력이 시간순이라는 전제를 검사한다"""

    def test_이력이_시간순이_아니면_거부한다(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        목적: 조회가 전제하는 정렬이 실제로 지켜지는지 확인한다.

        `contract_multiplier_on` 은 이력을 앞에서부터 훑으며 **뒤에 오는 것이 더 최신**이라고
        전제하고 마지막으로 걸린 값을 고른다. 정렬이 어긋나면 옛 승수를 고르는데,
        그 함수의 docstring 자신이 **"경계를 하루 잘못 잡으면 그날의 명목금액이 두 배로 틀린다"**
        고 경고한다. 이력은 이 저장소가 소유한 상수이므로 어긋남은 **내부 불변조건 위반**이다.

        Given: 날짜가 거꾸로 든 승수 이력
        When: 그 상품의 승수를 조회한다
        Then: `RuntimeError` 가 오른다
        """
        # Given
        monkeypatch.setattr(
            contracts,
            "CONTRACT_MULTIPLIER_HISTORY",
            {PRODUCT_KOSPI200: ((date(2017, 3, 27), 250_000), (date(1996, 5, 3), 500_000))},
        )

        # When · Then
        with pytest.raises(RuntimeError, match="내부 불변조건 위반"):
            contract_multiplier_on(PRODUCT_KOSPI200, date(2026, 9, 3))

    def test_실제_이력은_시간순이다(self) -> None:
        """
        목적: 지금 들어 있는 이력이 전제를 만족하는지 고정한다.

        위 테스트만으로는 "검사는 하지만 실제 데이터가 틀렸다"를 잡지 못하므로 짝으로 둔다.

        Given: 저장소가 소유한 승수 이력
        When: 상품마다 날짜 순서를 본다
        Then: 전부 오름차순이다
        """
        # Given · When · Then
        for product, history in contracts.CONTRACT_MULTIPLIER_HISTORY.items():
            days = [effective_from for effective_from, _ in history]
            assert days == sorted(days), f"{product} 의 승수 이력이 시간순이 아닙니다: {days}"
