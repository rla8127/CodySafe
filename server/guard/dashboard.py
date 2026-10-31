"""사용자 본인의 대시보드 집계입니다."""
import sqlite3

from . import db



def user(conn: sqlite3.Connection, device: str) -> dict:
    results = conn.execute("SELECT scenario, tag, score FROM training_results WHERE device_id = ? ORDER BY id", (device,)).fetchall()
    # 시나리오마다 가장 최근 점수로 약점을 봅니다. 다시 풀어 나아지면 추천에서 내려갑니다.
    latest = {r["scenario"]: r for r in results}
    weak = sorted((r for r in latest.values() if r["score"] < 100), key=lambda r: r["score"])[:3]
    calls = conn.execute(
        "SELECT COUNT(*) AS total, SUM(COALESCE(review_label, label) IN ('voice_phishing', 'other_scam')) AS flagged FROM recordings"
        " WHERE device_id = ? AND status = 'done' AND client_key NOT LIKE ?",
        (device, f"{db.SAMPLE_KEY_PREFIX}%"),
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
