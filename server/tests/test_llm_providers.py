"""API 키 없이 공급자별 요청 형태와 응답 처리를 검증합니다."""
import json
from types import SimpleNamespace as NS

import pytest

from guard import config, llm

RESULT = {"label": "normal", "confidence": 0.9, "scam_type": "none", "summary": "일상", "evidence": []}


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)


def test_openai_uses_strict_schema(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return NS(choices=[NS(finish_reason="stop", message=NS(content=json.dumps(RESULT)))])

    monkeypatch.setattr(config, "LLM", "openai")
    monkeypatch.setattr(config, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(llm, "_client", NS(chat=NS(completions=NS(create=create))))
    assert llm.analyze("안녕")["label"] == "normal"
    assert seen["model"] == "test-model" and seen["response_format"]["json_schema"]["strict"] is True


def test_openai_requires_model(monkeypatch):
    monkeypatch.setattr(config, "LLM", "openai")
    monkeypatch.setattr(config, "OPENAI_MODEL", "")
    with pytest.raises(RuntimeError):
        llm.analyze("안녕")


def test_anthropic_uses_api_model(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps(RESULT))])

    monkeypatch.setattr(config, "LLM", "anthropic")
    monkeypatch.setattr(llm, "_client", NS(messages=NS(create=create)))
    assert llm.analyze("안녕")["label"] == "normal"
    assert seen["model"] == config.ANTHROPIC_MODEL


def test_refusal_is_an_error(monkeypatch):
    monkeypatch.setattr(config, "LLM", "anthropic")
    monkeypatch.setattr(llm, "_client", NS(messages=NS(create=lambda **k: NS(stop_reason="refusal", content=[]))))
    with pytest.raises(RuntimeError):
        llm.analyze("안녕")
