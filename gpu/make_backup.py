"""Make the offline backup set from the live GPU endpoints (run while the GPU apps are up).

  /Users/kimble/01_Projects/CodySafe_wt/sim/server/.venv/bin/python gpu/make_backup.py \
      --sim /Users/kimble/01_Projects/CodySafe_wt/sim/server [--tts] [--judge] [--answers eval/demo_answers.csv]

- TTS: every spoken line (lines + pressure) of every graph, rendered for every preset with seed 0
  (OTP digits fixed), voice SIM_TTS_VOICE (default caller_male), tone of the node -> server/backup/tts/*.mp3
- Judge: for every node, the graph's own choice texts + the paraphrased answer sets (judge_holdout, demo answers)
  judged by the GPU LLM with the training judge prompt -> server/backup/judge.json
Token and URLs come from the sim server/.env (never printed).
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

GPU_ROOT = Path(__file__).resolve().parents[1]
OUT = GPU_ROOT / "server" / "backup"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # readers never see a half-written file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", required=True, help="path to the training server folder (hoyeon/sim server/)")
    ap.add_argument("--tts", action="store_true")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--answers", action="append", default=[])
    a = ap.parse_args()
    sys.path.insert(0, a.sim)
    from guard import config  # noqa: F401  (loads server/.env into the environment)
    from guard import sim_api
    from guard.sim import engine, judge
    from guard.sim.schema import PRESETS, SimProfile

    import importlib.util  # backup.py lives in this branch; the "guard" package above comes from the sim folder
    spec = importlib.util.spec_from_file_location("sim_backup", GPU_ROOT / "server/guard/sim/backup.py")
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    voice = os.getenv("SIM_TTS_VOICE", "") or "caller_male"
    graphs = engine.graphs()

    if a.tts:
        (OUT / "tts").mkdir(exist_ok=True)
        items, made, t0 = {}, 0, time.time()
        for preset_id, preset in PRESETS.items():
            prof = SimProfile(**preset["profile"])
            for graph in graphs.values():
                values = engine.start(graph, prof, seed=0)["values"]
                for node_id, node in graph.nodes.items():
                    for line, tone in [(x, node.tone) for x in node.lines] + [(x, node.pressure_tone) for x in node.pressure]:
                        text = engine.render(line, values)
                        key = backup.tts_key(text, tone, voice)
                        items[key] = {"text": text, "tone": tone, "voice": voice, "scenario": graph.id,
                                      "node": node_id, "preset": preset_id}
        for key, it in items.items():
            mp3 = OUT / "tts" / f"{key}.mp3"
            if mp3.exists():
                continue
            for attempt in range(3):
                try:
                    os.environ["SIM_TTS_TIMEOUT"] = "120"
                    audio, kind = sim_api.call_tts(it["text"], it["tone"])
                    break
                except Exception as exc:  # cold start or transient error
                    print("retry", attempt, type(exc).__name__, flush=True)
                    time.sleep(10)
            else:
                raise SystemExit(f"TTS failed: {it['scenario']} {it['node']}")
            enc = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "-", "-ac", "1", "-b:a", "64k",
                                  "-f", "mp3", "-"], input=audio, capture_output=True, check=True)
            mp3.write_bytes(enc.stdout)
            made += 1
            print(f"tts {made}/{len(items)} {it['scenario']}/{it['node']} {it['tone']}", flush=True)
        manifest["tts"] = {"made_at": time.strftime("%Y-%m-%d %H:%M %Z"), "voice": voice, "count": len(items),
                           "format": "mp3 64 kbps mono", "seed": 0, "presets": list(PRESETS),
                           "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base (voice designed by Qwen3-TTS-12Hz-1.7B-VoiceDesign)",
                           "gpu": "Modal NVIDIA L40S", "items": items, "seconds": round(time.time() - t0)}
        _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=1))

    if a.judge:
        os.environ["SIM_LLM_TIMEOUT"] = "60"
        table_path = OUT / "judge.json"
        table = json.loads(table_path.read_text()) if table_path.exists() else {}
        jobs = []  # (scenario, node, answer, label or None)
        # Choice sentences: use the graph's own grade/intent (authoritative, no LLM) for every preset.
        # The OTP digits in a choice change per session, so those keys only match seed-0 sessions.
        for preset in PRESETS.values():
            prof = SimProfile(**preset["profile"])
            for graph in graphs.values():
                state = engine.start(graph, prof, seed=0)
                for node_id, node in graph.nodes.items():
                    for ch in node.choices:
                        text = engine.render(ch.text, state["values"])
                        table[f"{graph.id}|{node_id}|{backup.norm_answer(text)}"] = {
                            "grade": ch.grade, "intent": ch.intent, "confidence": 1.0, "answer": text,
                            "source": "graph-choice"}
        for path in a.answers:
            with open(path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    jobs.append((row["scenario_id"], row["node_id"], row["answer"], row.get("label") or None))
        made, agree, labelled = 0, 0, 0
        for scenario, node_id, answer, label in jobs:
            key = f"{scenario}|{node_id}|{backup.norm_answer(answer)}"
            if key in table:
                continue
            graph = graphs[scenario]
            state = engine.start(graph, SimProfile(**PRESETS["mother_74_alone"]["profile"]), seed=0)
            state["node"] = node_id
            ctx = engine._judge_context(graph, state)
            res = judge._ask_gpu(answer, ctx)
            table[key] = {"grade": res["grade"], "intent": res["intent"], "confidence": res["confidence"],
                          "answer": answer, "source": "gpu-llm"}
            made += 1
            if label:
                labelled += 1
                agree += res["grade"] == label
            print(f"judge {made}/{len(jobs)} {scenario}/{node_id} -> {res['grade']}", flush=True)
        _atomic_write(table_path, json.dumps(table, ensure_ascii=False, indent=1))
        manifest["judge"] = {"made_at": time.strftime("%Y-%m-%d %H:%M %Z"), "count": len(table),
                             "model": "kakaocorp/kanana-1.5-8b-instruct-2505 fp8 (vLLM)", "gpu": "Modal NVIDIA L40S",
                             "new_this_run": made, "agree_with_label_this_run": f"{agree}/{labelled}"}
        _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=1))
    print("manifest", manifest_path)


if __name__ == "__main__":
    main()
