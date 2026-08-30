"""터미널 출력 포맷팅

한글과 영문이 섞인 표를 정렬한다. **글자 수가 아니라 터미널이 차지하는 칸 수로 센다** —
한글은 두 칸을 쓰므로 `len()` 으로 맞추면 열이 어긋난다.

컬럼 폭을 인자로 받는다. 폭을 손으로 적으면 내용이 길어질 때 헤더가 다음 열과 맞닿으므로,
**내용에서 폭을 계산하는 `report.tables.print_dataframe` 을 우선 쓴다.** 이 모듈은 그쪽이
받지 못하는 형태(키-값 나열 같은 자유 형식 표)를 내는 실측 스크립트가 쓴다.
"""

import logging
import unicodedata
from collections.abc import Sequence
from enum import Enum

# 터미널에서 두 칸을 차지하는 문자의 동아시아 폭 속성 (Wide / Fullwidth)
_WIDE_CHARACTER_WIDTHS = ("W", "F")


class Align(Enum):
    """텍스트 정렬 방향

    Attributes:
        LEFT: 왼쪽 정렬 — 이름·레이블처럼 읽는 순서가 중요한 값
        RIGHT: 오른쪽 정렬 — 숫자처럼 자릿수를 맞춰 봐야 하는 값
    """

    LEFT = "left"
    RIGHT = "right"


def get_display_width(text: str) -> int:
    """문자열이 터미널에서 차지하는 폭을 칸 수로 낸다.

    한글·한자 같은 전각 문자는 두 칸, 나머지는 한 칸으로 센다.

    Args:
        text: 폭을 잴 문자열

    Returns:
        터미널에서 차지하는 칸 수
    """
    width = 0

    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in _WIDE_CHARACTER_WIDTHS else 1

    return width


def _format_cell(text: str, width: int, align: Align = Align.LEFT) -> str:
    """한 칸을 목표 폭에 맞춰 채운다.

    **폭이 모자라면 자르지 않고 원본을 그대로 돌려준다.** 값을 잘라내면 숫자가 조용히
    달라 보이므로, 열이 밀리는 쪽이 낫다.

    Args:
        text: 정렬할 문자열
        width: 목표 폭 (칸 수)
        align: 정렬 방향

    Returns:
        여백이 채워진 문자열
    """
    content = str(text)
    available_padding = width - get_display_width(content)

    if available_padding <= 0:
        return content

    if align is Align.LEFT:
        return content + " " * available_padding

    return " " * available_padding + content


def _format_row(cells: list[tuple[str, int, Align]], indent: int = 2) -> str:
    """여러 칸을 이어 붙여 한 행을 만든다.

    Args:
        cells: (텍스트, 폭, 정렬) 목록
        indent: 들여쓰기 칸 수

    Returns:
        한 행 문자열
    """
    formatted_cells = [_format_cell(text, width, align) for text, width, align in cells]

    return " " * indent + "".join(formatted_cells)


class TableLogger:
    """컬럼 정의를 받아 표를 로그로 출력한다.

    헤더·데이터·푸터를 따로 부를 수 있어 **행을 만들어 가며 찍는 표**에 쓴다.
    실측 스크립트가 키-값을 한 줄씩 쌓는 용도로 그렇게 쓴다.

    Examples:
        >>> columns = [("날짜", 12, Align.LEFT), ("가격", 12, Align.RIGHT)]
        >>> table = TableLogger(columns, logger)
        >>> table.print_table([["2024-01-01", "100.50"]], title="가격")
    """

    def __init__(self, columns: list[tuple[str, int, Align]], logger: logging.Logger, indent: int = 2) -> None:
        """표 구조를 정한다.

        Args:
            columns: (컬럼명, 폭, 정렬) 목록
            logger: 출력에 쓸 로거
            indent: 들여쓰기 칸 수
        """
        self.columns = columns
        self.logger = logger
        self.indent = indent
        self._total_width = indent + sum(width for _, width, _ in columns)

    def print_header(self, title: str | None = None) -> None:
        """구분선·제목·컬럼 헤더를 출력한다.

        Args:
            title: 표 제목 (`None` 이면 제목 없음)
        """
        self.logger.debug("=" * self._total_width)

        if title:
            self.logger.debug(title)

        self.logger.debug(_format_row(list(self.columns), self.indent))
        self.logger.debug("-" * self._total_width)

    def print_row(self, data: Sequence[str | int | float]) -> None:
        """데이터 행 하나를 출력한다.

        Args:
            data: 컬럼 순서대로 담은 값 (문자열이 아니면 내부에서 변환한다)

        Raises:
            ValueError: 값의 개수가 컬럼 수와 다른 경우
        """
        if len(data) != len(self.columns):
            raise ValueError(f"데이터 길이({len(data)})가 컬럼 수({len(self.columns)})와 일치하지 않습니다")

        cells = [(str(value), width, align) for value, (_, width, align) in zip(data, self.columns, strict=True)]

        # 로그 포맷에 함수명이 들어가는데 `print_row` 가 `print_header` 보다 두 글자 짧다.
        # 그만큼 앞에서 밀리므로 여기서 두 칸을 보태 헤더와 데이터의 열을 맞춘다
        self.logger.debug("  " + _format_row(cells, self.indent))

    def print_footer(self) -> None:
        """표 아래 구분선을 출력한다."""
        self.logger.debug("=" * self._total_width)

    def print_table(self, rows: Sequence[Sequence[str | int | float]], title: str | None = None) -> None:
        """헤더부터 푸터까지 한 번에 출력한다.

        Args:
            rows: 데이터 행 목록
            title: 표 제목 (`None` 이면 제목 없음)
        """
        self.print_header(title)
        for row in rows:
            self.print_row(row)
        self.print_footer()
