"""Run under sudo unshare --net; generates no network connections or API calls."""
import json,os,time,socket,fcntl,struct
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['OMP_NUM_THREADS']='2'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'benchmark'))
from evaluate import decode_audio
from faster_whisper import WhisperModel

namespace=os.readlink('/proc/self/ns/net')
init_namespace=os.readlink('/proc/1/ns/net')
assert namespace != init_namespace, 'Must execute in a separate network namespace'
interfaces=[name for _,name in socket.if_nameindex()]
assert interfaces==['lo'], interfaces
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
    flags=struct.unpack('H',fcntl.ioctl(probe,0x8913,struct.pack('256s',b'lo'))[16:18])[0]
assert not flags & 1, 'Loopback must be down'
started=time.perf_counter()
model=WhisperModel(str(ROOT/'benchmark/models/whisper_turbo'),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
audio=decode_audio(ROOT/'benchmark/dataset/seoyeon_daily.wav')
segments,info=model.transcribe(audio,language='ko',beam_size=5,vad_filter=True,condition_on_previous_text=False)
text=' '.join(s.text.strip() for s in segments)
assert text
result={'status':'passed','model':'openai/whisper-large-v3-turbo','device':'cpu','compute_type':'int8','local_files_only':True,'network_namespace':namespace,'host_network_namespace':init_namespace,'interfaces':interfaces,'loopback_up':False,'audio':'benchmark/dataset/seoyeon_daily.wav','audio_seconds':info.duration,'text':text,'elapsed_including_load_seconds':round(time.perf_counter()-started,3),'scope':'Same local model weights executed directly in an isolated network namespace with no usable network interface. This validates offline inference capability; it is not a packet audit of the production API.'}
print(json.dumps(result,ensure_ascii=False,indent=2))
