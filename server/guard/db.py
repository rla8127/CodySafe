import json
import random
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
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, scenario TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS report_votes (
  report_id INTEGER NOT NULL, device_id TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (report_id, device_id)
);
CREATE TABLE IF NOT EXISTS recording_feedback (
  recording_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, model_label TEXT, model_confidence REAL,
  human_label TEXT NOT NULL, reason TEXT, scam_type TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS training_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, scenario TEXT NOT NULL, tag TEXT NOT NULL,
  score INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS response_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS review_dataset (
  recording_id TEXT PRIMARY KEY, transcript TEXT NOT NULL, label TEXT NOT NULL, scam_type TEXT,
  model_label TEXT, note TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sim_sessions (
  id TEXT PRIMARY KEY, device_id TEXT NOT NULL, scenario_id TEXT NOT NULL, scam_type TEXT NOT NULL, mode TEXT NOT NULL,
  started_at REAL NOT NULL, finished_at REAL, total INTEGER, breakdown_json TEXT, state_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sim_sessions_device ON sim_sessions (device_id, finished_at);
CREATE TABLE IF NOT EXISTS sim_turns (
  session_id TEXT NOT NULL, seq INTEGER NOT NULL, node_id TEXT NOT NULL, input_type TEXT NOT NULL, input_text TEXT,
  grade TEXT NOT NULL, intent TEXT NOT NULL, source TEXT NOT NULL, latency_ms INTEGER, stt_ms INTEGER,
  created_at REAL NOT NULL, PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS weakness (
  device_id TEXT NOT NULL, scam_type TEXT NOT NULL, value REAL NOT NULL, updated_at REAL NOT NULL,
  PRIMARY KEY (device_id, scam_type)
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
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(devices)")}
        for column in ("role", "memo", "sim_profile"):  # sim_profile: 모의 훈련 프로필(JSON)
            if column not in columns:
                conn.execute(f"ALTER TABLE devices ADD COLUMN {column} TEXT")
        # 이전 버전 알림에 저장된 요약과 사기 유형을 지웁니다.
        conn.execute(
            "UPDATE alerts SET body = ?, title = (SELECT name FROM devices WHERE id = alerts.protected_id) || '님 보이스피싱 의심 통화'"
            " WHERE body != ?",
            (FAMILY_ALERT_BODY, FAMILY_ALERT_BODY),
        )


DEMO_MEMBERS = [
    ("demo-me", "동현", "me"),
    ("demo-dad", "상우", "dad"),
    ("demo-mom", "선형", "mom"),
    ("demo-brother", "호연", "brother"),
    ("demo-uncle", "병국", "uncle"),
]


DEMO_REPORTS = [
    ("demo-brother", "전화", "아들 목소리로 합의금을 요구하는 전화", "아들 목소리와 비슷한 사람이 사고가 났다며 합의금을 바로 보내라고 했습니다. 끊지 말라고 재촉했어요.", 5),
    ("demo-mom", "문자", "건강검진 결과 확인하라는 문자", "건강검진 결과를 확인하라는 문자의 링크를 누르면 앱을 설치하라고 나왔습니다.", 4),
    ("demo-uncle", "메신저", "회사 대표를 사칭한 급한 송금 요청", "대표님 프로필 사진으로 메시지가 와서 거래처에 급히 송금하라고 했습니다.", 3),
    ("demo-dad", "투자", "공모주 무료 배정 단체방 초대", "무료 공모주를 준다며 단체방에 초대하고 전용 앱 설치를 권했습니다.", 2),
]


def seed_demo_analytics() -> None:
    """관제 화면 시연용 가상 기록입니다. 켤 때마다 지금 시각 기준으로 다시 만들며, 실제 통계가 아닙니다."""
    rng = random.Random(7)
    weights = [
        ("prosecutor_impersonation", 34), ("family_impersonation", 18), ("loan_refinance", 22),
        ("bank_security", 12), ("government_benefit", 8), ("investment_rebate", 6),
    ]
    callers = [f"0100000{n:04d}" for n in (1001, 1002, 1003, 2044, 3120, 3121, 4555, 5310)]
    start = now()
    devices = [f"demo-seed-{n}" for n in range(14)]
    with connect() as conn:
        for table in ("recordings", "recording_feedback", "training_results", "response_events"):
            conn.execute(f"DELETE FROM {table} WHERE device_id LIKE 'demo-seed-%'")
        for device in devices:
            conn.execute(
                "INSERT OR IGNORE INTO devices (id, token, name, created_at) VALUES (?, ?, '시연 집계용', ?)",
                (device, secrets.token_urlsafe(32), start),
            )
        for i in range(420):
            # 평일 낮에 몰리게 만들고, 최근 12시간에는 가족 사칭이 늘어나게 합니다.
            when = start - rng.random() * 30 * 86400
            local = time.gmtime(when + 9 * 3600)
            if (local.tm_hour < 9 or local.tm_hour > 18 or local.tm_wday > 4) and rng.random() < 0.7:
                when = start - rng.random() * 30 * 86400
            scam_type = rng.choices([w[0] for w in weights], [w[1] for w in weights])[0]
            label = "voice_phishing" if scam_type != "investment_rebate" else "other_scam"
            device = rng.choice(devices)
            if rng.random() < 0.45:
                label, scam_type = "normal", "none"
            filename = f"통화 {rng.choice(callers) if label == 'voice_phishing' and rng.random() < 0.75 else '지인'}_260101_120000.m4a"
            rec_id = f"demo-seed-rec-{i}"
            add_demo_recording(conn, rec_id, device, filename, label, scam_type, when)
            if rng.random() < 0.3 and label != "normal":
                human = "normal" if rng.random() < 0.12 else label
                conn.execute(
                    "INSERT INTO recording_feedback VALUES (?, ?, ?, ?, ?, '시연', ?, ?)",
                    (rec_id, device, label, 0.9, human, scam_type, when + 600),
                )
            if label == "voice_phishing":
                conn.execute("INSERT INTO response_events (device_id, kind, created_at) VALUES (?, 'family_alert', ?)", (device, when))
                if rng.random() < 0.72:
                    conn.execute("INSERT INTO response_events (device_id, kind, created_at) VALUES (?, 'alert_ack', ?)", (device, when + 300))
                if rng.random() < 0.55:
                    conn.execute("INSERT INTO response_events (device_id, kind, created_at) VALUES (?, 'lock_auto', ?)", (device, when))
                    if rng.random() < 0.6:
                        conn.execute("INSERT INTO response_events (device_id, kind, created_at) VALUES (?, 'unlock_family', ?)", (device, when + 1800))
        for i in range(16):
            when = start - rng.random() * 12 * 3600
            add_demo_recording(conn, f"demo-seed-surge-{i}", rng.choice(devices), f"통화 {callers[0]}_260101_120000.m4a", "voice_phishing", "family_impersonation", when)


def add_demo_recording(conn: sqlite3.Connection, rec_id: str, device: str, filename: str, label: str, scam_type: str, when: float) -> None:
    conn.execute(
        "INSERT INTO recordings (id, device_id, client_key, filename, s3_key, upload_token, status, label, confidence, scam_type, created_at)"
        " VALUES (?, ?, ?, ?, '', '', 'done', ?, 0.9, ?, ?)",
        (rec_id, device, rec_id, filename, label, scam_type, when),
    )


def seed_demo_family() -> None:
    """모든 구성원이 서로의 경고를 받도록 양방향으로 연결합니다."""
    with connect() as conn:
        for device_id, name, role in DEMO_MEMBERS:
            conn.execute(
                "INSERT OR IGNORE INTO devices (id, token, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, secrets.token_urlsafe(32), name, role, now()),
            )
        ids = [m[0] for m in DEMO_MEMBERS]
        for protected in ids:
            for guardian in ids:
                if protected != guardian:
                    conn.execute("INSERT OR IGNORE INTO family_links VALUES (?, ?, ?)", (protected, guardian, now()))
        if not conn.execute("SELECT 1 FROM reports WHERE is_demo = 1").fetchone():
            for author, category, title, body, votes in DEMO_REPORTS:
                report_id = conn.execute(
                    "INSERT INTO reports (device_id, category, title, body, is_demo, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                    (author, category, title, body, now()),
                ).lastrowid
                for voter in ids[:votes]:
                    conn.execute("INSERT INTO report_votes VALUES (?, ?, ?)", (report_id, voter, now()))


def now() -> float:
    return time.time()


def log_event(conn: sqlite3.Connection, device_id: str, kind: str) -> None:
    conn.execute("INSERT INTO response_events (device_id, kind, created_at) VALUES (?, ?, ?)", (device_id, kind, now()))


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
