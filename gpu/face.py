"""CodySafe face on Modal: one-off portrait of a FICTIONAL person for the family video-call training scene.

Model: Tongyi-MAI/Z-Image-Turbo (Apache-2.0, not gated). FLUX.1-schnell was the first pick but its HF repo
is gated (accept-terms), so it is not used.

Run:  modal run gpu/face.py                 -> runs/face_0.png .. runs/face_3.png
      modal run gpu/face.py --n 2 --seed 7
      modal run gpu/face.py --preset son_accident,daughter_deposit   -> runs/face_<preset>_<i>.png
      (presets: gpu/deepfake_presets.py — age band x gender x story x expression)

The person does not exist; no real face is used as input. Not deployed (modal run only), scale to zero.
"""
import modal

APP_NAME = "codysafe-face"
REPO = "Tongyi-MAI/Z-Image-Turbo"
GPU = "L40S"
MINUTES = 60

PROMPT = (
    "Photorealistic passport-style head-and-shoulders portrait photo of a fictional Korean man in his late "
    "20s, short black hair, plain casual dark t-shirt, facing the camera straight on, eyes looking directly "
    "into the camera, neutral expression, mouth closed, face centered, shoulders up, plain light grey "
    "background, soft even studio lighting, sharp focus, natural skin texture, no text, no watermark, "
    "no logo, no glasses, no hands"
)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "torch==2.8.0", index_url="https://download.pytorch.org/whl/cu128",
    )
    .uv_pip_install(
        "diffusers==0.36.0", "transformers==4.57.1", "accelerate==1.11.0", "safetensors", "sentencepiece",
        "huggingface_hub[hf_xet]", "Pillow",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

hf_cache = modal.Volume.from_name("codysafe-hf-cache", create_if_missing=True)
VOLUMES = {"/root/.cache/huggingface": hf_cache}
app = modal.App(APP_NAME)


@app.function(image=image, gpu=GPU, volumes=VOLUMES, timeout=30 * MINUTES, min_containers=0, max_containers=1)
def generate(n: int = 4, seed: int = 20261101, size: int = 1024, prompts: list[str] | None = None) -> list[bytes]:
    import io
    import time

    import torch
    from diffusers import ZImagePipeline

    t0 = time.time()
    pipe = ZImagePipeline.from_pretrained(REPO, torch_dtype=torch.bfloat16).to("cuda")
    hf_cache.commit()
    print(f"loaded {REPO} in {time.time() - t0:.1f}s")
    out = []
    jobs = [(p, i) for p in (prompts or [PROMPT]) for i in range(n)]
    for k, (prompt, i) in enumerate(jobs):
        t1 = time.time()
        img = pipe(prompt=prompt, height=size, width=size, num_inference_steps=9, guidance_scale=0.0,
                   generator=torch.Generator("cuda").manual_seed(seed + i)).images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
        print(f"image {k} seed {seed + i} in {time.time() - t1:.1f}s")
    return out


@app.local_entrypoint()
def main(n: int = 4, seed: int = 20261101, size: int = 1024, preset: str = ""):
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    runs = here.parent / "runs"
    runs.mkdir(exist_ok=True)
    names = [x for x in preset.split(",") if x]
    prompts = None
    if names:
        sys.path.insert(0, str(here))
        from deepfake_presets import PRESETS
        prompts = [PRESETS[x]["face_prompt"] for x in names]
    pngs = generate.remote(n, seed, size, prompts)
    labels = [f"face_{x}_{i}" for x in names for i in range(n)] if names else [f"face_{i}" for i in range(n)]
    for label, png in zip(labels, pngs):
        p = runs / f"{label}.png"
        p.write_bytes(png)
        print("saved", p)
