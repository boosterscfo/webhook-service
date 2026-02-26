# Plan: SlackNotifier 리팩터링

> lib/slack.py 보안 취약점 수정 및 코드 품질 개선

---

## 1. 개요

### 배경
`lib/slack.py`의 `SlackNotifier` 클래스는 웹훅 수신 후 다양한 서비스 메시지(에러 알림, 작업 완료 알림, Meta 광고 알리미 등)를 Slack으로 전달하는 핵심 라이브러리이다. 코드 리뷰 결과 **SQL Injection 취약점 1건**과 코드 품질 개선 포인트가 발견되었다.

### 목표
- **Critical**: `find_slackid`의 SQL Injection 취약점 해결
- **Medium**: 에러 핸들링 및 로깅 추가
- **Low**: `notify` 메서드의 `user_id`/`channel_id` 동시 전달 시 동작 명확화

### 영향 범위
| 파일 | 호출 위치 | 영향 |
|------|-----------|------|
| `lib/slack.py` | 직접 수정 대상 | 전체 |
| `jobs/meta_ads_manager.py` | `SlackNotifier.find_slackid`, `SlackNotifier.notify` 사용 | 호출부 변경 없음 |
| `jobs/global_boosta.py` | `SlackNotifier.find_slackid`, `SlackNotifier.notify` 사용 | 호출부 변경 없음 |
| `app/router.py` | `SlackNotifier.notify` (에러 알림) 사용 | 호출부 변경 없음 |

---

## 2. 개선 항목

### 2-1. [Critical] SQL Injection 취약점 수정

**현상**: `find_slackid` 메서드에서 `email` 파라미터를 f-string으로 SQL에 직접 삽입
```python
# AS-IS (취약)
f"AND email = '{email}'"
```

**위험**: 웹훅 payload의 `user_email` 필드가 직접 전달되므로, 악의적 입력으로 임의 SQL 실행 가능

**해결**: `MysqlConnector.read_query_table`의 `params` 파라미터를 활용한 파라미터 바인딩
```python
# TO-BE (안전)
query = "... AND email = %s"
df = conn.read_query_table(query, (email,))
```

**근거**: `MysqlConnector.read_query_table`이 이미 `params: tuple | None` 파라미터를 지원 (mysql_connector.py:75)

### 2-2. [Medium] 에러 핸들링 및 로깅 추가

**현상**:
- `logger = logging.getLogger(__name__)` 선언만 있고 어디서도 사용하지 않음
- Slack API 호출 실패 시 예외가 그대로 전파되어 웹훅 요청 자체가 실패할 수 있음

**해결**:
- `send` 메서드에 Slack API 에러 로깅 추가
- `find_slackid`에 DB 조회 에러 로깅 추가
- 예외 전파는 유지하되, 호출 추적을 위한 로그 기록

### 2-3. [Low] notify 메서드 동작 명확화

**현상**: `user_id`와 `channel_id`를 동시에 전달하면 `user_id`가 우선되고 `channel_id`는 무시됨. `meta_ads_manager.py`의 `slack_send` 함수에서 둘 다 전달하는 경우가 있음.

**해결**: 의도적 설계임을 docstring으로 명시. DM 우선 정책 문서화.

---

## 3. 구현 계획

| # | 작업 | 심각도 | 예상 변경 |
|---|------|--------|-----------|
| 1 | `find_slackid` SQL 파라미터 바인딩 적용 | Critical | 2줄 수정 |
| 2 | `send` 메서드 로깅 추가 | Medium | 5줄 추가 |
| 3 | `find_slackid` 에러 로깅 추가 | Medium | 3줄 추가 |
| 4 | `notify` docstring 추가 (DM 우선 정책 명시) | Low | docstring 추가 |

### 변경 파일
- `lib/slack.py` — 유일한 수정 대상

### 호출부 영향
- **없음**: 모든 수정이 `SlackNotifier` 내부에서 완결. 메서드 시그니처 변경 없음.

---

## 4. 검증 계획

- 기존 테스트 실행으로 회귀 확인
- `find_slackid`의 파라미터 바인딩이 정상 동작하는지 확인
- Slack API 호출 실패 시 로그가 정상 출력되는지 확인

---

## 5. 위험 요소

| 위험 | 영향 | 대응 |
|------|------|------|
| 파라미터 바인딩 후 쿼리 결과 차이 | Low | `%s` 자동 이스케이핑으로 동일 결과 보장 |
| 로깅 추가로 인한 성능 영향 | None | 무시 가능한 수준 |
