"""실행 요약의 **데이터셋 한 줄** — 계층을 가리지 않는 소유자

`summary.json` 의 `datasets` 는 「무엇을 어느 기간으로 쟀는가」를 담는 자리이며
**범위의 SoT** 다(`src/verify_lab/CLAUDE.md` 출력 계약). 검증도 매매도 같은 줄을 낸다.

**소유자가 `report` 인 이유는 계층 방향이다.** 이 줄을 매매 계층이 가지면 `studies` 가
가져올 수 없어(`studies → strategy` 가 방향을 뒤집는다) 검증 셋이 각자 만들게 되고,
**키를 맞춰 놓고도 구현이 갈라진 채**로 남아 한 벌만 고쳐도 예외가 나지 않는다.
`studies` 도 `strategy` 도 이미 `report` 에 의존하므로 여기서는 방향이 뒤집히지 않는다.
저장은 같은 계층의 `writer.save_run_summary` 가 한다.

**이 모듈은 「한 줄」만 소유한다.** 요약 전체의 틀(`track`·`rule`·`cost` …)은 매매 계층의
규칙이라 `execution/run_summary.py` 에 남는다 — 검증은 요약 모양이 매매와 다르다.
"""

from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_DATE

# ============================================================
# 실행 요약의 최상위 키 — 계층을 가리지 않는다
# ============================================================

# 매매법 이름(slug). **값의 정의처는 `studies/<slug>/constants.py` 의 `TRACK_NAME`** 이고
# 여기는 키 이름만 소유한다.
#
# [중요] **`execution` 이 아니라 여기 둔다.** 신호가 없는 조사 검증(등가성·배수·선물)은
# 체결 계층을 쓰지 않는데, 키 하나 때문에 `execution` 을 import 하면 **쓰지도 않는 계층에
# 의존**하게 된다. `dataset_record` 를 이 모듈에 둔 것과 같은 이유다 —
# `studies` 도 `execution` 도 이미 `report` 에 의존한다
KEY_TRACK: Final = "track"

# ============================================================
# 데이터셋 한 줄의 키
# ============================================================

# **`ticker` 는 종목코드이고 `label` 은 표시 이름이다.** 여섯 산출 지점(검증 셋·매매 셋)이
# 같은 뜻을 쓴다 — `ticker` 에 **표시 이름**을 넣으면 요약이 `"ticker": "KODEX 200"` 처럼
# 적히고, **미국 ETF 는 둘이 같아(`QQQ`) 그 충돌이 국내에서만 드러난다.**
# 둘 다 `str` 이라 타입 검사가 잡지 못한다
KEY_DATASET_TICKER: Final = "ticker"
KEY_DATASET_LABEL: Final = "label"
KEY_DATASET_FILE: Final = "file"
KEY_DATASET_PERIOD: Final = "period"
KEY_DATASET_ROWS: Final = "rows"

# 기간 표기. 「시작 ~ 종료」이며 `.claude/rules/docs.md` 가 결과 문서에 요구하는 형식과 같다.
#
# **이 상수가 매매 계층에 있으면 `studies` 가 가져올 수 없어**(계층 방향) 검증 runner 가
# f-string 에 `" ~ "` 를 직접 적게 된다. 형식을 고정하는 것이 없으면 **한 곳만
# `" - "` 로 바뀌어도 예외가 나지 않는다** — 산출물만 조용히 갈린다
PERIOD_SEPARATOR: Final = " ~ "


def dataset_record(*, ticker: str, label: str, file: str, frame: pd.DataFrame) -> dict[str, Any]:
    """데이터셋 한 줄을 만든다.

    **기간과 거래일 수를 시세에서 직접 읽는다.** 호출 측이 따로 세면 산출 지점마다 갈리고,
    결과 문서가 인용하는 「데이터 기간」이 실제 파일과 어긋나도 예외가 나지 않는다 —
    실측으로 `docs/매매/역방향/규칙.md` 의 기간이 낡은 채 남은 적이 있다.

    **자기 축을 더 붙이는 것은 호출 측의 몫이다.** 검증마다 더 담을 것이 다르므로
    (`price_basis`·`expiry_count`·`is_index`) 이 함수에 검증별 인자를 두지 않는다 —
    두면 공통 함수가 어느 검증이 자기를 쓰는지 알게 된다.

    Args:
        ticker: 종목 또는 지수 코드 (`069500`·`QQQ`)
        label: 표시 이름 (`KODEX 200`). 산출물의 종목 컬럼이 쓰는 값이다
        file: 읽은 파일 이름. 경로가 아니라 이름이다 — 절대경로는 PC 마다 달라 산출물이 갈린다
        frame: 그 대상의 시세 또는 계열. 날짜 오름차순이어야 한다

    Returns:
        데이터셋 한 줄

    Raises:
        ValueError: 코드나 이름이 비었거나, 시세가 비어 있는 경우
    """
    if not ticker or not label:
        raise ValueError(f"데이터셋에는 코드와 표시 이름이 둘 다 있어야 합니다: 코드 {ticker!r}, 이름 {label!r}")
    if frame.empty:
        raise ValueError(f"시세가 비어 있어 기간을 낼 수 없습니다: {label}")

    dates = frame[COL_DATE]

    return {
        KEY_DATASET_TICKER: ticker,
        KEY_DATASET_LABEL: label,
        KEY_DATASET_FILE: file,
        KEY_DATASET_PERIOD: format_period(dates.iloc[0], dates.iloc[-1]),
        KEY_DATASET_ROWS: len(frame),
    }


def format_period(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """기간을 산출물 표기로 바꾼다.

    **`dataset_record` 밖에서도 필요하다** — 배수 검증이 구간 기간을 CSV 셀에 적는다.
    거기서 형식을 따로 만들면 같은 뜻의 값이 두 산출물에서 다르게 보인다.

    Args:
        start: 시작일
        end: 종료일

    Returns:
        `시작 ~ 종료` (날짜만)
    """
    return f"{start.date()}{PERIOD_SEPARATOR}{end.date()}"


__all__ = [
    "KEY_DATASET_FILE",
    "KEY_DATASET_LABEL",
    "KEY_DATASET_PERIOD",
    "KEY_DATASET_ROWS",
    "KEY_DATASET_TICKER",
    "PERIOD_SEPARATOR",
    "dataset_record",
    "format_period",
]
