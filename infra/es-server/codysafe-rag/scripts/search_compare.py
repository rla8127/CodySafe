#!/usr/bin/env python3
"""BM25 / kNN / 앱 쪽 RRF 비교. 질문 임베딩은 적재와 동일 설정(bge-m3, 정규화)을 쓴다."""
import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."), ".env"))
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

QUERIES = ["금감원 직원이라며 앱 설치하라고 해요", "상품권 사면 대출해 준다는데 사기인가요",
           "자녀 우는 목소리로 돈을 보내라는 전화", "주식 리딩방에서 수익 인증을 보여줘요"]
SRC = ["title", "scam_type", "source_tier", "source_url", "published_at"]
es = Elasticsearch(os.environ["ES_URL"], basic_auth=("scam_rag_app", os.environ["SCAM_RAG_APP_PASSWORD"]))
m = SentenceTransformer("BAAI/bge-m3", device="cpu"); m.max_seq_length = 512
IDX, K = "scam_knowledge", 20


def bm25(q, flt=None):
    qq = {"multi_match": {"query": q, "fields": ["title^2", "content", "summary"]}}
    if flt: qq = {"bool": {"must": qq, "filter": flt}}
    return es.search(index=IDX, size=K, query=qq, _source=SRC)["hits"]["hits"]


def knn(q, vec, flt=None):
    kn = {"field": "embedding", "query_vector": vec, "k": K, "num_candidates": 100}
    if flt: kn["filter"] = flt
    return es.search(index=IDX, size=K, knn=kn, _source=SRC)["hits"]["hits"]


def rrf(*lists, c=60):
    sc, doc = {}, {}
    for l in lists:
        for r, h in enumerate(l):
            sc[h["_id"]] = sc.get(h["_id"], 0) + 1 / (c + r + 1); doc[h["_id"]] = h
    return [doc[i] for i in sorted(sc, key=sc.get, reverse=True)]


def show(name, hits):
    print(f"  [{name}]")
    for h in hits[:3]:
        s = h["_source"]; print(f"    - {s['title'][:42]} | {s['scam_type']} | {s['source_url'][-34:]}")


if __name__ == "__main__":
    for q in QUERIES:
        v = m.encode([q], normalize_embeddings=True)[0].tolist()
        b, k = bm25(q), knn(q, v)
        print(f"\nQ: {q}"); show("BM25", b); show("kNN", k); show("RRF", rrf(b, k))
    # published_at 필터
    flt = [{"range": {"published_at": {"gte": "2025-01-01"}}}]
    v = m.encode([QUERIES[0]], normalize_embeddings=True)[0].tolist()
    print("\n[published_at >= 2025-01-01 필터]")
    for name, hits in (("BM25", bm25(QUERIES[0], flt)), ("kNN", knn(QUERIES[0], v, flt))):
        print(" ", name, [(h["_source"]["published_at"], h["_source"]["title"][:20]) for h in hits])
