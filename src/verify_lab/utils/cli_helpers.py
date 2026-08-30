"""CLI 스크립트 공통 헬퍼

실행 스크립트의 `main()` 에서 예외를 일관되게 처리하는 데코레이터를 제공한다.
비즈니스 로직은 예외를 그대로 던지고(`src/verify_lab/CLAUDE.md` 계층 분리),
**ERROR 로그와 종료 코드는 CLI 계층인 여기서만** 다룬다.
"""

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any


def cli_exception_handler(func: Callable[[], int]) -> Callable[[], int]:
    """`main()` 의 예외를 잡아 스택 트레이스와 함께 남기고 실패 코드를 돌려준다.

    로거는 **함수가 정의된 모듈의 최상위 `logger` 변수**를 찾아 쓴다. 그래야 로그의
    발생 위치가 실제 스크립트로 찍힌다.

    예외 메시지는 스택 트레이스에 이미 들어 있으므로 따로 출력하지 않는다.

    Args:
        func: 실행 스크립트의 `main()` (성공 시 0 을 돌려준다)

    Returns:
        예외를 처리하는 래퍼. 실패하면 1 을 돌려준다

    Raises:
        RuntimeError: 대상 모듈에 `logger` 가 없는 경우.
            모든 실행 스크립트가 모듈 레벨 로거를 두는 것이 이 저장소의 관용이므로,
            없다는 것은 스크립트 구성이 잘못됐다는 뜻이다
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> int:
        module = inspect.getmodule(func)
        logger: logging.Logger | None = getattr(module, "logger", None)

        if logger is None:
            raise RuntimeError(f"내부 불변조건 위반: 모듈에 logger 가 없습니다 - {func.__module__}.{func.__qualname__}")

        try:
            return func(*args, **kwargs)

        except Exception:
            logger.error("예외 발생", exc_info=True)

            return 1

    return wrapper
