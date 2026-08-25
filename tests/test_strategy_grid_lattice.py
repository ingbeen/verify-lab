"""원달러 그리드 격자의 계약을 고정한다.

격자는 **나머지 네 조각의 좌표계**다. 범위는 어느 레벨을 켤지만 정하고, 자금 배분은 활성 레벨의
위치로 배수를 정하며, 체결은 레벨가 돌파로 판정하고, 매도 목표가는 격자가 준다.
여기서 정의가 틀리면 그 위의 모든 판정이 **예외 없이 조용히 어긋난다.**

핵심 계약은 네 가지다.

- **레벨 가격은 영구 고정이다.** 범위가 어떻게 바뀌어도 같은 k 의 가격이 같다
- **목표가는 언제나 바로 위 칸**(`레벨_(k+1)`)이며 매수 체결가와 무관하다
- **활성 구간은 양끝을 포함한다.** 범위 경계가 레벨가와 정확히 같으면 그 레벨은 켜진다
- **경계 판정은 레벨가 직접 비교로 한다.** `log` 추정만 쓰면 g=0.008 에서 k=-40~39 의
  경계 80개 중 28개가 한 칸 밀린다 — 레벨이 조용히 사라지면 슬롯 금액의 분모가 달라져
  전 구간의 자금 배분이 어긋난다
- **가격을 감싸는 칸은 그 가격 이하의 가장 높은 레벨이다.** 하단 이탈 B안이 격자를
  아래로 연장할 때 어디까지 켜는지를 이 정의가 정한다
"""

import pytest

from verify_lab.strategy.grid.constants import GRID_ANCHOR_PRICE
from verify_lab.strategy.grid.lattice import (
    active_level_indices,
    enclosing_level_index,
    level_price,
    target_price,
)

# 손계산을 쉽게 하려고 앵커 100원·익절폭 25% 를 쓴다. 1.25 는 이진수로 정확히 표현되므로
# 레벨 가격이 51.2 / 64 / 80 / 100 / 125 / 156.25 / 195.3125 처럼 딱 떨어진다
HAND_ANCHOR = 100.0
HAND_GROWTH = 0.25

# 사양서 §12 의 기본 익절폭
SPEC_GROWTH = 0.008

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


class TestLevelPrice:
    """레벨 가격 산식을 손계산으로 박는다."""

    @pytest.mark.parametrize(
        ("index", "expected"),
        [(-3, 51.2), (-2, 64.0), (-1, 80.0), (0, 100.0), (1, 125.0), (2, 156.25), (3, 195.3125)],
    )
    def test_손계산_값과_일치한다(self, index: int, expected: float) -> None:
        """
        목적: `레벨_k = 앵커 × (1+g)^k` 산식을 고정한다 (음수 k 포함)

        Given: 앵커 100원·익절폭 25%
        When: 레벨 가격을 구한다
        Then: 손으로 계산한 값과 같다
        """
        # When
        actual = level_price(index, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # Then
        assert actual == pytest.approx(expected, abs=EXACT_TOLERANCE)

    def test_앵커는_k가_0인_레벨이다(self) -> None:
        """
        목적: 앵커의 의미를 고정한다 — 임의 상수이되 k=0 의 가격이다

        Given: 사양서의 앵커 1000원
        When: k=0 의 레벨 가격을 구한다
        Then: 앵커와 같다
        """
        # When
        actual = level_price(0, growth_rate=SPEC_GROWTH, anchor=GRID_ANCHOR_PRICE)

        # Then
        assert actual == pytest.approx(GRID_ANCHOR_PRICE, abs=EXACT_TOLERANCE)

    def test_k가_커지면_가격도_커진다(self) -> None:
        """
        목적: 격자가 단조 증가함을 고정한다. 활성 레벨 목록의 정렬 계약이 여기에 기댄다

        Given: 사양서 기본 익절폭
        When: 연속한 k 의 가격을 늘어놓는다
        Then: 오름차순이다
        """
        # When
        prices = [level_price(k, growth_rate=SPEC_GROWTH) for k in range(-30, 31)]

        # Then
        assert prices == sorted(prices)

    def test_앵커를_바꾸면_가격표가_달라진다(self) -> None:
        """
        목적: 사양서 §3.1 의 "앵커는 임의 상수"가 **가격표가 같다는 뜻이 아님**을 고정한다

        Given: 같은 익절폭, 앵커만 1000원과 500원
        When: 같은 가격대를 덮는 레벨 가격 집합을 각각 만든다
        Then: 한 가격도 겹치지 않는다 — 격자가 통째로 이동한다

        Note:
            이 계약이 없으면 "앵커를 바꿔도 동일"을 가격 동일로 오해해
            앵커를 자유롭게 바꾸는 코드가 들어온다. 성적이 크게 달라지지 않을 뿐이다
        """
        # When
        base = {level_price(k, growth_rate=SPEC_GROWTH, anchor=1000.0) for k in range(-60, 61)}
        shifted = {level_price(k, growth_rate=SPEC_GROWTH, anchor=500.0) for k in range(20, 141)}

        # Then
        assert min(shifted) < max(base) and max(shifted) > min(base)
        assert not base & shifted


class TestTargetPrice:
    """매도 목표가 계약을 고정한다."""

    def test_목표가는_바로_위_칸이다(self) -> None:
        """
        목적: `목표가 = 레벨_(k+1)` 을 고정한다 (사양서 §3.3)

        Given: 임의의 레벨 k
        When: 목표가와 한 칸 위 레벨 가격을 각각 구한다
        Then: 두 값이 같다
        """
        for index in (-12, -1, 0, 1, 17):
            # When
            actual = target_price(index, growth_rate=SPEC_GROWTH)
            expected = level_price(index + 1, growth_rate=SPEC_GROWTH)

            # Then
            assert actual == pytest.approx(expected, abs=EXACT_TOLERANCE)

    def test_익절폭이_레벨마다_정확히_같다(self) -> None:
        """
        목적: 격자 전 구간에서 `목표가 / 레벨가 - 1 == g` 임을 고정한다

        Given: 사양서 기본 익절폭
        When: 여러 레벨에서 목표가와 레벨가의 비를 구한다
        Then: 전부 정확히 g 다

        Note:
            레벨가를 미리 반올림해 두면 이 등식이 레벨마다 미세하게 깨져
            익절폭이 칸마다 달라진다 (결정 L3 의 근거)
        """
        for index in range(-30, 31):
            # When
            ratio = target_price(index, growth_rate=SPEC_GROWTH) / level_price(index, growth_rate=SPEC_GROWTH) - 1.0

            # Then
            assert ratio == pytest.approx(SPEC_GROWTH, abs=EXACT_TOLERANCE)


class TestActiveLevelIndices:
    """범위 안의 활성 레벨 목록 계약을 고정한다."""

    def test_손계산_구간과_일치한다(self) -> None:
        """
        목적: 범위가 주어졌을 때 활성 레벨 목록을 고정한다

        Given: 앵커 100원·익절폭 25%, 범위 64원 ~ 195.3125원 (레벨가와 정확히 일치)
        When: 활성 레벨을 구한다
        Then: k = -2 ~ 3 여섯 개다
        """
        # When
        actual = active_level_indices(64.0, 195.3125, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # Then
        assert actual == [-2, -1, 0, 1, 2, 3]

    def test_범위_경계가_레벨가와_같으면_포함한다(self) -> None:
        """
        목적: 활성 구간이 **양끝을 포함**함을 고정한다 (결정 L1)

        Given: 하단·상단이 레벨가와 정확히 일치하는 범위
        When: 활성 레벨을 구한다
        Then: 양끝 레벨이 목록에 들어 있다
        """
        # Given
        low = level_price(-5, growth_rate=SPEC_GROWTH)
        high = level_price(7, growth_rate=SPEC_GROWTH)

        # When
        actual = active_level_indices(low, high, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == list(range(-5, 8))

    @pytest.mark.parametrize("index", list(range(-40, 40)))
    def test_모든_경계에서_log_추정이_밀리지_않는다(self, index: int) -> None:
        """
        목적: 부동소수점 보정을 고정한다 (결정 L2)

        Given: 레벨가와 정확히 일치하는 하단을 k = -40 ~ 39 전부에서 만든다
        When: 그 레벨 하나만 담기는 좁은 범위로 활성 레벨을 구한다
        Then: 언제나 그 레벨 하나다

        Note:
            `log` 추정만 쓰면 이 80개 중 28개가 한 칸 밀려 목록이 비거나 다른 레벨을 준다.
            레벨이 조용히 사라지면 슬롯 금액의 분모가 달라져 전 구간의 자금 배분이 어긋난다
        """
        # Given
        boundary = level_price(index, growth_rate=SPEC_GROWTH)

        # When
        actual = active_level_indices(boundary, boundary, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == [index]

    def test_언제나_k_오름차순이다(self) -> None:
        """
        목적: 목록의 정렬 계약을 고정한다. 현금 부족 시 "아래(싼) 레벨부터" 체결하는
        결정 C5 가 이 순서에 기댄다

        Given: 넓은 범위
        When: 활성 레벨을 구한다
        Then: k 오름차순이고 가격도 오름차순이다
        """
        # When
        actual = active_level_indices(900.0, 1500.0, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == sorted(actual)
        prices = [level_price(k, growth_rate=SPEC_GROWTH) for k in actual]
        assert prices == sorted(prices)

    def test_활성_레벨은_전부_범위_안에_있다(self) -> None:
        """
        목적: 목록에 범위 밖 레벨이 섞이지 않음을 고정한다

        Given: 레벨가와 어긋나는 임의의 범위
        When: 활성 레벨을 구한다
        Then: 모든 레벨가가 하단 이상 상단 이하이고, 바로 바깥 두 칸은 범위 밖이다
        """
        # Given
        low, high = 1234.5, 1456.7

        # When
        actual = active_level_indices(low, high, growth_rate=SPEC_GROWTH)

        # Then
        assert actual
        for index in actual:
            assert low <= level_price(index, growth_rate=SPEC_GROWTH) <= high
        assert level_price(actual[0] - 1, growth_rate=SPEC_GROWTH) < low
        assert level_price(actual[-1] + 1, growth_rate=SPEC_GROWTH) > high

    def test_레벨이_하나도_없는_좁은_범위는_빈_목록이다(self) -> None:
        """
        목적: 엣지 케이스 — 두 레벨 사이에 낀 범위의 처리를 고정한다

        Given: 이웃한 두 레벨 사이에 완전히 들어가는 범위
        When: 활성 레벨을 구한다
        Then: 예외를 던지지 않고 빈 목록을 돌려준다

        Note:
            빈 목록은 "매수할 곳이 없다"는 정상 상태다. 최소 범위폭 20% 강제(§4.2)가
            평시에 이것을 막지만, 그 강제는 조각 2 의 책임이라 여기서 막지 않는다
        """
        # Given
        low = level_price(3, growth_rate=SPEC_GROWTH) * 1.001
        high = level_price(4, growth_rate=SPEC_GROWTH) * 0.999

        # When
        actual = active_level_indices(low, high, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == []

    def test_하단과_상단이_같아도_계산한다(self) -> None:
        """
        목적: 엣지 케이스 — 폭이 0인 범위를 오류로 보지 않음을 고정한다

        Given: 레벨가에 걸치지 않는 한 점
        When: 활성 레벨을 구한다
        Then: 빈 목록이다 (그 점이 레벨가면 그 레벨 하나임은 별도 테스트가 고정한다)
        """
        # Given
        point = level_price(2, growth_rate=SPEC_GROWTH) * 1.002

        # When
        actual = active_level_indices(point, point, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == []


class TestEnclosingLevelIndex:
    """가격을 감싸는 칸의 아래 레벨 번호를 고정한다 (결정 C79).

    하단 이탈 B안은 「당일 종가를 포함하는 칸까지」 격자를 연장한다. 칸은 두 레벨 사이의
    구간이므로 그 칸의 바닥, 즉 **종가 이하의 가장 높은 레벨**이 연장의 끝이다.
    """

    def test_레벨_사이_가격은_아래_레벨을_준다(self) -> None:
        """
        목적: `레벨_k ≤ 가격 < 레벨_(k+1)` 의 k 를 돌려줌을 고정한다

        Given: 레벨 1(125원)과 레벨 2(156.25원) 사이의 가격
        When: 감싸는 레벨을 구한다
        Then: 아래 레벨인 1 이다
        """
        # Given
        price = 130.0

        # When
        actual = enclosing_level_index(price, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # Then
        assert actual == 1

    def test_레벨가와_정확히_같으면_그_레벨이다(self) -> None:
        """
        목적: 아래쪽 경계를 **포함**함을 고정한다

        Given: 레벨 2 의 가격 그 자체
        When: 감싸는 레벨을 구한다
        Then: 2 다 — 한 칸 아래인 1 이 아니다
        """
        # Given
        price = level_price(2, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # When
        actual = enclosing_level_index(price, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # Then
        assert actual == 2

    def test_바로_아래_레벨보다_높고_그_위_레벨보다_낮다(self) -> None:
        """
        목적: 반환값의 불변조건을 가격으로 직접 고정한다

        Given: 레벨가에 걸치지 않는 가격
        When: 감싸는 레벨을 구한다
        Then: `레벨_k ≤ 가격 < 레벨_(k+1)` 이 성립한다
        """
        # Given
        price = 1234.56

        # When
        index = enclosing_level_index(price, growth_rate=SPEC_GROWTH)

        # Then
        assert level_price(index, growth_rate=SPEC_GROWTH) <= price
        assert price < level_price(index + 1, growth_rate=SPEC_GROWTH)

    @pytest.mark.parametrize("index", list(range(-40, 40)))
    def test_모든_레벨가에서_log_추정이_밀리지_않는다(self, index: int) -> None:
        """
        목적: 부동소수점 보정을 고정한다 (결정 C22 와 같은 함정)

        Given: 레벨가와 정확히 일치하는 가격을 k = -40 ~ 39 전부에서 만든다
        When: 감싸는 레벨을 구한다
        Then: 언제나 그 레벨 자신이다

        Note:
            `floor(log(가격/앵커) / log(1+g))` 만 쓰면 여기서 한 칸 밀린다.
            연장 하단이 한 칸 밀리면 **켜지는 레벨 수가 달라져 슬롯 금액의 분모가 어긋나는데**
            예외는 나지 않는다 — `active_level_indices` 가 밟았던 함정과 같다
        """
        # Given
        price = level_price(index, growth_rate=SPEC_GROWTH)

        # When
        actual = enclosing_level_index(price, growth_rate=SPEC_GROWTH)

        # Then
        assert actual == index

    def test_앵커보다_싼_가격은_음수_레벨을_준다(self) -> None:
        """
        목적: 엣지 케이스 — 음수 k 구간에서도 성립함을 고정한다

        Given: 앵커(100원)의 절반보다 조금 높은 가격
        When: 감싸는 레벨을 구한다
        Then: 음수 레벨이며 가격 관계가 그대로 성립한다
        """
        # Given
        price = 55.0

        # When
        actual = enclosing_level_index(price, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

        # Then
        assert actual < 0
        assert level_price(actual, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR) <= price
        assert price < level_price(actual + 1, growth_rate=HAND_GROWTH, anchor=HAND_ANCHOR)

    @pytest.mark.parametrize("price", [0.0, -1.0])
    def test_가격이_양수가_아니면_거부한다(self, price: float) -> None:
        """
        목적: 입력 검증 정책을 고정한다

        Given: 0 이하의 가격
        When: 감싸는 레벨을 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="가격"):
            enclosing_level_index(price, growth_rate=SPEC_GROWTH)


class TestLatticeIsPermanent:
    """격자 영구 고정 불변조건을 고정한다."""

    def test_범위가_바뀌어도_같은_k의_가격이_같다(self) -> None:
        """
        목적: 사양서 §3.2 의 "레벨 가격은 영구 고정" 을 불변조건으로 박는다

        Given: 겹치는 구간이 있는 서로 다른 범위 두 개
        When: 각각의 활성 레벨을 구하고 겹치는 k 의 가격을 비교한다
        Then: 전부 같다

        Note:
            범위 하단 기준으로 레벨을 재생성하면 재조정 때마다 격자가 미세하게 어긋나
            **기존 보유 슬롯 옆에 유령 레벨이 생기고 중복 매수가 누적된다.**
            고정 격자는 이 사고가 구조적으로 발생하지 않는다
        """
        # When
        narrow = active_level_indices(1100.0, 1300.0, growth_rate=SPEC_GROWTH)
        wide = active_level_indices(900.0, 1600.0, growth_rate=SPEC_GROWTH)

        # Then
        assert narrow
        offset = wide.index(narrow[0])
        assert wide[offset : offset + len(narrow)] == narrow

        for index in narrow:
            assert level_price(index, growth_rate=SPEC_GROWTH) == pytest.approx(
                GRID_ANCHOR_PRICE * (1.0 + SPEC_GROWTH) ** index, abs=EXACT_TOLERANCE
            )


class TestValidation:
    """입력 검증 정책을 고정한다."""

    @pytest.mark.parametrize("growth_rate", [0.0, -0.008, 1.0, 1.5])
    def test_익절폭이_0과_1_사이가_아니면_거부한다(self, growth_rate: float) -> None:
        """
        목적: 익절폭의 유효 범위를 고정한다

        Given: 0 이하이거나 1 이상인 익절폭
        When: 레벨 가격을 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="익절폭"):
            level_price(0, growth_rate=growth_rate)

    @pytest.mark.parametrize("anchor", [0.0, -1000.0])
    def test_앵커가_양수가_아니면_거부한다(self, anchor: float) -> None:
        """
        목적: 앵커의 유효 범위를 고정한다

        Given: 0 이하인 앵커
        When: 레벨 가격을 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="앵커"):
            level_price(0, growth_rate=SPEC_GROWTH, anchor=anchor)

    @pytest.mark.parametrize("low", [0.0, -100.0])
    def test_범위_하단이_양수가_아니면_거부한다(self, low: float) -> None:
        """
        목적: 범위 하단의 유효 범위를 고정한다. 로그를 취하므로 0 이하는 정의되지 않는다

        Given: 0 이하인 하단
        When: 활성 레벨을 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="하단"):
            active_level_indices(low, 1500.0, growth_rate=SPEC_GROWTH)

    def test_상단이_하단보다_낮으면_거부한다(self) -> None:
        """
        목적: 뒤집힌 범위를 조용히 통과시키지 않음을 고정한다

        Given: 상단 < 하단
        When: 활성 레벨을 구한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="상단"):
            active_level_indices(1500.0, 1400.0, growth_rate=SPEC_GROWTH)
