"""AWS 없이 text STT와 rule 판정으로 전체 흐름을 검증합니다."""
import os
import tempfile
from urllib.parse import urlsplit

_tmp = tempfile.mkdtemp()
os.environ.update(
    GUARD_DB=f"{_tmp}/t.db",
    GUARD_LOCAL_AUDIO_DIR=f"{_tmp}/a",
    GUARD_STORAGE="local",
    GUARD_STT="text",
    GUARD_LLM="rule",
    GUARD_EMBED="hash",
    GUARD_ADMIN_TOKEN="admin",
)

import pytest
from fastapi.testclient import TestClient

from guard import config, rag
from guard.app import app

PHISHING = "서울중앙지검 수사관입니다. 명의가 도용되어 구속 수사 대상입니다. 안전 계좌로 옮기세요."
WEAK = "금감원 이라고 하던데요."
INVEST = "리딩방에서 원금 보장이라고 했고 출금 수수료를 내라고 합니다."
NORMAL = "엄마 오늘 저녁에 뭐 먹을까요. 7시까지 갈게요."


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def device(client, name):
    token = client.post("/v1/devices", json={"name": name}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def send(client, h, text, key):
    r = client.post("/v1/recordings", headers=h, json={"filename": f"{key}.txt", "client_key": key}).json()
    u = urlsplit(r["upload_url"])
    assert client.put(f"{u.path}?{u.query}", content=text.encode()).status_code == 200
    assert client.post(f"/v1/recordings/{r['id']}/complete", headers=h).status_code == 200
    return next(x for x in client.get("/v1/recordings", headers=h).json()["items"] if x["id"] == r["id"])


def linked(client, name="엄마"):
    protected, guardian = device(client, name), device(client, "자녀")
    code = client.post("/v1/family/invite", headers=protected).json()["code"]
    assert client.post("/v1/family/link", headers=guardian, json={"code": code}).json()["protected_name"] == name
    return protected, guardian


def test_auth_required(client):
    assert client.get("/v1/recordings").status_code == 401
    assert client.get("/v1/recordings", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_phishing_alerts_guardian_without_transcript(client):
    p, g = linked(client)
    rec = send(client, p, PHISHING, "a")
    assert rec["label"] == "voice_phishing" and not rec["needs_review"]
    assert rec["matches"][0]["id"] == "prosecutor_impersonation"
    items = client.get("/v1/alerts", headers=g).json()["items"]
    assert len(items) == 1 and "엄마" in items[0]["title"]
    assert "안전 계좌로 옮기세요" not in items[0]["body"]
    assert "transcript" not in rec


def test_low_confidence_goes_to_review_not_alert(client):
    p, g = linked(client)
    rec = send(client, p, WEAK, "weak")
    assert rec["label"] == "voice_phishing" and rec["needs_review"]
    assert client.get("/v1/alerts", headers=g).json()["items"] == []


def test_other_scam_review_goes_to_separate_dataset(client):
    p, g = linked(client)
    rec = send(client, p, INVEST, "inv")
    assert rec["label"] == "other_scam" and rec["needs_review"]
    assert client.get("/v1/alerts", headers=g).json()["items"] == []
    assert client.get("/v1/admin/review-dataset.jsonl").status_code == 403
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=p, json={"label": "other_scam"}).json()["in_dataset"]
    dump = client.get("/v1/admin/review-dataset.jsonl", headers={"X-Admin-Token": "admin"}).text
    assert rec["id"] in dump and "리딩방" in dump
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=p, json={"label": "normal"}).json()["in_dataset"] is False
    assert rec["id"] not in client.get("/v1/admin/review-dataset.jsonl", headers={"X-Admin-Token": "admin"}).text


def test_normal_call_keeps_no_transcript_and_audio_is_deleted(client):
    import sqlite3

    p = device(client, "일상")
    rec = send(client, p, NORMAL, "n")
    assert rec["label"] == "normal"
    row = sqlite3.connect(config.DB_PATH).execute("SELECT transcript, s3_key FROM recordings WHERE id = ?", (rec["id"],)).fetchone()
    assert row[0] is None
    assert not (config.LOCAL_AUDIO_DIR / row[1].replace("/", "_")).exists()


def test_recommendations_rank_by_frequency(client):
    p = device(client, "추천")
    assert client.get("/v1/recommendations", headers=p).json()["items"] == []
    send(client, p, INVEST, "1")
    send(client, p, PHISHING, "2")
    send(client, p, INVEST + " ", "3")
    items = client.get("/v1/recommendations", headers=p).json()["items"]
    assert items[0]["id"] == "investment_rebate" and items[0]["count"] == 2
    assert items[1]["id"] == "prosecutor_impersonation"


def test_devices_are_isolated(client):
    a, b = device(client, "A"), device(client, "B")
    rec = send(client, a, PHISHING, "x")
    assert client.get("/v1/recordings", headers=b).json()["items"] == []
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=b, json={"label": "normal"}).status_code == 404
    assert client.delete(f"/v1/recordings/{rec['id']}", headers=b).status_code == 404


def test_duplicate_upload_is_skipped_and_bad_token_rejected(client):
    h = device(client, "중복")
    send(client, h, NORMAL, "dup")
    assert client.post("/v1/recordings", headers=h, json={"filename": "dup.txt", "client_key": "dup"}).json()["already_uploaded"]
    r = client.post("/v1/recordings", headers=h, json={"filename": "z.txt", "client_key": "z"}).json()
    assert client.put(f"/v1/local-upload/{r['id']}?token=bad", content=b"x").status_code == 403
    assert client.post("/v1/recordings", headers=h, json={"filename": "z.exe", "client_key": "e"}).status_code == 415


def test_invite_is_single_use_and_guardian_can_be_removed(client):
    p, g = device(client, "P"), device(client, "G")
    code = client.post("/v1/family/invite", headers=p).json()["code"]
    assert client.post("/v1/family/link", headers=p, json={"code": code}).status_code == 400
    assert client.post("/v1/family/link", headers=g, json={"code": code}).status_code == 200
    assert client.post("/v1/family/link", headers=device(client, "H"), json={"code": code}).status_code == 400
    gid = client.get("/v1/family", headers=p).json()["guardians"][0]["id"]
    client.delete(f"/v1/family/guardians/{gid}", headers=p)
    send(client, p, PHISHING, "after")
    assert client.get("/v1/alerts", headers=g).json()["items"] == []


def test_hybrid_retrieval_finds_type():
    assert rag.retrieve("저금리 대환대출로 갈아타려면 선납 이자를 입금하라고 함")[0]["id"] == "loan_refinance"
    assert rag.retrieve("아들이 폰이 고장나서 다른 번호로 합의금을 보내달라고 함")[0]["id"] == "family_impersonation"
