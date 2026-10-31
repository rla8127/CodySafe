import hmac
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import av
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from faster_whisper import WhisperModel
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent
MODEL_PATH = os.getenv('STT_MODEL_PATH', str(ROOT / 'benchmark/models/whisper_turbo'))
MODEL_ID = os.getenv('STT_MODEL_ID', 'openai/whisper-large-v3-turbo')
API_KEY = os.environ['STT_API_KEY']
MAX_BYTES = 50 * 1024 * 1024
MAX_SECONDS = 300
busy = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    app.state.model = await run_in_threadpool(
        lambda: WhisperModel(MODEL_PATH, device='cpu', compute_type='int8',
                             cpu_threads=2, num_workers=1, local_files_only=True)
    )
    yield


app = FastAPI(title='Korean STT', version='1.1.0', lifespan=lifespan)


def authenticate(authorization: str = Header(default='')):
    if not hmac.compare_digest(authorization, 'Bearer ' + API_KEY):
        raise HTTPException(401, 'Invalid bearer token')


@app.get('/health')
def health():
    return {'status': 'ok', 'model': MODEL_ID,
            'device': 'cpu', 'compute_type': 'int8', 'busy': busy.locked()}


def decode(path):
    chunks = []
    count = 0
    try:
        with av.open(path) as container:
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    data = converted.to_ndarray().flatten()
                    count += data.size
                    if count > MAX_SECONDS * 16000:
                        raise HTTPException(413, f'Audio exceeds {MAX_SECONDS} seconds; split into shorter files')
                    chunks.append(data)
            for converted in resampler.resample(None):
                data = converted.to_ndarray().flatten()
                count += data.size
                if count > MAX_SECONDS * 16000:
                    raise HTTPException(413, 'Audio too long')
                chunks.append(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, 'Cannot decode audio') from exc
    if not chunks:
        raise HTTPException(400, 'Empty audio')
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe(path, prompt):
    started = time.perf_counter()
    audio = decode(path)
    segments, info = app.state.model.transcribe(
        audio, language='ko', task='transcribe', beam_size=5,
        vad_filter=True, vad_parameters={'min_silence_duration_ms': 500},
        condition_on_previous_text=False, initial_prompt=prompt or None,
    )
    result = [{'id': s.id, 'start': s.start, 'end': s.end, 'text': s.text.strip()} for s in segments]
    elapsed = time.perf_counter() - started
    return {'text': ' '.join(s['text'] for s in result), 'language': 'ko',
            'duration': info.duration, 'processing_seconds': round(elapsed, 3),
            'rtf': round(elapsed / info.duration, 3) if info.duration else None,
            'model': MODEL_ID, 'segments': result}


@app.post('/v1/audio/transcriptions', dependencies=[Depends(authenticate)])
async def transcription(file: UploadFile = File(...), model: str = Form('korean-stt'),
                        language: str = Form('ko'), prompt: str = Form(''),
                        response_format: str = Form('json')):
    if language != 'ko':
        raise HTTPException(400, 'This endpoint supports Korean (ko)')
    if model not in ('korean-stt', 'whisper-1', 'whisper-large-v3-turbo', MODEL_ID):
        raise HTTPException(400, 'Unknown model; use korean-stt')
    if response_format not in ('json', 'verbose_json', 'text'):
        raise HTTPException(400, 'Supported formats: json, verbose_json, text')
    if len(prompt) > 2000:
        raise HTTPException(400, 'Prompt too long')
    if not busy.acquire(blocking=False):
        raise HTTPException(429, 'Server busy; retry after current transcription', headers={'Retry-After': '30'})
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='korean-stt-', suffix='.audio', delete=False) as temp:
            path = temp.name
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'File exceeds 50 MiB')
                temp.write(chunk)
        if size == 0:
            raise HTTPException(400, 'Empty file')
        result = await run_in_threadpool(transcribe, path, prompt)
        return PlainTextResponse(result['text']) if response_format == 'text' else result
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
        await file.close()
        busy.release()
