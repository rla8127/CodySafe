# kimble125-patch-1 안내 (동현님께, 2026-11-01)

호연 브랜치 `kimble125-patch-1`에 들어 있는 것과 main에 합칠 때 알아 두실 것만 적었습니다.

## 1. 합치기

- `origin/main`(6368741)까지 이미 합쳐 두어서, main으로 합칠 때 충돌이 없습니다.
- 시험: `cd server && .venv/bin/python -m pytest -q` → 216개 통과(11-01 11:2x). 새 의존성은 `mutagen`·`langfuse`(이미 requirements.txt에 있음)입니다.

## 2. 새로 들어온 것

| 기능 | 위치 | 켜는 법 |
|---|---|---|
| 모의 훈련 v2(문자·전화 훈련, 안심 대응 점수) | `server/guard/sim/`, `server/guard/sim_api.py`, `server/web/sim2.js` | 앱 `#/sim2`. 체험 탭 맨 위 배너 |
| 예비 자료(미리 만든 대사 음성·판정·영상) | `server/backup/` | `.env`에 `SIM_BACKUP_FIRST=1` |
| 탐지 개선(사례 검색 먼저) | `server/guard/rag_first.py`, `server/web/detect_extra.js` | `.env`에 `GUARD_RAG_FIRST=1`, `GUARD_RAG_TIMEOUT=3`(기본은 꺼짐, 끄면 예전 화면 그대로) |
| 공식 사기 사례 46건, 생성 대본 1개 | `data/clean/2026_official_cases.jsonl`, `server/guard/sim/graphs/generated/` | 따로 켤 것 없음 |

실행 중에는 임대 GPU를 쓰지 않습니다. 서버 `.env`(모의 훈련 부분)는 `gpu/README.md`의 'server/.env (실행할 때)'를 따르면 됩니다. GPU 주소·토큰은 넣지 않고, 말소리 인식(STT)만 팀 STT 서버를 씁니다.

## 3. 발표자료·시연 영상에 쓸 것

| 무엇 | 파일 |
|---|---|
| 가족 사칭 영상 통화 예시 2편(합성 얼굴, 화면에 'AI 생성' 표시, 각 28초) | `server/backup/video/son_accident.mp4`, `server/backup/video/daughter_deposit.mp4` |
| 화면 캡처 8장(문자·전화 훈련, 결과, 탐지 결과·잠금·가족 알림) | `eval/screens/` |
| 합성 통화 음성(자체 대본, 실제 통화 아님) | `eval/synthetic_call.wav` |
| 쓴 GPU·모델 표, 발표용 한 줄 설명 | `docs/gpu-models.md`(5절이 한 줄 설명) |
| 외부 자원 표 | `docs/external-resources.md` |
| 숫자 근거 | 판정기 `eval/judge_report.md`, 지연 `eval/latency.md`·`eval/gpu_latency.md`, 목소리 개선 `eval/tts_voice_tuning.md`, 탐지 오탐·미탐 `eval/detect_report.md` |

## 4. 주의

- 영상의 얼굴과 목소리는 실제 사람이 아닙니다(합성). 영상을 쓸 때 'AI 생성' 표시를 지우지 말아 주세요.
- 판정기는 규칙으로 판정하는 부분에 아직 한계가 있습니다. 예를 들어 "신고할 생각 없어요"를 정답으로 보는 등의 반례가 검토에서 나왔지만 제출 전에 고치지 못했습니다. 발표에서 "판정이 완벽하다"고 말하지 않는 것이 안전합니다.
- 실제 마이크로 말해 보는 경로는 확인하지 못했습니다(합성 음성으로만 확인).
