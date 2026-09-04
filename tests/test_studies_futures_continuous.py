"""비율 조정 연속 시계열의 계약

여기서 조용히 틀리면 **그 위의 모든 측정이 무효가 된다.** 이으는 방식이 잘못되면
베이시스가 수익률로 들어가고, 그것은 눈으로 보이지 않는다. 그래서 고정하는 것은 둘이다.

1. **조정 항등식** — 조정 계열의 일간 수익률이 «그날 들고 있던 계약의 실제 수익률» 과 같다
2. **미래 참조 없음** — 미결제약정 역전은 **확인한 다음 거래일**에 집행된다

합성 데이터만 쓴다. 실제 시세에 의존하면 데이터를 갱신할 때마다 테스트가 깨진다.
"""

import pandas as pd
import pytest

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
)
from verify_lab.studies.futures_leverage.constants import (
    ROLL_DAYS_BEFORE_EXPIRY,
    ROLL_RULE_DAYS_BEFORE_EXPIRY,
    ROLL_RULE_OPEN_INTEREST,
)
from verify_lab.studies.futures_leverage.continuous import (
    COL_ADJUSTED_SETTLE,
    COL_LAST_DATE,
    COL_SEGMENT,
    build_continuous_series,
    build_contract_calendar,
    plan_rolls,
)

# 두 계약의 가격 차이 (베이시스). 조정이 없으면 이 값이 이음매에서 수익률로 새어 들어간다
BASIS = 3.0

# 합성 계열의 일간 수익률. 계약마다 같게 두어 조정 항등식을 눈으로 확인할 수 있게 한다
DAILY_STEP = 1.0


def _make_frame(
    *,
    days: int = 30,
    near_expiry_index: int = 14,
    crossover_index: int = 9,
) -> pd.DataFrame:
    """계약 두 개가 겹치는 합성 선물 시세를 만든다.

    근월물 `AAA` 는 `near_expiry_index` 일에 만기가 되고 차월물 `BBB` 는 끝까지 산다.
    차월물 가격은 근월물보다 `BASIS` 만큼 높아 **이음매에서 조정이 안 되면 그만큼 튄다.**
    미결제약정은 `crossover_index` 일에 역전된다.

    Args:
        days: 전체 거래일 수
        near_expiry_index: 근월물의 마지막 거래일 인덱스
        crossover_index: 차월물 미결제약정이 근월물을 넘어서는 날의 인덱스

    Returns:
        선물 시세 스키마의 DataFrame
    """
    dates = pd.bdate_range("2020-01-01", periods=days)
    rows: list[dict[str, object]] = []

    for index, day in enumerate(dates):
        base_price = 100.0 + DAILY_STEP * index

        if index <= near_expiry_index:
            rows.append(
                {
                    COL_DATE: day,
                    COL_CONTRACT: "AAA",
                    COL_CONTRACT_NAME: "테스트 근월물",
                    COL_OPEN: base_price,
                    COL_HIGH: base_price,
                    COL_LOW: base_price,
                    COL_CLOSE: base_price,
                    COL_VOLUME: 1_000,
                    COL_SETTLE: base_price,
                    COL_OPEN_INTEREST: 1_000 - index * 50,
                    COL_SPOT: base_price - 0.5,
                }
            )

        rows.append(
            {
                COL_DATE: day,
                COL_CONTRACT: "BBB",
                COL_CONTRACT_NAME: "테스트 차월물",
                COL_OPEN: base_price + BASIS,
                COL_HIGH: base_price + BASIS,
                COL_LOW: base_price + BASIS,
                COL_CLOSE: base_price + BASIS,
                COL_VOLUME: 100,
                COL_SETTLE: base_price + BASIS,
                COL_OPEN_INTEREST: 100 + index * 80 if index >= crossover_index else 100,
                COL_SPOT: base_price - 0.5,
            }
        )

    return pd.DataFrame(rows).sort_values([COL_DATE, COL_CONTRACT]).reset_index(drop=True)


class TestContractCalendar:
    """계약 달력의 계약."""

    def test_calendar_is_sorted_by_expiry(self) -> None:
        """
        목적: 달력이 만기 오름차순임을 고정한다. 롤 순서가 여기서 정해진다.

        Given: 근월물과 차월물이 섞인 시세
        When: 달력을 만든다
        Then: 만기가 이른 계약이 먼저 온다
        """
        # Given / When
        calendar = build_contract_calendar(_make_frame())

        # Then
        assert calendar[COL_CONTRACT].tolist() == ["AAA", "BBB"]
        assert calendar[COL_LAST_DATE].is_monotonic_increasing

    def test_empty_frame_raises(self) -> None:
        """
        목적: 빈 입력에 조용히 빈 결과를 돌려주지 않음을 고정한다.

        Given: 빈 DataFrame
        When: 달력을 만든다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="비어 있습니다"):
            build_contract_calendar(pd.DataFrame())


class TestRollTiming:
    """롤 시점 판정의 계약 — 여기가 미래 참조가 들어오는 자리다."""

    def test_open_interest_rule_executes_the_day_after_the_decision(self) -> None:
        """
        목적: **미결제약정 역전은 확인한 다음 거래일에 집행**됨을 고정한다.

        KRX 미결제약정은 장 마감 후 공표된다. 판정일 종가에 옮기면 그 시점에 알 수 없는
        정보로 주문을 내는 것이며, 이 검증 전체가 무효가 된다.

        Given: 9일째에 미결제약정이 역전되는 시세
        When: 미결제약정 규칙으로 롤 일정을 만든다
        Then: 집행일이 판정일보다 정확히 한 거래일 뒤다
        """
        # Given
        df = _make_frame(crossover_index=9)

        # When
        events = plan_rolls(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert len(events) == 1
        event = events[0]
        assert event.decision_date is not None
        trading_days = sorted(df[COL_DATE].unique())
        decision_position = trading_days.index(event.decision_date)
        assert event.execution_date == trading_days[decision_position + 1]
        assert not event.fallback

    def test_open_interest_rule_falls_back_when_never_crossed(self) -> None:
        """
        목적: 미결제약정이 끝내 역전되지 않아도 롤이 일어나고 **그 사실이 표시**됨을 고정한다.

        조용히 최종거래일로 미루면 「규칙이 집어낸 롤」과 구분되지 않는다.

        Given: 역전이 일어나지 않는 시세
        When: 미결제약정 규칙으로 롤 일정을 만든다
        Then: 최종거래일에 집행되고 fallback 이 True 다
        """
        # Given
        df = _make_frame(crossover_index=999)

        # When
        events = plan_rolls(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert len(events) == 1
        assert events[0].fallback is True
        assert events[0].decision_date is None

    def test_crossover_on_the_last_overlapping_day_is_not_a_decision(self) -> None:
        """
        목적: **마지막 겹치는 날의 역전을 「판정」으로 기록하지 않음**을 고정한다.

        그날 종가에는 그날의 미결제약정을 알 수 없다. 판정일로 기록하면 그것이 곧
        미래 참조다. 실제로는 계약이 만기라 어차피 옮겨야 하는 «만기가 강제한 롤» 이므로
        판정일을 비우고 `fallback` 으로 표시한다.

        **실데이터에서 실제로 나왔다** — 코스닥150 49건 중 2건이 여기 해당했다.

        Given: 근월물 만기 당일에야 미결제약정이 역전되는 시세
        When: 미결제약정 규칙으로 롤 일정을 만든다
        Then: 판정일이 비어 있고 fallback 이 True 다
        """
        # Given
        df = _make_frame(near_expiry_index=14, crossover_index=14)

        # When
        events = plan_rolls(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert len(events) == 1
        assert events[0].decision_date is None, "만기 당일 역전을 판정으로 기록하면 미래 참조입니다"
        assert events[0].fallback is True

    def test_live_contract_at_data_end_is_not_rolled_out_of(self) -> None:
        """
        목적: **데이터 끝에 아직 살아 있는 계약에서는 롤하지 않음**을 고정한다.

        살아 있는 계약은 「마지막 거래일」이 곧 데이터의 끝이라, 만기 기준 규칙이
        데이터의 끝을 만기로 착각해 롤 날짜를 앞으로 당긴다. 그러면 집행일이 역전돼
        구간이 뒤집힌다 — **실데이터에서 시작일이 종료일보다 하루 뒤인 구간이 실제로 생겼다.**

        Given: 만기가 오지 않은 계약이 둘 남아 있는 시세
        When: 만기 전 고정 규칙으로 롤 일정을 만든다
        Then: 살아 있는 계약에서는 롤하지 않아 집행일이 시간순이다
        """
        # Given — BBB·CCC 둘 다 데이터 끝까지 산다
        df = _make_frame(days=30, near_expiry_index=14)
        tail = df[df[COL_CONTRACT] == "BBB"].copy()
        tail[COL_CONTRACT] = "CCC"
        tail[COL_CONTRACT_NAME] = "테스트 초원월물"
        tail[COL_SETTLE] = tail[COL_SETTLE] + BASIS
        tail[COL_CLOSE] = tail[COL_SETTLE]
        tail[COL_OPEN_INTEREST] = 50
        df = pd.concat([df, tail], ignore_index=True).sort_values([COL_DATE, COL_CONTRACT]).reset_index(drop=True)

        # When
        events = plan_rolls(df, ROLL_RULE_DAYS_BEFORE_EXPIRY)

        # Then
        execution_dates = [event.execution_date for event in events]
        assert execution_dates == sorted(execution_dates), f"집행일이 시간순이 아닙니다: {execution_dates}"
        assert len(execution_dates) == len(set(execution_dates)), "같은 날 두 번 롤했습니다"
        assert all(event.from_contract != "CCC" for event in events), "살아 있는 계약에서 롤했습니다"

    def test_expiry_rule_rolls_fixed_days_before_expiry(self) -> None:
        """
        목적: 만기 전 고정 규칙의 집행일이 만기에서 정확히 N거래일 앞임을 고정한다.

        Given: 근월물 만기가 정해진 시세
        When: 만기 전 고정 규칙으로 롤 일정을 만든다
        Then: 집행일이 만기에서 N거래일 앞이고 판정일이 없다
        """
        # Given
        df = _make_frame(near_expiry_index=14)
        expiry = df.loc[df[COL_CONTRACT] == "AAA", COL_DATE].max()

        # When
        events = plan_rolls(df, ROLL_RULE_DAYS_BEFORE_EXPIRY)

        # Then
        assert len(events) == 1
        assert events[0].decision_date is None
        overlap = sorted(df.loc[df[COL_CONTRACT] == "AAA", COL_DATE].unique())
        assert overlap.index(expiry) - overlap.index(events[0].execution_date) == ROLL_DAYS_BEFORE_EXPIRY

    def test_two_rules_choose_different_dates(self) -> None:
        """
        목적: 두 규칙이 실제로 다른 날을 고름을 고정한다 (측정의 원칙 1).

        같은 날을 고르면 두 벌을 내는 뜻이 없어지므로, 차이가 관측되는 것 자체가 계약이다.

        Given: 역전이 만기보다 훨씬 이른 시세
        When: 두 규칙으로 각각 롤 일정을 만든다
        Then: 집행일이 다르다
        """
        # Given
        df = _make_frame(near_expiry_index=14, crossover_index=3)

        # When
        by_interest = plan_rolls(df, ROLL_RULE_OPEN_INTEREST)
        by_expiry = plan_rolls(df, ROLL_RULE_DAYS_BEFORE_EXPIRY)

        # Then
        assert by_interest[0].execution_date != by_expiry[0].execution_date

    def test_unknown_rule_raises(self) -> None:
        """
        목적: 모르는 규칙으로 조용히 계산하지 않음을 고정한다.

        Given: 목록에 없는 규칙 이름
        When: 롤 일정을 만든다
        Then: ValueError 를 던진다
        """
        # Given / When / Then
        with pytest.raises(ValueError, match="모르는 롤 규칙입니다"):
            plan_rolls(_make_frame(), "아무거나")

    def test_out_of_range_adjustment_factor_raises(self) -> None:
        """
        목적: 조정계수가 타당 범위를 벗어나면 막힘을 고정한다.

        근월물과 차월물의 차이는 3개월치 캐리라 몇 %를 넘지 않는다. 크게 벌어졌다면
        계약을 잘못 짝지었거나 정산가가 잘못 들어온 것이다.

        Given: 차월물 정산가가 근월물의 두 배인 시세
        When: 롤 일정을 만든다
        Then: ValueError 를 던진다
        """
        # Given
        df = _make_frame()
        is_far = df[COL_CONTRACT] == "BBB"
        df.loc[is_far, COL_SETTLE] = df.loc[is_far, COL_SETTLE] * 2

        # When / Then
        with pytest.raises(ValueError, match="조정계수가 타당 범위를 벗어났습니다"):
            plan_rolls(df, ROLL_RULE_OPEN_INTEREST)


class TestContinuousSeries:
    """연속 계열의 계약 — 조정 항등식이 이 검증의 뼈대다."""

    @pytest.mark.parametrize("rule", [ROLL_RULE_OPEN_INTEREST, ROLL_RULE_DAYS_BEFORE_EXPIRY])
    def test_adjusted_returns_match_the_held_contract(self, rule: str) -> None:
        """
        목적: **조정 계열의 일간 수익률이 그날 들고 있던 계약의 실제 수익률과 같음**을 고정한다.

        이 검증의 핵심 항등식이다. 어긋나면 베이시스가 수익률로 새어 들어간 것이고,
        그 위의 모든 비교가 무효가 된다.

        Given: 두 계약이 겹치는 합성 시세
        When: 연속 계열을 만든다
        Then: 조정 계열의 일간 수익률이 «그날 활성 계약의 원본 수익률» 과 일치한다
        """
        # Given
        df = _make_frame()

        # When
        series, _ = build_continuous_series(df, rule)

        # Then
        adjusted_return = series[COL_ADJUSTED_SETTLE].pct_change()

        raw = df.set_index([COL_DATE, COL_CONTRACT])[COL_SETTLE]
        expected: list[float] = []
        for position in range(1, len(series)):
            today = series.iloc[position]
            yesterday = series.iloc[position - 1]
            # 그날 들고 있던 계약으로 전날 대비 수익률을 낸다.
            # 롤 다음 날이면 새 계약의 전날 가격을 쓴다 — 그것이 실제로 겪는 수익률이다
            contract = today[COL_CONTRACT]
            expected.append(float(raw[(today[COL_DATE], contract)] / raw[(yesterday[COL_DATE], contract)] - 1))

        assert adjusted_return.iloc[1:].tolist() == pytest.approx(expected, abs=1e-12)

    def test_seam_has_no_basis_jump(self) -> None:
        """
        목적: 이음매에서 베이시스가 수익률로 새지 않음을 고정한다.

        조정을 안 하면 롤 다음 날 수익률에 `BASIS` 만큼의 가짜 점프가 생긴다.

        Given: 차월물이 근월물보다 비싼 시세
        When: 연속 계열을 만든다
        Then: 롤 다음 날의 수익률이 평상시와 같은 크기다
        """
        # Given
        df = _make_frame()

        # When
        series, events = build_continuous_series(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        returns = series[COL_ADJUSTED_SETTLE].pct_change()
        execution_position = int(series.index[series[COL_DATE] == events.iloc[0]["ExecutionDate"]][0])
        seam_return = returns.iloc[execution_position + 1]
        neighbours = returns.iloc[2:execution_position].tolist()

        assert seam_return == pytest.approx(max(neighbours), abs=0.005), "롤 다음 날 수익률이 평상시와 다릅니다 — 베이시스가 새어 들어갔습니다"

    def test_active_contract_switches_after_the_execution_date(self) -> None:
        """
        목적: **집행일까지 근월물을 들고 있음**을 고정한다.

        집행일에 이미 차월물로 바뀌어 있으면 그날 하루치 수익률이 근월물이 아니라
        차월물에서 나오게 되어 실제와 어긋난다.

        Given: 롤이 한 번 있는 시세
        When: 연속 계열을 만든다
        Then: 집행일의 활성 계약은 근월물이고 그다음 거래일부터 차월물이다
        """
        # Given
        df = _make_frame()

        # When
        series, events = build_continuous_series(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        execution_date = pd.Timestamp(str(events["ExecutionDate"].iloc[0]))
        on_execution = series[series[COL_DATE] == execution_date][COL_CONTRACT].tolist()
        after = series[series[COL_DATE] > execution_date][COL_CONTRACT].tolist()

        assert on_execution[0] == "AAA"
        assert after[0] == "BBB"

    def test_series_covers_every_trading_day_exactly_once(self) -> None:
        """
        목적: 연속 계열이 거래일마다 정확히 한 행임을 고정한다 (표본 보존).

        Given: 두 계약이 겹치는 시세
        When: 연속 계열을 만든다
        Then: 날짜에 중복이 없고 원본의 거래일을 모두 덮는다
        """
        # Given
        df = _make_frame()

        # When
        series, _ = build_continuous_series(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert series[COL_DATE].duplicated().sum() == 0
        assert set(series[COL_DATE]) == set(df[COL_DATE])

    def test_adjusted_prices_stay_positive(self) -> None:
        """
        목적: 조정가가 전 구간에서 양수임을 고정한다.

        비율 조정에서는 자동으로 참이지만, 차분 조정으로 바뀌면 과거 가격이 음수가 된다.
        구현이 바뀌었을 때 이 테스트가 그것을 잡는다.

        Given: 두 계약이 겹치는 시세
        When: 연속 계열을 만든다
        Then: 조정가가 모두 0보다 크다
        """
        # Given
        df = _make_frame()

        # When
        series, _ = build_continuous_series(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert (series[COL_ADJUSTED_SETTLE] > 0).all()

    def test_last_segment_is_unadjusted(self) -> None:
        """
        목적: 마지막 구간의 조정가가 원본과 같음을 고정한다.

        비율 조정은 **과거를 현재에 맞춘다.** 현재 구간까지 건드리면 지금 화면에 뜨는
        가격과 어긋나 사용자가 대조할 수 없다.

        Given: 롤이 한 번 있는 시세
        When: 연속 계열을 만든다
        Then: 마지막 구간에서 조정가와 원본 정산가가 같다
        """
        # Given
        df = _make_frame()

        # When
        series, _ = build_continuous_series(df, ROLL_RULE_OPEN_INTEREST)

        # Then
        last = series[series[COL_SEGMENT] == series[COL_SEGMENT].max()]
        assert last[COL_ADJUSTED_SETTLE].tolist() == pytest.approx(last[COL_SETTLE].tolist(), abs=1e-12)


class TestLookAhead:
    """미래 참조 감시 — 뒤를 잘라도 앞의 판정이 달라지지 않아야 한다."""

    def test_roll_dates_are_stable_under_truncation(self, assert_stable_under_truncation: object) -> None:
        """
        목적: 뒤를 잘라낸 입력에서도 **앞 구간의 롤 집행일이 그대로**임을 고정한다.

        미결제약정 규칙은 판정일까지의 정보만 쓰므로, 뒤에 무엇이 있든 롤 날짜가 달라지면 안 된다.

        Given: 계약이 통째로 들어 있는 구간까지 자른 입력
        When: 두 입력으로 각각 롤 일정을 만든다
        Then: 겹치는 구간의 집행일이 같다
        """
        # Given
        df = _make_frame(days=40, near_expiry_index=14, crossover_index=9)
        cut_date = df[COL_DATE].unique()[24]
        truncated = df[df[COL_DATE] <= cut_date]

        # When
        whole_events = plan_rolls(df, ROLL_RULE_OPEN_INTEREST)
        truncated_events = plan_rolls(truncated, ROLL_RULE_OPEN_INTEREST)

        # Then
        assert truncated_events, "자른 입력에도 롤이 하나는 있어야 비교가 성립합니다"
        for index, event in enumerate(truncated_events):
            assert (
                event.execution_date == whole_events[index].execution_date
            ), "뒤를 잘라낸 입력에서 롤 날짜가 달라졌습니다 — 미래 데이터를 참조하고 있습니다"
            assert event.decision_date == whole_events[index].decision_date
