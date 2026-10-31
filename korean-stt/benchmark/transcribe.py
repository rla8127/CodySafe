"""Run any installed model once. Temporarily stops the resident API to save RAM."""
import argparse,json,subprocess,time
from pathlib import Path
from evaluate import ROOT,MODELS,decode_audio

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('model',choices=MODELS)
 p.add_argument('audio',type=Path)
 args=p.parse_args()
 if not args.audio.is_file():raise SystemExit('Audio file not found')
 active=subprocess.run(['systemctl','--user','is-active','--quiet','korean-stt']).returncode==0
 try:
  if active:subprocess.run(['systemctl','--user','stop','korean-stt'],check=True)
  started=time.perf_counter()
  if args.model.startswith('qwen'):
   import torch
   from qwen_asr import Qwen3ASRModel
   torch.set_num_threads(2)
   model=Qwen3ASRModel.from_pretrained(str(ROOT/'models'/args.model),dtype=torch.bfloat16,device_map='cpu',attn_implementation='sdpa',max_inference_batch_size=1,max_new_tokens=512,local_files_only=True)
   if args.model=='qwen17':
    from quant_cpu import quantize_linears
    quantize_linears(model.model)
   loaded=time.perf_counter()
   text=model.transcribe(audio=str(args.audio),language='Korean')[0].text
   segments=[]
  else:
   from faster_whisper import WhisperModel
   path=ROOT.parent/'models/komix-medium-int8' if args.model=='komix' else ROOT/'models'/args.model
   model=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
   loaded=time.perf_counter()
   output,info=model.transcribe(decode_audio(args.audio),language='ko',beam_size=5,vad_filter=True,vad_parameters={'min_silence_duration_ms':500},condition_on_previous_text=False)
   segments=[{'start':s.start,'end':s.end,'text':s.text.strip()} for s in output]
   text=' '.join(s['text'] for s in segments)
  finished=time.perf_counter()
  result={'model':args.model,'audio':str(args.audio.resolve()),'text':text,'segments':segments,'load_seconds':loaded-started,'inference_seconds':finished-loaded}
  target=args.audio.with_name(args.audio.stem+'.'+args.model+'.json')
  target.write_text(json.dumps(result,ensure_ascii=False,indent=2))
  print(json.dumps(result,ensure_ascii=False,indent=2))
 finally:
  # Release weights before restarting the API; the process exits after this.
  if 'model' in locals():
   del model
   import gc
   gc.collect()
  if active:subprocess.run(['systemctl','--user','start','korean-stt'])
