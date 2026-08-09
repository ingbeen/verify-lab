"""병렬 처리 유틸리티 모듈

ProcessPoolExecutor를 사용하여 CPU 집약적 작업을 병렬로 실행한다.

학습 포인트:
1. 병렬 처리: 여러 작업을 동시에 실행하여 성능 향상
2. ProcessPoolExecutor: 멀티프로세싱 기반 병렬 실행 (CPU 집약적 작업용)
3. Future 객체: 비동기 작업의 결과를 나타내는 객체
4. pickle: Python 객체를 직렬화하여 프로세스 간 전달
"""

import multiprocessing
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from typing import Any

from qbt.utils import get_logger

logger = get_logger(__name__)

# 워커 프로세스별 캐시 저장소
# 병렬 실행 시 큰 DataFrame을 작업마다 전달하지 않고, 워커당 1회만 세팅
WORKER_CACHE: dict[str, Any] = {}


def init_worker_cache(cache_payload: dict[str, Any]) -> None:
    """
    워커 프로세스 초기화 함수.

    WORKER_CACHE를 초기화하고 전달받은 데이터를 캐싱한다.
    병렬 실행 시 큰 DataFrame을 작업마다 전달하지 않고, 워커당 1회만 세팅한다.

    이 함수는 ProcessPoolExecutor의 initializer 인자로 사용되며,
    각 워커 프로세스가 시작될 때 자동으로 호출된다.

    Args:
        cache_payload: 캐시할 데이터 딕셔너리
            - 키: 캐시 항목 이름 (예: "df", "underlying_overlap", "ffr_df")
            - 값: 캐시할 데이터 (주로 DataFrame)

    Example:
        >>> # backtest 그리드 서치
        >>> cache_payload = {"df": stock_df}
        >>> results = execute_parallel(
        ...     worker_func,
        ...     inputs,
        ...     initializer=init_worker_cache,
        ...     initargs=(cache_payload,)
        ... )

        >>> # tqqq 비용 모델 최적화
        >>> cache_payload = {
        ...     "underlying_overlap": qqq_overlap,
        ...     "actual_overlap": tqqq_overlap,
        ...     "ffr_df": ffr_df
        ... }
        >>> results = execute_parallel(
        ...     worker_func,
        ...     inputs,
        ...     initializer=init_worker_cache,
        ...     initargs=(cache_payload,)
        ... )

    Note:
        - 이 함수는 pickle 가능하도록 모듈 최상위 레벨에 정의되어야 함
        - WORKER_CACHE는 워커 프로세스 전역 변수이므로, 워커 함수에서 직접 참조 가능
        - 워커 프로세스마다 독립적인 WORKER_CACHE를 가지므로 서로 간섭하지 않음
    """
    WORKER_CACHE.clear()
    WORKER_CACHE.update(cache_payload)


def _unwrap_kwargs(args: tuple[Callable[..., Any], dict[str, Any]]) -> Any:
    """
    (함수, kwargs 딕셔너리) 튜플을 받아 함수를 호출한다.

    ProcessPoolExecutor에서 pickle 가능하도록 모듈 레벨에 정의한다.

    Args:
        args: (func, kwargs_dict) 튜플
            - func: 호출할 함수
            - kwargs_dict: 키워드 인자 딕셔너리

    Returns:
        함수 호출 결과
    """
    func: Callable[..., Any] = args[0]
    kwargs_dict: dict[str, Any] = args[1]
    return func(**kwargs_dict)


def _should_log_progress(
    completed_count: int,
    total_count: int,
    last_logged_percentage: int,
) -> tuple[bool, int]:
    """
    진행도 로그 출력 여부를 결정한다.

    다음 조건 중 하나라도 만족하면 로그를 출력한다:
    1. 첫 번째 작업 완료
    2. 마지막 작업 완료
    3. 10% 경계를 넘었을 때 (10%, 20%, ..., 90%)

    Args:
        completed_count: 완료된 작업 수
        total_count: 전체 작업 수
        last_logged_percentage: 마지막으로 로그를 출력한 퍼센트 (0-100)

    Returns:
        (출력 여부, 현재 퍼센트) 튜플
    """
    current_percentage = int((completed_count / total_count) * 100)

    # 1. 첫 번째 작업 완료
    if completed_count == 1:
        return (True, current_percentage)

    # 2. 마지막 작업 완료
    if completed_count == total_count:
        return (True, current_percentage)

    # 3. 10% 경계를 넘었을 때
    last_decile = last_logged_percentage // 10
    current_decile = current_percentage // 10
    if current_decile > last_decile:
        return (True, current_percentage)

    return (False, current_percentage)


def execute_parallel(
    func: Callable[..., Any],
    inputs: list[Any],
    max_workers: int | None = None,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[Any, ...] | None = None,
    log_progress: bool = True,
) -> list[Any]:
    """
    CPU 집약적 함수를 여러 입력에 대해 병렬로 실행한다.

    학습 포인트:
    1. ProcessPoolExecutor: 멀티프로세싱 기반 작업 병렬 실행
    2. enumerate(): 리스트 순회 시 (인덱스, 값) 쌍으로 가져오기
    3. 딕셔너리 컴프리헨션: {key: value for ...} 형태로 딕셔너리 생성
    4. initializer: 워커 프로세스 시작 시 실행되는 초기화 함수 (캐시 세팅용)
    5. 리스트 컴프리헨션: [result for _, result in ...] 형태로 리스트 생성

    ProcessPoolExecutor를 사용하여 함수를 병렬로 실행하고,
    모든 작업이 완료될 때까지 대기한 후 입력 순서대로 정렬된 결과를 반환한다.

    Args:
        func: 병렬로 실행할 함수 (단일 인자를 받아야 함)
        inputs: 함수에 전달할 입력 리스트
        max_workers: 최대 워커 수 (None이면 기본값 2)
        initializer: 워커 프로세스 초기화 함수 (WORKER_CACHE 세팅용)
        initargs: initializer에 전달할 인자 튜플 (cache_payload,)
        log_progress: 진행도 로깅 출력 여부 (기본값: True)
            - True: 첫 번째, 마지막, 10% 경계마다 진행도 로그 출력
            - False: 진행도 로그 미출력 (시작/완료 로그는 출력)

    Returns:
        입력 순서대로 정렬된 결과 리스트

    Raises:
        ValueError: inputs가 비어있을 때
        Exception: 작업 중 발생한 예외 (첫 번째 예외만 전파)

    Example:
        >>> def heavy_computation(x: int) -> int:
        ...     return x ** 2
        >>> inputs = [1, 2, 3, 4, 5]
        >>> results = execute_parallel(heavy_computation, inputs, max_workers=2)
        >>> print(results)  # [1, 4, 9, 16, 25]

    Note:
        - Windows 환경에서는 호출하는 스크립트에서 `if __name__ == "__main__"`으로 보호해야 함
        - func는 pickle 가능해야 함 (람다 함수는 사용 불가)
        - 각 워커는 독립적인 프로세스에서 실행되므로 전역 상태를 공유하지 않음
        - initializer를 사용하면 큰 데이터를 작업마다 전달하지 않고 워커당 1회만 세팅 가능
    """
    # 1. 입력 검증
    if not inputs:
        raise ValueError("inputs가 비어있습니다")

    # 2. max_workers 기본값 설정
    if max_workers is None:
        max_workers = 2

    logger.debug(f"병렬 실행 시작 - 작업 수: {len(inputs)}, 워커 수: {max_workers}, " f"함수: {func.__module__}.{func.__name__}")

    # 3. 병렬 실행
    # (입력 인덱스, 결과) 쌍을 저장하여 나중에 순서를 복원
    # 타입 힌트: list[tuple[int, Any]] - (정수, 임의 타입) 튜플의 리스트
    results_with_index: list[tuple[int, Any]] = []
    last_logged_percentage = 0

    # with 문: ProcessPoolExecutor를 자동으로 종료
    # spawn 컨텍스트 사용: fork() 대신 spawn() 사용하여 멀티스레드 환경에서 안정성 확보
    # - fork()는 멀티스레드 환경에서 데드락 위험이 있음 (DeprecationWarning)
    # - spawn()은 새 Python 인터프리터를 시작하여 깨끗한 상태로 프로세스 생성
    # - 참고: WSL/Linux에서 기본은 fork(), Windows는 spawn() 사용
    mp_context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=max_workers, mp_context=mp_context, initializer=initializer, initargs=initargs or ()
    ) as executor:
        # 딕셔너리 컴프리헨션: {key: value for ...}
        # enumerate(inputs): (0, inputs[0]), (1, inputs[1]), ... 생성
        # executor.submit(func, input_data): 작업 제출하고 Future 객체 반환
        # Future 객체를 키로, 인덱스를 값으로 하는 딕셔너리 생성
        future_to_index: dict[Future[Any], int] = {
            executor.submit(func, input_data): idx for idx, input_data in enumerate(inputs)
        }

        # 완료되는 대로 결과 수집
        # as_completed(): 작업이 완료되는 순서대로 Future 객체 반환
        for future in as_completed(future_to_index):
            # 딕셔너리에서 Future에 해당하는 인덱스 가져오기
            idx = future_to_index[future]
            try:
                # future.result(): 작업의 실제 결과 가져오기 (완료될 때까지 대기)
                result: Any = future.result()
                # (인덱스, 결과) 튜플로 저장
                results_with_index.append((idx, result))

                # 진행도 로깅 (첫 번째, 마지막, 10% 경계마다)
                if log_progress:
                    completed_count = len(results_with_index)
                    should_log, current_pct = _should_log_progress(completed_count, len(inputs), last_logged_percentage)
                    if should_log:
                        logger.debug(f"진행도: {completed_count}/{len(inputs)} ({current_pct}%)")
                        last_logged_percentage = current_pct

            except Exception as e:
                logger.debug(f"작업 {idx + 1}/{len(inputs)} 실패: {e}")
                raise

    # 4. 입력 순서대로 정렬
    # .sort(key=...): key 함수의 반환값을 기준으로 정렬
    # lambda x: x[0]: 튜플의 첫 번째 요소(인덱스)를 기준으로 정렬
    results_with_index.sort(key=lambda x: x[0])

    # 리스트 컴프리헨션: [표현식 for 변수 in 리스트]
    # for _, result in results_with_index: 인덱스는 무시하고 결과만 추출
    results = [result for _, result in results_with_index]

    logger.debug(f"병렬 실행 완료 - 총 {len(results)}개 작업 성공")

    return results


def execute_parallel_with_kwargs(
    func: Callable[..., Any],
    inputs: list[dict[str, Any]],
    max_workers: int | None = None,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[Any, ...] | None = None,
    log_progress: bool = True,
) -> list[Any]:
    """
    CPU 집약적 함수를 여러 입력에 대해 병렬로 실행한다. (키워드 인자 지원)

    각 입력을 딕셔너리로 받아 **kwargs 형태로 함수에 전달한다.
    나머지 동작은 execute_parallel과 동일하다.

    Args:
        func: 병렬로 실행할 함수 (키워드 인자를 받아야 함)
        inputs: 함수에 전달할 키워드 인자 딕셔너리 리스트
        max_workers: 최대 워커 수 (None이면 기본값 2)
        initializer: 워커 프로세스 초기화 함수 (WORKER_CACHE 세팅용)
        initargs: initializer에 전달할 인자 튜플 (cache_payload,)
        log_progress: 진행도 로깅 출력 여부 (기본값: True)
            - True: 첫 번째, 마지막, 10% 경계마다 진행도 로그 출력
            - False: 진행도 로그 미출력 (시작/완료 로그는 출력)

    Returns:
        입력 순서대로 정렬된 결과 리스트

    Raises:
        ValueError: inputs가 비어있을 때
        Exception: 작업 중 발생한 예외 (첫 번째 예외만 전파)

    Example:
        >>> def compute(a: int, b: int) -> int:
        ...     return a + b
        >>> inputs = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        >>> results = execute_parallel_with_kwargs(compute, inputs, max_workers=2)
        >>> print(results)  # [3, 7]

    Note:
        - Windows 환경에서는 호출하는 스크립트에서 `if __name__ == "__main__"`으로 보호해야 함
        - func와 inputs의 모든 객체는 pickle 가능해야 함
        - 각 워커는 독립적인 프로세스에서 실행되므로 전역 상태를 공유하지 않음
        - initializer를 사용하면 큰 데이터를 작업마다 전달하지 않고 워커당 1회만 세팅 가능
    """
    # (func, kwargs) 튜플 리스트 생성
    unwrap_inputs: list[tuple[Callable[..., Any], dict[str, Any]]] = [(func, kwargs_dict) for kwargs_dict in inputs]

    # 모듈 레벨 _unwrap_kwargs 함수 사용 (pickle 가능)
    return execute_parallel(_unwrap_kwargs, unwrap_inputs, max_workers, initializer, initargs, log_progress)
