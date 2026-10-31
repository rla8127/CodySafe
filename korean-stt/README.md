# 한국어 STT 서버

> 이 디렉터리는 CodySafe의 소스·문서 관리용 사본입니다. 실제 STT 서비스는 별도 운영 경로 `/home/ubuntu/korean-stt`에서 실행됩니다. 이 사본을 추가하면서 운영 서비스나 환경변수는 변경하지 않았습니다.
> 모델 가중치, 가상환경, 실제 `.env`, 원본 음성·전사 자료, 생성된 HTML·ZIP은 포함하지 않습니다. 관련 링크와 절대 경로는 STT 운영 서버를 기준으로 한 기록입니다.
> 별도 배포 시 `.env.example`을 참고해 환경변수를 설정하고, 가상환경 설치 및 모델 다운로드·평가 데이터 생성 후 실행하세요.

현재 모델은 **Whisper large-v3-turbo / CPU INT8**입니다.
공개 모델 가중치를 자체 EC2에서 직접 실행하며, 다른 서버는 이 서버의 REST API로 접속합니다.

## 문서 안내

- **최종 참고 문서:** [Word](docs/한국어_STT_모델_비교_평가_2026-11-01.docx) · [Markdown](docs/한국어_STT_모델_비교_평가_2026-11-01.md)
  — 모델 비교, 선정 이유, 운영 설정, 자체 호스팅·로컬 추론 근거를 한 문서에 통합했습니다.
- **음성 비교 부록:** [HTML](benchmark/REPORT.html) — 음성을 들으며 모델별 결과를 비교합니다.
- **제출·재현 자료:** [ZIP](benchmark/korean-stt-evaluation.zip) — 최신 문서, 로컬 추론 증빙, 데이터, 결과, 코드를 포함합니다. 모델 가중치와 인증 키는 포함하지 않습니다.
- 평가 재현·추가 모델 실행: [benchmark/README.md](benchmark/README.md)

## API 사용

- 전사: `POST http://3.38.144.231:8000/v1/audio/transcriptions`
- 상태 확인: `GET http://3.38.144.231:8000/health`
- API 명세: `http://3.38.144.231:8000/docs`
- 전사 요청에는 `Authorization: Bearer <STT_API_KEY>`가 필요합니다.

서버에 있는 토큰을 환경변수로 읽어 호출하는 예:

```bash
cd /home/ubuntu/korean-stt
set -a
source .env
set +a
curl http://3.38.144.231:8000/v1/audio/transcriptions \
  -H "Authorization: Bearer $STT_API_KEY" \
  -F model=whisper-large-v3-turbo -F language=ko \
  -F file=@/path/to/audio.mp3
```

다른 서버에서는 동일한 주소와 형식을 사용하고 `STT_API_KEY`를 해당 서버의 환경변수에 설정합니다.
응답에는 `text`, `segments`, `duration`, `processing_seconds`, `rtf`, `model`이 포함됩니다.
`response_format=text`로 전사문만 받을 수 있습니다. 요청당 50 MiB / 300초,
동시에 전사 1건을 처리하며 추가 요청은 429와 Retry-After를 반환합니다.
업로드 파일은 처리 후 삭제합니다. 파일 전사 방식이며 실시간 스트리밍은 지원하지 않습니다.

## 운영

```bash
systemctl --user status korean-stt
systemctl --user restart korean-stt
journalctl --user -u korean-stt -n 50 --no-pager
```

systemd와 linger로 부팅 시 자동 시작합니다. 바인딩은 `0.0.0.0:8000`입니다.
`.env`에는 토큰과 `STT_MODEL_PATH`, `STT_MODEL_ID`, 오프라인 모델 설정이 있습니다.
모델 파일은 `benchmark/models/whisper_turbo/`, 원본 커밋은 `benchmark/model_provenance.json` 참조.
전환 전 설정은 `backups/`에 보관합니다. 원본 사용자 음성과 전사 결과, 평가 데이터·모델은 유지합니다.

운영 검증은 `deployment/turbo-verification.json`, 공인 접속 설정은 `deployment/public-access.json`,
로컬 추론 근거는 `deployment/local-inference-evidence.json`에 저장되어 있습니다.
`HF_HUB_OFFLINE=1`과 `local_files_only=True`는 모델 파일 로딩 설정이며 자체 API 통신을 차단하는 설정은 아닙니다.

## 검증과 문서 갱신

```bash
.venv/bin/python tests/check_api.py
sudo unshare --net -- .venv/bin/python -B scripts/verify_local_inference.py
.venv/bin/python scripts/build_document.py
```

네트워크 격리 검증은 운영 API와 별도 프로세스에서 동일한 가중치를 직접 실행합니다.
문서 생성 원본은 `scripts/build_document.py`이며, `docs/`에는 최신 문서 한 종의 Word·Markdown만 유지합니다.
구버전·임시 자료 정리 내역은 `deployment/cleanup-record.json`에 있습니다.
