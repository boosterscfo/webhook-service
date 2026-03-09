# CLAUDE.md

## 프로젝트 구조 및 코드 배치 규칙 (분기 기준)

이 프로젝트는 **단일 uv 환경**에서 **lib 리소스를 공유**하며, 코드는 다음 두 가지로 구분된다. 새 기능을 추가할 때 아래 기준으로 배치 위치를 결정한다.

### jobs (웹훅 태스크)

| 기준 | 설명 |
|------|------|
| **위치** | 루트 `jobs/` 패키지 (`jobs/{job_name}.py`) |
| **진입** | `POST /webhook` — payload의 `job` + `function`으로 `jobs.{job_name}.{function_name}` 호출 |
| **등록** | `app/router.py`의 `ALLOWED_JOBS`에 화이트리스트 추가 필요 |

**jobs에 넣을 것**
- 외부(n8n, 스케줄러 등)에서 **웹훅 한 번**으로 호출하는 단순 태스크
- **입력: JSON payload → 출력: 결과 한 번** 구조 (동기, 짧은 실행)
- 공통 `lib`(mysql_connector, slack, google_sheet)만 쓰고, **자체 라우터·여러 엔드포인트가 필요 없음**
- 예: 시트→DB 동기화, 광고 데이터 갱신, 알림 전송

### 프로젝트급 도메인 (도메인 모듈)

| 기준 | 설명 |
|------|------|
| **위치** | 루트에 패키지로 둠 (예: `amz_researcher/`) |
| **진입** | 자체 라우터를 `main.py`에서 `include_router`로 마운트 (예: `/slack/amz`, `/webhook/brightdata`) |
| **구조** | `router.py` + `services/` + 필요 시 `models.py`, `jobs/`(CLI·배치용) |

**프로젝트급 도메인으로 올릴 것**
- **자체 API·엔드포인트가 여러 개** 필요함 (Slack 슬래시, 콜백, 테스트용 API 등)
- **도메인 모델·서비스 레이어**가 있고, lib 외에 전용 로직이 많음
- **상태 있는 플로우** 또는 **외부 서비스와의 다단계 연동**(예: Bright Data 웹훅 → DB → Slack)
- 같은 uv 환경·같은 `lib`(및 `app.config`)를 쓰되, **진입점·라우팅이 웹훅 단일 엔드포인트와 다름**

**분기 체크리스트 (새 기능 추가 시)**
1. “웹훅 하나로 job+function만 호출하면 끝”인가? → **jobs**에 모듈 추가 + `ALLOWED_JOBS` 등록
2. “여러 URL·Slack/외부 콜백·도메인 전용 로직”이 필요한가? → **새 도메인 패키지** 생성 후 `main.py`에 라우터 마운트

참고: 구조 상세·옵션은 `docs/01-plan/structure-jobs-amz-researcher.plan.md` 참고.

---

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
