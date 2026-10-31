import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parent / 'samples'
root.mkdir(exist_ok=True)
url = 'https://datasets-server.huggingface.co/rows?dataset=google%2Ffleurs&config=ko_kr&split=test&offset=0&length=1'
d = json.load(urllib.request.urlopen(url))
row = d['rows'][0]['row']
(root / 'fleurs-ko-0.json').write_text(json.dumps({'dataset': 'google/fleurs', 'config': 'ko_kr', 'split': 'test', 'row': 0, 'reference': row['raw_transcription']}, ensure_ascii=False, indent=2))
# Fetch a fresh signed link; do not persist its credentials.
with urllib.request.urlopen(row['audio'][0]['src']) as response:
    (root / 'fleurs-ko-0.wav').write_bytes(response.read())
print(row['raw_transcription'])
