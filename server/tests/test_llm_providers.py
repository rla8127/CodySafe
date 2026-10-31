"""API 키 없이 공급자별 요청 형태와 응답 처리를 검증합니다."""
import json
from types import SimpleNamespace as NS

import httpx
import pytest

from guard import config, llm, remote_rag

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


def analyzed(monkeypatch, label, evidence):
    answer = {**RESULT, "label": label, "scam_type": "unknown", "evidence": evidence}
    monkeypatch.setattr(config, "LLM", "anthropic")
    response = NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps(answer))])
    monkeypatch.setattr(llm, "_client", NS(messages=NS(create=lambda **k: response)))
    return llm.analyze("저는 은행 직원입니다. 계좌번호 1234 불러 주시고 앱을 설치하세요.")


def test_only_quotes_found_in_transcript_are_kept(monkeypatch):
    result = analyzed(monkeypatch, "voice_phishing", ["앱을  설치하세요", "계좌번호 *** 불러 주시고", "이 사람은 대출상담사다"])
    assert result["evidence"] == ["앱을  설치하세요", "계좌번호 *** 불러 주시고"]
    assert result["label"] == "voice_phishing"


def test_scam_verdict_without_real_quote_becomes_uncertain(monkeypatch):
    assert analyzed(monkeypatch, "voice_phishing", ["최근 비슷한 사건이 있었다"])["label"] == "uncertain"
    assert analyzed(monkeypatch, "voice_phishing", ["***"])["label"] == "uncertain"
    assert analyzed(monkeypatch, "normal", [])["label"] == "normal"


def test_non_phishing_skips_evidence_check(monkeypatch):
    other = analyzed(monkeypatch, "other_scam", ["녹취에 없는 말"])
    assert other["label"] == "other_scam" and other["evidence"] == []
    assert analyzed(monkeypatch, "normal", ["녹취에 없는 말"])["evidence"] == []


def test_prompt_forbids_identity_and_outside_facts():
    for rule in ("단정하지 않습니다", "최근 사건", "글자 그대로"):
        assert rule in llm.ANALYSIS_SYSTEM


def test_generated_scenario_is_validated_and_cleaned():
    from guard import reports

    good = reports._rule_scenario("제목")
    good["steps"][0]["messages"] = ["010-1111-2222로 https://real.example/a 접속"]
    cleaned = reports.validate(good)
    assert "1111" not in cleaned["steps"][0]["msgs"][0] and "real.example" not in cleaned["steps"][0]["msgs"][0]
    assert cleaned["steps"][0]["choices"][0]["act"] is True
    short = reports._rule_scenario("제목")
    short["steps"].pop()
    with pytest.raises(ValueError):
        reports.validate(short)
    two_safe = reports._rule_scenario("제목")
    two_safe["steps"][0]["choices"][1]["safe"] = True
    with pytest.raises(ValueError):
        reports.validate(two_safe)


def _capture_llm(monkeypatch):
    seen = {}

    def ask(system, user, schema, name="llm"):
        seen["user"] = user
        return {"label": "normal", "confidence": 0.9, "scam_type": "none", "summary": "요약", "evidence": []}

    monkeypatch.setattr(config, "LLM", "anthropic")
    monkeypatch.setattr(llm, "_ask_json", ask)
    return seen


def test_rag_hits_are_passed_to_llm(monkeypatch):
    seen = _capture_llm(monkeypatch)
    monkeypatch.setattr(remote_rag, "search", lambda q: [{"title": "대환대출 사기", "scam_type": "대출빙자", "summary": "선납 이자 요구"}])
    assert llm.analyze("안녕")["label"] == "normal"
    assert "<reference>" in seen["user"] and "대환대출 사기" in seen["user"]


def test_rag_failure_falls_back_to_llm_only(monkeypatch):
    seen = _capture_llm(monkeypatch)
    monkeypatch.setattr(config, "RAG_URL", "http://rag.invalid")

    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(remote_rag.httpx, "post", boom)
    assert llm.analyze("안녕")["label"] == "normal"
    assert "<reference>" not in seen["user"]


def test_tracing_records_usage_without_call_content_and_survives_failures(monkeypatch):
    from contextlib import contextmanager

    from guard import tracing

    seen = []

    class Client:
        def start_as_current_observation(self, **fields):
            seen.append(fields)

            @contextmanager
            def context():
                yield NS(update=lambda **f: seen.append(f))

            return context()

    secret = "안전 계좌로 옮기세요"
    answer = {**RESULT, "label": "voice_phishing", "scam_type": "unknown", "evidence": [secret]}
    response = NS(stop_reason="end_turn", usage=NS(input_tokens=11, output_tokens=7), content=[NS(type="text", text=json.dumps(answer))])
    monkeypatch.setattr(config, "LLM", "anthropic")
    monkeypatch.setattr(llm, "_client", NS(messages=NS(create=lambda **k: response)))
    monkeypatch.setattr(tracing, "_ready", True)
    monkeypatch.setattr(tracing, "_langfuse", Client())
    assert llm.analyze(secret)["label"] == "voice_phishing"
    assert any(f.get("name") == "판정" and f.get("as_type") == "generation" for f in seen)
    assert {"input": 11, "output": 7} in [f.get("usage_details") for f in seen]
    assert secret not in str(seen) and not any("input" in f or "output" in f for f in seen)

    class Broken:
        def start_as_current_observation(self, **_):
            raise OSError("down")

    monkeypatch.setattr(tracing, "_langfuse", Broken())
    assert llm.analyze(secret)["label"] == "voice_phishing"
