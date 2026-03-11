# Report Enhancement V7 Design Document

> **Summary**: Excel/HTML 리포트의 가격 투명성, 제품 접근성, 성분 분석 정밀도, 드릴다운, 할인 전략 분석 개선을 위한 상세 구현 설계
>
> **Project**: amz_researcher (webhook-service)
> **Author**: Claude (Design Phase)
> **Date**: 2026-03-11
> **Status**: Draft
> **Planning Doc**: [report-enhancement-v7.plan.md](../../01-plan/features/report-enhancement-v7.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 리포트에서 할인 정보, 제품 링크, 성분 출처 구분, 집계 상세, 세그먼트별 할인 전략이 제공되지 않아 외부 확인 작업 필요 |
| **Solution** | 5개 REQ를 모델-분석-렌더링 전 계층에 걸쳐 구현. SNS→할인 분석 대체, Featured/INCI 성분 분리, 인라인 드릴다운 |
| **Function/UX Effect** | 가격 투명성, 원클릭 제품 접근, 마케팅 성분 식별, 전성분 확인, 집계 수치 드릴다운, 세그먼트별 할인 전략 파악 |
| **Core Value** | 리포트 하나로 의사결정 완결 — 외부 도구/탭 전환 없이 분석부터 제품 확인까지 원스톱 |

---

## 1. Overview

### 1.1 Design Goals

1. **가격 투명성**: Initial Price + Discount% 를 Excel/HTML 양쪽에서 명확히 표시
2. **제품 접근성**: 제품 타이틀 클릭 시 Amazon 페이지 직접 이동
3. **성분 정밀도**: Featured(마케팅 소구) vs INCI(전성분) 성분을 명확히 구분 + 전성분 확인 가능
4. **데이터 탐색**: 집계 수치에서 개별 제품으로 인라인 드릴다운
5. **할인 전략**: SNS 분석 제거, 세그먼트별 할인율 분석으로 대체

### 1.2 Design Principles

- **최소 파급 범위**: 기존 컬럼 번호 시프트를 상쇄하여 영향 최소화
- **점진적 마이그레이션**: `source` 필드 기본값 `""` 으로 레거시 캐시 호환
- **DRY**: TableController 드릴다운을 공통 인프라로 구현, 각 섹션은 설정만 전달

---

## 2. Architecture

### 2.1 변경 영향 컴포넌트 다이어그램

```
┌──────────────┐
│  models.py   │ ← Ingredient.source, WeightedProduct.ingredients_raw,
│              │   IngredientRanking.featured_count/inci_only_count
└──────┬───────┘
       │
┌──────▼───────┐     ┌──────────────────┐
│  gemini.py   │────▶│  PROMPT_TEMPLATE │ ← source 분류 지시 추가
│              │     │  generate_market_ │ ← SNS→Discount 분기 수정
└──────┬───────┘     │  report()        │
       │             └──────────────────┘
┌──────▼───────┐
│ analyzer.py  │ ← _aggregate_ingredients: source 집계
└──────┬───────┘
       │
┌──────▼──────────────┐
│ market_analyzer.py  │ ← analyze_discount_by_segment() 신규
│                     │   build_market_analysis(): sns→discount 교체
│                     │   build_keyword_market_analysis(): 동일 교체
└──────┬──────────────┘
       │
┌──────▼──────────────┐     ┌────────────────────────┐
│ excel_builder.py    │     │ html_report_builder.py │
│ - Product Detail    │     │ - _product_to_dict     │
│ - Sales & Pricing   │     │ - TableController      │
│                     │     │ - renderProductDetail  │
│                     │     │ - renderSalesPricing   │
│                     │     │ - renderBrandPositioning│
│                     │     │ - renderIngredientRanking│
└─────────────────────┘     └────────────────────────┘
```

### 2.2 Data Flow (변경 후)

```
DB: amz_products.ingredients (TEXT) ──→ product_db.py ──→ orchestrator.py
                                                              │
                                    WeightedProduct.ingredients_raw = row["ingredients"]
                                                              │
Gemini PROMPT (+ source 분류) ──→ Ingredient(name, common_name, category, source)
                                                              │
analyzer.py: _aggregate_ingredients ──→ IngredientRanking(+ featured_count, inci_only_count)
                                                              │
                              ┌────────────────────────────────┤
                              │                                │
                         Excel Builder                   HTML Builder
                         - Featured Ingredients col       - _product_to_dict: + source, ingredients_raw
                         - Full INCI col                  - Ingredient Ranking: Source 컬럼
                         - Initial Price col              - Featured Ingredients 카드
                         - Title hyperlink                - Product Detail: INCI 확장 UI
                         - Discount Strategy table        - Discount Strategy 카드
                                                          - Drilldown panels
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| analyzer.py source 집계 | models.py Ingredient.source | source 필드 존재 필요 |
| excel_builder Featured Ingredients | WeightedProduct.ingredients source | 필터링 기준 |
| html_report_builder drilldown | REPORT_DATA.products | 전체 제품 데이터로 필터 |
| analyze_discount_by_segment | WeightedProduct.initial_price, price | 할인율 계산 |
| gemini SNS→Discount 분기 | analysis_data.discount_analysis | 새 키 참조 |

---

## 3. Data Model

### 3.1 Model 변경 (`models.py`)

#### 3.1.1 Ingredient — source 필드 추가

```python
# Before (line 72-75):
class Ingredient(BaseModel):
    name: str
    common_name: str = ""
    category: str

# After:
class Ingredient(BaseModel):
    name: str
    common_name: str = ""
    category: str
    source: str = ""  # "featured", "inci", "both", "" (legacy)
```

**호환성**: 기본값 `""` 으로 기존 캐시 데이터 파싱 시 누락 필드 자동 처리.

#### 3.1.2 WeightedProduct — ingredients_raw 필드 추가

```python
# After (line 127 부근, badge 아래에 추가):
class WeightedProduct(BaseModel):
    # ... existing fields (line 101-129) ...
    voice_positive: list[str] = []
    voice_negative: list[str] = []
    # V7 신규 필드
    ingredients_raw: str = ""  # DB amz_products.ingredients 원본 텍스트
```

#### 3.1.3 IngredientRanking — source 집계 필드 추가

```python
# Before (line 132-141):
class IngredientRanking(BaseModel):
    rank: int = 0
    ingredient: str
    weighted_score: float
    product_count: int
    avg_weight: float
    category: str
    avg_price: float | None = None
    price_range: str = ""
    key_insight: str = ""

# After:
class IngredientRanking(BaseModel):
    rank: int = 0
    ingredient: str
    weighted_score: float
    product_count: int
    avg_weight: float
    category: str
    avg_price: float | None = None
    price_range: str = ""
    key_insight: str = ""
    featured_count: int = 0    # 해당 성분이 source="featured"/"both"로 추출된 제품 수 (제품 단위 카운트)
    inci_only_count: int = 0   # 해당 성분이 source="inci"로만 추출된 제품 수 (제품 단위 카운트)
```

---

## 4. Detailed Implementation per Phase

### 4.1 Phase 1: REQ-2 — Title Hyperlinks

#### 4.1.1 Excel (`excel_builder.py` `_build_product_detail`)

**현재** (line 222-223):
```python
ws.cell(row=row, column=3, value=p.title)
```

**변경**:
```python
title_cell = ws.cell(row=row, column=3, value=p.title)
url = f"https://www.amazon.com/dp/{p.asin}"
title_cell.hyperlink = url
title_cell.style = "Hyperlink"
```

**URL 컬럼 (현재 col 22)**: 유지 (하위 호환). Phase 2에서 컬럼 번호 변경 없이 동일 위치.

**Raw Search 시트**: 이 시트에서도 타이틀 셀에 동일 hyperlink 추가.

#### 4.1.2 HTML (`html_report_builder.py`)

**Product Detail** (line 1739):
```javascript
// Before:
{ key: 'title', header: 'Title', render: (v) => truncate(v, 'lg'), sortable: false },

// After:
{ key: 'title', header: 'Title', sortable: false,
  render: (v, row) => {
    const url = `https://www.amazon.com/dp/${row.asin}`;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="product-link">${truncate(v, 'lg')}</a>`;
  }
},
```

**Raw Search** (line 1779):
```javascript
// Before:
{ key: 'title', header: 'Title', sortable: false, render: (v) => truncate(v, 'xl') },

// After:
{ key: 'title', header: 'Title', sortable: false,
  render: (v, row) => {
    const url = `https://www.amazon.com/dp/${row.asin}`;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="product-link">${truncate(v, 'xl')}</a>`;
  }
},
```

**Rising Products** (카테고리 리포트만 — `renderRisingProducts` 내 title 표시):
동일 패턴 적용. `esc(p.title || '')` → `<a>` 태그 래핑.

> **⚠️ ASIN 검증 가드 (Plan §4.2.3 반영)**: 모든 URL 생성 시 ASIN 형식을 검증한다. 유효하지 않은 ASIN은 링크를 생성하지 않고 plain text로 표시:
> ```javascript
> function isValidAsin(asin) { return /^[A-Z0-9]{10}$/.test(asin); }
>
> // 사용 예:
> render: (v, row) => {
>   if (isValidAsin(row.asin)) {
>     const url = `https://www.amazon.com/dp/${row.asin}`;
>     return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="product-link">${truncate(v, 'lg')}</a>`;
>   }
>   return truncate(v, 'lg');
> }
> ```
> Excel 하이퍼링크에서도 동일하게 ASIN 검증 후 적용:
> ```python
> import re
> ASIN_PATTERN = re.compile(r'^[A-Z0-9]{10}$')
>
> if ASIN_PATTERN.match(p.asin):
>     title_cell.hyperlink = f"https://www.amazon.com/dp/{p.asin}"
>     title_cell.style = "Hyperlink"
> ```

**CSS 추가**:
```css
.product-link {
  color: var(--color-positive);
  text-decoration: none;
}
.product-link:hover {
  text-decoration: underline;
}
```

---

### 4.2 Phase 2: REQ-1 + REQ-5 Excel 컬럼 (통합)

> **핵심**: SNS Price (col 5) 제거 + 같은 자리에 Initial Price 삽입 → 시프트 상쇄, col 6 이후 변동 없음.

#### 4.2.1 Excel Product Detail headers 변경

```python
# Before (line 206-213):
headers = [
    "ASIN", "Brand", "Title", "Price", "SNS Price",
    "Bought/Mo", "Reviews", "Rating", "BSR",
    "Weight", "Unit Price", "Sellers", "Coupon",
    "A+", "Badge", "Discount%", "Variations",
    "Customer Says", "Voice Positive", "Voice Negative",
    "Ingredients Found", "URL",
]

# After:
headers = [
    "ASIN", "Brand", "Title", "Price", "Initial Price",
    "Bought/Mo", "Reviews", "Rating", "BSR",
    "Weight", "Unit Price", "Sellers", "Coupon",
    "A+", "Badge", "Discount%", "Variations",
    "Customer Says", "Voice Positive", "Voice Negative",
    "Featured Ingredients", "Full Ingredients (INCI)", "URL",
]
# col_count: 22 → 23 (Full INCI 컬럼 1개 추가, SNS 제거/Initial 추가는 상쇄)
```

#### 4.2.2 Excel 데이터 매핑 변경

```python
# Before (line 226-227):
if p.sns_price is not None:
    ws.cell(row=row, column=5, value=p.sns_price).number_format = "$#,##0.00"

# After:
if p.initial_price is not None:
    ws.cell(row=row, column=5, value=p.initial_price).number_format = "$#,##0.00"
```

**col 6~20**: 변경 없음 (시프트 상쇄).

**col 21 (Featured Ingredients)**:
```python
# Before (line 220-221, 251):
ingredients_str = ", ".join(ing.name for ing in p.ingredients)
ws.cell(row=row, column=21, value=ingredients_str)

# After:
# NOTE: _get_display_name은 analyzer.py에 정의됨 → excel_builder.py에서 import 필요
# from amz_researcher.services.analyzer import _get_display_name
# 또는 인라인: (ing.common_name or ing.name)
featured_str = ", ".join(
    (ing.common_name or ing.name) for ing in p.ingredients
    if ing.source in ("featured", "both")
)
# 레거시 데이터 (source="" 인 경우): 전부 표시
if not featured_str and p.ingredients:
    featured_str = ", ".join((ing.common_name or ing.name) for ing in p.ingredients)
ws.cell(row=row, column=21, value=featured_str)
```
> **결정**: `_get_display_name`을 import하지 않고 `(ing.common_name or ing.name)` 인라인 패턴 사용. excel_builder.py에서 analyzer.py 의존성 추가를 피함.

**col 22 (Full Ingredients INCI)** — 신규:
```python
ws.cell(row=row, column=22, value=p.ingredients_raw)
```

**col 23 (URL)** — 기존 col 22에서 이동:
```python
url = f"https://www.amazon.com/dp/{p.asin}"
ws.cell(row=row, column=23, value=url)
```

**col_count 업데이트**: `22 → 23`

**컬럼 너비 업데이트** (`_set_column_widths`):
```python
# Before (line 258-264):
_set_column_widths(ws, {
    "A": 14, "B": 16, "C": 45, "D": 10, "E": 10,
    ...
    "U": 45, "V": 14,
})

# After:
_set_column_widths(ws, {
    "A": 14, "B": 16, "C": 45, "D": 10, "E": 12,  # E: Initial Price
    "F": 12, "G": 10, "H": 8, "I": 10,
    "J": 10, "K": 16, "L": 8, "M": 14,
    "N": 5, "O": 18, "P": 10, "Q": 10,
    "R": 40, "S": 30, "T": 30, "U": 40, "V": 50, "W": 14,
    # U: Featured Ingredients, V: Full INCI, W: URL
})
```

#### 4.2.3 HTML Product Detail 컬럼 변경

**SNS Price 컬럼 제거** (line 1742):
```javascript
// DELETE this line:
{ key: 'sns_price', header: 'SNS Price', render: (v) => fmtPrice(v) },
```

**Price 컬럼 복합 렌더링** (line 1740):
```javascript
// Before:
{ key: 'price', header: 'Price', render: (v) => fmtPrice(v) },

// After:
{ key: 'price', header: 'Price', render: (v, row) => {
    let html = fmtPrice(v);
    if (row.initial_price && row.initial_price > v) {
      const disc = Math.round((1 - v / row.initial_price) * 100);
      html += ` <span class="price-original">${fmtPrice(row.initial_price)}</span>`;
      html += ` <span class="badge badge-negative">-${disc}%</span>`;
    }
    return html;
  }
},
```

**CSS**:
```css
.price-original {
  text-decoration: line-through;
  color: var(--color-text-muted);
  font-size: 0.85em;
}
```

---

### 4.3 Phase 3: REQ-3 — Ingredients Overhaul

#### 4.3.1 Phase 3-1: Model 변경

위 §3.1 참조. `models.py`에 3개 변경.

#### 4.3.2 Phase 3-2: ingredients_raw 데이터 경로

**product_db.py**: 변경 불필요. `get_products_by_category()` (line 50)와 `get_keyword_products()` (line 217) 모두 `SELECT *` 또는 `SELECT p.*`를 사용하므로 `ingredients` 컬럼이 이미 포함됨.

**orchestrator.py — 카테고리 플로우**: V4 확장 필드 주입 블록 (line 791-806)에 추가:
```python
# orchestrator.py line 791-806: V4 확장 필드 주입 블록
bright_map = {p.asin: p for p in products}
for wp in weighted_products:
    bp = bright_map.get(wp.asin)
    if bp:
        wp.sns_price = bp.sns_price
        # ... existing injections (line 796-806) ...
        wp.variations_count = bp.variations_count
        # V7 NEW:
        wp.ingredients_raw = bp.ingredients or ""  # BrightDataProduct.ingredients
```

**orchestrator.py — 키워드 플로우**: V4 확장 필드 주입 블록 (line 1150-1167)에 추가:
```python
# orchestrator.py line 1150-1167: 키워드 V4 확장 필드 주입 블록
kp_map = {p["asin"]: p for p in keyword_products}
for wp in weighted_products:
    kp = kp_map.get(wp.asin)
    if kp:
        # ... existing injections (line 1155-1167) ...
        wp.bought_past_month = int(bpm) if bpm is not None else None
        # V7 NEW:
        wp.ingredients_raw = str(kp.get("ingredients", "") or "")
```

> **참고**: `calculate_weights()` (analyzer.py)에서 WeightedProduct를 생성하지만, `ingredients_raw` 등 확장 필드는 이후 orchestrator에서 주입하는 패턴을 따른다. `ingredients_raw`도 동일 패턴으로 post-injection한다.

#### 4.3.3 Phase 3-3: Gemini 프롬프트 변경 (`gemini.py`)

**PROMPT_TEMPLATE** (line 35-86) 규칙 추가:

```
# After 규칙 6번 (line 71) 뒤에 추가:
7. source: 성분이 어디에서 확인되었는지 반드시 분류
   - "featured": 제품의 title 또는 features에서만 언급된 성분 (INCI에는 없거나 INCI가 비어있음)
   - "inci": ingredients_raw(전성분 리스트)에서만 확인된 성분
   - "both": title/features와 ingredients_raw 양쪽 모두에서 확인된 성분
   - 판단 근거: title/features에 성분명이 직접 언급되어 있으면 "featured" 또는 "both"
```

**JSON 출력 예시** (line 74-83) 변경:
```json
{
  "products": [
    {
      "asin": "제품ASIN",
      "ingredients": [
        {"name": "Argania Spinosa Kernel Oil", "common_name": "Argan Oil", "category": "Natural Oil", "source": "both"},
        {"name": "Tocopherol", "common_name": "Vitamin E", "category": "Vitamin", "source": "inci"}
      ]
    }
  ]
}
```

#### 4.3.4 Phase 3-4: analyzer.py source 집계

**`_aggregate_ingredients`** (line 64-116) 변경:

```python
def _aggregate_ingredients(
    weighted_products: list[WeightedProduct],
) -> list[IngredientRanking]:
    ingredient_data: dict[str, dict] = {}

    for wp in weighted_products:
        for ing in wp.ingredients:
            key = _get_display_name(ing)
            if key not in ingredient_data:
                ingredient_data[key] = {
                    "category": ing.category,
                    "total_weight": 0.0,
                    "product_count": 0,
                    "prices": [],
                    "featured_count": 0,   # NEW
                    "inci_only_count": 0,   # NEW
                }
            data = ingredient_data[key]
            data["total_weight"] += wp.composite_weight
            data["product_count"] += 1
            if wp.price is not None:
                data["prices"].append(wp.price)
            # NEW: source 집계 (제품 단위 카운트)
            # NOTE: 동일 제품에서 같은 common_name의 성분이 여러 번 나올 수 있으나,
            # _get_display_name 기준으로 이미 같은 키로 묶이므로 제품당 1회만 카운트됨
            # (같은 wp 루프 내에서 같은 key에 대해 product_count도 1씩 증가)
            if ing.source in ("featured", "both"):
                data["featured_count"] += 1
            elif ing.source == "inci":
                data["inci_only_count"] += 1

    rankings = []
    for name, data in ingredient_data.items():
        # ... existing price calculation ...
        rankings.append(IngredientRanking(
            ingredient=name,
            weighted_score=data["total_weight"],
            product_count=data["product_count"],
            avg_weight=avg_weight,
            category=data["category"],
            avg_price=avg_price,
            price_range=price_range,
            featured_count=data["featured_count"],      # NEW
            inci_only_count=data["inci_only_count"],    # NEW
        ))
    # ... rest unchanged ...
```

#### 4.3.5 Phase 3-5a: `_product_to_dict` 직렬화 (`html_report_builder.py` line 49-76)

```python
# Before (line 72-75):
"ingredients": [
    {"name": i.name, "common_name": i.common_name, "category": i.category}
    for i in p.ingredients
],

# After:
"ingredients": [
    {"name": i.name, "common_name": i.common_name, "category": i.category, "source": i.source}
    for i in p.ingredients
],
"ingredients_raw": p.ingredients_raw,
```

**`_ranking_to_dict`** (또는 rankings 직렬화 부분):
```python
# rankings 데이터에 featured_count, inci_only_count 포함 확인
# rankings가 이미 dict 변환되는 경우 해당 필드 자동 포함
```

#### 4.3.6 Phase 3-5b: HTML Ingredient Ranking 변경

**Source 컬럼 추가** (`renderIngredientRanking` line 1611-1619):

```javascript
// After 'category' column (line 1617):
{ key: 'featured_count', header: 'Source', sortable: true,
  render: (v, row) => {
    const fc = row.featured_count || 0;
    const ic = row.inci_only_count || 0;
    if (fc > 0 && ic > 0) return `<span class="badge badge-positive">Featured</span> <span class="badge badge-mid">+INCI</span>`;
    if (fc > 0) return `<span class="badge badge-positive">Featured (${fc})</span>`;
    if (ic > 0) return `<span class="badge badge-mid">INCI Only (${ic})</span>`;
    return '<span class="badge">Unknown</span>';
  }
},
```

**Featured Ingredients 요약 카드** (`renderIngredientRanking` 상단, heroEl 앞에):

```javascript
// Featured Ingredients 카드 (rankings 중 featured_count > 0인 항목)
const featuredRankings = data.rankings.filter(r => (r.featured_count || 0) > 0);
const featuredCardEl = el.querySelector('#featured-ingredients-card');
if (featuredCardEl && featuredRankings.length > 0) {
  const top10 = featuredRankings.slice(0, 10);
  featuredCardEl.innerHTML = `
    <div class="insight-callout" style="border-left:3px solid var(--color-positive)">
      <h4>Featured Ingredients — Actively Marketed by Brands</h4>
      <p style="color:var(--color-text-muted);font-size:12px;margin-bottom:12px">
        These ingredients appear in product titles or feature bullets, indicating brands actively market them as selling points.
      </p>
      <div class="kpi-grid">${top10.map(r =>
        `<div class="kpi-card" style="border-top:2px solid var(--color-positive)">
          <div class="kpi-label">${esc(r.ingredient)}</div>
          <div class="kpi-value">${r.featured_count} products</div>
          <div style="font-size:11px;color:var(--color-text-muted)">${esc(r.category)}</div>
        </div>`
      ).join('')}</div>
    </div>`;
}
```

**HTML 템플릿 삽입 위치**: `html_report_builder.py` line 2120 `<div id="ingredient-hero">` 바로 **앞에** 삽입:
```python
# html_report_builder.py 내 HTML 템플릿 문자열, line 2119-2120 사이:
# Before:
#     </div>
#   </div>
#   <div class="card-grid card-grid-5" id="ingredient-hero" ...>

# After:
#     </div>
#   </div>
#   <div id="featured-ingredients-card" style="margin-bottom:24px"></div>
#   <div class="card-grid card-grid-5" id="ingredient-hero" ...>
```

#### 4.3.7 Phase 3-5c: Product Detail 전성분 확장 UI

**HTML Product Detail columns** (Phase 2에서 SNS 제거 후):

```javascript
// 기존 마지막 컬럼들 뒤에 추가:
{ key: 'ingredients', header: 'Featured', sortable: false,
  render: (v, row) => {
    if (!v || !v.length) return '';
    const featured = v.filter(i => i.source === 'featured' || i.source === 'both');
    if (!featured.length) {
      // Legacy data (no source) — show all
      return v.map(i => esc(i.common_name || i.name)).join(', ');
    }
    return featured.map(i =>
      `<span class="badge badge-positive" style="font-size:10px;margin:1px">${esc(i.common_name || i.name)}</span>`
    ).join(' ');
  }
},
{ key: 'ingredients_raw', header: 'Full INCI', sortable: false,
  render: (v) => {
    if (!v) return '';
    const short = v.length > 80 ? v.substring(0, 80) + '...' : v;
    // NOTE: esc() uses textContent→innerHTML which escapes <, >, & but NOT double quotes.
    // For HTML attributes (title, data-full), additionally escape " to &quot;
    const attrSafe = (s) => esc(s).replace(/"/g, '&quot;');
    return `<span class="cell-truncate inci-expand" title="${attrSafe(v)}" onclick="this.textContent = this.dataset.full || this.textContent; this.classList.toggle('expanded')" data-full="${attrSafe(v)}">${esc(short)}</span>`;
  }
},
```

**CSS**:
```css
.inci-expand {
  cursor: pointer;
  max-width: 200px;
  display: inline-block;
}
.inci-expand.expanded {
  max-width: none;
  white-space: normal;
  word-break: break-all;
}
```

#### 4.3.8 Phase 3-6: Excel Featured + Full INCI 컬럼

Phase 2 §4.2.2에서 이미 설계. col 21 = Featured Ingredients (source 필터), col 22 = Full INCI (ingredients_raw).

#### 4.3.9 Phase 3-7: 하위 호환

- `Ingredient.source = ""` → Pydantic 기본값으로 기존 캐시 자동 호환
- `WeightedProduct.ingredients_raw = ""` → 빈 문자열 기본값
- 렌더링: source가 `""` 이면 모든 성분을 표시 (레거시 모드)
- Featured Ingredients 카드: featured_count가 0이면 카드 숨김

---

### 4.4 Phase 4: REQ-5 분석 계층 (SNS→Discount)

#### 4.4.1 새 함수: `analyze_discount_by_segment` (`market_analyzer.py`)

```python
def analyze_discount_by_segment(products: list[WeightedProduct]) -> dict:
    """세그먼트(Budget/Mid/Premium/Luxury)별 할인 전략 분석."""
    segments: dict[str, list] = defaultdict(list)

    for p in products:
        tier = _price_tier(p.price)
        segments[tier].append(p)

    overall_discounted = [
        p for p in products
        if p.initial_price is not None and p.price is not None
        and p.initial_price > p.price
    ]

    def _segment_stats(group: list[WeightedProduct]) -> dict:
        discounted = [
            p for p in group
            if p.initial_price is not None and p.price is not None
            and p.initial_price > p.price
        ]
        non_discounted = [p for p in group if p not in discounted]

        discount_pcts = [
            round((1 - p.price / p.initial_price) * 100, 1)
            for p in discounted
        ]
        bought_disc = [p.bought_past_month for p in discounted if p.bought_past_month is not None]
        bought_non = [p.bought_past_month for p in non_discounted if p.bought_past_month is not None]

        return {
            "total": len(group),
            "discounted": len(discounted),
            "discount_rate": round(len(discounted) / len(group) * 100, 1) if group else 0,
            "avg_discount_pct": round(sum(discount_pcts) / len(discount_pcts), 1) if discount_pcts else 0,
            "max_discount_pct": max(discount_pcts) if discount_pcts else 0,
            "avg_bought_discounted": round(sum(bought_disc) / len(bought_disc)) if bought_disc else None,
            "avg_bought_non_discounted": round(sum(bought_non) / len(bought_non)) if bought_non else None,
        }

    tier_order = ["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]
    by_segment = {}
    for tier_name in tier_order:
        group = segments.get(tier_name, [])
        if group:
            by_segment[tier_name] = _segment_stats(group)

    return {
        "overall": {
            "total_products": len(products),
            "discounted_count": len(overall_discounted),
            "discount_rate": round(len(overall_discounted) / len(products) * 100, 1) if products else 0,
            "avg_discount_pct": round(
                sum((1 - p.price / p.initial_price) * 100 for p in overall_discounted) / len(overall_discounted), 1
            ) if overall_discounted else 0,
        },
        "by_segment": by_segment,
    }
```

#### 4.4.2 build_market_analysis / build_keyword_market_analysis 교체

```python
# market_analyzer.py

# build_market_analysis (line 1147):
# Before:
"sns_pricing": analyze_sns_pricing(weighted_products),
# After:
"discount_analysis": analyze_discount_by_segment(weighted_products),

# build_keyword_market_analysis (line 1115):
# Before:
"sns_pricing": analyze_sns_pricing(weighted_products),
# After:
"discount_analysis": analyze_discount_by_segment(weighted_products),
```

`analyze_sns_pricing` 함수 자체는 삭제하지 않고 코드에 유지 (다른 곳에서 호출할 가능성 대비). 호출만 제거.

> **⚠️ 키 혼동 주의**: 기존 analysis_data에 `"discount_impact"` (line 1152)가 이미 있다. 이번에 추가하는 `"discount_analysis"`는 **별도의 새 키**로, `"sns_pricing"`을 대체한다. `"discount_impact"` (기존 할인 영향 분석)는 변경하지 않고 유지한다.
> ```
> 기존 유지: "discount_impact" → analyze_discount_impact() — 할인 제품 BSR/판매 영향
> 신규 대체: "discount_analysis" → analyze_discount_by_segment() — 세그먼트별 할인 전략 (sns_pricing 대체)
> ```

#### 4.4.3 Excel Sales & Pricing SNS 섹션 교체 (`excel_builder.py`)

**`_build_sales_pricing`** (line 672-839):

1. **변수 변경** (line 675):
```python
# Before:
sns = analysis_data.get("sns_pricing") or {}
# After:
disc_seg = analysis_data.get("discount_analysis") or {}
```

2. **빈 섹션 체크** (line 681):
```python
# Before:
if not any([sales, sns, lt, discount, promos]):
# After:
if not any([sales, disc_seg, lt, discount, promos]):
```

3. **SNS 분기 제거 + Discount Strategy 삽입** (line 810-839):
```python
# Before:
elif sns:
    # ... SNS Pricing 표 (line 810-839)

# After:
elif disc_seg:
    row += 2
    ws.cell(row=row, column=1, value="Discount Strategy by Segment")
    ws.cell(row=row, column=1).font = Font(bold=True, size=11)
    row += 1

    d_headers = ["Segment", "Total", "Discounted", "Disc. Rate", "Avg Disc%", "Max Disc%", "Avg Bought (Disc)", "Avg Bought (No Disc)"]
    for c, h in enumerate(d_headers, 1):
        ws.cell(row=row, column=c, value=h)
    _style_header_row(ws, row, 8)
    row += 1
    d_data_start = row

    by_seg = disc_seg.get("by_segment", {})
    tier_order = ["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]
    for tier_name in tier_order:
        seg = by_seg.get(tier_name)
        if seg is None:
            continue
        ws.cell(row=row, column=1, value=tier_name)
        ws.cell(row=row, column=2, value=seg.get("total", 0)).number_format = "#,##0"
        ws.cell(row=row, column=3, value=seg.get("discounted", 0)).number_format = "#,##0"
        ws.cell(row=row, column=4, value=f"{seg.get('discount_rate', 0)}%")
        ws.cell(row=row, column=5, value=f"{seg.get('avg_discount_pct', 0)}%")
        ws.cell(row=row, column=6, value=f"{seg.get('max_discount_pct', 0)}%")
        if seg.get("avg_bought_discounted") is not None:
            ws.cell(row=row, column=7, value=seg["avg_bought_discounted"]).number_format = "#,##0"
        if seg.get("avg_bought_non_discounted") is not None:
            ws.cell(row=row, column=8, value=seg["avg_bought_non_discounted"]).number_format = "#,##0"
        row += 1

    if row > d_data_start:
        _style_data_rows(ws, d_data_start, row - 1, 8)

    # Overall summary
    overall = disc_seg.get("overall", {})
    if overall:
        row += 1
        ws.cell(row=row, column=1, value="Overall").font = Font(bold=True)
        ws.cell(row=row, column=2, value=overall.get("total_products", 0))
        ws.cell(row=row, column=3, value=overall.get("discounted_count", 0))
        ws.cell(row=row, column=4, value=f"{overall.get('discount_rate', 0)}%")
        ws.cell(row=row, column=5, value=f"{overall.get('avg_discount_pct', 0)}%")
```

#### 4.4.4 HTML Sales & Pricing SNS→Discount 교체

**변수 변경** (line 1246):
```javascript
// Before:
const sns = data.analysis && data.analysis.sns_pricing;
// After:
const discSeg = data.analysis && data.analysis.discount_analysis;
```

**빈 섹션 체크** (line 1250):
```javascript
// Before:
if (!sv && !sns && !disc && !lt) { el.style.display = 'none'; return; }
// After:
if (!sv && !discSeg && !disc && !lt) { el.style.display = 'none'; return; }
```

**SNS KPI 카드 교체** (line 1322-1339):
```javascript
// Before:
} else if (ltEl) {
    if (sns && sns.sns_adoption_pct > 0) {
      // ... SNS Adoption cards ...
    }
}

// After:
} else if (ltEl) {
    if (discSeg && discSeg.overall) {
      const ov = discSeg.overall;
      ltEl.querySelector('.subsection-title').textContent = 'Discount Strategy by Segment';
      const kpiGrid = ltEl.querySelector('#lt-kpi-grid');
      if (kpiGrid) {
        const items = [
          ['Discount Rate', Math.round(ov.discount_rate) + '%', ov.discounted_count + ' of ' + ov.total_products],
          ['Avg Discount', ov.avg_discount_pct ? ov.avg_discount_pct.toFixed(1) + '%' : '-', ''],
        ];
        // Add per-segment KPI cards
        const segs = discSeg.by_segment || {};
        for (const [seg, sd] of Object.entries(segs)) {
          items.push([seg, sd.discount_rate + '%', sd.discounted + ' of ' + sd.total + ' discounted']);
        }
        kpiGrid.innerHTML = items.map(([label, value, sub]) =>
          `<div class="kpi-card" style="border-top:2px solid var(--color-sales-pricing)">
            <div class="kpi-label">${esc(label)}</div>
            <div class="kpi-value">${esc(String(value))}</div>
            ${sub ? '<div style="font-size:11px;color:var(--color-text-muted);margin-top:2px">' + esc(sub) + '</div>' : ''}
          </div>`
        ).join('');
      }
      // Segment comparison table
      const adTbody = ltEl.querySelector('#lt-ad-position-tbody');
      if (adTbody && discSeg.by_segment) {
        adTbody.innerHTML = Object.entries(discSeg.by_segment).map(([seg, sd]) =>
          `<tr>
            <td>${esc(seg)}</td>
            <td>${sd.total}</td>
            <td>${sd.discounted}</td>
            <td><strong>${sd.avg_discount_pct}%</strong></td>
            <td>${sd.avg_bought_discounted != null ? fmt(sd.avg_bought_discounted) : '-'}</td>
            <td>${sd.avg_bought_non_discounted != null ? fmt(sd.avg_bought_non_discounted) : '-'}</td>
          </tr>`
        ).join('');
      }
    }
}
```

#### 4.4.5 Gemini `generate_market_report` 분기 수정 (`gemini.py` line 297-306)

```python
# Before (line 303-306):
else:
    section9_title = "Subscribe & Save 가격 분석"
    section9_json = _dump("sns_pricing")
    section6_guidance = "SNS(Subscribe & Save) 채택 현황과 재구매 유도 효과"

# After:
else:
    section9_title = "세그먼트별 할인 전략 분석 (Budget/Mid/Premium/Luxury)"
    section9_json = _dump("discount_analysis")
    section6_guidance = "세그먼트별 할인율 현황, 할인/비할인 제품의 판매량 비교, 가격 전략 인사이트"
```

**MARKET_REPORT_PROMPT** 내 section 9 설명:
- 기존 SNS 관련 설명 → "세그먼트별 할인 전략을 분석하라: 할인 비율, 평균/최대 할인율, 할인 제품과 비할인 제품의 판매량 차이" 로 교체.

---

### 4.5 Phase 5: REQ-4 — Drilldown

#### 4.5.1 Phase 5-1: TableController 드릴다운 확장

**constructor** (line 860):
```javascript
// Before:
constructor({ data, columns, container, pageSize = 100, searchInput = null, filterInput = null }) {

// After:
constructor({ data, columns, container, pageSize = 100, searchInput = null, filterInput = null, drilldown = null }) {
    // ... existing init ...
    this.drilldown = drilldown;  // { triggerKey, matchFn, sourceData, columns }
    this._openDrilldownRow = null;
```

**_render** (line 930-941) — 드릴다운 셀에 클릭 핸들러:
```javascript
_render() {
    const start = (this.currentPage - 1) * this.pageSize;
    const pageData = this.filtered.slice(start, start + this.pageSize);
    const tbody = this.container.querySelector('tbody');
    tbody.innerHTML = pageData.map((row, idx) =>
      '<tr>' + this.columns.map(c => {
        const raw = typeof c.value === 'function' ? c.value(row) : row[c.key];
        let html = typeof c.render === 'function' ? c.render(raw, row) : esc(raw);
        const cls = c.className ? ` class="${c.className}"` : '';

        // Drilldown trigger
        if (this.drilldown && c.key === this.drilldown.triggerKey && raw > 0) {
          html = `<span class="drilldown-trigger" data-row-idx="${idx}">${html}</span>`;
        }

        return `<td${cls}>${html}</td>`;
      }).join('') + '</tr>'
    ).join('');

    // Attach drilldown click handlers (이벤트 위임으로 자식 요소 클릭도 안전 처리)
    if (this.drilldown) {
      tbody.querySelectorAll('.drilldown-trigger').forEach(el => {
        el.addEventListener('click', (e) => {
          const trigger = e.target.closest('.drilldown-trigger');
          if (!trigger) return;
          const rowIdx = parseInt(trigger.dataset.rowIdx);
          const row = pageData[rowIdx];
          this._toggleDrilldown(row, trigger.closest('tr'));
        });
      });
    }

    // ... existing pagination logic ...
}
```

**_toggleDrilldown 메서드** (신규):
```javascript
_toggleDrilldown(row, parentTr) {
  // Close existing drilldown
  if (this._openDrilldownRow) {
    this._openDrilldownRow.remove();
    if (this._openDrilldownRow._sourceRow === parentTr) {
      this._openDrilldownRow = null;
      return; // Toggle off
    }
  }

  const matched = this.drilldown.sourceData.filter(p => this.drilldown.matchFn(row, p));
  const maxRows = 20;
  const display = matched.slice(0, maxRows);
  const hasMore = matched.length > maxRows;

  const drilldownTr = document.createElement('tr');
  drilldownTr.className = 'drilldown-row';
  drilldownTr._sourceRow = parentTr;
  drilldownTr.innerHTML = `
    <td colspan="${this.columns.length}">
      <div class="drilldown-panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-weight:600;font-size:13px">${matched.length} products</span>
          <button class="drilldown-close" style="background:none;border:none;color:var(--color-text-muted);cursor:pointer;font-size:16px">&times;</button>
        </div>
        <table class="drilldown-table">
          <thead><tr>
            <th>ASIN</th><th>Title</th><th>Price</th><th>BSR</th><th>Rating</th><th>Bought/Mo</th>
          </tr></thead>
          <tbody>${display.map(p => `
            <tr>
              <td class="mono">${esc(p.asin)}</td>
              <td><a href="https://www.amazon.com/dp/${p.asin}" target="_blank" rel="noopener noreferrer" class="product-link">${truncate(p.title, 'lg')}</a></td>
              <td>${fmtPrice(p.price)}</td>
              <td>${fmt(p.bsr_category)}</td>
              <td>${fmt(p.rating, 1)}</td>
              <td>${p.bought_past_month != null ? fmt(p.bought_past_month) : '-'}</td>
            </tr>
          `).join('')}</tbody>
        </table>
        ${hasMore ? `<div style="text-align:center;color:var(--color-text-muted);font-size:12px;margin-top:8px">... and ${matched.length - maxRows} more</div>` : ''}
      </div>
    </td>`;

  drilldownTr.querySelector('.drilldown-close').addEventListener('click', () => {
    drilldownTr.remove();
    this._openDrilldownRow = null;
  });

  parentTr.after(drilldownTr);
  this._openDrilldownRow = drilldownTr;
}
```

**CSS**:
```css
.drilldown-row { background: var(--color-bg-input); }
.drilldown-panel { padding: 12px 16px; max-height: 300px; overflow-y: auto; }
.drilldown-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.drilldown-table th { font-size: 11px; color: var(--color-text-muted); text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--color-border); }
.drilldown-table td { padding: 4px 8px; border-bottom: 1px solid var(--color-border); }
.drilldown-trigger { cursor: pointer; color: var(--color-positive); text-decoration: underline; font-weight: 600; }
.drilldown-trigger:hover { color: var(--color-info); }
```

#### 4.5.2 Phase 5-2: Brand Positioning 드릴다운 (카테고리 리포트만)

**`renderBrandPositioning`** (line 1460-1473):

```javascript
// Before:
const btc = new TableController({
    data: bp.positioning,
    pageSize: 20,
    columns: [
        { key: 'brand', header: 'Brand', render: (v) => `<strong>${esc(v)}</strong>` },
        { key: 'product_count', header: 'Products' },
        // ...
    ],
    container: brandTableEl,
    searchInput: brandSearchInput,
});

// After:
const btc = new TableController({
    data: bp.positioning,
    pageSize: 20,
    columns: [
        { key: 'brand', header: 'Brand', render: (v) => `<strong>${esc(v)}</strong>` },
        { key: 'product_count', header: 'Products' },
        // ... remaining columns unchanged ...
    ],
    container: brandTableEl,
    searchInput: brandSearchInput,
    drilldown: {
        triggerKey: 'product_count',
        matchFn: (row, product) => product.brand === row.brand,
        sourceData: data.products,
    },
});
```

#### 4.5.3 Phase 5-3: Ingredient Ranking 드릴다운 (양쪽 리포트)

**`renderIngredientRanking`** (line 1608-1623):

```javascript
// After — TableController 생성 시 drilldown 추가:
const tc = new TableController({
    data: data.rankings,
    pageSize: 20,
    columns: [
        // ... existing columns ...
    ],
    container: tableEl,
    searchInput: searchInput,
    drilldown: {
        triggerKey: 'product_count',
        matchFn: (row, product) => {
            if (!product.ingredients) return false;
            return product.ingredients.some(i =>
                (i.common_name || i.name) === row.ingredient
            );
        },
        sourceData: data.products,
    },
});
```

#### 4.5.4 Phase 5-4: Category Summary 드릴다운 (양쪽 리포트)

Category Summary 테이블의 `type_count` 또는 `mention_count` 컬럼에 drilldown 추가:

```javascript
drilldown: {
    triggerKey: 'type_count',
    matchFn: (row, product) => {
        if (!product.ingredients) return false;
        return product.ingredients.some(i => i.category === row.category);
    },
    sourceData: data.products,
},
```

---

## 5. Security Considerations

- [x] URL은 고정 패턴 `https://www.amazon.com/dp/{ASIN}` — XSS 위험 낮음
- [x] `rel="noopener noreferrer"` 적용으로 target blank 보안 처리
- [x] ingredients_raw는 DB에서 가져온 텍스트 — `esc()` 함수로 이스케이프
- [x] Gemini source 값 검증: `{"featured", "inci", "both", ""}` 외 값은 `""` 처리
- [x] drilldown 패널 데이터는 이미 로드된 REPORT_DATA 사용 — 추가 네트워크 요청 없음

---

## 6. Error Handling

| Scenario | Handling |
|----------|----------|
| `initial_price` 없는 제품 | 할인 표시 생략, 세그먼트 분석에서 제외 |
| Gemini `source` 필드 누락 | Pydantic 기본값 `""` 적용, "Unknown" 표시 |
| `source` 값이 유효하지 않음 | 후처리로 `""` 처리 |
| `ingredients_raw` 없음 | 빈 문자열, Full INCI 컬럼 비어있음 |
| 드릴다운 매칭 제품 0건 | "No matching products found" 메시지 표시 |
| 할인 분석 대상 제품 0건 | Discount Strategy 섹션 숨김 |

---

## 7. Test Plan

### 7.1 Test Cases

| Phase | Test Case | Verification |
|-------|-----------|-------------|
| 1 | Excel Title 클릭 → Amazon 페이지 오픈 | openpyxl hyperlink 속성 확인 |
| 1 | HTML Title 클릭 → 새 탭 Amazon 오픈 | `target="_blank"` 동작 확인 |
| 2 | Initial Price 표시 + Discount% 일치 | 할인 있는/없는 제품 양쪽 확인 |
| 2 | SNS Price 컬럼 완전 제거 | Excel 헤더, HTML 컬럼 부재 확인 |
| 3 | Gemini 추출 결과에 source 포함 | API 호출 후 JSON 검증 |
| 3 | 레거시 캐시 데이터로 리포트 생성 | 에러 없이 동작 + "Unknown" 표시 |
| 3 | Featured Ingredients 카드 표시 | HTML 리포트 시각 확인 |
| 3 | Product Detail Full INCI 확장 | 클릭 시 전성분 펼침 확인 |
| 4 | SNS 분석 제거 + Discount 분석 대체 | Sales & Pricing 시트/섹션 확인 |
| 4 | 세그먼트별 할인율 데이터 정합성 | 수동 계산과 비교 |
| 5 | Brand Positioning product_count 드릴다운 | 클릭 → 인라인 패널 확인 |
| 5 | Ingredient Ranking product_count 드릴다운 | 클릭 → 해당 성분 포함 제품 확인 |
| 5 | 드릴다운 토글 (열기/닫기) | 같은 셀 재클릭 시 패널 닫힘 |
| - | 50+ 제품 리포트 성능 | 렌더링 시간 기존 대비 20% 이내 |
| - | 키워드 검색 리포트 동일 적용 | Brand Positioning 드릴다운 없음 확인 |
| 3 | 빈 ingredients + 빈 ingredients_raw 제품 | Featured 컬럼 빈칸, Full INCI 빈칸 표시 (에러 없음) |
| 4 | 세그먼트 전체가 initial_price 미수집인 경우 | 해당 세그먼트 discount 0%, "N/A" 아닌 0건 표시 확인 |
| 5 | 검색/필터 활성 상태에서 드릴다운 클릭 | pageData 기반 rowIdx 정확히 매칭 확인 |
| 5 | 드릴다운 매칭 결과 0건 | "No matching products found" 메시지 표시 |
| 3 | 키워드 플로우 ingredients_raw 매핑 | orchestrator.py 키워드 injection 블록에서 정상 전달 확인 |

### 7.2 Regression Tests

- 기존 Excel 12시트 / 키워드 9시트 구성 유지
- 기존 Chart.js 차트 렌더링 정상
- TableController 페이지네이션/정렬/검색 기존 기능 유지
- Gemini Market Report 생성 정상 (has_listing_tactics 양쪽 분기)

---

## 8. Implementation Order

```
Phase 1: REQ-2 (Title Hyperlinks)              [독립, 낮은 리스크]
  ├── excel_builder.py: Title 셀 hyperlink 속성
  ├── html_report_builder.py: 3개 섹션 title render → <a> 태그
  └── CSS: .product-link 스타일

Phase 2: REQ-1 + REQ-5 컬럼 (통합)             [시프트 상쇄]
  ├── excel_builder.py: headers 배열 수정 (SNS→Initial, +Full INCI)
  ├── excel_builder.py: 데이터 매핑 (col 5, 21, 22, 23)
  ├── html_report_builder.py: Price 복합 렌더링, sns_price 제거
  └── CSS: .price-original 스타일

Phase 3: REQ-3 (Ingredients Overhaul)          [핵심, 높은 복잡도]
  ├── 3-1: models.py 3개 변경
  ├── 3-2: product_db.py/orchestrator.py ingredients_raw 전달
  ├── 3-3: gemini.py PROMPT_TEMPLATE source 규칙 추가
  ├── 3-4: analyzer.py _aggregate_ingredients source 집계
  ├── 3-5a: html_report_builder.py _product_to_dict 직렬화
  ├── 3-5b: html_report_builder.py Ingredient Ranking Source 컬럼 + Featured 카드
  ├── 3-5c: html_report_builder.py Product Detail Featured/INCI UI
  ├── 3-6: excel_builder.py Featured + Full INCI 컬럼
  └── 3-7: 하위 호환 테스트

Phase 4: REQ-5 분석 계층 (SNS→Discount)        [Phase 2 이후]
  ├── 4-1: market_analyzer.py analyze_discount_by_segment() 신규
  ├── 4-2: market_analyzer.py build_*_analysis() 교체
  ├── 4-3: excel_builder.py Sales & Pricing SNS→Discount 테이블
  ├── 4-4: html_report_builder.py SNS→Discount 카드
  └── 4-5: gemini.py has_listing_tactics=False 분기 수정

Phase 5: REQ-4 (Drilldown)                    [HTML only]
  ├── 5-1: TableController drilldown 확장 (공통 인프라)
  ├── 5-2: Brand Positioning 적용 (카테고리만)
  ├── 5-3: Ingredient Ranking 적용 (양쪽)
  ├── 5-4: Category Summary 적용 (양쪽)
  └── CSS: .drilldown-* 스타일

의존성: Phase 1,2,3 병렬 가능 → Phase 4 (Phase 2 이후) → Phase 5
```

---

## 9. File Change Summary

| File | Phase | Changes |
|------|-------|---------|
| `models.py` | 3-1 | Ingredient.source, WeightedProduct.ingredients_raw, IngredientRanking.featured/inci count |
| `gemini.py` | 3-3, 4-5 | PROMPT_TEMPLATE source 규칙, generate_market_report SNS→Discount 분기 |
| `analyzer.py` | 3-4 | _aggregate_ingredients source 집계 |
| `market_analyzer.py` | 4-1, 4-2 | analyze_discount_by_segment 신규, build_*_analysis 교체 |
| `product_db.py` | - | 변경 불필요 (SELECT * 사용 확인 완료, verify only) |
| `orchestrator.py` | 3-2 | WeightedProduct.ingredients_raw 주입 (카테고리 line 806 뒤 + 키워드 line 1167 뒤) |
| `excel_builder.py` | 1, 2, 3-6, 4-3 | Title hyperlink, headers/col 변경, Featured+INCI 컬럼, Discount 테이블 |
| `html_report_builder.py` | 1, 2, 3-5, 4-4, 5 | Title link, Price 복합렌더, _product_to_dict, Source/Featured/INCI UI, Discount 카드, TableController drilldown |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial design — 5 phases covering all REQs with exact code-level specifications | Claude |
| 0.2 | 2026-03-11 | CTO Team 리뷰 8건 반영: (A-2) orchestrator.py ingredients_raw 주입 위치 명시 (카테고리 line 806, 키워드 line 1167), (G-1) ASIN 검증 가드 추가, (F-4) featured-ingredients-card HTML 삽입 위치 line 2119-2120, (C-3) _get_display_name 인라인 패턴 사용, (F-1) drilldown closest() 안전 처리, (Q-1) 5개 테스트 시나리오 추가, (Q-3) discount_impact vs discount_analysis 키 구분 명시, (A-3) product_db.py 변경 불필요 확인, (S-3) esc() 속성 이스케이프 보강 | CTO Team |
