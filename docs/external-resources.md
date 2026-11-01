# 외부 자원 목록 (가이드 ⓕ 양식)

이 표는 쓰는 대로 고쳐 씁니다. 실제로 쓴 것만 적고, 확인하지 못한 칸은 '확인 중'으로 둡니다.
마지막 확인: 2026-11-01 08:5x KST (모의 훈련 v2 작업 기준, 임대 GPU 칸은 O-2 `gpu/external-resources_gpu.md` 반영)

## 1. 오픈소스

| 구분 | 명칭 | 용도 | 라이선스 |
|---|---|---|---|
| 오픈소스(서버) | FastAPI | API 서버 | MIT |
| 오픈소스(서버) | Uvicorn | ASGI 서버 실행 | BSD-3-Clause |
| 오픈소스(서버) | Pydantic | 요청·대본 그래프·프로필 형식 검사 | MIT |
| 오픈소스(서버) | HTTPX | 임대 GPU 음성 합성·인식 주소 호출, 시험 클라이언트 | BSD-3-Clause |
| 오픈소스(서버) | pytest | 자동 시험 | MIT |
| 오픈소스(서버) | OpenAI Python SDK | OpenAI 호환 주소(임대 GPU LLM) 호출, 대체 경로 | Apache-2.0 |
| 오픈소스(서버) | Anthropic Python SDK | 기존 탐지 분석, 판정기 대체 경로(설정했을 때만) | MIT |
| 오픈소스(서버) | boto3 | 기존 탐지 기능의 AWS 연동 | Apache-2.0 |
| 오픈소스(화면) | Lucide 아이콘 0.460.0 | 화면 아이콘 | ISC |
| 오픈소스(화면) | SUIT 글꼴 2.0.5 | 화면 글꼴 | SIL OFL 1.1 |
| 오픈소스(GPU) | vLLM 0.21.0 | 판정 LLM을 OpenAI 호환 주소로 서빙 | Apache-2.0 |
| 오픈소스(GPU) | faster-whisper 1.2.1 (CTranslate2) | 전화 훈련 답 음성 인식 | MIT |
| 오픈소스(GPU) | qwen-tts 0.1.1 | 전화 훈련 대사 음성 합성 | Apache-2.0 |
| 오픈소스(GPU) | Modal Python 클라이언트 | 배포·자동 크기 조절 | Apache-2.0 |
| 오픈 모델 | kakaocorp/kanana-1.5-8b-instruct-2505 (fp8 동적 양자화) | 규칙으로 정하지 못한 답의 판정(등급·의도 JSON) | Apache-2.0 |
| 오픈 모델 | openai/whisper-large-v3-turbo (변환본 dropbox-dash/faster-whisper-large-v3-turbo) | 음성 인식(팀 korean-stt와 같은 모델) | MIT |
| 오픈 모델 | Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign | 한국어 음성 합성. 목소리 3개는 글 설명으로 설계, 실제 사람 목소리 복제 없음 | Apache-2.0 |
| 오픈소스(도구) | FFmpeg | 합성 통화 녹음을 전화 음질(300–3400Hz)·16kHz로 변환 | LGPL-2.1 이상(빌드에 따라 GPL) |

## 2. 외부 API·브라우저 기능

| 구분 | 명칭 | 용도 | 라이선스·조건 |
|---|---|---|---|
| 브라우저 기능 | Web Speech API `speechSynthesis` | 전화 훈련에서 임대 GPU 음성이 없을 때 대사를 ko-KR로 읽음 | 브라우저 내장 기능 |
| 브라우저 기능 | Web Speech API `webkitSpeechRecognition` | 전화 훈련에서 임대 GPU 음성 인식이 없을 때 답을 글자로 바꿈. Chrome은 말소리를 Google 서버로 보내므로 화면에서 먼저 알린 뒤 사용 | Google 서비스 약관(Chrome) |
| 브라우저 기능 | Web Audio API | 대사 음성에 전화 음질(300–3400Hz) 필터 적용 | 브라우저 내장 기능 |
| 외부 서비스 | Modal (https://modal.com) — LLM 주소 `SIM_LLM_BASE_URL` | 팀이 고른 오픈 모델을 임대 GPU에서 직접 서빙, 규칙으로 정하지 못한 답만 판정. 토큰 인증(주소·토큰 값은 `server/.env`에만 둠) | Modal 이용 약관 https://modal.com/legal/terms , 무료 크레딧 US$30 |
| 외부 서비스 | Modal — 음성 주소 `SIM_TTS_URL`·`SIM_STT_URL` | 전화 훈련 대사 합성, 답 음성 인식 | 위와 같음 |
| 외부 API | OpenAI·Anthropic API (`SIM_FALLBACK`) | 판정기 대체 경로. `server/.env`에 켰을 때만 부르며 기본은 꺼짐 | 각 회사 이용 약관 |

## 3. 데이터·자료

| 구분 | 명칭 | 용도 | 라이선스·조건 |
|---|---|---|---|
| 공공 자료 | 금융위원회 「보이스피싱 피해예방 10계명」(2026-02-10, https://www.fsc.go.kr/no010101/86250) | 훈련 대본 3개의 대사 흐름과 해설의 바탕. 원문을 옮기지 않고 새로 쓴 가상 대화이며, 대본의 `source_refs`에 출처를 적음 | 출처 표시. 공공누리 유형은 확인 중 |
| 자체 제작 | 훈련 대본 그래프 3개(`server/guard/sim/graphs/`) | 모의 훈련 | 팀 제작. 번호는 010-0000-XXXX 꼴, 주소는 example 도메인만 씀 |
| 자체 제작 | 판정기 평가 후보 60개(`eval/judge_candidates.csv`) | 판정기 정확도 평가. 라벨은 호연이 붙임 | 팀 제작(AI 도구로 초안) |

## 4. 도구

| 구분 | 명칭 | 용도 | 라이선스·조건 |
|---|---|---|---|
| 코딩 도우미 | Claude Code (Claude Opus 5.5) | 모의 훈련 v2 코드·시험·문서 초안 작성. 커밋 메시지에 'AI 도구로 초안 작성'을 적음 | Anthropic 이용 약관 |
| 음성 합성 도구 | macOS `say` 음성 Yuna·Grandma | 탐지 시연용 **합성** 사기 통화 `eval/synthetic_call.wav` 임시 제작, 임대 GPU 리허설에서 사용자 답 음성 합성(실제 사람 목소리 아님) | macOS 소프트웨어 사용권 |

## 5. GPU

| 구분 | 명칭 | 용도 | 비고 |
|---|---|---|---|
| GPU | Modal의 NVIDIA L40S 48GB (앱마다 1장, 쓸 때만 켜짐) | 판정 LLM·음성 합성·음성 인식 | 실측 `eval/gpu_latency.md`(O-2), 훈련 차례별 지연 `eval/latency.md`(O-1). 대회 L4는 쓰지 않았다 |

## 6. 사전 보유 코드

| 구분 | 명칭 | 용도 | 비고 |
|---|---|---|---|
| 사전 보유 코드 | 팀 확인 중 | 팀 확인 중 | 대회 전부터 있던 코드가 있으면 팀 전체 확인 뒤 적습니다(빠뜨리면 실격 사유) |
