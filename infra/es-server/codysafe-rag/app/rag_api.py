"""사기 수법 검색 API. BM25와 kNN을 앱 쪽 RRF로 합치고, 임베딩을 못 쓰면 BM25만 쓴다."""
import hmac
import logging
import os
import threading
import time

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("uvicorn.error")

ES_URL = os.environ.get("ES_URL", "http://127.0.0.1:9200")
ES_AUTH = ("scam_rag_app", os.environ["SCAM_RAG_APP_PASSWORD"])
RAG_API_KEY = os.environ["RAG_API_KEY"]
INDEX = "scam_knowledge"
RRF_K = 60
CANDIDATES = 20
MAX_QUERY_CHARS = 2000
# 내부 학습 전용 데이터는 공개 시연 답변에 쓰지 않는다.
EXCLUDE_SOURCES = [s for s in os.environ.get("RAG_EXCLUDE_SOURCES", "금감원 공개 녹음 전사(KorCCVi, 내부 학습용)").split("|") if s]
FIELDS = ["title", "scam_type", "summary", "method_steps", "warning_signs", "response_guide", "source_name", "source_tier", "source_url", "published_at"]

app = FastAPI(title="Scam RAG API")
embedder = None
es = httpx.Client(timeout=5, auth=ES_AUTH)


def load_embedder() -> None:
    global embedder
    try:
        from sentence_transformers import SentenceTransformer

        m = SentenceTransformer("BAAI/bge-m3", device="cpu")
        m.max_seq_length = 512
        m.encode(["준비"], normalize_embeddings=True)
        embedder = m
        log.info("embedder ready")
    except Exception:
        log.exception("embedder load failed, BM25 only")


threading.Thread(target=load_embedder, daemon=True).start()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top: int = Field(default=3, ge=1, le=10)


def es_search(body: dict) -> list[dict]:
    res = es.post(f"{ES_URL}/{INDEX}/_search", json={"size": CANDIDATES, "_source": FIELDS, **body})
    res.raise_for_status()
    return res.json()["hits"]["hits"]


@app.get("/health")
def health():
    try:
        count = es.get(f"{ES_URL}/{INDEX}/_count").json()["count"]
    except Exception:
        count = None
    return {"es_docs": count, "embedder_ready": embedder is not None, "excluded_sources": len(EXCLUDE_SOURCES)}


@app.post("/v1/search")
def search(req: SearchRequest, x_api_key: str = Header("")):
    if not hmac.compare_digest(x_api_key, RAG_API_KEY):
        raise HTTPException(401, "invalid api key")
    started = time.monotonic()
    query = req.query[:MAX_QUERY_CHARS]
    exclude = [{"terms": {"source_name": EXCLUDE_SOURCES}}] if EXCLUDE_SOURCES else []
    rankings, docs = [], {}
    try:
        hits = es_search({"query": {"bool": {
            "must": {"multi_match": {"query": query, "fields": ["title^2", "summary", "content", "warning_signs"]}},
            "must_not": exclude,
        }}})
        rankings.append([h["_id"] for h in hits])
        docs.update({h["_id"]: h["_source"] for h in hits})
    except Exception as e:
        log.error("bm25 failed: %s", type(e).__name__)
        raise HTTPException(503, "search failed")

    mode = "bm25"
    if embedder is not None:
        try:
            vec = embedder.encode([query], normalize_embeddings=True)[0].tolist()
            knn = {"field": "embedding", "query_vector": vec, "k": CANDIDATES, "num_candidates": 100}
            if exclude:
                knn["filter"] = {"bool": {"must_not": exclude}}
            hits = es_search({"knn": knn})
            rankings.append([h["_id"] for h in hits])
            docs.update({h["_id"]: h["_source"] for h in hits})
            mode = "hybrid"
        except Exception as e:
            log.error("knn failed, using bm25: %s", type(e).__name__)

    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1 / (RRF_K + rank + 1)
    ranked = sorted(scores, key=scores.get, reverse=True)[: req.top]
    took_ms = int((time.monotonic() - started) * 1000)
    # 통화 내용이 남지 않도록 질의 원문은 기록하지 않는다.
    log.info("search mode=%s query_chars=%d hits=%d took_ms=%d", mode, len(query), len(ranked), took_ms)
    return {"mode": mode, "took_ms": took_ms, "hits": [docs[i] for i in ranked]}
