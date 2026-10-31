"""CodySafe voice on Modal: STT (faster-whisper large-v3-turbo) + TTS (Qwen3-TTS 1.7B VoiceDesign).

One app, one GPU container, FastAPI with Bearer auth (same token as the LLM, Secret `codysafe-gpu`).

Deploy:   modal deploy gpu/voice.py
Prefill:  modal run gpu/voice.py::download

POST /stt   multipart `file` (wav/webm/m4a/mp3), optional `language` (default ko), `model` ignored
            -> {"text": str, "duration_s": float, "elapsed_s": float}
POST /tts   JSON {"text"|"input": str, "voice": caller_male|caller_female|family (else caller_male),
                  "format"|"response_format": "wav", "emotion"?: str, "instruct"?: str}
            -> audio/wav bytes
GET  /health -> {"ok": true, "model": str}   (no auth)
GET  /gpu    -> GPU memory numbers (auth), for eval/gpu_latency.md

Voices are designed from text descriptions (VoiceDesign). No real person's voice is cloned.
STT model matches the team's korean-stt server (openai/whisper-large-v3-turbo, CTranslate2 conversion
dropbox-dash/faster-whisper-large-v3-turbo) so detection and training see the same recognizer.
"""
import modal

APP_NAME = "codysafe-voice"
STT_REPO = "dropbox-dash/faster-whisper-large-v3-turbo"
TTS_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
GPU = "L40S"
MINUTES = 60

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .apt_install("sox", "libsox-fmt-all", "ffmpeg")
    .uv_pip_install(
        "torch==2.8.0", "torchaudio==2.8.0",
        index_url="https://download.pytorch.org/whl/cu128",
    )
    .uv_pip_install(
        "qwen-tts==0.1.1", "faster-whisper==1.2.1", "soundfile", "numpy<2.3",
        "fastapi[standard]", "python-multipart", "huggingface_hub[hf_xet]",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

hf_cache = modal.Volume.from_name("codysafe-hf-cache", create_if_missing=True)
VOLUMES = {"/root/.cache/huggingface": hf_cache}
app = modal.App(APP_NAME)

VOICES = {
    "caller_male": "A Korean man in his early 40s with a low, steady, businesslike voice, "
                   "speaking standard Seoul Korean on a phone call.",
    "caller_female": "A Korean woman in her early 30s with a clear, polite, composed call-center voice, "
                     "speaking standard Seoul Korean on a phone call.",
    "family": "A Korean man in his late 20s, the listener's son, with a natural, familiar, warm voice, "
              "speaking casual Seoul Korean on a phone call.",
}
SEEDS = {"caller_male": 1101, "caller_female": 2202, "family": 3303}  # fixed seed per voice -> steadier timbre
TONES = {  # O-1 TONE_GUIDE keys -> English style words for the instruct
    "calm": "calm, slow and clearly articulated",
    "official": "stiff, formal and bureaucratic, slightly low pitch",
    "urgent": "urgent and fast, pressing the listener to hurry",
    "threat": "intimidating, stern and low, scolding",
    "tremble": "anxious and trembling, short of breath",
    "sob": "tearful, sobbing, the ends of sentences shaking",
    "friendly": "friendly, warm and bright",
}
MAX_TEXT = 400
MAX_AUDIO = 15 * 1024 * 1024


@app.function(image=image, volumes=VOLUMES, timeout=30 * MINUTES)
def download():
    from huggingface_hub import snapshot_download

    for repo in (STT_REPO, TTS_REPO):
        print("cached", repo, "->", snapshot_download(repo))
    hf_cache.commit()


@app.cls(
    image=image,
    gpu=GPU,
    cpu=4.0,                   # TTS decoding loop is CPU-bound per step; Modal default CPU is small
    memory=16384,
    volumes=VOLUMES,
    secrets=[modal.Secret.from_name("codysafe-gpu")],
    min_containers=0,
    max_containers=1,
    scaledown_window=5 * MINUTES,
    timeout=10 * MINUTES,
    startup_timeout=10 * MINUTES,
)
@modal.concurrent(max_inputs=8)
class Voice:
    @modal.enter()
    def load(self):
        import threading

        import torch
        from faster_whisper import WhisperModel
        from qwen_tts import Qwen3TTSModel

        self.lock = threading.Lock()
        self.stt = WhisperModel(STT_REPO, device="cuda", compute_type="float16")
        self.tts = Qwen3TTSModel.from_pretrained(TTS_REPO, device_map="cuda:0", dtype=torch.bfloat16,
                                                 attn_implementation="sdpa")
        langs = self.tts.get_supported_languages() or []
        self.lang = next((x for x in langs if str(x).lower() in ("korean", "ko")), "Korean")
        # warm the kernels once so the first real request is not the slow one
        self._synth("안녕하세요.", "caller_male", "")

    def _synth(self, text: str, voice: str, style: str):
        import io

        import soundfile as sf
        import torch

        instruct = VOICES[voice] + (f" Speaking style: {style}." if style else "")
        with self.lock:
            torch.manual_seed(SEEDS[voice])
            wavs, sr = self.tts.generate_voice_design(text=text, instruct=instruct, language=self.lang)
        buf = io.BytesIO()
        sf.write(buf, wavs[0], sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @modal.asgi_app()
    def web(self):
        import os
        import secrets
        import subprocess
        import tempfile
        import time

        import numpy as np
        import torch
        from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
        from fastapi.responses import Response

        token = os.environ["GPU_TOKEN"]
        api = FastAPI(title="codysafe-voice", docs_url=None, redoc_url=None, openapi_url=None)

        def auth(request: Request):
            got = request.headers.get("authorization", "")
            if not (got.startswith("Bearer ") and secrets.compare_digest(got[7:].strip(), token)):
                raise HTTPException(status_code=401, detail="unauthorized")

        @api.get("/health")
        def health():
            return {"ok": True, "model": f"stt={STT_REPO}; tts={TTS_REPO}"}

        @api.post("/stt", dependencies=[Depends(auth)])
        def stt(file: UploadFile = File(...), language: str = Form("ko"), model: str = Form("")):
            data = file.file.read(MAX_AUDIO + 1)
            if not data:
                raise HTTPException(status_code=400, detail="empty file")
            if len(data) > MAX_AUDIO:
                raise HTTPException(status_code=413, detail="file too large")
            suffix = os.path.splitext(file.filename or "")[1] or ".wav"
            t0 = time.perf_counter()
            with tempfile.NamedTemporaryFile(suffix=suffix) as f:
                f.write(data)
                f.flush()
                # decode with ffmpeg ourselves (faster-whisper's PyAV path breaks on new av versions)
                dec = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", f.name, "-f", "f32le",
                                      "-ac", "1", "-ar", "16000", "-"], capture_output=True)
            if dec.returncode != 0 or not dec.stdout:
                raise HTTPException(status_code=400, detail="cannot decode audio")
            audio = np.frombuffer(dec.stdout, dtype=np.float32)
            with self.lock:
                segments, info = self.stt.transcribe(
                    audio, language=(language or "ko")[:2], beam_size=5, vad_filter=True,
                    condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segments).strip()
            return {"text": text, "duration_s": round(len(audio) / 16000, 3),
                    "elapsed_s": round(time.perf_counter() - t0, 3)}

        @api.post("/tts", dependencies=[Depends(auth)])
        async def tts(request: Request):
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="JSON body required")
            text = str(body.get("text") or body.get("input") or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="text required")
            if len(text) > MAX_TEXT:
                raise HTTPException(status_code=413, detail=f"text longer than {MAX_TEXT}")
            fmt = str(body.get("format") or body.get("response_format") or "wav").lower()
            if fmt != "wav":
                raise HTTPException(status_code=400, detail="only wav")
            voice = body.get("voice")
            voice = voice if voice in VOICES else "caller_male"
            emotion = str(body.get("emotion") or "")
            style = TONES.get(emotion) or str(body.get("instruct") or "")[:200]
            import anyio

            t0 = time.perf_counter()
            audio = await anyio.to_thread.run_sync(self._synth, text, voice, style)
            return Response(content=audio, media_type="audio/wav",
                            headers={"X-Elapsed-S": f"{time.perf_counter() - t0:.3f}", "X-Voice": voice})

        @api.get("/gpu", dependencies=[Depends(auth)])
        def gpu():
            smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True).stdout.strip()
            return {"nvidia_smi": smi,
                    "torch_max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20),
                    "torch_max_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20)}

        return api
