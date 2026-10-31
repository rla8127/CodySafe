"""탐지 시연용 합성 사기 통화(T-008)를 만든다. 실제 사람 목소리가 아니라 macOS `say`(TTS)로 읽은 것이다.

기관 사칭 대본 그래프(agency_call)의 대사를 '혼자 사시는 70대 어머니' 프리셋으로 채워 읽는다.
사기범 역은 Yuna, 받는 사람 역은 Grandma 목소리이고, 맨 앞에 합성 음성이라고 알린다.
임대 GPU TTS 주소가 오면 그 음성으로 다시 만들 수 있다(지금은 macOS 음성만).

쓰는 법(저장소 루트, macOS): server/.venv/bin/python scripts/make_synthetic_call.py
결과: eval/synthetic_call.wav(16kHz 모노, 300–3400Hz 전화 음질), eval/synthetic_call.txt(대본)
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from guard.sim import engine  # noqa: E402
from guard.sim.schema import preset_profile  # noqa: E402

SCAMMER, VICTIM, NOTICE = "Yuna", "Grandma", "Yuna"


def script() -> list[tuple[str, str]]:
    graph = engine.get_graph("agency_call")
    values = engine.start(graph, preset_profile("mother_74_alone"), seed=1)["values"]
    values["otp"] = graph.bait.otp
    say = lambda node, key="lines": [engine.render(t, values) for t in getattr(graph.nodes[node], key)]
    mid = lambda node: engine.render(next(c.text for c in graph.nodes[node].choices if c.grade == "중답"), values)
    turns = [(NOTICE, "이 녹음은 훈련용 합성 음성입니다. 실제 통화가 아닙니다.")]
    for node in ("n1_intro", "n2_fear", "n3_otp", "n4_transfer"):
        turns += [(SCAMMER, line) for line in say(node)]
        if node != "n4_transfer":
            turns.append((VICTIM, mid(node)))
            turns += [(SCAMMER, line) for line in say(node, "pressure")]
    return turns


def main() -> int:
    if not shutil.which("say") or not shutil.which("ffmpeg"):
        print("macOS say와 ffmpeg가 필요합니다")
        return 1
    turns = script()
    out_dir = ROOT / "eval"
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (voice, text) in enumerate(turns):
            part = Path(tmp) / f"{i:02d}.aiff"
            subprocess.run(["say", "-v", voice, "-r", "175", "-o", str(part), text], check=True)
            parts.append(part)
        listing = Path(tmp) / "list.txt"
        silence = Path(tmp) / "gap.aiff"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.5", str(silence)], check=True)
        listing.write_text("".join(f"file '{p}'\nfile '{silence}'\n" for p in parts))
        subprocess.run([
            "ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-af", "highpass=f=300,lowpass=f=3400", "-ar", "16000", "-ac", "1", str(out_dir / "synthetic_call.wav"),
        ], check=True)
    lines = ["# 합성 사기 통화 대본 (훈련·탐지 시연용, 실제 통화 아님)", "",
             "macOS `say` 음성으로 읽은 합성 음성입니다. 대사는 CodySafe 기관 사칭 대본 그래프(agency_call)를 '혼자 사시는 70대 어머니' 프리셋으로 채운 것입니다.", ""]
    lines += [f"- {'안내' if i == 0 else ('사기범 역' if v == SCAMMER else '받는 사람 역')}({v}): {t}" for i, (v, t) in enumerate(turns)]
    (out_dir / "synthetic_call.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out_dir / 'synthetic_call.wav'} ({len(turns)}개 발화)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
