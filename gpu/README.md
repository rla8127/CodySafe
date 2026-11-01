# gpu/ — 임대 GPU(Modal) 모델 서빙

CodySafe 모의 훈련의 판정 LLM·음성 인식·음성 합성을 Modal(작업 공간 hoykim125)의 NVIDIA L40S에 올린다.
실측은 `eval/gpu_latency.md`.

| 앱 | 파일 | 주소 | 내용 |
|---|---|---|---|
| codysafe-llm | `llm.py` | https://hoykim125--codysafe-llm-serve.us-east.modal.run (`/v1`, `/health`) | vLLM OpenAI 호환, Kanana 1.5 8B fp8, 모델 이름 `codysafe-llm` |
| codysafe-voice | `voice.py` | https://hoykim125--codysafe-voice-voice-web.us-east.modal.run (`/stt`, `/tts`, `/health`) | faster-whisper large-v3-turbo + Qwen3-TTS 1.7B VoiceDesign |
| codysafe-video | `video.py` (P1, 아직 없음) | — | EchoMimicV3, 동의한 사진만 |

## 인증

모든 주소는 `Authorization: Bearer <토큰>` 하나로 받는다(`/health`만 토큰 없음). 토큰은 Modal Secret `codysafe-gpu`(키 `GPU_TOKEN`)와 git이 무시하는 `server/.env`·`.env.gpu`에만 있다. 화면·로그·커밋에 쓰지 않는다. vLLM에는 `--api-key` 대신 환경 변수로 넘긴다(vLLM이 시작할 때 명령 인자를 로그에 찍기 때문).

## server/.env 변수

```
SIM_LLM_BASE_URL=https://hoykim125--codysafe-llm-serve.us-east.modal.run/v1
SIM_LLM_MODEL=codysafe-llm
SIM_LLM_API_KEY=<토큰>
SIM_TTS_URL=https://hoykim125--codysafe-voice-voice-web.us-east.modal.run/tts
SIM_STT_URL=https://hoykim125--codysafe-voice-voice-web.us-east.modal.run/stt
SIM_TTS_VOICE=caller_male
SIM_TTS_API_KEY=<같은 토큰>   # 음성 주소의 호스트가 LLM과 달라 O-1 클라이언트가 LLM 토큰을 빌리지 않는다
SIM_STT_API_KEY=<같은 토큰>
```

## 요청 형식 (O-1 클라이언트에 맞춰 너그럽게 받음)

- `POST /tts` JSON: `text`(없으면 `input`), `voice` ∈ caller_male·caller_female·family(그 밖은 caller_male), `format` 또는 `response_format` = wav, 선택 `emotion`(calm·official·urgent·threat·tremble·sob·friendly)·`instruct`(말투 설명) → `audio/wav`. 400자까지.
- `POST /stt` multipart `file`(wav·webm·m4a·mp3, 15MB까지), 선택 `language`(기본 ko), `model`은 무시 → `{"text", "duration_s", "elapsed_s"}`.
- `GET /health` → `{"ok": true, "model": ...}`. LLM의 `/health`는 vLLM 기본(200, 빈 본문).

## 배포·운영

```bash
python3 -m venv .venv && .venv/bin/pip install modal python-dotenv httpx
.venv/bin/modal run gpu/llm.py::download      # 가중치를 Volume(codysafe-hf-cache)에 CPU로 미리 받기
.venv/bin/modal run gpu/voice.py::download
.venv/bin/modal deploy gpu/llm.py
.venv/bin/modal deploy gpu/voice.py
.venv/bin/python gpu/measure.py --llm <llm 주소> --voice <voice 주소>   # 실측 → runs/
```

- 최소 컨테이너 0, 유휴 5분 뒤 꺼짐, 최대 1개. 그래서 오래 쉬었다가 처음 부르면 콜드 스타트(LLM 약 2분, 음성 약 25초)가 걸려 O-1의 시간 초과(LLM 6초·TTS 10초·STT 15초)를 넘는다.
- **시연·리허설 전에 반드시 `gpu/warm.sh up`**, 끝나면 **바로 `gpu/warm.sh down`**. 켜 두는 동안 시간당 크레딧이 나간다(L40S 약 US$1.95/h × 2개 앱 ≈ US$3.9/h). 크레딧은 US$30, 지출 한도 $0이라 다 쓰면 Modal이 앱을 멈춘다. 실행 시각은 호연이 정한다.
- 상태: `gpu/warm.sh status` 또는 https://modal.com/apps/hoykim125/main
- GPU는 ES 서버를 부르지 않는다. 검색은 서비스 서버가 하고 결과만 LLM 요청에 넣는다.
- 올리는 자료: 공개 자료, 바꿔 쓴 대사, 합성 음성, 동의한 사진만. 실제 사기 통화 원문(KorCCVi 등)·가족 실제 통화는 올리지 않는다.
