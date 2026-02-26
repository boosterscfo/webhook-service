# Plan: Meta Ads Webhook Migration

> Google Apps Script → FastAPI 웹훅 서비스로 Meta 광고 관리 기능 마이그레이션

---

## 1. 개요

### 배경
기존 Django 서버(`https://boostb.boosters-labs.com`)에서 Google Apps Script를 통해 웹훅으로 호출하던 Meta 광고 관리 기능을 현재 FastAPI 웹훅 서비스(`https://sidehook.boosters-labs.com`)로 마이그레이션한다.

서버 측 코드(`jobs/meta_ads_manager.py`)와 라우터(`app/router.py`)는 이미 구현 완료 상태이며, **클라이언트 측(Google Apps Script) 코드 업데이트**와 **연동 검증**이 핵심 작업이다.

### 목표
- Google Apps Script가 새 FastAPI 서버 엔드포인트로 호출하도록 변경
- 기존과 동일한 6개 함수가 정상 동작함을 검증
- 마이그레이션 가이드 문서를 통해 클라이언트 수정 방법 제공

---

## 2. 현재 상태 분석

### 2-1. 서버 측 (FastAPI) — 이미 완료

| 항목 | 현재 상태 |
|------|-----------|
| 엔드포인트 | `POST /webhook` |
| 인증 | `X-Webhook-Token` 헤더 |
| 라우팅 | `ALLOWED_JOBS`에 `meta_ads_manager` 6개 함수 등록됨 |
| 코드 | `jobs/meta_ads_manager.py` 마이그레이션 완료 |
| 라이브러리 | `lib/google_sheet.py`, `lib/mysql_connector.py`, `lib/slack.py` 구현 완료 |
| 배포 | Docker + Caddy (`sidehook.boosters-labs.com`) 운영 중 |

### 2-2. 등록된 함수 목록

```python
ALLOWED_JOBS = {
    "meta_ads_manager": [
        "update_ads",           # 광고 업데이트 (변경/등록대상 비교)
        "add_ad",               # 광고 등록
        "regis_slack_send",     # 변경대상 Slack 알림 (채널)
        "unregis_slack_send",   # 등록대상 Slack 알림 (채널)
        "unregis_user_slack_send",  # 등록대상 Slack 알림 (개인)
        "regis_user_slack_send",    # 변경대상 Slack 알림 (개인)
    ],
}
```

### 2-3. 클라이언트 측 (Google Apps Script) — 변경 필요

| 항목 | 기존 (Django) | 신규 (FastAPI) |
|------|---------------|----------------|
| **URL** | `https://boostb.boosters-labs.com/webhooks/mPnBRC1qxapOAxQpWmjy4NofbgxCmXSj/` | `https://sidehook.boosters-labs.com/webhook` |
| **인증 헤더** | `Webhook-Token` | `X-Webhook-Token` |
| **토큰 값** | `webhook_token_uusihfuhokdwjifasdoijf^&%(*&` | 환경변수 `WEBHOOK_TOKEN` 참조 |
| **모듈 지정** | `"api": "dev.google_sheet_to_db.get_sheet.meta_ads_manager"` | `"job": "meta_ads_manager"` |
| **함수 지정** | `"function": "update_ads"` | `"function": "update_ads"` (동일) |
| **추가 파라미터** | `"user_email"`, `"trigger"` 등 | 동일하게 전달 |

---

## 3. Google Apps Script 함수 ↔ FastAPI 매핑

| # | Apps Script 함수 | payload.function | 추가 파라미터 | 용도 |
|---|------------------|------------------|---------------|------|
| 1 | `update_ads()` | `update_ads` | `user_email` | 광고 변경/등록 대상 업데이트 |
| 2 | `trigger_update()` | `update_ads` | `user_email`, `trigger: true` | 트리거에 의한 광고 업데이트 |
| 3 | `register_ads()` | `add_ad` | `user_email` | 광고 등록 |
| 4 | `unregis_user_slack_send()` | `unregis_user_slack_send` | `user_email` | 등록대상 개인 Slack 알림 |
| 5 | `regis_user_slack_send()` | `regis_user_slack_send` | `user_email` | 변경대상 개인 Slack 알림 |

> `regis_slack_send`, `unregis_slack_send`는 Apps Script에서 직접 호출하지 않으나, 서버 측에 등록되어 있어 필요 시 호출 가능.

---

## 4. 변경 사항 상세

### 4-1. Google Apps Script 변경 내용

**공통 변경:**
```
변경 전: var url = 'https://boostb.boosters-labs.com/webhooks/mPnBRC1qxapOAxQpWmjy4NofbgxCmXSj/';
변경 후: var url = 'https://sidehook.boosters-labs.com/webhook';

변경 전: 'Webhook-Token': 'webhook_token_uusihfuhokdwjifasdoijf^&%(*&'
변경 후: 'X-Webhook-Token': '<NEW_TOKEN>'

변경 전: "api": "dev.google_sheet_to_db.get_sheet.meta_ads_manager"
변경 후: "job": "meta_ads_manager"
```

**payload 구조 변경 예시 (update_ads):**

```
변경 전:
{
  "api": "dev.google_sheet_to_db.get_sheet.meta_ads_manager",
  "function": "update_ads",
  "user_email": userEmail
}

변경 후:
{
  "job": "meta_ads_manager",
  "function": "update_ads",
  "user_email": userEmail
}
```

### 4-2. 서버 측 검증 필요 사항

| 검증 항목 | 상태 | 비고 |
|-----------|------|------|
| `update_ads(payload)` — `payload.get("user_email")` | 확인 필요 | Apps Script에서 `user_email` 키 전달 |
| `update_ads(payload)` — `payload.get("trigger")` | 확인 필요 | `trigger_update()`에서 `true` 전달 |
| `add_ad(payload)` — `payload.get("user_email")` | 확인 필요 | 기본값 `default@email.com` 사용 |
| Slack 알림 정상 발송 | 확인 필요 | `META_BOT_TOKEN` 유효성 |
| MySQL 쿼리 정상 실행 | 확인 필요 | BOOSTA DB 접근 가능 여부 |
| Google Sheet 읽기/쓰기 | 확인 필요 | 서비스 계정 권한 |

---

## 5. 구현 순서

### Phase 1: 서버 측 검증
- [ ] `curl`로 각 함수 호출 테스트 (인증 토큰 + payload)
- [ ] `update_ads` 호출 — DB 쿼리, Sheet 갱신, Slack 알림 확인
- [ ] `add_ad` 호출 — 광고 등록 로직 확인
- [ ] `regis_user_slack_send`, `unregis_user_slack_send` — Slack DM 발송 확인

### Phase 2: Google Apps Script 업데이트
- [ ] 공통 설정 변수 정리 (URL, 헤더, 토큰)
- [ ] 5개 함수 payload 구조 변경 (`api` → `job`)
- [ ] `getEmailSafely()` — 변경 없음 (유지)

### Phase 3: 통합 테스트
- [ ] Apps Script → FastAPI 실제 호출 테스트
- [ ] 각 함수별 정상 응답 확인 (`SpreadsheetApp.toast` 결과)
- [ ] 에러 시 Slack 알림 동작 확인

### Phase 4: 전환 완료
- [ ] 기존 Django 서버 호출 제거 (Apps Script에서 old URL 삭제)
- [ ] 모니터링 기간 운영 (1-2일)

---

## 6. 리스크 및 고려사항

| 리스크 | 대응 |
|--------|------|
| Apps Script에서 새 서버 접근 불가 | sidehook.boosters-labs.com DNS 확인, HTTPS 정상 여부 체크 |
| 토큰 노출 위험 | Apps Script 속성 서비스(PropertiesService) 사용 권장 |
| 기존 Django 서버와 동시 운영 충돌 | 동일 Sheet를 양쪽에서 쓰지 않도록 전환 시점 조율 |
| `trigger` 파라미터 boolean vs string | FastAPI는 JSON boolean `true`를 정상 수신, Apps Script에서 `true` (boolean)로 전송 확인 |
| 장시간 처리 (~23초) | FastAPI 타임아웃 60초 이내, Apps Script UrlFetchApp 타임아웃(60초) 이내 |
| Slack 봇 토큰 유효성 | `.env`의 `META_BOT_TOKEN` 유효한지 사전 확인 |

---

## 7. 산출물

| 산출물 | 경로/위치 |
|--------|-----------|
| 업데이트된 Google Apps Script 코드 | Google Sheets 연결된 Apps Script 에디터 |
| 서버 측 테스트 결과 | curl 테스트 로그 |
| 마이그레이션 가이드 | 이 Plan 문서의 섹션 4 참조 |
