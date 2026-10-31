import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, name TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS invites (
  code TEXT PRIMARY KEY, device_id TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS family_links (
  protected_id TEXT NOT NULL, guardian_id TEXT NOT NULL, created_at REAL NOT NULL,
  PRIMARY KEY (protected_id, guardian_id)
);
CREATE TABLE IF NOT EXISTS recordings (
  id TEXT PRIMARY KEY, device_id TEXT NOT NULL, client_key TEXT NOT NULL, filename TEXT NOT NULL,
  s3_key TEXT NOT NULL, upload_token TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
  transcript TEXT, label TEXT, confidence REAL, scam_type TEXT, summary TEXT,
  evidence TEXT, matches TEXT, needs_review INTEGER NOT NULL DEFAULT 0,
  review_label TEXT, created_at REAL NOT NULL,
  UNIQUE (device_id, client_key)
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, guardian_id TEXT NOT NULL, protected_id TEXT NOT NULL,
  recording_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  acked INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS emergency_phrases (
  device_id TEXT PRIMARY KEY, question TEXT NOT NULL, salt BLOB NOT NULL, hash BLOB NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS review_dataset (
  recording_id TEXT PRIMARY KEY, transcript TEXT NOT NULL, label TEXT NOT NULL, scam_type TEXT,
  model_label TEXT, note TEXT, created_at REAL NOT NULL
);
"""


FAMILY_ALERT_BODY = "통화 내용은 공유되지 않습니다. 본인에게 직접 연락해 확인해 주세요."


@contextmanager
def connect():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        if "lock_until" not in {r["name"] for r in conn.execute("PRAGMA table_info(devices)")}:
            conn.execute("ALTER TABLE devices ADD COLUMN lock_until REAL NOT NULL DEFAULT 0")
        # 이전 버전 알림에 저장된 요약과 사기 유형을 지웁니다.
        conn.execute(
            "UPDATE alerts SET body = ?, title = (SELECT name FROM devices WHERE id = alerts.protected_id) || '님 보이스피싱 의심 통화'"
            " WHERE body != ?",
            (FAMILY_ALERT_BODY, FAMILY_ALERT_BODY),
        )


def now() -> float:
    return time.time()


def passphrase_key(conn: sqlite3.Connection) -> bytes:
    conn.execute("INSERT OR IGNORE INTO meta VALUES ('passphrase_key', ?)", (secrets.token_bytes(32),))
    return conn.execute("SELECT value FROM meta WHERE key = 'passphrase_key'").fetchone()["value"]


def extend_lock(conn: sqlite3.Connection, device_id: str, seconds: float) -> None:
    conn.execute("UPDATE devices SET lock_until = MAX(lock_until, ?) WHERE id = ?", (now() + seconds, device_id))


def public_recording(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "status": row["status"],
        "error": row["error"],
        "label": row["label"],
        "confidence": row["confidence"],
        "scam_type": row["scam_type"],
        "summary": row["summary"],
        "evidence": json.loads(row["evidence"] or "[]"),
        "matches": json.loads(row["matches"] or "[]"),
        "needs_review": bool(row["needs_review"]) and row["review_label"] is None,
        "review_label": row["review_label"],
        "created_at": row["created_at"],
    }
