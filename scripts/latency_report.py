"""전화·문자 훈련의 차례별 지연(R-003): sim_turns 표에서 음성 인식(stt_ms)과 판정(latency_ms) 시간을 모아 eval/latency.md로 쓴다.

쓰는 법(저장소 루트): server/.venv/bin/python scripts/latency_report.py --db <GUARD_DB 경로>
답 원문은 쓰지 않는다.
"""
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pct(values: list[int], q: float):
    if not values:
        return "–"
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("GUARD_DB", str(ROOT / "server" / "data" / "guard.db")))
    parser.add_argument("--out", default=str(ROOT / "eval" / "latency.md"))
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT t.input_type, t.source, t.latency_ms, t.stt_ms, s.mode FROM sim_turns t JOIN sim_sessions s ON s.id = t.session_id"
    ).fetchall()
    lines = [
        "# 훈련 차례별 지연 (R-003)",
        "",
        f"- 만든 때: {datetime.now(timezone(timedelta(hours=9))):%Y-%m-%d %H:%M} KST, 차례 {len(rows)}개",
        "- 판정 시간(latency_ms)은 서버에서 잰 값, 음성 인식 시간(stt_ms)은 화면에서 말이 끝난 뒤 글자가 오기까지 잰 값이다.",
        "",
        "| 훈련 | 답 방식 | 판정 경로 | 차례 수 | 판정 중앙값(ms) | 판정 p90(ms) | 인식 중앙값(ms) | 인식 p90(ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["mode"], r["input_type"], r["source"]), []).append(r)
    for (mode, kind, source), items in sorted(groups.items()):
        judge = [r["latency_ms"] for r in items if r["latency_ms"] is not None]
        stt = [r["stt_ms"] for r in items if r["stt_ms"] is not None]
        lines.append(f"| {mode} | {kind} | {source} | {len(items)} | {pct(judge, .5)} | {pct(judge, .9)} | {pct(stt, .5)} | {pct(stt, .9)} |")
    if not any(r["stt_ms"] is not None for r in rows):
        lines += ["", "- 음성 인식 차례는 아직 없다(마이크로 말한 기록이 생기면 다시 만든다)."]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{args.out} ({len(rows)}차례)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
