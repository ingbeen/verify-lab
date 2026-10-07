"""표시용 표 — 번역과 렌더링

`measure` 가 낸 값을 사람이 읽는 형태로 바꾼다. **계산하지 않는다.** 집계와 검정은 전부
`measure` 의 일이며, 여기서 파생값을 만들기 시작하면 같은 수가 두 곳에서 나오게 된다.

하는 일은 둘이다.
- 저장 직전에 영문 헤더를 한글 레이블로 바꾸고 단위(백분율 · 확률 자릿수)를 맞춘다
- 표를 터미널에 그린다

**터미널과 CSV 는 같은 표를 쓴다.** 따로 가공하면 반올림 시점이 갈려 화면에서 본 숫자를
CSV 에서 찾지 못하고, 그러면 사용자가 직접 대조한다는 이 프로젝트의 전제가 무너진다.
"""

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from verify_lab.common_constants import RATE_TO_PERCENT
from verify_lab.report.constants import (
    COLUMN_GAP,
    EMPTY_MARK,
    PERCENT_DECIMALS,
    PROBABILITY_DECIMALS,
)
from verify_lab.utils.formatting import Align, TableLogger, get_display_width


def print_dataframe(table: pd.DataFrame, logger: logging.Logger, title: str | None = None) -> None:
    """표를 터미널에 출력한다.

    컬럼 폭을 내용에서 계산한다. 표마다 폭을 손으로 적으면 데이터가 바뀔 때마다 어긋난다.
    숫자 컬럼은 오른쪽 정렬해 자릿수를 눈으로 맞춘다.

    **오른쪽 정렬 컬럼은 여백을 값에 직접 단다.** 정렬 여백이 값 앞쪽에만 붙어서,
    폭만 늘리면 다음 컬럼과 글자가 맞닿아 헤더가 "p값비고" 처럼 읽힌다.

    Args:
        table: 표시용 표
        logger: 출력에 쓸 로거
        title: 표 제목

    Raises:
        ValueError: 표가 비어 있는 경우
    """
    if table.empty:
        raise ValueError("표가 비어 있습니다")

    columns: list[tuple[str, int, Align]] = []
    rendered: list[list[str]] = []

    for name in table.columns:
        align = Align.RIGHT if pd.api.types.is_numeric_dtype(table[name]) else Align.LEFT
        trailing = " " * COLUMN_GAP if align is Align.RIGHT else ""

        header = str(name) + trailing
        cells = [_cell_text(value) + trailing for value in table[name]]
        width = max(get_display_width(text) for text in [header, *cells])

        columns.append((header, width if align is Align.RIGHT else width + COLUMN_GAP, align))
        rendered.append(cells)

    rows = [list(row) for row in zip(*rendered, strict=True)]
    TableLogger(columns, logger).print_table(rows, title)


def _cell_text(value: Any) -> str:
    """표 한 칸을 문자열로 바꾼다. 값이 없으면 표시 문자를 쓴다.

    **정수에는 천 단위 구분자를 붙인다.** 신호 수·행 수처럼 자릿수를 눈으로 세는 값이라
    구분자가 없으면 자리를 잘못 읽는다. 실수는 이미 반올림된 상태로 들어오므로 건드리지 않는다.

    **결측 검사를 빈 문자열 비교보다 «먼저», 그리고 «스칼라일 때만» 한다.** 건수 컬럼은
    결측을 담을 수 있는 정수형(`Int64`)이라 빈 칸이 `pd.NA` 로 오는데, `pd.NA == ""` 는 참도
    거짓도 아닌 `pd.NA` 를 돌려주고 그것을 `if` 가 평가하면 **`TypeError` 로 터진다.**
    반대로 목록·배열에 `pd.isna` 를 걸면 **배열이 돌아와 `ValueError` 로 터진다** —
    두 조건이 다른 값에서 반대로 걸리므로 순서와 스칼라 검사가 둘 다 계약이다.

    Args:
        value: 셀 값

    Returns:
        표시 문자열
    """
    if value is None or (pd.api.types.is_scalar(value) and bool(pd.isna(value))) or value == "":
        return EMPTY_MARK

    if pd.api.types.is_integer(value):
        return f"{value:,}"

    return str(value)


def to_display_columns(
    table: pd.DataFrame,
    labels: Mapping[str, str],
    *,
    percent_columns: Sequence[str] = (),
    probability_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """저장 직전에 컬럼 헤더를 한글로 바꾸고 단위를 맞춘다.

    **사전에 없는 컬럼이 하나라도 있으면 예외를 던진다.** 이것이 이 함수의 존재 이유다 —
    컬럼을 새로 추가하고 한글 이름을 만들지 않으면 영문 토큰이 그대로 사용자에게 나가는데,
    조용히 지나가면 발견되지 않는다 (`src/verify_lab/CLAUDE.md` 「내부/출력 분리」).

    **단위 변환을 함께 하는 이유**: 헤더를 `평균(%)` 로 바꾸면서 값이 비율(0.003)이면
    헤더가 거짓말이 된다. 이름과 단위는 한 자리에서 같이 정해야 어긋나지 않는다.

    **사전은 호출자가 준다.** 이 계층은 어떤 검증이 자기를 쓰는지 몰라야 하므로
    검증별 컬럼 이름을 알 수 없다.

    Args:
        table: 저장할 표 (영문 `COL_*` 헤더)
        labels: `COL_* → 한글 레이블` 사전. 표의 모든 컬럼을 덮어야 한다
        percent_columns: 비율(0~1)로 들어와 백분율로 내보낼 컬럼
        probability_columns: 확률로 들어와 자릿수만 맞출 컬럼

    Note:
        **단위 변환은 백분율과 확률 둘뿐이고, 배수(손익비) 인자를 두지 않는다** — 판정표에
        손익비가 없어 호출처가 0 이기 때문이다. 매매 계층의 `성적표.csv` 는 이 함수를 지나지 않고
        `execution/periods.py` 가 저장 직전에 직접 반올림하므로 그쪽에도 필요가 없다.
        **세 번째 단위가 실제로 필요해지면 그때 더한다.**

    Returns:
        헤더가 한글이고 단위가 맞춰진 새 DataFrame. 컬럼 순서는 그대로다

    Raises:
        ValueError: 표가 비어 있거나, 사전이 덮지 못한 컬럼이 있는 경우,
            변환 대상으로 지목한 컬럼이 표에 없는 경우
    """
    if table.empty:
        raise ValueError("표가 비어 있습니다")

    missing = [column for column in table.columns if column not in labels]
    if missing:
        raise ValueError(f"한글 이름이 없는 컬럼이 있습니다: {missing}")

    unknown = [column for column in (*percent_columns, *probability_columns) if column not in table.columns]
    if unknown:
        raise ValueError(f"변환 대상 컬럼이 표에 없습니다: {unknown}")

    # **두 컬럼이 같은 헤더로 접히는 것을 막는다.** pandas 는 이름이 겹쳐도 예외를 내지 않고
    # 같은 이름의 컬럼 둘을 만들어, CSV 에 `보유 거래일,보유 거래일` 이 나간다 — 읽는 쪽은
    # 어느 것이 무엇인지 알 수 없고 **에러도 경고도 없다.**
    # 판정은 사전이 아니라 **결과 헤더**로 한다 — 사전에 같은 값을 가진 키가 둘 있어도
    # 한 표에 함께 나오지 않으면 겹치지 않는다 (`Date`·`StartDate` 가 둘 다 `시작일` 이다)
    renamed = [labels[column] for column in table.columns]
    collisions = sorted(name for name, count in Counter(renamed).items() if count > 1)
    if collisions:
        raise ValueError(f"두 컬럼이 같은 헤더로 접힙니다: {collisions}")

    converted = table.copy()
    for column in percent_columns:
        converted[column] = (converted[column] * RATE_TO_PERCENT).round(PERCENT_DECIMALS)
    for column in probability_columns:
        converted[column] = converted[column].round(PROBABILITY_DECIMALS)

    return converted.rename(columns=dict(labels))
