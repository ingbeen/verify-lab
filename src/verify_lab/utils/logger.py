"""로깅 설정

로그 포맷: `시간 · 레벨 · [파일:줄] · [함수명] · 메시지`

**파일 경로를 저장소 루트 기준 상대 경로로 찍는다.** VSCode 터미널에서 `경로:줄번호` 가
클릭 가능한 형태라, 로그를 읽다가 그 자리로 바로 갈 수 있다.

레벨 정책은 `.claude/rules/python.md` 를 따른다 — 비즈니스 로직은 DEBUG·WARNING 만 쓰고
ERROR 는 CLI 계층이 예외를 받을 때만 쓴다.
"""

import logging
import sys
from pathlib import Path
from typing import Any

# 저장소 루트를 찾을 때 거슬러 올라가는 최대 깊이. 무한 루프를 막는 상한이며
# 실제로는 두세 단계에서 끝난다
_MAX_ROOT_SEARCH_DEPTH = 10

# 저장소 루트임을 알려주는 표지. 둘 중 하나만 있어도 루트로 본다
_ROOT_MARKERS = ("pyproject.toml", ".git")

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s [%(location)s] [%(funcName)s] : %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ClickableFormatter(logging.Formatter):
    """로그에 저장소 루트 기준 상대 경로를 붙이는 포맷터

    `record.location` 을 만들어 포맷 문자열이 쓸 수 있게 한다.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        """포맷터를 만들고 저장소 루트를 미리 찾아 둔다."""
        super().__init__(*args, **kwargs)
        self.project_root = self._find_project_root()

    def _find_project_root(self) -> Path:
        """이 파일에서 위로 올라가며 저장소 루트를 찾는다.

        **찾지 못해도 예외를 던지지 않는다.** 로깅 초기화에서 멈추면 정작 원인을 알려줄
        로그가 하나도 안 나온다. 저장소 안에서만 실행되므로 이 자리에 도달하지 않으며,
        도달하더라도 잃는 것은 로그 경로가 상대에서 절대로 바뀌는 것뿐이다.

        Returns:
            루트 경로. 찾지 못하면 현재 작업 디렉터리
        """
        current = Path(__file__).resolve().parent

        for _ in range(_MAX_ROOT_SEARCH_DEPTH):
            if any((current / marker).exists() for marker in _ROOT_MARKERS):
                return current

            parent = current.parent
            if parent == current:
                break
            current = parent

        return Path.cwd()

    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드에 `location` 을 채우고 문자열로 만든다.

        저장소 밖의 파일(외부 라이브러리)은 상대 경로로 바꿀 수 없으므로 절대 경로를 쓴다.

        Args:
            record: 로그 레코드

        Returns:
            포맷팅된 로그 문자열
        """
        pathname = Path(record.pathname)

        try:
            relative_path = pathname.relative_to(self.project_root)
        except ValueError:
            relative_path = pathname

        record.location = f"{relative_path}:{record.lineno}"

        return super().format(record)


def setup_logger(name: str = "verify_lab") -> logging.Logger:
    """로거를 만들고 콘솔 핸들러를 붙인다.

    **이미 핸들러가 있으면 그대로 돌려준다.** 다시 붙이면 같은 줄이 두 번 찍힌다.

    Args:
        name: 로거 이름

    Returns:
        설정된 로거
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ClickableFormatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
    logger.addHandler(console_handler)

    # 상위 로거로 전파하지 않는다. 전파하면 루트 로거가 같은 줄을 한 번 더 찍는다
    logger.propagate = False

    return logger


def get_logger(name: str = "verify_lab") -> logging.Logger:
    """설정된 로거를 가져오고, 없으면 그때 만든다.

    Args:
        name: 로거 이름

    Returns:
        로거
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger = setup_logger(name)

    return logger
