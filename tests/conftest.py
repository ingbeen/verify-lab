"""테스트 공통 픽스처

파일을 쓰는 기능은 프로덕션 경로(`storage/`)를 건드리지 않도록 `tmp_path`로 격리한다.
look-ahead 감시 계약은 이벤트 정의가 늘 때마다 같은 형태로 재사용되므로 여기에 둔다.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
import pytest

from verify_lab import common_constants
from verify_lab.utils import meta_manager

# 수학적으로 정확해야 하는 값의 허용오차 (tests/CLAUDE.md 허용오차 기준)
EXACT_TOLERANCE = 1e-12


@pytest.fixture
def mock_meta_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """실행 메타데이터 경로를 임시 디렉터리로 격리한다.

    `meta_manager`는 `from ... import META_JSON_PATH` 형태로 import 시점에 경로 값을
    자기 모듈에 캡처한다. 따라서 `common_constants`만 패치하면 이미 캡처된 실제 경로가
    그대로 쓰인다. 두 모듈을 함께 패치해야 격리가 성립한다.

    Args:
        tmp_path: pytest가 테스트마다 새로 만드는 임시 디렉터리
        monkeypatch: 테스트 종료 시 원복을 보장하는 pytest 패치 도구

    Returns:
        격리된 meta.json 경로 (아직 파일은 생성되지 않은 상태)
    """
    meta_json_path = tmp_path / "results" / "meta.json"

    monkeypatch.setattr(common_constants, "META_JSON_PATH", meta_json_path)
    monkeypatch.setattr(meta_manager, "META_JSON_PATH", meta_json_path)

    return meta_json_path


@pytest.fixture
def assert_stable_under_truncation() -> Callable[..., None]:
    """look-ahead 감시 계약을 검사하는 함수를 돌려준다.

    계약은 **"뒤를 잘라낸 입력의 결과가 전체 입력의 결과와 겹치는 범위에서 같다"** 이다.
    미래 데이터가 있든 없든 판정이 달라지지 않아야 미래를 참조하지 않는 것이다.

    비교 대상은 **짧은 입력에서 값이 있는 칸**뿐이다. forward return 은 정의상 미래를 보므로
    뒤를 자르면 그 구간이 "제외"로 바뀌는 것이 정상이고, 그 칸까지 비교하면 계약이 항상 실패한다.
    반대로 이벤트 판정(bool)은 빈 칸이 없으므로 같은 함수로 겹치는 구간 전체가 비교된다.

    Returns:
        `(run, df, cut, key_columns, value_column)` 를 받아 계약을 검사하는 함수.
        `run` 은 시세 DataFrame 하나를 받아 결과 DataFrame 을 내는 호출 가능 객체다
    """

    def _assert(
        run: Callable[[pd.DataFrame], pd.DataFrame],
        df: pd.DataFrame,
        cut: int,
        *,
        key_columns: Sequence[str],
        value_column: str,
    ) -> None:
        keys = list(key_columns)
        truncated = run(df.iloc[:cut])
        whole = run(df)

        merged = truncated.merge(whole, on=keys, how="left", suffixes=("_truncated", "_whole"))
        assert len(merged) == len(truncated), "결과 키가 중복돼 비교가 성립하지 않습니다"

        short_values = merged[f"{value_column}_truncated"]
        compared = merged[short_values.notna()]
        assert not compared.empty, "비교할 칸이 하나도 없습니다 — 자르는 위치를 뒤로 옮기세요"

        unmatched = compared[compared[f"{value_column}_whole"].isna()]
        assert unmatched.empty, f"전체 입력에 없는 칸이 있습니다:\n{unmatched[keys]}"

        assert compared[f"{value_column}_truncated"].tolist() == pytest.approx(
            compared[f"{value_column}_whole"].tolist(), abs=EXACT_TOLERANCE
        ), "뒤를 잘라낸 입력과 전체 입력의 값이 다릅니다 — 미래 데이터를 참조하고 있습니다"

    return _assert
