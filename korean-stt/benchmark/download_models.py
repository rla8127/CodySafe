from pathlib import Path
import json
from huggingface_hub import HfApi,snapshot_download
root=Path(__file__).resolve().parent
repos=[('qwen06','Qwen/Qwen3-ASR-0.6B'),('qwen17','Qwen/Qwen3-ASR-1.7B'),('whisper_turbo','dropbox-dash/faster-whisper-large-v3-turbo'),('whisper_large','Systran/faster-whisper-large-v3')]
provenance=json.loads((root/'model_provenance.json').read_text()) if (root/'model_provenance.json').exists() else {}
for name,repo in repos:
 revision=provenance.get(name,{}).get('revision') or HfApi().model_info(repo).sha
 print('Downloading',name,revision,flush=True)
 target=root/'models'/name
 snapshot_download(repo,revision=revision,local_dir=target,allow_patterns=['*.safetensors','*.json','merges.txt','model.bin'],max_workers=2)
 provenance[name]={**provenance.get(name,{}),'repo':repo,'revision':revision,'path':str(target)}
 (root/'model_provenance.json').write_text(json.dumps(provenance,indent=2))
 print('Ready',name,flush=True)
