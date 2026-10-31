"""사용자와 관리자 대시보드 집계. 관리자 쪽에는 이름, 기기 ID, 통화 내용을 넣지 않습니다."""
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

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


# ---------- 관제 화면: 시간대별 급증, 반복 발신 번호, 오탐 추이 ----------
KST = timezone(timedelta(hours=9))
RANGES = {24: 3600, 168: 6 * 3600, 720: 86400}  # 조회 범위(시간): 묶음 크기(초)
TOP_TYPES = 5
_NUMBER = re.compile(r"(?<!\d)(0\d{1,2})[- ]?(\d{3,4})[- ]?(\d{4})(?!\d)")


def _number(filename: str) -> str | None:
    """삼성 녹음 파일명의 날짜와 겹치지 않도록 전화번호 꼴만 찾습니다."""
    match = _NUMBER.search(filename.rsplit(".", 1)[0])
    return "".join(match.groups()) if match else None


def _mask(number: str) -> str:
    # 관리자 화면에도 전체 번호를 보내지 않습니다.
    return f"{number[:3]}-****-{number[-4:]}"


def ops(conn: sqlite3.Connection, hours: int, include_demo: bool, now: float) -> dict:
    step = RANGES[hours]
    start = (now - hours * 3600) // step * step
    scope = _scope(include_demo)
    calls = conn.execute(
        "SELECT device_id, filename, scam_type, created_at, COALESCE(review_label, label) AS final FROM recordings"
        f" WHERE status = 'done' AND created_at >= ?{scope}",
        (start - hours * 3600,),
    ).fetchall()
    current = [c for c in calls if c["created_at"] >= start]
    previous = [c for c in calls if c["created_at"] < start]
    is_scam = lambda c: c["final"] in SCAM_LABELS
    phishing = [c for c in current if c["final"] == "voice_phishing"]

    # 유형별 시계열. 많은 순서로 5개, 나머지는 기타로 묶습니다.
    counts = Counter(c["scam_type"] or "unknown" for c in current if is_scam(c))
    top = [t for t, _ in counts.most_common(TOP_TYPES)]
    buckets = list(range(int(start), int(now) + 1, step))
    series = {t: [0] * len(buckets) for t in top + ["other"]}
    for c in filter(is_scam, current):
        key = c["scam_type"] if c["scam_type"] in top else "other"
        series[key][min(int((c["created_at"] - start) // step), len(buckets) - 1)] += 1
    if not any(series["other"]):
        del series["other"]

    # 급증: 최근 구간을 그 앞 구간 평균과 비교합니다.
    window = max(hours * 3600 // 8, 3 * 3600)
    surges = []
    for scam_type in counts:
        recent = sum(1 for c in current if is_scam(c) and c["scam_type"] == scam_type and c["created_at"] >= now - window)
        earlier = sum(1 for c in current if is_scam(c) and c["scam_type"] == scam_type and c["created_at"] < now - window)
        baseline = earlier / max((now - window - start) / window, 1)
        if recent >= 3 and recent >= baseline * 2:
            surges.append({"type": scam_type, "recent": recent, "baseline": round(baseline, 1), "ratio": round(recent / baseline, 1) if baseline else None})
    surges.sort(key=lambda s: -(s["ratio"] or 1e9))

    # 반복 발신 번호: 보이스피싱으로 남은 통화만 집계합니다. 가족이나 지인의 일상 통화 번호는 넣지 않습니다.
    numbers: dict[str, list] = {}
    no_number = 0
    for c in phishing:
        number = _number(c["filename"])
        if number:
            numbers.setdefault(number, []).append(c)
        else:
            no_number += 1
    ranked = sorted(numbers.items(), key=lambda kv: (-len(kv[1]), -max(c["created_at"] for c in kv[1])))[:10]
    callers = [
        {
            "number": _mask(number),
            "calls": len(rows),
            "devices": len({c["device_id"] for c in rows}),
            "last": max(c["created_at"] for c in rows),
            "type": Counter(c["scam_type"] for c in rows).most_common(1)[0][0],
        }
        for number, rows in ranked
    ]

    # 요일과 시간대: 사기 통화가 몰리는 때를 봅니다.
    heatmap = [[0] * 24 for _ in range(7)]
    for c in filter(is_scam, current):
        moment = datetime.fromtimestamp(c["created_at"], KST)
        heatmap[moment.weekday()][moment.hour] += 1

    # 오탐률 추이. 사람이 확인한 건만 씁니다.
    day = 86400 if hours > 24 else 6 * 3600
    trend: dict[int, list[int]] = {}
    for f in conn.execute(
        f"SELECT model_label, human_label, created_at FROM recording_feedback WHERE created_at >= ? AND model_label = 'voice_phishing'{scope}",
        (start,),
    ):
        slot = int(f["created_at"] // day * day)
        trend.setdefault(slot, [0, 0])
        trend[slot][1] += 1
        trend[slot][0] += f["human_label"] != "voice_phishing"

    events = Counter(
        r["kind"] for r in conn.execute(f"SELECT kind FROM response_events WHERE created_at >= ?{scope}", (start,))
    )
    return {
        "hours": hours,
        "step": step,
        "now": now,
        "buckets": buckets,
        "series": series,
        "totals": {
            "calls": len(current),
            "calls_before": len(previous),
            "phishing": len(phishing),
            "phishing_before": sum(1 for c in previous if c["final"] == "voice_phishing"),
            "scam_share": round(sum(map(is_scam, current)) / len(current) * 100, 1) if current else None,
        },
        "surges": surges,
        "callers": callers,
        "callers_no_number": no_number,
        "heatmap": heatmap,
        "false_alarm": [{"at": k, "wrong": v[0], "total": v[1]} for k, v in sorted(trend.items())],
        "funnel": [
            ["보이스피싱 의심", len(phishing)],
            ["가족 경고 발송", events["family_alert"]],
            ["가족이 경고 확인", events["alert_ack"]],
            ["금융 앱 자동 잠금", events["lock_auto"]],
            ["가족이 확인 후 해제", events["unlock_family"]],
        ],
    }
