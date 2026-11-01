"""예비 자료(백업): 임대 GPU가 꺼지거나 끊겼을 때 미리 GPU로 만들어 둔 결과를 대신 쓴다.

- 대사 음성: server/backup/tts/<key>.mp3, key = sha256("<voice>|<tone>|<text>")[:32]
  (주소·모델은 키에 넣지 않는다. GPU 주소가 없어도 같은 키로 찾게)
- 판정: server/backup/judge.json  {"<scenario>|<node>|<정규화한 답>": {"grade","intent","confidence"}}
  임대 GPU LLM(Kanana 1.5 8B)이 미리 판정한 결과. 정해진 답에는 늘 같은 판정이 나온다.
- 영상: server/backup/video/<name>.mp4  (합성 얼굴, 'AI 생성' 표시. 실제 사람 아님)
- 만든 방법·목록: server/backup/manifest.json, 생성 스크립트 gpu/make_backup.py

이 모듈은 파일만 읽는다(네트워크 없음). 못 찾으면 None을 돌려주고, 부르는 쪽이 원래 대체 경로(브라우저 음성·규칙 판정)로 간다.
"""
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # server/
BACKUP = Path(os.getenv("SIM_BACKUP_DIR", str(ROOT / "backup")))
DEFAULT_VOICE = "caller_male"
_GRADES = ("정답", "중답", "오답")


def tts_key(text: str, tone: str | None = None, voice: str | None = None) -> str:
    voice = voice or os.getenv("SIM_TTS_VOICE", "") or DEFAULT_VOICE
    if voice == "default":
        voice = DEFAULT_VOICE
    return hashlib.sha256(f"{voice}|{tone or ''}|{text}".encode()).hexdigest()[:32]


def tts(text: str, tone: str | None = None, voice: str | None = None) -> tuple[bytes, str] | None:
    """미리 만든 대사 음성. 없으면 None."""
    path = BACKUP / "tts" / f"{tts_key(text, tone, voice)}.mp3"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return (data, "audio/mpeg") if len(data) > 1000 else None  # empty/broken file -> not a backup


# STT가 숫자를 한글로 적거나 흔한 소리 나는 대로 적은 것을 맞춘다(Argon 검토 11-01).
_SPOKEN = [("일일이", "112"), ("일삼공일", "1301"), ("일삼삼이", "1332"), ("일삼구사", "1394"),
           ("할께", "할게"), ("볼께", "볼게"), ("줄께", "줄게"), ("갈께", "갈게"), ("드릴께", "드릴게")]


def norm_answer(text: str) -> str:
    """판정 찾기용: 공백·문장부호를 지우고 소문자로, 숫자 읽기·흔한 철자를 한 가지로."""
    out = re.sub(r"[\s\.,!?~…·'\"“”‘’()\-]+", "", (text or "").lower())
    for spoken, canon in _SPOKEN:
        out = out.replace(spoken, canon)
    return out


@lru_cache(maxsize=4)
def _judge_table_at(mtime: float) -> dict:
    return json.loads((BACKUP / "judge.json").read_text(encoding="utf-8"))


def _judge_table() -> dict:
    """파일이 바뀌면 다시 읽고, 파일이 없을 때의 빈 결과는 캐시하지 않는다."""
    path = BACKUP / "judge.json"
    try:
        return _judge_table_at(path.stat().st_mtime)
    except (OSError, ValueError):  # missing, unreadable or half-written file -> no backup, never an exception
        return {}


def judge(scenario_id: str, node_id: str, text: str) -> dict | None:
    """같은 장면에서 미리 판정해 둔 답이면 그 판정, 없으면 None(부르는 쪽이 규칙·기본값으로)."""
    table, key = _judge_table(), norm_answer(text)
    if not key:
        return None
    hit = table.get(f"{scenario_id}|{node_id}|{key}")
    if not isinstance(hit, dict) or hit.get("grade") not in _GRADES or not isinstance(hit.get("intent"), str):
        return None
    try:
        conf = min(1.0, max(0.0, float(hit.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"grade": hit["grade"], "intent": hit["intent"], "confidence": conf}


def video(name: str) -> Path | None:
    """저장한 영상(이름은 영문 소문자·숫자·밑줄만, 폴더 밖 경로 차단)."""
    if not re.fullmatch(r"[a-z0-9_]{1,64}", name or ""):
        return None
    path = BACKUP / "video" / f"{name}.mp4"
    return path if path.is_file() else None
