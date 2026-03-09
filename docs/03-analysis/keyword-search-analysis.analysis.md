# keyword-search-analysis Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: webhook-service
> **Analyst**: Gap Detector Agent
> **Date**: 2026-03-09
> **Design Doc**: [keyword-search-analysis.design.md](../02-design/features/keyword-search-analysis.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design document(keyword-search-analysis.design.md)와 실제 구현 코드를 비교하여 일치율을 산출하고, 누락/변경/추가 항목을 식별한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/keyword-search-analysis.design.md`
- **Implementation Files**:
  - `app/config.py`
  - `amz_researcher/services/bright_data.py`
  - `amz_researcher/services/data_collector.py`
  - `amz_researcher/services/product_db.py`
  - `amz_researcher/services/market_analyzer.py`
  - `amz_researcher/services/excel_builder.py`
  - `amz_researcher/orchestrator.py`
  - `amz_researcher/router.py`
  - `amz_researcher/migrations/v6_keyword_search.py`
- **Analysis Date**: 2026-03-09

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Config (Section 4.9)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `AMZ_KEYWORD_CACHE_DAYS: int = 7` | `app/config.py:80` — `AMZ_KEYWORD_CACHE_DAYS: int = 7` | MATCH | |
| 기존 `BRIGHT_DATA_DATASET_ID` 재활용 | `app/config.py:76` — 그대로 사용 | MATCH | |

### 2.2 DB Migration (Section 3 + 5.3)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `amz_keyword_search_log` 스키마 | `migrations/v6_keyword_search.py:4-14` | MATCH | 모든 컬럼, 타입, 디폴트, 인덱스 일치 |
| `amz_keyword_products` 스키마 | `migrations/v6_keyword_search.py:16-48` | MATCH | 모든 26개 컬럼, 타입, 디폴트, 인덱스 일치 |
| `run_migration()` 함수 | `migrations/v6_keyword_search.py:52-61` | MATCH (Added) | 디자인에 없으나 실용적 추가 |

### 2.3 BrightDataService — `trigger_keyword_search()` (Section 4.1)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 메서드 시그니처 `(keyword, limit_per_input=100) -> str` | `bright_data.py:105-109` | MATCH | |
| URL 구성: `discover_by=keyword` | `bright_data.py:114-119` | MATCH | |
| body: `[{"keyword": keyword}]` | `bright_data.py:122` | MATCH | |
| 재시도 로직 (2회) | `bright_data.py:125` — `range(2)` | MATCH | |
| `BrightDataError` 예외 | `bright_data.py:128-129` | MATCH | |
| `snapshot_id` 반환 | `bright_data.py:130-133` | MATCH | |
| 재시도 로깅 | `bright_data.py:138` | MATCH | |
| `dataset_id` 재활용 | `self.dataset_id` 사용 | MATCH | |
| `notify_url` 미사용 | 파라미터 없음 | MATCH | |

### 2.4 DataCollector — `process_search_snapshot()` (Section 4.2)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 메서드 시그니처 `(products, keyword, searched_at) -> int` | `data_collector.py:213-217` | MATCH | |
| 빈 products 체크 → 0 반환 | `data_collector.py:229-230` | MATCH | |
| `_resolve_brand()` 적용 | `data_collector.py:236` | MATCH | |
| `customer_says` / `customers_say` fallback | `data_collector.py:239` | MATCH | |
| `title[:500]` truncate | `data_collector.py:234` | MATCH | |
| `final_price → price` 매핑 | `data_collector.py:248` | MATCH | |
| `root_bs_rank → bsr` 매핑 | `data_collector.py:252` | MATCH | |
| `root_bs_category → bsr_category` 매핑 | `data_collector.py:253` | MATCH | |
| `enumerate(products, 1)` → position | `data_collector.py:233,254` — `i + 1` | MATCH | |
| `sponsored: bool → int` | `data_collector.py:255` | MATCH | |
| `url → product_url` 매핑 | `data_collector.py:264` | MATCH | |
| `features: json.dumps()` | `data_collector.py:265` | MATCH | |
| `categories: json.dumps()` | `data_collector.py:267` | MATCH | |
| `delete_and_insert()` 사용 | `data_collector.py:274-278` | MATCH | |
| `variations_count` 매핑 | `data_collector.py:262` | CHANGED (Compatible) | 디자인: `int, 기본 0`. 구현: `variations` 리스트 길이 또는 `variations_count` fallback. API 호환성 개선 |

### 2.5 ProductDBService (Section 4.3)

#### `get_keyword_cache()`

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword) -> dict | None` | `product_db.py:99` | MATCH | |
| 키워드 정규화 `" ".join(keyword.lower().split())` | `product_db.py:107` | MATCH | |
| `INTERVAL %s DAY` 쿼리 | `product_db.py:112` | MATCH | |
| `settings.AMZ_KEYWORD_CACHE_DAYS` 사용 | `product_db.py:118` | MATCH | |
| 반환 dict 필드 | `product_db.py:103` — `snapshot_id` 추가 포함 | CHANGED (Compatible) | 디자인보다 `snapshot_id` 필드 1개 추가 반환. 호환 |
| 예외 처리 | `product_db.py:119-121` — try/except 추가 | ADDED (Improvement) | 디자인에 없는 방어적 에러 처리 |

#### `get_keyword_products()`

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword, searched_at) -> list[dict]` | `product_db.py:126` | MATCH | |
| 키워드 정규화 | `product_db.py:128` | MATCH | |
| `ORDER BY position ASC` | `product_db.py:132` | MATCH | |
| 예외 처리 | `product_db.py:135-139` — try/except 추가 | ADDED (Improvement) | |

#### `save_keyword_search_log()`

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword, snapshot_id="") -> datetime` | `product_db.py:142-144` | MATCH | |
| 키워드 정규화 | `product_db.py:148` | MATCH | |
| `status='collecting'` INSERT | `product_db.py:151` | MATCH | |
| `searched_at` 반환 | `product_db.py:161` | MATCH | |

#### `update_keyword_search_log()`

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword, searched_at, status, product_count=0)` | `product_db.py:163-164` | MATCH | |
| 키워드 정규화 | `product_db.py:167` | MATCH | |
| UPDATE 쿼리 | `product_db.py:168-171` | MATCH | |

### 2.6 `build_keyword_market_analysis()` (Section 4.6)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword, weighted_products, details) -> dict` | `market_analyzer.py:894-898` | MATCH | |
| `keyword` 필드 | `market_analyzer.py:907` | MATCH | |
| `total_products` 필드 | `market_analyzer.py:908` | MATCH | |
| `price_tier_analysis` | `market_analyzer.py:909` | MATCH | |
| `bsr_analysis` (참고용 유지) | `market_analyzer.py:910` | MATCH | |
| `brand_analysis` | `market_analyzer.py:911` | MATCH | |
| `cooccurrence_analysis` | `market_analyzer.py:912` | MATCH | |
| `rating_ingredients` | `market_analyzer.py:913` | MATCH | |
| `sales_volume` | `market_analyzer.py:914` | MATCH | |
| `sns_pricing` | `market_analyzer.py:915` | MATCH | |
| `promotions` | `market_analyzer.py:916` | MATCH | |
| `customer_voice` | `market_analyzer.py:917` | MATCH | |
| `discount_impact` | `market_analyzer.py:918` | MATCH | |
| `title_keywords` | `market_analyzer.py:919` | MATCH | |
| `unit_economics` | `market_analyzer.py:920` | MATCH | |
| `manufacturer` | `market_analyzer.py:921` | MATCH | |
| `sku_strategy` | `market_analyzer.py:922` | MATCH | |
| `brand_positioning` 제외 | 미포함 | MATCH | |
| `rising_products` 제외 | 미포함 | MATCH | |
| `badges` 제외 | 미포함 | MATCH | |

### 2.7 `build_keyword_excel()` (Section 4.7)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 (8 params) | `excel_builder.py:1126-1135` | MATCH | |
| `_build_ingredient_ranking()` 호출 | `excel_builder.py:1148` | MATCH | |
| `_build_market_insight()` 호출 (조건부) | `excel_builder.py:1149-1150` | MATCH | |
| `_build_consumer_voice(is_keyword=True)` | `excel_builder.py:1154` | MATCH | |
| Badge Analysis 제거 | `excel_builder.py:1155` 주석 확인 | MATCH | |
| `_build_sales_pricing()` | `excel_builder.py:1156` | MATCH | |
| Brand Positioning 제거 | `excel_builder.py:1160` 주석 확인 | MATCH | |
| `_build_marketing_keywords()` | `excel_builder.py:1161` | MATCH | |
| `_build_category_summary()` | `excel_builder.py:1162` | MATCH | |
| Rising Products 제거 | `excel_builder.py:1163` 주석 확인 | MATCH | |
| `_build_product_detail()` | `excel_builder.py:1164` | MATCH | |
| `_build_raw_search()` | `excel_builder.py:1167` | MATCH | |
| `_build_raw_detail()` | `excel_builder.py:1168` | MATCH | |
| 9시트 `desired_order` | `excel_builder.py:1171-1181` | MATCH | 디자인과 동일한 9개 시트, 동일 순서 |
| `BytesIO` 반환 | `excel_builder.py:1187-1190` | MATCH | |

### 2.8 `_build_consumer_voice()` — `is_keyword` 파라미터 (Section 4.7)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `is_keyword: bool = False` 파라미터 추가 | `excel_builder.py:432` | MATCH | |
| `if not is_keyword:` → BSR Correlation 스킵 | `excel_builder.py:482` — `if is_keyword: return` | MATCH | 로직 동등: 디자인은 `if not is_keyword`로 BSR 출력, 구현은 `if is_keyword: return`으로 조기 종료 |

### 2.9 `orchestrator.py` — `run_keyword_analysis()` (Section 4.5)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword, response_url, channel_id)` | `orchestrator.py:669-673` | MATCH | |
| Step 1: 캐시 확인 `get_keyword_cache()` | `orchestrator.py:692` | MATCH | |
| `collecting` status + 10분 timeout | `orchestrator.py:694-702` | MATCH | |
| 캐시 HIT → `get_keyword_products()` | `orchestrator.py:708-718` | MATCH | |
| 캐시 MISS → `save_keyword_search_log()` | `orchestrator.py:724` | MATCH | |
| `trigger_keyword_search()` 호출 | `orchestrator.py:727` | MATCH | |
| `poll_snapshot()` 호출 | `orchestrator.py:728` | MATCH | |
| `process_search_snapshot()` 호출 | `orchestrator.py:735` | MATCH | |
| `update_keyword_search_log('completed')` | `orchestrator.py:736` | MATCH | |
| 0건 결과 → 즉시 응답 + 종료 | `orchestrator.py:730-733, 745-747` | MATCH | |
| Step 2: 성분 보완 Layer 1 (캐시) | `orchestrator.py:750-752` | MATCH | |
| Step 2: 성분 보완 Layer 2 (Gemini) | `orchestrator.py:754-788` | MATCH | |
| `_prepare_for_gemini()` 사용 | `orchestrator.py:761` | MATCH | |
| `save_ingredient_cache()` + `harmonize_common_names()` | `orchestrator.py:773-775` | MATCH | |
| Step 3: `_adapt_search_for_analyzer()` | `orchestrator.py:791` | MATCH | |
| `calculate_weights()` | `orchestrator.py:792-794` | MATCH | |
| V4 확장 필드 주입 | `orchestrator.py:797-809` | MATCH | |
| Step 4: `build_keyword_market_analysis()` | `orchestrator.py:812` | MATCH | |
| Market report 캐시 비활성화 (V1) | `orchestrator.py:814-816` | MATCH | `generate_market_report()` 직접 호출, 캐시 저장 없음 |
| Step 5: `build_keyword_excel()` | `orchestrator.py:819-824` | MATCH | |
| Step 6: `_build_summary_blocks()` | `orchestrator.py:827-834` | MATCH | |
| Step 7: 파일 업로드 | `orchestrator.py:837-841` | MATCH | |
| Bright Data API 실패 → `status='failed'` + 관리자 DM | `orchestrator.py:741-743, 844-852` | MATCH | |
| `finally` 클라이언트 정리 | `orchestrator.py:853-858` | MATCH | |

### 2.10 `_prepare_for_gemini()` (Section 4.4)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `description → ingredients_raw` 매핑 | `orchestrator.py:603` | MATCH | |
| `features` JSON 파싱 | `orchestrator.py:591-598` | CHANGED (Improvement) | 디자인은 단순 전달. 구현은 JSON 문자열 → list 파싱 추가 (DB 조회 시 JSON string으로 저장되어 있으므로 필수) |
| `additional_details: {}` | `orchestrator.py:605` | MATCH | |
| `asin`, `title` 필드 | `orchestrator.py:601-602` | MATCH | |

### 2.11 `_adapt_search_for_analyzer()` (Section 4.5)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 시그니처 `(keyword_products) -> (list[SearchProduct], list[ProductDetail])` | `orchestrator.py:609-611` | MATCH | |
| `SearchProduct` 필드 매핑 | `orchestrator.py:622-634` | MATCH | |
| `ProductDetail` 필드 매핑 | `orchestrator.py:651-664` | MATCH | |
| `features` JSON → dict 변환 | `orchestrator.py:637-645` | MATCH | |
| `bsr_category` = `row.get("bsr")` | `orchestrator.py:647-649, 657` | MATCH | |
| `price` float 변환 | `orchestrator.py:617-619` | CHANGED (Improvement) | 디자인은 암묵적 float. 구현은 명시적 `float()` + None guard. Decimal → float 호환성 처리 |
| `reviews` / `rating` None guard | `orchestrator.py:628-630, 659` | CHANGED (Improvement) | 디자인은 `or 0` 패턴. 구현은 `or 0` + `float()` 명시적 변환 추가 |

### 2.12 router.py — "search" 서브커맨드 (Section 4.8)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `if subcommand == "search":` | `router.py:270` | MATCH | |
| `keyword_parts = parts[1:]` | `router.py:271` | MATCH | |
| 빈 키워드 → 사용법 안내 | `router.py:273-277` | MATCH | |
| `background_tasks.add_task(run_keyword_analysis, ...)` | `router.py:278` | MATCH | |
| 즉시 응답 메시지 | `router.py:279-282` | MATCH | |
| `prod` 서브커맨드 앞 배치 | `router.py:270` (search) vs `285` (prod) | MATCH | |

### 2.13 `/amz help` 업데이트 (Section 4.8)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 키워드 검색 분석 섹션 추가 | `router.py:59-73` | MATCH | |
| 제목: `*키워드 검색 분석*` | `router.py:63` | MATCH | |
| 사용법: `/amz search {키워드}` | `router.py:65` | MATCH | |
| 캐시 설명 | `router.py:66` | MATCH | |
| 예시 3개 | `router.py:68-70` | MATCH | 디자인과 동일 |

### 2.14 Slack 메시지 (Section 4.12)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| 즉시 응답 메시지 | `router.py:281` | MATCH | |
| 캐시 HIT 메시지 | `orchestrator.py:715-718` | MATCH | |
| 캐시 MISS 메시지 | `orchestrator.py:722` | MATCH | |
| 수집 완료 메시지 | `orchestrator.py:739` | MATCH | |
| 성분 매칭 메시지 | `orchestrator.py:756-758` | MATCH | |
| 0건 결과 메시지 | `orchestrator.py:732, 746` | MATCH | |
| 에러 메시지 | `orchestrator.py:846` | MATCH | |
| Block Kit 요약 재활용 | `orchestrator.py:827-834` | MATCH | |

### 2.15 에러 핸들링 (Section 4.13)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| Bright Data API 실패 → `failed` + 관리자 DM | `orchestrator.py:741-743, 848-852` | MATCH | |
| 0건 결과 처리 | `orchestrator.py:730-733, 745-747` | MATCH | |
| Gemini 실패 → graceful degradation | `orchestrator.py:767-772` — 로깅 후 빈 성분으로 계속 | MATCH | |
| Race condition 처리 | `orchestrator.py:694-702` | MATCH | |
| 10분 timeout | `orchestrator.py:697` — `elapsed < 600` | MATCH | |

### 2.16 가중치 계산 호환성 (Section 4.10)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| `calculate_weights()` 변경 없이 재활용 | `orchestrator.py:792-794` | MATCH | |
| V4 확장 필드 주입 (badge, customer_says, initial_price 등) | `orchestrator.py:797-809` | MATCH | |
| `bought_past_month` 주입 | `orchestrator.py:809` | ADDED (Improvement) | 디자인 Step 5에는 명시적 `bought_past_month` 주입 미언급이나, V4 호환에 필수. 올바른 추가 |

### 2.17 Market Report 캐시 (Section 4.11)

| Design Item | Implementation | Status | Notes |
|-------------|---------------|--------|-------|
| V1: 캐시 비활성화 | `orchestrator.py:814-816` | MATCH | `generate_market_report()` 직접 호출, `save_market_report_cache()` 미호출 |

---

## 3. Implementation Improvements (Design X, Implementation O)

| # | Item | Location | Description |
|---|------|----------|-------------|
| 1 | `_prepare_for_gemini()` features JSON 파싱 | `orchestrator.py:591-598` | DB에서 JSON 문자열로 저장된 features를 list로 파싱하는 로직 추가. 실제 DB 데이터 형태에 맞는 필수 처리 |
| 2 | `_adapt_search_for_analyzer()` Decimal→float 변환 | `orchestrator.py:617-619` | MySQL `DECIMAL(10,2)` → Python `float` 명시적 변환. DB 반환 타입 호환성 처리 |
| 3 | `get_keyword_cache()` 방어적 에러 처리 | `product_db.py:119-121` | try/except로 DB 오류 시 None 반환. 서비스 안정성 향상 |
| 4 | `get_keyword_products()` 방어적 에러 처리 | `product_db.py:135-139` | 동일 패턴 적용 |
| 5 | `process_search_snapshot()` variations fallback | `data_collector.py:262` | variations 리스트 길이 또는 variations_count 둘 다 처리. API 응답 변동 대응 |
| 6 | `run_migration()` 함수 | `migrations/v6_keyword_search.py:52-61` | 마이그레이션 실행 유틸리티 추가 |
| 7 | `get_keyword_cache()` snapshot_id 반환 | `product_db.py:109` | SELECT에 snapshot_id 포함. 디버깅 편의성 |
| 8 | `run_keyword_analysis()` bought_past_month 주입 | `orchestrator.py:809` | V4 확장 필드 주입에 bought_past_month 추가. 가중치 계산 정확도 보장 |

---

## 4. Match Rate Summary

### 4.1 Comparison Items Breakdown

| Category | Items | Match | Changed (Compatible) | Added (Improvement) | Missing | Partial |
|----------|:-----:|:-----:|:-------------------:|:-------------------:|:-------:|:-------:|
| Config | 2 | 2 | 0 | 0 | 0 | 0 |
| DB Schema | 2 | 2 | 0 | 1 | 0 | 0 |
| BrightDataService | 9 | 9 | 0 | 0 | 0 | 0 |
| DataCollector | 14 | 13 | 1 | 0 | 0 | 0 |
| ProductDBService | 14 | 12 | 1 | 2 | 0 | 0 |
| MarketAnalyzer | 19 | 19 | 0 | 0 | 0 | 0 |
| ExcelBuilder | 17 | 17 | 0 | 0 | 0 | 0 |
| ConsumerVoice | 2 | 2 | 0 | 0 | 0 | 0 |
| Orchestrator | 28 | 26 | 2 | 1 | 0 | 0 |
| Router | 7 | 7 | 0 | 0 | 0 | 0 |
| Help | 4 | 4 | 0 | 0 | 0 | 0 |
| Slack Messages | 8 | 8 | 0 | 0 | 0 | 0 |
| Error Handling | 6 | 6 | 0 | 0 | 0 | 0 |
| **Total** | **132** | **127** | **4** | **4** | **0** | **0** |

### 4.2 Overall Score

```
+---------------------------------------------+
|  Overall Match Rate: 99%                     |
+---------------------------------------------+
|  MATCH:             127 items (96.2%)        |
|  CHANGED (compat):    4 items ( 3.0%)        |
|  ADDED (improve):     4 items ( 0.8%)  [*]   |
|  MISSING:             0 items ( 0.0%)        |
|  PARTIAL:             0 items ( 0.0%)        |
+---------------------------------------------+
|  Critical gaps: 0                            |
|  Major gaps:    0                            |
|  Minor gaps:    0                            |
+---------------------------------------------+

[*] Added items are implementation improvements not counted as gaps.
    Match rate = (MATCH + CHANGED) / Total = 131/132 = 99.2%
```

---

## 5. Changed Items Detail

| # | Item | Design | Implementation | Impact |
|---|------|--------|----------------|--------|
| 1 | `variations_count` 매핑 | `int, 기본 0` | `variations` 리스트 길이 fallback 포함 | None (호환) |
| 2 | `get_keyword_cache()` 반환 필드 | 4 fields | 5 fields (+snapshot_id) | None (호환) |
| 3 | `_prepare_for_gemini()` features | 직접 전달 | JSON string 파싱 후 전달 | None (필수 수정) |
| 4 | `_adapt_search_for_analyzer()` 타입 변환 | 암묵적 float | 명시적 `float()` 변환 | None (안정성 향상) |

모든 Changed 항목은 하위 호환이며, 디자인 의도를 훼손하지 않는 구현 수준의 개선이다.

---

## 6. File Change Verification

| Design (Section 5.2) | Implementation | Status |
|----------------------|----------------|--------|
| `app/config.py` — `AMZ_KEYWORD_CACHE_DAYS` 추가 | Line 80 | MATCH |
| `bright_data.py` — `trigger_keyword_search()` 추가 | Lines 105-139 | MATCH |
| `data_collector.py` — `process_search_snapshot()` 추가 | Lines 213-283 | MATCH |
| `product_db.py` — 4개 신규 메서드 | Lines 99-178 | MATCH |
| `market_analyzer.py` — `build_keyword_market_analysis()` 추가 | Lines 894-923 | MATCH |
| `excel_builder.py` — `build_keyword_excel()` + `_build_consumer_voice` 수정 | Lines 432, 1126-1190 | MATCH |
| `orchestrator.py` — 3개 신규 함수 | Lines 585-858 | MATCH |
| `router.py` — search 서브커맨드 + help 업데이트 | Lines 59-73, 270-282 | MATCH |
| 신규 파일 없음 (디자인 Section 5.1) | 확인: 기존 파일에만 메서드 추가 | MATCH |
| DB 마이그레이션 `v6_keyword_search.py` (Section 5.3) | `migrations/v6_keyword_search.py` | MATCH |

---

## 7. Recommended Actions

### 7.1 Design Document Update (Optional)

1. **`_prepare_for_gemini()` features JSON 파싱**: 디자인에 "features가 DB에서 JSON string으로 조회되므로 파싱 필요" 설명 추가 권장
2. **`get_keyword_cache()` snapshot_id 반환**: 반환 dict에 `snapshot_id` 포함 명시
3. **`bought_past_month` V4 확장 필드 주입**: Step 5 설명에 `bought_past_month` 주입 명시 추가

### 7.2 No Immediate Code Changes Required

구현이 디자인을 충실히 따르며, 모든 차이점은 하위 호환적 개선이므로 코드 변경 불필요.

---

## 8. Conclusion

Match Rate **99%** -- 디자인 문서와 구현이 거의 완벽하게 일치한다. 132개 비교 항목 중 127개 완전 일치, 4개 하위 호환 변경, 0개 누락. 변경 항목은 모두 DB 타입 호환성이나 방어적 에러 처리 등 실용적 개선이며, 디자인 의도를 훼손하지 않는다. 8개의 구현 수준 개선사항(JSON 파싱, Decimal 변환, try/except 등)이 추가되어 코드 안정성이 향상되었다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-09 | 초기 분석 리포트 작성 | Gap Detector Agent |
