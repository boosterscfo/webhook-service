# Design: Meta Ads Webhook Migration

> Plan 문서 기반 상세 설계. HMAC-SHA256 서명 인증 + Google Apps Script 코드 변경.

---

## 1. 구현 순서

```
1. app/dependencies.py 수정           ← HMAC 서명 검증 추가 (서버 측)
2. app/config.py 수정                 ← WEBHOOK_SECRET 환경변수 추가
3. Google Apps Script 코드 작성       ← HMAC 서명 생성 + 클라이언트 변경
4. curl 기반 서버 측 검증              ← 배포된 서버 동작 확인
5. Apps Script → FastAPI 통합 테스트   ← 실제 환경 연동 확인
```

---

## 2. 프로토콜 변경 상세

### 2-1. 요청 형식 비교

**기존 (Django):**
```http
POST /webhooks/mPnBRC1qxapOAxQpWmjy4NofbgxCmXSj/ HTTP/1.1
Host: boostb.boosters-labs.com
Content-Type: application/json; charset=utf-8
Webhook-Token: webhook_token_uusihfuhokdwjifasdoijf^&%(*&

{
  "api": "dev.google_sheet_to_db.get_sheet.meta_ads_manager",
  "function": "update_ads",
  "user_email": "user@company.com"
}
```

**신규 (FastAPI + HMAC-SHA256):**
```http
POST /webhook HTTP/1.1
Host: sidehook.boosters-labs.com
Content-Type: application/json; charset=utf-8
X-Webhook-Timestamp: 1740528000
X-Webhook-Signature: sha256=a1b2c3d4e5f6...

{
  "job": "meta_ads_manager",
  "function": "update_ads",
  "user_email": "user@company.com"
}
```

### 2-2. 변경 포인트 정리

| # | 항목 | 변경 전 | 변경 후 | 변경 이유 |
|---|------|---------|---------|-----------|
| 1 | URL | `/webhooks/mPnBRC...Sj/` | `/webhook` | FastAPI 단일 엔드포인트 |
| 2 | Host | `boostb.boosters-labs.com` | `sidehook.boosters-labs.com` | 신규 서버 도메인 |
| 3 | 인증 방식 | 정적 토큰 (`Webhook-Token`) | **HMAC-SHA256 서명** (`X-Webhook-Signature` + `X-Webhook-Timestamp`) | 업계 표준, 변조/리플레이 방지 |
| 4 | 모듈 지정 필드 | `"api": "dev.google_sheet_to_db.get_sheet.meta_ads_manager"` | `"job": "meta_ads_manager"` | 키명 변경 + 값 단순화 |
| 5 | 함수 지정 필드 | `"function"` | `"function"` | **변경 없음** |
| 6 | 추가 파라미터 | `user_email`, `trigger` | 동일 | **변경 없음** |

### 2-3. 응답 형식 비교

**기존 (Django):** 텍스트 응답 (plain text)
```
result: 100 records are inserted ...
```

**신규 (FastAPI):** JSON 응답
```json
{
  "status": "ok",
  "result": "result: 100 records are inserted ..."
}
```

> Apps Script에서 `response.getContentText()`로 받으면 JSON 문자열이 반환됨.
> `SpreadsheetApp.toast(responseData)` 에서 JSON 형태로 보일 수 있음.
> 필요 시 `JSON.parse(responseData).result`로 파싱 가능.

---

## 3. HMAC-SHA256 + Timestamp 인증 설계

### 3-1. 인증 프로토콜 개요

```
Slack/Stripe/GitHub Webhook 검증과 동일한 업계 표준 패턴:

[클라이언트]                           [서버]
    │                                    │
    ├─ timestamp = 현재 Unix 시간         │
    ├─ body = JSON.stringify(payload)     │
    ├─ sig = HMAC-SHA256(                 │
    │    key = WEBHOOK_SECRET,            │
    │    msg = "{timestamp}.{body}"       │
    │  )                                  │
    │                                    │
    ├─ X-Webhook-Timestamp: {timestamp} ─►│
    ├─ X-Webhook-Signature: sha256={sig} ►│
    ├─ Body: {body} ─────────────────────►│
    │                                    │
    │                    timestamp 검증 ◄─┤ (5분 이내?)
    │                    서명 재계산 ◄────┤ HMAC-SHA256(secret, ts.body)
    │                    비교 ◄──────────┤ hmac.compare_digest()
    │                                    │
    │◄─────────── 200 OK ────────────────┤
```

### 3-2. 보안 특성

| 특성 | 정적 토큰 (기존) | HMAC + Timestamp (신규) |
|------|:-:|:-:|
| 토큰 노출 시 무단 호출 | 가능 | 불가 (시크릿은 전송되지 않음) |
| 요청 변조 감지 | 불가 | 가능 (body 변경 시 서명 불일치) |
| 리플레이 공격 | 가능 | 5분 이내만 유효 |
| MITM 가로채기 | 토큰 탈취 가능 | 시크릿 노출 없음 (HTTPS + 서명만 전송) |

### 3-3. 하위 호환성 (Dual-mode)

기존 `X-Webhook-Token` 방식을 사용하는 다른 caller (cash_mgmt, upload_financial_db, global_boosta)가
있으므로, **전환 기간 동안 두 인증 방식을 모두 지원**한다.

```
인증 우선순위:
1. X-Webhook-Signature 헤더 존재 → HMAC 검증
2. X-Webhook-Token 헤더 존재   → 정적 토큰 검증 (레거시)
3. 둘 다 없음                  → 401 Unauthorized
```

> 모든 caller가 HMAC으로 전환 완료 후, 레거시 정적 토큰 지원을 제거한다.

---

## 4. 서버 측 구현 설계

### 4-1. `app/config.py` — 환경변수 추가

```python
class Settings(BaseSettings):
    # 기존
    WEBHOOK_TOKEN: str          # 레거시 정적 토큰 (하위 호환)

    # 신규
    WEBHOOK_SECRET: str = ""    # HMAC-SHA256 서명용 시크릿 키
```

`.env` 추가:
```
WEBHOOK_SECRET=<충분히 긴 랜덤 문자열 (32자 이상 권장)>
```

### 4-2. `app/dependencies.py` — HMAC 검증 로직

```python
import hashlib
import hmac
import time
from typing import Optional

from fastapi import Header, HTTPException, Request

from app.config import settings

TIMESTAMP_TOLERANCE = 300  # 5분 (초)


async def verify_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
    x_webhook_token: Optional[str] = Header(None),
):
    """
    Dual-mode 인증:
    1. HMAC 서명이 있으면 → HMAC 검증 (신규)
    2. 정적 토큰만 있으면 → 토큰 비교 (레거시)
    3. 둘 다 없으면 → 401
    """

    # --- Mode 1: HMAC-SHA256 서명 검증 ---
    if x_webhook_signature and x_webhook_timestamp:
        # 타임스탬프 유효성 (5분)
        try:
            ts = int(x_webhook_timestamp)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid timestamp")

        if abs(time.time() - ts) > TIMESTAMP_TOLERANCE:
            raise HTTPException(status_code=401, detail="Request expired")

        # Raw body 읽기
        body = await request.body()

        # 서명 계산: HMAC-SHA256("{timestamp}.{body}")
        sig_basestring = f"{x_webhook_timestamp}.{body.decode('utf-8')}"
        expected = hmac.new(
            settings.WEBHOOK_SECRET.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 비교 (timing-safe)
        received = x_webhook_signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, received):
            raise HTTPException(status_code=401, detail="Invalid signature")

        return  # 인증 성공

    # --- Mode 2: 레거시 정적 토큰 ---
    if x_webhook_token:
        if x_webhook_token != settings.WEBHOOK_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid webhook token")
        return  # 인증 성공

    # --- 인증 정보 없음 ---
    raise HTTPException(status_code=401, detail="Authentication required")
```

**설계 포인트:**
- `request.body()` → Starlette가 내부 캐시하므로 이후 FastAPI JSON 파싱에 영향 없음
- `hmac.compare_digest()` → 타이밍 공격 방지 (constant-time 비교)
- `removeprefix("sha256=")` → `sha256=` 접두사 제거 후 비교
- 레거시 모드는 `WEBHOOK_SECRET`이 비어있어도 동작

### 4-3. `app/router.py` — 의존성 변경

```python
# 변경 전
from app.dependencies import verify_webhook_token

@router.post("/webhook")
async def handle_webhook(
    payload: dict,
    _: None = Depends(verify_webhook_token),
):

# 변경 후
from app.dependencies import verify_webhook

@router.post("/webhook")
async def handle_webhook(
    payload: dict,
    _: None = Depends(verify_webhook),
):
```

---

## 5. Google Apps Script 상세 설계

### 5-1. 공통 설정 (상수)

```javascript
// ─── 공통 설정 ───
var WEBHOOK_URL = 'https://sidehook.boosters-labs.com/webhook';
var WEBHOOK_SECRET = '<WEBHOOK_SECRET 값>';  // HMAC 서명용 시크릿
var JOB_NAME = 'meta_ads_manager';
```

### 5-2. 공통 헬퍼 함수

#### `getEmailSafely()` — 변경 없음

```javascript
function getEmailSafely() {
  try {
    var userEmail = Session.getActiveUser().getEmail();
    if (userEmail !== "") {
      return userEmail;
    } else {
      return "default@email.com";
    }
  } catch (e) {
    console.log("Error fetching user email: " + e.toString());
  }
  return "default@email.com";
}
```

#### `computeSignature(body, timestamp)` — HMAC-SHA256 서명 생성

```javascript
/**
 * HMAC-SHA256 서명 생성
 * @param {string} body - JSON 문자열 (payload)
 * @param {string} timestamp - Unix 타임스탬프 (초)
 * @returns {string} hex 인코딩된 서명
 */
function computeSignature(body, timestamp) {
  var sigBasestring = timestamp + '.' + body;
  var signatureBytes = Utilities.computeHmacSha256Signature(
    sigBasestring, WEBHOOK_SECRET
  );
  // byte[] → hex string
  return signatureBytes.map(function(byte) {
    return ('0' + (byte & 0xFF).toString(16)).slice(-2);
  }).join('');
}
```

> `Utilities.computeHmacSha256Signature(value, key)` → Google Apps Script 네이티브 지원.
> 별도 라이브러리 불필요.

#### `callWebhook(functionName, extraPayload)` — HMAC 서명 포함 호출

```javascript
/**
 * 웹훅 호출 공통 함수 (HMAC-SHA256 서명 포함)
 * @param {string} functionName - 실행할 서버 함수명
 * @param {object} extraPayload - 추가 페이로드 (user_email, trigger 등)
 * @returns {string} 서버 응답 텍스트
 */
function callWebhook(functionName, extraPayload) {
  var payload = {
    "job": JOB_NAME,
    "function": functionName
  };

  // extraPayload 병합
  if (extraPayload) {
    for (var key in extraPayload) {
      payload[key] = extraPayload[key];
    }
  }

  var body = JSON.stringify(payload);
  var timestamp = Math.floor(Date.now() / 1000).toString();
  var signature = computeSignature(body, timestamp);

  var headers = {
    'X-Webhook-Timestamp': timestamp,
    'X-Webhook-Signature': 'sha256=' + signature,
    'Content-Type': 'application/json; charset=utf-8'
  };

  var options = {
    'method': 'post',
    'headers': headers,
    'payload': body,
    'muteHttpExceptions': true
  };

  var response = UrlFetchApp.fetch(WEBHOOK_URL, options);
  var responseCode = response.getResponseCode();
  var responseData = response.getContentText();

  if (responseCode !== 200) {
    SpreadsheetApp.getActive().toast(
      'Error (' + responseCode + '): ' + responseData, 'Webhook Error', 10
    );
    return responseData;
  }

  // JSON 응답에서 result 추출
  try {
    var jsonResponse = JSON.parse(responseData);
    var resultText = jsonResponse.result || 'Success';
    SpreadsheetApp.getActive().toast(resultText, 'Webhook', 5);
    return resultText;
  } catch (e) {
    SpreadsheetApp.getActive().toast(responseData, 'Webhook', 5);
    return responseData;
  }
}
```

**설계 포인트:**
- `JSON.stringify(payload)` → body를 한 번만 생성하여 서명과 전송에 동일하게 사용
- `Math.floor(Date.now() / 1000)` → Unix epoch (초 단위)
- `sha256=` 접두사 → 서버에서 알고리즘 식별 (Stripe/GitHub 패턴)
- `muteHttpExceptions: true` → HTTP 에러도 수신하여 사용자에게 표시

### 5-3. 각 함수 설계

#### `update_ads()` — 광고 업데이트

```javascript
function update_ads() {
  callWebhook('update_ads', {
    'user_email': getEmailSafely()
  });
}
```

#### `trigger_update()` — 트리거 기반 업데이트

```javascript
function trigger_update() {
  callWebhook('update_ads', {
    'user_email': getEmailSafely(),
    'trigger': true
  });
}
```

> `trigger: true` → FastAPI는 JSON boolean을 `True` (Python)로 수신.
> `update_ads(payload)`에서 `payload.get("trigger")` → truthy 값으로 분기 정상 동작.

#### `register_ads()` — 광고 등록

```javascript
function register_ads() {
  callWebhook('add_ad', {
    'user_email': getEmailSafely()
  });
}
```

#### `unregis_user_slack_send()` — 등록대상 개인 Slack 알림

```javascript
function unregis_user_slack_send() {
  callWebhook('unregis_user_slack_send', {
    'user_email': getEmailSafely()
  });
}
```

#### `regis_user_slack_send()` — 변경대상 개인 Slack 알림

```javascript
function regis_user_slack_send() {
  callWebhook('regis_user_slack_send', {
    'user_email': getEmailSafely()
  });
}
```

---

## 6. 서버 측 payload 호환성 검증

### 6-1. `update_ads(payload)` — payload 접근 패턴

| 접근 코드 | 전달 값 | 동작 |
|-----------|---------|------|
| `payload.get("user_email")` | `"user@company.com"` 또는 `"default@email.com"` | 이메일로 Slack ID 조회 |
| `payload.get("trigger")` | `True` (boolean) 또는 `None` | trigger 모드 분기 (`if not trigger:` 체크) |
| `payload.get("job")` | `"meta_ads_manager"` | 라우터에서 사용, 함수 내에서는 미사용 |
| `payload.get("function")` | `"update_ads"` | 라우터에서 사용, 함수 내에서는 미사용 |

**`trigger` 분기 로직 검증 (meta_ads_manager.py:161):**

```python
if not trigger:
    # trigger가 None(미전달) 또는 False → 사용자별 Slack 알림
    if user_id:
        slack_send(..., user_id)
    else:
        slack_send(...)
else:
    # trigger가 True → 채널 전체 알림 (user_id 없이)
    slack_send(...)
```

- `trigger_update()`에서 `"trigger": true` 전달 → `payload.get("trigger")` = `True` → else 분기
- `update_ads()`에서 `trigger` 미전달 → `payload.get("trigger")` = `None` → if 분기 (falsy)

### 6-2. `add_ad(payload)` — payload 접근 패턴

| 접근 코드 | 전달 값 | 동작 |
|-----------|---------|------|
| `payload.get("user_email", default_email)` | `"user@company.com"` | 기본값 `"default@email.com"` |

### 6-3. `unregis_user_slack_send(payload)` / `regis_user_slack_send(payload)`

| 접근 코드 | 전달 값 | 동작 |
|-----------|---------|------|
| (payload 직접 접근 없음) | — | 함수 시그니처에 `payload: dict`만 받고 내부에서 사용하지 않음 |

> 두 함수는 payload에서 값을 읽지 않고, Google Sheet에서 직접 이메일 목록을 가져옴.

---

## 7. Slack 테스트 채널 설계

### 7-1. 테스트 채널 환경변수

`.env`에 이미 존재:
```
SLACK_CHANNEL_ID_TEST=C06PT07RK40
```

`app/config.py`에 추가:
```python
class Settings(BaseSettings):
    # Slack
    BOOSTA_BOT_TOKEN: str
    META_BOT_TOKEN: str
    SLACK_CHANNEL_ID_TEST: str = ""  # 테스트용 Slack 채널
```

### 7-2. 테스트 모드 payload 설계

curl 테스트 시 `"test": true`를 payload에 포함하면, Slack 알림을 **테스트 채널로 전송**하도록 한다.

**서버 측 지원 — `jobs/meta_ads_manager.py` 수정:**

```python
from app.config import settings

# 기존
channel_id = "C06NZHCD17F"

# 변경: payload에서 test 모드 확인하여 채널 선택
def _get_channel_id(payload: dict) -> str:
    if payload.get("test") and settings.SLACK_CHANNEL_ID_TEST:
        return settings.SLACK_CHANNEL_ID_TEST
    return "C06NZHCD17F"
```

**적용 함수:**
- `update_ads(payload)` → `channel_id = _get_channel_id(payload)`
- `add_ad(payload)` → 내부에서 `update_ads` 호출 시에도 test 전파

> `regis_slack_send`, `unregis_slack_send`는 하드코딩된 채널(`C04FQ47F231`)을 사용하므로,
> 테스트 모드 적용 시 동일하게 `_get_channel_id()`로 대체.

---

## 8. curl 테스트 스펙

> 테스트 시 `"test": true`를 포함하여 Slack 알림을 테스트 채널로 전송한다.
> HMAC 서명은 bash에서 `openssl dgst`로 생성한다.

### 8-0. HMAC 서명 생성 헬퍼 (bash)

```bash
# 환경변수 설정 (테스트 시)
export WEBHOOK_SECRET="<시크릿 값>"

# 서명 생성 함수
sign_request() {
  local body="$1"
  local timestamp=$(date +%s)
  local signature=$(echo -n "${timestamp}.${body}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')
  echo "TIMESTAMP=${timestamp}"
  echo "SIGNATURE=sha256=${signature}"
}
```

### 8-1. update_ads 테스트

```bash
BODY='{"job":"meta_ads_manager","function":"update_ads","user_email":"default@email.com","test":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

**기대 응답:**
```json
{"status": "ok", "result": "..."}
```

**검증 포인트:**
- BOOSTA DB 접근 성공 (`facebook_data_ads`, `facebook_id_ads` 테이블)
- Google Sheet 읽기/쓰기 성공
- Slack 알림 → **테스트 채널** (`C06PT07RK40`)에 발송

### 8-2. update_ads + trigger 테스트

```bash
BODY='{"job":"meta_ads_manager","function":"update_ads","user_email":"default@email.com","trigger":true,"test":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

### 8-3. add_ad 테스트

```bash
BODY='{"job":"meta_ads_manager","function":"add_ad","user_email":"default@email.com","test":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

### 8-4. Slack 알림 함수 테스트

```bash
# regis_user_slack_send
BODY='{"job":"meta_ads_manager","function":"regis_user_slack_send","user_email":"default@email.com","test":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"

# unregis_user_slack_send
BODY='{"job":"meta_ads_manager","function":"unregis_user_slack_send","user_email":"default@email.com","test":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $TS" \
  -H "X-Webhook-Signature: sha256=$SIG" \
  -d "$BODY"
```

### 8-5. 인증 실패 테스트

```bash
# 인증 헤더 없음
curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"job":"meta_ads_manager","function":"update_ads"}'
# 기대: 401 {"detail": "Authentication required"}

# 잘못된 서명
curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $(date +%s)" \
  -H "X-Webhook-Signature: sha256=invalid_signature" \
  -d '{"job":"meta_ads_manager","function":"update_ads"}'
# 기대: 401 {"detail": "Invalid signature"}

# 만료된 타임스탬프 (10분 전)
curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: $(($(date +%s) - 600))" \
  -H "X-Webhook-Signature: sha256=some_sig" \
  -d '{"job":"meta_ads_manager","function":"update_ads"}'
# 기대: 401 {"detail": "Request expired"}

# 레거시 정적 토큰 (하위 호환)
curl -s -X POST https://sidehook.boosters-labs.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: qnfvodmlzjajtmrhdtlr" \
  -d '{"job":"meta_ads_manager","function":"update_ads","user_email":"default@email.com","test":true}'
# 기대: 200 (레거시 모드로 정상 처리)
```

---

## 6. 데이터 흐름도

### 6-1. update_ads 흐름

```
[Google Apps Script]
  │
  │  POST /webhook
  │  job=meta_ads_manager, function=update_ads, user_email=...
  │
  ▼
[FastAPI Router] ─── X-Webhook-Token 검증
  │
  │  execute_job("meta_ads_manager", "update_ads", payload)
  │
  ▼
[jobs/meta_ads_manager.py::update_ads(payload)]
  │
  ├─► [BOOSTA DB] SELECT MAX(date_start) FROM facebook_data_ads
  ├─► [BOOSTA DB] SELECT campaign_name, ad_id, ad_name FROM facebook_data_ads
  ├─► [BOOSTA DB] SELECT * FROM facebook_id_ads (7개 # 조건)
  │
  ├─► [Google Sheet] 1_광고이름생성 읽기
  ├─► [Google Sheet] 2_삭제광고 읽기
  │
  ├─► DataFrame 머지/비교 (변경대상, 등록대상 산출)
  │
  ├─► [Google Sheet] 2_변경대상광고 클리어 + 쓰기
  ├─► [Google Sheet] 2_등록대상광고 클리어 + 쓰기
  │
  ├─► [Slack] 변경대상 알림 (채널 또는 DM)
  └─► [Slack] 등록대상 알림 (채널 또는 DM)
```

### 6-2. add_ad 흐름

```
[Google Apps Script]
  │
  ▼
[jobs/meta_ads_manager.py::add_ad(payload)]
  │
  ├─► [Google Sheet] 2_등록대상광고 읽기 (Key 컬럼 확인)
  ├─► [Google Sheet] 0_키워드생성 읽기 (중복 키워드 확인)
  │
  ├─► [Google Sheet] 0_키워드생성에 키워드 추가 (append)
  ├─► [Google Sheet] 1_광고이름생성에 광고 추가 (append)
  ├─► [Google Sheet] 2_등록대상광고 클리어 + 잔여 데이터 쓰기
  │
  ├─► [Slack] 등록 완료 알림 (DM)
  └─► update_ads({"user_email": default_email}) 내부 호출
```

---

## 9. 에러 처리 설계

### 9-1. 서버 측

| 에러 유형 | HTTP 코드 | 대응 |
|-----------|-----------|------|
| 인증 헤더 없음 | 401 | `"Authentication required"` |
| HMAC 서명 불일치 | 401 | `"Invalid signature"` |
| 타임스탬프 만료 (5분) | 401 | `"Request expired"` |
| 레거시 토큰 불일치 | 401 | `"Invalid webhook token"` |
| job/function 누락 | 400 | `handle_webhook` 검증 |
| 미등록 job/function | 400 | `ALLOWED_JOBS` 화이트리스트 |
| 실행 중 예외 | 500 | 에러 로그 + Slack 알림 전송 |

### 9-2. 클라이언트 측 (Apps Script)

| 에러 유형 | 대응 |
|-----------|------|
| 네트워크 에러 | `UrlFetchApp.fetch` 예외 → 기본 에러 팝업 |
| HTTP 4xx/5xx | `muteHttpExceptions`로 수신 → toast 알림으로 에러 표시 |
| JSON 파싱 실패 | try-catch → 원본 텍스트 그대로 toast |
| 타임아웃 (60초 초과) | `UrlFetchApp` 기본 타임아웃 → 에러 팝업 |

---

## 10. 전환 계획

### 10-1. 전환 순서

```
Step 1: 서버 코드 배포 (HMAC 인증 + 테스트 채널 + 레거시 호환)
  ↓
Step 2: curl + HMAC 서명으로 서버 검증 (test:true → 테스트 채널)
  ↓
Step 3: Google Apps Script에 새 코드 배포
  ↓ (기존 코드는 주석 처리 또는 별도 함수로 보관)
Step 4: Apps Script에서 실제 호출 테스트 (각 함수 1회씩)
  ↓
Step 5: 정상 동작 확인 후 기존 코드 삭제
  ↓
Step 6: 1-2일 모니터링 후 레거시 토큰 인증 제거
```

### 10-2. 롤백 계획

| 상황 | 롤백 방법 |
|------|-----------|
| 새 서버 장애 | Apps Script에서 URL/토큰을 기존 Django 값으로 되돌림 |
| HMAC 인증 문제 | 서버의 dual-mode가 레거시 토큰도 지원하므로 즉시 폴백 |
| 특정 함수 오류 | 해당 함수만 기존 코드로 복원 |
| 전체 장애 | Git revert + Apps Script 전체 복원 |

> 기존 Django 서버를 즉시 내리지 않고, 마이그레이션 완료 후 안정화 기간을 두고 종료.

---

## 11. 산출물 목록

| # | 산출물 | 경로/위치 | 상태 |
|---|--------|-----------|------|
| 1 | `app/dependencies.py` | HMAC dual-mode 인증 | 수정 필요 |
| 2 | `app/config.py` | `WEBHOOK_SECRET`, `SLACK_CHANNEL_ID_TEST` 추가 | 수정 필요 |
| 3 | `app/router.py` | 의존성 함수명 변경 | 수정 필요 |
| 4 | `jobs/meta_ads_manager.py` | `_get_channel_id()` 테스트 채널 지원 | 수정 필요 |
| 5 | `.env` | `WEBHOOK_SECRET` 추가 | 수정 필요 |
| 6 | Google Apps Script 전체 코드 | Google Sheets Apps Script 에디터 | 작성 필요 |
| 7 | curl 테스트 스크립트 | `tests/test_meta_ads_curl.sh` | 작성 필요 |
