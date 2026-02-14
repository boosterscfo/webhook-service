# Gap Analysis: webhook-service

> Design 문서 vs 실제 구현 코드 비교 분석

**분석일**: 2026-02-14
**Design 문서**: `docs/02-design/features/webhook-service.design.md`
**Match Rate**: **98%**

---

## 1. 컴포넌트별 비교

### 1-1. `app/config.py` — Settings

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| Settings 클래스 | pydantic_settings BaseSettings | pydantic_settings BaseSettings | 100% |
| WEBHOOK_TOKEN | str | str | 100% |
| DB 환경변수 (7그룹) | CFO, BOOSTA, BOOSTAERP, BOOSTAADMIN, BOOSTAAPI, SCM, MART | 동일 | 100% |
| GOOGLE_KEY_PATH | str, 기본값 포함 | str, 기본값 포함 | 100% |
| Slack 토큰 | BOOSTA_BOT_TOKEN, META_BOT_TOKEN | 동일 | 100% |
| model_config | env_file=".env", extra="ignore" | 동일 | 100% |
| 모듈 레벨 인스턴스 | `settings = Settings()` | 동일 | 100% |

**Match: 100%**

---

### 1-2. `lib/mysql_connector.py` — MysqlConnector

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `__init__(environment)` | prefix 패턴, pymysql.connect | 동일 | 100% |
| `__enter__`/`__exit__` | context manager | 동일 | 100% |
| `read_query_table(query)` | cursor → DataFrame | 동일 | 100% |
| `upsert_data(df, table_name)` | MySQL 8.0 alias, executemany | 동일 | 100% |
| upsert 제외 컬럼 | id, created_at, updated_at | 동일 | 100% |
| `get_column_max_length()` | information_schema 조회 | 동일 | 100% |
| `close()` | cursor + connection close | 동일 | 100% |
| `update_table_with_temp_merge` | 제거 | 제거됨 | 100% |
| `connectClose()` | 미설계 | Legacy alias 추가 | -2% |

**Match: 98%**
- Minor: `connectClose()` legacy alias가 설계에 없이 추가됨. 호환성을 위한 것으로 기능에 문제 없음.

---

### 1-3. `lib/google_sheet.py` — GoogleSheetApi

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `__init__` | gspread.Client + Credentials | 동일 | 100% |
| `get_doc(url)` | open_by_url | 동일 | 100% |
| `get_dataframe(url, sheet, header, range)` | 헤더 처리, dropna | 동일 + fallback 에러처리 추가 | 100% |
| `paste_values_to_googlesheet()` | append 지원 | 동일 | 100% |
| `clear_contents()` | batch_clear | 동일 | 100% |
| `update_sheet_range()` | 범위 계산 + update | 동일 | 100% |
| `column_to_number()` | static method | 동일 | 100% |
| `number_to_column()` | static method | 동일 | 100% |
| `_make_unique_headers()` | 중복 헤더 처리 | 동일 | 100% |

**Match: 100%**

---

### 1-4. `lib/slack.py` — SlackNotifier

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `send(text, blocks, ...)` | bot_name 토큰 선택, DM 지원 | 동일 | 100% |
| `notify(text, header, ...)` | 구조화된 blocks 생성 | 동일 | 100% |
| url_button actions block | button 요소 | 동일 | 100% |
| `find_slackid(email)` | BOOSTA 환경 + admin.flex_users | 동일 | 100% |
| `_get_token()` helper | 미설계 | 내부 헬퍼 추가 | 0% (무해) |

**Match: 100%**

---

### 1-5. `app/dependencies.py` — Authentication

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `verify_webhook_token` | Header + HTTPException 401 | 동일 | 100% |

**Match: 100%**

---

### 1-6. `app/router.py` — Webhook Router

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `router = APIRouter()` | APIRouter | 동일 | 100% |
| `@router.post("/webhook")` | payload dict + Depends | 동일 | 100% |
| `execute_job()` | importlib + getattr | 동일 | 100% |
| ALLOWED_JOBS | 4개 job, 동일 키/값 | 동일 | 100% |
| 보안 검증 | job/function 허용 목록 검사 | 동일 | 100% |
| 에러 핸들링 | Slack 알림 + HTTPException 500 | 동일 | 100% |
| ERROR_CHANNEL_ID | 변수 참조 (`ERROR_CHANNEL_ID`) | 하드코딩 (`"C04FQ47F231"`) | 95% |
| 400 에러 응답 | 미설계 | job/function 누락 시 400 추가 | +5% |
| ValueError 분리 | 미설계 | 허용되지 않은 job → 400 | +5% |

**Match: 97%**
- Minor: `ERROR_CHANNEL_ID`가 상수/설정 변수 대신 문자열 리터럴로 하드코딩됨.
- Positive: 설계에 없는 400 에러 핸들링, ValueError 분리, Slack 알림 실패 시 이중 에러 방지 등 방어 코드 추가.

---

### 1-7. `main.py` — FastAPI App

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| FastAPI 인스턴스 | `title="Webhooks Service"` | 동일 | 100% |
| `include_router(router)` | router 등록 | 동일 | 100% |
| `GET /health` | `{"status": "ok"}` | 동일 | 100% |

**Match: 100%**

---

### 1-8. Jobs 마이그레이션

#### `jobs/cash_mgmt.py`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| import 경로 | `from lib.xxx` | 동일 | 100% |
| `update_table_with_temp_merge` → `upsert_data` | 대체 | 대체됨 | 100% |
| 청크 처리 (20000건) | for 루프 유지 | 동일 | 100% |
| `removeCommaNumber` | job 내 로컬 함수 | `_remove_comma_number` | 100% |
| `truncate_string_to_max_length` | job 내 로컬 함수 | `_truncate_string` | 100% |
| Context manager | MysqlConnector with문 | 동일 | 100% |
| 로깅 | StreamHandler(sys.stdout) | 동일 | 100% |

**Match: 100%**

#### `jobs/upload_financial_db.py`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `get_doc` → worksheets 목록 | 시트 목록 조회 | 동일 | 100% |
| `upsertAnyData` → `upsert_data` | 메서드명 변경 | 동일 | 100% |
| table_map (10개 매핑) | 10개 시트 → 테이블 | 동일 | 100% |
| Context manager | MysqlConnector with문 | 동일 | 100% |
| 로깅 | StreamHandler(sys.stdout) | 동일 | 100% |

**Match: 100%**

#### `jobs/global_boosta.py`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| `Helper()` → `SlackNotifier` | 정적 메서드 대체 | 동일 | 100% |
| `update_to_sheet()` | 내부 함수 유지 | 동일 | 100% |
| MysqlConnector context manager | with문 사용 | 동일 | 100% |
| SlackNotifier.find_slackid | 이메일 → Slack ID | 동일 | 100% |

**Match: 100%**

#### `jobs/meta_ads_manager.py`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| Helper → SlackNotifier 직접 사용 | 모듈 레벨 인스턴스 제거 | 동일 | 100% |
| conn.connectClose 버그 수정 | context manager 적용 | 동일 | 100% |
| slack_send() | job 내 유지 | 동일 | 100% |
| 6개 함수 구현 | update_ads, add_ad, regis/unregis_slack_send, user 버전 | 모두 구현 | 100% |

**Match: 100%**

---

### 1-9. `pyproject.toml`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| name, version, description | 동일 | 동일 | 100% |
| requires-python | >=3.13 | 동일 | 100% |
| dependencies (10개) | fastapi ~ slack-sdk | 동일 | 100% |

**Match: 100%**

---

### 1-10. `Dockerfile`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| base image | python:3.13-slim | 동일 | 100% |
| uv 복사 | ghcr.io/astral-sh/uv:latest | 동일 | 100% |
| 의존성 캐시 레이어 | pyproject.toml + uv.lock 먼저 | 동일 | 100% |
| 소스 선택적 복사 | main.py, app/, lib/, jobs/ | 동일 | 100% |
| EXPOSE + CMD | 9000, uvicorn | 동일 | 100% |

**Match: 100%**

---

### 1-11. `docker-compose.yml`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| service: webhooks | build, container_name | 동일 | 100% |
| ports | 9000:9000 | 동일 | 100% |
| env_file + environment | .env + GOOGLE_KEY_PATH | 동일 | 100% |
| volumes | google_keys:ro | 동일 | 100% |
| restart | unless-stopped | 동일 | 100% |
| healthcheck | curl /health | 동일 | 100% |
| networks | fastdashboards external | 동일 | 100% |

**Match: 100%**

---

### 1-12. `.gitignore`

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| .env | 포함 | 포함 | 100% |
| google_keys/ | 포함 | 포함 | 100% |
| reference/ | 포함 | 포함 | 100% |
| Python 기본 패턴 | 미언급 | __pycache__, .venv 등 추가 | 100% |

**Match: 100%** (설계 요구사항의 상위집합)

---

### 1-13. Logging Strategy

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| FileHandler → StreamHandler | stdout 변경 | 모든 job에서 적용 | 100% |
| 로그 포맷 | `%(asctime)s - %(levelname)s - %(message)s` | 동일 | 100% |

**Match: 100%**

---

### 1-14. API Spec

| 항목 | Design | Implementation | Match |
|------|--------|----------------|-------|
| POST /webhook | X-Webhook-Token + JSON body | 동일 | 100% |
| 성공 응답 | `{"status": "ok", "result": ...}` | 동일 | 100% |
| 인증 실패 | 401 + detail | 동일 | 100% |
| 실행 에러 | 500 + Slack 알림 | 동일 | 100% |
| GET /health | `{"status": "ok"}` | 동일 | 100% |

**Match: 100%**

---

## 2. 추가 구현 (설계 외)

| 파일 | 내용 | 평가 |
|------|------|------|
| `docker-compose.prod.yml` | Caddy 연동용 coo-network 추가 | 프로덕션 배포 개선, 양호 |
| `caddy/` | Caddy reverse proxy 설정 | 프로덕션 인프라, 양호 |
| `connectClose()` legacy alias | 기존 코드 호환 | 무해, 향후 제거 가능 |
| router.py 400 에러 핸들링 | job/function 누락 시 400 | 설계보다 개선된 에러 처리 |
| router.py Slack 알림 실패 방어 | try/except 이중 보호 | 안정성 향상 |

---

## 3. Gap 목록

| # | 심각도 | 파일 | Gap | 권장 조치 |
|---|--------|------|-----|-----------|
| 1 | Low | `app/router.py:68` | ERROR_CHANNEL_ID가 `"C04FQ47F231"` 문자열 리터럴로 하드코딩 | 상수 또는 config 변수로 추출 권장 |
| 2 | Info | `lib/mysql_connector.py:73` | `connectClose()` legacy alias가 설계에 없음 | 현재 사용처 없으면 향후 제거 검토 |

---

## 4. Match Rate 산출

| 컴포넌트 | Match Rate |
|----------|------------|
| app/config.py | 100% |
| lib/mysql_connector.py | 98% |
| lib/google_sheet.py | 100% |
| lib/slack.py | 100% |
| app/dependencies.py | 100% |
| app/router.py | 97% |
| main.py | 100% |
| jobs/cash_mgmt.py | 100% |
| jobs/upload_financial_db.py | 100% |
| jobs/global_boosta.py | 100% |
| jobs/meta_ads_manager.py | 100% |
| pyproject.toml | 100% |
| Dockerfile | 100% |
| docker-compose.yml | 100% |
| .gitignore | 100% |
| Logging Strategy | 100% |
| API Spec | 100% |
| **Overall** | **98%** |

---

## 5. 결론

구현이 설계 문서를 매우 충실하게 따르고 있으며, 발견된 Gap은 모두 Low/Info 수준입니다.

- 설계에 명시된 17개 컴포넌트 중 15개가 100% 일치
- 2개 컴포넌트에서 경미한 차이 발견 (하드코딩, legacy alias)
- 설계에 없는 추가 구현(docker-compose.prod.yml, 400 에러 핸들링)은 모두 품질 개선 방향

**Overall Match Rate: 98%** (>= 90% 기준 통과)
