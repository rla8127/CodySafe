"""Reproducible sequential CPU benchmark; scores only the predeclared Polly set."""
import argparse, json, os, re, resource, subprocess, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ENV={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2'}
MODELS=['komix','whisper_turbo','whisper_large','qwen06','qwen17']


def decode_audio(path):
    import av,numpy as np
    with av.open(str(path)) as source:
        resampler=av.AudioResampler(format='s16',layout='mono',rate=16000)
        pieces=[chunk.to_ndarray().flatten() for frame in source.decode(audio=0) for chunk in resampler.resample(frame)]
        pieces.extend(chunk.to_ndarray().flatten() for chunk in resampler.resample(None))
    return np.concatenate(pieces).astype(np.float32)/32768.0


def main(name):
    rows=json.loads((ROOT/'manifest.json').read_text())
    # Real user recording has no ground truth: transcribe separately, exclude from CER/WER.
    rows.append({'id':'user_recording','file':'../박철민검사.mp3','duration':44.4343125,'condition':'real_unscored','reference':None})
    outfile=ROOT/'results'/f'{name}.jsonl'
    outfile.parent.mkdir(exist_ok=True)
    completed={r['id'] for r in map(json.loads,outfile.read_text().splitlines()) if r.get('status')=='ok'} if outfile.exists() else set()
    if all(row['id'] in completed for row in rows):
        print(name,'already complete',flush=True)
        return
    runtime='faster-whisper 1.2.1 / CTranslate2 4.8.4 INT8' if not name.startswith('qwen') else 'Qwen official Python runtime (configured below)'
    if not name.startswith('qwen'):
        from faster_whisper import WhisperModel
        import numpy as np
        path=ROOT.parent/'models/komix-medium-int8' if name=='komix' else ROOT/'models'/name
        start=time.perf_counter()
        model=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
        load=time.perf_counter()-start
        list(model.transcribe(np.zeros(16000,dtype=np.float32),language='ko',vad_filter=True)[0])
    else:
        import torch
        from qwen_asr import Qwen3ASRModel
        torch.set_num_threads(2)
        start=time.perf_counter()
        model=Qwen3ASRModel.from_pretrained(str(ROOT/'models'/name),dtype=torch.bfloat16,device_map='cpu',attn_implementation='sdpa',max_inference_batch_size=1,max_new_tokens=256,local_files_only=True)
        if name=='qwen17':
            from quant_cpu import quantize_linears
            print('Quantized linear modules:',quantize_linears(model.model),flush=True)
        load=time.perf_counter()-start
        # Warm up decoding/feature extraction on an existing input; not scored.
        model.transcribe(audio=str(ROOT/rows[0]['file']),language='Korean')
        runtime='Qwen official qwen-asr 0.0.6 / Transformers 4.57.6 / PyTorch CPU BF16 SDPA' + (' + dynamic INT8 Linear adapter' if name=='qwen17' else '')
    for row in rows:
        if row['id'] in completed:continue
        start=time.perf_counter()
        result={**row,'model':name,'runtime':runtime,'status':'ok'}
        try:
            path=ROOT/row['file']
            if name.startswith('qwen'):
                output=model.transcribe(audio=str(path),language='Korean')
                result['text']=output[0].text
                result['inference_seconds']=time.perf_counter()-start
                result['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
                result['load_seconds']=load
                result['runtime']=runtime
            else:
                segments,info=model.transcribe(decode_audio(path),language='ko',task='transcribe',beam_size=5,vad_filter=True,vad_parameters={'min_silence_duration_ms':500},condition_on_previous_text=False)
                result['text']=' '.join(s.text.strip() for s in segments)
                result['inference_seconds']=time.perf_counter()-start
                result['load_seconds']=load
                result['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
            result['wall_seconds']=time.perf_counter()-start
            result['rtf']=result['inference_seconds']/row['duration']
        except Exception as exc:
            result.update(status='error',error=str(exc),wall_seconds=time.perf_counter()-start)
        with outfile.open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
        print(name,row['id'],result['status'],round(result['wall_seconds'],2),result.get('text',result.get('error','')),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',choices=MODELS);args=p.parse_args()
    if args.model:main(args.model)
    else:
        try:
            subprocess.run(['systemctl','--user','stop','korean-stt'],check=True)
            for name in MODELS:
                print('START_MODEL',name,flush=True)
                try:
                    subprocess.run([sys.executable,'-u',__file__,'--model',name],env=ENV,check=True,timeout=3600)
                except Exception:
                    traceback.print_exc()
        finally:
            subprocess.run(['systemctl','--user','start','korean-stt'],check=True)
