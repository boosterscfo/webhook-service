# Keyword Search Analysis Plan

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 `/amz`는 BSR 카테고리 기반 분석만 가능. "vitamin c serum for face"처럼 세그먼트 키워드로 검색된 제품군의 인사이트를 추출할 수 없음 |
| **Solution** | 기존 Bright Data BSR dataset의 `discover_by=keyword` 모드 활용 → 별도 dataset 구매 불필요. 80+ 필드 반환. 성분은 기존 `amz_ingredient_cache` ASIN 매칭 + Gemini 추출 병행 |
| **Function/UX Effect** | `/amz search {keyword}` 입력 → 1-3분 후 키워드 전용 9시트 Excel 리포트 수신. 동일 키워드 7일 캐시. 기존 ASIN 성분 캐시 자동 활용 |
| **Core Value** | 카테고리에 국한되지 않는 자유로운 시장 탐색. 추가 dataset 구매 불필요. 기존 분석 자산 + 성분 캐시 100% 재활용. BSR 카테고리 의존 분석 제거로 오해 없는 리포트 |

---

## 1. User Intent Discovery

### 1.1 Core Problem

BSR 카테고리 분석은 미리 등록한 카테고리 내 Top 100만 분석 가능. "vitamin c serum for face", "organic hair oil for curly hair" 등 세그먼트 키워드로 Amazon 검색 결과를 분석하고 싶은 니즈가 있음.

### 1.2 Target Users

- 제품 기획자: 특정 세그먼트의 경쟁 환경, 성분 트렌드 파악
- 마케터: 키워드별 가격대, 리뷰, 배지 현황 분석

### 1.3 Success Criteria

- `/amz search {keyword}`로 키워드 검색 → 키워드 전용 9시트 Excel 리포트 생성
- 동일 키워드 7일 내 재검색 시 DB 캐시 활용 (API 호출 없음)
- 기존 카테고리 분석(`/amz {keyword}`) 기능에 영향 없음

---

## 2. Alternatives Explored

### Approach A: 기존 BSR Dataset의 `discover_by=keyword` 모드 — Selected (API 테스트 검증 완료)

- **API**: `POST /datasets/v3/trigger?dataset_id={기존ID}&type=discover_new&discover_by=keyword`
- **Input**: `[{"keyword": "vitamin c serum"}]`
- **Output**: 80+ 필드 (title, brand, price, rating, reviews_count, root_bs_rank, bought_past_month, badge, coupon, customer_says, plus_content, number_of_sellers, features, description 등)
- **Pros**: 별도 dataset 구매 불필요, 기존 크레딧 사용, 데이터 필드가 카테고리 수집보다 풍부
- **Cons**: `ingredients` 전용 필드 없음 (하단 4.5 성분 보완 전략으로 해결)
- **검증**: `sd_mmj116xb1dlmlhbrjd` snapshot으로 10건 수신 확인 (2026-03-09)

### Approach B: Amazon Products Search 별도 Dataset (Rejected)

- $0.0025/건, 28 필드
- 별도 구매 필요 ($250 min order), 기존 dataset보다 필드 적음
- 기존 dataset에서 동일 기능 가능하므로 불필요

### Approach C: Browse AI / PA-API (Rejected)

- Browse AI: 26% 실패율, V4에서 대체 완료
- PA-API: 어필리에이트 계정 필요, 성분 정보 미제공

---

## 3. YAGNI Review

### 3.1 Included (V1)

- [x] `/amz search {keyword}` 실시간 검색 + 분석
- [x] 기존 BSR dataset `discover_by=keyword` 모드 활용
- [x] 검색 결과 DB 적재 (amz_keyword_products 테이블)
- [x] 7일 캐시 전략 (동일 키워드 재검색 시 DB 조회)
- [x] 성분 보완: `amz_ingredient_cache` ASIN 매칭 + 미캐시 ASIN Gemini 추출
- [x] 키워드 전용 리포트 (9시트 Excel — BSR 카테고리 의존 3시트 제거)
- [x] Slack 응답 + Excel 파일 첨부

### 3.2 Deferred (V2+)

- [ ] Sponsored vs Organic 비율 분석 시트
- [ ] 카테고리 vs 키워드 검색 비교 시트
- [ ] 키워드 등록 + 주기적 배치 수집
- [ ] 검색 트렌드 시계열 분석
- [ ] `pages_to_search` 파라미터 노출 (현재 1페이지 고정)

---

## 4. Architecture

### 4.1 Data Flow

```
/amz search {keyword}
    ↓
SlackRouter (서브커맨드 "search" 추가)
    ↓
캐시 확인: amz_keyword_search_log에서 7일 이내 동일 키워드 조회
    ├─ HIT → DB에서 제품 데이터 로드
    ├─ COLLECTING → 이미 수집 진행 중 → 대기 후 DB 로드
    └─ MISS ↓
        amz_keyword_search_log INSERT (status='collecting')
            ↓
        Bright Data (기존 BSR dataset, discover_by=keyword)
            → trigger_keyword_search(keyword, limit=100)
            → poll_snapshot() (기존 함수 재활용)
            ↓
        검색 결과 DB 적재
            → amz_keyword_products 테이블
            → amz_keyword_search_log UPDATE (status='completed')
    ↓
성분 보완 전략 (4.5 참조)
    → amz_ingredient_cache에서 ASIN 매칭 (기존 캐시 활용)
    → 미캐시 ASIN → Gemini 성분 추출 → 캐시 저장
    ↓
키워드 전용 분석 파이프라인
    → _adapt_search_for_analyzer() (검색 결과 → WeightedProduct 변환)
    → _resolve_brand() 적용 (기존 브랜드 보정 로직 재활용)
    → build_market_analysis() (BSR 의존 분석 스킵)
    → build_keyword_excel() → 9시트 Excel (4.10 참조)
    ↓
Slack 응답 + Excel 파일
```

### 4.2 Key Components

| Component | Role | Status |
|-----------|------|--------|
| `BrightDataService.trigger_keyword_search()` | 키워드 검색 트리거 (기존 dataset, discover_by=keyword) | 신규 메서드 |
| `DataCollector.process_search_snapshot()` | 검색 결과 파싱 + DB 적재 (`customer_says`/`customers_say` 양쪽 필드 fallback) | 신규 메서드 |
| `ProductDBService.get_keyword_cache()` | 7일 캐시 조회 | 신규 메서드 |
| `ProductDBService.save_keyword_products()` | 검색 결과 저장 | 신규 메서드 |
| `AmzCacheService.get_ingredient_cache()` | 기존 ASIN 성분 캐시 조회 | **재활용** |
| `GeminiService.extract_ingredients()` | 미캐시 ASIN 성분 추출 | **재활용** |
| `_resolve_brand()` | 브랜드명 보정 (기존 `_BRAND_MAPPINGS` 적용) | **재활용** |
| `router.py` | `/amz search` 서브커맨드 | 수정 |
| `orchestrator.py` | `run_keyword_analysis()` | 신규 함수 |
| 기존 분석 파이프라인 | calculate_weights, market_analyzer, excel_builder | **재활용** |

### 4.3 DB Schema (신규 테이블)

#### amz_keyword_search_log

| Column | Type | Description |
|--------|------|-------------|
| id | INT AUTO_INCREMENT | PK |
| keyword | VARCHAR(255) | 검색 키워드 (정규화: lower, strip, 다중공백 제거) |
| product_count | INT | 수집 제품 수 |
| snapshot_id | VARCHAR(100) | Bright Data snapshot ID |
| status | ENUM('collecting', 'completed', 'failed') | 수집 상태 (race condition 방지) |
| searched_at | DATETIME | 검색 시각 |

INDEX: `idx_keyword_searched (keyword, searched_at DESC)`

#### amz_keyword_products

| Column | Type | Description |
|--------|------|-------------|
| id | INT AUTO_INCREMENT | PK |
| keyword | VARCHAR(255) | 검색 키워드 |
| asin | VARCHAR(20) | Amazon ASIN |
| title | VARCHAR(500) | 제품명 |
| brand | VARCHAR(200) | 브랜드 (보정 후) |
| manufacturer | VARCHAR(200) | 제조사 |
| price | DECIMAL(10,2) | final_price |
| initial_price | DECIMAL(10,2) | initial_price (할인 전) |
| currency | VARCHAR(10) | 통화 (기본: USD) |
| rating | DECIMAL(3,2) | 평점 |
| reviews_count | INT | 리뷰 수 |
| bsr | INT | root_bs_rank |
| bsr_category | VARCHAR(200) | root_bs_category |
| position | INT | 검색 결과 순위 (API 응답 배열 인덱스 기반) |
| sponsored | TINYINT(1) | 광고 여부 |
| badge | VARCHAR(100) | Amazon's Choice / Best Seller 등 |
| bought_past_month | INT | 월 구매 수 |
| coupon | VARCHAR(200) | 쿠폰 정보 |
| customer_says | TEXT | AI 리뷰 요약 (API의 `customer_says` 또는 `customers_say` fallback) |
| plus_content | TINYINT(1) | A+ Content 여부 |
| number_of_sellers | INT | 셀러 수 |
| variations_count | INT | 변형 수 |
| image_url | VARCHAR(500) | 이미지 URL |
| product_url | VARCHAR(500) | 제품 URL |
| features | TEXT | 제품 특징 (JSON array) |
| description | TEXT | 제품 설명 |
| categories | TEXT | 카테고리 트리 (JSON array) |
| searched_at | DATETIME | 검색 시각 (캐시 키) |

INDEX: `idx_kp_keyword_searched (keyword, searched_at)`

> **Note**: `amz_keyword_products.asin`은 기존 `amz_products.asin`과 동일 ASIN이 중복 존재 가능.
> 별도 테이블로 독립 관리하되, 성분 캐시(`amz_ingredient_cache`)는 ASIN 기반으로 공유.

### 4.4 캐시 전략

- **캐시 키 정규화**: `" ".join(keyword.lower().split())` (다중 공백, 특수 공백 문자 제거)
- **TTL**: 7일 (config: `AMZ_KEYWORD_CACHE_DAYS`)
  - 기존 카테고리 캐시(30일)보다 짧은 이유: 검색 결과 순위는 BSR 랭킹보다 변동성이 높음 (광고, 시즌, A9 알고리즘 변화)
- **조회**: `SELECT * FROM amz_keyword_search_log WHERE keyword = %s AND status = 'completed' AND searched_at >= NOW() - INTERVAL 7 DAY ORDER BY searched_at DESC LIMIT 1`
- **HIT**: `amz_keyword_products`에서 해당 keyword + searched_at 기준 조회 → 즉시 분석
- **MISS**: Bright Data 수집 → DB 적재 → 분석
- **Race condition 방지**: `status='collecting'` 상태가 이미 있으면 동일 키워드 중복 API 호출 방지. 10분 이상 `collecting` 상태면 timeout으로 간주하고 재수집 허용.

### 4.5 성분 보완 전략 (Ingredient Enrichment)

키워드 검색 결과에는 `ingredients` 전용 필드가 없으나, 두 가지 방법으로 보완:

#### Layer 1: 기존 성분 캐시 매칭 (비용 $0)

```
검색 결과 ASIN 목록
    ↓
amz_ingredient_cache에서 ASIN 매칭
    → HIT: 이미 추출된 성분 데이터 사용
    → MISS: Layer 2로
```

카테고리 수집에서 이미 분석한 ASIN이 검색 결과에도 등장할 가능성 높음 (동일 시장 세그먼트).

#### Layer 2: Gemini 성분 추출 (미캐시 ASIN만)

```
미캐시 ASIN의 description + features 텍스트
    ↓
_prepare_for_gemini() 어댑터
    → description → ingredients_raw 필드에 매핑
    → features → features 필드 (기존 형식 유지)
    → additional_details → {} (비어있음)
    ↓
GeminiService.extract_ingredients() (기존 함수 재활용)
    → 추출된 성분 → amz_ingredient_cache에 저장
```

검색 결과 데이터에 `description`, `features` 필드가 포함되어 있어 Gemini가 성분 추출 가능.
기존 Gemini 프롬프트는 `ingredients_raw`가 비어있어도 title/features에서 추출 가능하도록 설계되어 있음.

#### Gemini 어댑터 상세 매핑

```python
def _prepare_for_gemini(keyword_product: dict) -> dict:
    """키워드 검색 결과를 Gemini 성분 추출 입력으로 변환."""
    return {
        "asin": keyword_product["asin"],
        "title": keyword_product["title"],
        "ingredients_raw": keyword_product.get("description", ""),
        "features": keyword_product.get("features", []),
        "additional_details": {},
    }
```

#### 성분 보완 흐름 요약

| ASIN 상태 | 데이터 소스 | Gemini 호출 | 비용 |
|-----------|-----------|------------|------|
| 캐시 HIT | amz_ingredient_cache | 없음 | $0 |
| 캐시 MISS | description + features → Gemini | 있음 | Gemini API 비용 |
| Gemini 추출 실패 | 빈 성분으로 처리 (graceful) | 시도 후 실패 | $0 (실패 시 빈 데이터) |

### 4.6 Config 변경

```python
# app/config.py — 추가
AMZ_KEYWORD_CACHE_DAYS: int = 7
# BRIGHT_DATA_SEARCH_DATASET_ID 불필요 (기존 BRIGHT_DATA_DATASET_ID 재활용)
```

### 4.7 API 호출 명세 (테스트 검증 완료)

```python
# 트리거 — 기존 trigger_collection()과 동일 base URL (/trigger), 파라미터만 다름
resp = httpx.post(
    f"{self.base_url}/trigger",  # 기존과 동일: https://api.brightdata.com/datasets/v3/trigger
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    params={
        "dataset_id": settings.BRIGHT_DATA_DATASET_ID,  # 기존 BSR dataset
        "type": "discover_new",
        "discover_by": "keyword",
        "limit_per_input": 100,
    },
    json=[{"keyword": keyword}],
)
# 응답: {"snapshot_id": "sd_xxx", "status": "closing"}

# 폴링: 기존 poll_snapshot() 재활용
```

### 4.8 가중치 계산 호환성

키워드 검색 결과에 `bought_past_month` 필드가 존재하므로, `calculate_weights()`에서 V4 가중치가 자동 적용됨:

| 가중치 요소 | V4 비율 | 키워드 검색 적용 |
|------------|--------|----------------|
| bought_past_month | 30% | ✅ (필드 존재 확인됨) |
| BSR | 25% | ✅ root_bs_rank |
| reviews_count | 20% | ✅ |
| rating | 15% | ✅ |
| number_of_sellers | 10% | ✅ |

### 4.9 Market Report 캐시 분리

기존 `AmzCacheService.get_market_report_cache()`는 `_get_data_freshness()`에서 `amz_categories` 테이블을 조인.
키워드 검색에서는 이 조인이 불가능하므로, 키워드 검색용 market report는 **캐시를 사용하지 않거나** `amz_keyword_search_log`의 `searched_at` 기준으로 freshness를 판단하는 별도 로직 필요.

→ V1에서는 키워드 검색 market report 캐시를 **비활성화** (매 검색마다 Gemini 리포트 생성). 7일 캐시로 API 호출 자체가 제한되므로 비용 영향 최소.

### 4.10 키워드 전용 리포트 구성 (카테고리 리포트와 분리)

키워드 검색 결과는 **여러 카테고리에 걸친 제품**이 섞여 반환됨. 따라서 동일 카테고리 BSR 비교를 전제로 한 시트는 오해를 줄 수 있어 제거.

#### 카테고리 리포트 (12시트) vs 키워드 리포트 (9시트)

| # | 카테고리 리포트 시트 | 키워드 리포트 | 사유 |
|---|---------------------|:----------:|------|
| 1 | Market Insight | ✅ 유지 | 범용 AI 분석, 카테고리 무관 |
| 2 | Consumer Voice | ✅ 유지 (변형) | BSR correlation 섹션 제거, 키워드 빈도 분석만 |
| 3 | Badge Analysis | ❌ **제거** | Mann-Whitney U 통계 검정이 크로스 카테고리 BSR 비교 시 무의미 |
| 4 | Sales & Pricing | ✅ 유지 | 거래/가격 기반 분석, BSR 의존도 낮음 |
| 5 | Brand Positioning | ❌ **제거** | 다른 카테고리 브랜드를 BSR로 비교하면 오해 유발 |
| 6 | Marketing Keywords | ✅ 유지 | 타이틀 키워드 분석, 카테고리 무관 |
| 7 | Ingredient Ranking | ✅ 유지 | BSR은 가중치 25%일 뿐, 성분 중심 분석 |
| 8 | Category Summary | ✅ 유지 | 성분 카테고리화, BSR 무관 |
| 9 | Rising Products | ❌ **제거** | "BSR < 10,000이면 성장 제품" 로직이 크로스 카테고리에서 무의미 |
| 10 | Product Detail | ✅ 유지 | 제품 정보 나열, 범용 |
| 11 | Raw - Search Results | ✅ 유지 | 검색 순위(position) 포함, 키워드 검색 핵심 데이터 |
| 12 | Raw - Product Detail | ✅ 유지 | 원본 데이터 |

#### 키워드 리포트 시트 순서 (9시트)

```
1. Market Insight          (AI 리포트)
2. Consumer Voice          (BSR correlation 섹션 제외)
3. Sales & Pricing         (그대로)
4. Marketing Keywords      (그대로)
5. Ingredient Ranking      (그대로)
6. Category Summary        (그대로)
7. Product Detail          (그대로)
8. Raw - Search Results    (검색 순위 강조)
9. Raw - Product Detail    (그대로)
```

#### 구현 전략

`build_keyword_excel()` 신규 함수 생성 (기존 `build_excel()` 복사 후 축소):
- `_build_badge_analysis()`, `_build_brand_positioning_sheet()`, `_build_rising()` 호출 제거
- `_build_consumer_voice()`에서 BSR correlation 섹션 조건부 스킵 (`is_keyword=True`)
- `build_market_analysis()`에서도 `analyze_badges()`, `analyze_brand_positioning()`, `detect_rising_products()` 스킵

> **V2 고려**: Search Position Analysis 시트 추가 (검색 순위별 가격/리뷰 상관관계)

---

## 5. Slack UX

### 5.1 Command

```
/amz search vitamin c serum for face
```

### 5.2 Response Flow

1. 즉시 응답: "🔍 키워드 '{keyword}' 검색 중..."
2. 캐시 HIT 시: "♻️ 캐시 사용 (N일 전 수집, M개 제품). 분석 시작..."
3. 캐시 MISS 시: "📡 Bright Data 수집 시작... (1-3분 소요)"
4. 성분 매칭 결과: "🧪 성분 캐시 {X}건 매칭 / {Y}건 Gemini 추출 중..."
5. 분석 완료: 기존과 동일한 Block Kit 응답 + Excel 파일

### 5.3 Help 업데이트

`/amz help`에 search 관련 섹션 추가:
```
*🔍 키워드 검색 분석*

`/amz search {키워드}`
Amazon 검색 결과를 분석합니다. 카테고리 등록 없이 자유롭게 검색 가능.
7일 내 동일 키워드 재검색 시 캐시를 사용합니다.

_예시:_
• `/amz search vitamin c serum for face`
• `/amz search organic hair oil`
• `/amz search korean skincare set`
```

---

## 6. Implementation Order

```
Phase 1: 인프라
├─ 1. [ ] Config 추가 (AMZ_KEYWORD_CACHE_DAYS)
├─ 2. [ ] DB 마이그레이션 (amz_keyword_search_log + status 컬럼, amz_keyword_products + 추가 필드)
└─ 3. [ ] BrightDataService.trigger_keyword_search() 메서드 추가
          (기존 /trigger endpoint + discover_by=keyword)

Phase 2: 데이터 레이어
├─ 4. [ ] ProductDBService: save_keyword_products(), get_keyword_cache() 메서드
├─ 5. [ ] DataCollector: process_search_snapshot() 메서드
│         (customer_says/customers_say fallback, _resolve_brand() 적용)
└─ 6. [ ] 검색 결과 필드 매핑 (80+ 필드 → DB 컬럼, position = 배열 인덱스)

Phase 2.5: E2E 검증 (10건)
└─ 7. [ ] trigger → poll → DB 적재 통합 테스트 (limit=10)

Phase 3: 성분 보완
├─ 8. [ ] 기존 amz_ingredient_cache ASIN 매칭 로직
└─ 9. [ ] _prepare_for_gemini() 어댑터 (description → ingredients_raw 매핑)

Phase 4: 비즈니스 로직
├─ 10. [ ] orchestrator.py: run_keyword_analysis() 함수
├─ 11. [ ] _adapt_search_for_analyzer() (검색 결과 → WeightedProduct 변환)
├─ 12. [ ] 키워드 검색용 market report 캐시 분리 (V1: 캐시 비활성화)
└─ 13. [ ] build_keyword_excel() (9시트 — Badge/Brand/Rising 제거)
          + _build_consumer_voice() BSR correlation 조건부 스킵

Phase 5: Slack 연동
├─ 14. [ ] router.py: "search" 서브커맨드 핸들링
├─ 15. [ ] /amz help 업데이트
└─ 16. [ ] 에러 핸들링 (관리자 알림, 0건 결과, rate limit)
```

---

## 7. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 검색 결과에 `ingredients` 필드 없음 | 성분 분석 불가능 | Layer 1: ASIN 캐시 매칭, Layer 2: description+features → Gemini 추출 |
| 카테고리와 겹치지 않는 새 ASIN의 성분 추출 정확도 | description이 성분 정보를 포함하지 않을 수 있음 | Gemini가 features/description에서 추출 실패 시 빈 성분으로 처리 (graceful) |
| `discover_by=keyword` API 변경/제거 가능성 | 기능 불능 | Bright Data 공식 문서 모니터링, fallback으로 별도 dataset 구매 |
| 100건 제한으로 커버리지 부족 | 상위 100건만 분석 | V2에서 `pages_to_search` 파라미터 노출 |
| Bright Data 응답 지연 (1-3분) | 사용자 대기 | 7일 캐시로 반복 호출 최소화 |
| 동시 검색 요청 (race condition) | Bright Data 이중 호출, 크레딧 낭비 | `status` 컬럼으로 수집 진행 상태 관리, 10분 timeout |
| `customer_says` / `customers_say` 필드명 불일치 | 데이터 누락 | 파싱 시 양쪽 필드명 fallback 체크 |
| 검색 결과 0건 | 빈 리포트 생성 시도 | 0건 시 "검색 결과 없음" 즉시 응답, 분석 스킵 |
| Gemini rate limit (429) | 성분 추출 실패 | 성분 없이 리포트 생성 (graceful degradation) |
| Market report 캐시 freshness 조인 실패 | 키워드 검색에 `amz_categories` 없음 | V1에서 키워드 market report 캐시 비활성화 |

---

## 8. Brainstorming Log

| Phase | Decision | Rationale |
|-------|----------|-----------|
| Intent | 세그먼트 키워드 검색 분석 | 카테고리에 없는 니치 시장 탐색 니즈 |
| Approach | 기존 BSR dataset `discover_by=keyword` | API 테스트 검증 완료. 별도 dataset 불필요. 80+ 필드 |
| Ingredients | 2-layer 보완 (ASIN 캐시 + Gemini) | 기존 ASIN 캐시 재활용으로 비용 절감. 미캐시 ASIN만 Gemini 호출 |
| Cache | 7일 DB 캐시 (vs 카테고리 30일) | 검색 순위 변동성 높음. 크레딧 절감 vs 데이터 신선도 균형 |
| Scope | 실시간 검색 + 기존 분석 재활용 | YAGNI: 배치 수집, Sponsored 분석은 V2 |
| UX | `/amz search {keyword}` 별도 커맨드 | 기존 `/amz {keyword}` (카테고리) 와 충돌 방지 |
| Config | BRIGHT_DATA_SEARCH_DATASET_ID 삭제 | 기존 dataset_id 재활용 확인됨 |
| API endpoint | `/trigger` 통일 (not `/scrape`) | 기존 `BrightDataService`와 일관성 유지 |
| DB 스키마 | 추가 필드 (manufacturer, variations_count 등) | V4 확장 필드 주입 코드 호환성 확보 |
| Race condition | `status` 컬럼 도입 | 동시 검색 시 이중 API 호출 방지 |
| Market report | V1 캐시 비활성화 | `amz_categories` 조인 불가, 7일 검색 캐시로 호출 자체 제한 |
| Report 구성 | 9시트 전용 리포트 (12시트에서 3시트 제거) | 크로스 카테고리 BSR 비교는 오해 유발. Badge/Brand/Rising 시트 제거 |

---

## 9. CTO Review Notes (v3.0)

### 평가 점수: 8.2/10 → 수정 후 반영 완료

#### 반영된 수정사항

| ID | 항목 | 상태 |
|----|------|------|
| C1 | API endpoint `/scrape` → `/trigger` 통일 | ✅ 4.7 수정 |
| C2 | Gemini 어댑터 `description → ingredients_raw` 매핑 구체화 | ✅ 4.5 `_prepare_for_gemini()` 추가 |
| C3 | `customers_say` / `customer_says` fallback 명시 | ✅ 4.2, 4.3, 7 반영 |
| M1 | DB 스키마에 `manufacturer`, `variations_count`, `currency`, `categories` 추가 | ✅ 4.3 보강 |
| M2 | 캐시 키 정규화 `" ".join(keyword.lower().split())` | ✅ 4.4 수정 |
| M3 | `position` = API 응답 배열 인덱스 명시 | ✅ 4.3, 6 반영 |
| M4 | 7일 vs 30일 TTL 근거 명시 | ✅ 4.4 설명 추가 |
| M5 | `amz_products`와의 관계 문서화 | ✅ 4.3 Note 추가 |
| m1 | Gemini 입력 필드 매핑 구체화 | ✅ 4.5 코드 예시 추가 |
| m3 | Race condition 방지 (`status` 컬럼) | ✅ 4.3, 4.4 반영 |
| m4 | 에러 핸들링 시나리오 추가 | ✅ 7 Risk 테이블 확장 |
| 누락1 | `_resolve_brand()` 적용 명시 | ✅ 4.1, 4.2 반영 |
| 누락2 | `bought_past_month` → V4 가중치 적용 확인 | ✅ 4.8 신규 섹션 |
| 누락3 | Market report 캐시 freshness 분리 | ✅ 4.9 신규 섹션 |
| 누락4 | Phase 2.5 E2E 검증 단계 추가 | ✅ 6 Implementation Order |
| v3.1 | 키워드 전용 9시트 리포트 (BSR 의존 3시트 제거) | ✅ 4.10 신규 섹션, 6 Phase 4 항목 추가 |

---

## Appendix: API 테스트 결과 (2026-03-09)

### 테스트 조건
- Dataset: `gd_l7q7dkf244hwjntr0` (기존 BSR dataset)
- Params: `type=discover_new`, `discover_by=keyword`, `limit_per_input=10`
- Input: `[{"keyword": "vitamin c serum"}]`

### 응답
- Snapshot ID: `sd_mmj116xb1dlmlhbrjd`
- Status 202 → 15초 후 Status 200
- 10건 반환, 80+ 필드

### 주요 필드 확인

| 필드 | 존재 | 예시 값 |
|------|:----:|---------|
| title | ✅ | "The Ordinary Ascorbyl Glucoside Solution 12%..." |
| brand | ✅ | "DECIEM" |
| final_price | ✅ | 14.0 |
| initial_price | ✅ | 14.0 |
| rating | ✅ | 4.6 |
| reviews_count | ✅ | 1677 |
| root_bs_rank | ✅ | 1012 |
| root_bs_category | ✅ | "Beauty & Personal Care" |
| bought_past_month | ✅ | (존재) |
| badge | ✅ | (존재) |
| coupon | ✅ | (존재) |
| customer_says / customers_say | ✅ | (존재, 필드명 불일치 주의) |
| plus_content | ✅ | true |
| number_of_sellers | ✅ | 1 |
| sponsored | ✅ | (존재) |
| features | ✅ | ["BRIGHTENING VITAMIN C SERUM...", ...] |
| description | ✅ | "About this item BRIGHTENING VITAMIN C..." |
| manufacturer | ✅ | (존재) |
| variations_count | ✅ | (존재) |
| categories | ✅ | (JSON array) |
| ingredients | ❌ | 없음 — Layer 1/2 보완 전략 적용 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-09 | Initial plan (Plan Plus) | CTO Lead |
| 2.0 | 2026-03-09 | API 테스트 결과 반영: 기존 dataset 재활용, 성분 보완 전략 추가, Config 간소화 | CTO Lead |
| 3.0 | 2026-03-09 | CTO Review 반영: API endpoint 통일, DB 스키마 보강, race condition 방지, Gemini 어댑터 구체화, 에러 핸들링 확장, 가중치/캐시 호환성 명시 | CTO Team |
| 3.1 | 2026-03-09 | 키워드 전용 9시트 리포트 분리: Badge/Brand/Rising 3시트 제거, Consumer Voice BSR 섹션 조건부 스킵, build_keyword_excel() 신규 | CTO Team |
