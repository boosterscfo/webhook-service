# Plan+: jobs와 amz_researcher 병렬 구조 — 향후 방향 아이디어

> **목적**: (1) **jobs에 둘 것**과 **프로젝트급으로 올라올 것**을 프로젝트에서 명확히 구분하고, (2) **uv와 동일 환경에서 lib 리소스를 공유**하는 전제를 유지하며, (3) **AI가 .claude.md(CLAUDE.md) 등으로 작업할 때 “어디에 넣을지” 분기할 수 있는 구조**를 프로젝트에 명시하는 것.

현재 `app.router`(일반 웹훅)와 `amz_researcher.router`(도메인 API)가 동일 앱에 병렬로 연결된 상태에서, 이 구분을 문서·규칙으로 고정하고 확장 시 일관되게 적용하는 방향을 정리한다.

**분기 규칙 요약**: 프로젝트 루트의 **`CLAUDE.md`**에 “jobs vs 프로젝트급 도메인” 기준과 분기 체크리스트가 정의되어 있음. 새 코드 배치 시 해당 규칙을 따른다.

---

## 1. 현재 구조 요약

### 1.1 진입점

| 진입점 | 경로 | 역할 |
|--------|------|------|
| **일반 웹훅** | `POST /webhook` | payload의 `job` + `function`으로 `jobs.{job_name}.{function_name}` 동적 호출 |
| **Amazon Researcher** | `POST /slack/amz`, `/slack/amz/interact`, `POST /webhook/brightdata`, `POST /research` | Slack 슬래시 커맨드, Bright Data 콜백, 테스트용 분석 API |

- `main.py`에서 두 라우터를 prefix 없이 동시에 마운트.
- **jobs**: 루트 `jobs/` 패키지 (cash_mgmt, upload_financial_db, global_boosta, meta_ads_manager, ad_migration).
- **amz_researcher**: 별도 패키지 — 라우터 + 서비스 + `amz_researcher/jobs/collect.py`(CLI/배치용, 웹훅 미사용).

### 1.2 의존성 관계

```
main.py
├── app.router          → jobs.* (ALLOWED_JOBS 화이트리스트)
│   └── app.config, lib.* (mysql_connector, slack, google_sheet)
└── amz_researcher.router → amz_researcher.*
    └── app.config, lib.mysql_connector, amz_researcher.services.*
```

- **공통**: `app.config`, `lib.mysql_connector`.
- **jobs 전용**: `lib.slack`(SlackNotifier), `lib.google_sheet`.
- **amz_researcher 전용**: `amz_researcher.services.slack_sender`, 자체 모델·서비스·오케스트레이터.

### 1.3 정리

- **일반 웹훅**: “job 이름 + 함수 이름” 기반 단일 엔드포인트, 등록형(jobs만).
- **amz_researcher**: 도메인 전용 라우트 여러 개, Slack/Bright Data 등 외부 연동이 API 설계에 반영됨.
- amz_researcher의 배치 작업(`collect`)은 `python -m amz_researcher.jobs.collect`로만 실행되며, `/webhook`에는 등록되어 있지 않음.

---

## 2. 향후 방향 아이디어

### 옵션 A: 현 구조 유지 + 계약 명확화 (단기)

**내용**
- “일반 웹훅(jobs)”와 “도메인 앱(amz_researcher)”를 병렬로 두고, 역할만 문서로 고정.
- `ALLOWED_JOBS`와 amz_researcher 라우트 목록을 한곳(또는 README/아키텍처 문서)에 정리.
- 필요 시 amz_researcher 라우터만 `prefix="/amz"` 등으로 묶어서 경로 그룹만 명확히 함.

**장점**: 변경 최소, 리스크 낮음.  
**단점**: 진입점이 둘로 나뉜 상태 유지, 새 “도메인” 추가 시 패턴이 계속 불명확해질 수 있음.

**적합**: 당분간 구조 변경 없이 안정화만 원할 때.

---

### 옵션 B: 도메인 라우터를 prefix로 분리 (단기)

**내용**
- `app.include_router(amz_router, prefix="/amz")` 로 변경.
- amz_researcher 쪽 경로: `/amz/slack/...`, `/amz/webhook/brightdata`, `/amz/research` 등.
- `/webhook`은 그대로 “일반 job 실행” 전용으로 유지.

**장점**: URL만 봐도 “일반 웹훅” vs “Amazon Researcher” 구분 가능, 향후 다른 도메인(예: `/meta/...`) 추가 시 패턴 일관.  
**단점**: Slack/Bright Data 등 외부에서 이미 URL을 쓰고 있다면 해당 URL 변경 필요.

**적합**: URL 체계를 정리하고 싶을 때, 외부 URL 변경이 가능한 경우.

---

### 옵션 C: 단일 Job 레지스트리로 통합 (중기)

**내용**
- “job” 개념을 확장해, `jobs.*`뿐 아니라 `amz_researcher`의 실행 가능 단위도 레지스트리에 등록.
- 예: `job=amz_researcher`, `function=run_collect` 또는 `run_analysis` 등으로 `POST /webhook`에서 디스패치.
- Slack/Bright Data는 그대로 amz_researcher 라우터가 받고, “무거운 실행”만 웹훅으로 트리거할 수 있게 할지 선택.

**장점**: 실행 진입점을 `/webhook` 하나로 맞추면, 인증·로깅·재시도·모니터링을 한 곳에서 적용하기 쉬움.  
**단점**: amz_researcher는 “함수 하나”가 아니라 Slack 플로우·콜백 등 상태 있는 API라, 전부 웹훅 패턴에 넣기엔 무리일 수 있음. “배치/헤비 태스크만” 웹훅으로 넣는 식으로 제한하면 구현 가능.

**적합**: n8n 등에서 “amz 수집/분석”을 웹훅으로만 트리거하고 싶을 때.

---

### 옵션 D: 공통 Job Runner 추상화 (중·장기)

**내용**
- “실행 단위”를 Job(이름, payload, 옵션)으로 추상화하고, `JobRunner`(인메모리 큐 또는 Celery/ARQ 등)가 실행.
- `POST /webhook`: payload 검증 후 JobRunner.enqueue(job_name, function, payload) → 즉시 202 + job_id.
- 기존 `jobs.*`와 amz_researcher의 특정 함수를 모두 “Job”으로 등록.
- Slack/블록킹 분석 등은 기존처럼 해당 라우터가 받고, 내부에서 필요 시 JobRunner.enqueue만 호출할 수 있게 함.

**장점**: 나중에 스케일 아웃(워커 분리, 재시도, 우선순위) 시 Runner만 교체하면 됨.  
**단점**: 설계·구현 비용이 큼. 당장은 과할 수 있음.

**적합**: 웹훅 호출이 많아지거나, 장시간 작업을 비동기로 빼고 싶을 때.

---

### 옵션 E: 도메인 모듈로 점진적 이전 (중기)

**내용**
- “일반 웹훅” 대상을 `jobs/` 플랫 구조에서 “도메인 모듈”로 옮김.
- 예: `domains/cash_mgmt/`, `domains/meta_ads/` 등에 각각 `router.py` + `tasks.py`(기존 job 함수들) 배치.
- `app.router`는 `ALLOWED_JOBS` 대신 “도메인별 job 레지스트리”를 참고하거나, 각 도메인의 router를 `include_router(domain.router, prefix="/webhook/...")` 형태로 마운트.

**장점**: amz_researcher와 동일하게 “도메인 = 라우터 + 서비스 + job” 구조로 통일.  
**단점**: 기존 jobs 전부 이동·리그레션 필요.

**적합**: 새 기능은 도메인 단위로 넣고, 기존 jobs는 점진적으로만 옮길 때.

---

### 옵션 F: 앱 분리 (webhooks vs amz-researcher) (장기)

**내용**
- 저장소는 하나(모노레포)로 두되, 배포 단위를 둘로 나눔.
  - **webhooks**: `/webhook` + 기존 jobs만 담당하는 경량 FastAPI 앱.
  - **amz-researcher**: Slack/Bright Data/분석 API만 담당하는 FastAPI 앱.
- 공통 코드는 `lib/`, `app.config` 등을 패키지로 두고 두 앱이 의존.

**장점**: 스케일·배포·장애 격리 분리 가능.  
**단점**: 배포·환경 변수·네트워크가 두 벌로 늘어남.

**적합**: 트래픽이나 팀이 나뉘거나, amz_researcher만 따로 스케일하고 싶을 때.

---

## 3. 권장 조합 (단계별)

| 단계 | 액션 | 선택 옵션 |
|------|------|-----------|
| **즉시** | 역할 문서화, 필요 시 URL 그룹만 정리 | A + (선택) B |
| **단기** | amz 쪽 배치를 웹훅으로도 트리거하고 싶다면 | C를 “amz collect만” 웹훅 등록으로 제한 |
| **중기** | 새 도메인을 계속 추가할 계획이면 | E로 새 도메인은 `domains/` 패턴으로, 기존 jobs는 유지 또는 점진 이전 |
| **장기** | 트래픽/배포 분리가 필요해지면 | D(Job Runner) 또는 F(앱 분리) 검토 |

---

## 4. 결정 시 체크리스트

- [ ] Slack/Bright Data 등 **외부에서 호출하는 URL** 변경 가능 여부 (옵션 B 시).
- [ ] **n8n 등에서 amz 수집/분석**을 웹훅으로만 돌릴 계획인지 (옵션 C 수요).
- [ ] **새 “도메인”**을 자주 추가할지, 아니면 amz_researcher가 사실상 유일한 도메인 앱인지 (옵션 E vs A 유지).
- [ ] **배포/스케일**을 지금 단일 프로세스로 갈지, 워커/앱 분리를 미리 고려할지 (옵션 D, F).

이 문서를 바탕으로 “지금은 A+B만 적용하고, 나머지는 요구가 생기면 단계적으로” 진행하는 흐름을 추천한다.

---

## 5. AI·작업자 분기 시 참조

- **코드 배치 결정(분기)** 의 단일 기준은 **루트 `CLAUDE.md`의 “프로젝트 구조 및 코드 배치 규칙”** 이다.
- 새 기능을 추가할 때: “웹훅 한 번 + job/function만 있으면 끝” → `jobs/` + `ALLOWED_JOBS` / “여러 엔드포인트·도메인 로직·외부 연동” → 도메인 패키지 + `main.py` 라우터 마운트.
- 동일 uv 환경·공통 `lib` 사용 전제는 유지하며, 구조만 jobs vs 도메인으로 명확히 나눈다.
