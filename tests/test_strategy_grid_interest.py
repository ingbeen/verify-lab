"""실수령 금리 모델의 계약을 고정한다.

금리를 원지표 그대로 쓰면 **성적이 조용히 좋아진다.** T-bill 은 증권사 RP 수익의 상한이고
CD91 도 개인이 받는 파킹 금리보다 높다.

핵심 계약은 다섯 가지다.

- **4구간 계단이 사양서 §11.2 의 검증표와 맞는다**
- **하한이 걸린다.** 특히 RP 는 절반 가까운 날을 하한이 정한다
- **음수 T-bill 이 가장 낮은 칸으로 떨어진다** — DTB3 에 실재하는 값이다
- **원지표가 없는 날은 전일값을 이월하고 그 건수를 돌려준다**
- 달력 첫날 이전에 값이 없으면 **조용히 채우지 않고 거부한다**
"""

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE, COL_VALUE
from verify_lab.strategy.grid.constants import (
    DEFAULT_PARKING_FLOOR_RATE,
    DEFAULT_RP_FLOOR_RATE,
)
from verify_lab.strategy.grid.interest import (
    InterestConfig,
    build_rate_series,
    parking_rate,
    rp_rate,
)

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


def _series(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """단일 값 시계열을 만든다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.to_datetime([date for date, _ in rows]),
            COL_VALUE: [value for _, value in rows],
        }
    )


def _config(*, rp: float = DEFAULT_RP_FLOOR_RATE, parking: float = DEFAULT_PARKING_FLOOR_RATE) -> InterestConfig:
    """검사용 이자 설정."""
    return InterestConfig(rp_floor_rate=rp, parking_floor_rate=parking)


class TestRpRateSteps:
    """달러 RP 의 4구간 계단을 고정한다."""

    @pytest.mark.parametrize(
        ("tbill", "expected"),
        [
            (5.00, 4.00),  # 사양서 §11.2 검증표 — 실측 4.00~4.05%
            (3.60, 3.00),  # 실측 3.4% 안팎
            (1.00, 0.70),  # 실측 0.5~1.3%
            (0.25, 0.40),  # 하한이 이긴다. 실측 0.3~0.7%
        ],
    )
    def test_사양서_검증표를_그대로_박는다(self, tbill: float, expected: float) -> None:
        """
        목적: 사양서 §11.2 의 검증표 4행을 손계산으로 고정한다

        Given: 검증표의 T-bill 값
        When: RP 실수령 금리를 만든다
        Then: 표의 모델 결과와 같다
        """
        # When
        actual = rp_rate(tbill, floor=DEFAULT_RP_FLOOR_RATE)

        # Then
        assert actual == pytest.approx(expected, abs=EXACT_TOLERANCE)

    @pytest.mark.parametrize(
        ("tbill", "spread"),
        [(4.0, 1.00), (6.0, 1.00), (2.0, 0.60), (3.99, 0.60), (0.5, 0.30), (1.99, 0.30)],
    )
    def test_경계값은_위_칸에_들어간다(self, tbill: float, spread: float) -> None:
        """
        목적: 계단 경계의 부등호를 고정한다 — 사양서가 `x >= 4.0` 처럼 이상으로 적었다

        Given: 경계에 정확히 걸리는 T-bill
        When: RP 실수령 금리를 만든다
        Then: 위 칸의 스프레드가 적용된다 (하한이 걸리지 않는 값만 고른다)
        """
        # When
        actual = rp_rate(tbill, floor=0.0)

        # Then
        assert actual == pytest.approx(tbill - spread, abs=EXACT_TOLERANCE)

    def test_가장_낮은_칸은_0_10퍼센트포인트를_뺀다(self) -> None:
        """
        목적: `x < 0.5%` 칸의 스프레드를 고정한다

        Given: 0.5% 미만의 T-bill
        When: 하한 0 으로 RP 금리를 만든다
        Then: 0.10%p 가 빠진다
        """
        # When
        actual = rp_rate(0.45, floor=0.0)

        # Then
        assert actual == pytest.approx(0.35, abs=EXACT_TOLERANCE)

    def test_음수_티빌이_예외를_내지_않는다(self) -> None:
        """
        목적: DTB3 에 실재하는 음수 값(최저 −0.050%)이 계단에서 떨어지지 않게 고정한다

        Given: 음수 T-bill
        When: 하한 0 으로 RP 금리를 만든다
        Then: 예외 없이 0 이 나온다 — 계단을 못 찾으면 `StopIteration` 이 났을 것이다
        """
        # When
        actual = rp_rate(-0.05, floor=0.0)

        # Then
        assert actual == pytest.approx(0.0, abs=EXACT_TOLERANCE)

    def test_하한이_음수_티빌을_받아낸다(self) -> None:
        """
        목적: 기본 하한이 음수 금리를 실제로 막는지 고정한다

        Given: 음수 T-bill
        When: 기본 하한으로 RP 금리를 만든다
        Then: 하한값이 나온다
        """
        # When
        actual = rp_rate(-0.05, floor=DEFAULT_RP_FLOOR_RATE)

        # Then
        assert actual == pytest.approx(DEFAULT_RP_FLOOR_RATE, abs=EXACT_TOLERANCE)

    def test_하한이_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 하한을 즉시 막는다

        Given: 음수 하한
        When: RP 금리를 만든다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="RP 하한"):
            rp_rate(3.0, floor=-0.1)


class TestParkingRate:
    """원화 파킹 금리를 고정한다."""

    def test_CD91에서_0_30퍼센트포인트를_뺀다(self) -> None:
        """
        목적: 사양서 §11.2 의 파킹 산식을 고정한다

        Given: CD91 3.00%
        When: 파킹 금리를 만든다
        Then: 2.70%
        """
        # When
        actual = parking_rate(3.00, floor=DEFAULT_PARKING_FLOOR_RATE)

        # Then
        assert actual == pytest.approx(2.70, abs=EXACT_TOLERANCE)

    def test_하한이_이긴다(self) -> None:
        """
        목적: 저금리 구간에서 하한이 작동함을 고정한다

        Given: CD91 0.60%
        When: 파킹 금리를 만든다
        Then: 0.30% 가 아니라 하한 0.50% 다
        """
        # When
        actual = parking_rate(0.60, floor=DEFAULT_PARKING_FLOOR_RATE)

        # Then
        assert actual == pytest.approx(DEFAULT_PARKING_FLOOR_RATE, abs=EXACT_TOLERANCE)

    def test_하한이_음수면_거부한다(self) -> None:
        """
        목적: 잘못된 하한을 즉시 막는다

        Given: 음수 하한
        When: 파킹 금리를 만든다
        Then: ValueError
        """
        # When / Then
        with pytest.raises(ValueError, match="파킹 하한"):
            parking_rate(3.0, floor=-0.1)


class TestInterestConfig:
    """이자 설정의 검증을 고정한다."""

    @pytest.mark.parametrize("field", ["rp", "parking"])
    def test_하한이_음수면_거부한다(self, field: str) -> None:
        """
        목적: 설정 단계에서 잘못된 값을 막는다

        Given: 한쪽 하한이 음수인 설정
        When: 설정을 만든다
        Then: ValueError
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="하한"):
            _config(**{field: -0.1})


class TestRateSeriesAlignment:
    """마스터 달력 정렬과 이월을 고정한다."""

    def test_원지표가_없는_날은_전일값을_이월한다(self) -> None:
        """
        목적: 결정 C14 의 「미국 휴일은 T-bill 전일값 이월」을 고정한다

        Given: 달력에는 3일이 있는데 T-bill 은 가운데 날이 비어 있다
        When: 금리 계열을 만든다
        Then: 가운데 날에 전일값이 이월되고 이월 건수가 1이다
        """
        # Given
        calendar = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]))
        tbill = _series([("2020-01-01", 3.00), ("2020-01-02", 3.00), ("2020-01-06", 3.20)])
        cd91 = _series([("2020-01-01", 2.00), ("2020-01-02", 2.00), ("2020-01-03", 2.00), ("2020-01-06", 2.00)])

        # When
        actual = build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config())

        # Then
        assert actual.rp_filled == 1
        assert actual.parking_filled == 0
        assert actual.rp.loc[pd.Timestamp("2020-01-03")] == pytest.approx(2.40, abs=EXACT_TOLERANCE)

    def test_달력에_없는_날의_값도_이월에_쓰인다(self) -> None:
        """
        목적: 미국 시장만 열린 날의 값이 버려지지 않게 고정한다

        Given: 한국 휴일(달력에 없음)에만 T-bill 이 바뀐다
        When: 금리 계열을 만든다
        Then: 다음 거래일이 그 바뀐 값을 받는다
        """
        # Given
        calendar = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-06"]))
        tbill = _series([("2020-01-02", 3.00), ("2020-01-03", 5.00), ("2020-01-06", 5.00)])
        cd91 = _series([("2020-01-02", 2.00), ("2020-01-06", 2.00)])

        # When
        actual = build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config())

        # Then
        assert actual.rp.loc[pd.Timestamp("2020-01-06")] == pytest.approx(4.00, abs=EXACT_TOLERANCE)

    def test_모든_거래일에_금리가_있다(self) -> None:
        """
        목적: 정렬 뒤에 빈 칸이 남지 않음을 고정한다

        Given: 결측이 있는 원지표
        When: 금리 계열을 만든다
        Then: 달력 길이만큼 값이 있고 결측이 없다
        """
        # Given
        calendar = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]))
        tbill = _series([("2020-01-01", 3.00)])
        cd91 = _series([("2020-01-01", 2.00)])

        # When
        actual = build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config())

        # Then
        assert len(actual.rp) == len(calendar)
        assert not actual.rp.isna().any()
        assert not actual.parking.isna().any()

    def test_첫날_이전에_값이_없으면_거부한다(self) -> None:
        """
        목적: 조용히 채우지 않는다는 계약을 고정한다

        Given: 달력 첫날보다 늦게 시작하는 원지표
        When: 금리 계열을 만든다
        Then: ValueError — 하한으로 채우면 그 구간이 통째로 하한 금리가 된다
        """
        # Given
        calendar = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03"]))
        tbill = _series([("2020-01-03", 3.00)])
        cd91 = _series([("2020-01-01", 2.00)])

        # When / Then
        with pytest.raises(ValueError, match="T-bill"):
            build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config())

    def test_달력이_비면_거부한다(self) -> None:
        """
        목적: 빈 입력을 즉시 막는다

        Given: 빈 달력
        When: 금리 계열을 만든다
        Then: ValueError
        """
        # Given
        tbill = _series([("2020-01-01", 3.00)])
        cd91 = _series([("2020-01-01", 2.00)])

        # When / Then
        with pytest.raises(ValueError, match="마스터 달력"):
            build_rate_series(pd.DatetimeIndex([]), tbill=tbill, cd91=cd91, config=_config())

    def test_하한이_계열_전체에_걸린다(self) -> None:
        """
        목적: 하한이 축으로 작동함을 고정한다

        Given: 제로금리 구간의 원지표
        When: 하한을 다르게 두 번 만든다
        Then: 결과가 각 하한값이다
        """
        # Given
        calendar = pd.DatetimeIndex(pd.to_datetime(["2020-01-02"]))
        tbill = _series([("2020-01-01", 0.10)])
        cd91 = _series([("2020-01-01", 0.60)])

        # When
        low = build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config(rp=0.10, parking=0.25))
        high = build_rate_series(calendar, tbill=tbill, cd91=cd91, config=_config(rp=0.70, parking=0.75))

        # Then
        assert low.rp.iloc[0] == pytest.approx(0.10, abs=EXACT_TOLERANCE)
        assert high.rp.iloc[0] == pytest.approx(0.70, abs=EXACT_TOLERANCE)
        assert low.parking.iloc[0] == pytest.approx(0.30, abs=EXACT_TOLERANCE)
        assert high.parking.iloc[0] == pytest.approx(0.75, abs=EXACT_TOLERANCE)
