import io
import json
import re
import wave
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
key = next(x.split('=', 1)[1] for x in (ROOT / '.env').read_text().splitlines() if x.startswith('STT_API_KEY='))
headers = {'Authorization': f'Bearer {key}'}
client = httpx.Client(base_url='http://127.0.0.1:8000', timeout=900)
health = client.get('/health')
assert health.status_code == 200
expected_model = next(x.split('=', 1)[1] for x in (ROOT / '.env').read_text().splitlines() if x.startswith('STT_MODEL_ID='))
assert health.json()['model'] == expected_model, health.text
assert health.json()['device'] == 'cpu' and health.json()['compute_type'] == 'int8'
old_model = client.post('/v1/audio/transcriptions', headers=headers, data={'model': 'seastar105/whisper-medium-komixv2'}, files={'file': ('test.wav', b'bad')})
assert old_model.status_code == 400 and old_model.json()['detail'] == 'Unknown model; use korean-stt'
assert client.post('/v1/audio/transcriptions', files={'file': ('bad.mp3', b'bad')}).status_code == 401
assert client.post('/v1/audio/transcriptions', headers=headers, files={'file': ('bad.mp3', b'bad')}).status_code == 400
assert client.post('/v1/audio/transcriptions', headers=headers, files={'file': ('empty.mp3', b'')}).status_code == 400
assert client.post('/v1/audio/transcriptions', headers=headers, data={'language': 'en'}, files={'file': ('bad.mp3', b'bad')}).status_code == 400
silence = io.BytesIO()
with wave.open(silence, 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(b'\0' * 32000)
r = client.post('/v1/audio/transcriptions', headers=headers, files={'file': ('silence.wav', silence.getvalue())})
assert r.status_code == 200, r.text
assert r.json()['text'] == '', r.text
print('PASS: health, authentication, invalid/empty audio, language validation, silence')

# Exercise MP3 decoding using the same real Korean recording.
import av
with av.open(str(ROOT / 'samples/fleurs-ko-0.wav')) as source:
    with av.open(str(ROOT / 'samples/fleurs-ko-0.mp3'), 'w') as dest:
        output = dest.add_stream('libmp3lame', rate=16000)
        output.layout = 'mono'
        for frame in source.decode(audio=0):
            for packet in output.encode(frame):
                dest.mux(packet)
        for packet in output.encode(None):
            dest.mux(packet)
with (ROOT / 'samples/fleurs-ko-0.mp3').open('rb') as audio:
    response = client.post('/v1/audio/transcriptions', headers=headers,
                           data={'model': 'korean-stt'}, files={'file': ('sample.mp3', audio, 'audio/mpeg')})
assert response.status_code == 200, response.text
result = response.json()
assert result['model'] == expected_model, result
reference = json.loads((ROOT / 'samples/fleurs-ko-0.json').read_text())['reference']
def normalize(text):
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text).lower()
def distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(row[-1] + 1, prev[j] + 1, prev[j-1] + (x != y)))
        prev = row
    return prev[-1]
result['reference'] = reference
result['normalized_cer'] = distance(normalize(reference), normalize(result['text'])) / len(normalize(reference))
result['evaluation_note'] = 'Single FLEURS test sample; punctuation/whitespace stripped, digits retained. Not representative of general accuracy.'
(ROOT / 'samples/result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
assert result['text'], result
print(json.dumps(result, ensure_ascii=False, indent=2))
