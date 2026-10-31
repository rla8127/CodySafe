"""업로드 완료 후 처리: STT → LLM 분석 → (사기면) RAG → 가족 알림·검토 대기열."""
import json
import logging

from . import config, db, llm, providers, rag
from .scam_kb import BY_ID, OTHER_SCAM, VOICE_PHISHING

log = logging.getLogger("guard.pipeline")


def _set(rec_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db.connect() as conn:
        conn.execute(f"UPDATE recordings SET {cols} WHERE id = ?", (*fields.values(), rec_id))


def _notify_family(rec_id: str, protected_id: str) -> None:
    with db.connect() as conn:
        name = conn.execute("SELECT name FROM devices WHERE id = ?", (protected_id,)).fetchone()["name"]
        guardians = conn.execute("SELECT guardian_id FROM family_links WHERE protected_id = ?", (protected_id,)).fetchall()
        if guardians:
            db.log_event(conn, protected_id, "family_alert")
        for g in guardians:
            # 가족에게는 의심 여부만 전달합니다. 요약, 유형, 녹취, 파일명은 보내지 않습니다.
            conn.execute(
                "INSERT INTO alerts (guardian_id, protected_id, recording_id, title, body, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (g["guardian_id"], protected_id, rec_id, f"{name}님 보이스피싱 의심 통화", db.FAMILY_ALERT_BODY, db.now()),
            )


def _finish_audio(key: str) -> None:
    if not config.KEEP_AUDIO:
        providers.delete_audio(key)


def find_matches(result: dict, transcript: str) -> list[dict]:
    if result["label"] == VOICE_PHISHING:
        return rag.retrieve(f"{result['summary']}\n{transcript}")
    return [BY_ID[result["scam_type"]]] if result["scam_type"] in BY_ID else []


def public_matches(matches: list[dict]) -> list[dict]:
    return [{"id": m["id"], "name": m["name"], "advice": m["advice"]} for m in matches]


def process(rec_id: str) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ?", (rec_id,)).fetchone()
    try:
        _set(rec_id, status="transcribing", error=None)
        transcript = providers.transcribe(rec_id, row["s3_key"])
        if not transcript:
            _set(rec_id, status="done", label="uncertain", confidence=0.0, scam_type="none", summary="음성에서 말을 찾지 못했습니다.")
            _finish_audio(row["s3_key"])
            return

        _set(rec_id, status="analyzing")
        result = llm.analyze(transcript)
        label, confidence = result["label"], result["confidence"]
        is_scam = label in (VOICE_PHISHING, OTHER_SCAM)

        matches = find_matches(result, transcript)

        alert = label == VOICE_PHISHING and confidence >= config.ALERT_THRESHOLD
        needs_review = label in (OTHER_SCAM, "uncertain") or (label == VOICE_PHISHING and not alert)
        _set(
            rec_id,
            status="done",
            label=label,
            confidence=confidence,
            scam_type=result["scam_type"],
            summary=result["summary"],
            evidence=json.dumps(result["evidence"] if is_scam or needs_review else [], ensure_ascii=False),
            matches=json.dumps(public_matches(matches), ensure_ascii=False),
            needs_review=int(needs_review),
            # 일상 통화 원문은 보관하지 않습니다. 검토와 재학습에 필요한 건만 남깁니다.
            transcript=transcript if is_scam or needs_review else None,
        )
        if alert:
            _notify_family(rec_id, row["device_id"])
        if label == VOICE_PHISHING and confidence >= config.LOCK_THRESHOLD:
            with db.connect() as conn:
                db.extend_lock(conn, row["device_id"], config.LOCK_SECONDS)
                db.log_event(conn, row["device_id"], "lock_auto")
        # 분석이 끝난 뒤에 지워야 LLM 실패 시 다시 시도할 수 있습니다.
        _finish_audio(row["s3_key"])
    except Exception as exc:
        log.exception("recording %s failed", rec_id)
        _set(rec_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:500])


def recommendations(device_id: str) -> dict:
    """본인 기록에서 자주 나온 유형을 먼저, 사람이 고친 라벨을 우선해 추천합니다."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT scam_type, label, review_label FROM recordings WHERE device_id = ? AND status = 'done'", (device_id,)
        ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        final = r["review_label"] or r["label"]
        if final in (VOICE_PHISHING, OTHER_SCAM) and r["scam_type"] in BY_ID:
            counts[r["scam_type"]] = counts.get(r["scam_type"], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    return {
        "analyzed": len(rows),
        "items": [
            {
                "id": i,
                "name": BY_ID[i]["name"],
                "count": n,
                "advice": BY_ID[i]["advice"],
                "training": BY_ID[i]["training"],
            }
            for i, n in ranked
        ],
    }
