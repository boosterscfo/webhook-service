# [Design] ad-name-migration

> BOOSTA DB에서 Active 광고를 추출, 파싱, Google Sheets에 기록하는 웹훅 기능의 상세 설계

**Plan 참조**: `docs/01-plan/features/ad-name-migration.plan.md`

---

## 1. 아키텍처 개요

```
n8n / 수동 호출
  │
  ▼  POST /webhook
┌─────────────────────────────────────────────────────────┐
│ app/router.py                                           │
│   ALLOWED_JOBS["ad_migration"] = ["run_extract"]        │
│   → jobs.ad_migration.run_extract(payload)              │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│ jobs/ad_migration.py                                    │
│                                                         │
│  run_extract(payload)                                   │
│    ├─ _extract_active_ads(conn)      → df_ads           │
│    ├─ _extract_performance(conn,ids) → df_30d, df_total │
│    ├─ _merge_data(df_ads, df_30d, df_total) → df       │
│    ├─ _parse_legacy_names(df)        → df (+ 파싱 컬럼) │
│    ├─ _paste_to_sheet(gsapi, df)     → result           │
│    └─ _notify_slack(payload, stats)  → result           │
└──────────┬──────────────┬───────────────────────────────┘
           │              │
     ┌─────┘              └─────┐
     ▼                          ▼
┌──────────┐          ┌──────────────────┐
│ BOOSTA   │          │ Google Sheets    │
│ MySQL DB │          │ 1qmbkOETk...     │
│          │          │ 시트: 변경대상광고 │
└──────────┘          └──────────────────┘
```

---

## 2. 파일 변경 목록

| 파일 | 작업 | 변경 내용 |
|------|------|-----------|
| `jobs/ad_migration.py` | **신규 생성** | 마이그레이션 추출 잡 모듈 전체 |
| `app/router.py` | **수정** | `ALLOWED_JOBS`에 `"ad_migration": ["run_extract"]` 추가 |

> 기존 파일 `lib/mysql_connector.py`, `lib/google_sheet.py`, `lib/slack.py`, `jobs/meta_ads_manager.py`는 변경하지 않음

---

## 3. 상세 설계: `jobs/ad_migration.py`

### 3.1 모듈 상수

```python
MIGRATION_SHEET_ID = "1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{MIGRATION_SHEET_ID}/"
TARGET_SHEET_NAME = "변경대상광고"
CHANNEL_ID = "C06NZHCD17F"  # Meta 광고 Slack 채널 (기존과 동일)
```

### 3.2 SQL 쿼리 상수

```python
STEP1_QUERY = """
SELECT
    fia.id          AS internal_ad_id,
    fia.ad_id       AS meta_ad_id,
    fia.name        AS ad_name,
    fia.product_name,
    fia.ad_type,
    fia.author,
    fia.start_time  AS ad_start_time,
    fis.id          AS internal_adset_id,
    fis.adset_id    AS meta_adset_id,
    fis.name        AS adset_name,
    fis.start_time  AS adset_start_time,
    fic.id          AS internal_campaign_id,
    fic.campaign_id AS meta_campaign_id,
    fic.name        AS campaign_name
FROM facebook_id_ads fia
INNER JOIN facebook_id_adsets fis ON fia.adset_id = fis.id
INNER JOIN facebook_id_campaigns fic ON fis.campaign_id = fic.id
WHERE fic.name LIKE %s
  AND fia.status = 'ACTIVE'
  AND fis.status = 'ACTIVE'
  AND fic.status = 'ACTIVE'
ORDER BY fia.name
"""

STEP2_QUERY = """
SELECT
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_30d,
    SUM(impressions)                AS impr_30d,
    SUM(clicks)                     AS clicks_30d,
    SUM(fb_pixel_purchase)          AS purchases_30d,
    SUM(fb_pixel_purchase_values)   AS purchase_value_30d
FROM facebook_data_ads
WHERE date_start >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND facebook_id_ad_id IN ({placeholders})
GROUP BY facebook_id_ad_id
ORDER BY spend_30d DESC
"""

STEP3_QUERY = """
SELECT
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_total,
    SUM(impressions)                AS impr_total,
    SUM(fb_pixel_purchase)          AS purchases_total,
    SUM(fb_pixel_purchase_values)   AS purchase_value_total,
    MIN(date_start)                 AS first_data_date,
    MAX(date_start)                 AS last_data_date
FROM facebook_data_ads
WHERE facebook_id_ad_id IN ({placeholders})
GROUP BY facebook_id_ad_id
ORDER BY spend_total DESC
"""
```

> **보안**: Step 1은 `MysqlConnector.read_query_table`의 `params` 인자를 사용하여 파라미터화. Step 2/3의 IN절은 정수 ID 리스트이므로 `",".join(str(int(x)) for x in ids)`로 안전하게 삽입 후 `.format()`으로 치환.

### 3.3 함수 설계

#### `run_extract(payload: dict) -> str`

**엔트리 함수** - 웹훅에서 호출됨

```
Parameters:
  payload.user_email (str, optional): Slack 알림 대상 이메일
  payload.test (bool, optional): True면 테스트 채널로 알림

Returns:
  str: 작업 결과 요약 메시지

Flow:
  1. MysqlConnector("BOOSTA")로 Step 1 실행 → df_ads
  2. df_ads가 비어있으면 조기 리턴
  3. internal_ad_id 목록 추출
  4. Step 2, Step 3 실행 → df_30d, df_total
  5. 3개 DataFrame merge
  6. _parse_legacy_names() 호출
  7. _paste_to_sheet() 호출
  8. _notify_slack() 호출
  9. 결과 문자열 리턴
```

#### `_extract_active_ads(conn: MysqlConnector) -> pd.DataFrame`

```
Parameters:
  conn: BOOSTA DB 연결

Returns:
  DataFrame with columns: internal_ad_id, meta_ad_id, ad_name,
    product_name, ad_type, author, ad_start_time,
    internal_adset_id, meta_adset_id, adset_name, adset_start_time,
    internal_campaign_id, meta_campaign_id, campaign_name

SQL: STEP1_QUERY with params=('%이퀄베리%',)
```

#### `_extract_performance(conn: MysqlConnector, internal_ids: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]`

```
Parameters:
  conn: BOOSTA DB 연결
  internal_ids: internal_ad_id 정수 리스트

Returns:
  (df_30d, df_total) tuple

SQL 파라미터화:
  placeholders = ",".join(str(int(x)) for x in internal_ids)
  STEP2_QUERY.format(placeholders=placeholders)
  STEP3_QUERY.format(placeholders=placeholders)
```

#### `_merge_data(df_ads, df_30d, df_total) -> pd.DataFrame`

```
Logic:
  result = (df_ads
      .merge(df_30d, on="internal_ad_id", how="left")
      .merge(df_total, on="internal_ad_id", how="left")
      .fillna(0)
      .sort_values("spend_30d", ascending=False))
  return result
```

#### `_parse_legacy_names(df: pd.DataFrame) -> pd.DataFrame`

**핵심 파싱 로직** - 구체계 광고명을 `_` 기준으로 분리

```
Input column: ad_name
  예: "260128_v-crm_ao_da_vd_kp_psy_20260128-1"

Output columns (추가):
  parsed_date       : parts[0] - 세팅일자 (YYMMDD 패턴 매칭)
  parsed_product    : parts[1] - 제품코드 (v-crm, v-srm 등)
  parsed_ao_pm      : parts[2] - 상시/프모 (ao, pm)
  parsed_creative   : parts[3] - 제작유형 (da, pa, ugc)
  parsed_material   : parts[4] - 소재유형 (vd, ig, hvd, crs, rl)
  parsed_remainder  : "_".join(parts[5:]) - USP+제작자+기타 (원본 보존)
  parse_error       : bool - 파싱 실패 여부

파싱 규칙:
  1. ad_name을 "_"로 split
  2. parts 길이가 6 미만이면 parse_error = True, 모든 필드 빈 문자열
  3. parts[0]이 6자리 숫자 패턴이 아니면 parse_error = True
  4. parts[2]가 {"ao", "pm"}에 없으면 parse_error = True
  5. 정상이면 각 필드 할당
  6. 항상 원본 ad_name은 보존
```

**구현 상세 (벡터화)**:

```python
def _parse_legacy_names(df: pd.DataFrame) -> pd.DataFrame:
    parts = df["ad_name"].str.split("_")

    # 기본값 설정
    df["parsed_date"] = ""
    df["parsed_product"] = ""
    df["parsed_ao_pm"] = ""
    df["parsed_creative"] = ""
    df["parsed_material"] = ""
    df["parsed_remainder"] = ""
    df["parse_error"] = False

    valid_mask = parts.str.len() >= 6

    df.loc[valid_mask, "parsed_date"] = parts[valid_mask].str[0]
    df.loc[valid_mask, "parsed_product"] = parts[valid_mask].str[1]
    df.loc[valid_mask, "parsed_ao_pm"] = parts[valid_mask].str[2]
    df.loc[valid_mask, "parsed_creative"] = parts[valid_mask].str[3]
    df.loc[valid_mask, "parsed_material"] = parts[valid_mask].str[4]
    df.loc[valid_mask, "parsed_remainder"] = parts[valid_mask].apply(
        lambda x: "_".join(x[5:])
    )

    # 날짜 패턴 검증 (6자리 숫자)
    date_invalid = ~df["parsed_date"].str.match(r"^\d{6}$") & valid_mask
    df.loc[~valid_mask | date_invalid, "parse_error"] = True

    return df
```

#### `_build_sheet_dataframe(df: pd.DataFrame) -> pd.DataFrame`

시트에 붙여넣을 최종 DataFrame 구성

```
Output columns (순서대로):
  1.  internal_ad_id       - 내부 광고 ID
  2.  meta_ad_id           - Meta 광고 ID
  3.  campaign_name        - 캠페인명
  4.  adset_name           - 세트명
  5.  ad_name              - 현재 광고명 (원본)
  6.  parsed_date          - 파싱: 세팅일자
  7.  parsed_product       - 파싱: 제품코드
  8.  parsed_ao_pm         - 파싱: 상시/프모
  9.  parsed_creative      - 파싱: 제작유형
  10. parsed_material      - 파싱: 소재유형
  11. parsed_remainder     - 파싱: USP+제작자+기타
  12. adset_start_time     - 세트 시작일
  13. spend_30d            - 30일 지출
  14. impr_30d             - 30일 노출
  15. purchases_30d        - 30일 구매
  16. spend_total          - 전체 지출
  17. impr_total           - 전체 노출
  18. purchases_total      - 전체 구매
  19. purchase_value_total - 전체 구매 금액
  20. first_data_date      - 최초 데이터 일자
  21. last_data_date       - 최종 데이터 일자
  22. parse_error          - 파싱 오류 여부

정렬: spend_30d DESC
```

#### `_paste_to_sheet(gsapi: GoogleSheetApi, df: pd.DataFrame) -> str`

```
Flow:
  1. gsapi.clear_contents(SPREADSHEET_URL, range="A2:V", sheetname=TARGET_SHEET_NAME)
  2. gsapi.paste_values_to_googlesheet(df, SPREADSHEET_URL, TARGET_SHEET_NAME, "A2")
  3. return result string
```

> **헤더 행(A1)**: 시트에 미리 수동 작성되어 있다고 가정. A2부터 데이터만 붙여넣기.

#### `_notify_slack(payload: dict, total: int, parsed_ok: int, parse_fail: int) -> str`

```
Message format:
  header: "[광고명 마이그레이션] 변경대상 광고 추출 완료"
  body:
    - 추출 광고 수: {total}건
    - 파싱 성공: {parsed_ok}건
    - 파싱 실패: {parse_fail}건
  footer: "Google Sheets에서 확인해주세요."
  url_button: {text: "시트 열기", url: SPREADSHEET_URL}

channel_id: payload.test → settings.SLACK_CHANNEL_ID_TEST, else CHANNEL_ID
user_id: payload.user_email → SlackNotifier.find_slackid()
bot_name: "META"
```

---

## 4. 상세 설계: `app/router.py` 변경

### 4.1 ALLOWED_JOBS 추가

```python
# 변경 전
ALLOWED_JOBS = {
    "cash_mgmt": ["banktransactionUpload"],
    "upload_financial_db": ["upload_financial_db"],
    "global_boosta": ["update_route"],
    "meta_ads_manager": [...],
}

# 변경 후 (1줄 추가)
ALLOWED_JOBS = {
    "cash_mgmt": ["banktransactionUpload"],
    "upload_financial_db": ["upload_financial_db"],
    "global_boosta": ["update_route"],
    "meta_ads_manager": [...],
    "ad_migration": ["run_extract"],       # ← 추가
}
```

---

## 5. 웹훅 호출 인터페이스

### 5.1 Request

```json
POST /webhook
Content-Type: application/json
X-Webhook-Signature: sha256=...
X-Webhook-Timestamp: ...

{
    "job": "ad_migration",
    "function": "run_extract",
    "user_email": "user@eqqualberry.com",
    "test": false
}
```

### 5.2 Response (성공)

```json
{
    "status": "ok",
    "result": "추출 완료: 총 285건 (파싱 성공 240건, 실패 45건). 시트 A2:V286 업데이트."
}
```

### 5.3 n8n 연동

기존 n8n 웹훅 호출 패턴과 동일하게 설정:
- HTTP Request 노드에서 `POST /webhook` 호출
- HMAC 서명 생성 or 레거시 토큰 사용
- 스케줄 트리거: 필요 시 수동 1회 실행 또는 주기적 실행

---

## 6. 데이터 플로우 다이어그램

```
Step 1                    Step 2                    Step 3
────────────────         ────────────────         ────────────────
facebook_id_ads          facebook_data_ads        facebook_data_ads
  + adsets                 30일 성과                전체 성과
  + campaigns            ────────────────         ────────────────
────────────────               │                        │
      │                        │                        │
      │                  ┌─────┘                  ┌─────┘
      ▼                  ▼                        ▼
┌─────────────────────────────────────────────────────┐
│                  pandas merge                        │
│  df_ads.merge(df_30d).merge(df_total)               │
│  on="internal_ad_id", how="left", fillna(0)         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
              _parse_legacy_names()
                       │
                       ▼
              _build_sheet_dataframe()
                       │
                       ▼
              _paste_to_sheet()
                 Google Sheets
           "변경대상광고" 시트 A2:V
                       │
                       ▼
              _notify_slack()
                 Slack 알림
```

---

## 7. 에러 처리

| 시나리오 | 처리 방식 |
|----------|-----------|
| DB 연결 실패 | `MysqlConnector.__exit__` → rollback + 상위 예외 전파 → router에서 500 + Slack 에러 알림 |
| Step 1 결과 0건 | 조기 리턴, Slack으로 "Active 광고 없음" 알림 |
| Step 2/3 IN절 ID가 많을 때 | 정수 ID만 허용 (`str(int(x))`), 쿼리 자체는 200~300건 수준으로 문제 없음 |
| 파싱 실패 | `parse_error=True` 마킹, 데이터 누락 없이 시트에 포함 |
| Google Sheets 권한 없음 | gspread `SpreadsheetNotFound` / `WorksheetNotFound` 예외 → 상위 전파 → Slack 에러 알림 |
| Slack 발송 실패 | 작업 자체에 영향 없음, 로그만 기록 |

---

## 8. 사전 조건 (Pre-requisites)

- [ ] Google Sheets `1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc`에 서비스 계정 편집자 권한 부여
- [ ] `변경대상광고` 시트에 A1행 헤더 작성 (22개 컬럼)
- [ ] BOOSTA DB에 `facebook_id_ads`, `facebook_id_adsets`, `facebook_id_campaigns`, `facebook_data_ads` 테이블 접근 권한 확인

---

## 9. 구현 순서

| 순서 | 작업 | 의존성 |
|------|------|--------|
| 1 | `jobs/ad_migration.py` 파일 생성 + 상수 정의 | 없음 |
| 2 | `_extract_active_ads()` 구현 | Step 1 |
| 3 | `_extract_performance()` 구현 | Step 2 |
| 4 | `_merge_data()` 구현 | Step 2 → 3 |
| 5 | `_parse_legacy_names()` 구현 | Step 4 |
| 6 | `_build_sheet_dataframe()` 구현 | Step 5 |
| 7 | `_paste_to_sheet()` 구현 | Step 6 |
| 8 | `_notify_slack()` 구현 | Step 7 |
| 9 | `run_extract()` 엔트리 함수 조립 | Step 1~8 |
| 10 | `app/router.py` ALLOWED_JOBS 추가 | Step 9 |

---

## 10. 성공 기준 (Plan 참조)

- [ ] Active 광고 전수 추출 (누락 0건)
- [ ] 성과 데이터 정상 merge (`spend_30d`, `spend_total` 확인)
- [ ] 구체계 광고명 파싱 성공률 80% 이상
- [ ] Google Sheets `변경대상광고` 시트 정상 기록
- [ ] Slack 완료 알림 발송
- [ ] 기존 `meta_ads_manager.py` 기능 영향 없음
- [ ] 기존 `lib/` 모듈 변경 없음
