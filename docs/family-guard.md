# 사기탐지 가족보호 시스템

저장된 통화 녹음을 분석해 사기를 판정하고, 보이스피싱이 강하게 의심되면 가족에게 알립니다.

```
폰 폴더 → (presigned URL) S3 → Transcribe → Claude 판정
                                              ├ 보이스피싱: Hybrid RAG + Reranker로 유형 확인, 가족 알림
                                              ├ 다른 사기: 사람 검토 → 별도 데이터셋
                                              └ 전체 기록 → 자주 노출된 유형과 훈련 추천
```

| 요구 사항 | 구현 |
|---|---|
| 폴더의 음성 수집 | 저장소 접근 프레임워크로 사용자가 고른 폴더를 읽음. 연결 후 생긴 파일만 대상 |
| S3 전송 | WorkManager 15분 주기와 수동 동기화. 기기에 AWS 키 없이 presigned URL 사용 |
| STT → LLM | Amazon Transcribe(ko-KR) → Claude Opus 5.5 스키마 출력 |
| 개인화 추천 | 기기별 판정 기록을 유형별로 집계해 상위 3개와 훈련 제시 |
| 가족 알림 | 초대 코드로 연결. 확신도 0.7 이상 보이스피싱만, 요약만 전달 |
| 유형 판별 | 음절 2-gram BM25 + Titan 벡터 → RRF → Claude 재순위 |
| 비보이스피싱 사기 | 사람이 확정한 건만 `review_dataset`에 보관, JSONL로 내보내기 |

보관 기준: 음성은 분석 후 삭제하고, 일상 통화는 글자 기록도 남기지 않습니다.

## 서버 실행

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q   # AWS 없이 전체 흐름 테스트
```

AWS 없이 (`.txt`를 녹취로 간주, 키워드 판정):

```bash
GUARD_PUBLIC_BASE_URL=http://<서버주소>:8091 .venv/bin/uvicorn guard.app:app --host 0.0.0.0 --port 8091
```

실제 구성:

```bash
GUARD_STORAGE=s3 GUARD_S3_BUCKET=<버킷> GUARD_STT=transcribe GUARD_LLM=bedrock GUARD_EMBED=titan \
GUARD_ADMIN_TOKEN=<임의 값> .venv/bin/uvicorn guard.app:app --host 0.0.0.0 --port 8091
```

버킷은 공개 차단과 수명 주기 삭제 규칙을 켜 두세요. 분석에 실패한 음성은 재시도를 위해 남기 때문입니다.

## 앱 빌드

- **GitHub Actions:** 브랜치를 올린 뒤 Actions의 `Android APK`에서 `codysafe-guard-debug-apk`를 받습니다.
- **Android Studio:** `android/` 폴더를 열고 실행합니다. 에뮬레이터에서 내 PC의 서버 주소는 `http://10.0.2.2:8091`입니다.

## 2분 테스트

1. 폰 A(보호 대상)와 폰 B(가족)에 앱을 설치하고 각각 등록합니다.
2. A의 가족 탭에서 초대 코드를 만들어 B에 입력합니다.
3. A에서 `테스트 파일 1개 올리기`로 파일을 올립니다. 테스트 모드에서는 `.txt`로 된 대본도 됩니다.
4. A에 판정이 나오고, 앱을 켜 둔 B에 5초 안에 알림이 오는지 확인합니다.

## 제약

- **녹음은 앱이 만들지 않습니다.** 안드로이드는 일반 앱의 통화 음성 녹음을 막습니다. 카카오톡·디스코드 음성은 사용자가 녹음 파일을 폴더에 넣어야 합니다.
- **가족 알림 지연:** 받는 쪽 앱이 꺼져 있으면 최대 15분 이상 늦습니다. 실서비스에는 FCM이 필요합니다.
- **HTTP 테스트 전용:** 실제 통화를 올리기 전에 서버를 HTTPS로 바꾸고 `usesCleartextTraffic`를 지웁니다.
- **데이터 이동:** 기본 모델은 `global.` 추론 프로파일이라 녹취가 국외에서 처리될 수 있습니다.
- **성능 미측정:** 소수의 합성 대본으로 동작만 확인했습니다. 탐지율과 오탐률은 측정하지 않았습니다.
