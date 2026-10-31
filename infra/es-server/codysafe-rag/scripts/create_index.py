#!/usr/bin/env python3
"""scam_knowledge_v1 인덱스, 별칭, 앱 계정(scam_rag_app)을 만든다. 이미 있으면 건너뛴다. elastic 계정으로 1회 실행."""
import os, sys
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, NotFoundError

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
es = Elasticsearch(os.environ["ES_URL"], basic_auth=("elastic", os.environ["ELASTIC_PASSWORD"]))
INDEX, ALIAS = "scam_knowledge_v1", "scam_knowledge"
ko = lambda: {"type": "text", "analyzer": "ko"}
body = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0, "analysis": {
        "tokenizer": {"nori_mixed": {"type": "nori_tokenizer", "decompound_mode": "mixed"}},
        "analyzer": {"ko": {"type": "custom", "tokenizer": "nori_mixed", "filter": ["lowercase", "nori_readingform"]}}}},
    "mappings": {"properties": {
        "title": ko(), "content": ko(), "summary": ko(), "method_steps": ko(), "warning_signs": ko(), "response_guide": ko(),
        "scam_type": {"type": "keyword"}, "impersonated_target": {"type": "keyword"}, "channel": {"type": "keyword"},
        "source_tier": {"type": "keyword"}, "source_name": {"type": "keyword"}, "source_url": {"type": "keyword"},
        "content_hash": {"type": "keyword"}, "data_period": {"type": "keyword"},
        "published_at": {"type": "date"}, "collected_at": {"type": "date"},
        "embedding": {"type": "dense_vector", "dims": 1024, "index": True, "similarity": "cosine"}}},
}
if es.indices.exists(index=INDEX):
    print(f"index {INDEX} exists, skip")
else:
    es.indices.create(index=INDEX, **body); es.indices.put_alias(index=INDEX, name=ALIAS); print("created", INDEX, "+ alias", ALIAS)
es.security.put_role(name="scam_rag_rw", indices=[{"names": ["scam_knowledge", "scam_knowledge_*"],
                     "privileges": ["read", "write", "create_index", "view_index_metadata"]}])
es.security.put_user(username="scam_rag_app", password=os.environ["SCAM_RAG_APP_PASSWORD"], roles=["scam_rag_rw"])
print("role/user scam_rag_app ok")
