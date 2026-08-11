"""KRX 로그인 자격증명 로딩

pykrx 는 KRX 데이터포털 계정 없이는 아무것도 조회하지 못하며, 계정을 **환경 변수로만** 읽는다.
`.env` 파일은 읽지 않는다. 이 모듈이 그 사이를 잇는 유일한 지점이다.

자격증명의 단일 출처는 저장소 루트의 `.env` 다. 셸 환경 변수가 이미 설정돼 있어도 `.env` 값으로
덮어써서, 어느 환경에서 실행하든 같은 계정을 쓰도록 고정한다.

**이 모듈은 pykrx 를 import 하지 않는다.** `import pykrx` 자체가 로그인 시도를 일으키므로,
자격증명 로딩이 그보다 먼저 끝나야 한다. 여기서 pykrx 를 import 하면 그 순서가 무너진다.
호출 측이 지켜야 할 순서는 `scripts/data/check_pykrx_etf.py` 를 참고한다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from verify_lab.common_constants import BASE_DIR
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# KRX 데이터포털 로그인 환경 변수. 이름은 pykrx 가 정한 것이라 바꿀 수 없다
ENV_KRX_ID = "KRX_ID"
ENV_KRX_PW = "KRX_PW"

REQUIRED_KEYS = (ENV_KRX_ID, ENV_KRX_PW)

# 자격증명 파일. git 에서 제외돼 있으며 이 파일에서만 참조한다
ENV_FILE_PATH = BASE_DIR / ".env"


def load_krx_credentials(path: Path = ENV_FILE_PATH) -> None:
    """`.env` 에서 KRX 자격증명을 읽어 환경 변수에 설정한다.

    **pykrx 를 import 하기 전에 호출해야 한다.** import 시점에 로그인이 시도되기 때문이다.

    예외 메시지에는 경로와 빠진 키 이름만 담고 **값은 담지 않는다.** 예외 메시지는 로그와
    스택 트레이스에 남고 그 로그는 공유된다.

    Args:
        path: 자격증명 파일 경로. 기본값은 저장소 루트의 `.env`

    Raises:
        ValueError: 파일이 없거나, 필수 키가 없거나, 값이 비어 있는 경우
    """
    if not path.is_file():
        raise ValueError(f"KRX 자격증명 파일이 없습니다: {path} (data.krx.co.kr 계정을 담은 .env 를 만드십시오)")

    # override=True: 셸 환경 변수보다 .env 를 우선한다.
    # 셸에 남아 있던 옛 값이 이기면 "어제는 됐는데 오늘은 안 되는" 상황이 생긴다
    load_dotenv(path, override=True)

    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        raise ValueError(f"{path} 에 값이 비어 있습니다: {', '.join(missing)}")

    logger.debug(f"KRX 자격증명을 환경 변수에 설정했습니다 (출처: {path})")
