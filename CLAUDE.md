# CLAUDE.md

## Git 커밋 규칙

- **기능 단위 커밋 분리**: 하나의 커밋에 하나의 기능/수정만 포함
- **Conventional Commit 형식**: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `style:`, `test:`
- **작업 완료 시 push 필수**
- **bkit 관련 파일만 변경 시 커밋 불필요**: `.bkit-*`, `.pdca-*`, `agent-memory/` 등 bkit 메타데이터만 변경된 경우 스킵
- 커밋 메시지는 한글로 간결하게 작성
