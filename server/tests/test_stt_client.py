"""자체 STT 서버 호출을 가짜 응답으로 검증합니다."""
import io
import wave

import httpx
import pytest

from guard import config, providers, stt_client

OK = {"text": " 전사 결과 ", "segments": [], "duration": 1.0, "processing_seconds": 0.5, "model": "m"}


@pytest.fixture
def stt(monkeypatch):
    monkeypatch.setattr(config, "STT_BASE_URL", "http://stt")
    monkeypatch.setattr(config, "STT_API_KEY", "secret")
    monkeypatch.setattr(config, "STT_MAX_RETRIES", 2)
    sleeps = []
    monkeypatch.setattr(stt_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(stt_client, "_duration", lambda filename, data: 10.0)

    def replies(*items):
        calls = []

        def post(url, **kw):
            calls.append((url, kw))
            item = items[len(calls) - 1]
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(stt_client.httpx, "post", post)
        return calls

    return replies, sleeps


def test_sends_contract_fields_and_returns_text(stt):
    replies, _ = stt
    calls = replies(httpx.Response(200, json=OK))
    assert stt_client.transcribe("a.mp3", b"audio") == "전사 결과"
    url, kw = calls[0]
    assert url == "http://stt/v1/audio/transcriptions"
    assert kw["headers"]["Authorization"] == "Bearer secret"
    assert kw["files"]["file"] == ("a.mp3", b"audio")
    assert kw["data"] == {"model": config.STT_MODEL, "language": "ko", "response_format": "json"}
    assert kw["timeout"].read <= config.STT_TIMEOUT


def test_429_waits_retry_after_then_succeeds(stt):
    replies, sleeps = stt
    calls = replies(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json=OK))
    assert stt_client.transcribe("a.mp3", b"audio") == "전사 결과"
    assert sleeps == [7.0] and len(calls) == 2


def test_429_gives_up_after_limited_retries(stt):
    replies, sleeps = stt
    busy = httpx.Response(429, headers={"Retry-After": "9999"})
    calls = replies(busy, busy, busy)
    with pytest.raises(stt_client.SttBusy):
        stt_client.transcribe("a.mp3", b"audio")
    assert len(calls) == 3 and sleeps == [stt_client.MAX_RETRY_AFTER] * 2


@pytest.mark.parametrize(
    "reply, error",
    [
        (httpx.Response(400, text="bad"), stt_client.SttBadRequest),
        (httpx.Response(401), stt_client.SttAuthError),
        (httpx.Response(413), stt_client.SttTooLarge),
        (httpx.Response(500), stt_client.SttError),
        (httpx.Response(200, text="not json"), stt_client.SttError),
        (httpx.ConnectError("down"), stt_client.SttConnectionError),
        (httpx.ReadTimeout("slow"), stt_client.SttTimeout),
    ],
)
def test_failures_are_distinguished_and_not_retried(stt, reply, error):
    replies, sleeps = stt
    calls = replies(reply)
    with pytest.raises(error):
        stt_client.transcribe("a.mp3", b"audio")
    assert len(calls) == 1 and not sleeps


def test_limits_are_checked_before_sending(stt, monkeypatch):
    replies, _ = stt
    calls = replies()
    monkeypatch.setattr(config, "STT_MAX_BYTES", 2)
    with pytest.raises(stt_client.SttTooLarge):
        stt_client.transcribe("a.mp3", b"audio")
    monkeypatch.setattr(config, "STT_MAX_BYTES", 100)
    monkeypatch.setattr(stt_client, "_duration", lambda filename, data: 301.0)
    with pytest.raises(stt_client.SttTooLarge):
        stt_client.transcribe("a.mp3", b"audio")
    assert not calls


def test_missing_key_fails_without_sending(stt, monkeypatch):
    replies, _ = stt
    calls = replies()
    monkeypatch.setattr(config, "STT_API_KEY", "")
    with pytest.raises(stt_client.SttAuthError):
        stt_client.transcribe("a.mp3", b"audio")
    assert not calls


def test_health_reports_states_without_key(stt, monkeypatch):
    seen = {}

    def get(url, **kw):
        seen.update(kw)
        return httpx.Response(200, json={"status": "ok", "model": "m", "busy": False}, request=httpx.Request("GET", url))

    monkeypatch.setattr(stt_client.httpx, "get", get)
    assert stt_client.health() == {"ok": True, "model": "m", "busy": False}
    assert "headers" not in seen

    def down(url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(stt_client.httpx, "get", down)
    assert stt_client.health() == {"ok": False, "error": "connection"}


def test_duration_reads_untagged_audio_and_ignores_unknown_data():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 16000)
    assert stt_client._duration("a.wav", buffer.getvalue()) == pytest.approx(2.0)
    assert stt_client._duration("a.bin", b"not audio") is None


@pytest.fixture
def fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(providers, "_read", lambda key: b"audio")
    monkeypatch.setattr(providers, "_openai_transcribe", lambda key: calls.append(key) or "대체 결과")
    return calls


@pytest.mark.parametrize(
    "error",
    [stt_client.SttBusy, stt_client.SttConnectionError, stt_client.SttTimeout, stt_client.SttAuthError, stt_client.SttTooLarge, stt_client.SttError],
)
def test_load_and_outage_fall_back_to_openai(fallback, monkeypatch, error):
    def fail(filename, data):
        raise error("실패")

    monkeypatch.setattr(stt_client, "transcribe", fail)
    assert providers._server_transcribe("r/a.mp3") == "대체 결과"
    assert fallback == ["r/a.mp3"]


def test_local_success_never_calls_openai(fallback, monkeypatch):
    monkeypatch.setattr(stt_client, "transcribe", lambda filename, data: "자체 결과")
    assert providers._server_transcribe("r/a.mp3") == "자체 결과"
    assert not fallback


def test_bad_request_and_disabled_fallback_do_not_call_openai(fallback, monkeypatch):
    def bad(filename, data):
        raise stt_client.SttBadRequest("잘못된 파일")

    monkeypatch.setattr(stt_client, "transcribe", bad)
    with pytest.raises(stt_client.SttBadRequest):
        providers._server_transcribe("r/a.mp3")

    def down(filename, data):
        raise stt_client.SttConnectionError("연결 실패")

    monkeypatch.setattr(stt_client, "transcribe", down)
    monkeypatch.setattr(config, "STT_FALLBACK", "none")
    with pytest.raises(stt_client.SttConnectionError):
        providers._server_transcribe("r/a.mp3")
    assert not fallback


def test_queue_wait_is_reported_as_busy(stt, monkeypatch):
    replies, _ = stt
    calls = replies()
    monkeypatch.setattr(config, "STT_QUEUE_TIMEOUT", 0.01)
    with stt_client._lock:
        with pytest.raises(stt_client.SttBusy):
            stt_client.transcribe("a.mp3", b"audio")
    assert not calls
