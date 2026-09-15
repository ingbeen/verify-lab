"""매매 실행 요약 — 매매법을 가리지 않는 공유 계층

`summary.json` 에 담을 내용을 조립한다. 저장은 `report/writer.save_run_summary` 가 한다.

**세 매매법이 같은 틀을 쓴다 — 매매법마다 구조를 만들지 않는다.** 만드는 자리와 키가
갈리면 세 가지가 조용히 어긋난다.

- `src/verify_lab/CLAUDE.md` 가 **「범위의 SoT 는 `summary.json` 의 `datasets`」**라고
  선언하는데 그 키를 가진 매매법과 안 가진 매매법이 갈린다 — 안 가진 쪽은 종목코드를
  어디에도 남기지 않는다
- `.claude/rules/trading.md` 가 요구하는 **맨몸 성적 표기**가 한 매매법에만 실린다
- 요약을 **CLI 에서** 조립하면 `scripts/CLAUDE.md` 의 「CLI 에 도메인 로직 금지」에 걸린다

**틀은 여섯 칸이고 그 안의 「무엇을 돌렸나」만 매매법이 채운다.**

| 키 | 무엇 | 누가 정하나 |
| --- | --- | --- |
| `track` | 매매법 이름(slug) | `studies/<slug>/constants.py` 의 `TRACK_NAME` |
| `datasets` | **대상 범위와 데이터 기간** — 코드·이름·파일·기간·거래일 수 | `report/run_summary.dataset_record` |
| `rule` | 무엇을 어떤 규칙으로 돌렸나 — 대상 칸·손절선·보유 한도와 **제외 건수** | 매매법 |
| `row_counts` | **파일 이름** → 행 수 | 매매법 (파일명 상수를 쓴다) |
| `cost` | 맨몸 성적 표기 | 이 모듈 (`COST_NOTE`) |
| `notes` | 산출물만 보고는 알 수 없는 실행 조건 | 매매법 |

**`rule` 안을 고정하지 않는 이유**는 매매법마다 실행 단위가 다르기 때문이다 — 역방향은
대상 × 순위 컷, 옵션 만기일은 종목 × 만기월 × 방향, 월말은 손절선 격자다. 억지로 한 모양에
맞추면 없는 칸을 비워 두거나 216개짜리 목록이 생긴다. **대신 제외 건수는 반드시 여기 담는다** —
집계표는 체결이 하나도 없는 대상의 행을 갖지 않아, 전부 제외되면 몇 건이 왜 빠졌는지가
어디에도 남지 않는다 (패키지 절대 원칙 「표본 보존」).

**`row_counts` 의 키를 파일 이름으로 두는 이유**: `"summary"`·`"performance"` 같은 별칭을
쓰면 스크립트가 그 문자열을 되짚어야 하고, **그 이름의 파일이 사라져도 키만 남는다.**
파일 이름으로 키잉하면 읽는 쪽이 파일명 상수를 그대로 쓴다.

**데이터셋 한 줄은 여기서 만들지 않는다.** `report/run_summary.dataset_record` 가 소유하며
검증 계층도 같은 함수를 쓴다 — 이 모듈이 소유하면 `studies` 가 쓸 수 없어
(`studies → strategy` 는 계층 방향을 뒤집는다) **구현이 검증마다 한 벌씩 늘어난다.**
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from verify_lab.report.run_summary import KEY_TRACK

# 비용을 넣지 않았다는 사실을 산출물에 남긴다. 「빠뜨린 것」과 「일부러 뺀 것」을
# 구별할 수 없으면 다음 사람이 다시 계산한다 (`.claude/rules/trading.md`)
COST_NOTE: Final = "맨몸 성적 — 수수료·슬리피지·세금 미반영 (사용자 요청 시에만 반영)"

# ============================================================
# 최상위 키
# ============================================================

# `KEY_TRACK` 는 `report/run_summary.py` 가 소유한다 — 조사 검증이 이 모듈을 쓰지 않기 때문
KEY_DATASETS: Final = "datasets"
KEY_RULE: Final = "rule"
KEY_ROW_COUNTS: Final = "row_counts"
KEY_COST: Final = "cost"
KEY_NOTES: Final = "notes"

# 한 실행이 측정과 체결을 함께 내므로 요약도 한 벌이다. **두 벌을 평평하게 합치지 않고**
# 이 두 칸 아래로 나눠 담는다 — `datasets`·`rule`·`notes` 가 같은 이름인데 다른 것을 가리킨다
KEY_MEASURE: Final = "measure"
KEY_TRADE: Final = "trade"


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
    (`.claude/rules/trading.md`). 비용을 넣기로 하면 그때 이 모듈을 고친다.

    Args:
        track: 매매법 이름(slug)
        datasets: `report.run_summary.dataset_record` 로 만든 줄들.
            **비어 있으면 안 된다** — 범위의 SoT 다
        rule: 무엇을 어떤 규칙으로 돌렸나. **제외 건수를 여기 담는다**
        row_counts: 파일 이름 → 행 수. 키는 `execution/constants.py` 의 파일명 상수를 쓴다
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


def merge_run_summary(measure: Mapping[str, Any], trade: Mapping[str, Any]) -> dict[str, Any]:
    """한 매매법의 측정 요약과 체결 요약을 **한 벌로** 합친다.

    **폴더 하나에 `summary.json` 도 하나다.** 등급(검증·매매)은 분류일 뿐이라 한 실행이
    측정과 체결을 함께 내므로, 요약을 두 벌 두면 **어느 쪽이 그 폴더의 것인지 판별할 수 없다.**

    **두 요약을 평평하게 합치지 않는다.** `datasets`·`rule`·`notes` 는 같은 이름인데 다른
    것을 가리킨다 — 측정 범위와 매매 범위가 갈릴 수 있고(월말은 매매가 더 좁다), 규칙도
    한쪽은 격자 축이고 다른 쪽은 손절선이다. 평평하게 합치면 **뒤에 온 쪽이 앞을 덮는데
    예외가 나지 않는다.**

    Args:
        measure: 측정 요약 (`studies/<slug>/runner.py` 가 낸 것)
        trade: 체결 요약 (`build_run_summary` 가 낸 것)

    Returns:
        `summary.json` 에 그대로 저장할 사전

    Raises:
        ValueError: 두 요약의 매매법 이름이 다르거나, 행 수의 키가 겹치는 경우
    """
    measure_track = measure.get(KEY_TRACK)
    trade_track = trade.get(KEY_TRACK)
    if measure_track != trade_track:
        raise ValueError(f"두 요약의 매매법 이름이 다릅니다: 측정 {measure_track!r} · 체결 {trade_track!r}")

    measure_counts: Mapping[str, int] = measure.get(KEY_ROW_COUNTS, {})
    trade_counts: Mapping[str, int] = trade.get(KEY_ROW_COUNTS, {})

    # **겹치면 한 표가 다른 표를 덮는다.** 저장도 행 수도 조용히 한 칸 줄어든다
    collided = sorted(set(measure_counts) & set(trade_counts))
    if collided:
        raise ValueError(f"측정과 체결이 같은 파일 이름을 씁니다: {collided}")

    nested_out = (KEY_TRACK, KEY_ROW_COUNTS, KEY_COST)

    return {
        KEY_TRACK: measure_track,
        KEY_ROW_COUNTS: {**measure_counts, **trade_counts},
        KEY_COST: COST_NOTE,
        KEY_MEASURE: {key: value for key, value in measure.items() if key not in nested_out},
        KEY_TRADE: {key: value for key, value in trade.items() if key not in nested_out},
    }


__all__ = [
    "COST_NOTE",
    "KEY_COST",
    "KEY_DATASETS",
    "KEY_MEASURE",
    "KEY_NOTES",
    "KEY_ROW_COUNTS",
    "KEY_RULE",
    "KEY_TRADE",
    "build_run_summary",
    "merge_run_summary",
]
