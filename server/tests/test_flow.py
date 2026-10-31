"""AWS 없이 text STT와 rule 판정으로 전체 흐름을 검증합니다."""
import os
import tempfile
from urllib.parse import urlsplit

_tmp = tempfile.mkdtemp()
os.environ.update(
    GUARD_DEMO_FAMILY="0",
    GUARD_DB=f"{_tmp}/t.db",
    GUARD_LOCAL_AUDIO_DIR=f"{_tmp}/a",
    GUARD_STORAGE="local",
    GUARD_STT="text",
    GUARD_LLM="rule",
    GUARD_EMBED="hash",
)

import pytest
from fastapi.testclient import TestClient

from guard import config, db, rag
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
    assert len(items) == 1 and items[0]["title"] == "엄마님 보이스피싱 의심 통화"
    assert items[0]["body"] == db.FAMILY_ALERT_BODY
    assert set(items[0]) == {"id", "title", "body", "acked", "created_at"}
    assert "transcript" not in rec
    # 가족은 분석 결과를 조회할 수 없습니다.
    assert client.get("/v1/recordings", headers=g).json()["items"] == []
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=g, json={"label": "normal"}).status_code == 404


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
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=p, json={"label": "other_scam"}).json()["in_dataset"]
    with db.connect() as conn:
        row = conn.execute("SELECT transcript FROM review_dataset WHERE recording_id = ?", (rec["id"],)).fetchone()
    assert "리딩방" in row["transcript"]
    assert client.post(f"/v1/recordings/{rec['id']}/review", headers=p, json={"label": "normal"}).json()["in_dataset"] is False
    with db.connect() as conn:
        assert not conn.execute("SELECT 1 FROM review_dataset WHERE recording_id = ?", (rec["id"],)).fetchone()


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


def test_text_mode_rejects_audio_and_binary(client):
    h = device(client, "음성")
    assert client.post("/v1/recordings", headers=h, json={"filename": "call.m4a", "client_key": "m"}).status_code == 415
    r = client.post("/v1/recordings", headers=h, json={"filename": "fake.txt", "client_key": "f"}).json()
    u = urlsplit(r["upload_url"])
    client.put(f"{u.path}?{u.query}", content=b"\x00\x00\x00\x18ftyp3gp4\xff\xfe\xfa")
    client.post(f"/v1/recordings/{r['id']}/complete", headers=h)
    rec = client.get("/v1/recordings", headers=h).json()["items"][0]
    assert rec["status"] == "failed" and rec["label"] is None


def test_openai_stt_sends_audio_and_enforces_limit(client, monkeypatch):
    from types import SimpleNamespace as NS

    from guard import providers

    seen = {}

    def create(**kw):
        seen.update(kw)
        return NS(text=" " + PHISHING + " ")

    monkeypatch.setattr(config, "STT", "openai")
    monkeypatch.setattr(providers, "_openai", NS(audio=NS(transcriptions=NS(create=create))))
    h = device(client, "전사")
    assert client.post("/v1/recordings", headers=h, json={"filename": "a.amr", "client_key": "amr"}).status_code == 415
    r = client.post("/v1/recordings", headers=h, json={"filename": "a.m4a", "client_key": "a"}).json()
    u = urlsplit(r["upload_url"])
    client.put(f"{u.path}?{u.query}", content=b"\x00audio")
    client.post(f"/v1/recordings/{r['id']}/complete", headers=h)
    rec = client.get("/v1/recordings", headers=h).json()["items"][0]
    assert rec["label"] == "voice_phishing" and seen["language"] == "ko" and seen["file"][1] == b"\x00audio"

    monkeypatch.setattr(config, "OPENAI_STT_MAX_BYTES", 2)
    r = client.post("/v1/recordings", headers=h, json={"filename": "b.m4a", "client_key": "b"}).json()
    u = urlsplit(r["upload_url"])
    client.put(f"{u.path}?{u.query}", content=b"\x00audio")
    client.post(f"/v1/recordings/{r['id']}/complete", headers=h)
    assert client.get("/v1/recordings", headers=h).json()["items"][0]["status"] == "failed"


def test_samsung_3gp_header_becomes_m4a_without_touching_audio():
    from guard.providers import _as_m4a

    head = (24).to_bytes(4, "big") + b"ftyp3gp4\x00\x00\x00\x01isom3gp4"
    body = b"mdat-3gp4-audio-mp4a"
    out = _as_m4a(head + body)
    assert out[8:12] == b"M4A " and out[20:24] == b"M4A " and out[16:20] == b"isom"
    assert out[24:] == body and len(out) == len(head + body)
    amr = head + b"samr"
    assert _as_m4a(amr) == amr


def test_web_ui_is_served_without_exposing_repo(client):
    assert client.get("/app/").status_code == 200 and "guard.js" in client.get("/app/").text
    assert client.get("/app/js/app.js").status_code == 200
    assert client.get("/app/css/style.css").headers["cache-control"] == "no-cache"
    for path in ("/app/.git/config", "/app/server/guard/config.py", "/app/js/../../server/.env", "/app/web/../guard/config.py"):
        assert client.get(path).status_code == 404, path


def test_high_confidence_phishing_locks_only_that_device(client):
    p, g = linked(client)
    assert client.get("/v1/lock", headers=p).json()["locked"] is False
    send(client, p, WEAK, "weak-lock")
    assert client.get("/v1/lock", headers=p).json()["locked"] is False
    rec = send(client, p, PHISHING, "lock")
    state = client.get("/v1/lock", headers=p).json()
    assert state["locked"] and 0 < state["remaining"] <= config.LOCK_SECONDS and "viva.republica.toss" in state["apps"]
    assert client.get("/v1/lock", headers=g).json()["locked"] is False
    # 잠금 상태만 가족에게 보이고, 사기범이 시킨 판정 변경이나 삭제로는 풀리지 않습니다.
    assert client.get("/v1/family", headers=g).json()["protected"][0]["locked"] is True
    client.post(f"/v1/recordings/{rec['id']}/review", headers=p, json={"label": "normal"})
    client.delete(f"/v1/recordings/{rec['id']}", headers=p)
    assert client.get("/v1/lock", headers=p).json()["locked"] is True


def test_self_release_waits_and_cannot_extend_or_unlock_immediately(client):
    p = device(client, "해제")
    assert client.post("/v1/lock", headers=p, json={"minutes": 0}).status_code == 422
    assert client.post("/v1/lock", headers=p, json={"minutes": 61}).status_code == 422
    assert client.post("/v1/lock/release", headers=p).json()["locked"] is False
    client.post("/v1/lock", headers=p, json={"minutes": 60})
    first = client.post("/v1/lock/release", headers=p).json()
    assert first["locked"] and first["remaining"] <= config.LOCK_RELEASE_WAIT
    assert client.post("/v1/lock/release", headers=p).json()["remaining"] <= first["remaining"]
    # 짧은 수동 잠금이 남은 시간을 줄이지 않습니다.
    client.post("/v1/lock", headers=p, json={"minutes": 60})
    assert client.post("/v1/lock", headers=p, json={"minutes": 1}).json()["remaining"] > 3000


def test_only_linked_guardian_can_unlock(client):
    p, g = linked(client)
    pid = client.get("/v1/family", headers=g).json()["protected"][0]["id"]
    client.post("/v1/lock", headers=p, json={"minutes": 60})
    assert client.post(f"/v1/family/protected/{pid}/unlock", headers=device(client, "남")).status_code == 404
    assert client.get("/v1/lock", headers=p).json()["locked"] is True
    assert client.post(f"/v1/family/protected/{pid}/unlock", headers=g).status_code == 200
    assert client.get("/v1/lock", headers=p).json()["locked"] is False
    assert client.get("/v1/family", headers=g).json()["protected"][0]["locked"] is False


def family_of_three(client):
    mom, a = linked(client)
    b = device(client, "둘째")
    code = client.post("/v1/family/invite", headers=mom).json()["code"]
    client.post("/v1/family/link", headers=b, json={"code": code})
    return mom, a, b


def test_passphrase_is_shared_across_family_and_changes_daily(client, monkeypatch):
    from datetime import datetime

    from guard import passphrase

    assert client.get("/v1/family/passphrase", headers=device(client, "혼자")).json() == {"linked": False}
    mom, a, b = family_of_three(client)
    get = lambda h: client.get("/v1/family/passphrase", headers=h).json()
    # 서로 직접 연결되지 않은 형제도 같은 단어를 봅니다.
    assert get(mom)["words"] == get(a)["words"] == get(b)["words"] and len(get(mom)["words"]) == 2
    other, _ = linked(client)
    days = [datetime(2026, 11, d, 23, 59, tzinfo=passphrase.KST) for d in range(1, 9)]
    seen, others = [], []
    for day in days:
        monkeypatch.setattr(passphrase, "now_kst", lambda day=day: day)
        seen.append(tuple(get(mom)["words"]))
        others.append(tuple(get(other)["words"]))
        assert get(mom)["seconds_left"] == 60
    assert len(set(seen)) > 1 and seen != others


def test_emergency_answer_is_hashed_normalized_and_rate_limited(client):
    import sqlite3

    mom, a, b = family_of_three(client)
    verify = lambda h, answer: client.post("/v1/family/passphrase/emergency/verify", headers=h, json={"answer": answer})
    body = {"question": "첫 반려견 이름은?", "answer": "초코 Dog"}
    assert client.put("/v1/family/passphrase/emergency", headers=device(client, "혼자"), json=body).status_code == 400
    assert verify(b, "초코").status_code == 404
    assert client.put("/v1/family/passphrase/emergency", headers=mom, json=body).status_code == 200
    seen = client.get("/v1/family/passphrase", headers=b).json()["emergency"]
    assert seen == {"question": "첫 반려견 이름은?", "set_by": "엄마"}
    assert verify(b, "초코dog").json()["match"] is True
    with sqlite3.connect(config.DB_PATH) as conn:
        assert not any("초코" in str(v) for row in conn.execute("SELECT * FROM emergency_phrases") for v in row)
    for _ in range(5):
        assert verify(a, "틀림").json()["match"] is False
    assert verify(a, "초코dog").status_code == 429


def test_samples_show_result_without_touching_records_alerts_or_lock(client):
    p, g = linked(client)
    assert client.get("/v1/samples").status_code == 401
    items = client.get("/v1/samples", headers=p).json()["items"]
    kinds = [s["expected"] for s in items]
    assert kinds.count("voice_phishing") == 3 and kinds.count("normal") == 3
    results = {s["id"]: client.post(f"/v1/samples/{s['id']}/analyze", headers=p).json() for s in items}
    assert client.post("/v1/samples/none/analyze", headers=p).status_code == 404
    # 규칙 판정의 정확도가 아니라 기록과 알림에 영향이 없는지 봅니다.
    assert results["prosecutor"]["label"] == "voice_phishing" and results["prosecutor"]["matches"]
    assert 0 < results["prosecutor"]["confidence"] <= 1
    assert results["dinner"]["label"] == "normal" and results["dinner"]["evidence"] == []
    assert client.get("/v1/recordings", headers=p).json()["items"] == []
    assert client.get("/v1/alerts", headers=g).json()["items"] == []
    assert client.get("/v1/lock", headers=p).json()["locked"] is False


def test_s3_mode_keeps_voice_per_device_and_deletes_after_analysis(client, monkeypatch):
    from guard import providers

    class FakeS3:
        objects: dict[str, bytes] = {}
        exceptions = None

        def generate_presigned_url(self, _, Params, ExpiresIn):
            return f"https://s3.example/{Params['Key']}"

        def upload_file(self, path, bucket, key):
            assert bucket == "voice-test"
            self.objects[key] = open(path, "rb").read()

        def head_object(self, Bucket, Key):
            return {"ContentLength": len(self.objects[Key])}

        def get_object(self, Bucket, Key):
            from io import BytesIO

            return {"Body": BytesIO(self.objects[Key])}

        def delete_object(self, Bucket, Key):
            del self.objects[Key]

    fake = FakeS3()
    monkeypatch.setattr(config, "STORAGE", "s3")
    monkeypatch.setattr(config, "S3_BUCKET", "voice-test")
    monkeypatch.setattr(providers, "_s3", fake)
    h = device(client, "저장")
    me = client.post("/v1/recordings", headers=h, json={"filename": "app.txt", "client_key": "app"}).json()
    assert me["upload_url"].startswith("https://s3.example/recordings/")
    r = client.post("/v1/recordings", headers=h, json={"filename": "web.txt", "client_key": "web", "direct": False}).json()
    u = urlsplit(r["upload_url"])
    assert client.put(f"{u.path}?{u.query}", content=NORMAL.encode()).status_code == 200
    key = next(iter(fake.objects))
    assert key.startswith("recordings/") and key.endswith(f"/{r['id']}.txt")
    assert not (config.LOCAL_AUDIO_DIR / key.replace("/", "_")).exists()
    assert client.post(f"/v1/recordings/{r['id']}/complete", headers=h).status_code == 200
    assert fake.objects == {}


def test_family_role_is_saved_shown_to_family_and_validated(client):
    assert client.post("/v1/devices", json={"name": "x", "role": "boss"}).status_code == 422
    token = client.post("/v1/devices", json={"name": "지수", "role": "daughter", "memo": "첫째"}).json()["token"]
    child = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/devices/me", headers=child).json() == {"name": "지수", "role": "daughter", "memo": "첫째"}
    parent = device(client, "엄마")
    code = client.post("/v1/family/invite", headers=child).json()["code"]
    client.post("/v1/family/link", headers=parent, json={"code": code})
    seen = client.get("/v1/family", headers=parent).json()["protected"][0]
    assert seen["role"] == "daughter" and seen["memo"] == "첫째"
    assert client.put("/v1/devices/me", headers=parent, json={"role": "mom"}).status_code == 200
    assert client.get("/v1/family", headers=child).json()["guardians"][0]["role"] == "mom"
    assert client.put("/v1/devices/me", headers=parent, json={"role": "x"}).status_code == 422


def test_demo_family_is_off_by_default_and_never_logs_in_real_devices(client, monkeypatch):
    assert client.get("/v1/demo/family").status_code == 404
    assert client.post("/v1/demo/family/demo-me/login").status_code == 404
    monkeypatch.setattr(config, "DEMO_FAMILY", True)
    db.seed_demo_family()
    db.seed_demo_family()
    items = client.get("/v1/demo/family").json()["items"]
    assert [m["name"] for m in items] == ["동현", "상우", "선형", "호연", "병국"]
    real = client.post("/v1/devices", json={"name": "실사용"}).json()["device_id"]
    assert client.post(f"/v1/demo/family/{real}/login").status_code == 404
    me = {"Authorization": "Bearer " + client.post("/v1/demo/family/demo-me/login").json()["token"]}
    mom = {"Authorization": "Bearer " + client.post("/v1/demo/family/demo-mom/login").json()["token"]}
    family = client.get("/v1/family", headers=me).json()
    assert len(family["guardians"]) == 4 and len(family["protected"]) == 4
    assert client.get("/v1/family/passphrase", headers=me).json()["words"] == client.get("/v1/family/passphrase", headers=mom).json()["words"]
    send(client, me, PHISHING, "demo")
    assert client.get("/v1/alerts", headers=mom).json()["items"][0]["title"] == "동현님 보이스피싱 의심 통화"


def test_reports_mask_private_data_hide_author_and_only_top_three_generate(client):
    # 앞선 테스트의 시연 제보가 상위권을 차지하지 않게 비웁니다.
    with db.connect() as conn:
        conn.execute("DELETE FROM reports")
        conn.execute("DELETE FROM report_votes")
    a, b = device(client, "제보자"), device(client, "독자")
    made = client.post("/v1/reports", headers=a, json={"category": "문자", "title": "택배 사칭 문자 신고", "body": "010-1234-5678 번호에서 https://evil.example/x 링크, 계좌 110-123-456789 입금 요구"})
    rid = made.json()["id"]
    items = client.get("/v1/reports", headers=b).json()["items"]
    item = next(i for i in items if i["id"] == rid)
    assert "1234-5678" not in item["body"] and "evil.example" not in item["body"] and "456789" not in item["body"]
    assert "device_id" not in item and item["mine"] is False
    assert client.post("/v1/reports", headers=a, json={"category": "없음", "title": "제목입니다", "body": "내용이 열 글자 넘습니다"}).status_code == 400
    # 투표 0개는 생성할 수 없습니다.
    fresh = client.post("/v1/reports", headers=a, json={"category": "기타", "title": "표 없는 제보", "body": "아직 아무도 추천하지 않은 제보입니다"}).json()["id"]
    assert client.post(f"/v1/reports/{fresh}/scenario", headers=a).status_code == 403
    client.post(f"/v1/reports/{rid}/vote", headers=b)
    client.post(f"/v1/reports/{rid}/vote", headers=b)
    assert next(i for i in client.get("/v1/reports", headers=b).json()["items"] if i["id"] == rid)["votes"] == 1
    made = client.post(f"/v1/reports/{rid}/scenario", headers=b)
    assert made.status_code == 200 and len(made.json()["steps"]) == 5
    assert client.delete(f"/v1/reports/{rid}", headers=b).status_code == 404
    assert client.delete(f"/v1/reports/{rid}", headers=a).status_code == 200
    for n in range(4):
        assert client.post("/v1/reports", headers=a, json={"category": "기타", "title": f"반복 제보 {n}", "body": "하루 제한을 확인하는 제보입니다"}).status_code == 200 or n == 3
    assert client.post("/v1/reports", headers=a, json={"category": "기타", "title": "초과 제보", "body": "하루 제한을 넘는 제보입니다"}).status_code == 429


def test_keep_audio_stores_after_analysis_until_user_deletes(client, monkeypatch):
    monkeypatch.setattr(config, "KEEP_AUDIO", True)
    assert client.get("/healthz").json()["keep_audio"] is True
    h = device(client, "보관")
    rec = send(client, h, NORMAL, "keep")
    assert rec["status"] == "done"
    import sqlite3

    key = sqlite3.connect(config.DB_PATH).execute("SELECT s3_key FROM recordings WHERE id = ?", (rec["id"],)).fetchone()[0]
    path = config.LOCAL_AUDIO_DIR / key.replace("/", "_")
    assert path.exists()
    assert client.delete(f"/v1/recordings/{rec['id']}", headers=h).status_code == 200
    assert not path.exists()


def test_feedback_and_user_dashboard(client):
    with db.connect() as conn:
        for table in ("recording_feedback", "training_results", "response_events"):
            conn.execute(f"DELETE FROM {table}")
    a, b = device(client, "대시A"), device(client, "대시B")
    phishing = send(client, a, PHISHING, "dash-p")
    normal = send(client, a, NORMAL, "dash-n")
    # 판정이 맞다는 확인, 오탐 신고, 미탐 신고
    client.post(f"/v1/recordings/{phishing['id']}/review", headers=a, json={"label": "voice_phishing"})
    other = send(client, b, PHISHING + " ", "dash-f")
    client.post(f"/v1/recordings/{other['id']}/review", headers=b, json={"label": "normal", "reason": "정상 통화"})
    client.post(f"/v1/recordings/{normal['id']}/review", headers=a, json={"label": "voice_phishing"})
    client.post("/v1/training", headers=a, json={"scenario": "agency", "tag": "기관 사칭", "score": 40})
    client.post("/v1/training", headers=a, json={"scenario": "agency", "tag": "기관 사칭", "score": 100})
    client.post("/v1/training", headers=a, json={"scenario": "loan", "tag": "대출 사기", "score": 60})
    assert client.post("/v1/training", headers=a, json={"scenario": "x", "tag": "y", "score": 101}).status_code == 422
    me = client.get("/v1/dashboard/me", headers=a).json()
    assert me["training"]["count"] == 3 and [w["scenario"] for w in me["training"]["weak"]] == ["loan"]
    assert me["calls"]["confirmed"] == 2
    assert client.get("/v1/dashboard/me", headers=b).json()["training"]["count"] == 0
    # 사용자가 기록을 지우면 라벨도 함께 지워집니다.
    client.delete(f"/v1/recordings/{normal['id']}", headers=a)
    assert client.get("/v1/dashboard/me", headers=a).json()["calls"]["confirmed"] == 1


def test_admin_api_is_removed(client):
    for path in ("dashboard", "ops", "feedback-dataset.jsonl", "review-dataset.jsonl"):
        assert client.get(f"/v1/admin/{path}").status_code == 404


def test_landing_demo_runs_only_fixed_samples_without_login(client):
    assert "방금 그 전화" in client.get("/").text
    assert len(client.get("/v1/demo/samples").json()["items"]) == 6
    assert client.post("/v1/demo/samples/prosecutor/analyze").json()["label"] == "voice_phishing"
    assert client.post("/v1/demo/samples/none/analyze").status_code == 404


def test_one_analysis_is_one_trace_and_other_requests_add_none(client, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace as NS

    from guard import tracing

    names = []

    @contextmanager
    def trace(name, **_):
        names.append(name)
        yield NS(update=lambda **f: None)

    monkeypatch.setattr(tracing, "trace", trace)
    h = device(client, "요청")
    client.get("/v1/lock", headers=h)
    send(client, h, NORMAL, "trace")
    assert names == ["통화 분석"]


def _quiz_answers(client, headers, right=True):
    from guard.quiz_cards import BY_ID

    gained = 0
    for card in client.get("/v1/quiz", headers=headers).json()["cards"]:
        is_scam = BY_ID[card["id"]]["is_scam"] == right
        gained += client.post(f"/v1/quiz/{card['id']}/answer", headers=headers, json={"is_scam": is_scam}).json()["gained"]
    return gained


def test_pet_grows_from_training_with_daily_limit_and_new_scenario_bonus(client):
    p, g = linked(client)
    start = client.get("/v1/pet", headers=p).json()
    assert start["xp"] == 0 and start["stage_name"] == "아기 코디" and start["mood"]["key"] == "green"
    assert device(client, "혼자") and client.get("/v1/pet", headers=device(client, "혼자")).json()["stage_name"] == "알"
    first = client.post("/v1/training", headers=p, json={"scenario": "agency", "tag": "기관 사칭", "score": 0}).json()["pet"]
    assert first["gained"] == 30
    assert client.post("/v1/training", headers=p, json={"scenario": "agency", "tag": "기관 사칭", "score": 100}).json()["pet"]["gained"] == 0
    assert client.post("/v1/training", headers=p, json={"scenario": "loan", "tag": "대출 사기", "score": 100}).json()["pet"]["gained"] == 10
    # 가족이 한 마리를 함께 키웁니다.
    assert client.get("/v1/pet", headers=g).json()["xp"] == 40


def test_pet_mood_shows_only_suspicion_to_family_and_turns_blue_after_check(client):
    p, g = linked(client)
    with db.connect() as conn:
        protected_id, guardian_id = (
            conn.execute("SELECT id FROM devices WHERE token = ?", (h["Authorization"].removeprefix("Bearer "),)).fetchone()["id"] for h in (p, g)
        )
        conn.execute(
            "INSERT INTO recordings (id, device_id, client_key, filename, s3_key, upload_token, status, needs_review, created_at)"
            " VALUES ('uncertain', ?, 'k', 'f', 's', 't', 'done', 1, ?)",
            (protected_id, db.now()),
        )
    # 애매한 통화는 본인만 노랑으로 보고 가족에게는 드러나지 않습니다.
    assert client.get("/v1/pet", headers=p).json()["mood"]["key"] == "yellow"
    assert client.get("/v1/pet", headers=g).json()["mood"]["key"] == "green"
    with db.connect() as conn:
        alert = conn.execute(
            "INSERT INTO alerts (guardian_id, protected_id, recording_id, title, body, created_at) VALUES (?, ?, 'r1', 't', 'b', ?)",
            (guardian_id, protected_id, db.now()),
        ).lastrowid
    seen = client.get("/v1/pet", headers=g).json()
    assert seen["mood"]["key"] == "red" and "r1" not in str(seen)
    assert client.post(f"/v1/alerts/{alert}/ack", headers=g).status_code == 200
    after = client.get("/v1/pet", headers=g).json()
    assert after["mood"]["key"] == "blue" and after["xp"] == 30


def test_quiz_hides_answers_until_answered_and_reveals_when_family_done(client):
    p, g = linked(client)
    view = client.get("/v1/quiz", headers=p).json()
    assert len(view["cards"]) == 3 and all("is_scam" not in c and "why" not in c for c in view["cards"])
    assert client.post("/v1/quiz/none/answer", headers=p, json={"is_scam": True}).status_code == 404
    assert _quiz_answers(client, p) == 25
    waiting = client.get("/v1/quiz", headers=p).json()
    assert waiting["finished"] and not waiting["reveal"] and waiting["dishes"] is None
    assert [m["score"] for m in waiting["members"] if not m["me"]] == [None]
    # 다시 답해도 점수와 정답 기록은 바뀌지 않습니다.
    assert _quiz_answers(client, p, right=False) == 0
    assert _quiz_answers(client, g, right=False) == 40
    done = client.get("/v1/quiz", headers=g).json()
    assert done["reveal"] and done["dishes"] == "자녀"
    assert client.get("/v1/pet", headers=g).json()["xp"] == 65


def test_weekly_quiz_always_mixes_scam_and_normal():
    from guard import pet

    for week in range(1, 53):
        cards = pet.week_cards(f"2026-W{week:02d}")
        kinds = {c["is_scam"] for c in cards}
        assert len({c["id"] for c in cards}) == 3 and kinds == {True, False}


def test_quiz_cards_clue_appears_in_text():
    from guard.quiz_cards import CARDS

    assert len(CARDS) == 15
    for card in CARDS:
        assert card["clue"] in card["text"], card["id"]
    # 발신자만 보고 찍을 수 없어야 합니다.
    assert not any(card["sender"] == "모르는 번호" for card in CARDS)
    scam_senders = {card["sender"] for card in CARDS if card["is_scam"]}
    assert scam_senders & {card["sender"] for card in CARDS if not card["is_scam"]}


def test_quiz_ignores_answers_to_retired_cards(client):
    p = device(client, "교체")
    from guard import pet

    with db.connect() as conn:
        device_id = conn.execute("SELECT id FROM devices WHERE token = ?", (p["Authorization"].removeprefix("Bearer "),)).fetchone()["id"]
        conn.execute(
            "INSERT INTO quiz_answers (device_id, week, card_id, answer, correct, created_at) VALUES (?, ?, 'retired', 1, 0, ?)",
            (device_id, pet.week_key(), db.now()),
        )
    assert client.get("/v1/pet", headers=p).json()["quiz_answered"] == 0
    assert client.get("/v1/quiz", headers=p).status_code == 200
