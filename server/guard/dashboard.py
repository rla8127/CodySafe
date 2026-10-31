"""사용자와 관리자 대시보드 집계. 관리자 쪽에는 이름, 기기 ID, 통화 내용을 넣지 않습니다."""
import sqlite3

SCAM_LABELS = ("voice_phishing", "other_scam")
SMALL_SAMPLE = 30


def user(conn: sqlite3.Connection, device: str) -> dict:
    results = conn.execute("SELECT scenario, tag, score FROM training_results WHERE device_id = ? ORDER BY id", (device,)).fetchall()
    # 시나리오마다 가장 최근 점수로 약점을 봅니다. 다시 풀어 나아지면 추천에서 내려갑니다.
    latest = {r["scenario"]: r for r in results}
    weak = sorted((r for r in latest.values() if r["score"] < 100), key=lambda r: r["score"])[:3]
    calls = conn.execute(
        "SELECT COUNT(*) AS total, SUM(COALESCE(review_label, label) IN ('voice_phishing', 'other_scam')) AS flagged FROM recordings"
        " WHERE device_id = ? AND status = 'done'",
        (device,),
    ).fetchone()
    confirmed = conn.execute("SELECT COUNT(*) FROM recording_feedback WHERE device_id = ?", (device,)).fetchone()[0]
    return {
        "training": {
            "count": len(results),
            "average": round(sum(r["score"] for r in results) / len(results)) if results else None,
            "scenarios": len(latest),
            "weak": [{"scenario": r["scenario"], "tag": r["tag"], "score": r["score"]} for r in weak],
        },
        "calls": {"total": calls["total"], "flagged": calls["flagged"] or 0, "confirmed": confirmed},
    }


def _scope(include_demo: bool, column: str = "device_id") -> str:
    return "" if include_demo else f" AND {column} NOT LIKE 'demo-%'"


def admin(conn: sqlite3.Connection, include_demo: bool) -> dict:
    scope = _scope(include_demo)
    labels = {r["label"] or "none": r["n"] for r in conn.execute(f"SELECT label, COUNT(*) AS n FROM recordings WHERE status = 'done'{scope} GROUP BY label")}
    rows = conn.execute(f"SELECT model_label, human_label FROM recording_feedback WHERE 1 = 1{scope}").fetchall()
    confirmed = len(rows)
    agree = sum(r["model_label"] == r["human_label"] for r in rows)
    # 보이스피싱으로 판정해 가족 알림까지 갈 수 있는 건 중 사람이 아니라고 한 비율입니다.
    flagged = [r for r in rows if r["model_label"] == "voice_phishing"]
    false_alarm = sum(r["human_label"] != "voice_phishing" for r in flagged)
    actual = [r for r in rows if r["human_label"] == "voice_phishing"]
    missed = sum(r["model_label"] != "voice_phishing" for r in actual)
    ratio = lambda part, whole: round(part / whole * 100, 1) if whole else None
    types = conn.execute(
        f"SELECT scam_type, COUNT(*) AS n FROM recording_feedback WHERE human_label IN {SCAM_LABELS}{scope} GROUP BY scam_type ORDER BY n DESC LIMIT 8"
    ).fetchall()
    training = conn.execute(
        f"SELECT tag, COUNT(*) AS n, ROUND(AVG(score)) AS average FROM training_results WHERE 1 = 1{scope} GROUP BY tag ORDER BY average ASC"
    ).fetchall()
    events = conn.execute(f"SELECT kind, COUNT(*) AS n FROM response_events WHERE 1 = 1{scope} GROUP BY kind").fetchall()
    return {
        "include_demo": include_demo,
        "calls": {"total": sum(labels.values()), "by_label": labels},
        "feedback": {
            "confirmed": confirmed,
            "agreement": ratio(agree, confirmed),
            "false_alarm_rate": ratio(false_alarm, len(flagged)),
            "false_alarm_n": [false_alarm, len(flagged)],
            "miss_rate": ratio(missed, len(actual)),
            "miss_n": [missed, len(actual)],
            "small_sample": confirmed < SMALL_SAMPLE,
        },
        "scam_types": [{"type": r["scam_type"] or "unknown", "n": r["n"]} for r in types],
        "training": [dict(r) for r in training],
        "events": {r["kind"]: r["n"] for r in events},
    }
