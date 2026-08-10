"""터미널 표 출력의 폭 계산과 정렬 계약을 고정한다.

이 프로젝트의 결과는 한글 헤더가 붙은 표로 출력된다. 한글을 1칸으로 세면 표가 어긋나
사용자가 숫자를 대조하기 어려워진다.
"""

import logging

import pytest

from verify_lab.utils.formatting import Align, TableLogger, _format_cell, _get_display_width


def test_ascii_width_is_one_per_character() -> None:
    """
    목적: 반각 문자의 폭 계산을 고정한다.

    Given: 영문 문자열
    When: 표시 폭을 계산한다
    Then: 글자 수와 같다
    """
    assert _get_display_width("QQQ") == 3


def test_hangul_counts_as_two_columns() -> None:
    """
    목적: 한글이 터미널에서 2칸을 차지함을 고정한다.

    Given: 한글 두 글자
    When: 표시 폭을 계산한다
    Then: 4가 된다
    """
    assert _get_display_width("날짜") == 4


def test_mixed_text_width_is_summed() -> None:
    """
    목적: 한글과 영문이 섞인 문자열의 폭 계산을 고정한다.

    Given: 한글 2글자 + 영문 3글자
    When: 표시 폭을 계산한다
    Then: 2*2 + 3 = 7 이다
    """
    assert _get_display_width("종가QQQ") == 7


def test_empty_text_width_is_zero() -> None:
    """
    목적: 빈 문자열의 폭을 고정한다 (경계 조건).

    Given: 빈 문자열
    When: 표시 폭을 계산한다
    Then: 0이다
    """
    assert _get_display_width("") == 0


def test_left_align_pads_on_the_right() -> None:
    """
    목적: 왼쪽 정렬 시 패딩 위치와 결과 폭을 고정한다.

    Given: 한글 2글자(4칸)와 목표 폭 8
    When: 왼쪽 정렬한다
    Then: 오른쪽에 4칸이 붙어 전체 폭이 8이 된다
    """
    # When
    cell = _format_cell("날짜", 8, Align.LEFT)

    # Then
    assert cell == "날짜    "
    assert _get_display_width(cell) == 8


def test_right_align_pads_on_the_left() -> None:
    """
    목적: 오른쪽 정렬 시 패딩 위치를 고정한다 (숫자 열 정렬).

    Given: 문자열 "1.5"와 목표 폭 6
    When: 오른쪽 정렬한다
    Then: 왼쪽에 3칸이 붙는다
    """
    assert _format_cell("1.5", 6, Align.RIGHT) == "   1.5"


def test_overflowing_text_is_returned_intact() -> None:
    """
    목적: 목표 폭보다 넓은 값을 자르지 않음을 고정한다 (경계 조건).

    값을 잘라내면 사용자가 대조해야 할 숫자가 사라진다. 표가 어긋나더라도
    원본을 그대로 보여주는 쪽이 안전하다.

    Given: 목표 폭보다 긴 문자열
    When: 정렬한다
    Then: 원본이 그대로 반환된다
    """
    assert _format_cell("2026-08-10", 4, Align.LEFT) == "2026-08-10"


def test_print_row_rejects_length_mismatch() -> None:
    """
    목적: 컬럼 수와 데이터 길이가 다르면 즉시 실패함을 고정한다.

    Given: 컬럼 1개로 만든 TableLogger
    When: 값 2개를 출력한다
    Then: ValueError 가 발생한다
    """
    # Given
    table = TableLogger([("날짜", 12, Align.LEFT)], logging.getLogger("verify_lab.test.formatting"))

    # When / Then
    with pytest.raises(ValueError, match="컬럼 수"):
        table.print_row(["2026-08-10", "군더더기"])
