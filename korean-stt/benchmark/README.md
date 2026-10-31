# 한국어 STT 비교 실험

설치 모델: komix, whisper_turbo, whisper_large, qwen06, qwen17.
Qwen 0.6B는 BF16, Qwen 1.7B는 메모리를 줄이기 위해 Linear 동적 INT8 + 나머지 BF16을 사용합니다.
현재 서버는 CPU 2 vCPU / RAM 3.7 GiB라 여러 모델을 동시에 상주시킬 수 없어 하나씩 로딩합니다.
2026-11-01 사용자 요청으로 포트 8000 API의 기본 모델을 whisper_turbo로 전환했으며, 추가 모델은 아래 명령으로 선택 실행합니다.

```bash
cd /home/ubuntu/korean-stt
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python benchmark/transcribe.py qwen06 박철민검사.mp3
```

메모리를 확보하기 위해 명령 실행 중 기존 API를 일시 중지하고 완료 후 다시 시작합니다.
결과는 입력 파일 옆에 `.모델명.json`으로 저장됩니다. Qwen은 별도 forced aligner 없이 전사하므로 구간 타임스탬프는 비어 있습니다.
전체 평가 실행 중에는 다른 모델 명령을 함께 실행하지 마세요.

최종 문서는 상위 `docs/`의 Word·Markdown 한 종으로 관리합니다.
`REPORT.html`은 음성을 포함한 부록이며, `internal/REPORT.md`는 HTML 생성을 위한 내부 원본입니다.
`per_sample.csv`는 샘플별 결과, `korean-stt-evaluation.zip`은 보고서·데이터·실행 코드를 묶은 파일입니다.
평가 데이터 생성에는 Amazon Polly API 사용료가 발생할 수 있으며 IAM `polly:SynthesizeSpeech` 권한이 필요합니다.
모델 가중치는 ZIP에 포함하지 않습니다. `model_provenance.json`에 원본 저장소와 커밋이 기록되어 있습니다.

재현:

```bash
cd /home/ubuntu/korean-stt/benchmark
../.venv/bin/python prepare_dataset.py
../.venv/bin/python download_models.py
../.venv/bin/python evaluate.py
../.venv/bin/python score.py
../.venv/bin/python render_report.py
../.venv/bin/python ../scripts/build_document.py
```

환경 버전은 requirements.lock.txt, environment.json 참조.
PyTorch는 https://download.pytorch.org/whl/cpu 에서 CPU wheel을 설치합니다.
원본 한국어 특화 모델의 INT8 변환은 상위 디렉터리 convert_model.py 참조.

미사용 Amazon Transcribe 실험 코드와 당시 오류 기록은 `optional/amazon_transcribe/`에 보관합니다. 운영 STT API에서 이 코드를 호출하지 않습니다.
