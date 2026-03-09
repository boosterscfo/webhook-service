#!/usr/bin/env bash
# Amazon Researcher 주간 전체 카테고리 수집 (Bright Data 트리거 → webhook 수신)
# 크론에서 매주 월요일 실행용.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
exec uv run python -m amz_researcher.jobs.collect
