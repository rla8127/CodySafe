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
| STT → LLM | OpenAI 전사 또는 Amazon Transcribe(ko-KR) → OpenAI, Claude API, Bedrock 중 선택, 스키마 출력 |
| 개인화 추천 | 기기별 판정 기록을 유형별로 집계해 상위 3개와 훈련 제시 |
| 가족 알림 | 초대 코드로 연결. 확신도 0.7 이상 보이스피싱의 의심 여부만 전달. 요약·유형·녹취는 본인만 조회 |
| 유형 판별 | 음절 2-gram BM25 + 벡터 → RRF → LLM 재순위 |
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

LLM은 API 키나 Bedrock 중에서 고릅니다. 키는 저장소에 넣지 말고 환경 변수로만 넘기세요.

| 구성 | 설정 |
|---|---|
| OpenAI | `OPENAI_API_KEY=<키> GUARD_LLM=openai GUARD_OPENAI_MODEL=<모델> GUARD_EMBED=openai` |
| Claude API | `ANTHROPIC_API_KEY=<키> GUARD_LLM=anthropic` (벡터 검색은 해시 방식, 실제 임베딩은 아님) |
| Bedrock | `GUARD_LLM=bedrock GUARD_EMBED=titan` |

실제 음성을 AWS 없이 처리하려면 `OPENAI_API_KEY=<키> GUARD_STT=openai`를 더합니다. 파일당 25MB까지이고 AMR은 지원하지 않습니다.

S3와 Transcribe로 처리하려면 다음을 더합니다.

```bash
GUARD_STORAGE=s3 GUARD_S3_BUCKET=<버킷> GUARD_STT=transcribe GUARD_ADMIN_TOKEN=<임의 값> \
.venv/bin/uvicorn guard.app:app --host 0.0.0.0 --port 8091
```

버킷은 공개 차단과 수명 주기 삭제 규칙을 켜 두세요. 분석에 실패한 음성은 재시도를 위해 남기 때문입니다.

## 화면 수정

화면은 서버의 `/app/`에서 제공합니다(`server/web/`, 공용 `css/`, `js/`). 앱은 이를 WebView로 띄우므로, 화면을 고치면 APK를 다시 빌드하지 않아도 브라우저와 앱에 바로 반영됩니다. 앱을 다시 빌드할 일은 폴더 접근, 동기화, 알림을 바꿀 때뿐입니다.

## 앱 빌드

- **GitHub Actions:** 브랜치를 올린 뒤 Actions의 `Android APK`에서 `codysafe-guard-debug-apk`를 받습니다.
- **Android Studio:** `android/` 폴더를 열고 실행합니다. 에뮬레이터에서 내 PC의 서버 주소는 `http://10.0.2.2:8091`입니다.

## 2분 테스트

1. 기기 A(보호 대상)와 B(가족)에서 앱이나 브라우저로 `/app/`을 열어 각각 등록합니다.
2. A의 가족 탭에서 초대 코드를 만들어 B에 입력합니다.
3. A의 검사 탭에서 파일을 올립니다.
4. A에는 분석 결과가, B에는 의심 여부만 나오는지 확인합니다.

## 금융 앱 잠금

- 보이스피싱 확신도가 `GUARD_LOCK_THRESHOLD`(기본 0.9) 이상이면 `GUARD_LOCK_SECONDS`(기본 1시간) 동안 잠급니다.
- 앱의 접근성 서비스가 30초마다 서버 상태를 확인하고, 잠금 중 대상 앱이 열리면 홈으로 보낸 뒤 경고 화면을 띄웁니다. 화면 내용은 읽지 않습니다.
- 대상 앱은 `server/guard/lock_apps.py`의 앱 ID 목록입니다. 수정 후 서버만 재시작하면 APK를 다시 빌드하지 않아도 반영됩니다.
- 해제: 연결된 가족은 즉시, 본인은 10분 대기 후, 또는 시간 만료. 판정 수정과 기록 삭제로는 풀리지 않습니다.
- 사용자가 접근성 권한을 끄거나 앱을 지우면 막을 수 없습니다.

## 가족 암구호

- 연결된 가족 전체가 같은 단어 2개를 보고, 한국 시간 0시에 자동으로 바뀝니다. 서버에 저장된 키와 가족 그룹, 날짜로 계산합니다.
- 폰을 잃은 가족을 위해 질문과 답을 정하는 비상 암구호를 둡니다. 답은 scrypt 해시만 저장하고, 기기당 10분에 5번까지 틀릴 수 있습니다.
- 서버 관리자는 키를 볼 수 있으므로 종단간 비밀은 아닙니다.

## 제약

- **웹에서의 차이:**

  | 기능 | HTTP | HTTPS + Chrome·Edge | 안드로이드 앱 |
  |---|---|---|---|
  | 파일 직접 올리기 | 가능 | 가능 | 가능 |
  | 폴더 검사 | 고를 때마다 확인 후 전송 | 페이지를 연 동안 자동 | 앱이 꺼져도 주기 실행 |
  | 가족 경고 | 페이지를 연 동안 화면·소리 | + 시스템 알림 | 앱을 연 동안 즉시, 닫으면 주기 확인 |

- **녹음은 앱이 만들지 않습니다.** 안드로이드는 일반 앱의 통화 음성 녹음을 막습니다. 카카오톡·디스코드 음성은 사용자가 녹음 파일을 폴더에 넣어야 합니다.
- **가족 알림 지연:** 받는 쪽 앱이 꺼져 있으면 최대 15분 이상 늦습니다. 실서비스에는 FCM이 필요합니다.
- **HTTP 테스트 전용:** 실제 통화를 올리기 전에 서버를 HTTPS로 바꾸고 `usesCleartextTraffic`를 지웁니다.
- **데이터 이동:** 어떤 LLM을 고르든 녹취가 외부 서비스로 전송되며 국외에서 처리될 수 있습니다.
- **성능 미측정:** 소수의 합성 대본으로 동작만 확인했습니다. 탐지율과 오탐률은 측정하지 않았습니다.
