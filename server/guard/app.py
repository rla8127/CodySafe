import hmac
import json
import logging
import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import PurePosixPath

from fastapi.concurrency import run_in_threadpool
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, dashboard, db, llm, passphrase, pipeline, providers, reports, samples, tracing
from .lock_apps import LOCK_APPS
from .scam_kb import BY_ID, OTHER_SCAM, VOICE_PHISHING

INVITE_TTL = 600
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VERIFY_LIMIT = 5
VERIFY_WINDOW = 600
_verify_fails: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if config.DEMO_FAMILY:
        db.seed_demo_family()
        db.seed_demo_analytics()
    config.LOCAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    yield
    tracing.shutdown()


# uvicorn 기본 설정에서는 guard 로그의 INFO가 보이지 않습니다.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger("guard").addHandler(_handler)
logging.getLogger("guard").setLevel(logging.INFO)
logging.getLogger("guard").propagate = False

app = FastAPI(title="CodySafe Family Guard", lifespan=lifespan)


# 웹 MVP의 파일을 복사하지 않고 필요한 폴더만 내보냅니다. 저장소 루트는 내보내지 않습니다.
WEB_DIR = config.ROOT / "web"
for path, folder in (("css", "css"), ("js", "js"), ("assets", "assets")):
    app.mount(f"/app/{path}", StaticFiles(directory=config.ROOT.parent / folder), name=f"app-{path}")
app.mount("/app/web", StaticFiles(directory=WEB_DIR), name="app-web")


@app.middleware("http")
async def no_stale_ui(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(WEB_DIR / "landing.html", headers={"Cache-Control": "no-cache"})


@app.get("/app", include_in_schema=False)
def app_redirect():
    return RedirectResponse("/app/")


@app.get("/app/", include_in_schema=False)
def app_index():
    return FileResponse(WEB_DIR / "index.html")


def current_device(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM devices WHERE token = ?", (token,)).fetchone()
    if not token or not row:
        raise HTTPException(401, "invalid token")
    return row["id"]


ROLE_PATTERN = "^(mom|dad|me|son|daughter|child|brother|sister|uncle|aunt)$"


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    memo: str | None = Field(default=None, max_length=20)


class ProfileIn(BaseModel):
    role: str = Field(pattern=ROLE_PATTERN)
    memo: str | None = Field(default=None, max_length=20)


class LinkIn(BaseModel):
    code: str


class RecordingIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    client_key: str = Field(min_length=1, max_length=255)
    content_type: str = "application/octet-stream"
    # 브라우저는 S3로 바로 올리려면 버킷 CORS가 필요하므로 서버를 거칩니다.
    direct: bool = True


class LockIn(BaseModel):
    minutes: int = Field(ge=1, le=60)


class EmergencyIn(BaseModel):
    question: str = Field(min_length=2, max_length=60)
    answer: str = Field(min_length=2, max_length=60)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=60)


class ReportIn(BaseModel):
    category: str
    title: str = Field(min_length=4, max_length=60)
    body: str = Field(min_length=10, max_length=1000)


class ReviewIn(BaseModel):
    label: str = Field(pattern="^(voice_phishing|other_scam|normal)$")
    scam_type: str | None = None
    note: str = Field(default="", max_length=500)
    reason: str | None = Field(default=None, max_length=40)


class TrainingIn(BaseModel):
    scenario: str = Field(min_length=1, max_length=40)
    tag: str = Field(min_length=1, max_length=30)
    score: int = Field(ge=0, le=100)


@app.get("/healthz")
def healthz():
    return {"ok": True, "storage": config.STORAGE, "stt": config.STT, "llm": config.LLM, "embed": config.EMBED, "keep_audio": config.KEEP_AUDIO}


@app.post("/v1/devices")
def register(body: DeviceIn):
    device_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO devices (id, token, name, role, memo, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (device_id, token, body.name, body.role, body.memo, db.now()),
        )
    return {"device_id": device_id, "token": token}


# ---------- 커뮤니티 제보 ----------
_scenario_lock = threading.Lock()


def _report_rows(conn, device: str) -> list[dict]:
    rows = conn.execute(
        "SELECT r.*, COUNT(v.device_id) AS votes, MAX(v.device_id = ?) AS voted FROM reports r"
        " LEFT JOIN report_votes v ON v.report_id = r.id GROUP BY r.id ORDER BY votes DESC, r.created_at ASC LIMIT 100",
        (device,),
    ).fetchall()
    items = []
    for rank, r in enumerate(rows, 1):
        items.append(
            {
                # 작성자는 공개하지 않고, 본인 글인지만 알려 줍니다.
                "id": r["id"], "category": r["category"], "title": r["title"], "body": r["body"],
                "votes": r["votes"], "voted": bool(r["voted"]), "mine": r["device_id"] == device, "is_demo": bool(r["is_demo"]),
                "rank": rank if rank <= reports.TOP_N and r["votes"] > 0 else None,
                "scenario": json.loads(r["scenario"]) if r["scenario"] else None,
                "created_at": r["created_at"],
            }
        )
    return items


@app.get("/v1/reports")
def list_reports(device: str = Depends(current_device)):
    with db.connect() as conn:
        return {"items": _report_rows(conn, device), "categories": reports.CATEGORIES}


@app.post("/v1/reports")
def create_report(body: ReportIn, device: str = Depends(current_device)):
    if body.category not in reports.CATEGORIES:
        raise HTTPException(400, "unknown category")
    title, text = reports.mask(body.title), reports.mask(body.body)
    with db.connect() as conn:
        recent = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE device_id = ? AND created_at > ?", (device, db.now() - 86400)
        ).fetchone()[0]
        if recent >= reports.DAILY_LIMIT:
            raise HTTPException(429, "daily limit")
        report_id = conn.execute(
            "INSERT INTO reports (device_id, category, title, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (device, body.category, title, text, db.now()),
        ).lastrowid
    return {"id": report_id}


@app.post("/v1/reports/{report_id}/vote")
def vote_report(report_id: int, device: str = Depends(current_device)):
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM reports WHERE id = ?", (report_id,)).fetchone():
            raise HTTPException(404)
        conn.execute("INSERT OR IGNORE INTO report_votes VALUES (?, ?, ?)", (report_id, device, db.now()))
    return {"ok": True}


@app.delete("/v1/reports/{report_id}/vote")
def unvote_report(report_id: int, device: str = Depends(current_device)):
    with db.connect() as conn:
        conn.execute("DELETE FROM report_votes WHERE report_id = ? AND device_id = ?", (report_id, device))
    return {"ok": True}


@app.delete("/v1/reports/{report_id}")
def delete_report(report_id: int, device: str = Depends(current_device)):
    with db.connect() as conn:
        deleted = conn.execute("DELETE FROM reports WHERE id = ? AND device_id = ?", (report_id, device)).rowcount
        if not deleted:
            raise HTTPException(404)
        conn.execute("DELETE FROM report_votes WHERE report_id = ?", (report_id,))
    return {"ok": True}


@app.post("/v1/reports/{report_id}/scenario")
def create_scenario(report_id: int, device: str = Depends(current_device)):
    """비용을 막기 위해 상위 제보만, 제보당 한 번만, 한 번에 하나씩 생성합니다."""
    with _scenario_lock:
        with db.connect() as conn:
            item = next((r for r in _report_rows(conn, device) if r["id"] == report_id), None)
        if not item:
            raise HTTPException(404)
        if item["scenario"]:
            return item["scenario"]
        if not item["rank"]:
            raise HTTPException(403, "top reports only")
        try:
            with tracing.trace("시나리오 생성", metadata={"report": report_id}):
                scenario = reports.generate(item["title"], item["body"])
        except Exception as exc:
            logging.getLogger("guard.reports").exception("scenario failed")
            raise HTTPException(502, "scenario generation failed") from exc
        with db.connect() as conn:
            conn.execute("UPDATE reports SET scenario = ? WHERE id = ?", (json.dumps(scenario, ensure_ascii=False), report_id))
    return scenario


# ---------- 시연 가족: 웹 시연에서만 씁니다 ----------
@app.get("/v1/demo/family")
def demo_family():
    if not config.DEMO_FAMILY:
        raise HTTPException(404)
    return {"items": [{"id": m[0], "name": m[1], "role": m[2]} for m in db.DEMO_MEMBERS]}


@app.post("/v1/demo/family/{member_id}/login")
def demo_login(member_id: str):
    if not config.DEMO_FAMILY or member_id not in {m[0] for m in db.DEMO_MEMBERS}:
        raise HTTPException(404)
    with db.connect() as conn:
        row = conn.execute("SELECT token, name, role FROM devices WHERE id = ?", (member_id,)).fetchone()
    return {"token": row["token"], "name": row["name"], "role": row["role"]}


@app.get("/v1/devices/me")
def my_profile(device: str = Depends(current_device)):
    with db.connect() as conn:
        row = conn.execute("SELECT name, role, memo FROM devices WHERE id = ?", (device,)).fetchone()
    return dict(row)


@app.put("/v1/devices/me")
def update_profile(body: ProfileIn, device: str = Depends(current_device)):
    with db.connect() as conn:
        conn.execute("UPDATE devices SET role = ?, memo = ? WHERE id = ?", (body.role, body.memo, device))
    return {"ok": True}


# ---------- 가족 연결: 보호받는 사람이 코드를 만들어 직접 건네야 연결됩니다 ----------
@app.post("/v1/family/invite")
def create_invite(device: str = Depends(current_device)):
    code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
    with db.connect() as conn:
        conn.execute("DELETE FROM invites WHERE device_id = ? OR expires_at < ?", (device, db.now()))
        conn.execute("INSERT INTO invites VALUES (?, ?, ?)", (code, device, db.now() + INVITE_TTL))
    return {"code": code, "expires_in": INVITE_TTL}


@app.post("/v1/family/link")
def link_guardian(body: LinkIn, device: str = Depends(current_device)):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT device_id FROM invites WHERE code = ? AND expires_at >= ?", (body.code.strip().upper(), db.now())
        ).fetchone()
        if not row or row["device_id"] == device:
            raise HTTPException(400, "invalid code")
        conn.execute(
            "INSERT OR IGNORE INTO family_links VALUES (?, ?, ?)", (row["device_id"], device, db.now())
        )
        conn.execute("DELETE FROM invites WHERE code = ?", (body.code.strip().upper(),))
        name = conn.execute("SELECT name FROM devices WHERE id = ?", (row["device_id"],)).fetchone()["name"]
    return {"protected_name": name}


@app.get("/v1/family")
def family(device: str = Depends(current_device)):
    with db.connect() as conn:
        guardians = conn.execute(
            "SELECT d.id, d.name, d.role, d.memo FROM family_links f JOIN devices d ON d.id = f.guardian_id WHERE f.protected_id = ?",
            (device,),
        ).fetchall()
        protected = conn.execute(
            "SELECT d.id, d.name, d.role, d.memo, d.lock_until > ? AS locked FROM family_links f JOIN devices d ON d.id = f.protected_id"
            " WHERE f.guardian_id = ?",
            (db.now(), device),
        ).fetchall()
    return {
        "guardians": [dict(r) for r in guardians],
        "protected": [{**dict(r), "locked": bool(r["locked"])} for r in protected],
    }


@app.delete("/v1/family/guardians/{guardian_id}")
def remove_guardian(guardian_id: str, device: str = Depends(current_device)):
    with db.connect() as conn:
        conn.execute("DELETE FROM family_links WHERE protected_id = ? AND guardian_id = ?", (device, guardian_id))
    return {"ok": True}


# ---------- 시연용 예시 통화: 기록, 가족 알림, 잠금에 영향을 주지 않습니다 ----------
_sample_results: dict[str, dict] = {}
_sample_lock = threading.Lock()


def _analyze_sample(sample_id: str) -> dict:
    sample = samples.BY_ID.get(sample_id)
    if not sample:
        raise HTTPException(404)
    # 눌러 볼 때마다 LLM 비용이 나가지 않도록 서버가 켜져 있는 동안 결과를 재사용합니다.
    # 로그인 없는 랜딩에서도 부르므로 동시에 눌러도 샘플당 한 번만 분석합니다.
    with _sample_lock:
        if sample_id not in _sample_results:
            with tracing.trace("예시 통화 분석", metadata={"sample": sample_id}):
                text = samples.transcript(sample)
                result = llm.analyze(text)
                _sample_results[sample_id] = {
                    "status": "done",
                    "label": result["label"],
                    "confidence": result["confidence"],
                    "review_label": None,
                    "evidence": result["evidence"],
                    "matches": pipeline.public_matches(pipeline.find_matches(result, text)),
                    "expected": sample["expected"],
                }
        return _sample_results[sample_id]


@app.get("/v1/samples")
def list_samples(_: str = Depends(current_device)):
    return {"items": samples.SAMPLES}


@app.post("/v1/samples/{sample_id}/analyze")
def analyze_sample(sample_id: str, _: str = Depends(current_device)):
    return _analyze_sample(sample_id)


@app.get("/v1/demo/samples")
def list_demo_samples():
    return {"items": samples.SAMPLES}


@app.post("/v1/demo/samples/{sample_id}/analyze")
def analyze_demo_sample(sample_id: str):
    return _analyze_sample(sample_id)


# ---------- 가족 암구호 ----------
def _emergency(conn, group: list[str]):
    marks = ",".join("?" * len(group))
    return conn.execute(
        f"SELECT e.*, d.name FROM emergency_phrases e JOIN devices d ON d.id = e.device_id"
        f" WHERE e.device_id IN ({marks}) ORDER BY e.updated_at DESC LIMIT 1",
        group,
    ).fetchone()


@app.get("/v1/family/passphrase")
def get_passphrase(device: str = Depends(current_device)):
    today = passphrase.now_kst()
    with db.connect() as conn:
        group = passphrase.members(conn, device)
        if len(group) < 2:
            return {"linked": False}
        emergency = _emergency(conn, group)
        words = passphrase.words(db.passphrase_key(conn), group, today.date().isoformat())
    midnight = today.replace(hour=0, minute=0, second=0, microsecond=0) + passphrase.timedelta(days=1)
    return {
        "linked": True,
        "words": words,
        "seconds_left": int((midnight - today).total_seconds()),
        # 비상 암구호의 답은 해시만 저장하므로 돌려주지 않습니다.
        "emergency": {"question": emergency["question"], "set_by": emergency["name"]} if emergency else None,
    }


@app.put("/v1/family/passphrase/emergency")
def set_emergency(body: EmergencyIn, device: str = Depends(current_device)):
    salt, digest = passphrase.hash_answer(body.answer)
    with db.connect() as conn:
        if len(passphrase.members(conn, device)) < 2:
            raise HTTPException(400, "no family")
        conn.execute(
            "INSERT OR REPLACE INTO emergency_phrases VALUES (?, ?, ?, ?, ?)",
            (device, body.question.strip(), salt, digest, db.now()),
        )
    return {"ok": True}


@app.post("/v1/family/passphrase/emergency/verify")
def verify_emergency(body: AnswerIn, device: str = Depends(current_device)):
    fails = [t for t in _verify_fails.get(device, []) if t > db.now() - VERIFY_WINDOW]
    if len(fails) >= VERIFY_LIMIT:
        raise HTTPException(429, "too many attempts")
    with db.connect() as conn:
        emergency = _emergency(conn, passphrase.members(conn, device))
    if not emergency:
        raise HTTPException(404)
    match = hmac.compare_digest(passphrase.hash_answer(body.answer, emergency["salt"])[1], emergency["hash"])
    _verify_fails[device] = [] if match else [*fails, db.now()]
    return {"match": match}


# ---------- 금융 앱 잠금 ----------
@app.get("/v1/lock")
def lock_state(device: str = Depends(current_device)):
    with db.connect() as conn:
        until = conn.execute("SELECT lock_until FROM devices WHERE id = ?", (device,)).fetchone()["lock_until"]
    # 기기 시계가 틀려도 동작하도록 시각이 아니라 남은 초를 보냅니다.
    remaining = max(0, int(until - db.now()))
    return {"locked": remaining > 0, "remaining": remaining, "apps": LOCK_APPS}


@app.post("/v1/lock")
def lock_now(body: LockIn, device: str = Depends(current_device)):
    with db.connect() as conn:
        db.extend_lock(conn, device, body.minutes * 60)
        db.log_event(conn, device, "lock_manual")
    return lock_state(device)


@app.post("/v1/lock/release")
def request_release(device: str = Depends(current_device)):
    """사기범이 시켜서 푸는 경우에 대비해 본인 해제는 대기 시간을 거칩니다."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE devices SET lock_until = MIN(lock_until, ?) WHERE id = ?",
            (db.now() + config.LOCK_RELEASE_WAIT, device),
        )
        db.log_event(conn, device, "unlock_self")
    return lock_state(device)


@app.post("/v1/family/protected/{protected_id}/unlock")
def guardian_unlock(protected_id: str, device: str = Depends(current_device)):
    with db.connect() as conn:
        link = conn.execute(
            "SELECT 1 FROM family_links WHERE protected_id = ? AND guardian_id = ?", (protected_id, device)
        ).fetchone()
        if not link:
            raise HTTPException(404)
        conn.execute("UPDATE devices SET lock_until = 0 WHERE id = ?", (protected_id,))
        db.log_event(conn, protected_id, "unlock_family")
    return {"ok": True}


# ---------- 녹음 업로드 ----------
@app.post("/v1/recordings")
def create_recording(body: RecordingIn, device: str = Depends(current_device)):
    ext = PurePosixPath(body.filename).suffix.lstrip(".").lower()
    allowed = {
        "text": config.TEXT_EXTENSIONS,
        "openai": config.OPENAI_STT_EXTENSIONS,
    }.get(config.STT, config.AUDIO_EXTENSIONS)
    if ext not in allowed:
        raise HTTPException(415, f"unsupported format: {ext}")

    rec_id, token = uuid.uuid4().hex, secrets.token_urlsafe(24)
    key = f"recordings/{device}/{rec_id}.{ext}"
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT id, status FROM recordings WHERE device_id = ? AND client_key = ?", (device, body.client_key)
        ).fetchone()
        if existing and existing["status"] != "pending_upload":
            return {"id": existing["id"], "upload_url": None, "already_uploaded": True}
        if existing:
            conn.execute("DELETE FROM recordings WHERE id = ?", (existing["id"],))
        conn.execute(
            "INSERT INTO recordings (id, device_id, client_key, filename, s3_key, upload_token, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending_upload', ?)",
            (rec_id, device, body.client_key, body.filename, key, token, db.now()),
        )
    return {
        "id": rec_id,
        "upload_url": providers.upload_url(key, body.content_type, token, rec_id, body.direct),
        "already_uploaded": False,
    }


@app.put("/v1/local-upload/{rec_id}")
async def local_upload(rec_id: str, request: Request, token: str = Query()):
    with db.connect() as conn:
        row = conn.execute("SELECT s3_key, upload_token FROM recordings WHERE id = ?", (rec_id,)).fetchone()
    if not row or not hmac.compare_digest(row["upload_token"], token):
        raise HTTPException(403)
    path, size = providers.local_path(row["s3_key"]), 0
    with path.open("wb") as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413)
            out.write(chunk)
    await run_in_threadpool(providers.store_uploaded, row["s3_key"])
    return {"size": size}


@app.post("/v1/recordings/{rec_id}/complete")
def complete(rec_id: str, tasks: BackgroundTasks, device: str = Depends(current_device)):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ? AND device_id = ?", (rec_id, device)).fetchone()
        if not row:
            raise HTTPException(404)
        if row["status"] not in ("pending_upload", "failed"):
            return {"status": row["status"]}
        size = providers.uploaded_size(row["s3_key"])
        if size is None:
            raise HTTPException(409, "upload not found")
        if size > config.MAX_UPLOAD_BYTES:
            providers.delete_audio(row["s3_key"])
            raise HTTPException(413)
        conn.execute("UPDATE recordings SET status = 'queued' WHERE id = ?", (rec_id,))
    tasks.add_task(pipeline.process, rec_id)
    return {"status": "queued"}


@app.get("/v1/recordings")
def list_recordings(device: str = Depends(current_device)):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE device_id = ? AND status != 'pending_upload' ORDER BY created_at DESC LIMIT 100",
            (device,),
        ).fetchall()
    return {"items": [db.public_recording(r) for r in rows]}


@app.delete("/v1/recordings/{rec_id}")
def delete_recording(rec_id: str, device: str = Depends(current_device)):
    with db.connect() as conn:
        row = conn.execute("SELECT s3_key FROM recordings WHERE id = ? AND device_id = ?", (rec_id, device)).fetchone()
        if not row:
            raise HTTPException(404)
        conn.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
        conn.execute("DELETE FROM alerts WHERE recording_id = ?", (rec_id,))
        conn.execute("DELETE FROM recording_feedback WHERE recording_id = ?", (rec_id,))
        conn.execute("DELETE FROM review_dataset WHERE recording_id = ?", (rec_id,))
    providers.delete_audio(row["s3_key"])
    return {"ok": True}


@app.get("/v1/recommendations")
def recommendations(device: str = Depends(current_device)):
    return pipeline.recommendations(device)


# ---------- 가족 알림 ----------
@app.get("/v1/alerts")
def alerts(after: int = 0, device: str = Depends(current_device)):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, body, acked, created_at FROM alerts WHERE guardian_id = ? AND id > ? ORDER BY id DESC LIMIT 50",
            (device, after),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/v1/alerts/{alert_id}/ack")
def ack(alert_id: int, device: str = Depends(current_device)):
    with db.connect() as conn:
        if conn.execute("UPDATE alerts SET acked = 1 WHERE id = ? AND guardian_id = ? AND acked = 0", (alert_id, device)).rowcount:
            db.log_event(conn, device, "alert_ack")
    return {"ok": True}


# ---------- 사람 검토: 보이스피싱 외 사기는 별도 데이터셋으로 ----------
@app.post("/v1/recordings/{rec_id}/review")
def review(rec_id: str, body: ReviewIn, device: str = Depends(current_device)):
    if body.scam_type is not None and body.scam_type not in BY_ID:
        raise HTTPException(400, "unknown scam_type")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ? AND device_id = ?", (rec_id, device)).fetchone()
        if not row:
            raise HTTPException(404)
        if row["status"] != "done":
            raise HTTPException(409, "not analyzed")
        scam_type = body.scam_type or row["scam_type"]
        # 사람이 확인한 라벨입니다. 글자 기록은 넣지 않아 정상 통화 내용 없이도 오탐률을 잴 수 있습니다.
        conn.execute(
            "INSERT OR REPLACE INTO recording_feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rec_id, device, row["label"], row["confidence"], body.label, body.reason, "none" if body.label == "normal" else scam_type, db.now()),
        )
        if body.label == "normal":
            # 사람이 정상으로 확인하면 원문을 지우고 데이터셋에서도 뺍니다.
            conn.execute(
                "UPDATE recordings SET review_label = ?, scam_type = 'none', transcript = NULL WHERE id = ?",
                (body.label, rec_id),
            )
            conn.execute("DELETE FROM review_dataset WHERE recording_id = ?", (rec_id,))
            return {"ok": True, "in_dataset": False}
        conn.execute(
            "UPDATE recordings SET review_label = ?, scam_type = ? WHERE id = ?", (body.label, scam_type, rec_id)
        )
        in_dataset = body.label == OTHER_SCAM and bool(row["transcript"])
        if in_dataset:
            conn.execute(
                "INSERT OR REPLACE INTO review_dataset VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rec_id, row["transcript"], body.label, scam_type, row["label"], body.note, db.now()),
            )
        else:
            conn.execute("DELETE FROM review_dataset WHERE recording_id = ?", (rec_id,))
    return {"ok": True, "in_dataset": in_dataset}


# ---------- 대시보드: 사용자는 자기 기록만, 관리자는 개인을 알 수 없는 집계만 봅니다 ----------
@app.post("/v1/training")
def save_training(body: TrainingIn, device: str = Depends(current_device)):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO training_results (device_id, scenario, tag, score, created_at) VALUES (?, ?, ?, ?, ?)",
            (device, body.scenario, body.tag, body.score, db.now()),
        )
    return {"ok": True}


@app.get("/v1/dashboard/me")
def my_dashboard(device: str = Depends(current_device)):
    with db.connect() as conn:
        return dashboard.user(conn, device)


@app.get("/v1/admin/dashboard")
def admin_dashboard(include_demo: bool = True):
    with db.connect() as conn:
        return dashboard.admin(conn, include_demo)


@app.get("/v1/admin/ops")
def admin_ops(hours: int = 168, include_demo: bool = True):
    if hours not in dashboard.RANGES:
        raise HTTPException(400, "unknown range")
    with db.connect() as conn:
        return dashboard.ops(conn, hours, include_demo, db.now())


@app.get("/v1/admin/feedback-dataset.jsonl", response_class=PlainTextResponse)
def export_feedback():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT model_label, model_confidence, human_label, reason, scam_type, created_at FROM recording_feedback ORDER BY created_at"
        ).fetchall()
    return "\n".join(json.dumps(dict(r), ensure_ascii=False) for r in rows)


@app.get("/v1/admin/review-dataset.jsonl", response_class=PlainTextResponse)
def export_dataset(x_admin_token: str = Header(default="")):
    if not config.DATASET_TOKEN or not hmac.compare_digest(config.DATASET_TOKEN, x_admin_token):
        raise HTTPException(403)
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM review_dataset ORDER BY created_at").fetchall()
    return "\n".join(json.dumps(dict(r), ensure_ascii=False) for r in rows)
