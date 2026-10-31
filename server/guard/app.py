import hmac
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import PurePosixPath

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, passphrase, pipeline, providers
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
    config.LOCAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    yield


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


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)


class LinkIn(BaseModel):
    code: str


class RecordingIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    client_key: str = Field(min_length=1, max_length=255)
    content_type: str = "application/octet-stream"


class LockIn(BaseModel):
    minutes: int = Field(ge=1, le=60)


class EmergencyIn(BaseModel):
    question: str = Field(min_length=2, max_length=60)
    answer: str = Field(min_length=2, max_length=60)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=60)


class ReviewIn(BaseModel):
    label: str = Field(pattern="^(voice_phishing|other_scam|normal)$")
    scam_type: str | None = None
    note: str = Field(default="", max_length=500)


@app.get("/healthz")
def healthz():
    return {"ok": True, "storage": config.STORAGE, "stt": config.STT, "llm": config.LLM, "embed": config.EMBED}


@app.post("/v1/devices")
def register(body: DeviceIn):
    device_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO devices (id, token, name, created_at) VALUES (?, ?, ?, ?)",
            (device_id, token, body.name, db.now()),
        )
    return {"device_id": device_id, "token": token}


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
            "SELECT d.id, d.name FROM family_links f JOIN devices d ON d.id = f.guardian_id WHERE f.protected_id = ?",
            (device,),
        ).fetchall()
        protected = conn.execute(
            "SELECT d.id, d.name, d.lock_until > ? AS locked FROM family_links f JOIN devices d ON d.id = f.protected_id"
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
    return lock_state(device)


@app.post("/v1/lock/release")
def request_release(device: str = Depends(current_device)):
    """사기범이 시켜서 푸는 경우에 대비해 본인 해제는 대기 시간을 거칩니다."""
    with db.connect() as conn:
        conn.execute(
            "UPDATE devices SET lock_until = MIN(lock_until, ?) WHERE id = ?",
            (db.now() + config.LOCK_RELEASE_WAIT, device),
        )
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
        "upload_url": providers.upload_url(key, body.content_type, token, rec_id),
        "already_uploaded": False,
    }


@app.put("/v1/local-upload/{rec_id}")
async def local_upload(rec_id: str, request: Request, token: str = Query()):
    if config.STORAGE != "local":
        raise HTTPException(404)
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
        conn.execute("UPDATE alerts SET acked = 1 WHERE id = ? AND guardian_id = ?", (alert_id, device))
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


@app.get("/v1/admin/review-dataset.jsonl", response_class=PlainTextResponse)
def export_dataset(x_admin_token: str = Header(default="")):
    if not config.ADMIN_TOKEN or not hmac.compare_digest(config.ADMIN_TOKEN, x_admin_token):
        raise HTTPException(403)
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM review_dataset ORDER BY created_at").fetchall()
    return "\n".join(json.dumps(dict(r), ensure_ascii=False) for r in rows)
