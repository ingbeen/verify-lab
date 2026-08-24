"""ECOS 인증키 로딩

한국은행 ECOS 오픈API 는 인증키를 **요청 URL 경로에 넣는다.** 그래서 이 모듈은
KRX 자격증명과 두 가지가 다르다.

1. **환경 변수로 올리지 않고 값으로 돌려준다.** `os.environ` 에 올리면 이후 실행되는
   모든 하위 프로세스가 키를 상속받는데, ECOS 는 그럴 이유가 없다.
   (`krx_credentials.py` 가 환경 변수를 쓰는 것은 pykrx 가 그 방식만 읽기 때문이며,
   그 제약은 여기 해당하지 않는다.)
2. **마스킹 함수를 함께 제공한다.** 요청 URL 을 그대로 로깅하면 키가 로그에 남는다.
   숨기는 방법을 키를 아는 모듈이 소유해야 호출 측이 잊지 않는다.

자격증명의 단일 출처는 저장소 루트의 `.env` 이며, KRX 자격증명과 같은 파일을 쓴다.
"""

from pathlib import Path

from dotenv import dotenv_values

from verify_lab.common_constants import BASE_DIR
from verify_lab.utils.logger import get_logger

logger = get_logger(__name__)

# ECOS 오픈API 인증키. ecos.bok.or.kr 에서 발급한다
ENV_ECOS_API_KEY = "ECOS_API_KEY"

# 자격증명 파일. git 에서 제외돼 있다
ENV_FILE_PATH = BASE_DIR / ".env"

# 마스킹으로 치환할 표시. 키 길이를 노출하지 않도록 길이와 무관한 고정 문자열을 쓴다
MASK_MARK = "***"


def load_ecos_api_key(path: Path = ENV_FILE_PATH) -> str:
    """`.env` 에서 ECOS 인증키를 읽어 돌려준다.

    예외 메시지에는 경로와 키 **이름**만 담고 값은 담지 않는다. 예외 메시지는 로그와
    스택 트레이스에 남고 그 로그는 공유된다.

    Args:
        path: 자격증명 파일 경로. 기본값은 저장소 루트의 `.env`

    Returns:
        앞뒤 공백이 제거된 인증키

    Raises:
        ValueError: 파일이 없거나, 인증키 항목이 없거나, 값이 비어 있는 경우
    """
    if not path.is_file():
        raise ValueError(f"ECOS 자격증명 파일이 없습니다: {path} (ecos.bok.or.kr 에서 발급받은 인증키를 넣으십시오)")

    raw = dotenv_values(path).get(ENV_ECOS_API_KEY)
    api_key = raw.strip() if raw else ""

    if not api_key:
        raise ValueError(f"{path} 에 {ENV_ECOS_API_KEY} 값이 없습니다")

    logger.debug(f"ECOS 인증키를 읽었습니다 (출처: {path})")

    return api_key


def mask_api_key(text: str, api_key: str) -> str:
    """문자열에 섞인 인증키를 가린다.

    요청 URL·오류 응답을 로그나 문서에 남기기 전에 반드시 통과시킨다.

    Args:
        text: 인증키가 섞여 있을 수 있는 문자열
        api_key: 가릴 인증키

    Returns:
        인증키가 치환된 문자열. 인증키가 없으면 원본 그대로

    Raises:
        ValueError: 인증키가 비어 있는 경우. 빈 문자열로 치환하면 모든 위치가 일치해
            결과가 망가지고 "마스킹했다"는 착각만 남는다
    """
    if not api_key:
        raise ValueError("인증키가 비어 있어 마스킹할 수 없습니다")

    return text.replace(api_key, MASK_MARK)
