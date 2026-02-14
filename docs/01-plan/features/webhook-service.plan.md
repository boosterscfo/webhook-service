# Plan: FastAPI Webhook Service

> Google Sheet 연동 작업을 트리거하는 경량 웹훅 서비스

---

## 1. 개요

### 배경
기존 Django 프로젝트(`/var/www/html/django_projects/mysite`)에서 운영하던 웹훅 트리거 기능을 독립적인 FastAPI 서비스로 마이그레이션한다. Google Sheet ↔ MySQL 동기화, Slack 알림 등 기존 기능을 유지하면서 유지보수가 쉬운 구조로 재구성한다.

### 목표
- 기존 4개 Python 모듈을 현재 환경에 맞게 마이그레이션
- FastAPI 기반 웹훅 엔드포인트 구현 (동기 처리)
- Docker 컨테이너로 배포, 기존 `fastdashboards` 네트워크와 공존
- 간편한 유지보수: 새 작업 추가 시 Python 파일 하나만 추가하면 동작

### 개발 환경
- **Python**: 3.13 (`.python-version`)
- **패키지 관리**: uv 0.8.22
- **컨테이너**: Docker + docker-compose
- **네트워크**: `fastdashboards_fastdashboards-network` (172.18.0.0/16) 공유

---

## 2. 마이그레이션 대상

| # | 파일 | 주요 함수 | 기능 | 사용 DB |
|---|------|-----------|------|---------|
| 1 | `cash_mgmt.py` | `banktransactionUpload` | 시트 → MySQL 은행거래/계좌 | CFO |
| 2 | `upload_financial_db.py` | `upload_financial_db` | 시트 → MySQL 재무 데이터 (10개 테이블) | CFO |
| 3 | `global_boosta.py` | `update_route` | MySQL → 시트 동기화 + Slack 알림 | BOOSTA, BOOSTAAPI |
| 4 | `meta_ads_manager.py` | `update_ads`, `add_ad` 외 4개 | Meta 광고 관리 + Slack 알림 | BOOSTA |

---

## 3. 공통 라이브러리 분석 (`reference/_lib/`)

> 원본 `_lib/` 코드가 제공됨. **참고만 하고 새로 작성**한다. 특히 MySQL 8.0 호환성 이슈를 해결한다.

### 3-1. GoogleSheetApi (`_lib/google_sheet/`)

**원본 제공 메서드:**
| 메서드 | 용도 | jobs에서 사용 여부 |
|--------|------|-------------------|
| `get_doc(url)` | 스프레드시트 문서 열기 | upload_financial_db |
| `get_dataframe(url, sheet, header_row, range)` | 시트 → DataFrame | 전체 |
| `paste_values_to_googlesheet(df, url, sheet, cell, append)` | DataFrame → 시트 붙여넣기 | global_boosta, meta_ads |
| `clear_contents(url, range, sheetname)` | 시트 범위 클리어 | meta_ads |
| `update_sheet_range(url, cell, data, sheet)` | 범위 업데이트 (내부용) | paste_values에서 호출 |

**재구현 방침:**
- gspread + google-auth 기반 유지
- Django 경로 하드코딩 제거 → 환경변수 `GOOGLE_KEY_PATH`로 단순화
- 중복 헤더 처리(`_make_unique_headers`) 유지
- 열 번호 ↔ 문자 변환 유틸 유지

### 3-2. MysqlConnector (`_lib/mysql_connector/`)

**원본 제공 메서드:**
| 메서드 | 용도 | jobs에서 사용 여부 |
|--------|------|-------------------|
| `__init__(environment)` | 환경별 DB 연결 (`PREFIX_HOST` 패턴) | 전체 |
| `read_query_table(query)` | SELECT → DataFrame | global_boosta, meta_ads |
| `update_table_with_temp_merge(df, temp, main, keys, updates)` | 임시 테이블 → MERGE 업데이트 | cash_mgmt |
| `upsertAnyData(table_name, df)` | INSERT ON DUPLICATE KEY UPDATE | upload_financial_db |
| `insert_data_into_table(df, table)` | 벌크 INSERT | temp_merge 내부 |
| `getTableColumns(table)` | 테이블 컬럼 목록 | upsertTableData 내부 |
| `connectClose()` | 연결 종료 | 전체 |

**MySQL 8.0 호환성 이슈:**
| 문제 | 원본 코드 | MySQL 8.0 대응 |
|------|-----------|----------------|
| `VALUES()` 함수 deprecated | `ON DUPLICATE KEY UPDATE col=VALUES(col)` | `INSERT INTO ... AS new ON DUPLICATE KEY UPDATE col=new.col` |
| sqlalchemy + pymysql 이중 연결 | `pymysql.connect()` + `create_engine()` 동시 사용 | pymysql만 사용, `read_query_table`도 pymysql cursor로 통일 |

**재구현 방침:**
- pymysql 단독 사용 (sqlalchemy 제거 → 의존성 경량화)
- MySQL 8.0 alias 문법으로 upsert 재작성
- `update_table_with_temp_merge` 로직은 유지하되, 새 INSERT 후 append 방식은 MySQL 8.0 `INSERT ... ON DUPLICATE KEY UPDATE`로 단순화 가능한지 검토
- 환경변수 prefix 패턴 유지 (`CFO_HOST`, `BOOSTA_HOST` 등)
- context manager (`with` 문) 지원 추가로 연결 누수 방지

### 3-3. Helper (`_lib/helper/`)

**원본 제공 메서드:**
| 메서드 | 용도 | jobs에서 사용 여부 |
|--------|------|-------------------|
| `slack_notify(text, header, body, footer, ...)` | 구조화된 Slack 알림 | global_boosta, meta_ads |
| `slack_send(text, block, channel_id, user_id, bot_name)` | 메시지 전송 | slack_notify 내부 |
| `find_slackid(email)` | 이메일 → Slack ID 조회 (DB) | global_boosta, meta_ads |
| `removeCommaNumber(value)` | 쉼표 제거 숫자 변환 | (cash_mgmt에서 직접 구현) |
| `processNumberColumn(df, cols)` | 숫자 컬럼 전처리 | (미사용) |

**재구현 방침:**
- `slack.py`로 분리 (Slack 전용)
- `find_slackid`는 MysqlConnector를 직접 사용 → Slack 모듈 내에 포함
- `bot_name` 파라미터로 BOOSTA/META 봇 토큰 선택 기능 유지
- `removeCommaNumber`, `processNumberColumn` 등 데이터 유틸은 각 job 내에서 필요 시 직접 처리

---

## 4. 아키텍처

### 프로젝트 구조

```
webhooks/
├── main.py                     # FastAPI 앱 엔트리포인트
├── app/
│   ├── __init__.py
│   ├── config.py               # 환경변수 로드 (pydantic-settings)
│   ├── router.py               # 웹훅 라우터
│   └── dependencies.py         # 인증 등 공통 의존성
├── lib/
│   ├── __init__.py
│   ├── google_sheet.py         # GoogleSheetApi (새로 작성)
│   ├── mysql_connector.py      # MysqlConnector (MySQL 8.0 호환, 새로 작성)
│   └── slack.py                # Slack 알림 헬퍼 (새로 작성)
├── jobs/
│   ├── __init__.py
│   ├── cash_mgmt.py            # banktransactionUpload
│   ├── upload_financial_db.py  # upload_financial_db
│   ├── global_boosta.py        # update_route
│   └── meta_ads_manager.py     # update_ads, add_ad 등
├── google_keys/
│   └── google_boosters_finance_key.json
├── reference/                  # 원본 코드 (마이그레이션 참고용, 배포 제외)
├── docs/                       # PDCA 문서
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env
├── .python-version
└── .gitignore
```

### 웹훅 동작 흐름

```
POST /webhook
  Headers: { "X-Webhook-Token": "<secret>" }
  Body:    { "job": "cash_mgmt", "function": "banktransactionUpload", ... }

→ Token 검증
→ jobs/{job}.py 모듈에서 {function} 함수 동적 import
→ function(payload) 호출 (동기)
→ 에러 시 Slack 알림
→ 응답 반환
```

### 핵심 설계 결정

| 항목 | 결정 | 이유 |
|------|------|------|
| 처리 방식 | **동기(sync)** | 최대 ~23초 소요, 타임아웃 내 처리 가능. 추후 Worker 도입 여지 남김 |
| 모듈 로딩 | **importlib 동적 import** | 새 job 추가 시 라우터 수정 불필요 |
| 인증 | **X-Webhook-Token 헤더** | 단순하고 효과적. 환경변수로 토큰 관리 |
| 설정 관리 | **pydantic-settings** | `.env` 자동 로드, 타입 검증 |
| DB 연결 | **요청별 생성/종료** | 동시 요청이 적고, 커넥션 풀 복잡도 불필요 |
| DB 드라이버 | **pymysql 단독** | sqlalchemy 제거, MySQL 8.0 호환 upsert |
| 패키지 관리 | **uv** | pyproject.toml 기반, Docker 빌드 시에도 uv 사용 |

---

## 5. Docker 환경

### 현재 Docker 상태

| 항목 | 값 |
|------|-----|
| 기존 네트워크 | `fastdashboards_fastdashboards-network` (172.18.0.0/16) |
| 기존 컨테이너 | `fastdashboards-backend` (:8000), `fastdashboards-frontend-dev` (:5173) |
| 사용할 포트 | **9000** (기존 서비스와 충돌 없음) |

### Docker 구성 계획

```yaml
# docker-compose.yml
services:
  webhooks:
    build: .
    container_name: webhooks
    ports:
      - "9000:9000"
    env_file:
      - .env
    volumes:
      - ./google_keys:/google_keys:ro
    restart: unless-stopped

networks:
  default:
    name: fastdashboards_fastdashboards-network
    external: true
```

### Dockerfile (uv 기반)

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

- 기존 `fastdashboards` 네트워크에 조인 (동일 네트워크에서 공존)
- `google_keys`는 read-only 볼륨으로 마운트
- uv로 빌드하여 빠른 의존성 설치
- 별도 Caddy/Nginx 없이 FastAPI 직접 노출 (내부용 서비스)

---

## 6. 환경변수 정리

### 필수 환경변수

| 그룹 | 변수 | 용도 | 상태 |
|------|------|------|------|
| **Webhook** | `WEBHOOK_TOKEN` | 웹훅 인증 토큰 | **신규 추가 필요** |
| **CFO DB** | `CFO_HOST/PORT/USER/PASSWORD/DATABASE` | 재무 DB | .env 설정됨 |
| **BOOSTA DB** | `BOOSTA_HOST/PORT/USER/PASSWORD/DATABASE` | 부스타 DB | .env 설정됨 |
| **BOOSTAAPI DB** | `BOOSTAAPI_HOST/PORT/USER/PASSWORD/DATABASE` | 부스타 API DB | .env 설정됨 |
| **Google** | `GOOGLE_KEY_PATH` | 서비스 계정 키 경로 | .env에 `google_key_path`로 존재, 변수명 통일 필요 |
| **Slack** | `BOOSTA_BOT_TOKEN` | Slack 알림 (boosta 봇) | .env 설정됨 |
| **Slack** | `META_BOT_TOKEN` | Slack 알림 (meta 봇) | .env 설정됨 |

> `.env`의 `google_key_path`를 `GOOGLE_KEY_PATH`로 통일하거나, 기존 변수명 그대로 사용 가능.

---

## 7. 의존성 (pyproject.toml)

```toml
dependencies = [
    "fastapi",
    "uvicorn",
    "pydantic-settings",
    "python-dotenv",
    "pandas",
    "numpy",
    "pymysql",
    "gspread",
    "google-auth",
    "slack-sdk",
]
```

> sqlalchemy 불포함 — pymysql 단독으로 MySQL 8.0 호환 구현.

---

## 8. 구현 순서

### Phase 1: 프로젝트 기반 구성
- [ ] `pyproject.toml` 의존성 추가 + `uv sync`
- [ ] `app/config.py` - 환경변수 설정 클래스 (pydantic-settings)
- [ ] `Dockerfile` (uv 기반) + `docker-compose.yml`

### Phase 2: 공통 라이브러리 새로 작성
- [ ] `lib/google_sheet.py` - GoogleSheetApi (gspread 기반, 경로 단순화)
- [ ] `lib/mysql_connector.py` - MysqlConnector (pymysql 단독, MySQL 8.0 alias upsert)
- [ ] `lib/slack.py` - Slack 알림 헬퍼 (find_slackid 포함)

### Phase 3: 웹훅 엔드포인트
- [ ] `app/dependencies.py` - 토큰 인증
- [ ] `app/router.py` - 동적 모듈 import + 함수 호출
- [ ] `main.py` - FastAPI 앱 구성

### Phase 4: Job 마이그레이션
- [ ] `jobs/cash_mgmt.py` - import 경로 수정, 새 lib 사용
- [ ] `jobs/upload_financial_db.py` - import 경로 수정, 새 lib 사용
- [ ] `jobs/global_boosta.py` - import 경로 수정, 새 lib 사용
- [ ] `jobs/meta_ads_manager.py` - import 경로 수정, 새 lib 사용

### Phase 5: Docker 배포 및 검증
- [ ] Docker 빌드 + `fastdashboards` 네트워크 조인 실행
- [ ] 각 엔드포인트 curl 테스트
- [ ] 에러 시 Slack 알림 동작 확인

---

## 9. 소요 시간 (참고)

| 작업 | 예상 응답 시간 |
|------|----------------|
| banktransactionUpload | ~18초 |
| upload_financial_db | ~6초 |
| global_boosta (update_route) | 2~6초 |
| meta_ads (update_ads) | ~23초 |

> uvicorn 기본 타임아웃(60초) 내 모두 처리 가능. 추후 타임아웃 이슈 시 background task 또는 worker 도입 검토.

---

## 10. 리스크 및 고려사항

| 리스크 | 대응 |
|--------|------|
| MySQL 8.0 `VALUES()` deprecated | alias 문법(`AS new ... new.col`)으로 upsert 재작성 |
| sqlalchemy 제거 영향 | `read_query_table`을 pymysql cursor + pandas로 대체 |
| `_lib/` 재구현 시 누락 메서드 | jobs 파일에서 사용하는 메서드만 정확히 추출하여 구현 |
| 긴 처리 시간 (최대 23초) | uvicorn timeout 충분, 추후 worker 도입 여지 |
| Google API 인증 실패 | 키 파일 볼륨 마운트, 경로 환경변수화 |
| DB 접근 불가 (외부 DB) | Docker 네트워크 설정 확인, 방화벽 규칙 점검 |
| 기존 네트워크 공존 | `fastdashboards_fastdashboards-network` external로 조인 |
