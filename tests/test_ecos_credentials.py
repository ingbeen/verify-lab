"""ECOS 인증키 로딩의 계약과 실패 정책을 고정한다.

ECOS 는 인증키를 **요청 URL 경로에 넣는다.** 그래서 이 모듈이 지켜야 할 것이 두 가지다 —
키가 없을 때 조용히 넘어가지 않는 것, 그리고 **키가 로그나 예외 메시지로 새지 않는 것**이다.
후자는 KRX 자격증명보다 위험하다. URL 을 통째로 로깅하는 순간 키가 그대로 남는다.
"""

from pathlib import Path

import pytest

from verify_lab.data.ecos_credentials import ENV_ECOS_API_KEY, load_ecos_api_key, mask_api_key


def _write_env(path: Path, body: str) -> Path:
    """`.env` 파일을 만들어 경로를 돌려준다."""
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def valid_env_file(tmp_path: Path) -> Path:
    """인증키가 채워진 `.env`."""
    return _write_env(tmp_path / ".env", "KRX_ID=env-id\nKRX_PW=env-pw\nECOS_API_KEY=abcd1234\n")


def test_returns_api_key_value(valid_env_file: Path) -> None:
    """
    목적: 인증키를 **값으로** 돌려줌을 고정한다.

    ECOS 는 URL 에 키를 끼워 넣으므로 환경 변수로 올릴 이유가 없다. KRX 로더와 다른 지점이다.

    Given: 인증키가 채워진 `.env`
    When: 인증키를 로드한다
    Then: 그 값이 그대로 반환된다
    """
    assert load_ecos_api_key(valid_env_file) == "abcd1234"


def test_does_not_touch_environment(valid_env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    목적: 환경 변수를 오염시키지 않음을 고정한다.

    `os.environ` 에 키를 올리면 이후 실행되는 모든 하위 프로세스가 키를 상속받는다.
    돌려주기만 하면 그 노출면이 생기지 않는다.

    Given: 인증키가 채워진 `.env` 와 비워진 환경 변수
    When: 인증키를 로드한다
    Then: 환경 변수는 여전히 비어 있다
    """
    # Given
    monkeypatch.delenv(ENV_ECOS_API_KEY, raising=False)

    # When
    load_ecos_api_key(valid_env_file)

    # Then
    import os

    assert ENV_ECOS_API_KEY not in os.environ


def test_surrounding_whitespace_is_stripped(tmp_path: Path) -> None:
    """
    목적: 앞뒤 공백이 붙은 값을 그대로 쓰지 않음을 고정한다 (경계 조건).

    복사·붙여넣기로 키를 넣으면 줄 끝 공백이 딸려 오는 일이 흔하고,
    그대로 URL 에 넣으면 인증 실패의 원인이 키 오타처럼 보인다.

    Given: 값 앞뒤에 공백이 있는 `.env`
    When: 인증키를 로드한다
    Then: 공백이 제거된 값이 반환된다
    """
    path = _write_env(tmp_path / ".env", "ECOS_API_KEY=  abcd1234  \n")

    assert load_ecos_api_key(path) == "abcd1234"


def test_missing_file_raises(tmp_path: Path) -> None:
    """
    목적: 파일이 없을 때 조용히 넘어가지 않음을 고정한다.

    Given: 존재하지 않는 경로
    When: 인증키를 로드한다
    Then: ValueError 가 발생하고 메시지에 경로가 담긴다
    """
    missing_path = tmp_path / "없는파일.env"

    with pytest.raises(ValueError, match="자격증명 파일"):
        load_ecos_api_key(missing_path)


def test_missing_key_raises(tmp_path: Path) -> None:
    """
    목적: 인증키 항목이 없으면 실패함을 고정한다.

    Given: KRX 키만 있는 `.env`
    When: 인증키를 로드한다
    Then: ValueError 가 발생하고 메시지에 빠진 키 이름이 담긴다
    """
    path = _write_env(tmp_path / ".env", "KRX_ID=env-id\nKRX_PW=env-pw\n")

    with pytest.raises(ValueError, match=ENV_ECOS_API_KEY):
        load_ecos_api_key(path)


def test_empty_value_raises(tmp_path: Path) -> None:
    """
    목적: 키는 있지만 값이 빈 경우도 실패로 판정함을 고정한다 (경계 조건).

    Given: 값이 빈 `.env`
    When: 인증키를 로드한다
    Then: ValueError 가 발생한다
    """
    path = _write_env(tmp_path / ".env", "ECOS_API_KEY=\n")

    with pytest.raises(ValueError, match=ENV_ECOS_API_KEY):
        load_ecos_api_key(path)


def test_error_message_never_contains_the_key(tmp_path: Path) -> None:
    """
    목적: 실패 메시지에 인증키 값이 담기지 않음을 고정한다.

    예외 메시지는 로그와 스택 트레이스에 남고 그 로그는 공유된다.

    Given: 인증키가 채워졌지만 다른 이유로 실패하는 상황 (파일 경로가 디렉터리)
    When: 인증키를 로드한다
    Then: 예외 메시지 어디에도 키 값이 없다
    """
    # Given
    _write_env(tmp_path / ".env", "ECOS_API_KEY=super-secret-value\n")

    # When / Then
    with pytest.raises(ValueError) as error:
        load_ecos_api_key(tmp_path / ".env" / "하위경로")

    assert "super-secret-value" not in str(error.value)


def test_mask_hides_key_inside_url() -> None:
    """
    목적: URL 안의 인증키가 마스킹됨을 고정한다.

    ECOS 는 키를 URL **경로**에 넣으므로 요청 URL 을 그대로 로깅하면 키가 남는다.

    Given: 인증키가 포함된 URL
    When: 마스킹한다
    Then: 키가 사라지고 나머지 경로는 남는다
    """
    url = "https://ecos.bok.or.kr/api/StatisticSearch/abcd1234/json/kr/1/10/731Y001"

    masked = mask_api_key(url, "abcd1234")

    assert "abcd1234" not in masked
    assert "StatisticSearch" in masked
    assert "731Y001" in masked


def test_mask_is_noop_when_key_absent() -> None:
    """
    목적: 키가 들어 있지 않은 문자열은 그대로 둠을 고정한다 (경계 조건).

    Given: 인증키가 없는 문자열
    When: 마스킹한다
    Then: 원본이 그대로 반환된다
    """
    text = "https://ecos.bok.or.kr/api/StatisticTableList/json/kr/1/10"

    assert mask_api_key(text, "abcd1234") == text


def test_mask_rejects_empty_key() -> None:
    """
    목적: 빈 키로 마스킹을 시도하면 실패함을 고정한다 (경계 조건).

    빈 문자열로 치환하면 문자열의 모든 위치가 일치해 결과가 망가지고,
    "마스킹했다"는 착각만 남는다.

    Given: 빈 인증키
    When: 마스킹한다
    Then: ValueError 가 발생한다
    """
    with pytest.raises(ValueError, match="인증키"):
        mask_api_key("아무 문자열", "")
