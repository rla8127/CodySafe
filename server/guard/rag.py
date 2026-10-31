"""Hybrid RAG: BM25와 벡터 검색을 RRF로 합친 뒤 reranker로 정렬합니다."""
import hashlib
import json
import math
import re
from collections import Counter

from . import config, llm
from .scam_kb import KB

RRF_K = 60
_doc_vectors: list[list[float]] | None = None


def _tokens(text: str) -> list[str]:
    """형태소 분석기 없이 한국어 어미 변화를 견디도록 음절 2-gram을 씁니다."""
    words = re.findall(r"[0-9a-z가-힣]+", text.lower())
    grams = [w[i : i + 2] for w in words for i in range(max(len(w) - 1, 1))]
    return grams


def _bm25_rank(query: str, k1: float = 1.5, b: float = 0.75) -> list[int]:
    docs = [_tokens(d["name"] + " " + d["text"]) for d in KB]
    avg = sum(map(len, docs)) / len(docs)
    df = Counter(t for doc in docs for t in set(doc))
    scores = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for t in set(_tokens(query)):
            if t in tf:
                idf = math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(doc) / avg))
        scores.append(score)
    return [i for i in sorted(range(len(KB)), key=lambda i: -scores[i]) if scores[i] > 0]


def _hash_embed(text: str, dim: int = 512) -> list[float]:
    vec = [0.0] * dim
    for t in _tokens(text):
        vec[int(hashlib.md5(t.encode()).hexdigest(), 16) % dim] += 1.0
    return vec


_bedrock = None


def _titan_embed(text: str) -> list[float]:
    global _bedrock
    if _bedrock is None:
        import boto3

        _bedrock = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)
    response = _bedrock.invoke_model(modelId=config.TITAN_MODEL, body=json.dumps({"inputText": text[:20000]}))
    return json.loads(response["body"].read())["embedding"]


_openai = None


def _openai_embed(text: str) -> list[float]:
    global _openai
    if _openai is None:
        from openai import OpenAI

        _openai = OpenAI()
    return _openai.embeddings.create(model=config.OPENAI_EMBED_MODEL, input=text[:8000]).data[0].embedding


def _embed(text: str) -> list[float]:
    if config.EMBED == "openai":
        return _openai_embed(text)
    return _titan_embed(text) if config.EMBED == "titan" else _hash_embed(text)


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def _vector_rank(query: str) -> list[int]:
    global _doc_vectors
    if _doc_vectors is None:
        _doc_vectors = [_embed(d["name"] + " " + d["text"]) for d in KB]
    q = _embed(query)
    scores = [_cosine(q, v) for v in _doc_vectors]
    return [i for i in sorted(range(len(KB)), key=lambda i: -scores[i]) if scores[i] > 0]


def retrieve(query: str, candidates: int = 5, top: int = 3) -> list[dict]:
    merged: Counter = Counter()
    for ranking in (_bm25_rank(query), _vector_rank(query)):
        for rank, i in enumerate(ranking):
            merged[i] += 1 / (RRF_K + rank + 1)
    pool = [KB[i] for i, _ in merged.most_common(candidates)]
    return llm.rerank(query, pool)[:top]
