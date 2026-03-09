# Amazon Researcher V5 Design Document

> **Summary**: V4 수집 데이터의 분석 활용도를 60%에서 95%로 끌어올리는 분석 고도화
>
> **Project**: webhook-service (amz_researcher)
> **Version**: V5
> **Author**: CTO Lead
> **Date**: 2026-03-09
> **Status**: Draft
> **Planning Doc**: [amazon-researcher-v5.plan.md](../01-plan/features/amazon-researcher-v5.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. 죽은 코드 제거로 분석 파이프라인 정리 (Phase 0)
2. 미활용 데이터 5종(customer_says, badge, discount, title keywords, AI report 확장) 즉시 분석 (Phase 1)
3. 심화 분석 6종(unit_price, manufacturer, variations, SNS 심화, 통계 검증, Excel 확장) 추가 (Phase 2)
4. 기존 파이프라인 구조를 최대한 유지하며 확장 (market_analyzer.py 중심)

### 1.2 Design Principles

- **기존 패턴 준수**: 모든 신규 분석 함수는 `analyze_*()` 네이밍, `list[WeightedProduct]` 입력, `dict` 반환
- **Zero-cost 확장**: Gemini 추가 호출 없이 키워드 사전 기반 분석 (customer_says, title)
- **점진적 배포**: Phase 0 -> 1 -> 2 순서로 각 Phase가 독립적으로 동작 가능
- **통계적 엄밀성**: Phase 2에서 scipy 기반 유의성 검증 추가

---

## 2. Architecture

### 2.1 Data Flow (현재 V4)

```
DB (amz_products) -> BrightDataProduct -> _adapt_for_analyzer()
  -> SearchProduct + ProductDetail
  -> calculate_weights() -> WeightedProduct[]
  -> build_market_analysis() -> analysis_data (dict)
  -> generate_market_report() -> market_report (str)
  -> build_excel() -> Excel bytes
```

### 2.2 V5 변경 범위

```
                          [변경 없음]
DB -> BrightDataProduct -> _adapt_for_analyzer() -> calculate_weights()
                                                          |
                    [변경] WeightedProduct 필드 추가       |
                    (badge, initial_price, manufacturer,   |
                     variations_count)                     v
                                                   WeightedProduct[]
                                                          |
              [대폭 변경] build_market_analysis()          |
              ├─ 기존 8개 분석 유지                        |
              ├─ 1개 제거 (competition)                    |
              ├─ 1개 수정 (promotions: plus_content 제거)  |
              └─ 7개 신규 추가                             v
                                                   analysis_data (dict)
                                                          |
              [변경] MARKET_REPORT_PROMPT                  |
              (10개 데이터 소스로 확장)                     v
                                                   market_report (str)
                                                          |
              [변경] build_excel()                         |
              (Consumer Voice, Badge Analysis 시트 추가)   v
                                                   Excel bytes
```

### 2.3 영향 받는 파일

| 파일 | 변경 유형 | Phase |
|------|-----------|:-----:|
| `amz_researcher/models.py` | 수정 — WeightedProduct 필드 추가 | 0 |
| `amz_researcher/services/market_analyzer.py` | 대폭 수정 — 7개 함수 추가, 1개 제거, 2개 수정 | 0, 1, 2 |
| `amz_researcher/services/gemini.py` | 수정 — MARKET_REPORT_PROMPT 확장 | 1 |
| `amz_researcher/orchestrator.py` | 수정 — WeightedProduct 필드 주입 확장 | 1 |
| `amz_researcher/services/excel_builder.py` | 수정 — 2개 시트 추가, Product Detail 컬럼 추가 | 2 |

---

## 3. Model Changes (WeightedProduct)

### 3.1 필드 추가

```python
class WeightedProduct(BaseModel):
    asin: str
    title: str
    position: int
    price: float | None = None
    reviews: int = 0
    rating: float = 0.0
    bsr_category: int | None = None
    bsr_subcategory: int | None = None
    composite_weight: float = 0.0
    ingredients: list[Ingredient] = []
    # V4 확장 필드
    bought_past_month: int | None = None
    brand: str = ""
    sns_price: float | None = None
    unit_price: str = ""
    number_of_sellers: int = 1   # Phase 0에서 제거 예정 (사용처 없음)
    coupon: str = ""
    plus_content: bool = False   # Phase 0에서 제거 예정 (사용처 없음)
    customer_says: str = ""
    # V5 신규 필드
    badge: str = ""                        # "Amazon's Choice", "#1 Best Seller" 등
    initial_price: float | None = None     # 할인 전 원가
    manufacturer: str = ""                 # 제조사 (OEM)
    variations_count: int = 0              # SKU 변형 수
```

> **Note**: `number_of_sellers`와 `plus_content`는 Phase 0에서 `analyze_competition()` 제거 및 `analyze_promotions()` 수정 후에도 모델에서는 유지한다. 다른 곳에서 참조 가능성이 있으므로 모델 필드 삭제는 V6에서 검토한다.

### 3.2 orchestrator.py 필드 주입 변경

`run_analysis()` 함수의 WeightedProduct 필드 주입 블록에 4개 필드 추가:

```python
# V4 + V5 확장 필드를 WeightedProduct에 주입
bright_map = {p.asin: p for p in products}
for wp in weighted_products:
    bp = bright_map.get(wp.asin)
    if bp:
        wp.sns_price = bp.sns_price
        wp.unit_price = bp.unit_price
        wp.number_of_sellers = bp.number_of_sellers
        wp.coupon = bp.coupon
        wp.plus_content = bp.plus_content
        wp.customer_says = bp.customer_says
        # V5 신규
        wp.badge = bp.badge
        wp.initial_price = bp.initial_price
        wp.manufacturer = bp.manufacturer
        wp.variations_count = bp.variations_count
```

---

## 4. Phase 0: Dead Code Cleanup

### 4.1 `analyze_competition()` 제거

**파일**: `market_analyzer.py` (lines 340-357)

**조치**: 함수 전체 삭제.

**근거**: `number_of_sellers` 필드가 874건 모두 1. 분석 결과가 항상 동일하여 의미 없음.

### 4.2 `build_market_analysis()`에서 `"competition"` 키 제거

**변경 전**:
```python
"competition": analyze_competition(weighted_products),
```

**변경 후**: 해당 라인 삭제.

### 4.3 `analyze_promotions()`에서 `plus_content` 비교 제거

**변경 전**:
```python
def analyze_promotions(products: list[WeightedProduct]) -> dict:
    with_coupon = [p for p in products if p.coupon]
    with_plus = [p for p in products if p.plus_content]
    # ...
    return {
        # ...
        "plus_content_count": len(with_plus),
        "plus_content_pct": round(len(with_plus) / len(products) * 100, 1) if products else 0,
        # ...
    }
```

**변경 후**:
```python
def analyze_promotions(products: list[WeightedProduct]) -> dict:
    """쿠폰/프로모션 분석."""
    with_coupon = [p for p in products if p.coupon]

    coupon_types: Counter = Counter()
    for p in with_coupon:
        coupon_types[p.coupon] += 1

    coupon_bsr = [p.bsr_category for p in with_coupon if p.bsr_category is not None]
    no_coupon_bsr = [
        p.bsr_category for p in products
        if not p.coupon and p.bsr_category is not None
    ]

    return {
        "total_products": len(products),
        "coupon_count": len(with_coupon),
        "coupon_pct": round(len(with_coupon) / len(products) * 100, 1) if products else 0,
        "coupon_types": [
            {"coupon": c, "count": n} for c, n in coupon_types.most_common(10)
        ],
        "avg_bsr_with_coupon": (
            round(sum(coupon_bsr) / len(coupon_bsr)) if coupon_bsr else None
        ),
        "avg_bsr_without_coupon": (
            round(sum(no_coupon_bsr) / len(no_coupon_bsr)) if no_coupon_bsr else None
        ),
    }
```

제거 항목: `with_plus` 변수, `plus_content_count`, `plus_content_pct` 키.

---

## 5. Phase 1: Quick Wins (5 items)

### 5.1 AI Report V4 Data Inclusion

#### 5.1.1 MARKET_REPORT_PROMPT 변경

**파일**: `gemini.py`

기존 7개 섹션 + 3개 섹션 추가 = 10개 데이터 소스:

```python
MARKET_REPORT_PROMPT = """아래는 아마존 "{keyword}" 카테고리의 시장 분석 데이터이다.
총 {total_products}개 제품을 분석한 결과이다.

## 분석 데이터

### 1. 가격대별 성분 전략
{price_tier_json}

### 2. BSR 상위 vs 하위 제품 성분 비교
{bsr_json}

### 3. 주요 브랜드 프로파일
{brand_json}

### 4. 성분 조합 분석 (Co-occurrence)
{cooccurrence_json}

### 5. 브랜드 포지셔닝 (가격 vs BSR)
{brand_positioning_json}

### 6. 급성장 제품 (리뷰 적지만 BSR 우수)
{rising_products_json}

### 7. 고평점 vs 저평점 성분 비교
{rating_ingredients_json}

### 8. 월간 판매량 분석
{sales_volume_json}

### 9. Subscribe & Save 가격 분석
{sns_pricing_json}

### 10. 쿠폰/프로모션 분석
{promotions_json}

---

위 데이터를 바탕으로 시장 분석 리포트를 작성하라.

반드시 아래 10개 섹션을 포함:

1. **시장 요약 (Market Overview)**
   - 가격대 분포와 성분 트렌드 한줄 요약
   - 시장의 성숙도 판단

2. **가격대별 성분 전략 (Pricing & Ingredient Strategy)**
   - 각 가격대에서 필수 성분 vs 차별화 성분
   - 가격 프리미엄을 정당화하는 성분은 무엇인가

3. **승리 공식 (Winning Formula)**
   - BSR 상위 제품에만 있는 성분과 그 의미
   - 고평점(4.5+) 전용 성분 vs 저평점(<4.3) 전용 성분의 차이와 해석
   - 추천 포뮬레이션 방향 (구체적 성분 조합 제시)

4. **경쟁 환경 & 브랜드 포지셔닝 (Competitive Landscape)**
   - 브랜드별 가격-BSR 포지셔닝 분석
   - 세그먼트별(Budget/Mid/Premium/Luxury) 주요 플레이어
   - 아직 비어있는 시장 기회

5. **급성장 제품 & 트렌드 (Rising Products)**
   - 리뷰 적지만 BSR 좋은 제품들의 공통점 분석
   - 신규 브랜드/K-뷰티 등 트렌드 시그널
   - 이 제품들이 성공하는 이유 추론

6. **판매량 & 재구매 전략 (Sales & Retention)**
   - 가격대별 판매량 차이와 전략적 의미
   - SNS(Subscribe & Save) 채택 현황과 재구매 유도 효과
   - 쿠폰/프로모션 사용 현황과 BSR 영향

7. **액션 아이템 (Action Items)**
   - 바로 실행할 수 있는 3-5개 구체적 제안
   - 각 제안에 근거 데이터 명시
   - 타겟 가격대 명시

8. **리스크 & 주의사항 (Risks)**
   - 과포화 세그먼트 경고
   - 피해야 할 포지셔닝

형식: 마크다운. 각 섹션에 구체적 수치와 성분명을 반드시 포함.
데이터에 있는 수치만 인용하라. JSON이 아닌 마크다운 텍스트로 출력하라."""
```

> **변경 요약**: 기존 7개 -> 8개 섹션으로 축소 재구성. 기존 7개 데이터 + 3개 데이터(sales_volume, sns_pricing, promotions) = 10개 데이터 소스 투입. 리포트 섹션은 "6. 판매량 & 재구매 전략"을 신설하여 3개 데이터를 통합 해석하고, 기존 "6. 액션 아이템" -> "7. 액션 아이템", "7. 리스크" -> "8. 리스크"로 번호 밀림.

#### 5.1.2 `generate_market_report()` 메서드 변경

```python
async def generate_market_report(self, analysis_data: dict) -> str:
    def _dump(key: str) -> str:
        return json.dumps(analysis_data.get(key, {}), ensure_ascii=False, indent=2)

    prompt = MARKET_REPORT_PROMPT.format(
        keyword=analysis_data["keyword"],
        total_products=analysis_data["total_products"],
        price_tier_json=_dump("price_tier_analysis"),
        bsr_json=_dump("bsr_analysis"),
        brand_json=_dump("brand_analysis"),
        cooccurrence_json=_dump("cooccurrence_analysis"),
        brand_positioning_json=_dump("brand_positioning"),
        rising_products_json=_dump("rising_products"),
        rating_ingredients_json=_dump("rating_ingredients"),
        # V5 추가
        sales_volume_json=_dump("sales_volume"),
        sns_pricing_json=_dump("sns_pricing"),
        promotions_json=_dump("promotions"),
    )
    # ... 이하 동일
```

#### 5.1.3 orchestrator.py `_extract_action_items_section()` 수정

섹션 번호가 6 -> 7로 변경되므로 정규식 업데이트:

```python
def _extract_action_items_section(report_md: str) -> str:
    if not report_md or not report_md.strip():
        return ""
    m = re.search(
        r"(?:^|\n)(?:##\s*)?7\.\s*(?:\*\*)?액션\s*아이템.*?\n(.*?)(?=\n(?:##\s*)?8\.|\n##\s|\Z)",
        report_md,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        text = m.group(1).strip()
        return text[:2000] if len(text) > 2000 else text
    return ""
```

---

### 5.2 customer_says Keyword Analysis

**함수명**: `analyze_customer_voice()`
**파일**: `market_analyzer.py`

```python
def analyze_customer_voice(products: list[WeightedProduct]) -> dict:
    """customer_says 키워드 빈도/감성 분석. Gemini 미사용, 키워드 사전 기반."""
    POSITIVE_KEYWORDS = [
        "effective", "moisturizing", "gentle", "lightweight", "absorbs quickly",
        "hydrating", "brightening", "smooth", "refreshing", "no irritation",
        "love", "soft", "clean", "works well", "great value",
    ]
    NEGATIVE_KEYWORDS = [
        "sticky", "strong smell", "irritation", "greasy", "breakout",
        "drying", "burning", "broke out", "allergic", "thin",
        "oily", "too thick", "stinging", "rash", "waste",
    ]

    with_cs = [p for p in products if p.customer_says]
    if not with_cs:
        return {}

    # 키워드 빈도 집계
    pos_counts: dict[str, list[WeightedProduct]] = {kw: [] for kw in POSITIVE_KEYWORDS}
    neg_counts: dict[str, list[WeightedProduct]] = {kw: [] for kw in NEGATIVE_KEYWORDS}

    for p in with_cs:
        text = p.customer_says.lower()
        for kw in POSITIVE_KEYWORDS:
            if kw in text:
                pos_counts[kw].append(p)
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                neg_counts[kw].append(p)

    def _kw_stats(products_with_kw: list[WeightedProduct]) -> dict:
        if not products_with_kw:
            return {"count": 0, "avg_bsr": None, "avg_rating": None}
        bsr_vals = [p.bsr_category for p in products_with_kw if p.bsr_category is not None]
        return {
            "count": len(products_with_kw),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_rating": round(
                sum(p.rating for p in products_with_kw) / len(products_with_kw), 2
            ),
        }

    # BSR 상위 50% vs 하위 50% 비교
    sorted_by_bsr = sorted(
        [p for p in with_cs if p.bsr_category is not None],
        key=lambda p: p.bsr_category,
    )
    mid = len(sorted_by_bsr) // 2
    top_half = sorted_by_bsr[:mid] if mid > 0 else []
    bottom_half = sorted_by_bsr[mid:] if mid > 0 else []

    def _group_keyword_freq(group: list[WeightedProduct], keywords: list[str]) -> dict[str, int]:
        freq: dict[str, int] = {}
        for kw in keywords:
            count = sum(1 for p in group if kw in p.customer_says.lower())
            if count > 0:
                freq[kw] = count
        return freq

    return {
        "total_with_customer_says": len(with_cs),
        "positive_keywords": {
            kw: _kw_stats(prods) for kw, prods in pos_counts.items() if prods
        },
        "negative_keywords": {
            kw: _kw_stats(prods) for kw, prods in neg_counts.items() if prods
        },
        "bsr_top_half_positive": _group_keyword_freq(top_half, POSITIVE_KEYWORDS),
        "bsr_top_half_negative": _group_keyword_freq(top_half, NEGATIVE_KEYWORDS),
        "bsr_bottom_half_positive": _group_keyword_freq(bottom_half, POSITIVE_KEYWORDS),
        "bsr_bottom_half_negative": _group_keyword_freq(bottom_half, NEGATIVE_KEYWORDS),
    }
```

---

### 5.3 Badge Analysis

**함수명**: `analyze_badges()`
**파일**: `market_analyzer.py`

```python
def analyze_badges(products: list[WeightedProduct]) -> dict:
    """badge 보유/미보유 제품 성과 비교 분석."""
    with_badge = [p for p in products if p.badge]
    without_badge = [p for p in products if not p.badge]

    # badge 종류별 분포
    badge_types: Counter = Counter()
    for p in with_badge:
        badge_types[p.badge] += 1

    def _group_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_price": None, "avg_reviews": None, "avg_rating": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        prices = [p.price for p in group if p.price is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_reviews": round(sum(p.reviews for p in group) / len(group)),
            "avg_rating": round(sum(p.rating for p in group) / len(group), 2),
        }

    # badge 획득 조건 역추론 (최소 리뷰수, 최소 평점)
    threshold = {}
    if with_badge:
        reviews_list = [p.reviews for p in with_badge]
        ratings_list = [p.rating for p in with_badge]
        threshold = {
            "min_reviews": min(reviews_list),
            "median_reviews": sorted(reviews_list)[len(reviews_list) // 2],
            "min_rating": min(ratings_list),
            "median_rating": round(
                sorted(ratings_list)[len(ratings_list) // 2], 1
            ),
        }

    return {
        "total_products": len(products),
        "with_badge": _group_metrics(with_badge),
        "without_badge": _group_metrics(without_badge),
        "badge_types": [
            {"badge": b, "count": c} for b, c in badge_types.most_common()
        ],
        "acquisition_threshold": threshold,
    }
```

---

### 5.4 Discount Impact Analysis

**함수명**: `analyze_discount_impact()`
**파일**: `market_analyzer.py`

```python
def analyze_discount_impact(products: list[WeightedProduct]) -> dict:
    """할인율(initial_price vs final_price) 구간별 BSR/판매량 비교."""

    def _discount_tier(pct: float) -> str:
        if pct <= 0:
            return "No Discount (0%)"
        if pct <= 15:
            return "Light (1-15%)"
        if pct <= 30:
            return "Medium (16-30%)"
        return "Heavy (31%+)"

    tiers: dict[str, list[WeightedProduct]] = defaultdict(list)

    for p in products:
        if p.initial_price is not None and p.price is not None and p.initial_price > 0:
            discount_pct = (1 - p.price / p.initial_price) * 100
            tier = _discount_tier(discount_pct)
        else:
            tier = "No Discount (0%)"
        tiers[tier].append(p)

    def _tier_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None, "avg_price": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        prices = [p.price for p in group if p.price is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        }

    tier_order = ["No Discount (0%)", "Light (1-15%)", "Medium (16-30%)", "Heavy (31%+)"]
    return {
        "total_products": len(products),
        "tiers": {
            tier: _tier_metrics(tiers.get(tier, []))
            for tier in tier_order
        },
    }
```

---

### 5.5 Title Marketing Keyword Analysis

**함수명**: `analyze_title_keywords()`
**파일**: `market_analyzer.py`

```python
def analyze_title_keywords(products: list[WeightedProduct]) -> dict:
    """title 내 마케팅 키워드별 BSR/판매량 비교."""
    MARKETING_KEYWORDS = [
        "Organic", "Natural", "Korean", "Vegan", "Sulfate-Free",
        "Dermatologist", "Clinical", "Hyaluronic", "Retinol", "Vitamin C",
        "Collagen", "Niacinamide", "Salicylic", "SPF", "Cruelty-Free",
        "Fragrance-Free", "Paraben-Free", "Gluten-Free", "Alcohol-Free",
        "Sensitive", "Anti-Aging", "Moisturizing",
    ]

    keyword_products: dict[str, list[WeightedProduct]] = {kw: [] for kw in MARKETING_KEYWORDS}

    for p in products:
        title_lower = p.title.lower()
        for kw in MARKETING_KEYWORDS:
            if kw.lower() in title_lower:
                keyword_products[kw].append(p)

    def _kw_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    results = {
        kw: _kw_metrics(prods)
        for kw, prods in keyword_products.items()
        if prods  # 0건인 키워드 제외
    }

    # BSR 기준으로 정렬
    sorted_results = dict(
        sorted(
            results.items(),
            key=lambda x: x[1].get("avg_bsr") or float("inf"),
        )
    )

    return {
        "total_products": len(products),
        "keyword_analysis": sorted_results,
    }
```

---

## 6. Phase 2: Deep Analysis (6 items)

### 6.1 unit_price Parsing + Unit Economics

**함수명**: `analyze_unit_economics()`
**파일**: `market_analyzer.py`

```python
import re

def _parse_unit_price(unit_price_str: str) -> tuple[float | None, str | None]:
    """'$0.36 / ounce' -> (0.36, 'ounce'). 파싱 실패 시 (None, None)."""
    if not unit_price_str:
        return None, None
    m = re.match(r"\$?([\d.]+)\s*/\s*(.+)", unit_price_str.strip())
    if m:
        try:
            return float(m.group(1)), m.group(2).strip().lower()
        except ValueError:
            return None, None
    return None, None


def analyze_unit_economics(products: list[WeightedProduct]) -> dict:
    """unit_price 파싱 + 동일 단위 기준 단가 비교."""
    unit_data: dict[str, list[dict]] = defaultdict(list)
    parse_success = 0
    parse_fail = 0

    for p in products:
        price_val, unit = _parse_unit_price(p.unit_price)
        if price_val is not None and unit is not None:
            parse_success += 1
            unit_data[unit].append({
                "asin": p.asin,
                "title": p.title[:60],
                "unit_price": price_val,
                "final_price": p.price,
                "bsr": p.bsr_category,
                "bought": p.bought_past_month,
            })
        elif p.unit_price:
            parse_fail += 1

    unit_summaries = {}
    for unit, items in unit_data.items():
        if len(items) < 3:
            continue
        prices = [i["unit_price"] for i in items]
        bsr_vals = [i["bsr"] for i in items if i["bsr"] is not None]
        items_sorted = sorted(items, key=lambda x: x["unit_price"])
        unit_summaries[unit] = {
            "count": len(items),
            "avg_unit_price": round(sum(prices) / len(prices), 3),
            "min_unit_price": round(min(prices), 3),
            "max_unit_price": round(max(prices), 3),
            "cheapest": items_sorted[0],
            "most_expensive": items_sorted[-1],
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
        }

    return {
        "parse_success": parse_success,
        "parse_fail": parse_fail,
        "parse_rate": round(parse_success / (parse_success + parse_fail) * 100, 1)
            if (parse_success + parse_fail) > 0 else 0,
        "units": unit_summaries,
    }
```

---

### 6.2 Manufacturer (OEM) Analysis

**함수명**: `analyze_manufacturer()`
**파일**: `market_analyzer.py`

```python
def analyze_manufacturer(
    products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    """제조사(OEM)별 프로파일 분석."""
    detail_map = {d.asin: d for d in details}
    mfr_data: dict[str, dict] = defaultdict(lambda: {
        "products": [],
        "bsr_values": [],
        "prices": [],
        "ratings": [],
        "bought_values": [],
    })

    for p in products:
        mfr = p.manufacturer
        if not mfr:
            d = detail_map.get(p.asin)
            mfr = d.manufacturer if d else ""
        if not mfr or mfr.lower() in ("unknown", ""):
            continue
        md = mfr_data[mfr]
        md["products"].append(p.asin)
        if p.bsr_category is not None:
            md["bsr_values"].append(p.bsr_category)
        if p.price is not None:
            md["prices"].append(p.price)
        md["ratings"].append(p.rating)
        if p.bought_past_month is not None:
            md["bought_values"].append(p.bought_past_month)

    # K-Beauty OEM 식별 키워드
    K_BEAUTY_KEYWORDS = [
        "medicube", "cosrx", "beauty of joseon", "laneige", "innisfree",
        "missha", "etude", "tonymoly", "some by mi", "klairs",
        "purito", "neogen", "banila co", "heimish", "dr.jart",
    ]

    results = []
    for mfr, md in mfr_data.items():
        if len(md["products"]) < 2:
            continue
        prices = md["prices"]
        bsr_vals = md["bsr_values"]
        bought_vals = md["bought_values"]
        is_kbeauty = any(kw in mfr.lower() for kw in K_BEAUTY_KEYWORDS)
        results.append({
            "manufacturer": mfr,
            "product_count": len(md["products"]),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_rating": round(sum(md["ratings"]) / len(md["ratings"]), 2),
            "total_bought": sum(bought_vals) if bought_vals else None,
            "is_kbeauty": is_kbeauty,
        })

    results.sort(key=lambda x: x["product_count"], reverse=True)

    # 시장 집중도: 상위 10개 제조사의 제품 수 합산
    top10_count = sum(r["product_count"] for r in results[:10])
    total = len([p for p in products if p.manufacturer])

    return {
        "total_manufacturers": len(results),
        "top_manufacturers": results[:15],
        "market_concentration": {
            "top10_products": top10_count,
            "total_products": total,
            "top10_share_pct": round(top10_count / total * 100, 1) if total > 0 else 0,
        },
        "kbeauty_manufacturers": [r for r in results if r["is_kbeauty"]],
    }
```

---

### 6.3 SKU Strategy Analysis (variations_count)

**함수명**: `analyze_sku_strategy()`
**파일**: `market_analyzer.py`

```python
def analyze_sku_strategy(products: list[WeightedProduct]) -> dict:
    """variations_count(SKU 수) 구간별 BSR/판매량 비교."""

    def _sku_tier(count: int) -> str:
        if count == 0:
            return "Single (0)"
        if count <= 3:
            return "Few (1-3)"
        if count <= 10:
            return "Medium (4-10)"
        return "Many (11+)"

    tiers: dict[str, list[WeightedProduct]] = defaultdict(list)
    for p in products:
        tier = _sku_tier(p.variations_count)
        tiers[tier].append(p)

    def _tier_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    tier_order = ["Single (0)", "Few (1-3)", "Medium (4-10)", "Many (11+)"]
    return {
        "total_products": len(products),
        "tiers": {
            tier: _tier_metrics(tiers.get(tier, []))
            for tier in tier_order
        },
    }
```

---

### 6.4 SNS Deep Analysis (extend existing)

**수정 함수**: `analyze_sns_pricing()` 확장
**파일**: `market_analyzer.py`

기존 함수에 3가지 심화 분석 추가:

```python
def analyze_sns_pricing(products: list[WeightedProduct]) -> dict:
    """Subscribe & Save 할인 분석 (V5 확장)."""
    with_sns = [p for p in products if p.sns_price is not None and p.price]
    without_sns = [p for p in products if p.sns_price is None]

    discounts = []
    for p in with_sns:
        discount_pct = (1 - p.sns_price / p.price) * 100 if p.price > 0 else 0
        discounts.append({
            "asin": p.asin,
            "title": p.title[:60],
            "price": p.price,
            "sns_price": p.sns_price,
            "discount_pct": round(discount_pct, 1),
        })
    discounts.sort(key=lambda x: x["discount_pct"], reverse=True)

    avg_discount = (
        round(sum(d["discount_pct"] for d in discounts) / len(discounts), 1)
        if discounts else 0
    )

    # V5 심화: SNS 할인율 구간별 BSR 비교
    def _sns_tier(pct: float) -> str:
        if pct <= 0:
            return "No Discount"
        if pct <= 5:
            return "1-5%"
        if pct <= 10:
            return "6-10%"
        return "11%+"

    sns_tiers: dict[str, list] = defaultdict(list)
    for p in with_sns:
        pct = (1 - p.sns_price / p.price) * 100 if p.price > 0 else 0
        sns_tiers[_sns_tier(pct)].append(p)

    tier_metrics = {}
    for tier_name, group in sns_tiers.items():
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        tier_metrics[tier_name] = {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    # V5 심화: SNS 채택 vs 미채택 bought_past_month 비교
    sns_bought = [p.bought_past_month for p in with_sns if p.bought_past_month is not None]
    no_sns_bought = [p.bought_past_month for p in without_sns if p.bought_past_month is not None]

    # V5 심화: 가격대별 SNS 채택률
    price_tier_sns: dict[str, dict] = defaultdict(lambda: {"total": 0, "with_sns": 0})
    for p in products:
        tier = _price_tier(p.price)
        price_tier_sns[tier]["total"] += 1
        if p.sns_price is not None:
            price_tier_sns[tier]["with_sns"] += 1

    return {
        "total_products": len(products),
        "with_sns_count": len(with_sns),
        "without_sns_count": len(without_sns),
        "sns_adoption_pct": round(len(with_sns) / len(products) * 100, 1) if products else 0,
        "avg_discount_pct": avg_discount,
        "top_discounts": discounts[:10],
        # V5 심화
        "discount_tier_metrics": tier_metrics,
        "retention_signal": {
            "sns_avg_bought": round(sum(sns_bought) / len(sns_bought)) if sns_bought else None,
            "no_sns_avg_bought": round(sum(no_sns_bought) / len(no_sns_bought)) if no_sns_bought else None,
        },
        "price_tier_adoption": {
            tier: {
                "total": d["total"],
                "with_sns": d["with_sns"],
                "adoption_pct": round(d["with_sns"] / d["total"] * 100, 1) if d["total"] > 0 else 0,
            }
            for tier, d in price_tier_sns.items()
        },
    }
```

---

### 6.5 Statistical Significance Testing

**추가 위치**: `market_analyzer.py` 내 유틸리티 함수

**의존성**: `scipy` (pyproject.toml에 추가)

```python
def _stat_compare(group_a: list[float], group_b: list[float]) -> dict:
    """두 그룹 간 Mann-Whitney U test. p-value와 유의성 판정 반환."""
    if len(group_a) < 5 or len(group_b) < 5:
        return {"p_value": None, "significant": None, "note": "insufficient_sample"}
    try:
        from scipy.stats import mannwhitneyu
        stat, p_value = mannwhitneyu(group_a, group_b, alternative="two-sided")
        return {
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
            "u_statistic": round(stat, 2),
        }
    except Exception:
        return {"p_value": None, "significant": None, "note": "test_failed"}
```

**적용 대상**:
- `analyze_badges()`: badge 보유 vs 미보유 BSR 비교에 p-value 추가
- `analyze_discount_impact()`: 할인 vs 미할인 BSR 비교에 p-value 추가
- `analyze_by_bsr()`: 상위/하위 그룹 비교에 p-value 추가

각 함수의 반환 dict에 `"stat_test"` 키 추가:

```python
# analyze_badges() 내 추가:
badge_bsr = [p.bsr_category for p in with_badge if p.bsr_category is not None]
no_badge_bsr = [p.bsr_category for p in without_badge if p.bsr_category is not None]
# ...
return {
    # ... 기존 결과 ...
    "stat_test_bsr": _stat_compare(
        [float(b) for b in badge_bsr],
        [float(b) for b in no_badge_bsr],
    ),
}
```

---

### 6.6 Excel Sheet Expansion

**파일**: `excel_builder.py`

#### 6.6.1 신규 시트: "Consumer Voice"

```python
def _build_consumer_voice(wb: Workbook, customer_voice_data: dict):
    """customer_says 키워드 분석 결과 시트."""
    ws = wb.create_sheet("Consumer Voice")
    ws.sheet_properties.tabColor = "FF9800"

    col_count = 4
    _write_title(
        ws,
        "Consumer Voice Analysis — Keyword Sentiment",
        "Amazon AI review summary(customer_says) 기반 키워드 빈도 및 BSR 상관 분석",
        col_count,
    )

    headers = ["Keyword", "Count", "Avg BSR", "Avg Rating"]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    row = 5
    # Positive keywords
    ws.cell(row=row, column=1, value="--- POSITIVE ---")
    ws.cell(row=row, column=1).font = Font(bold=True, color="2E7D32")
    row += 1
    for kw, stats in (customer_voice_data.get("positive_keywords") or {}).items():
        ws.cell(row=row, column=1, value=kw)
        ws.cell(row=row, column=2, value=stats["count"])
        if stats["avg_bsr"] is not None:
            ws.cell(row=row, column=3, value=stats["avg_bsr"]).number_format = "#,##0"
        if stats["avg_rating"] is not None:
            ws.cell(row=row, column=4, value=stats["avg_rating"])
        row += 1

    # Negative keywords
    ws.cell(row=row, column=1, value="--- NEGATIVE ---")
    ws.cell(row=row, column=1).font = Font(bold=True, color="C62828")
    row += 1
    for kw, stats in (customer_voice_data.get("negative_keywords") or {}).items():
        ws.cell(row=row, column=1, value=kw)
        ws.cell(row=row, column=2, value=stats["count"])
        if stats["avg_bsr"] is not None:
            ws.cell(row=row, column=3, value=stats["avg_bsr"]).number_format = "#,##0"
        if stats["avg_rating"] is not None:
            ws.cell(row=row, column=4, value=stats["avg_rating"])
        row += 1

    _style_data_rows(ws, 5, row - 1, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {"A": 20, "B": 10, "C": 12, "D": 10})
```

#### 6.6.2 신규 시트: "Badge Analysis"

```python
def _build_badge_analysis(wb: Workbook, badge_data: dict):
    """badge 보유/미보유 비교 시트."""
    ws = wb.create_sheet("Badge Analysis")
    ws.sheet_properties.tabColor = "673AB7"

    col_count = 5
    _write_title(
        ws,
        "Badge Analysis — Amazon's Choice / Best Seller Impact",
        "Badge 보유 여부에 따른 BSR, 가격, 리뷰, 평점 비교",
        col_count,
    )

    headers = ["Group", "Count", "Avg BSR", "Avg Price", "Avg Rating"]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, (label, key) in enumerate([("With Badge", "with_badge"), ("Without Badge", "without_badge")]):
        row = 5 + i
        metrics = badge_data.get(key, {})
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=metrics.get("count", 0))
        if metrics.get("avg_bsr") is not None:
            ws.cell(row=row, column=3, value=metrics["avg_bsr"]).number_format = "#,##0"
        if metrics.get("avg_price") is not None:
            ws.cell(row=row, column=4, value=metrics["avg_price"]).number_format = "$#,##0.00"
        if metrics.get("avg_rating") is not None:
            ws.cell(row=row, column=5, value=metrics["avg_rating"])

    # Badge types section
    row = 8
    ws.cell(row=row, column=1, value="Badge Type Distribution")
    ws.cell(row=row, column=1).font = Font(bold=True)
    row += 1
    for bt in badge_data.get("badge_types", []):
        ws.cell(row=row, column=1, value=bt["badge"])
        ws.cell(row=row, column=2, value=bt["count"])
        row += 1

    _style_data_rows(ws, 5, row - 1, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {"A": 25, "B": 10, "C": 12, "D": 12, "E": 10})
```

#### 6.6.3 Product Detail 컬럼 추가

기존 17컬럼에 3컬럼 추가 -> 20컬럼:

| 추가 컬럼 | 위치 | 데이터 |
|-----------|------|--------|
| Badge | 기존 A+ 뒤 (col 15) | `p.badge` |
| Discount% | Badge 뒤 (col 16) | `(1 - price/initial_price) * 100` |
| Variations | Discount% 뒤 (col 17) | `p.variations_count` |

기존 Customer Says, Ingredients Found, URL은 col 18, 19, 20으로 밀림.

#### 6.6.4 build_excel() 시그니처 변경

```python
def build_excel(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str = "",
    rising_products: list[dict] | None = None,
    # V5 추가
    analysis_data: dict | None = None,
) -> bytes:
```

`analysis_data`를 통째로 전달받아 Consumer Voice, Badge Analysis 시트 생성에 사용:

```python
    if analysis_data:
        customer_voice = analysis_data.get("customer_voice")
        if customer_voice:
            _build_consumer_voice(wb, customer_voice)
        badge_data = analysis_data.get("badges")
        if badge_data:
            _build_badge_analysis(wb, badge_data)
```

#### 6.6.5 orchestrator.py의 build_excel() 호출 변경

```python
excel_bytes = build_excel(
    category_name, weighted_products, rankings, categories,
    search_products, all_details,
    market_report=market_report,
    rising_products=analysis_data.get("rising_products"),
    analysis_data=analysis_data,  # V5 추가
)
```

---

## 7. build_market_analysis() 최종 형태

```python
def build_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    """전체 시장 분석 데이터 생성."""
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        # 기존 V4 분석 (7개)
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
        "brand_positioning": analyze_brand_positioning(weighted_products, details),
        "rising_products": detect_rising_products(weighted_products, details),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
        # V4 분석 (competition 제거)
        "sales_volume": analyze_sales_volume(weighted_products),
        "sns_pricing": analyze_sns_pricing(weighted_products),
        "promotions": analyze_promotions(weighted_products),
        # V5 Phase 1 신규
        "customer_voice": analyze_customer_voice(weighted_products),
        "badges": analyze_badges(weighted_products),
        "discount_impact": analyze_discount_impact(weighted_products),
        "title_keywords": analyze_title_keywords(weighted_products),
        # V5 Phase 2 신규
        "unit_economics": analyze_unit_economics(weighted_products),
        "manufacturer": analyze_manufacturer(weighted_products, details),
        "sku_strategy": analyze_sku_strategy(weighted_products),
    }
```

---

## 8. Implementation Order

```
Phase 0 (30분) — Dead Code Cleanup
├─ 0-1. market_analyzer.py: analyze_competition() 함수 삭제
├─ 0-2. market_analyzer.py: build_market_analysis()에서 "competition" 키 삭제
├─ 0-3. market_analyzer.py: analyze_promotions()에서 plus_content 관련 코드 삭제
└─ 0-4. 기존 파이프라인 정상 동작 확인

Phase 1 (1주차) — Quick Wins
├─ 1-1. models.py: WeightedProduct에 badge, initial_price, manufacturer, variations_count 추가
├─ 1-2. orchestrator.py: WeightedProduct 필드 주입에 4개 필드 추가
├─ 1-3. gemini.py: MARKET_REPORT_PROMPT 확장 (10개 데이터 소스)
├─ 1-4. gemini.py: generate_market_report()에 3개 _dump() 추가
├─ 1-5. orchestrator.py: _extract_action_items_section() 섹션 번호 6->7 수정
├─ 1-6. market_analyzer.py: analyze_customer_voice() 신규 추가
├─ 1-7. market_analyzer.py: analyze_badges() 신규 추가
├─ 1-8. market_analyzer.py: analyze_discount_impact() 신규 추가
├─ 1-9. market_analyzer.py: analyze_title_keywords() 신규 추가
└─ 1-10. market_analyzer.py: build_market_analysis()에 Phase 1 분석 4개 추가

Phase 2 (2주차) — Deep Analysis
├─ 2-1. pyproject.toml: scipy 의존성 추가
├─ 2-2. market_analyzer.py: _parse_unit_price() + analyze_unit_economics() 추가
├─ 2-3. market_analyzer.py: analyze_manufacturer() 추가
├─ 2-4. market_analyzer.py: analyze_sku_strategy() 추가
├─ 2-5. market_analyzer.py: analyze_sns_pricing() 확장 (심화 3항목)
├─ 2-6. market_analyzer.py: _stat_compare() + 기존 함수에 통계 검증 추가
├─ 2-7. market_analyzer.py: build_market_analysis()에 Phase 2 분석 3개 추가
├─ 2-8. excel_builder.py: _build_consumer_voice() 시트 추가
├─ 2-9. excel_builder.py: _build_badge_analysis() 시트 추가
├─ 2-10. excel_builder.py: Product Detail에 badge/discount%/variations 컬럼 추가
├─ 2-11. excel_builder.py: build_excel() 시그니처 변경 (analysis_data 파라미터)
└─ 2-12. orchestrator.py: build_excel() 호출에 analysis_data 전달
```

---

## 9. Dependencies

| Package | Version | Purpose | Phase |
|---------|---------|---------|:-----:|
| scipy | >=1.11 | Mann-Whitney U test, Fisher's exact test | Phase 2 |

> Phase 0, 1은 기존 패키지(pandas, openpyxl, pydantic)로 완전히 구현 가능.

---

## 10. Test Plan

### 10.1 Phase 0 검증

- [ ] `analyze_competition()` 삭제 후 `build_market_analysis()` 정상 반환
- [ ] `analyze_promotions()` 결과에 `plus_content_count` 키 없음
- [ ] 기존 Excel/리포트 파이프라인 정상 동작

### 10.2 Phase 1 검증

- [ ] WeightedProduct에 badge, initial_price, manufacturer, variations_count 값 정상 주입
- [ ] `analyze_customer_voice()` 반환값에 positive/negative keywords 포함
- [ ] `analyze_badges()` 반환값에 with_badge/without_badge 비교 포함
- [ ] `analyze_discount_impact()` 할인 구간별 데이터 정상 생성
- [ ] `analyze_title_keywords()` 마케팅 키워드별 BSR 데이터 정상 생성
- [ ] MARKET_REPORT_PROMPT에 10개 데이터 소스 전달 확인
- [ ] AI 리포트에 "판매량 & 재구매 전략" 섹션 포함
- [ ] `_extract_action_items_section()` 섹션 7번 정상 추출

### 10.3 Phase 2 검증

- [ ] `_parse_unit_price()`: "$0.36 / ounce" -> (0.36, "ounce") 정상 파싱
- [ ] `_parse_unit_price()`: 파싱률 90% 이상
- [ ] `analyze_manufacturer()` K-Beauty OEM 식별
- [ ] `analyze_sku_strategy()` 4개 구간 정상 분류
- [ ] `analyze_sns_pricing()` 심화 3항목 반환
- [ ] `_stat_compare()` p-value 정상 반환
- [ ] Excel "Consumer Voice" 시트 생성
- [ ] Excel "Badge Analysis" 시트 생성
- [ ] Excel "Product Detail" 20컬럼 정상 출력

---

## 11. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI 리포트 프롬프트 확장 -> 토큰 증가 | 월 $0.5 미만 증가 | 데이터 요약 후 전달 |
| customer_says 키워드 사전 누락 | 분석 정확도 저하 | 초기 배포 후 키워드 보완 반복 |
| unit_price 파싱 예외 형식 | 파싱률 하락 | 정규식 + 파싱 실패 로깅 |
| scipy import 오버헤드 | 초기 로딩 지연 | lazy import (함수 내 import) |
| 통계 검정 대부분 비유의 | 리포트 노이즈 | 유의하지 않은 결과도 투명 보고 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-09 | Initial draft | CTO Lead |
