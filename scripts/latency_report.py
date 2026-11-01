"""전화·문자 훈련의 차례별 지연(R-003): sim_turns 표에서 음성 인식(stt_ms)과 판정(latency_ms) 시간을 모아 eval/latency.md로 쓴다.

쓰는 법(저장소 루트): server/.venv/bin/python scripts/latency_report.py --db <GUARD_DB 경로>
답 원문은 쓰지 않는다.
"""
import argparse
import json
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


def cer(said: str, heard: str) -> float:
    """글자 오류율: 띄어쓰기·문장부호를 뺀 글자끼리 편집 거리 / 말한 글자 수."""
    a = [ch for ch in said if ch.isalnum()]
    b = [ch for ch in heard if ch.isalnum()]
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1] / max(1, len(a))


def gpu_run_section(conn, run: dict, path: str) -> list[str]:
    """임대 GPU 경로 전화 훈련 1회(scripts/gpu_call_run.py)의 대사 합성·답 인식·판정 시간."""
    caps = run.get("caps", {})
    result = run.get("result") or {}
    score = result.get("score") or {}
    turns = conn.execute(
        "SELECT seq, node_id, source, grade, intent, latency_ms, stt_ms FROM sim_turns WHERE session_id = ? ORDER BY seq",
        (run["session_id"],),
    ).fetchall()
    tts = [t for t in run["tts"] if t["status"] == 200]
    secs = sorted(t["wall_ms"] / 1000 for t in tts)
    out = [
        "",
        f"## 임대 GPU 경로 전화 훈련 1회 (11-01 {run['started'][:5]}–{run['finished'][:5]} KST, 기관 사칭)",
        "",
        f"- 경로: 판정 `{caps.get('llm')}`(규칙으로 못 정한 답만 LLM), 대사 합성 {'GPU' if caps.get('tts') else '브라우저'}, "
        f"답 인식 {'GPU' if caps.get('stt') else '브라우저'}. 임대 GPU는 Modal NVIDIA L40S(O-2 실측 `eval/gpu_latency.md`).",
        "- 방법: `scripts/gpu_call_run.py`가 화면(sim2.js)과 같은 순서로 localhost:8091에 요청했다. 사용자 답은 macOS `say`(Yuna)로 "
        "만든 **합성 음성**(16kHz WAV)이라 마이크 실측(R-003)을 대신하지 않는다. 기록 `" + Path(path).name + "`.",
        f"- 결과: {len(turns)}차례 뒤 {'안전 종료' if result.get('terminal') == 'safe' else result.get('terminal')}, "
        f"{score.get('total')}점({score.get('band')}).",
        "",
        "### 대사 음성 합성 (처음 만드는 대사, 캐시 없음)",
        "",
        "| 장면 | 말투 | 글자 수 | 음성 길이(초) | 합성 시간(초) | 합성/음성 |",
        "|---|---|---|---|---|---|",
    ]
    for t in run["tts"]:
        ratio = f"{t['wall_ms'] / 1000 / t['audio_s']:.1f}배" if t.get("audio_s") else "–"
        out.append(f"| {t['node']} | {t['tone']} | {t['chars']} | {t.get('audio_s', '–')} | {t['wall_ms'] / 1000:.1f} | {ratio} |")
    if secs:
        out += ["", f"- 합성 시간 중앙값 {secs[len(secs) // 2]:.1f}초(최소 {secs[0]:.1f}, 최대 {secs[-1]:.1f}). 같은 대사를 캐시에서 읽으면 서버 0ms·"
                "요청 2–3ms(09:0x 측정). 그래서 대사는 미리 만들어 두고, 화면은 3.5초 안에 안 오면 그 대사만 브라우저 음성으로 읽는다."]
    out += ["", "### 답 음성 인식", "", "| 차례 | 녹음 길이(초) | 인식 시간(초) | 글자 오류율 |", "|---|---|---|---|"]
    for s in run["stt"]:
        rate = f"{cer(s['said'], s.get('heard', '')) * 100:.0f}%" if s["status"] == 200 else f"실패 {s['status']}"
        out.append(f"| {s['n']} | {s['audio_s']} | {s['wall_ms'] / 1000:.1f} | {rate} |")
    stt_secs = sorted(s["wall_ms"] / 1000 for s in run["stt"] if s["status"] == 200)
    if len(stt_secs) > 1 and stt_secs[-1] > 3 * stt_secs[0]:
        out += ["", f"- 인식 시간 편차가 크다(최소 {stt_secs[0]:.1f}, 최대 {stt_secs[-1]:.1f}초). 원인은 미확인: 음성 서버 하나가 합성과 인식을 "
                "같은 GPU에서 받으므로(동시 입력 8개 허용) 합성과 겹치면 느려질 수 있다. 콜드 스타트는 O-2 실측(`eval/gpu_latency.md`)을 본다."]
    out += ["", "### 차례별 판정", "", "| 차례 | 장면 | 판정 경로 | 등급·의도 | 판정(ms) | 인식+판정(초) |", "|---|---|---|---|---|---|"]
    for r in turns:
        total = ((r["stt_ms"] or 0) + (r["latency_ms"] or 0)) / 1000
        out.append(f"| {r['seq']} | {r['node_id']} | {r['source']} | {r['grade']}·{r['intent']} | {r['latency_ms']} | {total:.1f} |")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("GUARD_DB", str(ROOT / "server" / "data" / "guard.db")))
    parser.add_argument("--out", default=str(ROOT / "eval" / "latency.md"))
    parser.add_argument("--run-json", default="", help="scripts/gpu_call_run.py 기록. 주면 임대 GPU 경로 전화 훈련 절을 덧붙인다")
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
    if args.run_json:
        lines += gpu_run_section(conn, json.loads(Path(args.run_json).read_text(encoding="utf-8")), args.run_json)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{args.out} ({len(rows)}차례)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
