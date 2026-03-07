git status와 git diff를 확인한 후, 변경사항을 기능 단위로 나누어 커밋하고 push해줘.

규칙:
1. conventional commit 형식 사용: feat:, fix:, refactor:, chore:, docs:, style:, test:
2. 하나의 커밋에 하나의 기능/수정만 포함
3. 커밋 메시지는 한글로, 간결하게 작성
4. bkit 관련 파일만 변경된 경우(.bkit-*, .pdca-*, agent-memory/) 커밋 불필요
5. 모든 커밋 완료 후 git push 실행
6. Co-Authored-By 헤더 포함

예시:
- feat: Browse.ai 상세 크롤링 파싱 로직 변경
- fix: BSR 파싱 시 None 처리 누락 수정
- refactor: checkpoint 기반 캐시를 MySQL 캐시로 대체
- chore: beautifulsoup4 의존성 추가
