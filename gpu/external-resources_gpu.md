# docs/external-resources.md 에 넣을 GPU 행 (O-2, 2026-11-01)

`docs/external-resources.md`는 hoyeon/sim(O-1)에 있어서, 이 브랜치에 같은 파일을 새로 만들면 합칠 때 충돌한다.
합치기(11번) 때 아래 행으로 그 파일의 '확인 중' 칸을 바꾼다. 실제로 쓴 것만 적었다.

## 1. 오픈소스

| 구분 | 명칭 | 용도 | 라이선스 |
|---|---|---|---|
| 오픈소스(GPU) | vLLM 0.21.0 | 판정 LLM을 OpenAI 호환 주소로 서빙 | Apache-2.0 |
| 오픈소스(GPU) | faster-whisper 1.2.1 (CTranslate2) | 전화 훈련 답 음성 인식 | MIT |
| 오픈소스(GPU) | qwen-tts 0.1.1 | 전화 훈련 대사 음성 합성 | Apache-2.0 |
| 오픈소스(GPU) | Modal Python 클라이언트 | 배포·자동 크기 조절 | Apache-2.0 |
| 오픈 모델 | kakaocorp/kanana-1.5-8b-instruct-2505 (fp8 동적 양자화) | 규칙으로 정하지 못한 답의 판정(등급·의도 JSON) | Apache-2.0 |
| 오픈 모델 | openai/whisper-large-v3-turbo (변환본 dropbox-dash/faster-whisper-large-v3-turbo) | 음성 인식(팀 korean-stt와 같은 모델) | MIT |
| 오픈 모델 | Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign | 한국어 음성 합성. 목소리 3개는 글 설명으로 설계, 실제 사람 목소리 복제 없음 | Apache-2.0 |

## 2. 외부 API (기존 '확인 중' 두 줄을 바꿈)

| 구분 | 명칭 | 용도 | 라이선스·조건 |
|---|---|---|---|
| 외부 서비스 | Modal (https://modal.com, 작업 공간 hoykim125) — LLM 주소 `SIM_LLM_BASE_URL` | 팀이 고른 오픈 모델을 임대 GPU에서 직접 서빙. 토큰 인증 | Modal 이용 약관 https://modal.com/legal/terms , 무료 크레딧 US$30 |
| 외부 서비스 | Modal — 음성 주소 `SIM_TTS_URL`·`SIM_STT_URL` | 전화 훈련 대사 합성, 답 음성 인식 | 위와 같음 |

## 5. GPU (기존 '확인 중' 줄을 바꿈)

| 구분 | 명칭 | 용도 | 비고 |
|---|---|---|---|
| GPU | Modal의 NVIDIA L40S 48GB (앱마다 1장, 쓸 때만 켜짐) | 판정 LLM·음성 합성·음성 인식 | 실측 `eval/gpu_latency.md`. 대회 L4는 쓰지 않았다 |
