from pathlib import Path
import csv,json,re,statistics,unicodedata,zipfile
ROOT=Path(__file__).resolve().parent
LABELS={'komix':'Whisper Medium 한국어 특화 (INT8)','whisper_turbo':'Whisper large-v3-turbo (INT8)','whisper_large':'Whisper large-v3 (INT8)','qwen06':'Qwen3-ASR 0.6B (BF16)','qwen17':'Qwen3-ASR 1.7B (실험용 Linear 동적 INT8)'}

def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFC',text).lower() if c.isalnum())

def number_ko(n):
    if n==0:return '영'
    digits='일이삼사오육칠팔구'; small=['','십','백','천'];large=['','만','억','조'];parts=[];group=0
    while n:
        v=n%10000;n//=10000;seg=''
        for i in range(4):
            d=v%10;v//=10
            if d:seg=(('' if d==1 and i else digits[d-1])+small[i])+seg
        if seg:parts.insert(0,seg+large[group])
        group+=1
    return ''.join(parts)

def numeric_norm(text):
    text=unicodedata.normalize('NFC',text).lower()
    text=re.sub(r'(?<=\d),(?=\d)','',text)
    text=re.sub(r'3\s*시','세 시',text)
    text=re.sub(r'\d+',lambda m:number_ko(int(m[0])),text)
    return norm(text)

def distance(a,b):
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        row=[i]
        for j,y in enumerate(b,1):row.append(min(row[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=row
    return prev[-1]

def score(rows,normalizer=norm):
    refs=[normalizer(r['reference']) for r in rows]
    return sum(distance(a,normalizer(r['text'])) for a,r in zip(refs,rows))/sum(map(len,refs)) if rows else None

if __name__=='__main__':
 summaries=[];allrows=[];real=[]
 for path in sorted((ROOT/'results').glob('*.jsonl')):
    # Last result per sample wins for interrupted/retried runs.
    rows=list({r['id']:r for r in map(json.loads,path.read_text().splitlines())}.values())
    successful=[r for r in rows if r['status']=='ok' and r['reference'] is not None]
    expected={r['id'] for r in json.loads((ROOT/'manifest.json').read_text())}
    if {r['id'] for r in successful} != expected:continue
    for row in successful:
        row['cer']=distance(norm(row['reference']),norm(row['text']))/len(norm(row['reference']))
        row['numeric_cer']=distance(numeric_norm(row['reference']),numeric_norm(row['text']))/len(numeric_norm(row['reference']))
    allrows.extend(successful)
    real.extend(r for r in rows if r['reference'] is None and r['status']=='ok')
    clean=[r for r in successful if r['condition']=='clean'];noisy=[r for r in successful if r['condition']!='clean']
    seconds=sum(r['inference_seconds'] for r in successful);duration=sum(r['duration'] for r in successful)
    summary={'model':path.stem,'samples':len(successful),'cer':score(successful),'numeric_cer':score(successful,numeric_norm),'clean_cer':score(clean),'noisy_cer':score(noisy),'inference_seconds':seconds,'audio_seconds':duration,'rtf':seconds/duration,'wall_seconds':sum(r['wall_seconds'] for r in successful),'peak_rss_mib':max(r['peak_rss_mib'] or 0 for r in successful),'model_load_seconds':max(r.get('load_seconds') or 0 for r in successful), 'failures':sum(r['status']!='ok' for r in rows), 'wer':sum(distance(re.findall(r'[\w]+',r['reference'].lower()),re.findall(r'[\w]+',r['text'].lower())) for r in successful)/sum(len(re.findall(r'[\w]+',r['reference'].lower())) for r in successful)}
    summaries.append(summary)
 summaries.sort(key=lambda r:r['cer'])
 (ROOT/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2))
 fields=['model','id','condition','voice','category','reference','text','cer','numeric_cer','runtime','load_seconds','duration','inference_seconds','wall_seconds','rtf','peak_rss_mib']
 with (ROOT/'per_sample.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(allrows)
 manifest=json.loads((ROOT/'manifest.json').read_text())
 lines=['# 한국어 STT 모델 비교 평가','', '작성일: 2026-11-01 (한국 시간). 현재 EC2의 CPU 2 vCPU / RAM 3.7 GiB / GPU 없음 / swap 4 GiB에서 순차 실행.','',
 '## 데이터와 평가 조건','',f'- Amazon Polly 서울 리전, Seoyeon·Jihye neural 목소리. 직접 작성한 대본 8개 × 목소리 2개 = 깨끗한 음성 16개.',
 '- 이 중 보이스피싱 예방·이름/주소 문장 각각에 두 목소리로 전화 대역(300–3400 Hz), 8 kHz 왕복 변환, 백색 잡음 10 dB SNR 적용: 4개 추가.',
 f'- 합계 {len(manifest)}개, {sum(r["duration"] for r in manifest):.2f}초. WAV 16 kHz, mono, 16-bit PCM. 난수 seed=20261101.',
 '- 대본과 변형 조건을 추론 전에 고정했으며 평가 음성을 학습·튜닝에 사용하지 않았습니다. 모델에 정답 대본이나 용어 힌트를 주지 않았습니다.',
 '- 기존 API를 중지하고 모델을 하나씩 실행했습니다. 모든 런타임의 CPU 스레드를 2개로 제한했습니다.',
 '- Whisper: faster-whisper/CTranslate2, INT8, beam=5, ko 고정, VAD on, 이전 문맥 조건 off. 로딩 후 무음 1초 warmup. 추론 시간은 해독·VAD·전사를 포함하고 모델 초기 로딩은 제외합니다.',
 '- Qwen: 공식 qwen-asr 0.0.6 / Transformers 4.57.6 / PyTorch CPU BF16 / SDPA. Korean 고정, batch=1, max_new_tokens=256, prompt 없음. 첫 평가 음성으로 1회 사전 구동한 출력은 점수에 넣지 않았습니다. 0.6B는 BF16이며, 1.7B는 메모리 제약으로 모든 Linear에 PyTorch 동적 INT8을 적용하고 나머지는 BF16을 유지했습니다. 입력/출력 형변환 어댑터는 quant_cpu.py에 포함됩니다.',
 '- 모든 모델은 한 프로세스에서 로딩 후 파일을 하나씩 전사합니다. 모델 초기 로딩과 warmup은 추론 시간에서 제외합니다. 런타임·정밀도·탐색 방법이 다르므로 속도는 이 배포 조합의 성능이지 모델 구조만의 비교가 아닙니다.',
 '- 주 지표 CER: NFC·소문자 처리 후 공백과 문장부호를 제거하고 숫자는 그대로 유지한 문자 단위 편집 거리 / 정답 문자 수. 전체 CER는 문자 수로 가중 합산합니다.',
 '- 보조 숫자 정규화 CER: 쉼표로 구분된 숫자를 합친 뒤 정수를 한글 수사로 변환하고, 3시를 세 시로 통일합니다. 표기 차이를 일부 줄이는 지표이며 모든 발음 동치나 의미 정확도를 보장하지 않습니다.',
 '- summary.json의 WER는 소문자 처리·문장부호 제거 후 공백 단위 토큰으로 계산합니다. 한국어 띄어쓰기 차이에 민감해 순위의 주 지표로 쓰지 않습니다.',
 '- RTF = 순수 추론 시간 합 / 음성 길이 합. 작을수록 빠르며 1 미만이면 해당 파일 처리량이 실시간보다 빠릅니다. 반복 측정·동시 요청 부하 테스트는 하지 않았습니다. 메모리는 프로세스 최대 RSS이며 swap·파일 캐시를 모두 표현하지 않습니다.','',
 '## 결과','', '| 모델 | 완료 | CER ↓ | 숫자 정규화 CER ↓ | 깨끗한 음성 CER | 전화+잡음 CER | RTF ↓ | 최대 RSS |', '|---|---:|---:|---:|---:|---:|---:|---:|']
 for s in summaries:
    lines.append(f'| {LABELS[s["model"]]} | {s["samples"]}/20 | {s["cer"]:.2%} | {s["numeric_cer"]:.2%} | {s["clean_cer"]:.2%} | {s["noisy_cer"]:.2%} | {s["rtf"]:.3f} | {s["peak_rss_mib"]:.0f} MiB |')
 if summaries:
    best_strict=min(summaries,key=lambda s:s['cer'])
    best_numeric=min(s['numeric_cer'] for s in summaries)
    numeric_names=' · '.join(LABELS[s['model']] for s in summaries if abs(s['numeric_cer']-best_numeric)<1e-10)
    fastest=min(summaries,key=lambda s:s['rtf'])
    lines+=['','## 이 평가에서 확인한 선택 기준','',f"- 원문 표기 기준 CER 최저: {LABELS[best_strict['model']]} ({best_strict['cer']:.2%}).",f"- 숫자 표기를 통일한 보조 CER 최저: {numeric_names} ({best_numeric:.2%}).",f"- 파일 처리량이 가장 빠른 설정: {LABELS[fastest['model']]} (RTF {fastest['rtf']:.3f}).",'- 숫자 표현 방식과 사용 목적에 따라 선택이 달라집니다. 작은 점수 차이에 대한 통계적 유의성은 확인하지 않았습니다.']
 lines+=['','## 해석과 한계','', '- Qwen 1.7B의 본 실험용 동적 INT8 설정에서는 문장 일부 누락이 관찰됐고 실제 MP3에서는 같은 문장을 반복했습니다. 누락 사례는 Seoyeon 기술 문장의 두 번째 문장입니다. 이 서버의 서비스용 설정으로는 권장하지 않습니다. 이 설정의 점수는 원본 1.7B 품질과 구분해야 합니다. 단순 Linear 수치 검증만으로 원본과의 전사 동등성을 보장하지 않습니다.', '- Qwen 1.7B 원본 BF16은 이 서버에서 warmup만 2분 이상 걸리고 디스크 읽기 대기가 커서 중단했습니다. 최종 표는 CPU 배포용 동적 INT8 변형의 결과입니다. 원본 BF16의 정확도 점수로 해석하면 안 됩니다.',
 '- 이 결과로 한국어 전체에서 가장 좋은 모델을 결정할 수 없습니다. 8개 대본, 두 합성 목소리, 단일 서버의 소규모 점검입니다. 같은 대본의 목소리/변형은 독립적인 새 문장이 아닙니다.',
 '- 합성 음성은 실제 통화의 억양·중첩 발화·압축 잡음·사투리를 충분히 반영하지 않습니다. 전화+잡음 조건도 실제 통신망 코덱을 재현한 것은 아닙니다.',
 '- 입력에는 수사를 한글로 쓴 문장이 있으므로 숫자 표기만 다른 정답도 주 CER에서 오류로 계산될 수 있습니다. 보조 숫자 정규화 CER와 샘플별 결과를 함께 확인하세요.',
 '- 실제 업무용 모델 선택에는 별도 사람이 확인한 통화 정답 대본과 충분한 실제 음성으로 추가 검증이 필요합니다.',
 '- Amazon Transcribe는 계정 서비스 구독 오류로 이번 순위에 포함하지 않았습니다. Polly와 Transcribe의 이용 가능 여부는 다릅니다.','',
 '## 사용자가 제공한 실제 녹음 (정답 없음)','', '박철민검사.mp3는 44.43초이며 아래 결과는 정량 점수에서 제외했습니다. 전사문 간 차이만으로 어느 것이 정답인지 단정하지 않습니다.','']
 for r in real:
    lines += [f'### {LABELS[r["model"]]}', '',f'추론 {r["inference_seconds"]:.2f}초 / 전체 {r["wall_seconds"]:.2f}초', '',r['text'],'']
 lines+=['## 재현과 파일','',
 '`manifest.json`: 정답·음성 설정·SHA256. `dataset/`: WAV. `model_provenance.json`: 모델 원본 커밋. `results/*.jsonl`: 원시 전사·시간·메모리. `per_sample.csv`: 샘플별 오류. `summary.json`: 집계.',
 '', '```bash','cd /home/ubuntu/korean-stt/benchmark','../.venv/bin/python prepare_dataset.py','../.venv/bin/python evaluate.py','../.venv/bin/python score.py','```','',
 '기존 결과가 있으면 evaluate.py가 완료 샘플을 건너뜁니다. 새로 측정하려면 results 디렉터리를 따로 보관한 뒤 다시 실행하세요.','',
 '## 출처','',
 '- https://huggingface.co/seastar105/whisper-medium-komixv2',
 '- https://huggingface.co/Systran/faster-whisper-large-v3',
 '- https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo',
 '- https://huggingface.co/Qwen/Qwen3-ASR-0.6B',
 '- https://huggingface.co/Qwen/Qwen3-ASR-1.7B',
 '- https://github.com/QwenLM/Qwen3-ASR',
 '- https://docs.aws.amazon.com/polly/latest/dg/neural-voices.html','']
 (ROOT/'internal').mkdir(exist_ok=True)
 (ROOT/'internal/REPORT.md').write_text('\n'.join(lines))
 with zipfile.ZipFile(ROOT/'korean-stt-evaluation.zip','w',zipfile.ZIP_DEFLATED) as z:
    files=[ROOT/'internal/REPORT.md',ROOT/'manifest.json',ROOT/'summary.json',ROOT/'per_sample.csv',ROOT/'model_provenance.json',ROOT/'prepare_dataset.py',ROOT/'evaluate.py',ROOT/'score.py',ROOT/'environment.json',ROOT/'requirements.lock.txt',ROOT/'README.md',ROOT/'transcribe.py',ROOT/'download_models.py',ROOT/'quant_cpu.py']
    files+=list((ROOT/'dataset').glob('*.wav'))+list((ROOT/'results').glob('*'))
    for path in files:
        if path.exists():z.write(path,str(path.relative_to(ROOT)))
    # Attach only current, non-secret application documentation and evidence.
    extras=[]
    for path in sorted((ROOT.parent/'docs').glob('*')):
        if path.is_file() and path.suffix in ('.md','.docx'):extras.append((path,'docs/'+path.name))
    for path in sorted((ROOT.parent/'deployment').glob('*.json')):extras.append((path,'deployment/'+path.name))
    for path in sorted((ROOT.parent/'scripts').glob('*.py')):extras.append((path,'scripts/'+path.name))
    for name in ['app.py','README.md','requirements.lock.txt','convert_model.py','tests/check_api.py']:
        path=ROOT.parent/name
        if path.exists():extras.append((path,'application/'+name))
    for path,arcname in extras:z.write(path,arcname)
 print(json.dumps(summaries,ensure_ascii=False,indent=2))
