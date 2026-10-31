"""자체 STT 서버 호출. 서버가 전사를 동시에 1건만 처리하므로 이 프로세스도 1건씩 보냅니다."""
import io
import logging
import threading
import time

import httpx

from . import config

log = logging.getLogger("guard.stt")

CONNECT_TIMEOUT = 10
HEALTH_TIMEOUT = 5
DEFAULT_RETRY_AFTER = 5
MAX_RETRY_AFTER = 60

_lock = threading.Lock()


class SttError(RuntimeError):
    pass


class SttBadRequest(SttError):
    pass


class SttAuthError(SttError):
    pass


class SttTooLarge(SttError):
    pass


class SttBusy(SttError):
    pass


class SttConnectionError(SttError):
    pass


class SttTimeout(SttError):
    pass


def _duration(filename: str, data: bytes) -> float | None:
    """길이를 못 읽는 형식이면 None을 돌려주고 서버의 검사에 맡깁니다."""
    from mutagen import File

    try:
        buffer = io.BytesIO(data)
        buffer.name = filename
        audio = File(buffer)
        # 태그가 없는 파일은 객체가 거짓으로 평가되므로 None과 직접 비교합니다.
        return audio.info.length if audio is not None else None
    except Exception:
        return None


def _check_limits(filename: str, data: bytes) -> None:
    if len(data) > config.STT_MAX_BYTES:
        raise SttTooLarge("파일이 50 MiB를 넘습니다")
    seconds = _duration(filename, data)
    if seconds is not None and seconds > config.STT_MAX_SECONDS:
        raise SttTooLarge(f"음성이 {config.STT_MAX_SECONDS}초를 넘습니다")


def _retry_after(response: httpx.Response) -> float:
    try:
        wait = float(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER))
    except ValueError:
        wait = DEFAULT_RETRY_AFTER
    return min(max(wait, 0), MAX_RETRY_AFTER)


def _detail(response: httpx.Response) -> str:
    return response.text[:200]


def _post(filename: str, data: bytes, timeout: float) -> httpx.Response:
    try:
        return httpx.post(
            f"{config.STT_BASE_URL}/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.STT_API_KEY}"},
            files={"file": (filename, data)},
            data={"model": config.STT_MODEL, "language": "ko", "response_format": "json"},
            timeout=httpx.Timeout(timeout, connect=min(CONNECT_TIMEOUT, timeout)),
        )
    except httpx.TimeoutException as exc:
        raise SttTimeout("STT 서버 시간 초과") from exc
    except httpx.TransportError as exc:
        raise SttConnectionError(f"STT 서버 연결 실패: {type(exc).__name__}") from exc


def _parse(response: httpx.Response) -> str:
    try:
        body = response.json()
        text = body["text"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SttError("STT 서버 응답 형식 오류") from exc
    # 통화 내용이 남지 않도록 전사문은 기록하지 않습니다.
    log.info("STT 완료 model=%s duration=%s processing_seconds=%s", body.get("model"), body.get("duration"), body.get("processing_seconds"))
    return text.strip()


def transcribe(filename: str, data: bytes) -> str:
    if not config.STT_BASE_URL:
        raise SttConnectionError("STT_BASE_URL을 설정하세요")
    if not config.STT_API_KEY:
        raise SttAuthError("STT_API_KEY를 설정하세요")
    _check_limits(filename, data)

    deadline = time.monotonic() + config.STT_TIMEOUT
    if not _lock.acquire(timeout=min(config.STT_QUEUE_TIMEOUT, config.STT_TIMEOUT)):
        raise SttBusy("앞선 전사가 끝나지 않았습니다")
    try:
        for attempt in range(config.STT_MAX_RETRIES + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SttTimeout("STT 서버 시간 초과")
            response = _post(filename, data, remaining)
            status = response.status_code
            if status == 200:
                return _parse(response)
            if status == 429:
                wait = _retry_after(response)
                if attempt == config.STT_MAX_RETRIES or wait >= deadline - time.monotonic():
                    raise SttBusy("STT 서버가 처리 중입니다")
                log.info("STT 429, %s초 뒤 다시 시도 (%d/%d)", wait, attempt + 1, config.STT_MAX_RETRIES)
                time.sleep(wait)
                continue
            if status == 400:
                raise SttBadRequest(f"STT 요청 오류: {_detail(response)}")
            if status == 401:
                raise SttAuthError("STT 인증 실패")
            if status == 413:
                raise SttTooLarge(f"STT 서버 제한 초과: {_detail(response)}")
            raise SttError(f"STT 서버 오류 {status}")
    finally:
        _lock.release()
    raise SttBusy("STT 서버가 처리 중입니다")


def health() -> dict:
    if not config.STT_BASE_URL:
        return {"ok": False, "error": "not_configured"}
    try:
        response = httpx.get(f"{config.STT_BASE_URL}/health", timeout=HEALTH_TIMEOUT)
        response.raise_for_status()
        body = response.json()
    except httpx.TimeoutException:
        return {"ok": False, "error": "timeout"}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"status_{exc.response.status_code}"}
    except (httpx.TransportError, ValueError):
        return {"ok": False, "error": "connection"}
    return {"ok": body.get("status") == "ok", "model": body.get("model"), "busy": body.get("busy")}
