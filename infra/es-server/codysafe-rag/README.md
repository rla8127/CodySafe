# 사기 수법 RAG (Elasticsearch + 검색 API)

```
docker-compose.yml, Dockerfile.es   Elasticsearch 8.17.0 단일 노드 (nori 플러그인 포함), 127.0.0.1:9200, 보안 켬
app/rag_api.py                      검색 API, 포트 8200, POST /v1/search, GET /health
scripts/create_index.py             인덱스 scam_knowledge_v1 + 별칭 + 앱 계정 생성 (1회)
scripts/ingest.py                   수집 -> LLM 분류/구조화 -> bge-m3 임베딩 -> _bulk 적재
scripts/search_compare.py           BM25 / kNN / RRF 비교
requirements.txt, .env.example
```

## 실행 순서

```bash
cp .env.example .env                      # 비밀번호, 키 채우기 (.env 는 커밋 금지)
docker compose up -d --build              # ES 기동
pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install -r requirements.txt
python scripts/create_index.py            # 인덱스, 별칭, scam_rag_app 계정
python scripts/ingest.py --dry-run --max 7 --pdf 2   # 검토 후
python scripts/ingest.py --max 100        # 적재
uvicorn app.rag_api:app --env-file .env --host 127.0.0.1 --port 8200
```

`ingest.py`는 이미 적재된 `source_url`을 LLM 호출 전에 건너뛰므로 재실행해도 문서가 늘지 않는다.

## 검색 API

```bash
curl -s localhost:8200/v1/search -H "x-api-key: $RAG_API_KEY" -H 'Content-Type: application/json' \
  -d '{"query":"금감원 직원이라며 앱 설치하라고 해요","top":3}'
```

BM25와 kNN 결과를 앱에서 RRF(k=60)로 합친다. 임베딩 모델을 아직 못 불러왔으면 BM25만 쓰고 응답의 `mode`에 `bm25`로 표시한다.
`RAG_EXCLUDE_SOURCES`에 적힌 출처(내부 학습 전용)는 검색 결과에서 제외된다.

## 임베딩 설정 (질문 임베딩에도 동일하게)

`BAAI/bge-m3`, 1024차원, `normalize_embeddings=True`, `max_seq_length=512`, 문서는 `title + "\n" + content`, 질문은 문장 그대로, 유사도는 cosine.

## 주의

- 실제 인덱스 `scam_knowledge_v1`, 앱은 별칭 `scam_knowledge`로만 접근한다.
- 데이터에는 팀 내부 전용 전사 요약(07)이 섞여 있다. 원문은 저장하지 않지만, 공개 서비스에는 노출하지 않는다.
- 상담 합성 데이터(08)는 "KISA 상담 기반 합성 데이터"로 표기한다.
- 메모리: ES 힙 1GB + bge-m3 약 1.6GB. 4GB 서버에서는 스왑이 필요하다.
