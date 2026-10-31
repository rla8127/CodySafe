#!/bin/bash
# ES 실행 전제 조건만 준비한다. ES 자체는 Docker Compose로 따로 올린다.
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker ubuntu

echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-elasticsearch.conf
sysctl --system

touch /var/lib/cloud/instance/es-ready
