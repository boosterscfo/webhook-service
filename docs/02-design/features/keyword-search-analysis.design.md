# Design: Keyword Search Analysis — Amazon 키워드 검색 기반 시장 분석

## 1. Overview

Amazon BSR 카테고리 분석과 별개로, 사용자가 자유 키워드로 Amazon 검색 결과를 분석할 수 있는 기능.
기존 Bright Data BSR dataset의 `discover_by=keyword` 모드를 활용하여 별도 dataset 구매 없이 구현.
9시트 전용 Excel 리포트로 크로스 카테고리 BSR 비교 오류 방지.

**Plan 참조**: `docs/01-plan/features/keyword-search-analysis.plan.md`

## 2. 아키텍처

### 2.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────┐
│                     키워드 검색 분석                           │
│                                                             │
│  [Slack: /amz search {keyword}]                             │
│       ↓                                                     │
│  router.py  (서브커맨드 "search" 분기)                       │
│       ↓                                                     │
│  캐시 확인: amz_keyword_search_log (7일 TTL)                 │
│       ├─ HIT  → DB에서 제품 데이터 로드                       │
│       ├─ COLLECTING → "수집 중" 응답 (중복 API 호출 방지)      │
│       └─ MISS ↓                                             │
│           amz_keyword_search_log INSERT (status='collecting') │
│               ↓                                             │
│           BrightDataService.trigger_keyword_search()          │
│               → discover_by=keyword, limit_per_input=100     │
│               ↓ (polling: 10s 간격, 기존 poll_snapshot 재활용)│
│           DataCollector.process_search_snapshot()             │
│               → amz_keyword_products INSERT                  │
│               → amz_keyword_search_log UPDATE (completed)    │
│       ↓                                                     │
│  성분 보완 (2-Layer)                                         │
│       → Layer 1: amz_ingredient_cache ASIN 매칭 (비용 $0)    │
│       → Layer 2: _prepare_for_gemini() → Gemini 추출         │
│       ↓                                                     │
│  분석 파이프라인                                              │
│       → _adapt_search_for_analyzer() (WeightedProduct 변환)  │
│       → _resolve_brand() 적용                                │
│       → build_market_analysis() (BSR 의존 분석 스킵)          │
│       → build_keyword_excel() (9시트)                        │
│       ↓                                                     │
│  Slack 응답 + Excel 파일                                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

```
Bright Data API Response (discover_by=keyword, JSON Array)
  → DataCollector.process_search_snapshot()
    → field mapping (80+ API 필드 → DB 컬럼)
    → _resolve_brand(raw_brand, title) 적용
    → customer_says / customers_say fallback
    → amz_keyword_products INSERT (keyword + searched_at 기준)
    → amz_keyword_search_log UPDATE (status='completed')
```

## 3. DB 설계

### 3.1 amz_keyword_search_log (검색 이력/캐시 관리)

```sql
CREATE TABLE amz_keyword_search_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,        -- 정규화: " ".join(keyword.lower().split())
    product_count INT DEFAULT 0,          -- 수집된 제품 수
    snapshot_id VARCHAR(100) DEFAULT '',  -- Bright Data snapshot ID
    status ENUM('collecting', 'completed', 'failed') NOT NULL DEFAULT 'collecting',
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_keyword_searched (keyword, searched_at DESC)
);
```

**캐시 조회 쿼리**:
```sql
SELECT * FROM amz_keyword_search_log
WHERE keyword = %s
  AND searched_at >= NOW() - INTERVAL 7 DAY
ORDER BY searched_at DESC
LIMIT 1;
```

**Race condition 방지**:
- `status='collecting'`이 이미 존재하면 중복 API 호출 차단
- 10분 이상 `collecting` 상태면 timeout 간주 → 재수집 허용

### 3.2 amz_keyword_products (검색 결과 제품)

```sql
CREATE TABLE amz_keyword_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    brand VARCHAR(200) DEFAULT '',        -- _resolve_brand() 적용 후
    manufacturer VARCHAR(200) DEFAULT '',
    price DECIMAL(10,2),                  -- final_price
    initial_price DECIMAL(10,2),          -- 할인 전 가격
    currency VARCHAR(10) DEFAULT 'USD',
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INT DEFAULT 0,
    bsr INT,                              -- root_bs_rank
    bsr_category VARCHAR(200) DEFAULT '', -- root_bs_category
    position INT DEFAULT 0,               -- 검색 결과 순위 (배열 인덱스 기반)
    sponsored TINYINT(1) DEFAULT 0,
    badge VARCHAR(100) DEFAULT '',
    bought_past_month INT,
    coupon VARCHAR(200) DEFAULT '',
    customer_says TEXT,                    -- customer_says / customers_say fallback
    plus_content TINYINT(1) DEFAULT 0,
    number_of_sellers INT DEFAULT 1,
    variations_count INT DEFAULT 0,
    image_url VARCHAR(500) DEFAULT '',
    product_url VARCHAR(500) DEFAULT '',
    features TEXT,                         -- JSON array
    description TEXT,
    categories TEXT,                       -- JSON array
    searched_at DATETIME NOT NULL,         -- 캐시 키 (search_log.searched_at 참조)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kp_keyword_searched (keyword, searched_at),
    INDEX idx_kp_asin (asin)
);
```

**amz_products와의 관계**: 동일 ASIN이 양쪽 테이블에 중복 존재 가능. 별도 테이블로 독립 관리하되, 성분 캐시(`amz_ingredient_cache`)는 ASIN 기반으로 공유.

## 4. 컴포넌트 상세 설계

### 4.1 BrightDataService — `trigger_keyword_search()` (신규 메서드)

**파일**: `amz_researcher/services/bright_data.py`

```python
async def trigger_keyword_search(
    self,
    keyword: str,
    limit_per_input: int = 100,
) -> str:
    """키워드 검색 트리거 → snapshot_id 반환.

    기존 trigger_collection()과 동일 base URL, discover_by만 변경.
    """
    url = (
        f"{self.base_url}/trigger"
        f"?dataset_id={self.dataset_id}"   # 기존 BSR dataset 재활용
        f"&type=discover_new"
        f"&discover_by=keyword"            # 카테고리: best_sellers_url
        f"&limit_per_input={limit_per_input}"
    )

    body = [{"keyword": keyword}]

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            resp = await self.client.post(url, headers=self._headers(), json=body)
            if resp.status_code != 200:
                raise BrightDataError(f"Keyword trigger failed: {resp.status_code} {resp.text[:300]}")
            data = resp.json()
            snapshot_id = data.get("snapshot_id")
            if not snapshot_id:
                raise BrightDataError(f"No snapshot_id in response: {data}")
            return snapshot_id
        except BrightDataError as e:
            last_error = e
            if attempt == 0:
                logger.warning("trigger_keyword_search attempt %d failed, retrying: %s", attempt + 1, e)
    raise last_error  # type: ignore[misc]
```

**설계 결정**:
- 기존 `trigger_collection()`과 구조 동일, `discover_by` 파라미터만 다름
- 재시도 로직(2회) 동일 적용
- `dataset_id`는 기존 BSR dataset 재활용 (`settings.BRIGHT_DATA_DATASET_ID`)
- `notify_url` 미사용 — polling 방식 채택 (실시간 요청이므로 webhook 불필요)

### 4.2 DataCollector — `process_search_snapshot()` (신규 메서드)

**파일**: `amz_researcher/services/data_collector.py`

```python
def process_search_snapshot(
    self,
    products: list[dict],
    keyword: str,
    searched_at: datetime,
) -> int:
    """키워드 검색 결과를 amz_keyword_products에 적재.

    Args:
        products: Bright Data API 응답 (JSON array)
        keyword: 정규화된 검색 키워드
        searched_at: 검색 시각 (캐시 키)

    Returns:
        적재된 제품 수
    """
```

**필드 매핑 (API → DB)**:

| API 필드 | DB 컬럼 | 변환 |
|----------|---------|------|
| `title` | `title` | `[:500]` truncate |
| `brand` | `brand` | `_resolve_brand(brand, title)` 적용 |
| `manufacturer` | `manufacturer` | 그대로 |
| `final_price` | `price` | `float`, None 허용 |
| `initial_price` | `initial_price` | `float`, None 허용 |
| `currency` | `currency` | 기본 `"USD"` |
| `rating` | `rating` | `float`, 기본 `0` |
| `reviews_count` | `reviews_count` | `int`, 기본 `0` |
| `root_bs_rank` | `bsr` | `int`, None 허용 |
| `root_bs_category` | `bsr_category` | `str` |
| (배열 인덱스) | `position` | `enumerate(products, 1)` |
| `sponsored` | `sponsored` | `bool → int` |
| `badge` | `badge` | `str` |
| `bought_past_month` | `bought_past_month` | `int`, None 허용 |
| `coupon` | `coupon` | `str` |
| `customer_says` or `customers_say` | `customer_says` | **양쪽 fallback** |
| `plus_content` | `plus_content` | `bool → int` |
| `number_of_sellers` | `number_of_sellers` | `int`, 기본 `1` |
| `variations_count` | `variations_count` | `int`, 기본 `0` |
| `image_url` | `image_url` | `str` |
| `url` | `product_url` | `str` |
| `features` | `features` | `json.dumps()` |
| `description` | `description` | `str` |
| `categories` | `categories` | `json.dumps()` |

**구현 전략**:
- pandas DataFrame → `MysqlConnector.upsert_data()` 사용 불가 (PK가 AUTO_INCREMENT)
- `delete_and_insert()` 사용: 동일 keyword + searched_at의 기존 데이터 삭제 후 INSERT
- `_resolve_brand()` 기존 함수 재활용 (모듈 레벨 import)

### 4.3 ProductDBService — 신규 메서드 2개

**파일**: `amz_researcher/services/product_db.py`

#### `get_keyword_cache(keyword: str) -> dict | None`

```python
def get_keyword_cache(self, keyword: str) -> dict | None:
    """7일 이내 완료된 검색 캐시 조회.

    Returns:
        {
            "keyword": str,
            "product_count": int,
            "searched_at": datetime,
            "status": str,
        } or None
    """
    normalized = " ".join(keyword.lower().split())
    query = """
        SELECT keyword, product_count, searched_at, status
        FROM amz_keyword_search_log
        WHERE keyword = %s
          AND searched_at >= NOW() - INTERVAL %s DAY
        ORDER BY searched_at DESC
        LIMIT 1
    """
    with MysqlConnector("CFO") as conn:
        df = conn.read_query_table(query, (normalized, settings.AMZ_KEYWORD_CACHE_DAYS))
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    return row
```

**Race condition 처리**:
- `status='collecting'`이면 → 호출자에게 "수집 중" 반환
- `status='completed'`이면 → 캐시 HIT
- `status='failed'`이면 → 캐시 MISS (재수집 허용)
- `collecting` 상태가 10분 초과면 → timeout 간주, 재수집 허용

```python
if cache and cache["status"] == "collecting":
    elapsed = (datetime.now() - cache["searched_at"]).total_seconds()
    if elapsed < 600:  # 10분 미만
        return "collecting"  # 대기 안내
    # timeout → 재수집 허용
```

#### `get_keyword_products(keyword: str, searched_at: datetime) -> list[dict]`

```python
def get_keyword_products(self, keyword: str, searched_at: datetime) -> list[dict]:
    """캐시된 키워드 검색 결과 조회."""
    normalized = " ".join(keyword.lower().split())
    query = """
        SELECT * FROM amz_keyword_products
        WHERE keyword = %s AND searched_at = %s
        ORDER BY position ASC
    """
    with MysqlConnector("CFO") as conn:
        df = conn.read_query_table(query, (normalized, searched_at))
    return df.to_dict("records") if not df.empty else []
```

#### `save_keyword_search_log()` / `update_keyword_search_log()`

```python
def save_keyword_search_log(
    self, keyword: str, snapshot_id: str = "",
) -> datetime:
    """검색 로그 INSERT (status='collecting'). searched_at 반환."""

def update_keyword_search_log(
    self, keyword: str, searched_at: datetime,
    status: str, product_count: int = 0,
):
    """검색 로그 상태 업데이트."""
```

### 4.4 성분 보완 전략 (Ingredient Enrichment)

**기존 재활용 컴포넌트**:
- `AmzCacheService.get_ingredient_cache(asins)` — ASIN 기반 성분 캐시 조회
- `GeminiService.extract_ingredients(products)` — Gemini 성분 추출
- `AmzCacheService.save_ingredient_cache()` — 캐시 저장
- `AmzCacheService.harmonize_common_names()` — common_name 통일

#### Layer 1: 기존 성분 캐시 매칭 ($0)

```python
asins = [p["asin"] for p in keyword_products]
cached_ingredients = cache.get_ingredient_cache(asins)
# HIT된 ASIN은 즉시 사용, MISS만 Layer 2로
uncached_asins = [a for a in asins if a not in cached_ingredients]
```

#### Layer 2: Gemini 추출 (미캐시 ASIN만)

```python
def _prepare_for_gemini(keyword_product: dict) -> dict:
    """키워드 검색 결과를 Gemini 성분 추출 입력으로 변환.

    키워드 검색 API에는 ingredients 전용 필드가 없으므로
    description → ingredients_raw로 매핑하여 Gemini가 추출하도록 함.
    features는 list[str] → dict 변환 불필요 (Gemini 프롬프트가 리스트도 처리).
    """
    return {
        "asin": keyword_product["asin"],
        "title": keyword_product["title"],
        "ingredients_raw": keyword_product.get("description", ""),
        "features": keyword_product.get("features", []),
        "additional_details": {},
    }
```

**features 타입 호환성**:
- 키워드 검색 API: `features` = `list[str]` (예: `["BRIGHTENING...", "LIGHTWEIGHT..."]`)
- 카테고리 수집: `features` = `dict` (product_details 파싱 결과)
- Gemini 프롬프트는 양쪽 모두 처리 가능 — 단, `features`가 `list[str]`일 경우 JSON 직렬화 후 전달

### 4.5 orchestrator.py — `run_keyword_analysis()` (신규 함수)

**파일**: `amz_researcher/orchestrator.py`

```python
async def run_keyword_analysis(
    keyword: str,
    response_url: str,
    channel_id: str,
):
    """키워드 검색 기반 분석 파이프라인.

    기존 run_analysis()와 유사하나:
    1. 카테고리 대신 키워드로 검색
    2. Bright Data discover_by=keyword 사용
    3. 성분 보완: ingredient_cache + Gemini (description 기반)
    4. 9시트 전용 Excel (BSR 의존 3시트 제거)
    5. Market report 캐시 비활성화 (V1)
    """
```

**Step-by-Step 흐름**:

```
Step 1: 캐시 확인
  → ProductDBService.get_keyword_cache(keyword)
  → HIT: DB에서 제품 로드 (Step 3으로)
  → COLLECTING: "수집 중" 응답 후 종료
  → MISS: Step 2로

Step 2: Bright Data 수집
  → ProductDBService.save_keyword_search_log(keyword)  # status='collecting'
  → BrightDataService.trigger_keyword_search(keyword)
  → BrightDataService.poll_snapshot(snapshot_id)
  → DataCollector.process_search_snapshot(products, keyword, searched_at)
  → ProductDBService.update_keyword_search_log(status='completed')

Step 3: 제품 데이터 로드
  → ProductDBService.get_keyword_products(keyword, searched_at)
  → 0건이면 "검색 결과 없음" 응답 후 종료

Step 4: 성분 보완
  → Layer 1: cache.get_ingredient_cache(asins)
  → Layer 2: _prepare_for_gemini() → gemini.extract_ingredients()
  → cache.save_ingredient_cache() + cache.harmonize_common_names()

Step 5: 가중치 계산
  → _adapt_search_for_analyzer(keyword_products)  # 신규 어댑터
  → calculate_weights(search_products, details, gemini_results)
  → V4 확장 필드 주입 (badge, customer_says, initial_price 등)

Step 6: 시장 분석
  → build_keyword_market_analysis(keyword, weighted_products, details)
  → Market report 캐시 비활성화 (V1)
  → gemini.generate_market_report(analysis_data)

Step 7: Excel 생성
  → build_keyword_excel() (9시트)

Step 8: Slack 응답
  → Block Kit 요약 + Excel 파일 업로드
```

#### `_adapt_search_for_analyzer()` — 검색 결과 → WeightedProduct 변환

```python
def _adapt_search_for_analyzer(
    keyword_products: list[dict],
) -> tuple[list[SearchProduct], list[ProductDetail]]:
    """키워드 검색 결과(DB dict) → SearchProduct + ProductDetail 변환.

    기존 _adapt_for_analyzer()와 유사하나:
    - 입력이 BrightDataProduct가 아닌 DB dict
    - ingredients_raw = description (키워드 검색에는 ingredients 필드 없음)
    - features = JSON 문자열 → list[str] 파싱 후 dict 변환
    """
    search_products = []
    details = []

    for row in keyword_products:
        price = row.get("price")
        price_str = f"${price:.2f}" if price is not None else ""

        search_products.append(SearchProduct(
            position=row.get("position", 0),
            title=row.get("title", ""),
            asin=row["asin"],
            price=price,
            price_raw=price_str,
            reviews=row.get("reviews_count", 0),
            reviews_raw=str(row.get("reviews_count", 0)),
            rating=row.get("rating", 0.0),
            sponsored=bool(row.get("sponsored", 0)),
            product_link=row.get("product_url", ""),
            bought_past_month=row.get("bought_past_month"),
        ))

        # features: JSON string → list → dict 변환
        features_raw = row.get("features", "[]")
        if isinstance(features_raw, str):
            try:
                features_list = json.loads(features_raw)
            except (json.JSONDecodeError, TypeError):
                features_list = []
        else:
            features_list = features_raw or []

        features_dict = {f"Feature {i+1}": f for i, f in enumerate(features_list)}

        details.append(ProductDetail(
            asin=row["asin"],
            ingredients_raw=row.get("description", ""),  # description → ingredients_raw
            features=features_dict,
            measurements={},
            additional_details={},
            bsr_category=row.get("bsr"),
            bsr_category_name=row.get("bsr_category", ""),
            rating=row.get("rating"),
            review_count=row.get("reviews_count"),
            brand=row.get("brand", ""),
            manufacturer=row.get("manufacturer", ""),
            product_url=row.get("product_url", ""),
        ))

    return search_products, details
```

### 4.6 시장 분석 — `build_keyword_market_analysis()` (신규)

**파일**: `amz_researcher/services/market_analyzer.py`

```python
def build_keyword_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    """키워드 검색 전용 시장 분석. BSR 의존 분석 3개 제외."""
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        # 재활용 (BSR 의존도 낮음)
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),  # 참고용 유지
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
        "sales_volume": analyze_sales_volume(weighted_products),
        "sns_pricing": analyze_sns_pricing(weighted_products),
        "promotions": analyze_promotions(weighted_products),
        "customer_voice": analyze_customer_voice(weighted_products),
        "discount_impact": analyze_discount_impact(weighted_products),
        "title_keywords": analyze_title_keywords(weighted_products),
        "unit_economics": analyze_unit_economics(weighted_products),
        "manufacturer": analyze_manufacturer(weighted_products, details),
        "sku_strategy": analyze_sku_strategy(weighted_products),
        # 제외 (크로스 카테고리 BSR 비교 무의미)
        # "brand_positioning": X  (BSR 기반 브랜드 비교 → 오해 유발)
        # "rising_products": X    (BSR < 10,000 로직 무의미)
        # "badges": X             (Mann-Whitney U 검정이 무의미)
    }
```

**제외 근거** (Plan 4.10 참조):
| 분석 | 제외 사유 |
|------|-----------|
| `analyze_brand_positioning()` | 다른 카테고리 브랜드를 BSR로 비교하면 오해 유발 |
| `detect_rising_products()` | "BSR < 10,000이면 성장 제품" 로직이 크로스 카테고리에서 무의미 |
| `analyze_badges()` | Mann-Whitney U 통계 검정이 크로스 카테고리 BSR 비교 시 무의미 |

### 4.7 Excel — `build_keyword_excel()` (신규 함수)

**파일**: `amz_researcher/services/excel_builder.py`

```python
def build_keyword_excel(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str = "",
    analysis_data: dict | None = None,
) -> bytes:
    """키워드 검색 전용 9시트 Excel 생성.

    카테고리 리포트(12시트)에서 BSR 의존 3시트 제거:
    - Badge Analysis (삭제)
    - Brand Positioning (삭제)
    - Rising Products (삭제)

    Consumer Voice는 BSR correlation 섹션만 제거.
    """
    wb = Workbook()

    # === Insight tabs ===
    _build_ingredient_ranking(wb, keyword, rankings, len(weighted_products))
    if market_report:
        _build_market_insight(wb, keyword, market_report)
    if analysis_data:
        customer_voice = analysis_data.get("customer_voice")
        if customer_voice:
            _build_consumer_voice(wb, customer_voice, is_keyword=True)
        # Badge Analysis 제거
        _build_sales_pricing(wb, analysis_data)

    # === Analysis tabs ===
    if analysis_data:
        # Brand Positioning 제거
        _build_marketing_keywords(wb, analysis_data)
    _build_category_summary(wb, categories)
    # Rising Products 제거
    _build_product_detail(wb, weighted_products)

    # === Raw tabs ===
    _build_raw_search(wb, keyword, search_products)
    _build_raw_detail(wb, details)

    # Reorder: 9시트
    desired_order = [
        "Market Insight",
        "Consumer Voice",
        "Sales & Pricing",
        "Marketing Keywords",
        "Ingredient Ranking",
        "Category Summary",
        "Product Detail",
        "Raw - Search Results",
        "Raw - Product Detail",
    ]
    existing = wb.sheetnames
    ordered = [s for s in desired_order if s in existing]
    ordered += [s for s in existing if s not in ordered]
    wb._sheets = [wb[s] for s in ordered]

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
```

#### Consumer Voice — BSR Correlation 조건부 스킵

기존 `_build_consumer_voice()` 함수에 `is_keyword: bool = False` 파라미터 추가:

```python
def _build_consumer_voice(wb: Workbook, customer_voice_data: dict, is_keyword: bool = False):
    """customer_says 키워드 분석 결과 시트.

    Args:
        is_keyword: True이면 BSR Correlation 섹션 스킵 (크로스 카테고리 비교 무의미)
    """
    # ... 기존 코드 ...

    # BSR Correlation 섹션 — 키워드 검색에서는 스킵
    if not is_keyword:
        bsr_top_pos = customer_voice_data.get("bsr_top_half_positive")
        # ... 기존 BSR correlation 코드 ...
```

### 4.8 router.py — "search" 서브커맨드 추가

**파일**: `amz_researcher/router.py`

기존 `slack_amz()` 함수의 서브커맨드 분기에 `search` 추가:

```python
# 기존 코드 위치: subcommand 분기 (help, add, list, refresh, prod 다음)

# /amz search {keyword} — 키워드 검색 분석
if subcommand == "search":
    keyword_parts = parts[1:]
    keyword = " ".join(keyword_parts).strip()
    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/amz search {키워드}`\n예: `/amz search vitamin c serum for face`",
        }
    background_tasks.add_task(run_keyword_analysis, keyword, response_url, channel_id)
    return {
        "response_type": "in_channel",
        "text": f"🔍 키워드 *\"{keyword}\"* 검색 분석 시작... (1-3분 소요)",
    }
```

**배치 위치**: `prod` 서브커맨드 앞 (default 키워드 검색보다 먼저 매칭)

#### `/amz help` 업데이트

기존 `_build_help_response()`에 키워드 검색 섹션 추가:

```python
{
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": (
            "*🔍 키워드 검색 분석*\n\n"
            "`/amz search {키워드}`\n"
            "Amazon 검색 결과를 분석합니다. 카테고리 등록 없이 자유롭게 검색 가능.\n"
            "7일 내 동일 키워드 재검색 시 캐시를 사용합니다.\n\n"
            "_예시:_\n"
            "• `/amz search vitamin c serum for face`\n"
            "• `/amz search organic hair oil`\n"
            "• `/amz search korean skincare set`"
        ),
    },
},
```

### 4.9 Config 변경

**파일**: `app/config.py`

```python
# 기존 Settings 클래스에 추가
AMZ_KEYWORD_CACHE_DAYS: int = 7
```

**기존 dataset_id 재활용**: `BRIGHT_DATA_DATASET_ID` (= `gd_l7q7dkf244hwjntr0`) 그대로 사용. 별도 `BRIGHT_DATA_SEARCH_DATASET_ID` 불필요.

### 4.10 가중치 계산 호환성

키워드 검색 결과에 `bought_past_month` 필드가 존재하므로 V4 가중치가 자동 적용:

| 가중치 요소 | V4 비율 | 키워드 검색 적용 |
|------------|--------|----------------|
| bought_past_month | 30% | `SearchProduct.bought_past_month` |
| BSR | 25% | `ProductDetail.bsr_category` (= `root_bs_rank`) |
| Reviews | 20% | `SearchProduct.reviews` |
| Position | 15% | `SearchProduct.position` (검색 순위) |
| Rating | 10% | `SearchProduct.rating` |

**기존 `calculate_weights()` 함수 변경 없음** — 입력 모델만 맞추면 자동 적용.

### 4.11 Market Report 캐시 분리

**V1 결정**: 키워드 검색 market report 캐시 **비활성화**

- 기존 `AmzCacheService.get_market_report_cache()`는 내부에서 `_get_data_freshness()`가 `amz_categories` 테이블을 조인
- 키워드 검색에서는 이 조인이 불가능
- 7일 검색 캐시로 API 호출 자체가 제한되므로 Gemini 리포트 생성 비용 영향 최소

```python
# orchestrator.py — run_keyword_analysis() 내부
# V1: market report 캐시 비활성화 (매번 Gemini 생성)
market_report = await gemini.generate_market_report(analysis_data)
# cache.save_market_report_cache() 호출 안 함
```

### 4.12 Slack 응답 메시지

**Phase별 진행 메시지**:

| 시점 | 메시지 |
|------|--------|
| 즉시 응답 | `🔍 키워드 "{keyword}" 검색 분석 시작... (1-3분 소요)` |
| 캐시 HIT | `♻️ 캐시 사용 ({N}일 전 수집, {M}개 제품). 분석 시작...` |
| 캐시 MISS | `📡 Bright Data 수집 시작... (1-3분 소요)` |
| 수집 완료 | `📦 {N}개 제품 수집 완료. 성분 분석 중...` |
| 성분 매칭 | `🧪 성분 캐시 {X}건 매칭 / {Y}건 Gemini 추출 중...` |
| 분석 완료 | Block Kit 요약 + Excel 파일 (기존과 동일 형식) |
| 0건 결과 | `⚠️ "{keyword}" 검색 결과가 없습니다.` |
| 에러 | `❌ "{keyword}" 검색 분석 실패: {에러메시지}` |

**Block Kit 요약**: 기존 `_build_summary_blocks()` 재활용. 가중치 공식 표기는 V4 기준 유지.

### 4.13 에러 핸들링

| 시나리오 | 처리 |
|----------|------|
| Bright Data API 실패 | `amz_keyword_search_log` status='failed' 업데이트 → Slack 에러 메시지 → 관리자 DM |
| 검색 결과 0건 | "검색 결과 없음" 즉시 응답, 분석 스킵 |
| Gemini 성분 추출 실패 | 빈 성분으로 처리 (graceful degradation) |
| Gemini rate limit (429) | 성분 없이 리포트 생성 |
| Market report 캐시 freshness 조인 실패 | V1: 캐시 비활성화로 이슈 없음 |
| Race condition (동시 검색) | `status='collecting'` 체크 → "수집 진행 중" 응답 |
| `collecting` 10분 초과 | timeout 간주, 재수집 허용 |

## 5. 파일 변경 목록

### 5.1 신규 파일

없음 (기존 파일에 메서드/함수 추가)

### 5.2 수정 파일

| 파일 | 변경 내용 | 영향 범위 |
|------|-----------|-----------|
| `app/config.py` | `AMZ_KEYWORD_CACHE_DAYS: int = 7` 추가 | 설정만, 기존 영향 없음 |
| `amz_researcher/services/bright_data.py` | `trigger_keyword_search()` 메서드 추가 | 신규 메서드, 기존 영향 없음 |
| `amz_researcher/services/data_collector.py` | `process_search_snapshot()` 메서드 추가 | 신규 메서드, 기존 `process_snapshot()` 미변경 |
| `amz_researcher/services/product_db.py` | `get_keyword_cache()`, `get_keyword_products()`, `save_keyword_search_log()`, `update_keyword_search_log()` 추가 | 신규 메서드 4개, 기존 미변경 |
| `amz_researcher/services/market_analyzer.py` | `build_keyword_market_analysis()` 함수 추가 | 신규 함수, 기존 `build_market_analysis()` 미변경 |
| `amz_researcher/services/excel_builder.py` | `build_keyword_excel()` 함수 추가, `_build_consumer_voice()` 파라미터 추가 | `_build_consumer_voice()` 시그니처 변경 (기본값으로 호환) |
| `amz_researcher/orchestrator.py` | `run_keyword_analysis()`, `_adapt_search_for_analyzer()`, `_prepare_for_gemini()` 함수 추가 | 신규 함수 3개, 기존 미변경 |
| `amz_researcher/router.py` | "search" 서브커맨드 추가, `_build_help_response()` 업데이트 | 기존 서브커맨드 미변경 |

### 5.3 DB 마이그레이션

신규 파일: `amz_researcher/migrations/v6_keyword_search.py`

```python
"""V6: 키워드 검색 분석 테이블 추가."""

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS amz_keyword_search_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    product_count INT DEFAULT 0,
    snapshot_id VARCHAR(100) DEFAULT '',
    status ENUM('collecting', 'completed', 'failed') NOT NULL DEFAULT 'collecting',
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_keyword_searched (keyword, searched_at DESC)
);

CREATE TABLE IF NOT EXISTS amz_keyword_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    brand VARCHAR(200) DEFAULT '',
    manufacturer VARCHAR(200) DEFAULT '',
    price DECIMAL(10,2),
    initial_price DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'USD',
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INT DEFAULT 0,
    bsr INT,
    bsr_category VARCHAR(200) DEFAULT '',
    position INT DEFAULT 0,
    sponsored TINYINT(1) DEFAULT 0,
    badge VARCHAR(100) DEFAULT '',
    bought_past_month INT,
    coupon VARCHAR(200) DEFAULT '',
    customer_says TEXT,
    plus_content TINYINT(1) DEFAULT 0,
    number_of_sellers INT DEFAULT 1,
    variations_count INT DEFAULT 0,
    image_url VARCHAR(500) DEFAULT '',
    product_url VARCHAR(500) DEFAULT '',
    features TEXT,
    description TEXT,
    categories TEXT,
    searched_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kp_keyword_searched (keyword, searched_at),
    INDEX idx_kp_asin (asin)
);
"""
```

## 6. 구현 순서

```
Phase 1: 인프라 (기반)
├─ 1. [ ] app/config.py: AMZ_KEYWORD_CACHE_DAYS 추가
├─ 2. [ ] DB 마이그레이션: amz_keyword_search_log + amz_keyword_products 테이블 생성
└─ 3. [ ] BrightDataService.trigger_keyword_search() 메서드 추가

Phase 2: 데이터 레이어
├─ 4. [ ] ProductDBService: get_keyword_cache(), get_keyword_products(),
│         save_keyword_search_log(), update_keyword_search_log()
├─ 5. [ ] DataCollector.process_search_snapshot() 메서드
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
├─ 12. [ ] build_keyword_market_analysis() (BSR 의존 3개 분석 제외)
└─ 13. [ ] build_keyword_excel() (9시트) + _build_consumer_voice() is_keyword 파라미터

Phase 5: Slack 연동
├─ 14. [ ] router.py: "search" 서브커맨드 핸들링
├─ 15. [ ] /amz help 업데이트 (키워드 검색 섹션 추가)
└─ 16. [ ] 에러 핸들링 (관리자 알림, 0건 결과, rate limit)
```

## 7. 테스트 전략

### 7.1 E2E 검증 (Phase 2.5)

```python
# limit=10으로 소규모 테스트
snapshot_id = await bright_data.trigger_keyword_search("vitamin c serum", limit_per_input=10)
products = await bright_data.poll_snapshot(snapshot_id)
count = collector.process_search_snapshot(products, "vitamin c serum", datetime.now())
assert count == 10
```

### 7.2 통합 테스트

| 시나리오 | 검증 항목 |
|----------|-----------|
| 신규 키워드 검색 | Bright Data 호출 → DB 적재 → 분석 → 9시트 Excel → Slack 응답 |
| 캐시 HIT | 7일 내 동일 키워드 → DB 조회만, Bright Data 미호출 |
| 캐시 MISS (7일 초과) | 재수집 트리거 |
| Race condition | 동시 "vitamin c serum" 2건 → 1건만 API 호출 |
| 0건 결과 | "검색 결과 없음" 즉시 응답 |
| 성분 캐시 재활용 | 카테고리 분석에서 캐시된 ASIN이 키워드 검색에도 등장 → Layer 1 HIT |

## 8. Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-09 | Plan 기반 초기 Design 문서 작성 | CTO Team |
