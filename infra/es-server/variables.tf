variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "availability_zone" {
  type    = string
  default = "ap-northeast-2a"
}

variable "name_prefix" {
  description = "공유 계정이므로 다른 사람 리소스와 겹치지 않는 이름"
  type        = string
  default     = "codysafe-es"
}

variable "instance_type" {
  description = "t4g.medium: vCPU 2, RAM 4GB (ARM). ES 힙 2GB 이하 기준"
  type        = string
  default     = "t4g.medium"
}

variable "root_volume_gb" {
  type    = number
  default = 50
}

variable "key_name" {
  description = "SSH 키페어"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "SSH 접근 허용 IP"
  type        = list(string)
}

variable "es_allowed_cidrs" {
  description = "Elasticsearch 9200 접근 허용 IP. 앱 서버 IP를 여기에 추가"
  type        = list(string)
}

variable "es_port" {
  type    = number
  default = 9200
}

variable "rag_allowed_cidrs" {
  description = "RAG 검색 API 접근 허용 IP. 앱 서버 IP"
  type        = list(string)
}

variable "rag_port" {
  type    = number
  default = 8200
}
