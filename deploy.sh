#!/bin/bash
# webhook-service 배포 스크립트
# 사용: ./deploy.sh

set -e
cd "$(dirname "$0")"

echo "==> git pull"
git pull

echo "==> Docker 빌드"
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

echo "==> 컨테이너 재기동"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "==> 배포 완료"
echo "확인: curl -sf https://sidehook.boosters-labs.com/health"
