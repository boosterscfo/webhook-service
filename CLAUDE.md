# CLAUDE.md

## Python 실행 환경

- **Python 실행은 반드시 `uv`로 수행**: 터미널에서 스크립트/서버 실행, 테스트, 의존성 설치 시 `uv run` 사용
  - 예: `uv run python script.py`, `uv run uvicorn main:app ...`, `uv run pytest`
  - 가상환경 활성화 없이 `uv run`으로 프로젝트 의존성 기준 실행

## Git 커밋 규칙

- **기능 단위 커밋 분리**: 하나의 커밋에 하나의 기능/수정만 포함
- **Conventional Commit 형식**: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `style:`, `test:`
- **작업 완료 시 push 필수**
- **bkit 관련 파일만 변경 시 커밋 불필요**: `.bkit-*`, `.pdca-*`, `agent-memory/` 등 bkit 메타데이터만 변경된 경우 스킵
- 커밋 메시지는 한글로 간결하게 작성
