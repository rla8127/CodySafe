"""환경 변수 설정. 기본값은 AWS 없이 도는 테스트 모드입니다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = os.getenv("GUARD_DB", str(ROOT / "data" / "guard.db"))
LOCAL_AUDIO_DIR = Path(os.getenv("GUARD_LOCAL_AUDIO_DIR", str(ROOT / "data" / "audio")))
PUBLIC_BASE_URL = os.getenv("GUARD_PUBLIC_BASE_URL", "http://localhost:8091").rstrip("/")
ADMIN_TOKEN = os.getenv("GUARD_ADMIN_TOKEN", "")
AWS_REGION = os.getenv("GUARD_AWS_REGION", "ap-northeast-2")

STORAGE = os.getenv("GUARD_STORAGE", "local")  # local | s3
S3_BUCKET = os.getenv("GUARD_S3_BUCKET", "")
STT = os.getenv("GUARD_STT", "text")  # text | transcribe
LLM = os.getenv("GUARD_LLM", "rule")  # rule | bedrock
EMBED = os.getenv("GUARD_EMBED", "hash")  # hash | titan

CLAUDE_MODEL = os.getenv("GUARD_CLAUDE_MODEL", "global.anthropic.claude-opus-5-5")
CLAUDE_REGION = os.getenv("GUARD_CLAUDE_REGION", AWS_REGION)
TITAN_MODEL = os.getenv("GUARD_TITAN_MODEL", "amazon.titan-embed-text-v2:0")

# 오탐 알림은 가족에게 실제 불안을 주므로, 이 값 미만이면 알림 대신 사람 검토로 보냅니다.
ALERT_THRESHOLD = float(os.getenv("GUARD_ALERT_THRESHOLD", "0.7"))
MAX_UPLOAD_BYTES = int(os.getenv("GUARD_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
AUDIO_EXTENSIONS = {"m4a", "mp3", "mp4", "wav", "flac", "ogg", "amr", "webm"}
TEXT_EXTENSIONS = {"txt"}  # GUARD_STT=text 테스트 전용
