# Design: Amazon Researcher V2 — 데이터 구조 변경 + MySQL 캐시 전략

> Plan: `docs/01-plan/features/amazon-researcher-v2.plan.md`
> Browse.ai 실제 응답 샘플: `/tmp/browse_ai_detail_response.json`

---

## 1. File Structure (변경사항만)

```
amz_researcher/
├── models.py                        # ← 수정: ProductDetail v2
├── router.py                        # ← 수정: /amz prod 서브커맨드 + --refresh
├── orchestrator.py                  # ← 수정: 캐시 전략 적용
└── services/
    ├── browse_ai.py                 # ← 수정: capturedTexts 신규 필드 파싱
    ├── html_parser.py               # ← 신규: HTML 테이블 → dict 파서
    ├── cache.py                     # ← 신규: MySQL 캐시 서비스
    ├── analyzer.py                  # ← 수정: Volume→BSR 가중치 변경
    ├── gemini.py                    # ← 수정: ingredients_raw 활용
    ├── excel_builder.py             # ← 수정: BSR 컬럼, Raw 시트 변경
    ├── checkpoint.py                # ← 제거: MySQL 캐시로 대체
    └── slack_sender.py              # 변경 없음
```

---

## 2. Data Models (`amz_researcher/models.py`)

### 변경 없는 모델

`SearchProduct`, `Ingredient`, `ProductIngredients`, `GeminiResponse`, `IngredientRanking`, `CategorySummary` — 기존 유지.

### 변경 모델

```python
class ProductDetail(BaseModel):
    """Browse.ai 상세 크롤링 결과 (V2 — capturedTexts 신규 필드)"""
    asin: str
    # 전성분 원문 (plain text, 쉼표 구분)
    ingredients_raw: str = ""
    # HTML 파싱 결과 (key-value dict, 카테고리마다 키가 다름)
    features: dict = {}         # {"Product Benefits": "Frizz Control", "Hair Type": "All", ...}
    measurements: dict = {}     # {"Liquid Volume": "100 Milliliters", ...}
    item_details: dict = {}     # {"Brand Name": "MAREE", "GTIN": "...", ...}
    additional_details: dict = {}  # {"Material Type Free": "Mineral Oil Free, ..."}
    # item_details에서 추출한 핵심 필드
    bsr_category: int | None = None       # 전체 카테고리 BSR (예: 581)
    bsr_subcategory: int | None = None    # 서브카테고리 BSR (예: 1)
    bsr_category_name: str = ""           # "Beauty & Personal Care"
    bsr_subcategory_name: str = ""        # "Hair Styling Serums"
    rating: float | None = None           # 상세 페이지 별점 (예: 4.6)
    review_count: int | None = None       # 상세 페이지 리뷰 수 (예: 1285)
    brand: str = ""
    manufacturer: str = ""
    product_url: str = ""


class WeightedProduct(BaseModel):
    """가중치 계산 완료된 제품 (V2 — BSR 기반)"""
    asin: str
    title: str
    position: int
    price: float | None = None
    reviews: int = 0
    rating: float = 0.0
    bsr_category: int | None = None       # Volume 대신 BSR
    bsr_subcategory: int | None = None
    composite_weight: float = 0.0
    ingredients: list[Ingredient] = []
```

### 삭제 필드

`ProductDetail`에서 제거: `title`, `top_highlights`, `features(str)`, `measurements(str)`, `bsr(str)`, `volume_raw`, `volume`

`WeightedProduct`에서 제거: `volume` → `bsr_category`, `bsr_subcategory` 추가

---

## 3. HTML Parser (`amz_researcher/services/html_parser.py`) — 신규

Browse.ai가 반환하는 아마존 `prodDetTable` HTML을 파싱하는 유틸리티.

### 의존성

`beautifulsoup4` 추가 필요 (`pyproject.toml`에 추가).

> 정규식만으로 가능하나, `<td>` 내부에 `<ul>`, `<div>`, `<span>` 등 중첩 HTML이 있는 `item_details`의 BSR/Reviews 셀 처리 시 BS4가 안정적.

### Public Interface

```python
def parse_product_table(html: str) -> dict[str, str]:
    """아마존 prodDetTable HTML → {key: value} dict.

    일반 셀: <th>key</th><td>value</td> → strip 후 dict에 추가
    Best Sellers Rank, Customer Reviews: 별도 핸들러로 처리

    Args:
        html: capturedTexts의 features/measurements/item_details/details 값
    Returns:
        {"Product Benefits": "Frizz Control", "Hair Type": "All", ...}
    """


def parse_bsr(html: str) -> list[dict]:
    """item_details HTML에서 Best Sellers Rank 파싱.

    <li> 태그에서 #N in Category 패턴 추출.

    Returns:
        [{"rank": 581, "category": "Beauty & Personal Care"},
         {"rank": 1, "category": "Hair Styling Serums"}]
    """


def parse_customer_reviews(html: str) -> tuple[float | None, int | None]:
    """item_details HTML에서 별점/리뷰 수 파싱.

    파싱 우선순위:
    1. title="X.X out of 5 stars" → rating
    2. aria-label="N Reviews" → review_count
    3. 텍스트 "(1,285)" → review_count fallback

    Returns:
        (rating, review_count) — 파싱 실패 시 (None, None)
    """
```

### 내부 구현 전략

```python
from bs4 import BeautifulSoup
import re

def parse_product_table(html: str) -> dict[str, str]:
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for row in soup.select("table.prodDetTable tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        key = th.get_text(strip=True)
        # 특수 셀 스킵 (별도 핸들러 사용)
        if key in ("Best Sellers Rank", "Customer Reviews"):
            continue
        value = td.get_text(strip=True)
        result[key] = value
    return result


def parse_bsr(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    # Best Sellers Rank의 <td> 찾기
    for row in soup.select("table.prodDetTable tr"):
        th = row.find("th")
        if th and "Best Sellers Rank" in th.get_text():
            td = row.find("td")
            if not td:
                return []
            results = []
            for li in td.select("li"):
                text = li.get_text()
                m = re.search(r"#([\d,]+)\s+in\s+(.+?)(?:\s*\(|$)", text)
                if m:
                    rank = int(m.group(1).replace(",", ""))
                    category = m.group(2).strip()
                    results.append({"rank": rank, "category": category})
            return results
    return []


def parse_customer_reviews(html: str) -> tuple[float | None, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    rating = None
    review_count = None

    # rating: title="X.X out of 5 stars"
    star_el = soup.find(attrs={"title": re.compile(r"out of 5 stars")})
    if star_el:
        m = re.search(r"([\d.]+)\s+out of", star_el["title"])
        if m:
            rating = float(m.group(1))

    # review_count: aria-label="N Reviews"
    review_el = soup.find(attrs={"aria-label": re.compile(r"Reviews")})
    if review_el:
        m = re.search(r"([\d,]+)", review_el["aria-label"])
        if m:
            review_count = int(m.group(1).replace(",", ""))

    return rating, review_count
```

---

## 4. Browse.ai Service 변경 (`amz_researcher/services/browse_ai.py`)

### 변경 범위

`run_detail`, `run_details_batch` 내부 파싱만 변경. API 호출/polling 로직은 그대로.

### AS-IS → TO-BE 파싱

```python
# AS-IS (기존)
texts = task.get("capturedTexts", {})
ProductDetail(
    asin=asin,
    title=texts.get("title") or "",
    top_highlights=texts.get("top_highlights") or "",
    features=texts.get("features") or "",
    measurements=texts.get("measurements") or "",
    bsr=texts.get("bsr") or "",
    volume_raw=texts.get("volumn") or "",
    volume=parse_volume(texts.get("volumn") or ""),
)
```

```python
# TO-BE (V2)
from amz_researcher.services.html_parser import (
    parse_product_table, parse_bsr, parse_customer_reviews,
)

def parse_detail_from_captured_texts(asin: str, texts: dict) -> ProductDetail:
    """capturedTexts dict → ProductDetail 변환.

    _STATUS, _PREV_* 필드는 무시.
    """
    # 1. ingredients: plain text → 그대로 저장
    ingredients_raw = texts.get("ingredients") or ""

    # 2. features/measurements/details: HTML → dict
    features = parse_product_table(texts.get("features") or "")
    measurements = parse_product_table(texts.get("measurements") or "")
    additional_details = parse_product_table(texts.get("details") or "")

    # 3. item_details: HTML → dict + BSR/Reviews 특수 파싱
    item_details_html = texts.get("item_details") or ""
    item_details = parse_product_table(item_details_html)
    bsr_list = parse_bsr(item_details_html)
    rating, review_count = parse_customer_reviews(item_details_html)

    # BSR: 첫 번째 = 전체 카테고리, 두 번째 = 서브카테고리
    bsr_category = bsr_list[0]["rank"] if len(bsr_list) > 0 else None
    bsr_category_name = bsr_list[0]["category"] if len(bsr_list) > 0 else ""
    bsr_subcategory = bsr_list[1]["rank"] if len(bsr_list) > 1 else None
    bsr_subcategory_name = bsr_list[1]["category"] if len(bsr_list) > 1 else ""

    # item_details dict에 bsr/reviews 정보도 추가 (JSON 컬럼 저장용)
    if bsr_list:
        item_details["bsr"] = bsr_list
    if rating is not None:
        item_details["rating"] = rating
    if review_count is not None:
        item_details["review_count"] = review_count

    return ProductDetail(
        asin=asin,
        ingredients_raw=ingredients_raw,
        features=features,
        measurements=measurements,
        item_details=item_details,
        additional_details=additional_details,
        bsr_category=bsr_category,
        bsr_subcategory=bsr_subcategory,
        bsr_category_name=bsr_category_name,
        bsr_subcategory_name=bsr_subcategory_name,
        rating=rating,
        review_count=review_count,
        brand=item_details.get("Brand Name", ""),
        manufacturer=item_details.get("Manufacturer", ""),
        product_url=f"https://www.amazon.com/dp/{asin}",
    )
```

### `run_details_batch` 변경

```python
# 기존 코드에서 ProductDetail 생성 부분만 교체
for task in raw_tasks:
    if task.get("status") != "successful":
        continue
    try:
        texts = task.get("capturedTexts", {})
        input_url = task.get("inputParameters", {}).get("originUrl", "")
        asin = extract_asin(input_url)
        if not asin:
            continue
        details.append(parse_detail_from_captured_texts(asin, texts))
    except Exception:
        logger.exception("Failed to parse bulk task: %s", task.get("id"))
```

### Robot ID 수정

```python
# config.py의 값이 아닌, 실제 확인된 Robot ID 반영 필요
# Search: 019cbd49-85aa-72bb-b5f5-ae97a1caabe0
# Detail: 019cbd6a-4448-7b63-acca-869c3a13afea
```

### 삭제 대상 함수

`parse_volume()` — 더 이상 사용되지 않음.

---

## 5. MySQL Cache Service (`amz_researcher/services/cache.py`) — 신규

### 의존성

`lib/mysql_connector.py`의 `MysqlConnector("CFO")` 사용. 추가 패키지 없음.

### Public Interface

```python
import json
import logging
from datetime import datetime, timedelta

import pandas as pd

from amz_researcher.models import ProductDetail, SearchProduct
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 30


class AmzCacheService:
    """MySQL 기반 Amazon 데이터 캐시 서비스."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    # ── Search Cache ─────────────────────────────────

    def get_search_cache(self, keyword: str) -> list[SearchProduct] | None:
        """30일 이내 검색 캐시 조회.

        Returns:
            캐시 존재 시 SearchProduct 리스트, 없으면 None
        """
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        query = (
            "SELECT * FROM amz_search_cache "
            "WHERE keyword = %s AND searched_at >= %s "
            "ORDER BY position"
        )
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query, (keyword, cutoff))
        if df.empty:
            return None
        return [
            SearchProduct(
                position=row["position"],
                title=row["title"],
                asin=row["asin"],
                price=float(row["price"]) if row["price"] else None,
                price_raw=row["price_raw"],
                reviews=int(row["reviews"]),
                reviews_raw=row["reviews_raw"],
                rating=float(row["rating"]),
                sponsored=bool(row["sponsored"]),
                product_link=row["product_link"],
            )
            for _, row in df.iterrows()
        ]

    def save_search_cache(self, keyword: str, products: list[SearchProduct]) -> None:
        """검색 결과를 캐시에 저장 (upsert)."""
        if not products:
            return
        rows = []
        now = datetime.now()
        for p in products:
            rows.append({
                "keyword": keyword,
                "asin": p.asin,
                "position": p.position,
                "title": p.title,
                "price": p.price,
                "price_raw": p.price_raw,
                "reviews": p.reviews,
                "reviews_raw": p.reviews_raw,
                "rating": p.rating,
                "sponsored": int(p.sponsored),
                "product_link": p.product_link,
                "searched_at": now,
            })
        df = pd.DataFrame(rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df, "amz_search_cache")
        logger.info("Search cache saved: keyword=%s, %d products", keyword, len(products))

    # ── Product Detail Cache ─────────────────────────

    def get_detail_cache(self, asins: list[str]) -> dict[str, ProductDetail]:
        """30일 이내 상세 캐시 조회.

        Args:
            asins: 조회할 ASIN 리스트
        Returns:
            {asin: ProductDetail} dict (캐시에 있는 것만)
        """
        if not asins:
            return {}
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        placeholders = ",".join(["%s"] * len(asins))
        query = (
            f"SELECT * FROM amz_product_detail "
            f"WHERE asin IN ({placeholders}) AND crawled_at >= %s"
        )
        params = (*asins, cutoff)
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query, params)
        result = {}
        for _, row in df.iterrows():
            result[row["asin"]] = ProductDetail(
                asin=row["asin"],
                ingredients_raw=row["ingredients_raw"] or "",
                features=json.loads(row["features"]) if row["features"] else {},
                measurements=json.loads(row["measurements"]) if row["measurements"] else {},
                item_details=json.loads(row["item_details"]) if row["item_details"] else {},
                additional_details=json.loads(row["additional_details"]) if row["additional_details"] else {},
                bsr_category=int(row["bsr_category"]) if row["bsr_category"] is not None else None,
                bsr_subcategory=int(row["bsr_subcategory"]) if row["bsr_subcategory"] is not None else None,
                bsr_category_name=row["bsr_category_name"] or "",
                bsr_subcategory_name=row["bsr_subcategory_name"] or "",
                rating=float(row["rating"]) if row["rating"] is not None else None,
                review_count=int(row["review_count"]) if row["review_count"] is not None else None,
                brand=row["brand"] or "",
                manufacturer=row["manufacturer"] or "",
            )
        return result

    def save_detail_cache(self, details: list[ProductDetail]) -> None:
        """상세 정보를 캐시에 저장 (upsert)."""
        if not details:
            return
        rows = []
        now = datetime.now()
        for d in details:
            rows.append({
                "asin": d.asin,
                "ingredients_raw": d.ingredients_raw,
                "features": json.dumps(d.features, ensure_ascii=False),
                "measurements": json.dumps(d.measurements, ensure_ascii=False),
                "item_details": json.dumps(d.item_details, ensure_ascii=False),
                "additional_details": json.dumps(d.additional_details, ensure_ascii=False),
                "bsr_category": d.bsr_category,
                "bsr_subcategory": d.bsr_subcategory,
                "bsr_category_name": d.bsr_category_name,
                "bsr_subcategory_name": d.bsr_subcategory_name,
                "rating": d.rating,
                "review_count": d.review_count,
                "brand": d.brand,
                "manufacturer": d.manufacturer,
                "crawled_at": now,
            })
        df = pd.DataFrame(rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df, "amz_product_detail")
        logger.info("Detail cache saved: %d products", len(details))
```

---

## 6. Analyzer 변경 (`amz_researcher/services/analyzer.py`)

### 가중치 공식 변경

```python
def _compute_composite_weight(
    position: int, reviews: int, rating: float, bsr_category: int | None,
    max_position: int, max_reviews: int, max_bsr: int,
) -> float:
    """Weight = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)"""
    pos_norm = 1 - (position - 1) / max_position if max_position > 0 else 0
    rev_norm = reviews / max_reviews if max_reviews > 0 else 0
    rat_norm = rating / 5.0
    # BSR: 낮을수록 좋음. None이면 최하위(max_bsr + 1) 취급
    bsr = bsr_category if bsr_category is not None else (max_bsr + 1)
    bsr_norm = 1 - (bsr - 1) / max_bsr if max_bsr > 0 else 0
    bsr_norm = max(bsr_norm, 0)  # 음수 방지 (max_bsr+1 입력 시)
    return pos_norm * 0.2 + rev_norm * 0.25 + rat_norm * 0.15 + bsr_norm * 0.4
```

### `calculate_weights` 시그니처 변경

```python
def calculate_weights(
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    gemini_results: list[ProductIngredients],
) -> tuple[list[WeightedProduct], list[IngredientRanking], list[CategorySummary]]:
    detail_map = {d.asin: d for d in details}
    ingredient_map = {g.asin: g.ingredients for g in gemini_results}

    max_position = max((p.position for p in search_products), default=1)
    max_reviews = max((p.reviews for p in search_products), default=1)

    # BSR: detail에서 가져오되, None 제외한 최대값
    bsr_values = [
        detail_map[p.asin].bsr_category
        for p in search_products
        if p.asin in detail_map and detail_map[p.asin].bsr_category is not None
    ]
    max_bsr = max(bsr_values) if bsr_values else 1

    weighted_products = []
    for sp in search_products:
        detail = detail_map.get(sp.asin)
        bsr_category = detail.bsr_category if detail else None
        bsr_subcategory = detail.bsr_subcategory if detail else None
        # rating: 상세 페이지 별점 우선, 없으면 검색 결과 별점
        rating = (detail.rating if detail and detail.rating else sp.rating)

        weight = _compute_composite_weight(
            sp.position, sp.reviews, rating, bsr_category,
            max_position, max_reviews, max_bsr,
        )

        weighted_products.append(WeightedProduct(
            asin=sp.asin,
            title=sp.title,
            position=sp.position,
            price=sp.price,
            reviews=sp.reviews,
            rating=rating,
            bsr_category=bsr_category,
            bsr_subcategory=bsr_subcategory,
            composite_weight=weight,
            ingredients=ingredient_map.get(sp.asin, []),
        ))

    weighted_products.sort(key=lambda p: p.composite_weight, reverse=True)
    rankings = _aggregate_ingredients(weighted_products)
    categories = _aggregate_categories(rankings, weighted_products)
    return weighted_products, rankings, categories
```

---

## 7. Gemini Service 변경 (`amz_researcher/services/gemini.py`)

### 입력 데이터 변경

기존: `top_highlights + features` (텍스트)
V2: `ingredients_raw` (INCI 전성분) + `features` dict + `additional_details` dict

```python
# orchestrator에서 Gemini에 전달하는 데이터 구성
products_for_gemini = [
    {
        "asin": d.asin,
        "ingredients_raw": d.ingredients_raw,
        "features": d.features,           # dict
        "additional_details": d.additional_details,  # dict
    }
    for d in details
]
```

### 프롬프트 변경

```python
PROMPT_TEMPLATE = """아래는 아마존에서 수집한 제품 목록이다.
각 제품에는 INCI 전성분 리스트와 제품 특성 정보가 포함되어 있다.

작업:
1. INCI 전성분에서 마케팅적으로 강조할 만한 핵심 성분을 선별하라.
2. 제품 특성(features, additional_details)도 참고하여 성분의 맥락을 파악하라.

규칙:
1. 성분명은 영문 표준명으로 통일 (예: 아르간오일 → Argan Oil)
2. 같은 성분의 다른 이름은 가장 널리 쓰이는 이름으로 통일
   (예: Vitamin B7 = Biotin → "Biotin", Tocopherol = Vitamin E → "Vitamin E")
3. 각 성분에 카테고리 부여:
   Natural Oil / Essential Oil / Vitamin / Protein / Peptide /
   Active/Functional / Hair Growth Complex / Silicone / Botanical /
   Pharmaceutical / Humectant / Other
4. 용매(Water), 방부제(Phenoxyethanol), 향료(Fragrance/Parfum) 등 기본 성분은 제외
5. 화학적으로 식별 가능한 물질만 추출
6. JSON만 출력:

{{
  "products": [
    {{
      "asin": "제품ASIN",
      "ingredients": [
        {{"name": "Argan Oil", "category": "Natural Oil"}}
      ]
    }}
  ]
}}

제품 목록:
{products_json}"""
```

---

## 8. Excel Builder 변경 (`amz_researcher/services/excel_builder.py`)

### Sheet 1: Ingredient Ranking

부제목 변경:
```
AS-IS: Weight = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
TO-BE: Weight = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)
```

### Sheet 3: Product Detail

| 변경 | AS-IS | TO-BE |
|------|-------|-------|
| 7번 컬럼 | Volume | BSR (Category) |
| 8번 컬럼 | Composite Weight | BSR (Sub) |
| 9번 컬럼 | Ingredients Found | Composite Weight |
| 10번 컬럼 | - | Ingredients Found |

```python
headers = [
    "ASIN", "Title", "Position", "Price", "Reviews",
    "Rating", "BSR (Category)", "BSR (Sub)", "Composite Weight", "Ingredients Found",
]
```

### Sheet 5: Raw - Product Detail (전면 변경)

기존 8컬럼 → 10컬럼:

```python
headers = [
    "ASIN", "Brand", "BSR Category", "BSR Subcategory",
    "Rating", "Reviews", "Ingredients (raw)",
    "Features", "Measurements", "Additional Details",
]
```

- `Features`, `Measurements`, `Additional Details`: dict를 `"key: value"` 줄바꿈 문자열로 변환
- `Ingredients (raw)`: 전성분 텍스트 그대로

```python
def _dict_to_text(d: dict) -> str:
    """{"Hair Type": "All", ...} → "Hair Type: All\nItem Form: Oil" """
    return "\n".join(f"{k}: {v}" for k, v in d.items())
```

---

## 9. Orchestrator 변경 (`amz_researcher/orchestrator.py`)

### 전체 파이프라인 (V2)

```python
async def run_research(
    keyword: str, response_url: str, channel_id: str,
    refresh: bool = False,
):
    browse = BrowseAiService(
        api_key=settings.BROWSE_AI_API_KEY,
        search_robot_id=settings.AMZ_SEARCH_ROBOT_ID,
        detail_robot_id=settings.AMZ_DETAIL_ROBOT_ID,
    )
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    cache = AmzCacheService("CFO")

    try:
        # Step 1: Search (캐시 우선)
        search_products = None
        if not refresh:
            search_products = cache.get_search_cache(keyword)
        if search_products:
            logger.info("Search cache hit: %d products", len(search_products))
            await slack.send_message(
                response_url,
                f"♻️ 캐시 사용: {len(search_products)}개 제품. 상세 정보 확인 중...",
                ephemeral=True,
            )
        else:
            search_products = await browse.run_search(keyword)
            cache.save_search_cache(keyword, search_products)
            await slack.send_message(
                response_url,
                f"✅ 검색 완료: {len(search_products)}개 제품. 상세 크롤링 시작...",
                ephemeral=True,
            )

        # Step 2: Detail (캐시 우선, 미캐시 ASIN만 크롤링)
        asins = [p.asin for p in search_products]
        cached_details = {}
        if not refresh:
            cached_details = cache.get_detail_cache(asins)
        uncached_asins = [a for a in asins if a not in cached_details]

        if uncached_asins:
            new_details = await browse.run_details_batch(uncached_asins)
            cache.save_detail_cache(new_details)
            all_details = list(cached_details.values()) + new_details
            await slack.send_message(
                response_url,
                f"📦 상세 정보: 캐시 {len(cached_details)}개 + 신규 {len(new_details)}개",
                ephemeral=True,
            )
        else:
            all_details = list(cached_details.values())
            await slack.send_message(
                response_url,
                f"♻️ 상세 정보 전체 캐시 사용: {len(all_details)}개",
                ephemeral=True,
            )

        # Step 3: Gemini 성분 추출
        await slack.send_message(response_url, "🧪 성분 추출 중... (Gemini Flash)", ephemeral=True)
        products_for_gemini = [
            {
                "asin": d.asin,
                "ingredients_raw": d.ingredients_raw,
                "features": d.features,
                "additional_details": d.additional_details,
            }
            for d in all_details
        ]
        gemini_results = await gemini.extract_ingredients(products_for_gemini)

        # Step 4: Weight calculation
        weighted_products, rankings, categories = calculate_weights(
            search_products, all_details, gemini_results,
        )

        # Step 5~7: Excel + Slack (기존과 동일)
        excel_bytes = build_excel(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
        )
        summary = _build_summary(keyword, len(weighted_products), rankings[:10])
        await slack.send_message(response_url, summary)

        filename = f"{keyword.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, filename,
            comment="📊 상세 분석 엑셀 파일",
        )
        logger.info("Research completed for keyword=%s", keyword)

    except Exception as e:
        logger.exception("Research failed for keyword=%s", keyword)
        await slack.send_message(
            response_url, f"❌ *{keyword}* 분석 실패: {e!s}",
            ephemeral=True,
        )
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Research 에러 발생\n키워드: {keyword}\n에러: {e!s}",
            )
    finally:
        await browse.close()
        await gemini.close()
        await slack.close()
```

### `_build_summary` 변경

```python
# 부제 변경
f"Score = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)\n"
```

### checkpoint.py 제거

MySQL 캐시로 완전 대체. `import`문 및 `ckpt` 관련 코드 모두 제거.

---

## 10. Router 변경 (`amz_researcher/router.py`)

### 서브커맨드 파싱

```python
@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    parts = text.strip().split()
    if not parts:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz prod {키워드} (예: /amz prod hair serum)",
        }

    subcommand = parts[0].lower()
    if subcommand != "prod":
        return {
            "response_type": "ephemeral",
            "text": f"알 수 없는 명령: {subcommand}\n사용법: /amz prod {{키워드}}",
        }

    refresh = "--refresh" in parts
    keyword_parts = [p for p in parts[1:] if p != "--refresh"]
    keyword = " ".join(keyword_parts).strip()
    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz prod {키워드} [--refresh]",
        }

    background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh)
    cache_msg = " (캐시 무시)" if refresh else ""
    return {
        "response_type": "in_channel",
        "text": f"🔍 *{keyword}* 분석 시작{cache_msg}. 약 10~15분 소요됩니다.",
    }
```

### 테스트 엔드포인트 변경

```python
class ResearchRequest(BaseModel):
    keyword: str
    response_url: str = ""
    channel_id: str = ""
    refresh: bool = False       # ← 추가

@router.post("/research")
async def research_test(
    background_tasks: BackgroundTasks,
    req: ResearchRequest,
):
    keyword = req.keyword.strip()
    if not keyword:
        return {"error": "keyword is required"}
    background_tasks.add_task(
        run_research, keyword, req.response_url, req.channel_id, req.refresh,
    )
    return {"status": "started", "keyword": keyword, "refresh": req.refresh}
```

---

## 11. DDL Scripts

### 테이블 생성

```sql
-- amz_search_cache
CREATE TABLE IF NOT EXISTS amz_search_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    position INT NOT NULL,
    title VARCHAR(500) DEFAULT '',
    price DECIMAL(10,2) DEFAULT NULL,
    price_raw VARCHAR(50) DEFAULT '',
    reviews INT DEFAULT 0,
    reviews_raw VARCHAR(50) DEFAULT '',
    rating DECIMAL(3,2) DEFAULT 0.00,
    sponsored TINYINT(1) DEFAULT 0,
    product_link VARCHAR(1000) DEFAULT '',
    searched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_keyword_asin (keyword, asin),
    INDEX idx_keyword_searched (keyword, searched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- amz_product_detail
CREATE TABLE IF NOT EXISTS amz_product_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    asin VARCHAR(20) NOT NULL,
    ingredients_raw TEXT,
    features JSON,
    measurements JSON,
    item_details JSON,
    additional_details JSON,
    bsr_category INT DEFAULT NULL,
    bsr_subcategory INT DEFAULT NULL,
    bsr_category_name VARCHAR(200) DEFAULT '',
    bsr_subcategory_name VARCHAR(200) DEFAULT '',
    rating DECIMAL(3,2) DEFAULT NULL,
    review_count INT DEFAULT NULL,
    brand VARCHAR(200) DEFAULT '',
    manufacturer VARCHAR(200) DEFAULT '',
    crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_asin (asin),
    INDEX idx_crawled_at (crawled_at),
    INDEX idx_bsr_category (bsr_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 12. Dependencies 변경

`pyproject.toml`에 추가:

```
beautifulsoup4>=4.12.0
```

기존 의존성 유지: `httpx`, `openpyxl`, `pymysql`, `pandas`, `pydantic-settings`

---

## 13. Sequence Diagram (V2)

```
Slack User     Router      Orchestrator    Cache(MySQL)    BrowseAi     Gemini
    |             |              |              |              |           |
    |--/amz prod->|              |              |              |           |
    |<--200 OK----|              |              |              |           |
    |             |--run_research(refresh=F)--->|              |           |
    |             |              |--get_search-->|              |           |
    |             |              |<--cache hit---|              |           |
    |             |              |              (or)            |           |
    |             |              |<--None--------|              |           |
    |             |              |--run_search------------------>|           |
    |             |              |<--products--------------------|           |
    |             |              |--save_search->|              |           |
    |             |              |              |              |           |
    |             |              |--get_detail(asins)---------->|           |
    |             |              |<--cached:{A,B}, miss:{C,D}--|           |
    |             |              |--run_details_batch({C,D})---->|           |
    |             |              |<--new details----------------|           |
    |             |              |--save_detail->|              |           |
    |             |              |              |              |           |
    |             |              |--extract_ingredients--------------------->|
    |             |              |<--gemini_results--------------------------|
    |             |              |              |              |           |
    |             |              |--[analyze + excel]          |           |
    |             |              |--[slack summary + file upload]           |
```

---

## 14. Implementation Order

| Phase | 파일 | 작업 | 의존성 |
|-------|------|------|--------|
| 1 | SQL | DDL 실행 (CFO DB) | 없음 |
| 2 | `pyproject.toml` | `beautifulsoup4` 추가 | 없음 |
| 3 | `models.py` | ProductDetail v2, WeightedProduct v2 | 없음 |
| 4 | `services/html_parser.py` | 신규: parse_product_table, parse_bsr, parse_customer_reviews | Phase 2 |
| 5 | `services/browse_ai.py` | parse_detail_from_captured_texts, run_detail/batch 파싱 교체 | Phase 3, 4 |
| 6 | `services/cache.py` | 신규: AmzCacheService | Phase 3 |
| 7 | `services/analyzer.py` | 가중치 공식 변경 (BSR 40%) | Phase 3 |
| 8 | `services/gemini.py` | 프롬프트 + 입력 데이터 변경 | Phase 3 |
| 9 | `services/excel_builder.py` | 컬럼 변경, Raw 시트 구조 변경 | Phase 3, 7 |
| 10 | `orchestrator.py` | 캐시 전략 적용, checkpoint 제거 | Phase 5, 6, 7, 8 |
| 11 | `router.py` | /amz prod 서브커맨드, --refresh | Phase 10 |
| 12 | `services/checkpoint.py` | 삭제 | Phase 10 |

---

## 15. Error Handling Matrix

| Location | Error | Action |
|----------|-------|--------|
| `html_parser.py` | HTML 파싱 실패 | 로그에 HTML 원본 출력, 빈 dict 반환 |
| `html_parser.py` | BSR 패턴 매칭 실패 | 빈 리스트 반환, bsr_category = None |
| `html_parser.py` | Reviews 파싱 실패 | (None, None) 반환 |
| `cache.py` | MySQL 연결 실패 | 로그 경고 후 None 반환 → browse.ai 직접 호출 (fallback) |
| `cache.py` | upsert 실패 | 로그 에러, 분석은 계속 진행 |
| `browse_ai.py` | capturedTexts 키 누락 | `texts.get(key) or ""` → 빈 문자열 처리 |
| `analyzer.py` | BSR 전부 None | max_bsr = 1 기본값, 모든 제품 BSR 가중치 0 |
| `router.py` | 알 수 없는 서브커맨드 | ephemeral 에러 메시지 반환 |
