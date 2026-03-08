# Design: Amazon Researcher V4 — Bright Data 전환 + 데이터 파이프라인

## 1. Overview

Browse.ai 실시간 크롤링을 Bright Data Web Scraper API 기반 주간 배치 수집으로 전환한다.
카테고리별 BSR Top 100을 DB에 적재하고, 사용자 요청 시 DB 조회 → Gemini 분석 → Excel/Slack 응답.

**Plan 참조**: `docs/01-plan/features/amazon-researcher-v4.plan.md`

## 2. 아키텍처

### 2.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────┐
│                     주간 배치 수집                            │
│                                                             │
│  [Cron / Manual Trigger]                                    │
│       ↓                                                     │
│  BrightDataService.trigger_collection(categories)           │
│       ↓                                                     │
│  Bright Data API (discover_by=best_sellers_url)             │
│       ↓ (polling: 10s 간격, 최대 30회)                       │
│  DataCollector.process_snapshot(data)                        │
│       ↓                                                     │
│  amz_products (upsert)  +  amz_products_history (append)    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     사용자 요청 분석                          │
│                                                             │
│  [Slack: /amz {keyword}]                                    │
│       ↓                                                     │
│  router.py → amz_categories fuzzy match                     │
│       ↓                                                     │
│  Slack 카테고리 버튼 제시                                     │
│       ↓ (사용자 선택)                                        │
│  [Slack: interactivity callback]                             │
│       ↓                                                     │
│  orchestrator.run_analysis(category_node_id)                 │
│       ↓                                                     │
│  amz_products 조회 → Gemini 성분 추출 → 가중치 계산           │
│       ↓                                                     │
│  Excel + Slack 응답                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

```
Bright Data API Response (JSON Array)
  → DataCollector.process_snapshot()
    → field mapping (API 필드 → DB 컬럼)
    → amz_products UPSERT (asin 기준)
    → amz_products_history INSERT (asin + snapshot_date UNIQUE)
    → amz_product_categories INSERT (asin ↔ category 매핑)
```

## 3. DB 설계 (검증된 스키마)

> API 테스트 결과를 반영하여 Plan 대비 필드명/타입 보정

### 3.1 amz_categories (카테고리 마스터)

```sql
CREATE TABLE amz_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    node_id VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    parent_node_id VARCHAR(20),
    url VARCHAR(500) NOT NULL,          -- Best Sellers 페이지 URL
    keywords VARCHAR(500) DEFAULT '',   -- fuzzy match용 검색어 (쉼표 구분)
    depth INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**초기 시딩 데이터:**

```sql
INSERT INTO amz_categories (node_id, name, parent_node_id, url, keywords, depth, is_active) VALUES
('11058281', 'Hair Growth Products', '11057241', 'https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281', 'hair growth, 탈모, 발모, 육모', 3, TRUE),
('3591081', 'Hair Loss Shampoos', '11057651', 'https://www.amazon.com/Best-Sellers/zgbs/beauty/3591081', 'hair loss shampoo, 탈모샴푸', 3, TRUE),
('11060451', 'Skin Care', '3760911', 'https://www.amazon.com/Best-Sellers/zgbs/beauty/11060451', 'skin care, 스킨케어, 기초화장품', 2, TRUE),
('11060901', 'Facial Cleansing', '11060451', 'https://www.amazon.com/Best-Sellers/zgbs/beauty/11060901', 'facial cleansing, 클렌징, 세안', 3, TRUE),
('3764441', 'Vitamins & Supplements', '3760901', 'https://www.amazon.com/Best-Sellers/zgbs/hpc/3764441', 'vitamins, supplements, 비타민, 영양제', 2, TRUE);
```

### 3.2 amz_products (최신 스냅샷)

```sql
CREATE TABLE amz_products (
    asin VARCHAR(20) PRIMARY KEY,
    title VARCHAR(500),
    brand VARCHAR(200),
    description TEXT,
    initial_price DECIMAL(10,2),
    final_price DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'USD',
    rating DECIMAL(3,2),
    reviews_count INT,
    bs_rank INT,                         -- 서브카테고리 BSR
    bs_category VARCHAR(200),            -- 서브카테고리명
    root_bs_rank INT,                    -- Beauty & Personal Care 전체 BSR
    root_bs_category VARCHAR(200),       -- 루트 카테고리명
    subcategory_ranks JSON,              -- [{subcategory_name, subcategory_rank}, ...]
    ingredients TEXT,                     -- Bright Data에서 직접 제공
    features JSON,                       -- 배열: ["feature1", "feature2", ...]
    product_details JSON,                -- [{type, value}, ...] dimensions/weight 등
    manufacturer VARCHAR(200),
    department VARCHAR(200),
    image_url VARCHAR(1000),
    url VARCHAR(1000),
    badge VARCHAR(100),                  -- "Amazon's Choice", "Best Seller" 등
    bought_past_month INT,
    is_available BOOLEAN DEFAULT TRUE,
    country_of_origin VARCHAR(100),
    item_weight VARCHAR(100),
    categories JSON,                     -- 카테고리 경로 배열 ["Beauty", "Makeup", ...]
    -- 분석 고도화 필드
    customer_says TEXT,                  -- Amazon AI 리뷰 요약 (소비자 인사이트)
    unit_price VARCHAR(100),             -- "$100.00 / ounce" 단가 비교용
    sns_price DECIMAL(10,2),             -- Subscribe & Save 가격 (재구매 제품 식별)
    variations_count INT DEFAULT 0,      -- SKU 다양성 (색상/사이즈 변형 수)
    number_of_sellers INT DEFAULT 1,     -- 셀러 수 (경쟁 강도)
    coupon VARCHAR(200),                 -- 쿠폰/프로모션 정보
    plus_content BOOLEAN DEFAULT FALSE,  -- A+ Content 보유 (리스팅 품질)
    collected_at DATETIME,               -- Bright Data 수집 시각
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.3 amz_products_history (시계열)

```sql
CREATE TABLE amz_products_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    asin VARCHAR(20) NOT NULL,
    snapshot_date DATE NOT NULL,
    bs_rank INT,
    bs_category VARCHAR(200),
    final_price DECIMAL(10,2),
    rating DECIMAL(3,2),
    reviews_count INT,
    bought_past_month INT,
    badge VARCHAR(100),
    root_bs_rank INT,
    number_of_sellers INT,               -- 경쟁 강도 변화 추적
    coupon VARCHAR(200),                 -- 프로모션 주기 추적
    INDEX idx_asin_date (asin, snapshot_date),
    UNIQUE KEY uk_asin_date (asin, snapshot_date)
);
```

### 3.4 amz_product_categories (제품-카테고리 매핑)

```sql
CREATE TABLE amz_product_categories (
    asin VARCHAR(20) NOT NULL,
    category_node_id VARCHAR(20) NOT NULL,
    collected_at DATE NOT NULL,
    PRIMARY KEY (asin, category_node_id),
    INDEX idx_category (category_node_id)
);
```

> 하나의 제품이 여러 카테고리에 속할 수 있으므로 N:M 매핑 테이블 필요.
> `discover_by=best_sellers_url` 호출 시 `origin_url`로 어떤 카테고리에서 수집되었는지 추적.

## 4. API 필드 매핑 (Bright Data → DB)

API 테스트 검증 완료 (`reference/brightdata_test_result.json`)

| Bright Data 필드 | DB 컬럼 | 타입 | 비고 |
|-----------------|---------|------|------|
| `asin` | `asin` | VARCHAR(20) | PK |
| `title` | `title` | VARCHAR(500) | |
| `brand` | `brand` | VARCHAR(200) | |
| `description` | `description` | TEXT | |
| `initial_price` | `initial_price` | DECIMAL(10,2) | |
| `final_price` | `final_price` | DECIMAL(10,2) | |
| `currency` | `currency` | VARCHAR(10) | |
| `rating` | `rating` | DECIMAL(3,2) | |
| `reviews_count` | `reviews_count` | INT | |
| `bs_rank` | `bs_rank` | INT | 서브카테고리 BSR |
| `bs_category` | `bs_category` | VARCHAR(200) | |
| `root_bs_rank` | `root_bs_rank` | INT | 전체 카테고리 BSR |
| `root_bs_category` | `root_bs_category` | VARCHAR(200) | |
| `subcategory_rank` | `subcategory_ranks` | JSON | 다중 서브카테고리 순위 배열 |
| `ingredients` | `ingredients` | TEXT | INCI 전성분 문자열 |
| `features` | `features` | JSON | 배열 형태 |
| `product_details` | `product_details` | JSON | [{type, value}] 배열 |
| `manufacturer` | `manufacturer` | VARCHAR(200) | |
| `department` | `department` | VARCHAR(200) | |
| `image_url` | `image_url` | VARCHAR(1000) | |
| `url` | `url` | VARCHAR(1000) | |
| `badge` | `badge` | VARCHAR(100) | "Amazon's Choice" 등 |
| `bought_past_month` | `bought_past_month` | INT | |
| `is_available` | `is_available` | BOOLEAN | |
| `categories` | `categories` | JSON | 카테고리 경로 배열 |
| `customer_says` | `customer_says` | TEXT | Amazon AI 리뷰 요약 |
| `buybox_prices.unit_price` | `unit_price` | VARCHAR(100) | 단가 비교용 |
| `buybox_prices.sns_price.base_price` | `sns_price` | DECIMAL(10,2) | Subscribe & Save 가격 |
| `len(variations)` | `variations_count` | INT | SKU 변형 수 |
| `number_of_sellers` | `number_of_sellers` | INT | 셀러 수 (경쟁 강도) |
| `coupon` | `coupon` | VARCHAR(200) | 프로모션 정보 |
| `plus_content` | `plus_content` | BOOLEAN | A+ Content 보유 |
| `origin_url` | → `amz_product_categories` | | 수집 카테고리 역추적 |

## 5. 파일 구조 및 변경 사항

### 5.1 신규 파일

| 파일 | 설명 |
|------|------|
| `amz_researcher/services/bright_data.py` | Bright Data API 클라이언트 |
| `amz_researcher/services/data_collector.py` | 수집 데이터 → DB 적재 로직 |
| `amz_researcher/services/product_db.py` | amz_products/categories DB 조회 서비스 |
| `amz_researcher/jobs/collect.py` | 주간 수집 job 엔트리포인트 |

### 5.2 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `amz_researcher/models.py` | `BrightDataProduct` 모델 추가, `WeightedProduct` 필드 확장 |
| `amz_researcher/orchestrator.py` | `run_analysis()` 신규 (DB 조회 기반), `run_research()` 유지→deprecate |
| `amz_researcher/router.py` | 카테고리 검색/선택 엔드포인트 추가, interactivity 핸들러 |
| `amz_researcher/services/analyzer.py` | `calculate_weights()` 입력을 `BrightDataProduct` 기반으로 변경 |
| `amz_researcher/services/gemini.py` | 입력 포맷 변경 (ingredients 문자열 직접 전달) |
| `app/config.py` | `BRIGHT_DATA_API_TOKEN`, `BRIGHT_DATA_DATASET_ID` 추가 |
| `main.py` | Slack interactivity endpoint 추가 |

### 5.3 삭제 파일 (Phase 3)

| 파일 | 사유 |
|------|------|
| `amz_researcher/services/browse_ai.py` | Bright Data로 완전 대체 |
| `amz_researcher/services/html_parser.py` | 구조화 JSON이므로 파싱 불필요 |

## 6. 컴포넌트 상세 설계

### 6.1 BrightDataService (`services/bright_data.py`)

```python
class BrightDataService:
    """Bright Data Web Scraper API 클라이언트."""

    def __init__(self, api_token: str, dataset_id: str):
        self.api_token = api_token
        self.dataset_id = dataset_id
        self.base_url = "https://api.brightdata.com/datasets/v3"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def trigger_collection(
        self, category_urls: list[str], limit_per_input: int = 100,
    ) -> str:
        """수집 트리거 → snapshot_id 반환.

        Args:
            category_urls: Best Sellers 카테고리 URL 리스트
            limit_per_input: 카테고리당 최대 수집 수

        Returns:
            snapshot_id (str)

        Raises:
            BrightDataError: API 호출 실패 시
        """
        url = (
            f"{self.base_url}/trigger"
            f"?dataset_id={self.dataset_id}"
            f"&type=discover_new"
            f"&discover_by=best_sellers_url"
            f"&limit_per_input={limit_per_input}"
        )
        body = [{"category_url": cat_url} for cat_url in category_urls]
        resp = await self.client.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        return resp.json()["snapshot_id"]

    async def poll_snapshot(
        self, snapshot_id: str,
        poll_interval: int = 10,
        max_attempts: int = 30,
    ) -> list[dict]:
        """스냅샷 결과 폴링. 완료 시 JSON 배열 반환.

        Returns:
            제품 데이터 리스트 (list[dict])

        Raises:
            TimeoutError: max_attempts 초과 시
        """
        url = f"{self.base_url}/snapshot/{snapshot_id}?format=json"
        for attempt in range(max_attempts):
            await asyncio.sleep(poll_interval)
            resp = await self.client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code != 202:
                logger.warning("Unexpected status %d: %s", resp.status_code, resp.text[:200])
        raise TimeoutError(f"Snapshot {snapshot_id} not ready after {max_attempts} attempts")

    async def collect_categories(
        self, category_urls: list[str], limit_per_input: int = 100,
    ) -> list[dict]:
        """trigger + poll을 한번에 수행."""
        snapshot_id = await self.trigger_collection(category_urls, limit_per_input)
        logger.info("Collection triggered: snapshot_id=%s", snapshot_id)
        return await self.poll_snapshot(snapshot_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def close(self):
        await self.client.aclose()
```

### 6.2 DataCollector (`services/data_collector.py`)

```python
class DataCollector:
    """Bright Data 수집 데이터를 DB에 적재."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def process_snapshot(
        self, products: list[dict], snapshot_date: date | None = None,
    ) -> int:
        """수집 데이터를 amz_products + amz_products_history에 적재.

        Args:
            products: Bright Data API 응답 (JSON 배열)
            snapshot_date: 스냅샷 날짜 (기본: today)

        Returns:
            적재된 제품 수
        """
        if not products:
            return 0
        snapshot_date = snapshot_date or date.today()

        # 1. amz_products upsert
        product_rows = [self._map_product(p) for p in products]
        df_products = pd.DataFrame(product_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_products, "amz_products")

        # 2. amz_products_history append
        history_rows = [self._map_history(p, snapshot_date) for p in products]
        df_history = pd.DataFrame(history_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_history, "amz_products_history")

        # 3. amz_product_categories 매핑
        cat_rows = self._map_categories(products, snapshot_date)
        if cat_rows:
            df_cats = pd.DataFrame(cat_rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df_cats, "amz_product_categories")

        logger.info("Processed %d products (snapshot: %s)", len(products), snapshot_date)
        return len(products)

    def _map_product(self, raw: dict) -> dict:
        """Bright Data 응답 → amz_products 행."""
        # Subscribe & Save 가격 추출
        buybox = raw.get("buybox_prices") or {}
        sns = buybox.get("sns_price") or {}
        sns_price = sns.get("base_price")

        return {
            "asin": raw["asin"],
            "title": (raw.get("title") or "")[:500],
            "brand": (raw.get("brand") or "")[:200],
            "description": raw.get("description") or "",
            "initial_price": raw.get("initial_price"),
            "final_price": raw.get("final_price"),
            "currency": raw.get("currency", "USD"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "root_bs_rank": raw.get("root_bs_rank"),
            "root_bs_category": raw.get("root_bs_category"),
            "subcategory_ranks": json.dumps(raw.get("subcategory_rank") or [], ensure_ascii=False),
            "ingredients": raw.get("ingredients") or "",
            "features": json.dumps(raw.get("features") or [], ensure_ascii=False),
            "product_details": json.dumps(raw.get("product_details") or [], ensure_ascii=False),
            "manufacturer": raw.get("manufacturer") or "",
            "department": raw.get("department") or "",
            "image_url": raw.get("image_url") or "",
            "url": raw.get("url") or "",
            "badge": raw.get("badge") or "",
            "bought_past_month": raw.get("bought_past_month"),
            "is_available": raw.get("is_available", True),
            "categories": json.dumps(raw.get("categories") or [], ensure_ascii=False),
            "customer_says": raw.get("customer_says") or "",
            "unit_price": buybox.get("unit_price") or "",
            "sns_price": sns_price,
            "variations_count": len(raw.get("variations") or []),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
            "plus_content": bool(raw.get("plus_content")),
            "collected_at": datetime.now(),
        }

    def _map_history(self, raw: dict, snapshot_date: date) -> dict:
        """Bright Data 응답 → amz_products_history 행."""
        return {
            "asin": raw["asin"],
            "snapshot_date": snapshot_date,
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "final_price": raw.get("final_price"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bought_past_month": raw.get("bought_past_month"),
            "badge": raw.get("badge") or "",
            "root_bs_rank": raw.get("root_bs_rank"),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
        }

    def _map_categories(self, products: list[dict], snapshot_date: date) -> list[dict]:
        """origin_url에서 카테고리 node_id를 추출하여 매핑 행 생성."""
        rows = []
        for p in products:
            origin = p.get("origin_url") or ""
            # origin_url 예: https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281
            node_id = origin.rstrip("/").split("/")[-1] if origin else ""
            if node_id and node_id.isdigit():
                rows.append({
                    "asin": p["asin"],
                    "category_node_id": node_id,
                    "collected_at": snapshot_date,
                })
        return rows
```

### 6.3 ProductDBService (`services/product_db.py`)

```python
class ProductDBService:
    """amz_products / amz_categories DB 조회 서비스."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def search_categories(self, keyword: str) -> list[dict]:
        """키워드로 카테고리 fuzzy 검색. is_active=TRUE만.

        Returns:
            [{"node_id": "11058281", "name": "Hair Growth Products", ...}, ...]
        """
        query = (
            "SELECT node_id, name, url, keywords "
            "FROM amz_categories WHERE is_active = TRUE"
        )
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query)
        if df.empty:
            return []

        keyword_lower = keyword.lower()
        results = []
        for _, row in df.iterrows():
            name = (row["name"] or "").lower()
            kws = (row["keywords"] or "").lower()
            if keyword_lower in name or keyword_lower in kws:
                results.append({
                    "node_id": row["node_id"],
                    "name": row["name"],
                    "url": row["url"],
                })
        return results

    def get_products_by_category(self, category_node_id: str) -> list[dict]:
        """카테고리별 제품 조회 (amz_product_categories JOIN amz_products)."""
        query = """
            SELECT p.*
            FROM amz_products p
            JOIN amz_product_categories pc ON p.asin = pc.asin
            WHERE pc.category_node_id = %s
            ORDER BY p.bs_rank ASC
        """
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query, (category_node_id,))
        if df.empty:
            return []
        return df.to_dict("records")

    def get_all_active_category_urls(self) -> list[str]:
        """활성 카테고리의 URL 목록 반환 (수집 job용)."""
        query = "SELECT url FROM amz_categories WHERE is_active = TRUE"
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query)
        return df["url"].tolist() if not df.empty else []

    def list_categories(self) -> list[dict]:
        """전체 활성 카테고리 목록."""
        query = (
            "SELECT node_id, name, keywords FROM amz_categories "
            "WHERE is_active = TRUE ORDER BY name"
        )
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query)
        return df.to_dict("records") if not df.empty else []
```

### 6.4 models.py 변경

```python
# 기존 모델 유지 + 추가

class BrightDataProduct(BaseModel):
    """Bright Data API 응답을 DB 조회 결과로 변환한 제품 모델.
    V3의 SearchProduct + ProductDetail을 통합."""
    asin: str
    title: str = ""
    brand: str = ""
    description: str = ""
    initial_price: float | None = None
    final_price: float | None = None
    currency: str = "USD"
    rating: float = 0.0
    reviews_count: int = 0
    bs_rank: int | None = None
    bs_category: str = ""
    root_bs_rank: int | None = None
    root_bs_category: str = ""
    subcategory_ranks: list[dict] = []   # [{subcategory_name, subcategory_rank}]
    ingredients: str = ""                # INCI 전성분 문자열 (Bright Data 직접 제공)
    features: list[str] = []
    manufacturer: str = ""
    department: str = ""
    image_url: str = ""
    url: str = ""
    badge: str = ""
    bought_past_month: int | None = None
    categories: list[str] = []           # 카테고리 경로 (세분화 분석용)
    # 분석 고도화 필드
    customer_says: str = ""              # Amazon AI 리뷰 요약
    unit_price: str = ""                 # 단가 비교 ("$X.XX / ounce")
    sns_price: float | None = None       # Subscribe & Save 가격
    variations_count: int = 0            # SKU 변형 수
    number_of_sellers: int = 1           # 셀러 수 (경쟁 강도)
    coupon: str = ""                     # 프로모션 정보
    plus_content: bool = False           # A+ Content 보유
```

### 6.5 orchestrator.py — `run_analysis()` (신규)

```python
async def run_analysis(
    category_node_id: str,
    category_name: str,
    response_url: str,
    channel_id: str,
):
    """DB 기반 분석 파이프라인. V3의 run_research() 대체.

    1. amz_products에서 해당 카테고리 제품 조회
    2. Gemini 성분 추출 (ingredients 문자열 직접 전달)
    3. 가중치 계산
    4. 시장 분석 리포트 생성
    5. Excel + Slack 응답
    """
    product_db = ProductDBService("CFO")
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    cache = AmzCacheService("CFO")

    try:
        # Step 1: DB에서 제품 조회 (수초)
        raw_products = product_db.get_products_by_category(category_node_id)
        if not raw_products:
            await slack.send_message(response_url, f"⚠️ {category_name} 카테고리에 수집된 제품이 없습니다.")
            return

        products = [BrightDataProduct(**_parse_db_row(r)) for r in raw_products]
        await slack.send_message(
            response_url,
            f"📦 {len(products)}개 제품 로드 완료. 성분 분석 중...",
            ephemeral=True, channel_id=channel_id,
        )

        # Step 2: Gemini 성분 추출 (캐시 우선)
        asins = [p.asin for p in products]
        cached_ingredients = cache.get_ingredient_cache(asins)
        uncached = [p for p in products if p.asin not in cached_ingredients]

        if uncached:
            products_for_gemini = [
                {
                    "asin": p.asin,
                    "title": p.title,
                    "ingredients_raw": p.ingredients,
                    "features": p.features,
                    "additional_details": {},
                }
                for p in uncached
            ]
            new_results = await gemini.extract_ingredients(products_for_gemini)
            if new_results:
                cache.save_ingredient_cache(new_results)
                cache.harmonize_common_names()
            gemini_results = new_results + [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]
        else:
            gemini_results = [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]

        # Step 3: 가중치 계산 (analyzer 재사용, 입력 어댑터 사용)
        search_products, details = _adapt_for_analyzer(products)
        weighted_products, rankings, categories = calculate_weights(
            search_products, details, gemini_results,
        )

        # Step 4-8: 시장 분석 → Excel → Slack (기존 로직 재사용)
        # ... (V3 orchestrator Step 5~8과 동일)

    except Exception as e:
        logger.exception("Analysis failed for category=%s", category_node_id)
        await slack.send_message(response_url, f"❌ 분석 실패: {e!s}")
    finally:
        for client in (gemini, slack):
            try:
                await client.close()
            except Exception:
                pass
```

### 6.6 router.py — Slack 인터랙션

```python
# 기존 /slack/amz 엔드포인트 수정

@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
):
    parts = text.strip().split()
    if not parts:
        return {"response_type": "ephemeral", "text": "사용법: /amz {키워드}"}

    subcommand = parts[0].lower()

    # /amz list — 카테고리 목록
    if subcommand == "list":
        product_db = ProductDBService("CFO")
        categories = product_db.list_categories()
        lines = [f"• {c['name']} (`{c['node_id']}`)" for c in categories]
        return {
            "response_type": "ephemeral",
            "text": f"📋 등록된 카테고리 ({len(categories)}개):\n" + "\n".join(lines),
        }

    # /amz refresh — 수동 수집 트리거
    if subcommand == "refresh":
        background_tasks.add_task(_run_manual_collection)
        return {"response_type": "ephemeral", "text": "🔄 수동 수집 트리거됨. 완료까지 수 분 소요."}

    # /amz {keyword} — 카테고리 검색 → 버튼 제시
    keyword = " ".join(parts)
    product_db = ProductDBService("CFO")
    matches = product_db.search_categories(keyword)

    if not matches:
        return {
            "response_type": "ephemeral",
            "text": f"🔍 \"{keyword}\" 관련 카테고리를 찾을 수 없습니다.\n`/amz list`로 전체 목록을 확인하세요.",
        }

    # Block Kit 버튼으로 카테고리 제시
    buttons = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": m["name"]},
            "action_id": f"amz_category_{m['node_id']}",
            "value": json.dumps({
                "node_id": m["node_id"],
                "name": m["name"],
                "response_url": response_url,
                "channel_id": channel_id,
            }),
        }
        for m in matches[:5]  # 최대 5개
    ]
    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"🔍 *\"{keyword}\"* 관련 카테고리:"},
            },
            {"type": "actions", "elements": buttons},
        ],
    }


# Slack Interactivity endpoint (버튼 콜백)
@router.post("/slack/amz/interact")
async def slack_amz_interact(
    background_tasks: BackgroundTasks,
    payload: str = Form(""),
):
    """Slack Block Kit 버튼 클릭 콜백 처리."""
    data = json.loads(payload)
    actions = data.get("actions", [])
    if not actions:
        return {"text": "No action received"}

    action = actions[0]
    value = json.loads(action["value"])
    node_id = value["node_id"]
    name = value["name"]
    response_url = value["response_url"]
    channel_id = value["channel_id"]

    background_tasks.add_task(
        run_analysis, node_id, name, response_url, channel_id,
    )
    return {
        "response_type": "in_channel",
        "text": f"📊 *{name}* BSR Top 100 분석 시작... (수초~1분 소요)",
    }
```

### 6.7 수집 Job (`jobs/collect.py`)

```python
"""주간 배치 수집 엔트리포인트.

사용법:
  python -m amz_researcher.jobs.collect         # 전체 활성 카테고리
  python -m amz_researcher.jobs.collect 11058281 # 특정 카테고리만
"""
import asyncio
import sys
import logging

from app.config import settings
from amz_researcher.services.bright_data import BrightDataService
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.product_db import ProductDBService

logger = logging.getLogger(__name__)


async def run_collection(category_node_ids: list[str] | None = None):
    """카테고리별 BSR Top 100 수집 → DB 적재."""
    product_db = ProductDBService("CFO")
    collector = DataCollector("CFO")
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )

    try:
        if category_node_ids:
            # 특정 카테고리만
            urls = []
            with MysqlConnector("CFO") as conn:
                for nid in category_node_ids:
                    df = conn.read_query_table(
                        "SELECT url FROM amz_categories WHERE node_id = %s AND is_active = TRUE",
                        (nid,)
                    )
                    if not df.empty:
                        urls.append(df.iloc[0]["url"])
        else:
            urls = product_db.get_all_active_category_urls()

        if not urls:
            logger.warning("No active categories to collect")
            return

        logger.info("Starting collection for %d categories", len(urls))
        products = await bright_data.collect_categories(urls)
        count = collector.process_snapshot(products)
        logger.info("Collection complete: %d products processed", count)

    finally:
        await bright_data.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    node_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(run_collection(node_ids))
```

## 7. Slack 인터랙션 플로우

### 7.1 카테고리 검색 → 선택 → 분석

```
사용자: /amz hair
봇 (ephemeral): 🔍 "hair" 관련 카테고리:
    [Hair Growth Products]  [Hair Loss Shampoos]

사용자: (Hair Growth Products 버튼 클릭)
봇 (in_channel): 📊 Hair Growth Products BSR Top 100 분석 시작... (수초~1분 소요)
봇 (ephemeral): 📦 97개 제품 로드 완료. 성분 분석 중...
봇 (ephemeral): 🧪 성분 추출 중... (캐시 45개, 신규 52개 → Gemini Flash)
봇 (ephemeral): 📊 시장 분석 리포트 생성 중... (Gemini)
봇 (in_channel): [Block Kit 요약 + Excel 첨부]
```

### 7.2 Slack App 설정 변경

| 항목 | 값 |
|------|-----|
| Interactivity Request URL | `https://{domain}/slack/amz/interact` |
| Slash Command `/amz` | `https://{domain}/slack/amz` (기존 유지) |

## 8. 환경 변수 추가

```python
# app/config.py에 추가
BRIGHT_DATA_API_TOKEN: str = ""
BRIGHT_DATA_DATASET_ID: str = "gd_l7q7dkf244hwjntr0"
```

## 9. 마이그레이션 전략 (Phase별 구현 순서)

### Phase 1: 데이터 인프라 (DB + 수집)
1. DB 테이블 생성 (amz_categories, amz_products, amz_products_history, amz_product_categories)
2. 카테고리 시딩
3. `BrightDataService` 구현
4. `DataCollector` 구현
5. `jobs/collect.py` 구현 + 수동 실행 테스트

### Phase 2: 분석 파이프라인 전환
1. `BrightDataProduct` 모델 추가
2. `ProductDBService` 구현
3. `run_analysis()` 구현 (DB 조회 → Gemini → Excel)
4. `analyzer.py` 어댑터 함수 추가 (BrightDataProduct → SearchProduct + ProductDetail)

### Phase 3: Slack 인터랙션 + Browse.ai 제거
1. `router.py` 카테고리 검색/버튼 로직 구현
2. Slack interactivity endpoint 추가
3. `main.py`에 interactivity 라우터 등록
4. Browse.ai 코드 제거 (`browse_ai.py`, `html_parser.py`)
5. V3 캐시 테이블은 당분간 유지 (롤백용)

### Phase 4: 운영 안정화 (향후)
1. Cron job 설정 (주 1회)
2. 수집 실패 알림 (Slack DM)
3. `amz_products_history` 기반 트렌드 기능

## 10. 에러 처리

| 시나리오 | 처리 |
|---------|------|
| Bright Data API 호출 실패 | 재시도 1회 → 실패 시 관리자 Slack DM |
| 폴링 타임아웃 (5분) | TimeoutError → 관리자 알림 |
| DB 적재 실패 | 로깅 + 관리자 알림, 다음 수집 시 재시도 |
| 카테고리 검색 0건 | "카테고리를 찾을 수 없습니다" + list 안내 |
| 제품 0건 (미수집 카테고리) | "수집된 제품이 없습니다" + refresh 안내 |
| Gemini 추출 실패 | V3 동일 (캐시 + 재시도) |

## 11. Success Criteria (검증 항목)

| # | 항목 | 검증 방법 |
|---|------|----------|
| 1 | Bright Data API 수집 동작 | `jobs/collect.py` 수동 실행 → amz_products 행 확인 |
| 2 | 카테고리별 BSR Top 100 적재 | SQL: `SELECT COUNT(*) FROM amz_product_categories WHERE category_node_id = '11058281'` |
| 3 | `/amz {keyword}` 응답 5초 이내 | Slack에서 버튼 표시까지 시간 측정 |
| 4 | 카테고리 선택 → 분석 완료 | 버튼 클릭 → Excel 첨부 메시지 도착 |
| 5 | Browse.ai 코드 완전 제거 | `grep -r "browse_ai\|BrowseAi" amz_researcher/` 결과 0건 |
| 6 | 시계열 데이터 누적 | `SELECT COUNT(DISTINCT snapshot_date) FROM amz_products_history` |
| 7 | Slack interactivity 동작 | 버튼 클릭 시 분석 시작 메시지 표시 |
