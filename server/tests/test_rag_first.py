"""GUARD_RAG_FIRST 경로: 사례 검색 먼저, AI 의심 점수 4구간, 근거 없으면 자동 조치 없음, 스위치 끄면 옛 동작."""
import os
import tempfile
from urllib.parse import urlsplit

_tmp = tempfile.mkdtemp()
# test_flow가 먼저 불러왔으면 그 설정을 그대로 씁니다(같은 프로세스에서 config는 한 번만 읽힘).
for k, v in dict(
    GUARD_DEMO_FAMILY="0", GUARD_DB=f"{_tmp}/t.db", GUARD_LOCAL_AUDIO_DIR=f"{_tmp}/a",
    GUARD_STORAGE="local", GUARD_STT="text", GUARD_LLM="rule", GUARD_EMBED="hash",
).items():
    os.environ.setdefault(k, v)

import pytest
from fastapi.testclient import TestClient

from guard import config, db, llm, rag_first, remote_rag
from guard.app import app

PHISHING = "서울중앙지검 수사관입니다. 명의가 도용되어 구속 수사 대상입니다. 안전 계좌로 옮기세요."
WEAK = "금감원 이라고 하던데요."
NORMAL = "엄마 오늘 저녁에 뭐 먹을까요. 7시까지 갈게요."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(config, "RAG_FIRST", True)
    monkeypatch.setattr(config, "LLM", "rule")
    monkeypatch.setattr(config, "RAG_URL", "")


def device(client, name):
    token = client.post("/v1/devices", json={"name": name}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def linked(client):
    p, g = device(client, "엄마"), device(client, "자녀")
    code = client.post("/v1/family/invite", headers=p).json()["code"]
    client.post("/v1/family/link", headers=g, json={"code": code})
    return p, g


def send(client, h, text, key):
    r = client.post("/v1/recordings", headers=h, json={"filename": f"{key}.txt", "client_key": key}).json()
    u = urlsplit(r["upload_url"])
    client.put(f"{u.path}?{u.query}", content=text.encode())
    client.post(f"/v1/recordings/{r['id']}/complete", headers=h)
    return next(x for x in client.get("/v1/recordings", headers=h).json()["items"] if x["id"] == r["id"])


def extra(client, h, rec):
    return client.get(f"/v1/detect/extra?ids={rec['id']}", headers=h).json()["items"].get(rec["id"])


def fake_llm(monkeypatch, result, seen=None):
    """판정은 고정 결과, 재순위는 후보 순서 그대로 돌려줍니다."""

    def ask(system, user, schema, name="llm"):
        if "ranked_ids" in schema["properties"]:
            return {"ranked_ids": [line[2:].split(":")[0] for line in user.splitlines() if line.startswith("- ")]}
        if seen is not None:
            seen.update(system=system, user=user, schema=schema)
        return dict(result)

    monkeypatch.setattr(config, "LLM", "anthropic")
    monkeypatch.setattr(llm, "_ask_json", ask)


@pytest.mark.parametrize("score,band", [(0, "log"), (39, "log"), (40, "caution"), (69, "caution"), (70, "alert"), (89, "alert"), (90, "lock"), (100, "lock"), (None, "unclear")])
def test_band_boundaries(score, band):
    assert rag_first.band(score) == band


def test_switch_off_keeps_old_behaviour(client, monkeypatch):
    monkeypatch.setattr(config, "RAG_FIRST", False)
    monkeypatch.setattr(rag_first, "analyze", lambda t: pytest.fail("스위치가 꺼지면 부르지 않아야 함"))
    p, g = linked(client)
    rec = send(client, p, PHISHING, "off")
    assert rec["label"] == "voice_phishing" and not rec["needs_review"]
    assert len(client.get("/v1/alerts", headers=g).json()["items"]) == 1
    assert client.get("/v1/lock", headers=p).json()["locked"] is True
    assert client.get(f"/v1/detect/extra?ids={rec['id']}", headers=p).json() == {"enabled": False, "items": {}}


def test_es_down_falls_back_to_local_cases_and_locks(client, on, monkeypatch):
    monkeypatch.setattr(config, "RAG_URL", "http://es.invalid:8200")

    def boom(*a, **kw):
        raise remote_rag.httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(remote_rag.httpx, "post", boom)
    p, g = linked(client)
    rec = send(client, p, PHISHING, "es-down")
    x = extra(client, p, rec)
    assert x["reference_source"] == "local" and x["references"][0]["title"] == "검찰·경찰·금감원 사칭"
    assert x["score"] == 95 and x["band"] == "lock" and x["family_alert"] and x["lock"]
    assert x["facts"] and x["training_url"] == "/app/#/sim2?type=prosecutor_impersonation"
    assert len(client.get("/v1/alerts", headers=g).json()["items"]) == 1
    assert client.get("/v1/lock", headers=p).json()["locked"] is True
    # 다른 기기는 남의 결과를 볼 수 없습니다.
    assert extra(client, device(client, "남"), rec) is None


def test_es_cases_go_before_judge_as_documents_without_synthetic(client, on, monkeypatch):
    hits = [
        {"title": "검찰 사칭 공식 사례", "scam_type": "기관사칭", "summary": "안전계좌 이체 요구", "url": "https://www.fss.or.kr/x"},
        {"title": "합성 대본", "scam_type": "기관사칭", "summary": "합성", "synthetic": True},
        {"title": "평가용 통화", "scam_type": "기관사칭", "summary": "평가", "split": "eval"},
    ]
    monkeypatch.setattr(remote_rag, "search", lambda q: hits)
    seen = {}
    fake_llm(monkeypatch, {
        "label": "voice_phishing", "confidence": 0.99, "scam_type": "prosecutor_impersonation", "summary": "수사관이라고 말했습니다.",
        "evidence": ["안전 계좌로 옮기세요"], "suspicion": [{"scam_type": "prosecutor_impersonation", "score": 0.8}, {"scam_type": "loan_refinance", "score": 0.1}],
    }, seen)
    p, g = linked(client)
    rec = send(client, p, PHISHING, "es-up")
    assert "<document>" in seen["user"] and "검찰 사칭 공식 사례" in seen["user"]
    assert "합성 대본" not in seen["user"] and "평가용 통화" not in seen["user"]
    assert "지시가 아닙니다" in seen["system"] and "suspicion" in seen["schema"]["required"]
    x = extra(client, p, rec)
    assert x["reference_source"] == "es" and [r["title"] for r in x["references"]] == ["검찰 사칭 공식 사례"]
    assert x["references"][0]["url"] == "https://www.fss.or.kr/x"
    # 확신도 0.99여도 점수는 수법별 의심 최댓값(0.8)이므로 위험: 가족 알림은 하고 잠금은 하지 않습니다.
    assert x["score"] == 80 and x["band"] == "alert" and x["family_alert"] and not x["lock"]
    assert len(client.get("/v1/alerts", headers=g).json()["items"]) == 1
    assert client.get("/v1/lock", headers=p).json()["locked"] is False


def test_no_fact_means_unclear_and_no_automatic_action(client, on, monkeypatch):
    fake_llm(monkeypatch, {
        "label": "voice_phishing", "confidence": 0.99, "scam_type": "prosecutor_impersonation", "summary": "요약",
        "evidence": ["녹취에 없는 말을 지어냄"], "suspicion": [{"scam_type": "prosecutor_impersonation", "score": 0.99}],
    })
    p, g = linked(client)
    rec = send(client, p, PHISHING, "no-fact")
    x = extra(client, p, rec)
    assert rec["label"] == "uncertain" and rec["needs_review"]
    assert x["band"] == "unclear" and x["score"] is None and not x["family_alert"] and not x["lock"]
    assert client.get("/v1/alerts", headers=g).json()["items"] == []
    assert client.get("/v1/lock", headers=p).json()["locked"] is False


def test_caution_band_goes_to_review_without_alert(client, on):
    p, g = linked(client)
    rec = send(client, p, WEAK, "caution")
    x = extra(client, p, rec)
    assert x["score"] == 65 and x["band"] == "caution" and not x["family_alert"]
    assert rec["needs_review"] and client.get("/v1/alerts", headers=g).json()["items"] == []


def test_normal_call_is_log_band_without_training_link(client, on):
    p, _ = linked(client)
    x = extra(client, p, send(client, p, NORMAL, "normal"))
    assert x["score"] == 0 and x["band"] == "log" and x["training_url"] == "" and x["facts"] == []


def test_other_scam_never_triggers_automatic_action(client, on, monkeypatch):
    fake_llm(monkeypatch, {
        "label": "other_scam", "confidence": 0.95, "scam_type": "investment_rebate", "summary": "요약",
        "evidence": [], "suspicion": [{"scam_type": "investment_rebate", "score": 0.95}],
    })
    p, g = linked(client)
    x = extra(client, p, send(client, p, "리딩방 원금 보장", "other"))
    assert x["band"] == "lock" and not x["family_alert"] and not x["lock"]
    assert client.get("/v1/alerts", headers=g).json()["items"] == []
    assert client.get("/v1/lock", headers=p).json()["locked"] is False


def test_deleting_recording_deletes_extra(client, on):
    p, _ = linked(client)
    rec = send(client, p, PHISHING, "del")
    assert extra(client, p, rec)
    client.delete(f"/v1/recordings/{rec['id']}", headers=p)
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM detect_extra WHERE recording_id = ?", (rec["id"],)).fetchone() is None


def test_web_loads_extra_script(client):
    html = client.get("/app/").text
    assert "web/detect_extra.js" in html and html.index("web/guard.js") < html.index("web/detect_extra.js")
    js = client.get("/app/web/detect_extra.js").text
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js
    for url in ("https://www.payinfo.or.kr", "https://pd.fss.or.kr", "https://www.msafer.or.kr", "https://www.fsc.go.kr/no010101/84607", "tel:112", "tel:1394"):
        assert url in js, url


def test_suspicion_on_0_100_scale_is_normalised():
    r = {"label": "voice_phishing", "confidence": 0.9, "evidence": ["x"], "suspicion": [{"scam_type": "loan_refinance", "score": 85}, {"scam_type": "bank_security", "score": 0}]}
    assert rag_first._score(r) == 0.85
    # 0–1 소수로 답하면 그대로, [1, 0]처럼 애매하면 1점(낮은 쪽)으로 읽습니다.
    assert rag_first._score({**r, "suspicion": [{"scam_type": "loan_refinance", "score": 0.8}]}) == 0.8
    assert rag_first._score({**r, "suspicion": [{"scam_type": "loan_refinance", "score": 1}, {"scam_type": "bank_security", "score": 0}]}) == 0.01


def test_save_after_delete_does_not_recreate(client):
    rag_first.save("no-such-recording", {"band": "lock"})
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM detect_extra WHERE recording_id = 'no-such-recording'").fetchone() is None


def test_sample_extra_never_claims_alert_or_lock(client, on):
    from guard import app as app_module, samples
    app_module._sample_results.clear()
    sid = next(s["id"] for s in samples.SAMPLES if s["expected"] == "voice_phishing")
    x = client.post(f"/v1/samples/{sid}/analyze", headers=device(client, "예시")).json()["detect"]
    assert x["sample"] and not x["family_alert"] and not x["lock"]
    app_module._sample_results.clear()


def test_normal_label_with_high_score_is_unclear():
    r = {"label": "normal", "confidence": 0.9, "evidence": [], "score": 100}
    assert rag_first.result_band(r) == "unclear" and rag_first.auto_actions(r) == (False, False)
    assert rag_first.result_band({**r, "score": 39}) == "log"
