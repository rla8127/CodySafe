# gpu/ — 임대 GPU(Modal) 모델 서빙

**GPU는 콘텐츠 생성 단계에서만 쓴다(호연 결정 11-01 11:1x).** 서비스·시연 실행 중에는 GPU를 부르지 않는다. Modal(NVIDIA L40S)에서 판정 LLM·음성 합성·영상 모델을 돌려 대사 음성·판정 표·딥페이크 영상을 **미리 만들어** `server/backup/`에 저장하고, 앱은 그 저장 자료만 쓴다. 말소리 인식(STT)은 팀 STT 서버(CPU)를 쓴다.
실측은 `eval/gpu_latency.md`, 모델 목록과 고른 이유는 `docs/gpu-models.md`.

| 앱 | 파일 | 주소 | 내용 |
|---|---|---|---|
| codysafe-llm | `llm.py` | 배포할 때만 생김(평소 내려 둠) | vLLM OpenAI 호환, Kanana 1.5 8B fp8, 모델 이름 `codysafe-llm` |
| codysafe-voice | `voice.py` | 배포할 때만 생김(평소 내려 둠) | faster-whisper large-v3-turbo + Qwen3-TTS 1.7B (VoiceDesign으로 목소리 4개를 1번 설계 → Base가 모든 대사를 그 목소리로) |
| codysafe-face·codysafe-video | `face.py`·`video.py`·`deepfake_presets.py` | 없음(`modal run`으로 필요할 때만) | Z-Image-Turbo로 실존하지 않는 얼굴 → EchoMimicV3로 말하는 영상, 'AI 생성' 표시 |

예비 자료: `server/backup/`(대사 mp3·판정 표·영상), 만드는 법 `gpu/make_backup.py`, 읽는 모듈 `server/guard/sim/backup.py`. GPU·모델 목록은 `docs/gpu-models.md`.

## 인증

모든 주소는 `Authorization: Bearer <토큰>` 하나로 받는다(`/health`만 토큰 없음). 토큰은 Modal Secret `codysafe-gpu`(키 `GPU_TOKEN`)와 git이 무시하는 `server/.env`·`.env.gpu`에만 있다. 화면·로그·커밋에 쓰지 않는다. vLLM에는 `--api-key` 대신 환경 변수로 넘긴다(vLLM이 시작할 때 명령 인자를 로그에 찍기 때문).

## server/.env (실행할 때)

GPU 주소·토큰은 넣지 않는다. 예비 자료와 팀 STT만 쓴다.

```
SIM_BACKUP_FIRST=1                 # 저장 자료(server/backup/)를 쓴다
SIM_TTS_VOICE=caller_male          # 예비 음성을 이 목소리로 만들었으므로 바꾸지 않는다
SIM_STT_URL=<팀 STT 서버 주소>/v1/audio/transcriptions
SIM_STT_API_KEY=<팀 STT 키>
SIM_STT_TIMEOUT=30
```

## 콘텐츠를 다시 만들 때만 (GPU)

`modal deploy gpu/llm.py`·`gpu/voice.py`로 잠시 올려 `gpu/make_backup.py`로 예비 자료를 만들고, 끝나면 `modal app stop`으로 내린다. 그때만 생성용 `.env`에 배포 주소와 토큰(Modal Secret `codysafe-gpu`와 같은 값)을 넣는다.

## 요청 형식 (O-1 클라이언트에 맞춰 너그럽게 받음)

- `POST /tts` JSON: `text`(없으면 `input`), `voice` ∈ caller_male·caller_female·family·family_female(그 밖은 caller_male), `format` 또는 `response_format` = wav, 선택 `emotion`(calm·official·urgent·threat·tremble·sob·friendly: 지금은 **말 빠르기로만** 반영, Base 모델은 말투 지시를 받지 않음)·`instruct`(지금은 쓰지 않음)·`rate`(목표 음절/초 3–9) → `audio/wav`. 400자까지.
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
- 시연·녹화는 **저장한 예비 자료**(`server/backup/`)로 한다(호연 11-01 결정). 실시간 GPU를 꼭 보여 줄 때만 직전에 `gpu/warm.sh up`, 끝나면 **바로 `gpu/warm.sh down`**. 켜 두는 동안 시간당 크레딧이 나간다(L40S 약 US$1.95/h × 2개 앱 ≈ US$3.9/h). 크레딧은 US$30, 지출 한도 $0이라 다 쓰면 Modal이 앱을 멈춘다. 실행 시각은 호연이 정한다.
- 상태: `gpu/warm.sh status` 또는 https://modal.com/apps/hoykim125/main
- GPU는 ES 서버를 부르지 않는다. 검색은 서비스 서버가 하고 결과만 LLM 요청에 넣는다.
- 올리는 자료: 공개 자료, 바꿔 쓴 대사, 합성 음성, 동의한 사진만. 실제 사기 통화 원문(KorCCVi 등)·가족 실제 통화는 올리지 않는다.
