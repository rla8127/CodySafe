"""가족 암구호. 연결된 가족 전체가 같은 단어를 보고, 한국 시간 0시에 바뀝니다."""
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ADJECTIVES = [
    "파란", "빨간", "노란", "초록", "하얀", "작은", "커다란", "따뜻한", "시원한", "달콤한", "포근한", "귀여운", "용감한", "씩씩한", "반짝이는", "조용한",
    "즐거운", "행복한", "동그란", "부지런한", "향긋한", "든든한", "느긋한", "상냥한", "말랑한", "푸른", "맑은", "고소한", "새콤한", "튼튼한", "신나는", "날쌘",
]
NOUNS = [
    "고래", "호랑이", "토끼", "강아지", "고양이", "다람쥐", "참새", "거북이", "사과", "포도", "감자", "고구마", "수박", "딸기", "호두", "밤송이",
    "소나무", "민들레", "해바라기", "단풍잎", "구름", "무지개", "바다", "달님", "별빛", "우산", "연필", "기차", "자전거", "주전자", "항아리", "솜사탕",
]


def now_kst() -> datetime:
    return datetime.now(KST)


def members(conn: sqlite3.Connection, device_id: str) -> list[str]:
    """형제처럼 직접 연결되지 않아도 같은 가족이면 같은 암구호를 보도록 연결 전체를 묶습니다."""
    seen, queue = {device_id}, [device_id]
    while queue:
        current = queue.pop()
        rows = conn.execute(
            "SELECT protected_id, guardian_id FROM family_links WHERE protected_id = ? OR guardian_id = ?",
            (current, current),
        ).fetchall()
        for row in rows:
            for other in row:
                if other not in seen:
                    seen.add(other)
                    queue.append(other)
    return sorted(seen)


def words(key: bytes, group: list[str], day: str) -> list[str]:
    digest = hmac.new(key, f"{group[0]}|{day}".encode(), hashlib.sha256).digest()
    return [ADJECTIVES[digest[0] % len(ADJECTIVES)], NOUNS[digest[1] % len(NOUNS)]]


def _normalize(answer: str) -> bytes:
    return "".join(answer.split()).lower().encode()


def hash_answer(answer: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.scrypt(_normalize(answer), salt=salt, n=2**14, r=8, p=1)
