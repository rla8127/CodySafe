import json
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
CREATE TABLE IF NOT EXISTS review_dataset (
  recording_id TEXT PRIMARY KEY, transcript TEXT NOT NULL, label TEXT NOT NULL, scam_type TEXT,
  model_label TEXT, note TEXT, created_at REAL NOT NULL
);
"""


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


def now() -> float:
    return time.time()


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
