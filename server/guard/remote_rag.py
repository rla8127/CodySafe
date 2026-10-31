"""ES 서버의 사기 수법 검색 API를 호출합니다. 실패해도 예외를 던지지 않아 분석은 LLM만으로 이어집니다."""
import logging

import httpx

from . import config

log = logging.getLogger("guard.rag")


def search(query: str) -> list[dict]:
    if not config.RAG_URL:
        log.info("RAG 꺼짐: GUARD_RAG_URL 없음")
        return []
    try:
        response = httpx.post(
            f"{config.RAG_URL}/v1/search",
            headers={"x-api-key": config.RAG_API_KEY},
            json={"query": query, "top": config.RAG_TOP},
            timeout=config.RAG_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        # 통화 내용이 로그에 남지 않도록 예외 종류만 기록합니다.
        log.warning("RAG 실패, LLM만 호출합니다: %s", type(exc).__name__)
        return []
    hits = data["hits"]
    log.info("RAG 성공 mode=%s hits=%d took_ms=%s titles=%s", data["mode"], len(hits), data["took_ms"], [h["title"] for h in hits])
    return hits


def format_reference(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        lines = [f"제목: {h['title']}", f"유형: {h.get('scam_type')}", f"요약: {h.get('summary')}"]
        if h.get("warning_signs"):
            lines.append(f"경고 신호: {h['warning_signs']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
