"""로거 초기화의 이름·중복 방지·전파 차단 계약을 고정한다.

로거는 이름 기준 전역 싱글톤이라, 초기화를 두 번 하면 같은 로그가 두 번 찍힌다.
"""

import logging
from collections.abc import Iterator

import pytest

from verify_lab.utils.logger import get_logger, setup_logger

# 테스트가 만드는 로거의 이름 접두사. 정리 대상을 식별하는 데 쓴다
TEST_LOGGER_PREFIX = "verify_lab"


@pytest.fixture(autouse=True)
def clear_verify_lab_loggers() -> Iterator[None]:
    """테스트가 만든 로거의 핸들러를 비운다.

    로거는 전역 싱글톤이므로 앞선 테스트가 붙인 핸들러가 남으면 실행 순서에 따라
    결과가 달라진다.
    """
    yield

    for name in list(logging.Logger.manager.loggerDict):
        if name == TEST_LOGGER_PREFIX or name.startswith(f"{TEST_LOGGER_PREFIX}."):
            logging.getLogger(name).handlers.clear()


def test_default_logger_name_is_package_name() -> None:
    """
    목적: 인자 없이 초기화했을 때의 로거 이름을 고정한다.

    Given: 인자 없는 호출
    When: 로거를 초기화한다
    Then: 이름이 verify_lab 이다
    """
    assert setup_logger().name == "verify_lab"


def test_get_logger_default_name_matches_setup() -> None:
    """
    목적: 두 진입점의 기본 이름이 같음을 고정한다 (판정식 단일화).

    Given: 인자 없는 호출
    When: get_logger 로 로거를 가져온다
    Then: setup_logger 와 같은 이름이다
    """
    assert get_logger().name == setup_logger().name


def test_setup_does_not_duplicate_handlers() -> None:
    """
    목적: 두 번 초기화해도 핸들러가 늘지 않음을 고정한다 (로그 중복 출력 방지).

    Given: 같은 이름으로 두 번 초기화
    When: 핸들러 수를 확인한다
    Then: 1개다
    """
    # Given / When
    setup_logger("verify_lab.test.duplicate")
    logger = setup_logger("verify_lab.test.duplicate")

    # Then
    assert len(logger.handlers) == 1


def test_setup_returns_same_instance_for_same_name() -> None:
    """
    목적: 같은 이름이 같은 인스턴스를 돌려줌을 고정한다.

    Given: 같은 이름으로 두 번 초기화
    When: 두 반환값을 비교한다
    Then: 동일 객체다
    """
    first = setup_logger("verify_lab.test.same")
    second = setup_logger("verify_lab.test.same")

    assert first is second


def test_get_logger_initializes_when_unconfigured() -> None:
    """
    목적: 설정된 적 없는 이름으로 호출해도 핸들러가 붙음을 고정한다 (지연 초기화).

    Given: 아직 초기화되지 않은 로거 이름
    When: get_logger 로 가져온다
    Then: 핸들러가 1개 붙어 있다
    """
    logger = get_logger("verify_lab.test.lazy")

    assert len(logger.handlers) == 1


def test_propagation_is_disabled() -> None:
    """
    목적: 상위 로거로 전파되지 않음을 고정한다 (중복 출력 방지).

    Given: 초기화된 로거
    When: propagate 를 확인한다
    Then: False 다
    """
    assert setup_logger("verify_lab.test.propagate").propagate is False


def test_level_is_debug() -> None:
    """
    목적: 로거 레벨이 DEBUG 로 고정됨을 확인한다.

    레벨을 인자로 받지 않는다 — 호출부가 전부 기본값만 썼고, 레벨을 낮추면
    비즈니스 로직의 실행 흐름 로그가 통째로 사라진다.

    Given: 새 이름의 로거
    When: 초기화한다
    Then: 레벨이 DEBUG 다
    """
    assert setup_logger("verify_lab.test.default_level").level == logging.DEBUG
