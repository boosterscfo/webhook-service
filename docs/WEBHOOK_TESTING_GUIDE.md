# bankTransactionUpload 웹훅 테스트 가이드

## 1. 웹훅 스펙 요약

| 항목 | 값 |
|------|-----|
| **Endpoint** | `POST /webhook` |
| **인증** | `X-Webhook-Token` 헤더 (`.env`의 `WEBHOOK_TOKEN`과 일치) |
| **Payload** | `job`, `function` 필수 + 추가 데이터(선택) |

**bankTransactionUpload 요청 예시:**
```json
{
  "job": "cash_mgmt",
  "function": "banktransactionUpload"
}
```

---

## 2. 테스트 방법

### 방법 A: curl로 수동 테스트 (가장 간단)

서버 실행 후 터미널에서:

```bash
# 1. 서버 실행 (다른 터미널에서)
# uv run uvicorn main:app --reload --port 9000

# 2. .env에서 WEBHOOK_TOKEN 확인 후
curl -X POST http://localhost:9000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: YOUR_WEBHOOK_TOKEN" \
  -d '{"job": "cash_mgmt", "function": "banktransactionUpload"}'
```

**주의:** 실제 Google Sheets와 MySQL DB에 연결되므로, 운영 환경에서는 데이터가 변경됩니다.  
테스트용 DB/시트가 있다면 해당 환경에서 실행하세요.

---

### 방법 B: pytest + TestClient (자동화 테스트)

**1) 테스트 실행:**
```bash
uv run pytest tests/test_webhook.py -v
```

**2) 포함된 테스트:**
- `test_webhook_banktransaction_upload_success`: bankTransactionUpload 라우팅 성공
- `test_webhook_rejects_missing_token`: 토큰 없을 때 422
- `test_webhook_rejects_invalid_token`: 잘못된 토큰 시 401
- `test_webhook_requires_job_and_function`: job/function 필수 검증
- `test_webhook_rejects_unknown_job/function`: 잘못된 job/function 시 400
- `test_health_endpoint`: /health 확인

**3) 통합 테스트 (실제 호출):**  
- Mock 없이 실제 함수 호출하려면 `execute_job` 패치를 제거하고,  
  `.env`에 테스트용 DB/Sheets 설정 후 실행 (데이터 변경 발생)

---

### 방법 C: 웹훅 수신만 검증 (Mock된 job)

실제 `banktransactionUpload`는 호출하지 않고, **웹훅이 잘 라우팅되는지**만 확인하려면  
테스트 전용 job/function을 추가하거나, 기존 job에 Mock을 적용할 수 있습니다.

---

## 3. 권장 테스트 전략

| 목적 | 권장 방법 |
|------|-----------|
| 웹훅 수신·라우팅 확인 | pytest + Mock (방법 B) |
| 토큰 검증 확인 | pytest + 잘못된/빠진 토큰 시나리오 |
| E2E (실제 DB/시트) | curl 또는 pytest + 실제 env |

---

## 5. curl로 실제 호출 테스트 (E2E)

서버가 `localhost:9000`에서 실행 중일 때:

```bash
# .env의 WEBHOOK_TOKEN 값을 사용
source .env 2>/dev/null || true
curl -X POST http://localhost:9000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $WEBHOOK_TOKEN" \
  -d '{"job": "cash_mgmt", "function": "banktransactionUpload"}'
```

**주의:** 실제 Google Sheets와 MySQL에 접근하므로, 운영 DB가 아닌 테스트 환경에서만 실행할 것을 권장합니다.

---

## 6. dry-run 모드 (선택) 

실제 DB에 쓰지 않고 **로직만 검증**하려면, `banktransactionUpload`에  
`payload`에 `dry_run: true`가 있을 때 DB upsert를 건너뛰는 분기를 추가할 수 있습니다.
