"""GPU 경로 전화 훈련 1회(O-1 리허설, CSIT 지시). localhost:8091 서버에만 요청하고 server/.env는 읽지 않는다.

화면(sim2.js)이 하는 순서를 그대로 따른다: 장면 대사마다 /v1/sim/tts(말투 포함) → 답은 녹음 파일을 /v1/sim/stt →
받은 글자를 input_type=voice, stt_ms와 함께 /turn → 마무리 → 결과. 사용자 목소리는 macOS say(Yuna)로 만든 합성 음성이다.

쓰는 법(저장소 루트, 8091 서버가 켜져 있을 때): server/.venv/bin/python -I scripts/gpu_call_run.py --audio-dir <임시 폴더> --json eval/gpu_call_run.json
임대 GPU를 부르므로(대사 합성·인식·판정) 필요할 때 한 번만 돌린다. 합성 음성 파일은 --audio-dir에만 두고 저장소에 넣지 않는다.
"""
import argparse
import io
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8091")
ap.add_argument("--audio-dir", required=True)
ap.add_argument("--json", required=True)
args = ap.parse_args()
BASE = args.base
out = Path(args.audio_dir)
out.mkdir(parents=True, exist_ok=True)
ANSWERS = [  # 장면 순서대로 말할 답(판정 경로를 고루 보려고 애매한 답 → 되묻기 → 확인 순)
    "아이고, 갑자기 그런 말씀을 하시니 너무 당황스럽네요.",
    "그 검찰청이 어디라고요? 사건 번호가 뭔데요?",
    "일단 전화 끊고 검찰청 대표번호로 제가 직접 확인해 볼게요.",
    "전화 끊고 경찰서 대표번호로 확인할게요.",
    "전화 끊을게요.",
]
rec = {"tts": [], "stt": [], "turns": [], "started": time.strftime("%H:%M:%S")}
c = httpx.Client(base_url=BASE, timeout=120)


def ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def wav_seconds(data: bytes):
    try:
        with wave.open(io.BytesIO(data)) as w:
            return round(w.getnframes() / w.getframerate(), 2)
    except Exception:
        return None


def speak_scene(scene: dict, H: dict, idx: int) -> None:
    for j, line in enumerate(scene["lines"]):
        t0 = time.perf_counter()
        r = c.post("/v1/sim/tts", json={"text": line, "tone": scene["tone"]}, headers=H)
        item = {"scene": idx, "node": scene["node_id"], "tone": scene["tone"], "chars": len(line), "status": r.status_code,
                "wall_ms": ms(t0), "server_ms": r.headers.get("x-sim-ms"), "type": r.headers.get("content-type")}
        if r.status_code == 200:
            item["audio_s"] = wav_seconds(r.content)
            name = f"tts_{idx}_{j}_{scene['tone']}.wav"
            (out / name).write_bytes(r.content)
            item["file"] = name
        else:
            item["body"] = r.text[:120]
        rec["tts"].append(item)
        print("TTS", json.dumps(item, ensure_ascii=False), flush=True)


def voice_answer(text: str, n: int, H: dict) -> tuple[str, int]:
    aiff, wav = out / f"answer_{n}.aiff", out / f"answer_{n}.wav"
    subprocess.run(["say", "-v", "Yuna", "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
    data = wav.read_bytes()
    t0 = time.perf_counter()
    r = c.post("/v1/sim/stt", content=data, headers={**H, "Content-Type": "audio/wav"})
    wall = ms(t0)
    item = {"n": n, "said": text, "audio_s": wav_seconds(data), "status": r.status_code, "wall_ms": wall}
    if r.status_code == 200:
        body = r.json()
        item.update(heard=body.get("text", ""), server_ms=body.get("ms"))
    else:
        item["body"] = r.text[:120]
    rec["stt"].append(item)
    print("STT", json.dumps(item, ensure_ascii=False), flush=True)
    return item.get("heard") or "", wall


dev = c.post("/v1/devices", json={"name": "O-1 GPU 리허설"}).json()
H = {"Authorization": f"Bearer {dev['token']}"}
caps = c.get("/v1/sim/scenarios", headers=H).json()
rec["caps"] = {k: caps.get(k) for k in ("llm", "tts", "stt")}
print("CAPS", rec["caps"], flush=True)
s = c.post("/v1/sim/sessions", json={"scenario_id": "agency_call", "mode": "call"}, headers=H).json()
sid, scene = s["session_id"], s["scene"]
rec["session_id"] = sid
idx = 1
resp = None
for n, answer in enumerate(ANSWERS, 1):
    speak_scene(scene, H, idx)
    heard, stt_ms = voice_answer(answer, n, H)
    if not heard:  # 화면은 인식이 안 되면 선택지로 넘어간다. 여기서는 그대로 멈춘다
        print("STOP: STT 결과 없음", flush=True)
        break
    t0 = time.perf_counter()
    r = c.post(f"/v1/sim/sessions/{sid}/turn", json={"text": heard, "input_type": "voice", "stt_ms": stt_ms}, headers=H)
    resp = r.json()
    rec["turns"].append({"n": n, "status": r.status_code, "wall_ms": ms(t0), "keys": sorted(resp)})
    print("TURN", n, r.status_code, ms(t0), sorted(resp), flush=True)
    if resp.get("scene"):
        scene = resp["scene"]
        idx += 1
        continue
    break

now = c.get(f"/v1/sim/sessions/{sid}/result", headers=H).json()
rec["after_turns"] = {"status": now.get("status"), "terminal": now.get("terminal")}
print("AFTER", json.dumps(rec["after_turns"], ensure_ascii=False)[:300], flush=True)
if now.get("status") == "closing":
    ids = {o["id"] for o in now["closing"]["options"]}
    opts = [k for k in ("k1", "k2", "k3") if k in ids]  # 공식번호 확인·가족 확인·신고(그래프의 k1–k3)
    r = c.post(f"/v1/sim/sessions/{sid}/closing", json={"option_ids": opts}, headers=H)
    rec["closing"] = {"status": r.status_code, "options": opts}
    res = c.get(f"/v1/sim/sessions/{sid}/result", headers=H).json()
    rec["result"] = {"status": res.get("status"), "score": res.get("score"), "terminal": (res.get("terminal") or {}).get("type")}
    print("RESULT", json.dumps(rec["result"], ensure_ascii=False), flush=True)
rec["finished"] = time.strftime("%H:%M:%S")
Path(args.json).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("saved", args.json)
