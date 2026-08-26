"""사양서 §12.1 축별 단독 검사의 계약을 고정한다.

**최적 조합을 찾는 것이 아니다.** §12.1 이 "전수 탐색 금지 — 4×4×3×4×4×3×3 = 6,912가지를 돌려
최고 조합을 고르면 그것이 과최적화" 라고 못 박았다. 이 계층이 답하는 것은 하나다 —
**기본 설정에서 나온 결론이 축을 옮겨도 유지되는가.**

핵심 계약은 다섯 가지다.

- **축값은 `constants.py` 의 `*_CHOICES` 에서 나온다.** 손으로 복제하면 사양서 §12 와 조용히 갈라진다
- **한 번에 한 축만 바뀐다.** 두 축이 함께 움직이면 어느 것이 결과를 만들었는지 알 수 없다
- **기본 설정 실행은 한 번만 돈다.** 8축이 전부 기본값을 포함하므로 28 축값이 고유 21회다
- **판정은 불리언의 뒤집힘 여부다.** 금액의 크기로 우열을 매기면 그 순간 「좋은 값 고르기」가 된다
- **N 축만 네 실행 전부에 돈다** (결정 C105). §15.3 #8 과 §18 의 1차 목적이 N×경로를 요구한다
"""

from verify_lab.strategy.grid.constants import (
    ALLOCATION_SPREAD_CHOICES,
    AXIS_ALLOCATION_SPREAD,
    AXIS_EXCHANGE_SPREAD,
    AXIS_GROWTH_RATE,
    AXIS_LOOKBACK_YEARS,
    AXIS_MIN_RANGE_WIDTH,
    AXIS_PARKING_FLOOR,
    AXIS_RP_FLOOR,
    AXIS_SLOT_CAP_RATIO,
    BENCHMARK_BUY_HOLD,
    BENCHMARK_KRW_PARKING,
    BENCHMARK_SPLIT_BUY_HOLD,
    EXCHANGE_SPREAD_RATE_CHOICES,
    EXECUTION_ETF_1X,
    EXECUTION_ETF_2X,
    EXECUTION_EXCHANGE_FULL,
    EXECUTION_EXCHANGE_MATCHED,
    GROWTH_RATE_CHOICES,
    LOOKBACK_YEAR_CHOICES,
    MIN_RANGE_WIDTH_CHOICES,
    PARKING_FLOOR_RATE_CHOICES,
    RP_FLOOR_RATE_CHOICES,
    SLOT_CAP_RATIO_CHOICES,
)
from verify_lab.strategy.grid.sweep import (
    CONCLUSION_BEAT_BUY_HOLD,
    CONCLUSION_BEAT_PARKING,
    CONCLUSION_BEAT_SPLIT_BUY_HOLD,
    CONCLUSION_INTEREST_MAJORITY,
    CONCLUSION_SHALLOW_DRAWDOWN,
    SweepRow,
    axis_verdicts,
    build_axes,
    build_executions,
    conclusion_flags,
    path_rank_verdicts,
    plan_runs,
)


def _row(
    *,
    execution: str = EXECUTION_EXCHANGE_FULL,
    axis: str = AXIS_LOOKBACK_YEARS,
    value_label: str = "3",
    is_default: bool = True,
    final_assets: float = 178_494_280.0,
    max_drawdown: float = -0.0810,
    total_return: float = 78_494_280.0,
    interest_after_tax: float = 50_163_902.0,
    calmar: float | None = 0.339,
    sharpe: float | None = 0.122,
    gaps: dict[str, float] | None = None,
) -> SweepRow:
    """검사용 축 행 하나. 기본값은 환전 2005~ 기본 설정의 실측값이다."""
    return SweepRow(
        execution=execution,
        axis=axis,
        value_label=value_label,
        is_default=is_default,
        in_spec=True,
        final_assets=final_assets,
        total_return_rate=final_assets / 100_000_000.0 - 1.0,
        cagr=0.0275,
        max_drawdown=max_drawdown,
        calmar=calmar,
        volatility=0.0312,
        sharpe=sharpe,
        sortino=0.182,
        deployment_mean=0.3587,
        turnover_per_year=29.22,
        total_return=total_return,
        interest_after_tax=interest_after_tax,
        grid_excess_share_of_total_return=0.2494,
        grid_excess_share_of_trading=0.6909,
        benchmark_gaps=gaps
        if gaps is not None
        else {
            BENCHMARK_BUY_HOLD: 6_182_627.0,
            BENCHMARK_SPLIT_BUY_HOLD: -3_094_074.0,
            BENCHMARK_KRW_PARKING: 20_940_600.0,
        },
        red_flags_triggered=1,
    )


class TestBuildAxes:
    """축 정의 — 값을 손으로 적지 않는다."""

    def test_축값이_사양서_상수와_정확히_같다(self) -> None:
        """
        목적: 축 정의를 복제하면 사양서 §12 의 검사 범위와 조용히 갈라진다

        Given / When: 축 정의
        Then: 축마다 값 목록이 대응하는 `*_CHOICES` 와 순서까지 같다
        """
        # Given / When
        axes = {item.key: item for item in build_axes()}

        # Then
        assert axes[AXIS_LOOKBACK_YEARS].values == LOOKBACK_YEAR_CHOICES
        assert axes[AXIS_GROWTH_RATE].values == GROWTH_RATE_CHOICES
        assert axes[AXIS_ALLOCATION_SPREAD].values == ALLOCATION_SPREAD_CHOICES
        assert axes[AXIS_MIN_RANGE_WIDTH].values == MIN_RANGE_WIDTH_CHOICES
        assert axes[AXIS_SLOT_CAP_RATIO].values == SLOT_CAP_RATIO_CHOICES
        assert axes[AXIS_RP_FLOOR].values == RP_FLOOR_RATE_CHOICES
        assert axes[AXIS_PARKING_FLOOR].values == PARKING_FLOOR_RATE_CHOICES
        assert axes[AXIS_EXCHANGE_SPREAD].values == EXCHANGE_SPREAD_RATE_CHOICES

    def test_사양서_축_일곱과_추가_축_하나다(self) -> None:
        """
        목적: 결정 C106 — 스프레드 축은 사양서 §12 파라미터 표에 없다.
              출처를 표기하지 않으면 사양서가 요구한 검사와 섞인다

        Given / When: 축 정의
        Then: 8축이고 그중 사양서 축이 7개, 추가 축이 스프레드 하나다
        """
        # Given / When
        axes = build_axes()

        # Then
        assert len(axes) == 8
        assert sum(1 for item in axes if item.in_spec) == 7
        assert [item.key for item in axes if not item.in_spec] == [AXIS_EXCHANGE_SPREAD]

    def test_기본값이_축값_목록_안에_있다(self) -> None:
        """
        목적: 기본값이 축에 없으면 「기본 설정 대비」 비교의 기준선이 사라진다

        Given / When: 축 정의
        Then: 축마다 기본값이 값 목록에 들어 있다
        """
        # Given / When / Then
        for axis in build_axes():
            assert axis.default in axis.values, f"{axis.name} 의 기본값이 검사 범위 밖입니다"

    def test_축값_합이_스물여덟이다(self) -> None:
        """
        목적: 사양서 §12.1 의 「약 25회」에 추가 축 3회를 더한 수다

        Given / When: 축 정의
        Then: 축값의 총합이 28 이고 사양서 축만 세면 25 다
        """
        # Given / When
        axes = build_axes()

        # Then
        assert sum(len(item.values) for item in axes) == 28
        assert sum(len(item.values) for item in axes if item.in_spec) == 25


class TestPlanRuns:
    """실행 계획 — 중복을 지우고 한 번에 한 축만 바꾼다."""

    def test_기본_설정이_한_번만_돈다(self) -> None:
        """
        목적: 8축이 전부 기본값을 포함하므로 그대로 돌리면 같은 실행을 8번 한다

        Given: 축 정의와 실행 정의
        When: 실행 계획을 만든다
        Then: 환전 2005~ 의 기본 설정 실행이 정확히 하나다
        """
        # Given
        axes, executions = build_axes(), build_executions()

        # When
        runs = plan_runs(axes, executions)

        # Then
        defaults = [item for item in runs if item.execution == EXECUTION_EXCHANGE_FULL and item.is_default]
        assert len(defaults) == 1, f"기본 설정이 {len(defaults)}번 돕니다 - 중복이 지워지지 않았습니다"

    def test_고유_실행이_서른셋이다(self) -> None:
        """
        목적: 환전 2005~ 21회 + N축 3경로 12회 (결정 C105)

        Given: 축 정의와 실행 정의
        When: 실행 계획을 만든다
        Then: 총 33회이고 환전 2005~ 가 21회다
        """
        # Given
        axes, executions = build_axes(), build_executions()

        # When
        runs = plan_runs(axes, executions)

        # Then
        assert len(runs) == 33
        assert sum(1 for item in runs if item.execution == EXECUTION_EXCHANGE_FULL) == 21

    def test_N_축만_네_실행_전부에_돈다(self) -> None:
        """
        목적: 결정 C105 — §15.3 #8 은 N×경로가 있어야 판정된다.
              나머지 축까지 4배로 늘리면 §12.1 이 경계한 「많이 돌려 좋은 것 고르기」가 된다

        Given: 축 정의와 실행 정의
        When: 실행 계획을 만든다
        Then: 환전 2005~ 밖의 실행은 전부 N 축이고 실행마다 4회씩이다
        """
        # Given
        axes, executions = build_axes(), build_executions()

        # When
        runs = plan_runs(axes, executions)

        # Then
        others = [item for item in runs if item.execution != EXECUTION_EXCHANGE_FULL]
        assert {item.axis for item in others} == {AXIS_LOOKBACK_YEARS}
        for execution in (EXECUTION_EXCHANGE_MATCHED, EXECUTION_ETF_1X, EXECUTION_ETF_2X):
            assert sum(1 for item in others if item.execution == execution) == 4

    def test_한_번에_한_축만_바뀐다(self) -> None:
        """
        목적: 두 축이 함께 움직이면 어느 것이 결과를 만들었는지 알 수 없다

        Given: 축 정의와 실행 정의
        When: 실행 계획을 만든다
        Then: 기본 설정이 아닌 실행은 설정이 기본과 **정확히 한 필드**만 다르다
        """
        # Given
        axes, executions = build_axes(), build_executions()
        runs = plan_runs(axes, executions)
        baseline = next(item for item in runs if item.execution == EXECUTION_EXCHANGE_FULL and item.is_default)

        # When
        changed = [_diff_fields(item.settings, baseline.settings) for item in runs if not item.is_default]

        # Then
        assert changed, "비교할 비기본 실행이 없습니다"
        assert all(len(fields) == 1 for fields in changed), f"두 축이 함께 움직였습니다: {changed}"

    def test_모든_비교_실행이_같은_기간을_겪는다(self) -> None:
        """
        목적: N 축의 순위 비교는 세 경로가 **같은 시작일**이라야 성립한다.
              기간이 다르면 순위가 기간에서 나온 건지 경로에서 나온 건지 알 수 없다 (결정 C72)

        Given: 실행 정의
        When: 환전 2005~ 를 뺀 세 실행의 시작일을 본다
        Then: 셋이 전부 같다
        """
        # Given / When
        starts = {
            item.start_date
            for item in build_executions()
            if item.key in (EXECUTION_EXCHANGE_MATCHED, EXECUTION_ETF_1X, EXECUTION_ETF_2X)
        }

        # Then
        assert len(starts) == 1, f"비교 실행의 시작일이 갈립니다: {starts}"


def _diff_fields(actual: dict[str, object], baseline: dict[str, object]) -> list[str]:
    """기본 설정과 다른 필드 이름을 낸다."""
    return sorted(key for key in baseline if actual[key] != baseline[key])


class TestConclusionFlags:
    """결론 판정 — 불리언이지 금액이 아니다."""

    def test_분할매수에_지면_거짓이다(self) -> None:
        """
        목적: §13.3 의 판정. 실측 기본 설정은 −3,094,074원으로 진다

        Given: 분할매수 대비 음수 격차
        When: 결론 불리언을 낸다
        Then: 「분할매수를 이긴다」가 거짓이다
        """
        # Given
        row = _row()

        # When
        flags = conclusion_flags(row)

        # Then
        assert flags[CONCLUSION_BEAT_SPLIT_BUY_HOLD] is False
        assert flags[CONCLUSION_BEAT_BUY_HOLD] is True
        assert flags[CONCLUSION_BEAT_PARKING] is True

    def test_MDD_가_십_퍼센트보다_얕으면_참이다(self) -> None:
        """
        목적: §15.3 #2. 실측 네 경로가 전부 여기 걸린다

        Given: MDD −8.10%
        When: 결론 불리언을 낸다
        Then: 「MDD 가 얕다」가 참이다
        """
        # Given / When
        flags = conclusion_flags(_row(max_drawdown=-0.0810))
        deeper = conclusion_flags(_row(max_drawdown=-0.1200))

        # Then
        assert flags[CONCLUSION_SHALLOW_DRAWDOWN] is True
        assert deeper[CONCLUSION_SHALLOW_DRAWDOWN] is False

    def test_이자가_총수익의_절반을_넘으면_참이다(self) -> None:
        """
        목적: 실측에서 세후 이자가 총수익의 63.9% 다. 이 구조가 축을 옮겨도 유지되는지 본다

        Given: 총수익 7,849만원 중 이자 5,016만원
        When: 결론 불리언을 낸다
        Then: 참이다
        """
        # Given / When
        flags = conclusion_flags(_row())

        # Then
        assert flags[CONCLUSION_INTEREST_MAJORITY] is True

    def test_총수익이_0_이하면_비중_판정이_None_이다(self) -> None:
        """
        목적: 결정 C91 — 음수 분모로 나누면 비중의 부호가 조용히 뒤집혀
              "이자 기여가 없다"로 읽힌다

        Given: 총수익이 0 인 행
        When: 결론 불리언을 낸다
        Then: 이자 비중 판정이 `None` 이다
        """
        # Given / When
        flags = conclusion_flags(_row(total_return=0.0))

        # Then
        assert flags[CONCLUSION_INTEREST_MAJORITY] is None


class TestAxisVerdicts:
    """축 판정 — 결론이 뒤집혔는가만 답한다."""

    def test_전_축값에서_같으면_견고하다(self) -> None:
        """
        목적: 루트 CLAUDE.md 「측정의 원칙」 7 — 뒤집히지 않으면 그 사실을 적는다

        Given: 네 축값 전부 분할매수에 지는 행
        When: 축 판정을 낸다
        Then: 「분할매수를 이긴다」 판정이 안정이다
        """
        # Given
        rows = [_row(value_label=str(value), is_default=value == 3) for value in LOOKBACK_YEAR_CHOICES]

        # When
        verdicts = {
            (item.axis, item.conclusion): item
            for item in axis_verdicts(rows)
            if item.execution == EXECUTION_EXCHANGE_FULL
        }

        # Then
        assert verdicts[(AXIS_LOOKBACK_YEARS, CONCLUSION_BEAT_SPLIT_BUY_HOLD)].stable is True

    def test_한_축값에서라도_달라지면_뒤집힘이다(self) -> None:
        """
        목적: 파라미터 하나를 옮겼을 때 결론이 흔들리면 **그 사실 자체가 결과**다.
              `.claude/rules/strategy.md` 가 "흔들림은 그 값이 좋다가 아니라 표본이
              그 지점을 특정할 만큼 크지 않다는 신호" 라고 규정했다

        Given: 한 축값에서만 분할매수를 이기는 행 묶음
        When: 축 판정을 낸다
        Then: 판정이 뒤집힘이고 어느 축값인지가 근거에 남는다
        """
        # Given
        rows = [
            _row(value_label="1", is_default=False),
            _row(value_label="3", is_default=True),
            _row(
                value_label="5",
                is_default=False,
                gaps={
                    BENCHMARK_BUY_HOLD: 1.0,
                    BENCHMARK_SPLIT_BUY_HOLD: 1.0,
                    BENCHMARK_KRW_PARKING: 1.0,
                },
            ),
            _row(value_label="7", is_default=False),
        ]

        # When
        verdict = next(
            item
            for item in axis_verdicts(rows)
            if item.axis == AXIS_LOOKBACK_YEARS and item.conclusion == CONCLUSION_BEAT_SPLIT_BUY_HOLD
        )

        # Then
        assert verdict.stable is False
        assert "5" in verdict.detail, "어느 축값에서 갈렸는지가 근거에 없습니다"

    def test_판정_불가가_섞이면_판정_불가다(self) -> None:
        """
        목적: 결정 C95 — "검사했는데 괜찮았다"와 "애초에 판정할 수 없었다"를 구분한다

        Given: 한 축값의 총수익이 0 이라 이자 비중을 낼 수 없는 묶음
        When: 축 판정을 낸다
        Then: 안정 여부가 `None` 이다
        """
        # Given
        rows = [_row(value_label="1"), _row(value_label="3", total_return=0.0)]

        # When
        verdict = next(
            item
            for item in axis_verdicts(rows)
            if item.axis == AXIS_LOOKBACK_YEARS and item.conclusion == CONCLUSION_INTEREST_MAJORITY
        )

        # Then
        assert verdict.stable is None


class TestPathRankVerdicts:
    """사양서 §15.3 #8 — N 에 따라 경로 순위가 바뀌는가."""

    def test_순위가_그대로면_통과다(self) -> None:
        """
        목적: §14 축3 — 네 N 에서 결론이 같으면 견고하다

        Given: N 이 바뀌어도 경로 순위가 그대로인 행 묶음
        When: 순위 판정을 낸다
        Then: 걸리지 않는다
        """
        # Given
        rows = _rank_rows(
            {1: (100.0, 90.0, 80.0), 3: (100.0, 90.0, 80.0), 5: (101.0, 91.0, 81.0), 7: (102.0, 92.0, 82.0)}
        )

        # When
        verdicts = {item.basis: item for item in path_rank_verdicts(rows)}

        # Then
        assert verdicts["종료 총자산"].triggered is False

    def test_순위가_뒤집히면_걸린다(self) -> None:
        """
        목적: §15.3 #8 — "전략이 아니라 N 을 맞춘 것" 이다

        Given: N=7 에서 261250 이 1위가 되는 행 묶음
        When: 순위 판정을 낸다
        Then: 걸리고 근거에 N 값이 남는다
        """
        # Given
        rows = _rank_rows(
            {1: (100.0, 90.0, 80.0), 3: (100.0, 90.0, 80.0), 5: (100.0, 90.0, 80.0), 7: (80.0, 90.0, 100.0)}
        )

        # When
        verdict = next(item for item in path_rank_verdicts(rows) if item.basis == "종료 총자산")

        # Then
        assert verdict.triggered is True
        assert "7" in verdict.detail

    def test_기준마다_따로_판정한다(self) -> None:
        """
        목적: 금액 순위와 리스크 조정 순위는 다른 것을 잰다.
              사양서 §1.1 이 노출이 다르면 리스크 조정 지표로만 보라고 규정했다

        Given: N 별 경로 행 묶음
        When: 순위 판정을 낸다
        Then: 종료 총자산·Calmar·Sharpe 세 기준이 각각 나온다
        """
        # Given
        rows = _rank_rows({value: (100.0, 90.0, 80.0) for value in LOOKBACK_YEAR_CHOICES})

        # When
        bases = [item.basis for item in path_rank_verdicts(rows)]

        # Then
        assert bases == ["종료 총자산", "Calmar", "Sharpe"]


def _rank_rows(by_lookback: dict[int, tuple[float, float, float]]) -> list[SweepRow]:
    """N 별로 세 경로의 종료 총자산을 준 행 묶음. Calmar·Sharpe 는 같은 순서를 따른다."""
    executions = (EXECUTION_EXCHANGE_MATCHED, EXECUTION_ETF_1X, EXECUTION_ETF_2X)
    rows: list[SweepRow] = []
    for lookback, assets in by_lookback.items():
        for execution, value in zip(executions, assets, strict=False):
            rows.append(
                _row(
                    execution=execution,
                    value_label=str(lookback),
                    is_default=lookback == 3,
                    final_assets=value * 1_000_000.0,
                    calmar=value / 100.0,
                    sharpe=value / 100.0,
                )
            )

    return rows
