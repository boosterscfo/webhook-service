#!/bin/bash
# Auto-commit hook: 변경사항 있을 때만 commit + push

cd "$(git rev-parse --show-toplevel)" || exit 0

# bkit 관련 파일만 변경된 경우 스킵
changes=$(git status --porcelain)
if [ -z "$changes" ]; then
  exit 0
fi

non_bkit_changes=$(echo "$changes" | grep -v -E '(\.bkit-|\.pdca-|/agent-memory/|bkit)')
if [ -z "$non_bkit_changes" ]; then
  exit 0
fi

timestamp=$(date '+%Y-%m-%d %H:%M:%S')
git add -A
git commit -m "auto: ${timestamp} claude code session"
git push
