"""CodySafe video on Modal: talking-face MP4 of a FICTIONAL person (EchoMimicV3 Flash), "AI 생성" label burned in.

Models (all Apache-2.0 / MIT, not gated):
  BadToBest/EchoMimicV3  echomimicv3-flash-pro/  (Apache-2.0)  audio-driven transformer weights
  alibaba-pai/Wan2.1-Fun-V1.1-1.3B-InP          (Apache-2.0)  base DiT, VAE, umT5 text encoder, CLIP
  TencentGameMate/chinese-wav2vec2-base          (MIT)         audio encoder used by the Flash weights
Code: github.com/antgroup/echomimic_v3 (Apache-2.0) at a pinned commit; we drive its src/ modules the same
way as its infer_flash.py / run_flash.sh, with these changes (round 2, 2026-11-01, checked on frames + gpu/lipsync_check.py):
  - TeaCache off, audio CFG 5.0 (official 3.0 + TeaCache gave little mouth movement; see render() docstring)
  - long audio in ~100-frame chunks; each chunk starts from the previous chunk's last frame ("continue"),
    CLIP identity stays on the original face; audio features computed once over the whole clip
  - face/voice/script/prompt presets: gpu/deepfake_presets.py

Prefill:  modal run gpu/video.py::download        (weights -> Volume, CPU only)
Run:      modal run gpu/video.py --image runs/face_0.png --audio runs/family_call.wav [--out runs/video_family.mp4]
          [--preset son_accident] [--size 768] [--variants "steps:acfg:teacache,..."] [--start 6 --dur 4.84]

Not deployed. Separate app from codysafe-llm / codysafe-voice. Scale to zero, no warm containers.
Only synthetic inputs (generated face, TTS voice) go in.
"""
import modal

APP_NAME = "codysafe-video"
EM_COMMIT = "7e89489ca51c0d008fc1963ec6c03fc5bd0b9397"
EM_REPO = "BadToBest/EchoMimicV3"
WAN_REPO = "alibaba-pai/Wan2.1-Fun-V1.1-1.3B-InP"
W2V_REPO = "TencentGameMate/chinese-wav2vec2-base"
GPU = "L40S"
MINUTES = 60
LABEL = "AI 생성"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .apt_install("git", "ffmpeg", "fonts-noto-cjk", "libgl1", "libglib2.0-0")
    .uv_pip_install(
        "torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0",
        index_url="https://download.pytorch.org/whl/cu124",
    )
    .uv_pip_install(
        "diffusers==0.32.2", "transformers==4.49.0", "accelerate==1.4.0", "safetensors", "einops", "omegaconf",
        "librosa", "pyloudnorm", "moviepy==2.2.1", "imageio[ffmpeg]", "decord", "opencv-python-headless",
        "scipy", "ftfy", "sentencepiece", "timm", "tomesd", "torchdiffeq", "torchsde", "scikit-image",
        "numpy<2", "soundfile", "huggingface_hub[hf_xet]",
    )
    .run_commands(
        "git clone https://github.com/antgroup/echomimic_v3 /opt/echomimic_v3",
        f"cd /opt/echomimic_v3 && git checkout {EM_COMMIT}",
    )
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)

hf_cache = modal.Volume.from_name("codysafe-hf-cache", create_if_missing=True)
VOLUMES = {"/root/.cache/huggingface": hf_cache}
app = modal.App(APP_NAME)


def _paths(download: bool = False):
    from huggingface_hub import snapshot_download

    kw = {} if download else {"local_files_only": True}
    em = snapshot_download(EM_REPO, allow_patterns=["echomimicv3-flash-pro/*"], **kw)
    wan = snapshot_download(WAN_REPO, **kw)
    w2v = snapshot_download(W2V_REPO, ignore_patterns=["*fairseq*"], **kw)
    return em, wan, w2v


@app.function(image=image, volumes=VOLUMES, timeout=40 * MINUTES)
def download():
    for p in _paths(download=True):
        print("cached", p)
    hf_cache.commit()


def _chunks(total: int, max_len: int, overlap: int = 0) -> list[tuple[int, int]]:
    """Consecutive chunks (start, length) of length 4k+1 (Wan VAE), each <= max_len, sharing `overlap` frames."""
    import math

    step = max_len - overlap
    n = max(1, math.ceil((total - overlap) / step))
    want = (math.ceil((total - overlap) / n) + overlap + 2) // 4 * 4 + 1  # balanced, rounded up to 4k+1
    out, start = [], 0
    while start < total:
        length = (min(want, total - start) - 1) // 4 * 4 + 1
        if length < 5 or (out and length - overlap < 4):
            break
        out.append((start, length))
        if start + length >= total:
            break
        start += length - overlap
    return out


@app.function(image=image, gpu=GPU, volumes=VOLUMES, timeout=40 * MINUTES, min_containers=0, max_containers=1,
              cpu=4.0, memory=32768)
def render(image_png: bytes, audio_wav: bytes, prompt: str, size: int = 512, variants: list[dict] | None = None,
           chunk: int = 113, seed: int = 43, start: float = 0.0, dur: float = 0.0) -> list[bytes]:
    """One mp4 per variant. variant keys: steps (8), acfg (audio CFG, 3.0), teacache (False), join ("continue").

    Round-2 finding: with audio CFG the pipeline calls the transformer twice per step, but TeaCache counts
    calls as steps, so with the official flash settings (8 steps, skip 5) it reuses cached residuals across
    the conditional/unconditional calls. Default is therefore teacache off.
    """
    import math
    import os
    import subprocess
    import sys
    import time

    import imageio
    import librosa
    import numpy as np
    import torch
    from einops import rearrange
    from omegaconf import OmegaConf
    from PIL import Image

    os.chdir("/opt/echomimic_v3")
    sys.path.insert(0, "/opt/echomimic_v3")
    from transformers import AutoTokenizer, Wav2Vec2FeatureExtractor

    from src.cache_utils import get_teacache_coefficients
    from src.fm_solvers_unipc import FlowUniPCMultistepScheduler
    from src.pipeline_wan_fun_inpaint_audio_2512 import WanFunInpaintAudioPipeline
    from src.utils import color_transfer, filter_kwargs, get_image_to_video_latent2
    from src.wan_image_encoder import CLIPModel
    from src.wan_text_encoder import WanT5EncoderModel
    from src.wan_transformer3d_audio_2512 import WanTransformerAudioMask3DModel as WanTransformer
    from src.wan_vae import AutoencoderKLWan
    from src.wav2vec2 import Wav2Vec2Model

    t_all = time.time()
    em, wan, w2v = _paths()
    work = "/tmp/cs"
    os.makedirs(work, exist_ok=True)
    img_path, wav_path = f"{work}/ref.png", f"{work}/in.wav"
    open(img_path, "wb").write(image_png)
    open(f"{work}/orig.wav", "wb").write(audio_wav)
    trim = (["-ss", str(start)] if start else []) + (["-t", str(dur)] if dur else [])
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *trim, "-i", f"{work}/orig.wav", wav_path],
                   check=True)
    dtype, device, fps = torch.bfloat16, "cuda", 25

    # ---- models (as in infer_flash.py) ----
    t0 = time.time()
    audio_encoder = Wav2Vec2Model.from_pretrained(w2v, local_files_only=True).to("cpu")
    audio_encoder.feature_extractor._freeze_parameters()
    fe = Wav2Vec2FeatureExtractor.from_pretrained(w2v, local_files_only=True)
    cfg = OmegaConf.load("config/config.yaml")
    transformer = WanTransformer.from_pretrained(
        os.path.join(wan, cfg["transformer_additional_kwargs"].get("transformer_subpath", "transformer")),
        transformer_additional_kwargs=OmegaConf.to_container(cfg["transformer_additional_kwargs"]),
        low_cpu_mem_usage=True, torch_dtype=dtype)
    from safetensors.torch import load_file
    sd = load_file(os.path.join(em, "echomimicv3-flash-pro", "diffusion_pytorch_model.safetensors"))
    m, u = transformer.load_state_dict(sd, strict=False)
    print(f"echomimic weights: missing {len(m)}, unexpected {len(u)}")
    del sd
    vae = AutoencoderKLWan.from_pretrained(os.path.join(wan, cfg["vae_kwargs"].get("vae_subpath", "vae")),
                                           additional_kwargs=OmegaConf.to_container(cfg["vae_kwargs"])).to(dtype)
    tokenizer = AutoTokenizer.from_pretrained(
        os.path.join(wan, cfg["text_encoder_kwargs"].get("tokenizer_subpath", "tokenizer")))
    text_encoder = WanT5EncoderModel.from_pretrained(
        os.path.join(wan, cfg["text_encoder_kwargs"].get("text_encoder_subpath", "text_encoder")),
        additional_kwargs=OmegaConf.to_container(cfg["text_encoder_kwargs"]), low_cpu_mem_usage=True,
        torch_dtype=dtype).eval()
    clip = CLIPModel.from_pretrained(
        os.path.join(wan, cfg["image_encoder_kwargs"].get("image_encoder_subpath", "image_encoder"))).to(dtype).eval()
    cfg["scheduler_kwargs"]["shift"] = 1  # Flow_Unipc, same as infer_flash.py
    scheduler = FlowUniPCMultistepScheduler(**filter_kwargs(FlowUniPCMultistepScheduler,
                                                            OmegaConf.to_container(cfg["scheduler_kwargs"])))
    pipe = WanFunInpaintAudioPipeline(transformer=transformer, vae=vae, tokenizer=tokenizer,
                                      text_encoder=text_encoder, scheduler=scheduler, clip_image_encoder=clip)
    pipe.to(device=device)
    coeff = get_teacache_coefficients(wan)
    print(f"models loaded in {time.time() - t0:.1f}s")

    # ---- audio features once over the whole clip ----
    import pyloudnorm as pyln
    wav16, sr = librosa.load(wav_path, sr=16000)
    loud = pyln.Meter(sr).integrated_loudness(wav16)
    if abs(loud) <= 100:
        wav16 = pyln.normalize.loudness(wav16, loud, -23)
    total = int(len(wav16) / sr * fps)
    with torch.no_grad():
        feat = torch.from_numpy(np.squeeze(fe(wav16, sampling_rate=sr).input_values)).float().unsqueeze(0)
        emb = audio_encoder(feat, seq_len=total, output_hidden_states=True)
    emb = rearrange(torch.stack(emb.hidden_states[1:], dim=1).squeeze(0), "b s d -> s b d").cpu()  # [F, 12, 768]
    emb = emb.to(device=device, dtype=dtype)

    ref = Image.open(img_path).convert("RGB")
    w0, h0 = ref.size
    r = math.sqrt(w0 * h0 / size / size)
    sh, sw = (int(h0 / r // 16 * 16), int(w0 / r // 16 * 16)) if r > 1 else (h0 // 16 * 16, w0 // 16 * 16)
    neg = ("Gesture is bad. Gesture is unclear. Strange and twisted hands. Bad hands. Bad fingers. Unclear and "
           "blurry hands. Unclear gestures, broken hands, fused fingers. 手指融合，")
    print(f"audio {len(wav16) / sr:.2f}s -> {total} frames, {sh}x{sw}")
    _, _, clip_ref = get_image_to_video_latent2(ref, None, video_length=5, sample_size=[sh, sw])
    results = []
    for vi, var in enumerate(variants or [{}]):
        steps, acfg, tc = int(var.get("steps", 8)), float(var.get("acfg", 3.0)), bool(var.get("teacache", False))
        # join: "continue" = next chunk starts from the previous chunk's last frame (1 shared frame, CLIP identity
        # stays on the original face); "xfade" = every chunk starts from the face, 8-frame crossfade;
        # "restart" = round-1 behaviour (hard cut every chunk).
        join = var.get("join", "continue")
        overlap = {"continue": 1, "xfade": 8}.get(join, 0)
        plan = _chunks(total, chunk, overlap)
        print(f"variant {vi}: join={join} chunks {plan}")
        if tc and coeff is not None:
            pipe.transformer.enable_teacache(coeff, steps, 0.1, num_skip_start_steps=5, offload=False)
        else:
            pipe.transformer.disable_teacache()
        gen = torch.Generator(device=device).manual_seed(seed)
        frames, t_r = [], time.time()
        for ci, (st, length) in enumerate(plan):
            t1 = time.time()
            idx = (torch.arange(st, st + length).unsqueeze(1) + (torch.arange(5) - 2).unsqueeze(0))
            a = emb[idx.clamp(0, emb.shape[0] - 1)].unsqueeze(0)  # [1, F, 5, 12, 768]
            start_img = Image.fromarray(frames[-1]) if (join == "continue" and frames) else ref
            vid, vmask, _ = get_image_to_video_latent2(start_img, None, video_length=length, sample_size=[sh, sw])
            clip_img = clip_ref
            with torch.no_grad():
                sample = pipe(prompt, num_frames=length, negative_prompt=neg, audio_embeds=a, audio_scale=1.0,
                              ip_mask=None, use_un_ip_mask=False, height=sh, width=sw, generator=gen,
                              neg_scale=1.0, neg_steps=0, use_dynamic_cfg=False, use_dynamic_acfg=False,
                              guidance_scale=6.0, audio_guidance_scale=acfg, num_inference_steps=steps,
                              video=vid, mask_video=vmask, clip_image=clip_img, cfg_skip_ratio=0.0,
                              shift=5.0).videos
            x = sample[0, :, :length].permute(1, 2, 3, 0).float().clamp(0, 1).mul(255).byte().cpu().numpy()
            x = list(x)
            if frames and overlap:
                if join == "xfade":
                    for k in range(overlap):
                        wgt = (k + 1) / (overlap + 1)
                        frames[-overlap + k] = (frames[-overlap + k].astype(np.float32) * (1 - wgt)
                                                + x[k].astype(np.float32) * wgt).round().astype(np.uint8)
                x = x[overlap:]
            frames.extend(x)
            print(f"variant {vi} {var}: chunk {ci + 1}/{len(plan)} ({length} frames) in {time.time() - t1:.1f}s",
                  flush=True)
        print(f"variant {vi}: render {len(frames)} frames in {time.time() - t_r:.1f}s "
              f"on {torch.cuda.get_device_name(0)}")
        frames = [frames[0]] + [color_transfer(f, frames[0]) for f in frames[1:]]  # as save_videos_grid does
        raw, out = f"{work}/raw{vi}.mp4", f"{work}/out{vi}.mp4"
        imageio.mimwrite(raw, frames, fps=fps, codec="libx264", quality=8, macro_block_size=16)
        fs = max(28, sh // 12)
        draw = (f"drawtext=fontfile={FONT}:text='{LABEL}':fontcolor=white:fontsize={fs}:box=1:"
                f"boxcolor=red@0.85:boxborderw={fs // 3}:x=w-tw-{fs // 2}:y={fs // 2}")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", raw, "-i", wav_path, "-vf", draw,
                        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", out], check=True)
        results.append(open(out, "rb").read())
    print(f"total {time.time() - t_all:.1f}s")
    return results


@app.local_entrypoint()
def main(image: str, audio: str, out: str = "runs/video_family.mp4", size: int = 512, chunk: int = 113,
         seed: int = 43, prompt: str = "", preset: str = "", variants: str = "8:5:0:continue",
         start: float = 0.0, dur: float = 0.0):
    """--variants "steps:acfg:teacache[:join],..." e.g. "8:3:1:restart,8:5:0:continue" (several -> out_v0.mp4 ...)."""
    import sys
    from pathlib import Path

    if preset:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from deepfake_presets import PRESETS
        prompt = prompt or PRESETS[preset]["video_prompt"]
    prompt = prompt or "A young Korean man is talking anxiously to the camera on a phone video call."
    vs = []
    for v in variants.split(","):
        f = v.split(":")
        vs.append({"steps": int(f[0]), "acfg": float(f[1]), "teacache": f[2] == "1",
                   "join": f[3] if len(f) > 3 else "continue"})
    res = render.remote(Path(image).read_bytes(), Path(audio).read_bytes(), prompt, size, vs, chunk, seed,
                        start, dur)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    for i, data in enumerate(res):
        p = Path(out) if len(res) == 1 else Path(out).with_name(f"{Path(out).stem}_v{i}{Path(out).suffix}")
        p.write_bytes(data)
        print("saved", p, len(data), "bytes", vs[i])
