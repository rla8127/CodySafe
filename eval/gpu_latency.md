# 임대 GPU 실측 (Modal, NVIDIA L40S) — 2026-11-01 08:02–08:22 KST

측정: O-2(Claude Code), 스크립트 `gpu/measure.py`. 원자료는 `runs/gpu_measure_*.json`(git 제외).
넣은 자료: 훈련 팀이 만든 판정 시험 문장(`eval/judge_holdout.csv` 앞 20개, 바꿔 쓴 대사)과 합성 음성뿐. 실제 통화는 올리지 않았다.
호출 위치: 호연 맥(서울) → Modal us-east. 아래 시간은 이 네트워크 왕복을 포함한다.

## 1. 요약

| 항목 | 값 | O-1 시간 초과 안에? |
|---|---|---|
| GPU | NVIDIA L40S 48GB (LLM 1장, 음성 1장, 앱마다 컨테이너 1개) | |
| LLM 콜드 스타트(0 → `/v1/models` 200) | 첫 배포 149초, 두 번째 109초(컴파일 캐시 사용) | 아니오 (6초) → 시연 전 `gpu/warm.sh up` 필수 |
| LLM 판정 JSON 20회: 형식 깨짐 | **0/20 (0%)** → Qwen3.5-9B로 바꾸지 않음 | |
| LLM 웜 첫 토큰 | 중앙 0.27초 · 최대 2.08초 | |
| LLM 웜 전체 응답 | 중앙 0.66초 · 최대 2.45초 | 예 (20/20이 6초 안) |
| LLM 등급 일치(참고) | 라벨과 15/20 (규칙 없이 LLM만. 판정기 정확도는 O-1 R-005가 따로 잰다) | |
| 음성 콜드 스타트(0 → `/health` 200, 모델 적재+예열 포함) | 25–26초 | 아니오 → warm.sh 필수 |
| STT 16.6초 음성(합성) | 왕복 중앙 0.73초 · 최대 2.1초, 서버 처리 0.32초 | 예 (15초) |
| TTS 한 문장 20자(4.1초 분량) | 중앙 7.7초 · 최대 8.4초 (5회, 세 목소리) | **간신히 예** (10초) |
| TTS 긴 문장 97자(16.6초 분량) | 26.7–28.2초 | **아니오** (10초) — 아래 4절 |
| TTS → STT 왕복 | "고객님 명의 계좌가 금융 범죄에 연루되었습니다" → "고객님 명의 계좌가 금융범죄에 연루되었습니다." (띄어쓰기·마침표만 다름) | |
| GPU 메모리 최대(nvidia-smi) | LLM 40,898 / 46,068 MiB (vLLM이 KV 캐시로 90%를 미리 잡음. fp8 가중치는 약 9GB) · 음성 7,320 MiB (torch 최대 4,347 MiB) | |
| 쓴 크레딧(08:2x, `modal billing summary`) | 약 US$1.13 (배포 앱 1.10 + 임시 0.02 + 송신 0.01), 청구 $0 | |

## 2. 모델과 설정

- LLM: `kakaocorp/kanana-1.5-8b-instruct-2505`(Apache-2.0), vLLM 0.21.0, `--quantization fp8 --max-model-len 4096`, 이름 `codysafe-llm`, 구조화 출력 `response_format=json_schema`(strict, enum grade·intent).
- STT: `openai/whisper-large-v3-turbo`의 CTranslate2 변환본 `dropbox-dash/faster-whisper-large-v3-turbo`(MIT), faster-whisper 1.2.1, float16, ko 고정, beam 5, VAD. 팀 korean-stt 서버(김동현, 같은 모델 CPU int8)와 같은 모델을 골라 탐지·훈련의 인식 결과를 맞췄다.
- TTS: `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`(Apache-2.0, 한국어 지원·말투 지시 지원을 모델 카드에서 확인), qwen-tts 0.1.1, bf16. 목소리 세 개(caller_male·caller_female·family)는 글로 설명한 **설계 목소리**이고 목소리마다 난수 씨앗을 고정했다. 실제 사람 목소리 복제 없음.
- 스케일: 최소 컨테이너 0, 유휴 5분 뒤 종료, 최대 컨테이너 1.

## 3. 말투(감정) 지시

같은 문장 "지금 바로 확인하셔야 합니다. 시간이 얼마 없어요."(caller_male)를 `emotion=urgent`와 `emotion=calm`으로 만들었다: 다급함 3.68초, 차분함 6.40초. 말 빠르기 차이는 길이로 확인했다. 음색·감정이 귀로 들리는지는 **미확인**(듣기 파일: `runs/tts_tone_urgent.wav`, `runs/tts_tone_calm.wav`, 호연 확인 필요).

## 4. 한계와 대응

- TTS가 느리다(실시간 대비 약 1.6–1.9배 시간). qwen-tts의 Hugging Face 비스트리밍 경로라서이다. 컨테이너 CPU를 4코어로 올린 판(08:3x 재측정, 20자 3회)도 서버 처리 6.5초·왕복 7.8–8.1초로 거의 같았다. 왕복 중 약 1.4초는 서울↔Modal 미국 동부 네트워크와 wav 내려받기다. 빠른 경로(vLLM-Omni)는 시간 안에 시험하지 못했다.
- 대응: O-1은 대사를 미리 합성해 캐시한다. 그때 긴 대사는 10초를 넘으므로 `SIM_TTS_TIMEOUT`을 늘리거나(예 40) 대사를 짧게 끊는 편이 맞다(호연 결정).
- 콜드 스타트(LLM 약 2분, 음성 약 25초)는 O-1 시간 초과보다 길다. 시연·리허설 전에 `gpu/warm.sh up`, 끝나면 `gpu/warm.sh down`.
- 측정은 각 1회 실행(LLM 20회, TTS 5회, STT 3회)이고 동시 요청 부하는 재지 않았다.
