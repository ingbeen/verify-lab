"""KRX 자격증명 로딩의 계약과 실패 정책을 고정한다.

pykrx 는 `.env` 를 읽지 않고 환경 변수만 본다. 이 로더가 그 사이를 잇는 유일한 지점이므로,
"무엇이 없을 때 어떻게 실패하는가"가 분명해야 한다. 자격증명이 조용히 비어 있으면
국내 데이터 조회가 전부 실패하면서 원인은 KRX 응답 쪽에만 남는다.

**비밀값이 예외 메시지로 새지 않는 것**도 여기서 고정한다. 예외 메시지는 로그와 스택 트레이스에
그대로 남고, 그 로그는 공유된다.
"""

import os
from pathlib import Path

import pytest

from verify_lab.data.krx_credentials import ENV_KRX_ID, ENV_KRX_PW, load_krx_credentials


def _write_env(path: Path, body: str) -> Path:
    """`.env` 파일을 만들어 경로를 돌려준다."""
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def clean_krx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """KRX 환경 변수를 비우고, 테스트가 끝나면 원래 상태로 되돌린다.

    `load_dotenv` 는 `os.environ` 을 직접 고치므로 monkeypatch 가 그 변경을 알지 못한다.
    테스트 시작 시점에 monkeypatch 로 두 키를 한 번 건드려 두면 원래 값이 기록되고,
    테스트가 끝날 때 그 상태로 복원된다.
    """
    monkeypatch.delenv(ENV_KRX_ID, raising=False)
    monkeypatch.delenv(ENV_KRX_PW, raising=False)


@pytest.fixture
def valid_env_file(tmp_path: Path) -> Path:
    """두 키가 모두 채워진 `.env`."""
    return _write_env(tmp_path / ".env", "KRX_ID=env-id\nKRX_PW=env-pw\n")


def test_credentials_are_exported_to_environment(valid_env_file: Path, clean_krx_env: None) -> None:
    """
    목적: `.env` 값이 환경 변수로 올라감을 고정한다.

    pykrx 는 환경 변수만 보므로, 여기까지 와야 조회가 성립한다.

    Given: 두 키가 채워진 `.env`
    When: 자격증명을 로드한다
    Then: 두 값이 환경 변수에 있다
    """
    # When
    load_krx_credentials(valid_env_file)

    # Then
    assert os.environ[ENV_KRX_ID] == "env-id"
    assert os.environ[ENV_KRX_PW] == "env-pw"


def test_env_file_overrides_shell_variables(
    valid_env_file: Path, clean_krx_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    목적: 셸 환경 변수보다 `.env` 가 우선함을 고정한다.

    어느 환경에서 실행하든 같은 계정을 쓰게 하려는 정책이다. 셸에 남아 있던 옛 값이 이기면
    "어제는 됐는데 오늘은 안 되는" 상황이 생기고 원인을 찾기 어렵다.

    Given: 셸에 다른 값이 이미 설정된 상태
    When: 자격증명을 로드한다
    Then: `.env` 값이 이긴다
    """
    # Given
    monkeypatch.setenv(ENV_KRX_ID, "shell-id")

    # When
    load_krx_credentials(valid_env_file)

    # Then
    assert os.environ[ENV_KRX_ID] == "env-id"


def test_missing_file_raises(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 파일이 없을 때 조용히 넘어가지 않음을 고정한다.

    Given: 존재하지 않는 경로
    When: 자격증명을 로드한다
    Then: ValueError 가 발생하고 메시지에 경로가 담긴다
    """
    missing_path = tmp_path / "없는파일.env"

    with pytest.raises(ValueError, match="자격증명 파일"):
        load_krx_credentials(missing_path)


def test_missing_key_raises(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 키가 하나라도 없으면 실패함을 고정한다.

    Given: 아이디만 있는 `.env`
    When: 자격증명을 로드한다
    Then: ValueError 가 발생하고 메시지에 빠진 키 이름이 담긴다
    """
    # Given
    path = _write_env(tmp_path / ".env", "KRX_ID=env-id\n")

    # When / Then
    with pytest.raises(ValueError, match=ENV_KRX_PW):
        load_krx_credentials(path)


def test_empty_value_raises(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 키는 있지만 값이 빈 경우도 실패로 판정함을 고정한다 (경계 조건).

    `.env` 를 만들어만 두고 값을 안 채운 상태가 실제로 흔하다.

    Given: 비밀번호가 빈 `.env`
    When: 자격증명을 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    path = _write_env(tmp_path / ".env", "KRX_ID=env-id\nKRX_PW=\n")

    # When / Then
    with pytest.raises(ValueError, match=ENV_KRX_PW):
        load_krx_credentials(path)


def test_comment_only_file_raises(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 주석과 빈 줄뿐인 파일을 실패로 판정함을 고정한다 (경계 조건).

    Given: 주석만 있는 `.env`
    When: 자격증명을 로드한다
    Then: ValueError 가 발생한다
    """
    # Given
    path = _write_env(tmp_path / ".env", "# KRX 계정 정보를 여기에 적는다\n\n")

    # When / Then
    with pytest.raises(ValueError, match="비어"):
        load_krx_credentials(path)


def test_secret_value_is_not_leaked_in_error_message(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 예외 메시지에 비밀값이 섞이지 않음을 고정한다.

    예외 메시지는 로그와 스택 트레이스에 남고 그 로그는 공유된다. 실패를 설명하려고
    값을 찍는 순간 자격증명이 평문으로 유출된다.

    Given: 아이디가 비어 있고 비밀번호는 채워진 `.env`
    When: 자격증명을 로드한다
    Then: 예외 메시지에 비밀번호 값이 없다
    """
    # Given
    secret = "super-secret-password"
    path = _write_env(tmp_path / ".env", f"KRX_ID=\nKRX_PW={secret}\n")

    # When
    with pytest.raises(ValueError) as exc_info:
        load_krx_credentials(path)

    # Then
    assert secret not in str(exc_info.value)


def test_environment_is_untouched_when_file_is_missing(tmp_path: Path, clean_krx_env: None) -> None:
    """
    목적: 실패한 로딩이 환경을 반쯤 바꿔놓지 않음을 고정한다 (경계 조건).

    Given: 존재하지 않는 경로
    When: 로딩이 실패한다
    Then: 환경 변수가 설정되지 않은 상태 그대로다
    """
    # When
    with pytest.raises(ValueError):
        load_krx_credentials(tmp_path / "없는파일.env")

    # Then
    assert ENV_KRX_ID not in os.environ
    assert ENV_KRX_PW not in os.environ
