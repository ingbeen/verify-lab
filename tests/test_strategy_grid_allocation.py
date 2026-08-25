"""원달러 그리드 자금 배분의 계약을 고정한다.

배분이 틀리면 **성적이 통째로 달라지는데 자산곡선은 멀쩡해 보인다.** 특히 분모와 잉여가 그렇다.

핵심 계약은 다섯 가지다.

- **분모는 활성 레벨 전체다.** 미보유만 세면 보유가 늘수록 남은 슬롯이 커져 하단에서 노출이
  폭증한다. 이 함수는 **보유 여부를 인자로 받지 않아** 그 사고가 구조적으로 불가능하다
- **총액이 보존된다.** `Σ슬롯금액 + 잉여 == 총자산` 이 언제나 성립한다
- **구간 경계는 정확한 3등분**이며 경계값은 위 구간에 들어간다
- **상한 판정은 곱셈으로 한다.** 나눗셈으로 비중을 만들면 정확히 상한과 같은 값이 오발동해
  사양서 §13.2 의 필수 지표인 「상한 발동 횟수」가 오염된다
- **활성 레벨 0개는 예외가 아니다.** 하단 이탈 시 정상적으로 발생하는 상태다
"""

import inspect
import math

import pytest

from verify_lab.strategy.grid.allocation import allocate_slots, band_multiplier, level_position
from verify_lab.strategy.grid.constants import (
    DEFAULT_ALLOCATION_SPREAD,
    DEFAULT_SLOT_CAP_RATIO,
    GRID_ANCHOR_PRICE,
    LOWER_BAND_LIMIT,
    UPPER_BAND_LIMIT,
)
from verify_lab.strategy.grid.lattice import level_price

# 손계산을 쉽게 하려고 익절폭 25% 를 쓴다. 레벨 네 개(k=0~3)의 위치가 정확히 0 / ⅓ / ⅔ / 1 이 된다
HAND_GROWTH = 0.25
HAND_LOW = 1000.0
HAND_HIGH = 1953.125  # level_price(3) = 1000 × 1.25³

# 3.5 로 나누어떨어지는 총자산. 배수 합이 1.5+1.0+0.5+0.5 = 3.5 라 슬롯 금액이 딱 떨어진다
HAND_TOTAL = 350_000_000.0

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12

# 금액 비교 허용오차
AMOUNT_TOLERANCE = 0.01


def _hand_levels() -> list[int]:
    """손계산용 활성 레벨 네 개."""
    return [0, 1, 2, 3]


def _allocate(*, spread: float = DEFAULT_ALLOCATION_SPREAD, slot_cap_ratio: float = 1.0, total: float = HAND_TOTAL):
    """손계산용 기본 인자로 배분한다."""
    return allocate_slots(
        _hand_levels(),
        low=HAND_LOW,
        high=HAND_HIGH,
        total_assets=total,
        growth_rate=HAND_GROWTH,
        anchor=GRID_ANCHOR_PRICE,
        spread=spread,
        slot_cap_ratio=slot_cap_ratio,
    )


class TestLevelPosition:
    """로그 위치 산식을 고정한다."""

    def test_하단은_0이고_상단은_1이다(self) -> None:
        """
        목적: 위치의 양끝을 정확히 고정한다. 구간 배정이 여기에 기댄다

        Given: 범위 하단과 상단
        When: 위치를 구한다
        Then: 정확히 0 과 1 이다
        """
        # Then
        assert level_position(HAND_LOW, low=HAND_LOW, high=HAND_HIGH) == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert level_position(HAND_HIGH, low=HAND_LOW, high=HAND_HIGH) == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_등비_격자에서_위치가_균등하다(self) -> None:
        """
        목적: `ln(레벨가/하단) ÷ ln(상단/하단)` 산식을 손계산으로 박는다

        Given: 하단과 상단이 정확히 세 칸 떨어진 등비 격자
        When: 네 레벨의 위치를 구한다
        Then: 0 / ⅓ / ⅔ / 1 이다 — 등비 격자를 로그로 재면 균등 간격이다
        """
        # When
        actual = [
            level_position(level_price(index, growth_rate=HAND_GROWTH), low=HAND_LOW, high=HAND_HIGH)
            for index in _hand_levels()
        ]

        # Then
        assert actual == pytest.approx([0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0], abs=EXACT_TOLERANCE)

    def test_범위_밖_레벨도_계산한다(self) -> None:
        """
        목적: 엣지 케이스 — 위치가 0~1 밖으로 나가는 것을 막지 않음을 고정한다

        Given: 하단보다 한 칸 낮은 가격
        When: 위치를 구한다
        Then: 음수가 나온다 (예외가 아니다)

        Note:
            하단 이탈 B안(G3)이 격자를 아래로 연장하면 음수 위치가 실제로 생긴다.
            그때의 배수는 별도 규정(결정 C6)이므로 여기서 막지 않는다
        """
        # Given
        below = level_price(-1, growth_rate=HAND_GROWTH)

        # When
        actual = level_position(below, low=HAND_LOW, high=HAND_HIGH)

        # Then
        assert actual == pytest.approx(-1.0 / 3.0, abs=EXACT_TOLERANCE)

    def test_하단과_상단이_같으면_거부한다(self) -> None:
        """
        목적: 0 으로 나누는 상황을 조용히 통과시키지 않음을 고정한다

        Given: 하단 == 상단
        When: 위치를 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="상단"):
            level_position(1000.0, low=1000.0, high=1000.0)

    @pytest.mark.parametrize("low", [0.0, -100.0])
    def test_하단이_양수가_아니면_거부한다(self, low: float) -> None:
        """
        목적: 로그의 정의역을 고정한다

        Given: 0 이하인 하단
        When: 위치를 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="하단"):
            level_position(1200.0, low=low, high=1500.0)


class TestBandMultiplier:
    """3구간 배수를 고정한다."""

    @pytest.mark.parametrize(
        ("position", "expected"),
        [(0.0, 1.5), (0.2, 1.5), (1.0 / 3.0, 1.0), (0.5, 1.0), (2.0 / 3.0, 0.5), (0.9, 0.5), (1.0, 0.5)],
    )
    def test_구간별_배수를_손계산으로_박는다(self, position: float, expected: float) -> None:
        """
        목적: 3구간 차등(1.5 / 1.0 / 0.5)과 **경계값이 위 구간에 들어감**을 고정한다 (결정 A1)

        Given: 구간 안팎의 위치
        When: 배수를 구한다
        Then: 사양서 §5.1 표와 같다
        """
        # When
        actual = band_multiplier(position, spread=DEFAULT_ALLOCATION_SPREAD)

        # Then
        assert actual == pytest.approx(expected, abs=EXACT_TOLERANCE)

    def test_구간_경계가_정확한_3등분이다(self) -> None:
        """
        목적: 경계가 0.33/0.67 이 아니라 1/3·2/3 임을 고정한다 (결정 A1)

        Given: 0.33 과 1/3 사이의 위치
        When: 배수를 구한다
        Then: 아직 하단부다 — 사양서 표기(0.33)를 문자 그대로 쓰면 여기서 갈린다

        Note:
            0.33·0.67 은 1/3·2/3 의 소수 둘째 자리 반올림이다. 문자 그대로 쓰면
            중간부 0.34 · 상단부 0.33 으로 **의도하지 않은 비대칭**이 생긴다
        """
        # Given
        between = 0.332

        # When / Then
        assert 0.33 < between < LOWER_BAND_LIMIT
        assert band_multiplier(between, spread=DEFAULT_ALLOCATION_SPREAD) == pytest.approx(1.5, abs=EXACT_TOLERANCE)
        assert LOWER_BAND_LIMIT == pytest.approx(1.0 / 3.0, abs=EXACT_TOLERANCE)
        assert UPPER_BAND_LIMIT == pytest.approx(2.0 / 3.0, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize("spread", [0.3, 0.5, 0.7])
    def test_차등은_1을_중심으로_대칭이다(self, spread: float) -> None:
        """
        목적: 배수가 `(1+s, 1.0, 1−s)` 임을 고정한다 (사양서 §5.1 ±0.5 대칭)

        Given: 사양서 §12 의 차등 검사 범위
        When: 세 구간의 배수를 구한다
        Then: 하단부와 상단부의 평균이 정확히 중간부(1.0)다
        """
        # When
        lower = band_multiplier(0.0, spread=spread)
        middle = band_multiplier(0.5, spread=spread)
        upper = band_multiplier(1.0, spread=spread)

        # Then
        assert lower == pytest.approx(1.0 + spread, abs=EXACT_TOLERANCE)
        assert middle == pytest.approx(1.0, abs=EXACT_TOLERANCE)
        assert upper == pytest.approx(1.0 - spread, abs=EXACT_TOLERANCE)
        assert (lower + upper) / 2.0 == pytest.approx(middle, abs=EXACT_TOLERANCE)

    def test_차등이_0이면_균등_배분이다(self) -> None:
        """
        목적: 엣지 케이스 — 차등 0(균등 그리드)을 허용함을 고정한다

        Given: 차등 0
        When: 세 구간의 배수를 구한다
        Then: 전부 1.0 이다

        Note:
            사양서 §5.1 이 "균등 대비 우열은 백테스트가 판정한다" 고 적어
            균등이 비교 대상으로 존재한다. §12 의 검사 범위에는 없다
        """
        # Then
        for position in (0.0, 0.5, 1.0):
            assert band_multiplier(position, spread=0.0) == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize("spread", [1.0, 1.5, -0.1])
    def test_차등이_0과_1_사이가_아니면_거부한다(self, spread: float) -> None:
        """
        목적: 차등의 유효 범위를 고정한다. 1 이상이면 상단부 배수가 0 이하가 된다

        Given: 0 미만이거나 1 이상인 차등
        When: 배수를 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="차등"):
            band_multiplier(0.5, spread=spread)


class TestAllocateSlots:
    """슬롯 금액·잉여·상한 발동을 고정한다."""

    def test_슬롯_금액을_손계산으로_박는다(self) -> None:
        """
        목적: `총자산 × 배수 ÷ Σ(활성 레벨 배수)` 산식을 고정한다

        Given: 배수가 1.5 / 1.0 / 0.5 / 0.5 인 활성 레벨 네 개, 총자산 3.5억
        When: 상한이 걸리지 않는 조건으로 배분한다
        Then: 1.5억 / 1억 / 5천만 / 5천만 이다
        """
        # When
        actual = _allocate()

        # Then
        assert actual.amounts[0] == pytest.approx(150_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.amounts[1] == pytest.approx(100_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.amounts[2] == pytest.approx(50_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.amounts[3] == pytest.approx(50_000_000.0, abs=AMOUNT_TOLERANCE)

    def test_상한이_걸리지_않으면_총자산을_전부_배정한다(self) -> None:
        """
        목적: 총액 보존을 고정한다 — 잉여가 0 이다

        Given: 상한이 걸리지 않는 조건
        When: 배분한다
        Then: 슬롯 금액의 합이 총자산이고 잉여가 0 이다
        """
        # When
        actual = _allocate()

        # Then
        assert sum(actual.amounts.values()) == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)
        assert actual.surplus == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)
        assert actual.capped_levels == ()

    def test_상한이_걸리면_잉여로_남는다(self) -> None:
        """
        목적: 상한 발동 시에도 총액이 보존됨을 고정한다 (사양서 §5.2 잉여 산식)

        Given: 슬롯 상한 8%
        When: 배분한다
        Then: 네 레벨 전부 2,800만으로 잘리고 남은 2.38억이 잉여다
        """
        # When
        actual = _allocate(slot_cap_ratio=DEFAULT_SLOT_CAP_RATIO)

        # Then
        for index in _hand_levels():
            assert actual.amounts[index] == pytest.approx(28_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.surplus == pytest.approx(238_000_000.0, abs=AMOUNT_TOLERANCE)
        assert actual.capped_levels == (0, 1, 2, 3)

    @pytest.mark.parametrize("slot_cap_ratio", [0.06, 0.08, 0.10, 0.12, 0.5, 1.0])
    def test_총액이_언제나_보존된다(self, slot_cap_ratio: float) -> None:
        """
        목적: `Σ슬롯금액 + 잉여 == 총자산` 불변조건을 고정한다

        Given: 사양서 §12 의 상한 검사 범위와 그 밖의 값
        When: 배분한다
        Then: 언제나 총액이 맞는다

        Note:
            잉여를 돌려주지 않으면 상한이 걸렸을 때 **돈이 조용히 사라진다**
        """
        # When
        actual = _allocate(slot_cap_ratio=slot_cap_ratio)

        # Then
        assert sum(actual.amounts.values()) + actual.surplus == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)

    def test_상한과_정확히_같으면_자르지_않는다(self) -> None:
        """
        목적: 상한 판정의 부등호와 부동소수점 처리를 고정한다 (결정 A5)

        Given: 균등 배분(차등 0)이라 슬롯 넷이 정확히 총자산의 25% 씩인 조건
        When: 상한을 25% 로 두고 배분한다
        Then: 발동하지 않고 잉여가 0 이다

        Note:
            비중을 나눗셈으로 만들어 비교하면 여기가 오발동한다.
            값은 그대로인 채 「상한 발동 횟수」만 늘어 사양서 §13.2 의 지표가 오염된다
        """
        # When
        actual = _allocate(spread=0.0, slot_cap_ratio=0.25, total=100.0)

        # Then
        assert actual.capped_levels == ()
        assert actual.surplus == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_상한이_한_레벨만_걸리기도_한다(self) -> None:
        """
        목적: 상한이 레벨별로 판정됨을 고정한다

        Given: 하단부(1.5배)만 넘는 상한
        When: 배분한다
        Then: 하단부 하나만 잘리고 나머지는 그대로다
        """
        # Given — 하단부는 3.5억의 3/7 ≈ 42.9%, 중간부는 2/7 ≈ 28.6%
        cap = 0.35

        # When
        actual = _allocate(slot_cap_ratio=cap)

        # Then
        assert actual.capped_levels == (0,)
        assert actual.amounts[0] == pytest.approx(HAND_TOTAL * cap, abs=AMOUNT_TOLERANCE)
        assert actual.amounts[1] == pytest.approx(100_000_000.0, abs=AMOUNT_TOLERANCE)

    def test_상한_적용_전_금액을_함께_돌려준다(self) -> None:
        """
        목적: 상한이 얼마나 잘라냈는지를 알 수 있게 함을 고정한다

        Given: 상한이 걸리는 조건
        When: 배분한다
        Then: 상한 적용 전 금액의 합이 총자산이다
        """
        # When
        actual = _allocate(slot_cap_ratio=DEFAULT_SLOT_CAP_RATIO)

        # Then
        assert sum(actual.uncapped_amounts.values()) == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)
        assert actual.uncapped_amounts[0] == pytest.approx(150_000_000.0, abs=AMOUNT_TOLERANCE)

    def test_보유_여부를_인자로_받지_않는다(self) -> None:
        """
        목적: 분모가 **활성 레벨 전체**임을 시그니처로 고정한다 (결정 C4·A2)

        Given: 배분 함수
        When: 파라미터 목록을 살펴본다
        Then: 보유 상태를 넘길 자리가 아예 없다

        Note:
            미보유 활성 레벨만 분모로 세면 보유가 늘수록 남은 슬롯이 커져
            **하단에서 노출이 폭증**한다. 인자로 받지 않으면 구조적으로 불가능하다.
            파라미터 집합을 통째로 고정해, 보유 상태를 끼워 넣으려면 이 테스트를 반드시 지나게 한다
        """
        # When
        names = set(inspect.signature(allocate_slots).parameters)

        # Then
        assert names == {
            "level_indices",
            "low",
            "high",
            "total_assets",
            "growth_rate",
            "anchor",
            "spread",
            "slot_cap_ratio",
        }

    def test_활성_레벨이_없으면_전액이_잉여다(self) -> None:
        """
        목적: 엣지 케이스 — 하단 이탈 시의 정상 상태를 고정한다 (결정 A4)

        Given: 활성 레벨 0개
        When: 배분한다
        Then: 예외 없이 빈 배분이고 잉여가 총자산이다
        """
        # When
        actual = allocate_slots(
            [],
            low=HAND_LOW,
            high=HAND_HIGH,
            total_assets=HAND_TOTAL,
            growth_rate=HAND_GROWTH,
            anchor=GRID_ANCHOR_PRICE,
            spread=DEFAULT_ALLOCATION_SPREAD,
            slot_cap_ratio=DEFAULT_SLOT_CAP_RATIO,
        )

        # Then
        assert actual.amounts == {}
        assert actual.surplus == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)
        assert actual.capped_levels == ()

    def test_활성_레벨이_하나면_전액을_배정한다(self) -> None:
        """
        목적: 엣지 케이스 — 레벨 하나짜리 배분을 고정한다

        Given: 활성 레벨 하나, 상한 없음
        When: 배분한다
        Then: 배수와 무관하게 그 레벨이 총자산 전액을 받는다 (분모가 자기 배수뿐이다)
        """
        # When
        actual = allocate_slots(
            [0],
            low=HAND_LOW,
            high=HAND_HIGH,
            total_assets=HAND_TOTAL,
            growth_rate=HAND_GROWTH,
            anchor=GRID_ANCHOR_PRICE,
            spread=DEFAULT_ALLOCATION_SPREAD,
            slot_cap_ratio=1.0,
        )

        # Then
        assert actual.amounts[0] == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)
        assert actual.surplus == pytest.approx(0.0, abs=AMOUNT_TOLERANCE)

    def test_위치와_배수를_함께_돌려준다(self) -> None:
        """
        목적: 사용자가 직접 대조할 수 있도록 근거 값을 남김을 고정한다

        Given: 손계산용 활성 레벨 네 개
        When: 배분한다
        Then: 레벨마다 위치와 배수가 담겨 있다
        """
        # When
        actual = _allocate()

        # Then
        assert actual.positions[0] == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert actual.positions[3] == pytest.approx(1.0, abs=EXACT_TOLERANCE)
        assert actual.multipliers[0] == pytest.approx(1.5, abs=EXACT_TOLERANCE)
        assert actual.multipliers[3] == pytest.approx(0.5, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize("total_assets", [0.0, -1.0])
    def test_총자산이_양수가_아니면_거부한다(self, total_assets: float) -> None:
        """
        목적: 총자산의 유효 범위를 고정한다

        Given: 0 이하인 총자산
        When: 배분한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="총자산"):
            _allocate(total=total_assets)

    @pytest.mark.parametrize("slot_cap_ratio", [0.0, -0.1, 1.5])
    def test_상한이_0과_1_사이가_아니면_거부한다(self, slot_cap_ratio: float) -> None:
        """
        목적: 슬롯 상한의 유효 범위를 고정한다

        Given: 0 이하이거나 1 초과인 상한
        When: 배분한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="슬롯 상한"):
            _allocate(slot_cap_ratio=slot_cap_ratio)

    def test_배정된_금액은_언제나_음수가_아니다(self) -> None:
        """
        목적: 배분의 기본 불변조건을 고정한다

        Given: 차등 검사 범위의 양끝
        When: 배분한다
        Then: 모든 슬롯 금액과 잉여가 0 이상이다
        """
        for spread in (0.0, 0.3, 0.5, 0.7):
            # When
            actual = _allocate(spread=spread, slot_cap_ratio=DEFAULT_SLOT_CAP_RATIO)

            # Then
            assert all(amount >= 0 for amount in actual.amounts.values())
            assert actual.surplus >= 0


class TestLogPositionIsGeometric:
    """등비 격자와 로그 위치의 관계를 고정한다."""

    def test_위치는_가격이_아니라_비율에_비례한다(self) -> None:
        """
        목적: 사양서 §5.1 이 "등비 격자이므로 로그로 측정한다" 고 적은 이유를 고정한다

        Given: 하단 대비 같은 배율만큼 떨어진 두 가격
        When: 위치를 구한다
        Then: 위치 차이가 같다 — 산술 간격이 아니라 비율 간격이 균등하다
        """
        # Given
        low, high = 1000.0, 2000.0
        first, second, third = 1000.0 * 1.1, 1000.0 * 1.21, 1000.0 * 1.331

        # When
        positions = [level_position(price, low=low, high=high) for price in (first, second, third)]

        # Then
        assert positions[1] - positions[0] == pytest.approx(positions[2] - positions[1], abs=EXACT_TOLERANCE)
        assert positions[0] == pytest.approx(math.log(1.1) / math.log(2.0), abs=EXACT_TOLERANCE)


class TestExtendedLevelsBelowRange:
    """하단 이탈 B안이 켜는 **범위 아래 레벨**의 배분을 고정한다 (결정 C80·C81).

    연장 레벨은 위치가 음수라 별도 규정이 필요해 보이지만, 3구간 판정이 `위치 < 1/3` 이므로
    **하단부 배수가 그대로 나온다.** 특별 취급을 만들지 않는 것이 결정의 내용이다.
    """

    def _allocate_with_extension(self, *, spread: float = DEFAULT_ALLOCATION_SPREAD):
        """정식 범위는 그대로 두고 활성 레벨만 한 칸 아래로 늘려 배분한다."""
        return allocate_slots(
            [-1, *_hand_levels()],
            low=HAND_LOW,
            high=HAND_HIGH,
            total_assets=HAND_TOTAL,
            growth_rate=HAND_GROWTH,
            anchor=GRID_ANCHOR_PRICE,
            spread=spread,
            slot_cap_ratio=1.0,
        )

    def test_연장_레벨의_배수가_하단부다(self) -> None:
        """
        목적: 연장 구간의 배수를 고정한다 (결정 C80)

        Given: 정식 하단(레벨 0)보다 한 칸 아래인 레벨 -1 을 활성 레벨에 넣는다
        When: 배분한다
        Then: 그 레벨의 위치가 음수이고 배수가 하단부(1+차등)다
        """
        # When
        actual = self._allocate_with_extension()

        # Then
        assert actual.positions[-1] < 0.0
        assert actual.multipliers[-1] == pytest.approx(1.0 + DEFAULT_ALLOCATION_SPREAD, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize("spread", [0.3, 0.5, 0.7])
    def test_연장_배수가_차등_축을_따라간다(self, spread: float) -> None:
        """
        목적: 배수가 **리터럴 1.5 가 아니라 하단부 배수**임을 고정한다 (결정 C80 의 탈락안)

        Given: 자금 차등 축의 세 값
        When: 연장 레벨을 포함해 배분한다
        Then: 연장 레벨의 배수가 언제나 `1 + 차등` 이다

        Note:
            1.5 를 리터럴로 박으면 차등 0.3·0.7 에서 **연장 구간에만 축이 안 걸리는 예외**가 생긴다
        """
        # When
        actual = self._allocate_with_extension(spread=spread)

        # Then
        assert actual.multipliers[-1] == pytest.approx(1.0 + spread, abs=EXACT_TOLERANCE)

    def test_정식_범위의_위치가_연장에_흔들리지_않는다(self) -> None:
        """
        목적: 위치·배수의 기준이 **정식 범위**임을 고정한다 (결정 C81)

        Given: 연장 레벨이 있는 배분과 없는 배분
        When: 두 결과의 정식 레벨 위치를 견준다
        Then: 정확히 같다 — 하단은 여전히 0, 상단은 여전히 1 이다

        Note:
            연장 하단을 그대로 위치 산식에 넘기면 **3구간 경계가 통째로 이동해**
            상단부 레벨이 중간부로 내려앉는다. 예외는 나지 않고 배분만 조용히 달라진다
        """
        # Given
        plain = _allocate(slot_cap_ratio=1.0)

        # When
        extended = self._allocate_with_extension()

        # Then
        for index in _hand_levels():
            assert extended.positions[index] == pytest.approx(plain.positions[index], abs=EXACT_TOLERANCE)
        assert extended.positions[0] == pytest.approx(0.0, abs=EXACT_TOLERANCE)
        assert extended.positions[3] == pytest.approx(1.0, abs=EXACT_TOLERANCE)

    def test_연장이_기존_레벨의_슬롯을_줄인다(self) -> None:
        """
        목적: 사양서 §7 의 「매일 재정규화로 자동 축소 배분」을 고정한다

        Given: 연장 레벨이 있는 배분과 없는 배분
        When: 같은 총자산으로 배분한다
        Then: 기존 레벨의 슬롯 금액이 전부 작아지고, 총액은 여전히 보존된다

        Note:
            분모가 활성 레벨 전체(결정 C4)라 연장이 **기존 레벨의 슬롯까지 줄인다.**
            이것은 부작용이 아니라 B안이 노출을 감당하는 방식이다
        """
        # Given
        plain = _allocate(slot_cap_ratio=1.0)

        # When
        extended = self._allocate_with_extension()

        # Then
        for index in _hand_levels():
            assert extended.amounts[index] < plain.amounts[index]
        assert sum(extended.amounts.values()) + extended.surplus == pytest.approx(HAND_TOTAL, abs=AMOUNT_TOLERANCE)
