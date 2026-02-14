# Design: FastAPI Webhook Service

> Plan 문서 기반 상세 설계. 각 파일의 구현 스펙을 정의한다.

---

## 1. 파일별 상세 설계

### 구현 순서

```
1. app/config.py          ← 환경변수 (다른 모든 모듈의 기반)
2. lib/mysql_connector.py ← DB 커넥터
3. lib/google_sheet.py    ← Google Sheets API
4. lib/slack.py           ← Slack 알림
5. app/dependencies.py    ← 인증 미들웨어
6. app/router.py          ← 웹훅 라우터
7. main.py                ← FastAPI 앱
8. jobs/*.py              ← 4개 job 마이그레이션
9. pyproject.toml         ← 의존성
10. Dockerfile            ← 컨테이너
11. docker-compose.yml    ← 오케스트레이션
```

---

## 2. `app/config.py` — 환경변수 설정

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Webhook
    WEBHOOK_TOKEN: str

    # CFO DB
    CFO_HOST: str
    CFO_PORT: int = 3306
    CFO_USER: str
    CFO_PASSWORD: str
    CFO_DATABASE: str

    # BOOSTA DB
    BOOSTA_HOST: str
    BOOSTA_PORT: int = 3306
    BOOSTA_USER: str
    BOOSTA_PASSWORD: str
    BOOSTA_DATABASE: str

    # BOOSTAERP DB
    BOOSTAERP_HOST: str
    BOOSTAERP_PORT: int = 3306
    BOOSTAERP_USER: str
    BOOSTAERP_PASSWORD: str
    BOOSTAERP_DATABASE: str

    # BOOSTAADMIN DB
    BOOSTAADMIN_HOST: str
    BOOSTAADMIN_PORT: int = 3306
    BOOSTAADMIN_USER: str
    BOOSTAADMIN_PASSWORD: str
    BOOSTAADMIN_DATABASE: str

    # BOOSTAAPI DB
    BOOSTAAPI_HOST: str
    BOOSTAAPI_PORT: int = 3306
    BOOSTAAPI_USER: str
    BOOSTAAPI_PASSWORD: str
    BOOSTAAPI_DATABASE: str

    # SCM DB
    SCM_HOST: str
    SCM_PORT: int = 3306
    SCM_USER: str
    SCM_PASSWORD: str
    SCM_DATABASE: str

    # MART DB
    MART_HOST: str
    MART_PORT: int = 3306
    MART_USER: str
    MART_PASSWORD: str
    MART_DATABASE: str

    # Google
    GOOGLE_KEY_PATH: str = "/google_keys/google_boosters_finance_key.json"

    # Slack
    BOOSTA_BOT_TOKEN: str
    META_BOT_TOKEN: str

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

**설계 포인트:**
- `.env`의 `google_key_path`는 `GOOGLE_KEY_PATH`로 통일 (`.env` 파일도 수정)
- `extra = "ignore"` → `.env`에 사용하지 않는 변수가 있어도 에러 없음
- DB 환경별 prefix 패턴 유지 (기존 jobs 코드와 호환)
- 모듈 레벨에서 `settings` 인스턴스 생성 → import하여 사용

---

## 3. `lib/mysql_connector.py` — MySQL 커넥터

### 클래스 설계

```python
class MysqlConnector:
    def __init__(self, environment: str) -> None
    def __enter__(self) -> "MysqlConnector"
    def __exit__(self, ...) -> None
    def read_query_table(self, query: str) -> pd.DataFrame
    def upsert_data(self, df: pd.DataFrame, table_name: str) -> str
    def get_column_max_length(self, table_name: str, column_name: str) -> int | None
    def close(self) -> None
```

> **임시 테이블 머지(`update_table_with_temp_merge`) 제거 결정:**
> 원본은 upsert를 위해 CREATE TEMP → INSERT → UPDATE JOIN → DROP → INSERT 5단계를 거쳤으나,
> MySQL 8.0의 `INSERT ... AS new ON DUPLICATE KEY UPDATE col=new.col`로 1회 쿼리로 동일한 동작 가능.
> `cash_mgmt.py`도 `upsert_data`를 사용하도록 변경한다.

### `__init__` — 환경별 연결

```python
def __init__(self, environment: str) -> None:
    """
    environment: 'CFO', 'BOOSTA', 'BOOSTAAPI' 등
    settings에서 {ENV}_HOST, {ENV}_PORT 등을 읽어 pymysql.connect() 호출
    """
```

- `app.config.settings`에서 `getattr(settings, f"{environment}_HOST")` 패턴으로 읽기
- pymysql.connect()만 사용 (sqlalchemy 제거)
- `self.connection` + `self.cursor` 보유

### `__enter__` / `__exit__` — context manager

```python
with MysqlConnector("CFO") as conn:
    df = conn.read_query_table("SELECT ...")
# 자동 close
```

### `read_query_table` — SELECT → DataFrame

```python
def read_query_table(self, query: str) -> pd.DataFrame:
    """pymysql cursor로 실행 후 pd.DataFrame 반환"""
    self.cursor.execute(query)
    columns = [desc[0] for desc in self.cursor.description]
    rows = self.cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)
```

### `upsert_data` — MySQL 8.0 호환 upsert

```python
def upsert_data(self, df: pd.DataFrame, table_name: str) -> str:
    """
    MySQL 8.0 alias 문법 사용:
    INSERT INTO table (...) VALUES (...)
      AS new
      ON DUPLICATE KEY UPDATE col1=new.col1, col2=new.col2, ...

    - id, created_at, updated_at 컬럼 자동 제외
    - df.fillna('') 처리
    - executemany로 벌크 실행
    """
```

**MySQL 8.0 upsert 쿼리 패턴:**
```sql
INSERT INTO {table} ({columns}) VALUES ({placeholders})
  AS new
  ON DUPLICATE KEY UPDATE
    col1 = new.col1, col2 = new.col2, ...
```

### ~~`update_table_with_temp_merge`~~ — 제거

> **제거 사유:** 임시 테이블 5단계 로직은 MySQL 8.0 `INSERT ... ON DUPLICATE KEY UPDATE`로 완전 대체.
> `cash_mgmt.py`에서 `update_table_with_temp_merge` 대신 `upsert_data`를 직접 사용.
> 청크 처리(20000건 단위)는 job 내에서 for 루프로 유지.

### `get_column_max_length` — 컬럼 최대 길이 조회

```python
def get_column_max_length(self, table_name: str, column_name: str) -> int | None:
    """information_schema.COLUMNS에서 CHARACTER_MAXIMUM_LENGTH 조회"""
```

cash_mgmt.py에서 `acc_name` 길이 검증에 사용.

---

## 4. `lib/google_sheet.py` — Google Sheets API

### 클래스 설계

```python
class GoogleSheetApi:
    def __init__(self) -> None
    def get_doc(self, spreadsheet_url: str)
    def get_dataframe(self, spreadsheet_url, sheetname=None, header_row=1, range=None) -> pd.DataFrame
    def paste_values_to_googlesheet(self, df, spreadsheet_url, sheet_name, start_cell, append=False) -> str
    def clear_contents(self, spreadsheet_url, range=None, sheetname=None) -> str
    def update_sheet_range(self, spreadsheet_url, start_cell, data_array, sheetname=None) -> str
```

### `__init__` — 인증

```python
def __init__(self) -> None:
    """
    settings.GOOGLE_KEY_PATH에서 서비스 계정 키 로드
    gspread.Client 생성
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_KEY_PATH, scopes=scope
    )
    self.gc = gspread.Client(auth=creds)
```

- Django 경로 로직 완전 제거
- `settings.GOOGLE_KEY_PATH` 하나로 단순화

### `get_dataframe` — 시트 → DataFrame

원본 로직 유지:
- `header_row` 파라미터로 헤더 행 지정
- `range` 파라미터로 특정 범위만 조회
- `_make_unique_headers()`로 중복 헤더 처리
- 빈 행 `dropna(how='all')` 제거

### `paste_values_to_googlesheet` — DataFrame → 시트

원본 로직 유지:
- `append=True` 시 기존 데이터 아래에 추가
- 내부적으로 `update_sheet_range()` 호출

### 유틸 메서드

```python
@staticmethod
def column_to_number(col_str: str) -> int    # 'AA' → 27
@staticmethod
def number_to_column(col_num: int) -> str    # 27 → 'AA'
def _make_unique_headers(self, headers: list) -> list  # 중복 헤더 처리
```

---

## 5. `lib/slack.py` — Slack 알림

### 함수/클래스 설계

```python
class SlackNotifier:
    @staticmethod
    def send(text, blocks, channel_id=None, user_id=None, bot_name="BOOSTA") -> dict

    @staticmethod
    def notify(text, header, body=None, footer=None,
               user_id=None, channel_id=None, url_button=None,
               bot_name="BOOSTA") -> dict

    @staticmethod
    def find_slackid(email: str) -> str | None
```

### `send` — 메시지 전송

```python
@staticmethod
def send(text, blocks, channel_id=None, user_id=None, bot_name="BOOSTA"):
    """
    bot_name에 따라 settings에서 토큰 선택:
    - "BOOSTA" → settings.BOOSTA_BOT_TOKEN
    - "META" → settings.META_BOT_TOKEN

    user_id 지정 시 DM 채널 열기 → 전송
    channel_id 지정 시 채널에 전송
    """
```

### `notify` — 구조화된 알림

원본 `Helper.slack_notify` 로직 유지:
- header (필수) → section block
- body (선택) → divider + section block
- footer (선택) → divider + section block
- url_button (선택) → actions block with button

### `find_slackid` — 이메일 → Slack ID

```python
@staticmethod
def find_slackid(email: str) -> str | None:
    """
    BOOSTA DB의 admin.flex_users 테이블에서 이메일로 slack_id 조회
    MysqlConnector("BOOSTAADMIN") 사용
    """
```

> 원본은 `MysqlConnector("BOOSTA")`로 연결 후 `admin.flex_users`를 조회하는데,
> 이는 `BOOSTA` DB에서 다른 DB(`admin`)를 크로스 조회하는 것.
> `.env`에 `BOOSTAADMIN_DATABASE=admin`이 있으므로 `BOOSTAADMIN` 환경 사용 가능.
> 단, 원본 동작과 동일하게 `BOOSTA` 환경에서 `admin.flex_users` 크로스 쿼리도 유지 가능.

---

## 6. `app/dependencies.py` — 인증

```python
from fastapi import Header, HTTPException
from app.config import settings

async def verify_webhook_token(x_webhook_token: str = Header(...)):
    if x_webhook_token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
```

---

## 7. `app/router.py` — 웹훅 라우터

### 엔드포인트 설계

```python
from fastapi import APIRouter, Depends
from app.dependencies import verify_webhook_token

router = APIRouter()

@router.post("/webhook")
async def handle_webhook(
    payload: dict,
    _: None = Depends(verify_webhook_token),
):
    """
    payload 예시:
    {
        "job": "cash_mgmt",
        "function": "banktransactionUpload",
        ... (추가 파라미터는 그대로 함수에 전달)
    }
    """
```

### 동적 모듈 로딩 로직

```python
import importlib

def execute_job(job_name: str, function_name: str, payload: dict):
    """
    1. importlib.import_module(f"jobs.{job_name}") 로 모듈 로드
    2. getattr(module, function_name) 로 함수 참조
    3. func(payload) 호출
    4. 허용된 job/function 목록 검증 (보안)
    """
```

### 보안: 허용 목록

```python
ALLOWED_JOBS = {
    "cash_mgmt": ["banktransactionUpload"],
    "upload_financial_db": ["upload_financial_db"],
    "global_boosta": ["update_route"],
    "meta_ads_manager": ["update_ads", "add_ad", "regis_slack_send",
                          "unregis_slack_send", "unregis_user_slack_send",
                          "regis_user_slack_send"],
}
```

임의의 모듈/함수 실행 방지. 새 job 추가 시 이 딕셔너리에 등록.

### 에러 핸들링

```python
try:
    result = execute_job(job, function, payload)
    return {"status": "ok", "result": result}
except Exception as e:
    # Slack 에러 알림
    SlackNotifier.notify(
        text="Webhook Error",
        header=f"*[Webhook Error]* `{job}.{function}` 실행 중 에러 발생",
        body=f"```{str(e)}```",
        channel_id=ERROR_CHANNEL_ID,
    )
    raise HTTPException(status_code=500, detail=str(e))
```

---

## 8. `main.py` — FastAPI 앱

```python
from fastapi import FastAPI
from app.router import router

app = FastAPI(title="Webhooks Service")
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- `/health` 엔드포인트: Docker 헬스체크용
- 미들웨어 최소화 (내부 서비스)

---

## 9. `jobs/` — Job 마이그레이션 설계

### 공통 변경사항

모든 jobs에서:
- `sys.path.append` 제거
- `load_dotenv(startDirectory + "/.env")` 제거
- `from _lib.xxx import Xxx` → `from lib.xxx import Xxx`
- `from _lib.helper import Helper` → `from lib.slack import SlackNotifier`
- 로깅: `logging.getLogger` 유지, 파일 핸들러 → stdout으로 변경 (Docker 로그 수집)

### 9-1. `jobs/cash_mgmt.py`

**사용하는 lib 메서드:**
- `GoogleSheetApi().get_dataframe(url, sheet, header_row=1)`
- `MysqlConnector("CFO").upsert_data(df, table_name)` (원본: `update_table_with_temp_merge` → `upsert_data`로 대체)
- `MysqlConnector("CFO").get_column_max_length(table, column)`

**마이그레이션 포인트:**
- `update_table_with_temp_merge` → `upsert_data`로 대체 (임시 테이블 로직 제거)
- 청크 처리(20000건 단위) for 루프는 유지, 내부에서 `upsert_data` 호출
- `removeCommaNumber()` → job 내 로컬 함수로 유지
- `truncate_string_to_max_length()` → job 내 로컬 함수로 유지
- `get_column_max_length()` → `MysqlConnector.get_column_max_length()`로 이동
- `MysqlConnector`를 context manager로 사용

### 9-2. `jobs/upload_financial_db.py`

**사용하는 lib 메서드:**
- `GoogleSheetApi().get_doc(url)` → `.worksheets()` 목록 조회
- `GoogleSheetApi().get_dataframe(url, sheet)`
- `MysqlConnector("CFO").upsert_data(table_name, df)` (원본: `upsertAnyData`)

**마이그레이션 포인트:**
- `table_map` 딕셔너리 유지 (10개 시트 → 10개 테이블 매핑)
- `upsertAnyData` → `upsert_data`로 메서드명 변경

### 9-3. `jobs/global_boosta.py`

**사용하는 lib 메서드:**
- `MysqlConnector(env).read_query_table(query)`
- `GoogleSheetApi().paste_values_to_googlesheet(df, url, sheet, cell)`
- `SlackNotifier.notify(text, header, user_id, url_button)` (원본: `Helper().slack_notify`)
- `SlackNotifier.find_slackid(email)` (원본: `Helper().find_slackid`)

**마이그레이션 포인트:**
- `update_to_sheet()` 내부 함수 유지
- `Helper()` → `SlackNotifier` 정적 메서드로 대체

### 9-4. `jobs/meta_ads_manager.py`

**사용하는 lib 메서드:**
- `GoogleSheetApi().get_dataframe(url, sheet, header_row=1)`
- `GoogleSheetApi().paste_values_to_googlesheet(df, url, sheet, cell)`
- `GoogleSheetApi().clear_contents(url, range, sheetname)`
- `MysqlConnector("BOOSTA").read_query_table(query)`
- `SlackNotifier.notify(...)`, `SlackNotifier.find_slackid(...)`

**마이그레이션 포인트:**
- `helper = Helper()` 모듈 레벨 인스턴스 → `SlackNotifier` 직접 사용
- `conn.connectClose` (괄호 누락 — 원본 버그) → context manager로 수정
- `slack_send()` 로컬 함수 → `SlackNotifier.send()` 래핑하거나 job 내 유지

---

## 10. `pyproject.toml`

```toml
[project]
name = "webhooks"
version = "0.1.0"
description = "FastAPI webhook service for Google Sheet & MySQL sync"
readme = "README.md"
requires-python = ">=3.13"
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

---

## 11. `Dockerfile`

```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 의존성 먼저 설치 (캐시 활용)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 소스 복사
COPY main.py ./
COPY app/ ./app/
COPY lib/ ./lib/
COPY jobs/ ./jobs/

EXPOSE 9000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

**설계 포인트:**
- `reference/`, `docs/`, `google_keys/`는 COPY하지 않음
- `google_keys/`는 docker-compose에서 볼륨 마운트
- 레이어 캐싱: `pyproject.toml` + `uv.lock` 먼저 복사

---

## 12. `docker-compose.yml`

```yaml
services:
  webhooks:
    build: .
    container_name: webhooks
    ports:
      - "9000:9000"
    env_file:
      - .env
    environment:
      - GOOGLE_KEY_PATH=/google_keys/google_boosters_finance_key.json
    volumes:
      - ./google_keys:/google_keys:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  default:
    name: fastdashboards_fastdashboards-network
    external: true
```

---

## 13. `.env` 수정사항

기존 `.env`에 추가/변경:
```
# 추가
WEBHOOK_TOKEN=<생성할 시크릿 토큰>

# 변경 (기존 google_key_path → GOOGLE_KEY_PATH)
GOOGLE_KEY_PATH=/google_keys/google_boosters_finance_key.json
```

---

## 14. `.gitignore` 수정사항

```gitignore
# 기존 내용 유지 +
.env
google_keys/
reference/
```

---

## 15. API 스펙

### POST /webhook

**Request:**
```http
POST /webhook HTTP/1.1
Host: localhost:9000
Content-Type: application/json
X-Webhook-Token: <WEBHOOK_TOKEN>

{
    "job": "cash_mgmt",
    "function": "banktransactionUpload",
    "service": "product_info",
    "user_email": "user@company.com"
}
```

- `job` (필수): jobs/ 폴더 내 모듈명
- `function` (필수): 실행할 함수명
- 나머지 필드: payload로 함수에 전달

**Response (성공):**
```json
{
    "status": "ok",
    "result": "result: 100 records are inserted into fn_cash_banktransaction ..."
}
```

**Response (인증 실패):**
```json
{ "detail": "Invalid webhook token" }
```
Status: 401

**Response (실행 에러):**
```json
{ "detail": "에러 메시지" }
```
Status: 500 (+ Slack 에러 알림 전송)

### GET /health

**Response:**
```json
{ "status": "ok" }
```

---

## 16. 로깅 전략

- 각 job의 `logging.FileHandler` → `logging.StreamHandler(sys.stdout)`로 변경
- Docker 컨테이너 stdout으로 로그 수집
- `docker logs webhooks` 또는 `docker-compose logs webhooks`로 확인
- 로그 포맷 유지: `%(asctime)s - %(levelname)s - %(message)s`
