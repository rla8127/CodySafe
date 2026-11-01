# 임대 GPU·모델 목록 (PPT ⓒ·ⓓ·ⓕ용, 2026-11-01 10:3x 기준)

실제로 쓴 것만 적었다(정직성 원칙). 대회 L4·H100·L4(Modal)는 쓰지 않았다. 수치 근거는 `eval/gpu_latency.md`, `eval/tts_voice_tuning.md`.

## 1. GPU·서비스

| 항목 | 내용 |
|---|---|
| 서비스 | Modal (https://modal.com, 작업 공간 hoykim125, 서버리스 GPU, 약관 https://modal.com/legal/terms ) |
| GPU | **NVIDIA L40S 48GB** (Ada Lovelace 세대, FP8 지원. nvidia-smi 총 46,068 MiB). Modal 요금 US$1.95/시간 |
| 구성 | 앱 4개, 앱마다 컨테이너 최대 1개·GPU 1장. 쓰지 않으면 5분 뒤 꺼짐(비용 0), 부르면 깨어남 |
| 앱 | `codysafe-llm`(판정 LLM, 상시 주소) · `codysafe-voice`(STT·TTS, 상시 주소) · `codysafe-face`·`codysafe-video`(얼굴·영상, 필요할 때 1회 실행) |
| 인증 | 모든 주소 Bearer 토큰 1개(Modal Secret과 git 제외 `.env`에만) |
| 비용(10:2x까지) | 약 US$11 (10월분 약 $2.9 + 11월분 약 $8.0, 무료 크레딧으로 처리, 청구 $0). 집계가 늦게 반영될 수 있음 |
| 예비 자료 | GPU로 미리 만든 음성·판정·영상을 `server/backup/`에 저장해 GPU 없이도 시연(아래 4절) |

## 2. 모델 (모두 오픈 가중치, 우리가 학습시키지 않음. 팀이 직접 한 것: 모델 선택, GPU 서빙 코드, 목소리 고정 방식, 얼굴→음성→영상 연결과 구간 이어 그리기·후처리, 예비 자료 생성, 지연·화자 유사도·입 모양 평가)

| 역할 | 모델 (Hugging Face) | 크기 | 라이선스 | 우리 설정 | 실측 |
|---|---|---|---|---|---|
| 답 판정 LLM | kakaocorp/kanana-1.5-8b-instruct-2505 | 8.0B | Apache-2.0 | vLLM 0.21.0, FP8 동적 양자화, 최대 4,096토큰, JSON 스키마 강제 출력(등급·의도·확신) | 형식 깨짐 0/20, 웜 응답 중앙 0.66초, GPU 메모리 40.9GB(vLLM 선점 90%) |
| 음성 인식(STT) | openai/whisper-large-v3-turbo (CTranslate2 변환본 dropbox-dash/faster-whisper-large-v3-turbo) | 0.81B | MIT | faster-whisper 1.2.1, float16, 한국어 고정, beam 5, VAD | 16.6초 음성 0.73초(왕복), TTS→STT 되읽기 일치 |
| 음성 합성(TTS) 목소리 설계 | Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign | 1.9B | Apache-2.0 | 글 설명으로 목소리 4개(사기범 남·여, 아들, 딸)를 1번씩만 설계해 저장 | — |
| 음성 합성(TTS) 대사 읽기 | Qwen/Qwen3-TTS-12Hz-1.7B-Base | 1.9B | Apache-2.0 | 저장한 설계 목소리로 모든 대사를 읽음(실제 사람 목소리 복제 없음), 말투별 빠르기 맞춤(ffmpeg) | 화자 유사도 0.960→0.993, 6.2–7.2음절/초, 대사 하나 6–10초 |
| 얼굴 사진(실존하지 않는 사람) | Tongyi-MAI/Z-Image-Turbo | 6.2B | Apache-2.0 | 걱정스러운 표정의 20대 남녀 정면 사진 | 장당 약 4.4초 |
| 말하는 얼굴 영상 | BadToBest/EchoMimicV3 (echomimicv3-flash-pro), 코드 antgroup/echomimic_v3 | 1.7B | Apache-2.0 | 768×768, 오디오 CFG 5, 8단계, TeaCache 끔, 앞 구간 마지막 프레임에서 이어 그리기, 'AI 생성' 표시 | 27–29초 영상 1편 그리기 12–14분 |
| 영상 기반 모델 | alibaba-pai/Wan2.1-Fun-V1.1-1.3B-InP | 1.3B | Apache-2.0 | EchoMimicV3의 바탕 | — |
| 영상용 음성 인코더 | TencentGameMate/chinese-wav2vec2-base | 약 0.1B | MIT | EchoMimicV3 Flash 공식 구성 | — |

## 3. 오픈소스 도구

vLLM 0.21.0(Apache-2.0) · faster-whisper 1.2.1 / CTranslate2(MIT) · qwen-tts 0.1.1(Apache-2.0) · Modal Python 클라이언트(Apache-2.0) · FFmpeg(LGPL/GPL, 음성 디코딩·속도 맞춤·mp3 변환·'AI 생성' 표시) · PyTorch(BSD)

## 4. 팀 서버와 역할 나눔

| 구성 | 어디서 | 비고 |
|---|---|---|
| 탐지 STT | 팀 korean-stt 서버(김동현, EC2 CPU, whisper large-v3-turbo INT8) | 훈련 STT와 같은 모델 계열. 시연 때 훈련 STT도 이 서버를 씀(호연 11-01 10:1x 결정) |
| 훈련 대사 음성·판정·영상 | 임대 GPU로 **미리** 만들어 `server/backup/`에 저장 | 시연·녹화는 저장 자료로. 대사 49개 mp3(프리셋 3개 × 대본 3개의 108줄을 모두 찾음), 판정 138개(대본 선택지 48 + 미리 판정한 답 90), 영상 2편. 표에 없는 자유 답은 규칙·기본값으로 |
| 실시간 GPU | 필요할 때만 깨움(`gpu/warm.sh up`) | 시연 직전 30분 정도, 두 앱 시간당 약 US$3.9 |

## 5. 한 줄 설명 (발표용)

- "팀이 고른 오픈 모델 6종을 임대 GPU(Modal, NVIDIA L40S)에 직접 올려, 판정·음성 인식·음성 합성·딥페이크 영상을 만들었다. 시연은 GPU로 미리 만든 결과(대사 음성·판정·영상)를 저장해 두고 재생해, GPU 연결 없이도 같은 자료가 나온다. 말소리 인식(STT)만 팀 STT 서버 연결이 필요하다."
- "목소리는 녹음 없이 글 설명으로 설계했고, 영상 얼굴은 세상에 없는 사람이다. 모든 영상에 'AI 생성'을 표시했다."
