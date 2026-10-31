"""환경 변수 설정. 기본값은 AWS 없이 도는 테스트 모드입니다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = os.getenv("GUARD_DB", str(ROOT / "data" / "guard.db"))
LOCAL_AUDIO_DIR = Path(os.getenv("GUARD_LOCAL_AUDIO_DIR", str(ROOT / "data" / "audio")))
PUBLIC_BASE_URL = os.getenv("GUARD_PUBLIC_BASE_URL", "http://localhost:8091").rstrip("/")
# 웹 시연용 가족. 접속한 누구나 이 계정으로 들어올 수 있으니 실제 통화를 올리면 안 됩니다. 운영에서는 0으로 끕니다.
DEMO_FAMILY = os.getenv("GUARD_DEMO_FAMILY", "1") == "1"
ADMIN_TOKEN = os.getenv("GUARD_ADMIN_TOKEN", "")
AWS_REGION = os.getenv("GUARD_AWS_REGION", "ap-northeast-2")

STORAGE = os.getenv("GUARD_STORAGE", "local")  # local | s3
S3_BUCKET = os.getenv("GUARD_S3_BUCKET", "")
# 켜면 분석 뒤에도 음성을 저장소에 남깁니다. 앱의 동의 문구도 함께 바뀝니다.
KEEP_AUDIO = os.getenv("GUARD_KEEP_AUDIO", "0") == "1"
S3_REGION = os.getenv("GUARD_S3_REGION", AWS_REGION)
STT = os.getenv("GUARD_STT", "text")  # text | openai | transcribe
OPENAI_STT_MODEL = os.getenv("GUARD_OPENAI_STT_MODEL", "whisper-1")
LLM = os.getenv("GUARD_LLM", "rule")  # rule | anthropic | openai | bedrock
EMBED = os.getenv("GUARD_EMBED", "hash")  # hash | openai | titan

ANTHROPIC_MODEL = os.getenv("GUARD_ANTHROPIC_MODEL", "claude-opus-5-5")
OPENAI_MODEL = os.getenv("GUARD_OPENAI_MODEL", "")  # GUARD_LLM=openai일 때 필수
OPENAI_EMBED_MODEL = os.getenv("GUARD_OPENAI_EMBED_MODEL", "text-embedding-3-small")
CLAUDE_MODEL = os.getenv("GUARD_CLAUDE_MODEL", "global.anthropic.claude-opus-5-5")
CLAUDE_REGION = os.getenv("GUARD_CLAUDE_REGION", AWS_REGION)
TITAN_MODEL = os.getenv("GUARD_TITAN_MODEL", "amazon.titan-embed-text-v2:0")

# 오탐 알림은 가족에게 실제 불안을 주므로, 이 값 미만이면 알림 대신 사람 검토로 보냅니다.
ALERT_THRESHOLD = float(os.getenv("GUARD_ALERT_THRESHOLD", "0.7"))
# 잠금은 알림보다 오탐 피해가 크므로 기준을 더 높게 둡니다.
LOCK_THRESHOLD = float(os.getenv("GUARD_LOCK_THRESHOLD", "0.9"))
LOCK_SECONDS = int(os.getenv("GUARD_LOCK_SECONDS", "3600"))
LOCK_RELEASE_WAIT = int(os.getenv("GUARD_LOCK_RELEASE_WAIT", "600"))
MAX_UPLOAD_BYTES = int(os.getenv("GUARD_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
AUDIO_EXTENSIONS = {"m4a", "mp3", "mp4", "wav", "flac", "ogg", "amr", "webm"}
OPENAI_STT_EXTENSIONS = {"m4a", "mp3", "mp4", "wav", "flac", "ogg", "webm"}
OPENAI_STT_MAX_BYTES = 25 * 1024 * 1024  # OpenAI 전사 API의 파일 크기 제한
TEXT_EXTENSIONS = {"txt"}  # GUARD_STT=text 테스트 전용
