# FastAPI 웹훅 서비스 계획

> 웹훅을 받아서 `dev/` 하위 Python 파일을 안전하게 트리거한다.

---

## 트리거 대상 (현재 운영 중)

| # | 파일 | 함수 | 하는 일 | 후속 동작 |
|---|------|------|---------|-----------|
| 1 | `dev/google_sheet_to_db/get_sheet/cash_mgmt.py` | `banktransactionUpload` | 시트 → MySQL 은행거래/계좌 | Qlik Cloud 트리거 |
| 2 | `dev/google_sheet_to_db/get_sheet/upload_financial_db.py` | `upload_financial_db` | 시트 → MySQL 재무 데이터 | - |
| 3 | `dev/google_sheet_to_db/get_sheet/global_boosta.py` | `update_route` | MySQL ↔ 시트 동기화 | - |
| 4 | `dev/google_sheet_to_db/get_sheet/meta_ads_manager.py` | `update_ads` | 시트 → 광고 데이터 | 추후 광고명 일괄 수정 기획 가능 |

> newsletter 관련(`sent_to_everyone`, `sent_to_clevel`, `main`)은 n8n으로 대체 완료.

---

## 공용 라이브러리 (`_lib/`)
 
| 모듈 | 역할 |
|------|------|
| `_lib/mysql_connector` | MySQL 연결, upsert, temp merge |
| `_lib/google_sheet` | Google Sheets 읽기/쓰기 |
| `dev/google_sheet_to_db/_lib/helper` | Slack 알림 (에러 알림용) |

---

## 웹훅 동작 방식

```
POST /webhooks/{secret_path}/
  ├─ Webhook-Token 헤더 검증
  ├─ payload에서 api, function 추출
  ├─ importlib로 모듈 import → 함수 호출 (동기)
  ├─ 후속 동작 (banktransactionUpload → Qlik 호출)
  ├─ 에러 시 Slack 알림
  └─ 응답
```

현재 payload 예시:
```json
{ "api": "dev.google_sheet_to_db.get_sheet.cash_mgmt", "function": "banktransactionUpload", ... }
```

---

## 해야 할 일

- [ ] FastAPI 프로젝트 생성 (Docker + Caddy)
- [ ] 웹훅 엔드포인트 구현 (동기 처리)
- [ ] `dev/`, `_lib/` 모듈 이전 및 import 경로 설정
- [ ] Slack 에러 알림 공통화
- [ ] 환경변수 정리 (MySQL, Google Sheets, Qlik, Slack, Webhook-Token)
- [ ] 타임아웃 발생 시 Worker 도입 검토

---

## 참고: 소요 시간 (로그 기반)

| 작업 | 시간 |
|------|------|
| 시트 업데이트 (Code 시트 L/Q) | 2~6초 |
| banktransactionUpload | ~18초 |
| meta_ads (변경대상광고) | ~23초 |
