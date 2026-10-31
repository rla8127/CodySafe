# 사기 사례 검색 서버 인프라

`GUARD_RAG_URL`로 연결하는 Elasticsearch 검색 서버의 EC2, 보안 그룹, 고정 IP를 만듭니다.

```bash
terraform init
terraform apply -var key_name=<키페어> \
  -var 'ssh_allowed_cidrs=["<IP>/32"]' -var 'es_allowed_cidrs=["<IP>/32"]' -var 'rag_allowed_cidrs=["<앱 서버 IP>/32"]'
```

Elasticsearch 실행 설정과 검색 API 코드는 이 폴더에 없습니다.
