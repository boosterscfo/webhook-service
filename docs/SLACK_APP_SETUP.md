# Slack 앱 설정 가이드 (Amazon Researcher `/amz`)

## 1. 웹훅 URL

엔드포인트 경로는 **고정**이며, 서버 도메인만 환경에 따라 다릅니다.

| 환경 | 웹훅 URL |
|------|-----------|
| **프로덕션** | `https://sidehook.boosters-labs.com/slack/amz` |
| 로컬 | `http://localhost:9000/slack/amz` (Slack은 HTTPS 요구 시 사용 불가) |

- 라우터: `amz_researcher/router.py` → `POST /slack/amz` (prefix 없음)
- 메인 앱에서 `app.include_router(amz_router)` 만 하므로 **경로는 `/slack/amz`**

---

## 2. 슬래시 커맨드 설정 (Slack 앱 관리)

### 2.1 Slash Commands 등록

1. [api.slack.com/apps](https://api.slack.com/apps) → 해당 앱 선택
2. 왼쪽 **Features** → **Slash Commands** → **Create New Command**
3. 다음처럼 입력:

| 항목 | 값 |
|------|-----|
| **Command** | `/amz` |
| **Request URL** | `https://sidehook.boosters-labs.com/slack/amz` |
| **Short Description** | 예: Amazon 키워드 성분 분석 |
| **Usage Hint** | `prod {키워드} [--refresh]` (선택, 사용자 안내용) |

- **Escape channels, users, and links sent to your app**: 필요 시 체크 (멘션/링크를 이스케이프해서 받을 때)
- 저장 후 **Reinstall to Workspace** 하면 새 권한/커맨드가 반영됨

### 2.2 현재 코드 기준 사용법 (설정과 일치시키기)

실제 동작하는 형식은 아래와 같습니다 (라우터에서 검사).

| 입력 | 동작 |
|------|------|
| `/amz prod hair serum` | 정상: `hair serum` 키워드로 분석 시작 |
| `/amz prod toner pad --refresh` | 정상: 캐시 무시하고 최신 데이터로 분석 |
| `/amz prod` | 에러: 키워드 없음 → "사용법: /amz prod {키워드} [--refresh]" |
| `/amz dev ...` 또는 그 외 서브커맨드 | 에러: "알 수 없는 명령" (현재는 `prod`만 허용) |

- **서브커맨드**: 반드시 `prod`
- **키워드**: `prod` 다음에 한 칸 띄우고 입력, 여러 단어 가능
- **옵션**: `--refresh` 있으면 캐시 무시

Slack **Usage Hint**에는 다음처럼 넣어두면 됩니다.

```text
prod {키워드} [--refresh]
```

---

## 3. 설정 시 고려할 권한 (Bot Token Scopes)

아래 스코프는 **OAuth & Permissions** → **Bot Token Scopes**에 추가합니다.

| Scope | 용도 | 사용처 (코드) |
|-------|------|----------------|
| **`commands`** | 슬래시 커맨드 `/amz` 등록·호출 | Slack이 Request URL로 POST 보낼 때 필요 |
| **`chat:write`** | 채널/DM에 메시지 전송 | `chat.postMessage` (채널 공지, DM) |
| **`files:write`** | 파일 업로드 | `files.getUploadURLExternal`, `files.completeUploadExternal` (엑셀 업로드) |
| **`im:write`** | DM 대화 열기 | `conversations.open` (관리자에게 DM으로 결과 요약) |

### 3.1 API ↔ Scope 매핑

| API (slack_sender.py) | 필요한 Scope |
|------------------------|--------------|
| `response_url` POST (Slack이 준 URL) | 별도 scope 없음 (Slack이 발급한 URL로 1회성 전송) |
| `chat.postMessage` | `chat:write` |
| `files.getUploadURLExternal` + `files.completeUploadExternal` | `files:write` |
| `conversations.open` | `im:write` |
| `chat.postMessage` (DM 채널로) | `chat:write` |

### 3.2 권한 요약

- **최소 (슬래시만 응답·메시지·파일)**  
  `commands`, `chat:write`, `files:write`
- **관리자 DM까지**  
  위 3개 + `im:write`

앱 재설치 후에는 **Reinstall to Workspace** 해야 새 스코프가 적용됩니다.

---

## 4. 환경 변수 (서버 측)

Slack 앱에서 발급한 **Bot User OAuth Token**을 서버에 넣어야 합니다.

| 변수 | 설명 |
|------|------|
| `AMZ_BOT_TOKEN` | Bot User OAuth Token (xoxb-…) — 메시지·파일 업로드·DM |
| `AMZ_ADMIN_SLACK_ID` | (선택) 완료 후 DM 받을 관리자 Slack user ID (U…) |

- Slash Command 자체는 **Request URL만 맞으면** 토큰 없이도 호출되지만,  
  실제 메시지·파일 전송은 `AMZ_BOT_TOKEN`이 있어야 동작합니다.

---

## 5. 체크리스트

- [ ] Slash Command: `/amz`, Request URL = `https://sidehook.boosters-labs.com/slack/amz`
- [ ] Usage Hint: `prod {키워드} [--refresh]`
- [ ] Bot Token Scopes: `commands`, `chat:write`, `files:write`, `im:write` (DM 사용 시)
- [ ] 앱 재설치(Reinstall to Workspace)로 스코프 반영
- [ ] 서버 `.env`에 `AMZ_BOT_TOKEN` 설정
- [ ] (선택) `AMZ_ADMIN_SLACK_ID` 설정 후 DM 전송 확인
