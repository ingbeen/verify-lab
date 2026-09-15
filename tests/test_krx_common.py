"""KRX 세 수집기가 공유하는 판정 (`data/krx_common.py`)

전에는 이 판정들이 `etn`·`krx_futures` 에 복사본으로, `pykrx_collector` 에 인라인 세 벌로
있었다. **한 벌이 된 지금은 이 파일이 그 판정의 유일한 산식 고정 자리**다 —
세 수집기의 테스트가 각자 같은 것을 다시 재면 픽스처가 갈리는 만큼 판정도 갈린다.
"""

from datetime import date

import pandas as pd
import pytest

from verify_lab.common_constants import COL_DATE
from verify_lab.data.constants import DOMESTIC_RECENT_EXCLUSION_DAYS, START_DATE_LABEL
from verify_lab.data.krx_common import exclude_recent, to_numeric, validate_krx_date


class TestToNumeric:
    """숫자 변환 — 값이 없는 칸을 0 으로 채우지 않는다"""

    def test_값이_없는_칸은_결측으로_남는다(self) -> None:
        """
        목적: `-` 를 0 으로 채우지 않는 정책을 고정한다.
        0 으로 채우면 「가격 0」인 날이 생겨 이상치 검사를 통과해 버린다.

        Given: 쉼표가 붙은 숫자와 `-` 가 섞인 컬럼
        When: 숫자로 바꾼다
        Then: `-` 는 NaN 이고 나머지는 값이 된다
        """
        # Given
        series = pd.Series(["1,015.00", "-", "800"])

        # When
        converted = to_numeric(series)

        # Then
        assert converted.isna().tolist() == [False, True, False]
        assert converted.iloc[0] == pytest.approx(1015.0)
        assert converted.iloc[2] == pytest.approx(800.0)

    def test_쉼표가_여러_개여도_전부_뗀다(self) -> None:
        """
        목적: 천 단위 구분이 둘 이상인 값도 온전히 변환됨을 고정한다.

        Given: 쉼표가 둘 있는 값
        When: 숫자로 바꾼다
        Then: 쉼표를 전부 뗀 값이 된다
        """
        # Given
        series = pd.Series(["1,234,567"])

        # When
        converted = to_numeric(series)

        # Then
        assert converted.iloc[0] == pytest.approx(1234567.0)


class TestExcludeRecent:
    """최근 구간 제외 — 경계와 건수를 세 수집기가 같은 산식으로 쓴다"""

    def test_기준일보다_늦은_행이_빠지고_건수가_돌아온다(self) -> None:
        """
        목적: 제외 경계와 건수 보고를 함께 고정한다.
        건수를 내지 않으면 조용히 줄어든 표본이 생존편향을 만든다 (표본 보존).

        Given: 경계 앞뒤에 걸친 날짜
        When: 최근 구간을 제외한다
        Then: 경계 이후가 빠지고 빠진 행 수가 함께 돌아온다
        """
        # Given
        today = date(2026, 9, 10)
        cutoff = date(2026, 9, 10 - DOMESTIC_RECENT_EXCLUSION_DAYS)
        df = pd.DataFrame({COL_DATE: [date(2026, 9, 1), cutoff, today]})

        # When
        trimmed, excluded = exclude_recent(df, today)

        # Then
        assert trimmed[COL_DATE].tolist() == [date(2026, 9, 1), cutoff]
        assert excluded == 1

    def test_경계일은_남는다(self) -> None:
        """
        목적: 경계가 「이하」임을 고정한다.
        「미만」으로 바뀌면 확정된 하루가 매번 조용히 더 빠진다.

        Given: 경계일 하나뿐인 표
        When: 최근 구간을 제외한다
        Then: 그 행이 남고 제외 건수가 0 이다
        """
        # Given
        today = date(2026, 9, 10)
        cutoff = date(2026, 9, 10 - DOMESTIC_RECENT_EXCLUSION_DAYS)
        df = pd.DataFrame({COL_DATE: [cutoff]})

        # When
        trimmed, excluded = exclude_recent(df, today)

        # Then
        assert len(trimmed) == 1
        assert excluded == 0

    def test_입력을_변경하지_않는다(self) -> None:
        """
        목적: 원본 불변을 고정한다 (`~/.claude/rules/python.md` 데이터 불변성).

        **행 수만 세지 않는다** — 값이나 인덱스를 제자리에서 고치는 구현은 행 수를 유지하므로
        세기만 해서는 통과해 버린다.

        Given: 제외 대상이 있는 표
        When: 최근 구간을 제외한다
        Then: 입력이 호출 전과 전 셀 같다
        """
        # Given
        today = date(2026, 9, 10)
        df = pd.DataFrame({COL_DATE: [date(2026, 9, 3), date(2026, 9, 1), today]})
        before = df.copy()

        # When
        exclude_recent(df, today)

        # Then
        pd.testing.assert_frame_equal(df, before)


class TestValidateKrxDate:
    """날짜 형식 검증 — 어느 인자가 틀렸는지를 메시지가 말한다"""

    def test_형식이_맞으면_통과한다(self) -> None:
        """
        목적: 정상 입력이 막히지 않음을 고정한다.

        Given: YYYYMMDD 형식의 날짜
        When: 검증한다
        Then: 예외가 나지 않는다
        """
        # Given · When · Then
        validate_krx_date(START_DATE_LABEL, "20260910")

    @pytest.mark.parametrize("value", ["2026-09-10", "20260931", "", "일이삼사오육칠팔"])
    def test_형식이_틀리면_라벨과_함께_거부한다(self, value: str) -> None:
        """
        목적: 잘못된 형식이 `ValueError` 로 즉시 막히고 **어느 인자인지가 메시지에 남음**을
        고정한다. 선물 수집기는 인자가 둘(훑기 시작일·훑기 종료일)이라 라벨이 없으면
        어느 쪽이 틀렸는지 알 수 없다.

        Given: 형식이 잘못된 날짜
        When: 라벨을 붙여 검증한다
        Then: 그 라벨이 든 `ValueError` 가 난다
        """
        # Given · When · Then
        with pytest.raises(ValueError, match="훑기 종료일 형식이 잘못되었습니다"):
            validate_krx_date("훑기 종료일", value)
