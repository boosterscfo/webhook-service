# Design: SlackNotifier 리팩터링

> lib/slack.py 보안 취약점 수정 및 코드 품질 개선 — 상세 기술 설계

**Plan 참조**: [slack-notifier-refactor.plan.md](../../01-plan/features/slack-notifier-refactor.plan.md)

---

## 1. 개요

### 1.1 목적

- **Critical**: `find_slackid`의 SQL Injection 제거 (파라미터 바인딩)
- **Medium**: 에러 핸들링 및 로깅 추가 (`send`, `find_slackid`)
- **Low**: `notify`의 `user_id`/`channel_id` 동시 전달 시 동작을 docstring으로 명확화

### 1.2 변경 범위

| 대상 | 작업 |
|------|------|
| `lib/slack.py` | 유일한 수정 대상 |
| 호출부 (`jobs/meta_ads_manager.py`, `jobs/global_boosta.py`, `app/router.py`) | **변경 없음** (시그니처 유지) |

---

## 2. 아키텍처 및 데이터 흐름

### 2.1 SlackNotifier 역할

```
웹훅/잡 호출자
  │
  ├─ find_slackid(email) ──► BOOSTA DB (admin.flex_users) ──► slack_id 반환
  │
  └─ notify(...) / send(...) ──► Slack API (WebClient) ──► 메시지 전송
```

- `find_slackid`: 웹훅 payload의 `user_email`로 DB에서 `slack_id` 조회 (여기서 **email이 SQL에 직접 삽입되면 안 됨**).
- `send` / `notify`: Slack 채널 또는 DM으로 메시지 전송.

### 2.2 의존성

| 의존성 | 용도 |
|--------|------|
| `slack_sdk.WebClient` | Slack API 호출 |
| `app.config.settings` | 봇 토큰 (`BOOSTA_BOT_TOKEN` 등) |
| `lib.mysql_connector.MysqlConnector` | `find_slackid`에서만 lazy import, BOOSTA DB 조회 |

---

## 3. 상세 설계

### 3.1 [Critical] find_slackid — SQL 파라미터 바인딩

**요구사항**: `email`을 절대 f-string 등으로 SQL에 직접 넣지 않고, `MysqlConnector.read_query_table`의 `params` 인자만 사용한다.

**쿼리 형태 (TO-BE)**:

```python
query = (
    "SELECT slack_id FROM admin.flex_users "
    "WHERE slack_id IS NOT NULL AND slack_id != '' "
    "AND email = %s"
)
df = conn.read_query_table(query, (email,))
```

**금지 (AS-IS)**:

```python
# 금지: 문자열 포맷으로 값 삽입
f"AND email = '{email}'"
"AND email = '" + email + "'"
```

**근거**: `lib/mysql_connector.py`의 `read_query_table(query, params)`가 이미 `cursor.execute(query, params)`로 파라미터 바인딩을 수행함. `%s`와 튜플만 사용하면 SQL Injection이 방지됨.

---

### 3.2 [Medium] 에러 핸들링 및 로깅

**요구사항**:

1. **`send` 메서드**  
   - Slack API 호출 실패 시 예외 전파는 유지.  
   - 전파 전에 `logger.exception(...)`으로 로그 기록 (봇명, channel_id, user_id 포함).

2. **`find_slackid` 메서드**  
   - DB 조회 예외 시 `logger.exception(...)`으로 로그 기록 (email 포함).  
   - 예외 시 `None` 반환 유지.  
   - 조회 결과가 없을 때(empty DataFrame) `logger.debug(...)`로 기록 (선택).

**로깅 포맷 예시**:

```python
# send 실패 시
logger.exception(
    "Slack API error (bot=%s, channel=%s, user=%s)",
    bot_name, channel_id, user_id
)

# find_slackid DB 예외 시
logger.exception("Failed to look up Slack ID for email=%s", email)
```

**주의**: `logger`는 이미 `logging.getLogger(__name__)`으로 선언되어 있어야 하며, 모듈 전역에서 일관되게 사용. `send()`에서 예외 발생 시 `user_id`만 있고 `conversations_open` 전이면 `channel_id`는 아직 없을 수 있으므로, 로그에는 "가능한 경우" channel_id/user_id를 포함하면 됨.

---

### 3.3 [Low] notify — docstring (DM 우선 정책)

**요구사항**: `user_id`와 `channel_id`를 동시에 넘겼을 때 **user_id가 우선**되고 channel_id는 무시된다는 점을 docstring에 명시.

**docstring 예시**:

```python
def notify(
    ...
) -> dict:
    """Send a structured Slack notification with header, body, footer, and optional URL button.

    When both user_id and channel_id are provided, user_id takes priority (DM first policy).
    """
```

호출부(`meta_ads_manager.slack_send` 등)는 수정하지 않음. 동작 변경 없음.

---

## 4. 구현 체크리스트

| # | 작업 | 심각도 | 검증 기준 |
|---|------|--------|-----------|
| 1 | `find_slackid`: 쿼리에 `%s` 사용 + `read_query_table(query, (email,))` 호출 | Critical | 쿼리 문자열에 `email` 변수 또는 `.format()`/f-string 사용 없음. 값은 `params` 튜플로만 전달 |
| 2 | `send`: Slack API 예외 시 `logger.exception(...)` 호출 후 raise | Medium | `raise` 전에 `logger.exception` 호출. 로그 메시지에 bot_name, channel_id, user_id 중 설정된 값 포함 |
| 3 | `find_slackid`: DB 예외 시 `logger.exception(...)` 호출, 실패 시 `None` 반환 | Medium | DB 오류 시 로그 출력 및 반환값 `None` 확인 |
| 4 | `notify`: docstring에 "user_id 우선 (DM first)" 명시 | Low | docstring 존재 및 "user_id takes priority" 의미 일치 |

---

## 5. 보안 고려사항

| 항목 | 내용 |
|------|------|
| SQL Injection | `email`은 반드시 `params` 튜플로만 전달. 쿼리 문자열에는 `%s`만 사용. |
| 로그 개인정보 | `logger.exception`에 email/slack_id를 넣을 수 있으나, 운영 로그 정책에 따라 필요 시 마스킹 검토. |
| Slack 토큰 | 기존과 동일하게 `settings`에서 읽어오며, 코드 저장소에 하드코딩하지 않음. |

---

## 6. 테스트 및 검증

**검증 방법**: 수동 시나리오 + 로그 확인. (기존 pytest가 있다면 실행으로 회귀 확인.)

- 기존 테스트/수동 시나리오로 회귀 확인.
- `find_slackid`에 정상 email 전달 시 기대한 `slack_id` 반환.
- Slack API 실패 시(잘못된 채널/토큰 등) 해당 요청에서 `logger.exception` 로그가 한 번 이상 출력되는지 확인.

---

## 7. 위험·제약 사항 (Plan §5 반영)

| 위험 | 영향 | 대응 |
|------|------|------|
| 파라미터 바인딩 전환 후 쿼리 결과 차이 | Low | `%s` 자동 이스케이핑으로 기존과 동일 결과 기대. 필요 시 스모크 테스트로 확인 |
| 로깅 추가로 인한 성능 영향 | None | 무시 가능한 수준 |

---

## 8. 관련 문서

- Plan: [slack-notifier-refactor.plan.md](../../01-plan/features/slack-notifier-refactor.plan.md)
- `lib/mysql_connector.py`: `read_query_table(query, params)` 시그니처 및 사용법

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-03-09 | 초안 (Plan 기반 상세 설계) | CTO/Design |
