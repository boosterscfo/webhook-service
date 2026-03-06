# [Plan] ad-name-migration

> Meta 광고명 표준화를 위한 변경대상 광고 추출 → Google Sheets 붙여넣기 → 가공 요청 파이프라인

## 1. 개요

### 1.1 배경
EQQUALBERRY의 Meta 광고명이 비표준 상태로 운영되고 있어, 기계적 파싱 및 Shopify UTM 연동이 불가능하다. Active 광고 약 200~300개의 이름을 새 네이밍 규칙에 맞게 마이그레이션해야 한다.

### 1.2 목표
1. BOOSTA DB에서 Active 광고 목록 + 성과 데이터를 추출한다
2. 추출 결과를 Google Spreadsheet(`1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc`)의 `변경대상광고` 시트에 붙여넣는다
3. 기존 광고명을 파싱하여 신규 네이밍 규칙에 필요한 필드를 분리한다
4. 실무자가 검토할 수 있는 형태로 가공한다

### 1.3 범위
- **In Scope**: DB 추출, Google Sheets 기록, 기존 광고명 파싱, Slack 알림
- **Out of Scope**: USP 매핑(Phase 2), Meta API 이름 변경(Phase 4), 운영 자동화(Phase 5)

---

## 2. 현재 시스템 분석

### 2.1 활용 가능한 기존 인프라

| 구성요소 | 파일 | 상태 |
|----------|------|------|
| MySQL 커넥터 | `lib/mysql_connector.py` | `BOOSTA` DB 연결 가능, pandas DataFrame 반환 |
| Google Sheets API | `lib/google_sheet.py` | gspread 기반, 읽기/쓰기/클리어 지원 |
| Slack 알림 | `lib/slack.py` | META_BOT_TOKEN, 채널/DM 전송 |
| 웹훅 라우터 | `app/router.py` | `meta_ads_manager` 잡 모듈 등록 완료 |
| 기존 광고 관리 | `jobs/meta_ads_manager.py` | `update_ads` 등 6개 함수, 유사 패턴 참조 가능 |

### 2.2 기존 코드와의 차이점

| 항목 | 기존 (`meta_ads_manager.py`) | 신규 (본 기능) |
|------|------------------------------|----------------|
| 데이터 소스 | `facebook_data_ads` 단일 테이블 | 3개 쿼리 → pandas merge (마스터 + 성과 30일 + 전체) |
| 대상 시트 | `1zxUeBvU5k8Szvmmp_gBAqV9vCDGf2SGb_xPgxtlYOpg` | `1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc` |
| 광고명 처리 | `#` 구분자 7개 기준 정규식 | `_` 구분자 기반 파싱 (구체계 → 신체계 필드 분리) |
| 조인 키 주의 | 없음 | `facebook_data_ads.facebook_id_ad_id` ≠ `facebook_id_ads.ad_id` (내부 PK vs Meta ID) |

### 2.3 DB 스키마 (관련 테이블)

```
facebook_id_campaigns (캠페인 마스터)
  └─ facebook_id_adsets (세트 마스터, FK: campaign_id → campaigns.id)
      └─ facebook_id_ads (광고 마스터, FK: adset_id → adsets.id)
          └─ facebook_data_ads (일별 성과, FK: facebook_id_ad_id → ads.id)
```

**핵심 주의사항**: `facebook_data_ads.facebook_id_ad_id` → `facebook_id_ads.id` (내부 auto_increment). `facebook_id_ads.ad_id`는 Meta의 실제 광고 ID. 혼동 금지.

---

## 3. 기능 요구사항

### FR-01: Active 광고 추출
- `변경대상광고_쿼리_v1.2.sql` Step 1 실행
- 조건: `이퀄베리` 캠페인, 캠페인/세트/광고 모두 `ACTIVE`
- 결과 컬럼: `internal_ad_id`, `meta_ad_id`, `ad_name`, `product_name`, `ad_type`, `author`, `ad_start_time`, `internal_adset_id`, `meta_adset_id`, `adset_name`, `adset_start_time`, `internal_campaign_id`, `meta_campaign_id`, `campaign_name`

### FR-02: 성과 데이터 추출 + merge
- Step 2 (최근 30일): `spend_30d`, `impr_30d`, `clicks_30d`, `purchases_30d`, `purchase_value_30d`
- Step 3 (전체 기간): `spend_total`, `impr_total`, `purchases_total`, `purchase_value_total`, `first_data_date`, `last_data_date`
- `internal_ad_id` 기준 pandas left merge

### FR-03: 기존 광고명 파싱
- 구체계 광고명을 `_` 기준 split하여 필드 분리 시도:
  - `[0]`: 세팅일자 (YYMMDD)
  - `[1]`: 제품 코드 (`v-crm`, `v-srm` 등)
  - `[2]`: 상시/프모 (`ao`/`pm`)
  - `[3]`: 제작유형 (`da`/`pa`)
  - `[4]`: 소재유형 (`vd`/`ig` 등)
  - `[5:]`: USP + 제작자 + 기타 (자유형, 원본 보존)
- 파싱 실패 시 원본 그대로 보존, `parse_error` 플래그 표시

### FR-04: Google Sheets 기록
- 대상 시트: `https://docs.google.com/spreadsheets/d/1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc/`
- 시트명: `변경대상광고`
- 기존 데이터 클리어 후 새로 붙여넣기
- 컬럼 구성:
  - 식별 정보: `internal_ad_id`, `meta_ad_id`, `campaign_name`, `adset_name`, `ad_name`
  - 파싱 결과: `parsed_product`, `parsed_type`, `parsed_ao_pm`, `parsed_material_type`, `parsed_remainder`
  - 성과 데이터: `spend_30d`, `spend_total`, `impr_30d`, `purchases_30d`
  - 메타 정보: `adset_start_time`, `parse_error`
- `spend_30d` 내림차순 정렬

### FR-05: Slack 알림
- 작업 완료 시 Slack 채널에 알림 발송
- 추출 건수, 파싱 성공/실패 건수, 시트 링크 포함

### FR-06: 웹훅 엔드포인트 등록
- `meta_ads_manager` 잡 모듈에 새 함수 추가
- 또는 별도 잡 모듈 `ad_migration.py` 생성
- `app/router.py`의 `ALLOWED_JOBS`에 등록

---

## 4. 비기능 요구사항

### NFR-01: DB 부하 제어
- 3개 쿼리를 **별도 실행** 후 Python에서 merge (서브쿼리/JOIN 금지)
- Step 2, 3의 `IN (%s)` 절에 `internal_ad_id` 목록을 파라미터로 전달
- COO 서버에서 실행 시 무거운 쿼리 금지 원칙 준수

### NFR-02: 데이터 정합성
- `internal_ad_id` / `meta_ad_id` 혼동 방지 (명확한 변수명 사용)
- 파싱 실패 데이터 손실 방지 (원본 보존)
- 성과 데이터가 없는 광고도 누락 없이 포함 (left merge + fillna(0))

### NFR-03: 기존 코드 영향 최소화
- `lib/` 유틸 모듈 변경 없음
- 기존 `meta_ads_manager.py`의 기존 함수 변경 없음
- 새 함수 추가 또는 새 잡 모듈로 분리

---

## 5. 구현 계획

### 5.1 파일 구조

```
jobs/
├── meta_ads_manager.py      # 기존 (변경 없음)
└── ad_migration.py           # 신규: 마이그레이션 전용 잡 모듈
```

### 5.2 구현 단계

| 단계 | 작업 | 예상 산출물 |
|------|------|-------------|
| Step 1 | `ad_migration.py` 잡 모듈 생성 | 새 파일 |
| Step 2 | `extract_active_ads()` - DB 3단계 쿼리 + merge | DataFrame |
| Step 3 | `parse_legacy_ad_name()` - 구체계 파싱 로직 | 파싱 컬럼 추가된 DataFrame |
| Step 4 | `paste_to_sheet()` - Google Sheets 기록 | 시트 업데이트 |
| Step 5 | `run_migration_extract(payload)` - 웹훅 엔트리 함수 | 웹훅 등록 |
| Step 6 | `app/router.py` ALLOWED_JOBS 업데이트 | 라우터 등록 |
| Step 7 | Slack 알림 연동 | 완료 알림 |

### 5.3 핵심 로직 (pseudo)

```python
def run_migration_extract(payload):
    # 1. DB 추출
    with MysqlConnector("BOOSTA") as conn:
        df_ads = conn.read_query_table(STEP1_QUERY)

    ids = ",".join(df_ads["internal_ad_id"].astype(str))

    with MysqlConnector("BOOSTA") as conn:
        df_30d = conn.read_query_table(STEP2_QUERY % ids)
        df_total = conn.read_query_table(STEP3_QUERY % ids)

    # 2. Merge
    result = (df_ads
        .merge(df_30d, on="internal_ad_id", how="left")
        .merge(df_total, on="internal_ad_id", how="left")
        .fillna(0)
        .sort_values("spend_30d", ascending=False))

    # 3. 파싱
    result = parse_legacy_ad_names(result)

    # 4. Google Sheets 기록
    gsapi = GoogleSheetApi()
    gsapi.clear_contents(SHEET_URL, range="A2:Z", sheetname="변경대상광고")
    gsapi.paste_values_to_googlesheet(result, SHEET_URL, "변경대상광고", "A2")

    # 5. Slack 알림
    SlackNotifier.notify(...)
```

---

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Step 2/3 IN절 광고 수가 많을 때 쿼리 성능 | DB 부하 | 청크 단위 분할 (100개씩) 또는 임시 테이블 활용 |
| 구체계 광고명 형식이 불규칙 | 파싱 실패 증가 | `parse_error` 플래그로 식별, 원본 보존 |
| Google Sheets 행 제한 (5백만 셀) | 대량 데이터 시 실패 | Active 광고 200~300개 수준이므로 문제 없음 |
| 서비스 계정 시트 접근 권한 | 쓰기 실패 | 신규 시트에 서비스 계정 편집자 권한 부여 필요 |

---

## 7. 성공 기준

- [ ] Active 광고 전수 추출 (누락 0건)
- [ ] 성과 데이터 정상 merge (`spend_30d`, `spend_total` 값 확인)
- [ ] 구체계 광고명 파싱 성공률 80% 이상
- [ ] Google Sheets `변경대상광고` 시트에 정상 기록
- [ ] Slack 완료 알림 발송
- [ ] 기존 `meta_ads_manager.py` 기능 영향 없음

---

## 8. 참조 문서

| 문서 | 경로 |
|------|------|
| 프로젝트 스펙 | `docs/00-pre_plan/PROJECT_SPEC.md` |
| DB 쿼리 | `docs/00-pre_plan/변경대상광고_쿼리_v1.2.sql` |
| 기존 광고 관리 코드 | `jobs/meta_ads_manager.py` |
| MySQL 커넥터 | `lib/mysql_connector.py` |
| Google Sheets API | `lib/google_sheet.py` |
