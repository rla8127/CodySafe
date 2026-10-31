"""Collect allowlisted, non-secret configuration and local inference evidence."""
import ast,datetime,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while chunk:=f.read(8*1024*1024):h.update(chunk)
 return h.hexdigest()
source=ROOT/'app.py';tree=ast.parse(source.read_text())
call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='WhisperModel')
args={k.arg:ast.literal_eval(k.value) for k in call.keywords}
assert args['device']=='cpu' and args['compute_type']=='int8' and args['local_files_only'] is True
pid=int(subprocess.check_output(['systemctl','--user','show','korean-stt','--property','MainPID','--value'],text=True).strip())
allowed={'STT_MODEL_PATH','STT_MODEL_ID','HF_HUB_OFFLINE','OMP_NUM_THREADS'}
env={}
for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
 key,sep,value=item.partition(b'=')
 if sep and key.decode() in allowed:env[key.decode()]=value.decode()
model_dir=Path(env['STT_MODEL_PATH'])
artifacts=[]
for name in ['model.bin','config.json','tokenizer.json','preprocessor_config.json']:
 p=model_dir/name
 artifacts.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':digest(p)})
offline=json.loads((ROOT/'deployment/offline-inference-test.json').read_text())
assert offline['status']=='passed' and offline['interfaces']==['lo'] and offline['loopback_up'] is False
with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5) as r:health=json.load(r)
assert health['model']=='openai/whisper-large-v3-turbo'
record={'recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),'deployment':'Self-hosted local inference on EC2, exposed through own REST API','production_health':health,'service_pid':pid,'runtime_environment_allowlist':env,'model_loader':{'source':'app.py','source_sha256':digest(source),'line':call.lineno,'arguments':args},'model_artifacts':artifacts,'service_unit':Path('/home/ubuntu/.config/systemd/user/korean-stt.service').read_text(),'offline_test':offline,'offline_test_script':{'path':'scripts/verify_local_inference.py','sha256':digest(ROOT/'scripts/verify_local_inference.py')},'scope':'Source/configuration evidence and a separate network-isolated execution of the same weights. Not a complete packet audit of the production API.','secrets':'No API keys or AWS credentials included.'}
(ROOT/'deployment/local-inference-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('Evidence collected:',len(artifacts),'hashed model artifacts; isolated offline transcription passed')
