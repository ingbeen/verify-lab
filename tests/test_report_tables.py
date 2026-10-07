"""표시용 표의 계약을 고정한다.

이 계층이 하는 일은 계산이 아니라 **번역과 렌더링**이다. 영문 헤더를 한글 레이블로 바꾸며 단위를
맞추고, 표를 터미널에 그린다. 번역이 흔들리면 사용자가 화면에서 본 숫자를 CSV 에서 찾지 못하고,
그러면 "사용자가 직접 검증할 수 있어야 한다"는 전제가 무너진다.

핵심 계약은 세 가지다.
- 저장 직전 변환은 사전이 표의 모든 컬럼을 덮어야 하고, 비율은 **백분율 2자리**, 확률은 4자리다
- 두 컬럼이 같은 헤더로 접히면 저장 전에 막는다
- 터미널 출력은 표시 폭으로 정렬하고, 결측은 표시 문자로 찍는다
"""

import logging

import pandas as pd
import pytest

from verify_lab.report.constants import DISPLAY_TEST_NOTE, EMPTY_MARK
from verify_lab.report.tables import print_dataframe, to_display_columns
from verify_lab.utils.formatting import get_display_width


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
        table = pd.DataFrame({"평균 우연확률": [float("nan")], DISPLAY_TEST_NOTE: ["표본 부족으로 검정 불가"]})
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


class TestDisplayColumns:
    """저장 직전 한글 변환의 계약을 고정한다.

    이 계약이 없으면 `DISPLAY_*` 를 정의해두고 `rename` 에 연결하지 않는 실수가 조용히 지나간다 —
    실제로 옵션_만기일이 그렇게 영문 헤더로 나간 적이 있다.
    """

    def test_사전대로_한글_헤더가_붙는다(self) -> None:
        """
        목적: 저장용 표의 컬럼이 한글 레이블로 바뀐다.

        Given: 영문 컬럼 두 개와 그 한글 사전
        When: 변환하면
        Then: 헤더가 한글이고 값과 순서는 그대로다
        """
        # Given
        table = pd.DataFrame({"ticker": ["QQQ"], "SampleCount": [27]})
        labels = {"ticker": "종목", "SampleCount": "표본"}

        # When
        result = to_display_columns(table, labels)

        # Then
        assert list(result.columns) == ["종목", "표본"]
        assert result["종목"].iloc[0] == "QQQ"
        assert int(result["표본"].iloc[0]) == 27

    def test_사전에_없는_컬럼이_있으면_예외다(self) -> None:
        """
        목적: **이 테스트가 이 계약의 존재 이유다.** 컬럼을 새로 추가하고 한글 이름을 안 만들면
              영문 헤더가 그대로 사용자에게 나간다. 조용히 통과시키지 않고 즉시 실패시킨다.

        Given: 사전에 없는 컬럼이 섞인 표
        When: 변환하면
        Then: ValueError 가 나고 메시지에 빠진 컬럼 이름이 담긴다
        """
        # Given
        table = pd.DataFrame({"ticker": ["QQQ"], "NewColumn": [1]})
        labels = {"ticker": "종목"}

        # When / Then
        with pytest.raises(ValueError, match="NewColumn"):
            to_display_columns(table, labels)

    def test_원본_표를_바꾸지_않는다(self) -> None:
        """
        목적: 데이터 불변성. 변환이 원본을 건드리면 같은 표를 두 번 쓰는 자리에서 깨진다.

        Given: 영문 컬럼 표
        When: 변환하면
        Then: 원본의 컬럼은 그대로다
        """
        # Given
        table = pd.DataFrame({"ticker": ["QQQ"]})

        # When
        to_display_columns(table, {"ticker": "종목"})

        # Then
        assert list(table.columns) == ["ticker"]

    def test_빈_표는_예외다(self) -> None:
        """
        목적: 빈 표를 조용히 내보내지 않는다 (`save_table` 과 같은 정책).

        Given: 행이 없는 표
        When: 변환하면
        Then: ValueError
        """
        with pytest.raises(ValueError, match="비어"):
            to_display_columns(pd.DataFrame({"ticker": []}), {"ticker": "종목"})

    def test_비율_컬럼이_백분율로_바뀐다(self) -> None:
        """
        목적: 헤더에 `(%)` 를 붙이면 값도 백분율이어야 한다. 이름과 단위가 어긋나면
              사용자가 0.003 을 3% 로 읽거나 그 반대로 읽는다.

        Given: 비율 0.003123 이 담긴 컬럼
        When: 백분율 컬럼으로 지목해 변환하면
        Then: 0.31 (%) 이 된다 (백분율 2자리)
        """
        # Given
        table = pd.DataFrame({"Mean": [0.003123]})

        # When
        result = to_display_columns(table, {"Mean": "평균(%)"}, percent_columns=["Mean"])

        # Then
        assert float(result["평균(%)"].iloc[0]) == pytest.approx(0.31, abs=1e-9)

    def test_확률_컬럼은_자릿수만_맞춘다(self) -> None:
        """
        목적: 우연확률은 비율이 아니라 확률이므로 100 을 곱하지 않는다.

        Given: 우연확률 0.0029970
        When: 확률 컬럼으로 지목해 변환하면
        Then: 값이 그대로이고 자릿수만 맞는다
        """
        # Given
        table = pd.DataFrame({"PValue": [0.0029970]})

        # When
        result = to_display_columns(table, {"PValue": "우연확률"}, probability_columns=["PValue"])

        # Then
        assert float(result["우연확률"].iloc[0]) == pytest.approx(0.003, abs=1e-9)

    def test_변환_대상이_표에_없으면_예외다(self) -> None:
        """
        목적: 컬럼 이름을 잘못 적으면 **조용히 변환되지 않은 채 나간다.** 즉시 실패시킨다.

        Given: 표에 없는 컬럼을 백분율 대상으로 지목
        When: 변환하면
        Then: ValueError
        """
        with pytest.raises(ValueError, match="Missing"):
            to_display_columns(pd.DataFrame({"Mean": [0.01]}), {"Mean": "평균(%)"}, percent_columns=["Missing"])


class TestNullableIntegerCells:
    """결측을 담는 정수형 칸 — 화면 출력이 터지지 않는다"""

    def test_결측_정수_칸이_빈칸으로_찍힌다(self, caplog: pytest.LogCaptureFixture) -> None:
        """
        목적: `Int64` 의 `pd.NA` 를 화면에 낼 수 있음을 고정한다 (재현 테스트).

        건수 컬럼을 결측을 담는 정수형으로 바꾸자 **터미널 출력이 터졌다** —
        `pd.NA == ""` 는 참도 거짓도 아닌 `pd.NA` 를 돌려주고, 그것을 `if` 가 평가하면
        `TypeError: boolean value of NA is ambiguous` 가 난다.
        **테스트가 이 경로를 안 밟아서 재실행에서야 드러났다.**

        Given: 결측이 섞인 `Int64` 컬럼을 가진 표
        When: 화면에 출력한다
        Then: 예외 없이 찍히고 결측 칸이 표시 문자가 된다
        """
        # Given
        table = pd.DataFrame({"신호": pd.array([51, 25], dtype="Int64"), "제외": pd.array([0, None], dtype="Int64")})

        # When
        with caplog.at_level(logging.DEBUG):
            print_dataframe(table, logging.getLogger("test_nullable"))

        # Then
        rendered = caplog.text
        assert "51" in rendered
        assert EMPTY_MARK in rendered


class TestDisplayColumnsRejectDuplicateHeaders:
    """두 컬럼이 **같은 헤더로 접히는** 것을 저장 전에 막는다

    pandas 는 `rename` 으로 이름이 겹쳐도 예외를 내지 않고 **같은 이름의 컬럼 둘**을 만든다.
    그대로 저장하면 CSV 에 `보유 거래일,보유 거래일` 이 나가고, 읽는 쪽은 어느 것이 무엇인지
    알 수 없다. **에러도 경고도 없는 손상**이라 파일을 열어보기 전에는 발견되지 않는다.

    사전에 같은 값을 가진 키가 둘 있는 것 자체는 정당하다 — 한 표에 함께 나오지 않으면
    겹치지 않는다. 그래서 판정은 사전이 아니라 **결과 프레임의 헤더**로 한다.
    """

    def test_같은_헤더로_접히면_거부한다(self) -> None:
        """
        목적: 「조용히 중복 컬럼이 저장되는」 경로를 닫는다.

        Given: 두 컬럼이 같은 레이블을 가리키는 표
        When: 변환하면
        Then: ValueError 가 나고 메시지에 겹친 헤더 이름이 담긴다
        """
        # Given
        table = pd.DataFrame({"hold_days": [5], "horizon": [-1]})
        labels = {"hold_days": "보유 거래일", "horizon": "보유 거래일"}

        # When / Then
        with pytest.raises(ValueError, match="보유 거래일"):
            to_display_columns(table, labels)

    def test_사전에_같은_값이_있어도_한_표에_없으면_통과한다(self) -> None:
        """
        목적: 정당한 동일값 쌍을 막지 않는다.

        `futures_leverage` 의 `Date`·`StartDate` 가 둘 다 `시작일` 인데 **한 표에 같이 나오지
        않는다.** 사전으로 판정하면 이 정상 호출이 막힌다.

        Given: 같은 값을 가진 키가 둘 있지만 표에는 하나만 있는 경우
        When: 변환하면
        Then: 그대로 변환된다
        """
        # Given
        table = pd.DataFrame({"Date": ["2026-01-02"]})
        labels = {"Date": "시작일", "StartDate": "시작일"}

        # When
        result = to_display_columns(table, labels)

        # Then
        assert list(result.columns) == ["시작일"]
