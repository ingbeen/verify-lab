"""표시용 표 생성의 계약을 고정한다.

이 계층이 하는 일은 계산이 아니라 **번역**이다. `measure` 가 낸 비율과 영문 토큰을
사람이 읽는 백분율과 한글 레이블로 바꾼다. 번역이 흔들리면 사용자가 화면에서 본 숫자를
CSV 에서 찾지 못하고, 그러면 "사용자가 직접 검증할 수 있어야 한다"는 전제가 무너진다.

핵심 계약은 네 가지다.
- 신호일 목록은 **신호일 한 줄**로 펼쳐진다 (2-a 가 report 의 몫으로 미뤄둔 pivot)
- 수익률·승률은 **백분율 2자리**, p 값만 4자리다
- 행 순서는 **구간 → 기준**이다. 같은 구간의 두 기준이 붙어 있어야 갭이 보인다
- 검정하지 않은 칸은 빈칸이 아니라 **사유가 보인다**
"""

import logging

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.measure.constants import (
    COL_BASIS,
    COL_EXCLUDED_REASON,
    COL_FORWARD_RETURN,
    COL_HORIZON,
    REASON_NONE,
    REASON_OUT_OF_RANGE,
)
from verify_lab.measure.forward_return import ReturnBasis
from verify_lab.measure.statistics import excess, permutation_test, summarize
from verify_lab.report.constants import (
    DISPLAY_BASIS,
    DISPLAY_EXCLUDED,
    DISPLAY_HORIZON,
    DISPLAY_MEAN,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_TEST_NOTE,
    DISPLAY_WIN_RATE,
    HORIZON_LABELS,
)
from verify_lab.report.tables import (
    build_comparison_table,
    build_excess_table,
    build_signal_table,
    build_statistics_table,
    build_test_table,
    print_dataframe,
    to_markdown,
)
from verify_lab.utils.formatting import get_display_width

BASELINE_NAME = "단순 보유"


def _cell(
    values: list[float | None],
    basis: ReturnBasis = ReturnBasis.CLOSE,
    horizon: int = 1,
) -> pd.DataFrame:
    """한 칸짜리 long-form 프레임을 만든다. `None` 은 제외된 칸이다."""
    return pd.DataFrame(
        {
            COL_DATE: pd.bdate_range("2026-01-05", periods=len(values)),
            COL_BASIS: basis.value,
            COL_HORIZON: horizon,
            COL_FORWARD_RETURN: [float("nan") if value is None else value for value in values],
            COL_EXCLUDED_REASON: [REASON_OUT_OF_RANGE if value is None else REASON_NONE for value in values],
        }
    )


def _both_bases(values: list[float | None], horizons: tuple[int, ...] = (1, 252)) -> pd.DataFrame:
    """기준 2종 × 지정 구간을 모두 채운 long-form 프레임을 만든다."""
    return pd.concat(
        [_cell(values, basis=basis, horizon=horizon) for basis in ReturnBasis for horizon in horizons],
        ignore_index=True,
    )


class TestSignalTable:
    """신호일 전체 목록의 계약을 고정한다 — 사용자가 차트로 대조하는 원자료다."""

    def test_one_row_per_signal_day(self) -> None:
        """
        목적: long-form 이 **신호일 한 줄**로 펼쳐진다.

        Given: 신호 3건 × 기준 2종 × 구간 2개 (long-form 12행)
        When: 신호일 목록을 만든다
        Then: 3행이 된다
        """
        # Given
        frame = _both_bases([0.10, 0.20, 0.30])

        # When
        table = build_signal_table(frame)

        # Then
        assert len(table) == 3

    def test_columns_are_named_by_basis_and_horizon(self) -> None:
        """
        목적: 펼쳐진 컬럼 이름이 "기준 구간"이다 — 어느 값인지 헤더만 보고 알 수 있어야 한다.

        Given: 종가·익일시가 × 1일·1년
        When: 신호일 목록을 만든다
        Then: 날짜 컬럼 뒤에 "종가 1일 … 익일시가 1년" 이 붙는다
        """
        # Given
        frame = _both_bases([0.10])

        # When
        table = build_signal_table(frame)

        # Then
        assert list(table.columns) == ["날짜", "종가 1일", "종가 1년", "익일시가 1일", "익일시가 1년"]

    def test_values_are_percent_with_two_decimals(self) -> None:
        """
        목적: 저장 값은 **백분율 2자리**다 (`.claude/rules/python.md` 반올림 규칙).

        Given: 비율 0.062512
        When: 신호일 목록을 만든다
        Then: 6.25 로 나온다
        """
        # Given
        frame = _cell([0.062512])

        # When
        table = build_signal_table(frame)

        # Then
        assert float(table["종가 1일"].iloc[0]) == pytest.approx(6.25, abs=1e-9)

    def test_excluded_cell_stays_empty(self) -> None:
        """
        목적: 제외된 칸은 값이 비어 있다. 0 으로 채우면 "수익률 0%"로 읽힌다.

        Given: 구간 끝이 데이터를 넘어 제외된 신호
        When: 신호일 목록을 만든다
        Then: 그 칸이 비어 있다
        """
        # Given
        frame = _cell([None])

        # When
        table = build_signal_table(frame)

        # Then
        assert pd.isna(table["종가 1일"].iloc[0])

    def test_signal_details_are_placed_in_front(self) -> None:
        """
        목적: 검증별 컬럼(순위·사건 번호 등)을 앞에 붙일 수 있다 — 이벤트 정의가 채운다.

        Given: 날짜와 순위를 담은 부가 정보
        When: 신호일 목록을 만든다
        Then: 날짜 다음에 순위가 오고 수익률이 뒤따른다
        """
        # Given
        frame = _cell([0.10], horizon=1)
        details = pd.DataFrame({COL_DATE: frame[COL_DATE].unique(), "당시 순위": [3]})

        # When
        table = build_signal_table(frame, signal_details=details)

        # Then
        assert list(table.columns) == ["날짜", "당시 순위", "종가 1일"]

    def test_rejects_details_without_date(self) -> None:
        """
        목적: 날짜가 없는 부가 정보는 붙일 기준이 없다.

        Given: 날짜 컬럼이 없는 부가 정보
        When: 신호일 목록을 만든다
        Then: ValueError
        """
        frame = _cell([0.10])

        with pytest.raises(ValueError, match="날짜"):
            build_signal_table(frame, signal_details=pd.DataFrame({"당시 순위": [3]}))


class TestStatisticsTable:
    """집계 표의 레이블·단위·정렬을 고정한다."""

    def test_uses_korean_labels_and_horizon_names(self) -> None:
        """
        목적: 화면과 CSV 는 한글 레이블과 구간 이름을 쓴다 (내부/출력 분리).

        Given: 기준 2종 × 구간 1일·1년
        When: 집계 표를 만든다
        Then: 컬럼이 한글이고 구간이 "1일"·"1년" 으로 표기된다
        """
        # Given
        summary = summarize(_both_bases([0.10, 0.20]))

        # When
        table = build_statistics_table(summary)

        # Then
        assert DISPLAY_HORIZON in table.columns
        assert DISPLAY_SAMPLE_COUNT in table.columns
        assert set(table[DISPLAY_HORIZON]) == {HORIZON_LABELS[1], HORIZON_LABELS[252]}

    def test_rows_are_sorted_by_horizon_then_basis(self) -> None:
        """
        목적: 행 순서는 **구간 → 기준**이다. 같은 구간의 두 기준이 붙어 있어야 갭이 보인다.

        Given: 기준 2종 × 구간 1일·1년
        When: 집계 표를 만든다
        Then: 1일 두 줄이 먼저, 그 다음 1년 두 줄이 온다
        """
        # Given
        summary = summarize(_both_bases([0.10, 0.20]))

        # When
        table = build_statistics_table(summary)

        # Then
        assert table[DISPLAY_HORIZON].tolist() == ["1일", "1일", "1년", "1년"]
        assert table[DISPLAY_BASIS].tolist() == ["종가", "익일시가", "종가", "익일시가"]

    def test_rates_become_percent(self) -> None:
        """
        목적: 평균·중앙값·승률이 모두 백분율로 바뀐다.

        Given: 수익률 +10%·+20% (평균 15%, 승률 100%)
        When: 집계 표를 만든다
        Then: 평균 15.0, 승률 100.0 이다
        """
        # Given
        summary = summarize(_cell([0.10, 0.20]))

        # When
        table = build_statistics_table(summary)

        # Then
        assert float(table[DISPLAY_MEAN].iloc[0]) == pytest.approx(15.0, abs=1e-9)
        assert float(table[DISPLAY_WIN_RATE].iloc[0]) == pytest.approx(100.0, abs=1e-9)

    def test_keeps_sample_and_excluded_counts(self) -> None:
        """
        목적: 표본 수는 절대 생략하지 않는다. 제외 건수도 함께 보인다.

        Given: 값 2건과 제외 1건
        When: 집계 표를 만든다
        Then: 표본 2, 제외 1 이 남는다
        """
        # Given
        summary = summarize(_cell([0.10, 0.20, None]))

        # When
        table = build_statistics_table(summary)

        # Then
        assert int(table[DISPLAY_SAMPLE_COUNT].iloc[0]) == 2
        assert int(table[DISPLAY_EXCLUDED].iloc[0]) == 1


class TestExcessAndTestTables:
    """CSV 용 초과분·검정 표를 고정한다."""

    def test_excess_table_carries_baseline_name(self) -> None:
        """
        목적: 초과분 표는 어느 베이스라인 대비인지를 컬럼으로 남긴다.

        Given: 베이스라인 하나에 대한 초과분
        When: 초과분 표를 만든다
        Then: 베이스라인 이름 컬럼이 있다
        """
        # Given
        signal = summarize(_cell([0.10, 0.20]))
        baseline = summarize(_cell([0.0, 0.10]))

        # When
        table = build_excess_table({BASELINE_NAME: excess(signal, baseline)})

        # Then
        assert set(table["베이스라인"]) == {BASELINE_NAME}

    def test_excess_values_are_percentage_points(self) -> None:
        """
        목적: 초과분은 백분율 포인트다 (0.10 → 10.0).

        Given: 신호 평균 15%, 베이스라인 평균 5%
        When: 초과분 표를 만든다
        Then: 평균 초과가 10.0 이다
        """
        # Given
        signal = summarize(_cell([0.10, 0.20]))
        baseline = summarize(_cell([0.0, 0.10]))

        # When
        table = build_excess_table({BASELINE_NAME: excess(signal, baseline)})

        # Then
        assert float(table["평균 초과(%p)"].iloc[0]) == pytest.approx(10.0, abs=1e-9)

    def test_p_value_keeps_four_decimals(self) -> None:
        """
        목적: p 값은 확률이라 백분율이 아니다. 4자리로 남긴다.

        Given: 표본이 충분한 검정 결과
        When: 검정 표를 만든다
        Then: p 값이 0~1 범위의 값으로 남는다
        """
        # Given
        signal = _cell([0.09] * 12)
        population = _cell([value / 1000 for value in range(-100, 100)])

        # When
        table = build_test_table({"무작위 진입": permutation_test(signal, population, repeats=50, seed=0)})

        # Then
        p_value = float(table["p값"].iloc[0])
        assert 0.0 < p_value <= 1.0

    def test_untested_cell_shows_the_reason(self) -> None:
        """
        목적: 검정하지 않은 칸은 빈칸이 아니라 **사유**가 보인다.
              빈칸은 "값이 0" 또는 "아직 안 돌았다"로 읽힌다.

        Given: 표본 7건짜리 신호 (한 자릿수)
        When: 검정 표를 만든다
        Then: 비고에 "표본 부족으로 검정 불가" 가 있고 p 값은 비어 있다
        """
        # Given
        signal = _cell([0.09] * 7)
        population = _cell([value / 1000 for value in range(-100, 100)])

        # When
        table = build_test_table({"무작위 진입": permutation_test(signal, population, repeats=50, seed=0)})

        # Then
        assert table[DISPLAY_TEST_NOTE].iloc[0] == "표본 부족으로 검정 불가"
        assert pd.isna(table["p값"].iloc[0])


class TestComparisonTable:
    """터미널·마크다운용 비교 표를 고정한다."""

    def test_baselines_become_columns(self) -> None:
        """
        목적: 베이스라인을 **열로 펼쳐** 한 화면에서 나란히 비교한다.

        Given: 베이스라인 2종의 초과분과 검정 결과
        When: 비교 표를 만든다
        Then: 베이스라인마다 평균 초과 컬럼이 생긴다
        """
        # Given
        signal_summary = summarize(_cell([0.10, 0.20]))
        first = excess(signal_summary, summarize(_cell([0.0, 0.10])))
        second = excess(signal_summary, summarize(_cell([0.05, 0.05])))
        test = permutation_test(_cell([0.10, 0.20]), _cell([0.0, 0.10]), repeats=10, seed=0)

        # When
        table = build_comparison_table({"단순 보유": first, "조건부": second}, test)

        # Then
        assert "단순 보유 평균 초과(%p)" in table.columns
        assert "조건부 평균 초과(%p)" in table.columns

    def test_keeps_the_test_note_column(self) -> None:
        """
        목적: 비교 표에도 검정 사유가 남는다 — 검증 #1 은 이 칸이 전부 "검정 불가"가 된다.

        Given: 표본이 부족한 신호
        When: 비교 표를 만든다
        Then: 비고 컬럼에 사유가 있다
        """
        # Given
        signal = _cell([0.10, 0.20])
        signal_summary = summarize(signal)
        excess_table = excess(signal_summary, summarize(_cell([0.0, 0.10])))
        test = permutation_test(signal, _cell([0.0, 0.10]), repeats=10, seed=0)

        # When
        table = build_comparison_table({"단순 보유": excess_table}, test)

        # Then
        assert table[DISPLAY_TEST_NOTE].iloc[0] == "표본 부족으로 검정 불가"


class TestTerminalOutput:
    """터미널 출력의 폭 계산을 고정한다."""

    def test_numeric_column_keeps_a_gap_before_the_next_column(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        목적: 오른쪽 정렬 컬럼 뒤에도 여백이 남는다.

        정렬 여백은 값 **앞쪽**에 붙으므로, 폭만 늘리면 다음 컬럼과 글자가 맞닿아
        "p값비고" 처럼 읽힌다.

        Given: 숫자 컬럼 뒤에 긴 문자열 컬럼이 오는 표
        When: 터미널에 출력한다
        Then: 두 컬럼 사이에 여백이 있다
        """
        # Given
        table = pd.DataFrame({"p값": [float("nan")], DISPLAY_TEST_NOTE: ["표본 부족으로 검정 불가"]})
        logger = logging.getLogger("test_report_tables")

        # When
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            print_dataframe(table, logger)

        # Then
        assert any("-  표본 부족으로 검정 불가" in record.message for record in caplog.records)

    def test_korean_header_is_padded_by_display_width(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        목적: 한글은 두 칸을 차지하므로 글자 수가 아니라 표시 폭으로 정렬한다.

        Given: 한글 헤더와 그보다 긴 값
        When: 터미널에 출력한다
        Then: 헤더 줄과 데이터 줄의 표시 폭이 같다
        """
        # Given
        table = pd.DataFrame({"구간": ["1개월"], "기준": ["익일시가"]})
        logger = logging.getLogger("test_report_tables")

        # When
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            print_dataframe(table, logger)

        # Then
        messages = [record.message for record in caplog.records]
        assert get_display_width(messages[1].rstrip()) <= get_display_width(messages[0])

    def test_rejects_empty_table(self) -> None:
        """
        목적: 빈 표를 출력하지 않는다. 헤더만 찍히면 "결과 없음"과 구분되지 않는다.

        Given: 행이 없는 표
        When: 터미널에 출력한다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            print_dataframe(pd.DataFrame({"구간": []}), logging.getLogger("test_report_tables"))


class TestMarkdown:
    """마크다운 표 변환을 고정한다."""

    def test_renders_header_separator_and_rows(self) -> None:
        """
        목적: 마크다운 표에 헤더·구분선·행이 모두 나온다.

        Given: 2행짜리 표
        When: 마크다운으로 바꾼다
        Then: 세 번째 줄부터 데이터 행이고 두 번째 줄이 구분선이다
        """
        # Given
        table = pd.DataFrame({"구간": ["1일", "1년"], "평균(%)": [2.22, 44.09]})

        # When
        lines = to_markdown(table).splitlines()

        # Then
        assert lines[0] == "| 구간 | 평균(%) |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| 1일 | 2.22 |"

    def test_empty_value_becomes_a_dash(self) -> None:
        """
        목적: 빈 값이 표를 깨뜨리지 않는다. 칸이 비면 마크다운 열이 어긋난다.

        Given: 값이 없는 칸
        When: 마크다운으로 바꾼다
        Then: 빈칸 자리에 표시 문자가 들어간다
        """
        # Given
        table = pd.DataFrame({"구간": ["1년"], "p값": [float("nan")]})

        # When
        lines = to_markdown(table).splitlines()

        # Then
        assert lines[2] == "| 1년 | - |"

    def test_rejects_empty_table(self) -> None:
        """
        목적: 빈 표를 조용히 빈 문자열로 내보내지 않는다.

        Given: 행이 없는 표
        When: 마크다운으로 바꾼다
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            to_markdown(pd.DataFrame({"구간": []}))
