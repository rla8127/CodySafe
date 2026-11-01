"""예비 자료(O-2의 guard.sim.backup: 임대 GPU로 미리 만든 대사 음성·판정·영상) 연결.

- SIM_BACKUP_FIRST=1이면 예비 자료를 임대 GPU보다 먼저 쓴다(발표·작동 영상, 11-01 호연 결정).
- 0이어도 임대 GPU가 없거나 실패하면 예비 자료를 쓰고, 그것도 없으면 원래 대체 경로(브라우저 음성·규칙 기본값)로 간다.
- 예비 모듈이나 파일이 없으면 모두 None을 돌려준다(이 브랜치만으로도 돈다).
"""
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("guard.sim")
VIDEO_NAME = re.compile(r"^[a-z0-9_]{1,40}$")


def first() -> bool:
    return os.getenv("SIM_BACKUP_FIRST", "0").strip() == "1"


def module():
    try:
        from . import backup
    except Exception:
        return None
    return backup


def _call(name: str, *args):
    mod = module()
    if mod is None:
        return None
    try:
        return getattr(mod, name)(*args)
    except Exception as exc:  # 예비 자료 문제로 훈련이 멈추지 않게 한다
        log.warning("sim 예비 자료 %s 실패: %s", name, type(exc).__name__)
        return None


def tts(text: str, tone: str | None) -> tuple[bytes, str] | None:
    return _call("tts", text, tone)


def judge(scenario_id: str, node_id: str, text: str) -> dict | None:
    return _call("judge", scenario_id, node_id, text)


def video(name: str) -> Path | None:
    return _call("video", name) if VIDEO_NAME.match(name or "") else None


def ready() -> dict:
    """화면·/v1/sim/caps에 알릴 예비 자료 상태."""
    mod = module()
    root = Path(getattr(mod, "BACKUP", "")) if mod is not None else None
    if root is None or not root.is_dir():
        return {"tts": False, "judge": False, "video": []}
    return {
        "tts": any((root / "tts").glob("*.mp3")),
        "judge": (root / "judge.json").is_file(),
        "video": sorted(p.stem for p in (root / "video").glob("*.mp4")),
    }
