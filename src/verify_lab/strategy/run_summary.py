"""매매 실행 요약 — 매매법을 가리지 않는 공유 계층

`summary.json` 에 담을 내용을 조립한다. 저장은 `report/writer.save_run_summary` 가 한다.

**전에는 세 매매법이 세 구조였다.** 만드는 자리도 키도 달랐다 — 역방향은 runner 에서
`strategy`/`targets`/`rule`/`row_counts`/`notes`, 옵션 만기일은 **CLI 에서**
`cells`/`stop_levels`/`row_counts`, 월말은 runner 에서 `stop_levels`/`fixed_stop_level`/
`cost`/`datasets`/`row_counts` 를 냈다. 그래서 세 가지가 어긋나 있었다.

- `src/verify_lab/CLAUDE.md` 가 **「범위의 SoT 는 `summary.json` 의 `datasets`」**라고
  선언했는데 **월말만** 그 키를 가졌다. 옵션 만기일은 종목코드를 어디에도 남기지 않았다
- `.claude/rules/strategy.md` 가 요구하는 **맨몸 성적 표기가 월말에만** 있었다
- 옵션 만기일은 요약을 **CLI 에서** 조립해 `scripts/CLAUDE.md` 의 「CLI 에 도메인 로직 금지」에 걸렸다

**틀은 여섯 칸이고 그 안의 「무엇을 돌렸나」만 매매법이 채운다.**

| 키 | 무엇 | 누가 정하나 |
| --- | --- | --- |
| `track` | 매매법 이름(slug) | `studies/<slug>/constants.py` 의 `TRACK_NAME` |
| `datasets` | **대상 범위와 데이터 기간** — 코드·이름·파일·기간·거래일 수 | 이 모듈 (`dataset_record`) |
| `rule` | 무엇을 어떤 규칙으로 돌렸나 — 대상 칸·손절선·보유 한도와 **제외 건수** | 매매법 |
| `row_counts` | **파일 이름** → 행 수 | 매매법 (파일명 상수를 쓴다) |
| `cost` | 맨몸 성적 표기 | 이 모듈 (`COST_NOTE`) |
| `notes` | 산출물만 보고는 알 수 없는 실행 조건 | 매매법 |

**`rule` 안을 고정하지 않는 이유**는 매매법마다 실행 단위가 다르기 때문이다 — 역방향은
대상 × 순위 컷, 옵션 만기일은 종목 × 만기월 × 방향, 월말은 손절선 격자다. 억지로 한 모양에
맞추면 없는 칸을 비워 두거나 216개짜리 목록이 생긴다. **대신 제외 건수는 반드시 여기 담는다** —
집계표는 체결이 하나도 없는 대상의 행을 갖지 않아, 전부 제외되면 몇 건이 왜 빠졌는지가
어디에도 남지 않는다 (패키지 절대 원칙 「표본 보존」).

**`row_counts` 의 키를 파일 이름으로 두는 이유**: 전에는 `"summary"`·`"performance"` 같은
별칭이었고 스크립트가 그 문자열을 되짚었다. 작업 C 이후 `performance.csv` 라는 파일은
존재하지 않는데 키만 남아 있었다. 파일 이름으로 키잉하면 읽는 쪽이 파일명 상수를 그대로 쓴다.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

from verify_lab.common_constants import COL_DATE

# 비용을 넣지 않았다는 사실을 산출물에 남긴다. 「빠뜨린 것」과 「일부러 뺀 것」을
# 구별할 수 없으면 다음 사람이 다시 계산한다 (`.claude/rules/strategy.md`)
COST_NOTE: Final = "맨몸 성적 — 수수료·슬리피지·세금 미반영 (사용자 요청 시에만 반영)"

# ============================================================
# 최상위 키
# ============================================================

KEY_TRACK: Final = "track"
KEY_DATASETS: Final = "datasets"
KEY_RULE: Final = "rule"
KEY_ROW_COUNTS: Final = "row_counts"
KEY_COST: Final = "cost"
KEY_NOTES: Final = "notes"

# ============================================================
# 데이터셋 한 줄의 키
# ============================================================

# **`ticker` 는 종목코드이고 `label` 은 표시 이름이다.** 셋 다 같은 뜻을 쓴다 —
# 전에는 `studies/reverse`·`studies/option_expiry` 의 `ticker` 에 **표시 이름**이
# 들어 있어 역방향 요약이 `"ticker": "KODEX 200"` 이라고 적었다
KEY_DATASET_TICKER: Final = "ticker"
KEY_DATASET_LABEL: Final = "label"
KEY_DATASET_FILE: Final = "file"
KEY_DATASET_PERIOD: Final = "period"
KEY_DATASET_ROWS: Final = "rows"

# 기간 표기. 「시작 ~ 종료」이며 `.claude/rules/docs.md` 가 결과 문서에 요구하는 형식과 같다
PERIOD_SEPARATOR: Final = " ~ "


def dataset_record(*, ticker: str, label: str, file: str, frame: pd.DataFrame) -> dict[str, Any]:
    """데이터셋 한 줄을 만든다.

    **기간과 거래일 수를 시세에서 직접 읽는다.** 호출 측이 따로 세면 매매법마다 갈리고,
    결과 문서가 인용하는 「데이터 기간」이 실제 파일과 어긋나도 예외가 나지 않는다 —
    실제로 `docs/strategy/역방향_매매_규칙.md` 의 기간이 낡은 채로 남아 있었다.

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
        KEY_DATASET_PERIOD: f"{dates.iloc[0].date()}{PERIOD_SEPARATOR}{dates.iloc[-1].date()}",
        KEY_DATASET_ROWS: len(frame),
    }


def build_run_summary(
    *,
    track: str,
    datasets: Sequence[Mapping[str, Any]],
    rule: Mapping[str, Any],
    row_counts: Mapping[str, int],
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """실행 요약을 조립한다.

    **비용 표기를 인자로 받지 않는다.** 맨몸 성적이 기본이고 그 사실을 산출물에 남기는 것이
    규칙이므로, 매매법이 고를 수 있게 두면 한 곳만 빠져도 드러나지 않는다
    (`.claude/rules/strategy.md`). 비용을 넣기로 하면 그때 이 모듈을 고친다.

    Args:
        track: 매매법 이름(slug)
        datasets: `dataset_record` 로 만든 줄들. **비어 있으면 안 된다** — 범위의 SoT 다
        rule: 무엇을 어떤 규칙으로 돌렸나. **제외 건수를 여기 담는다**
        row_counts: 파일 이름 → 행 수. 키는 `strategy/constants.py` 의 파일명 상수를 쓴다
        notes: 산출물만 보고는 알 수 없는 실행 조건

    Returns:
        `summary.json` 에 그대로 저장할 사전

    Raises:
        ValueError: 매매법 이름이 비었거나, 데이터셋이 비었거나,
            행 수의 키가 파일 이름이 아닌 경우
    """
    if not track:
        raise ValueError("매매법 이름이 비어 있습니다")
    if not datasets:
        raise ValueError(f"데이터셋이 비어 있습니다 — 범위를 알 수 없습니다: {track}")

    # 별칭으로 되돌아가는 것을 막는다. `"performance"` 같은 키는 그 이름의 파일이 사라진
    # 뒤에도 남아 스크립트가 문자열로 되짚게 만들었다
    aliases = [key for key in row_counts if not key.endswith(".csv")]
    if aliases:
        raise ValueError(f"행 수의 키는 파일 이름이어야 합니다 (파일명 상수를 쓰세요): {aliases}")

    return {
        KEY_TRACK: track,
        KEY_DATASETS: [dict(record) for record in datasets],
        KEY_RULE: dict(rule),
        KEY_ROW_COUNTS: dict(row_counts),
        KEY_COST: COST_NOTE,
        KEY_NOTES: list(notes),
    }


__all__ = [
    "COST_NOTE",
    "KEY_COST",
    "KEY_DATASETS",
    "KEY_DATASET_FILE",
    "KEY_DATASET_LABEL",
    "KEY_DATASET_PERIOD",
    "KEY_DATASET_ROWS",
    "KEY_DATASET_TICKER",
    "KEY_NOTES",
    "KEY_ROW_COUNTS",
    "KEY_RULE",
    "KEY_TRACK",
    "build_run_summary",
    "dataset_record",
]
