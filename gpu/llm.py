"""CodySafe LLM on Modal: vLLM OpenAI-compatible server (Kanana 1.5 8B, fp8).

Deploy:   modal deploy gpu/llm.py
Prefill:  modal run gpu/llm.py::download      (weights -> Volume on CPU, no GPU time)
Call:     <url>/v1/chat/completions  with  Authorization: Bearer $GPU_TOKEN
Health:   <url>/health  (no auth, 200 when the engine is up)

Token lives only in the Modal Secret `codysafe-gpu` (key GPU_TOKEN) and the untracked server/.env.
"""
import os
import subprocess

import modal

APP_NAME = "codysafe-llm"
MODEL = os.environ.get("CODYSAFE_LLM_MODEL", "kakaocorp/kanana-1.5-8b-instruct-2505")
SERVED_NAME = "codysafe-llm"
GPU = os.environ.get("CODYSAFE_LLM_GPU", "L40S")
PORT = 8000
MINUTES = 60

image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.21.0", "huggingface_hub[hf_xet]")
    .env({"HF_XET_HIGH_PERFORMANCE": "1", "VLLM_LOG_STATS_INTERVAL": "5",
          "CODYSAFE_LLM_MODEL": MODEL})
)

hf_cache = modal.Volume.from_name("codysafe-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("codysafe-vllm-cache", create_if_missing=True)
VOLUMES = {"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache}

app = modal.App(APP_NAME)


@app.function(image=image, volumes=VOLUMES, timeout=30 * MINUTES)
def download():
    from huggingface_hub import snapshot_download

    path = snapshot_download(MODEL, ignore_patterns=["*.pt", "*.pth", "original/*"])
    hf_cache.commit()
    print("cached", MODEL, "->", path)


@app.function(
    image=image,
    gpu=GPU,
    volumes=VOLUMES,
    secrets=[modal.Secret.from_name("codysafe-gpu")],
    min_containers=0,          # scale to zero; gpu/warm.sh raises this to 1 only for the demo window
    max_containers=1,          # credit guard
    scaledown_window=5 * MINUTES,
    timeout=24 * 60 * MINUTES,
    startup_timeout=15 * MINUTES,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=PORT, startup_timeout=15 * MINUTES)
def serve():
    cmd = [
        "vllm", "serve", MODEL,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0", "--port", str(PORT),
        "--quantization", "fp8",
        "--max-model-len", "4096",
        "--gpu-memory-utilization", "0.90",
        "--uvicorn-log-level", "warning",
    ]
    if os.environ.get("CODYSAFE_FAST_BOOT") == "1":
        cmd.append("--enforce-eager")
    # Token via VLLM_API_KEY, not --api-key: vLLM logs its non-default CLI args at startup.
    env = dict(os.environ, VLLM_API_KEY=os.environ["GPU_TOKEN"])
    # Popen (not run): web_server waits for the port while the process keeps serving.
    subprocess.Popen(cmd, env=env)
