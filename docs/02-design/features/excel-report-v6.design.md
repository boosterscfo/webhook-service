# Excel Report V6 Design Document

> **Summary**: excel_builder.py 단일 파일 수정으로 3개 신규 시트 추가, 기존 시트 보강, URL 버그 수정
>
> **Project**: webhook-service (amz_researcher)
> **Date**: 2026-03-09
> **Status**: Draft
> **Planning Doc**: [excel-report-v6.plan.md](../../01-plan/features/excel-report-v6.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. Product Detail URL 컬럼 버그 수정 (column 20 값 누락)
2. Consumer Voice / Badge Analysis 기존 시트에 미사용 데이터 섹션 추가
3. TAB_COLORS dict 통합 (하드코딩 제거)
4. Sales & Pricing, Brand Positioning, Marketing Keywords 3개 신규 시트 구현
5. 모든 변경을 `excel_builder.py` 단일 파일 내에서 완결

### 1.2 Design Principles

- **기존 패턴 준수**: 모든 신규 `_build_*` 함수는 기존 함수와 동일한 구조 유지 (`_write_title` -> headers -> data loop -> `_style_data_rows` -> `_set_column_widths`)
- **Graceful Degradation**: `analysis_data.get(key)`가 None이거나 빈 dict이면 해당 시트 생략 (에러 없음)
- **섹션 간 구분**: 멀티섹션 시트에서 섹션 사이 빈 행 2줄 + Bold 섹션 타이틀로 시각적 분리

---

## 2. Architecture

### 2.1 Data Flow

```
orchestrator.py
  └── build_market_analysis() → analysis_data dict (16 keys)
        └── build_excel(analysis_data=analysis_data)
              ├── _build_consumer_voice(wb, customer_voice)    ← 기존 보강
              ├── _build_badge_analysis(wb, badge_data)        ← 기존 보강
              ├── _build_sales_pricing(wb, analysis_data)      ← 신규
              ├── _build_brand_positioning(wb, analysis_data)  ← 신규
              └── _build_marketing_keywords(wb, analysis_data) ← 신규
```

### 2.2 analysis_data Key → Sheet Mapping

| analysis_data Key | Target Sheet | Section |
|-------------------|-------------|---------|
| `customer_voice` | Consumer Voice | BSR Top/Bottom Half (신규 섹션) |
| `badges` | Badge Analysis | Statistical Test + Acquisition Threshold (신규 섹션) |
| `sales_volume` | **Sales & Pricing** | Section A: Top Sellers, Section B: Sales by Price Tier |
| `sns_pricing` | **Sales & Pricing** | Section C: SNS Pricing Summary |
| `discount_impact` | **Sales & Pricing** | Section D: Discount Impact |
| `promotions` | **Sales & Pricing** | Section E: Coupon Types |
| `brand_positioning` | **Brand Positioning** | Section A: Brand Positioning |
| `manufacturer` | **Brand Positioning** | Section B: Manufacturer Profile, Section C: Market Concentration |
| `title_keywords` | **Marketing Keywords** | Section A: Title Keyword Performance |
| `price_tier_analysis` | **Marketing Keywords** | Section B: Price Tier Top Ingredients |

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `_build_sales_pricing()` | `analysis_data["sales_volume"]`, `["sns_pricing"]`, `["discount_impact"]`, `["promotions"]` | 4개 분석 결과를 하나의 시트로 통합 |
| `_build_brand_positioning()` | `analysis_data["brand_positioning"]`, `["manufacturer"]` | 브랜드/제조사 데이터 통합 뷰 |
| `_build_marketing_keywords()` | `analysis_data["title_keywords"]`, `["price_tier_analysis"]` | 키워드 + 가격대별 성분 |

---

## 3. TAB_COLORS Consolidation

### 3.1 Before (Current)

```python
TAB_COLORS = {
    "Ingredient Ranking": "1B2A4A",
    "Category Summary": "2E86AB",
    "Product Detail": "4CAF50",
    "Raw - Search Results": "FF6B35",
    "Raw - Product Detail": "9B59B6",
    "Rising Products": "00BCD4",
    "Market Insight": "E91E63",
}
# _build_consumer_voice: ws.sheet_properties.tabColor = "FF9800"  (하드코딩)
# _build_badge_analysis: ws.sheet_properties.tabColor = "673AB7"  (하드코딩)
```

### 3.2 After

```python
TAB_COLORS = {
    "Market Insight": "E91E63",
    "Consumer Voice": "FF9800",
    "Badge Analysis": "673AB7",
    "Sales & Pricing": "009688",       # Teal — Insight 그룹
    "Brand Positioning": "3F51B5",     # Indigo — Analysis 그룹
    "Marketing Keywords": "795548",    # Brown — Analysis 그룹
    "Ingredient Ranking": "1B2A4A",
    "Category Summary": "2E86AB",
    "Rising Products": "00BCD4",
    "Product Detail": "4CAF50",
    "Raw - Search Results": "FF6B35",
    "Raw - Product Detail": "9B59B6",
}
```

색상 그룹 논리:
- **Insight (Warm)**: E91E63 (Red), FF9800 (Orange), 673AB7 (Purple), 009688 (Teal)
- **Analysis (Cool)**: 3F51B5 (Indigo), 795548 (Brown), 1B2A4A (Navy), 2E86AB (Blue), 00BCD4 (Cyan)
- **Raw (Accent)**: 4CAF50 (Green), FF6B35 (Orange), 9B59B6 (Purple)

### 3.3 변경 사항

`_build_consumer_voice()`와 `_build_badge_analysis()`에서 하드코딩된 탭 색상을 `TAB_COLORS["Consumer Voice"]`, `TAB_COLORS["Badge Analysis"]`로 교체.

---

## 4. Bug Fix: Product Detail URL Column

### 4.1 현상

`_build_product_detail()` 헤더(row 4, column 20)에 "URL" 존재하나, 데이터 루프에서 column 20에 값을 쓰는 코드 없음.

### 4.2 수정

`_build_product_detail()` 데이터 루프 내 column 19 (Ingredients Found) 이후에 추가:

```python
# URL column (column 20)
url = f"https://www.amazon.com/dp/{p.asin}"
ws.cell(row=row, column=20, value=url)
```

위치: line ~240, `ws.cell(row=row, column=19, value=ingredients_str)` 직후.

---

## 5. Consumer Voice Enhancement

### 5.1 신규 섹션: BSR Top Half vs Bottom Half

기존 Positive/Negative 키워드 테이블 아래에 추가.

**데이터 소스**: `customer_voice_data["bsr_top_half_positive"]`, `["bsr_top_half_negative"]`, `["bsr_bottom_half_positive"]`, `["bsr_bottom_half_negative"]`

각 key의 구조: `dict[str, int]` (keyword -> count)

### 5.2 섹션 레이아웃

기존 코드의 마지막 데이터 행(`row`) 이후:

```
row += 2  (빈 행 2줄)

[row]     "BSR Correlation: Top Half vs Bottom Half" (Bold, TITLE style)
[row+1]   headers: ["Keyword", "Type", "Top Half Count", "Bottom Half Count", "Difference"]

데이터: bsr_top_half_positive + bsr_top_half_negative 키를 순회
  - Keyword: 키워드명
  - Type: "Positive" 또는 "Negative"
  - Top Half Count: bsr_top_half_{type}[keyword] (없으면 0)
  - Bottom Half Count: bsr_bottom_half_{type}[keyword] (없으면 0)
  - Difference: top - bottom (양수면 Top 제품에서 더 자주 언급)
```

### 5.3 Edge Cases

- `bsr_top_half_positive`가 None 또는 빈 dict이면 섹션 전체 스킵
- Top Half와 Bottom Half 모두 0인 키워드는 행 생략

---

## 6. Badge Analysis Enhancement

### 6.1 신규 섹션 A: Statistical Test

기존 Badge Type Distribution 섹션 아래에 추가.

**데이터 소스**: `badge_data["stat_test_bsr"]`

구조:
```python
{
    "p_value": float | None,
    "significant": bool | None,
    "u_statistic": float | None,
    "note": str  # "insufficient_sample" 또는 "test_failed" (실패 시)
}
```

### 6.2 섹션 A 레이아웃

```
row += 2  (빈 행 2줄)

[row]     "Statistical Test: Badge vs No-Badge BSR" (Bold)
[row+1]   "Test" | "Value"
[row+2]   "Method" | "Mann-Whitney U Test"
[row+3]   "U Statistic" | {u_statistic}
[row+4]   "p-value" | {p_value}  (number_format: "0.0000")
[row+5]   "Significant (p < 0.05)" | "Yes" / "No" / "N/A"
```

`stat_test_bsr`가 None이거나 `note` == "insufficient_sample" 또는 "test_failed"이면:
- "p-value" 행에 note 문자열 표시, Significant는 "N/A"

### 6.3 신규 섹션 B: Acquisition Threshold

**데이터 소스**: `badge_data["acquisition_threshold"]`

구조:
```python
{
    "min_reviews": int,
    "median_reviews": int,
    "min_rating": float,
    "median_rating": float,
}
```

### 6.4 섹션 B 레이아웃

```
row += 2  (빈 행 2줄)

[row]     "Badge Acquisition Threshold" (Bold)
[row+1]   "Metric" | "Value"
[row+2]   "Minimum Reviews" | {min_reviews}  (number_format: "#,##0")
[row+3]   "Median Reviews" | {median_reviews}  (number_format: "#,##0")
[row+4]   "Minimum Rating" | {min_rating}
[row+5]   "Median Rating" | {median_rating}
```

`acquisition_threshold`가 빈 dict이면 섹션 스킵.

---

## 7. New Sheet: Sales & Pricing

### 7.1 Function Signature

```python
def _build_sales_pricing(wb: Workbook, analysis_data: dict) -> None:
```

### 7.2 Data Extraction

```python
sales = analysis_data.get("sales_volume") or {}
sns = analysis_data.get("sns_pricing") or {}
discount = analysis_data.get("discount_impact") or {}
promos = analysis_data.get("promotions") or {}

# 4개 모두 비어있으면 시트 생성하지 않음
if not any([sales, sns, discount, promos]):
    return
```

### 7.3 Sheet Structure

**Title**: "Sales & Pricing — Revenue, Discounts & Promotions"
**Subtitle**: "판매량, SNS 할인, 쿠폰 분석 통합 뷰"
**Tab Color**: `TAB_COLORS["Sales & Pricing"]` = `"009688"`

#### Section A: Top Sellers (row 4~)

**조건**: `sales.get("top_sellers")` 존재 시

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | ASIN | 14 | text | `top_sellers[i]["asin"]` |
| B | Brand | 16 | text | `top_sellers[i]["brand"]` |
| C | Title | 40 | text | `top_sellers[i]["title"]` |
| D | Bought/Mo | 12 | `#,##0` | `top_sellers[i]["bought_past_month"]` |
| E | Price | 10 | `$#,##0.00` | `top_sellers[i]["price"]` |
| F | BSR | 10 | `#,##0` | `top_sellers[i]["bsr"]` |

Row offset: title(1) + subtitle(2) + section_title(3) + header(4) + data(5~14) = max 14 rows

#### Section B: Sales by Price Tier (row offset: last_row + 3)

**조건**: `sales.get("sales_by_price_tier")` 존재 시

Section title: "Sales by Price Tier" (Bold)

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Price Tier | 20 | text | tier name |
| B | Count | 10 | `#,##0` | `tier["count"]` |
| C | Total Sales | 14 | `#,##0` | `tier["total_sales"]` |
| D | Avg Sales | 12 | `#,##0` | `tier["avg_sales"]` |

Tier order: `["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]`

#### Section C: SNS Pricing Summary (row offset: last_row + 3)

**조건**: `sns` dict가 비어있지 않을 때

Section title: "Subscribe & Save Pricing" (Bold)

Key-Value 세로 테이블:

| Metric | Value | Format | Source |
|--------|-------|--------|--------|
| SNS Adoption Rate | {sns_adoption_pct}% | text | `sns["sns_adoption_pct"]` |
| Avg SNS Discount | {avg_discount_pct}% | text | `sns["avg_discount_pct"]` |
| SNS Avg Bought/Mo | {value} | `#,##0` | `sns["retention_signal"]["sns_avg_bought"]` |
| No-SNS Avg Bought/Mo | {value} | `#,##0` | `sns["retention_signal"]["no_sns_avg_bought"]` |
| With SNS Count | {value} | `#,##0` | `sns["with_sns_count"]` |
| Without SNS Count | {value} | `#,##0` | `sns["without_sns_count"]` |

Column widths: A=25, B=15

#### Section D: Discount Impact (row offset: last_row + 3)

**조건**: `discount.get("tiers")` 존재 시

Section title: "Discount Impact on BSR" (Bold)

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Discount Tier | 22 | text | tier name |
| B | Count | 10 | `#,##0` | `tier["count"]` |
| C | Avg BSR | 12 | `#,##0` | `tier["avg_bsr"]` |
| D | Avg Bought | 12 | `#,##0` | `tier["avg_bought"]` |
| E | Avg Price | 10 | `$#,##0.00` | `tier["avg_price"]` |

Tier order: `["No Discount (0%)", "Light (1-15%)", "Medium (16-30%)", "Heavy (31%+)"]`

#### Section E: Coupon Types (row offset: last_row + 3)

**조건**: `promos.get("coupon_types")` 존재하고 비어있지 않을 때

Section title: "Coupon Type Distribution" (Bold)

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Coupon | 30 | text | `ct["coupon"]` |
| B | Count | 10 | `#,##0` | `ct["count"]` |

### 7.4 Column Widths (최종)

Sheet 전체 column widths는 Section A 기준으로 설정 (가장 넓은 섹션):

```python
_set_column_widths(ws, {
    "A": 22, "B": 16, "C": 40, "D": 14, "E": 12, "F": 10,
})
```

### 7.5 Freeze Panes

`ws.freeze_panes = "A5"` (Section A 헤더 아래)

---

## 8. New Sheet: Brand Positioning

### 8.1 Function Signature

```python
def _build_brand_positioning_sheet(wb: Workbook, analysis_data: dict) -> None:
```

Note: 함수명을 `_build_brand_positioning_sheet`으로 하여 `analyze_brand_positioning` 분석 함수와 구분.

### 8.2 Data Extraction

```python
positioning = analysis_data.get("brand_positioning")  # list[dict]
mfr = analysis_data.get("manufacturer") or {}          # dict

if not positioning and not mfr:
    return
```

### 8.3 Sheet Structure

**Title**: "Brand Positioning — Price vs BSR Analysis"
**Subtitle**: "브랜드/제조사별 가격 포지셔닝 및 시장 성과 비교"
**Tab Color**: `TAB_COLORS["Brand Positioning"]` = `"3F51B5"`

#### Section A: Brand Positioning (row 4~)

**조건**: `positioning` list가 비어있지 않을 때

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Brand | 20 | text | `bp["brand"]` |
| B | Products | 10 | `#,##0` | `bp["product_count"]` |
| C | Avg Price | 12 | `$#,##0.00` | `bp["avg_price"]` |
| D | Avg BSR | 12 | `#,##0` | `bp["avg_bsr"]` |
| E | Avg Rating | 10 | `0.00` | `bp["avg_rating"]` |
| F | Total Reviews | 14 | `#,##0` | `bp["total_reviews"]` |
| G | Segment | 18 | text | `bp["segment"]` |

데이터는 `brand_positioning` list를 순회 (이미 avg_bsr 오름차순 정렬됨).

#### Section B: Manufacturer Profile (row offset: last_row + 3)

**조건**: `mfr.get("top_manufacturers")` 존재 시

Section title: "Top Manufacturers" (Bold)

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Manufacturer | 24 | text | `m["manufacturer"]` |
| B | Products | 10 | `#,##0` | `m["product_count"]` |
| C | Avg BSR | 12 | `#,##0` | `m["avg_bsr"]` |
| D | Avg Price | 12 | `$#,##0.00` | `m["avg_price"]` |
| E | Avg Rating | 10 | `0.00` | `m["avg_rating"]` |
| F | Total Bought | 14 | `#,##0` | `m["total_bought"]` |
| G | K-Beauty | 10 | text | `"Y"` if `m["is_kbeauty"]` else `""` |

#### Section C: Market Concentration (row offset: last_row + 3)

**조건**: `mfr.get("market_concentration")` 존재 시

Section title: "Market Concentration" (Bold)

Key-Value 세로 테이블:

| Metric | Value | Format | Source |
|--------|-------|--------|--------|
| Total Manufacturers | {value} | `#,##0` | `mfr["total_manufacturers"]` |
| Top 10 Products | {value} | `#,##0` | `mc["top10_products"]` |
| Total Products | {value} | `#,##0` | `mc["total_products"]` |
| Top 10 Market Share | {value}% | text | `mc["top10_share_pct"]` |

### 8.4 Column Widths

```python
_set_column_widths(ws, {
    "A": 24, "B": 10, "C": 12, "D": 12, "E": 10, "F": 14, "G": 18,
})
```

### 8.5 Freeze Panes

`ws.freeze_panes = "A5"`

---

## 9. New Sheet: Marketing Keywords

### 9.1 Function Signature

```python
def _build_marketing_keywords(wb: Workbook, analysis_data: dict) -> None:
```

### 9.2 Data Extraction

```python
kw_data = analysis_data.get("title_keywords") or {}
tier_data = analysis_data.get("price_tier_analysis") or {}

if not kw_data and not tier_data:
    return
```

### 9.3 Sheet Structure

**Title**: "Marketing Keywords — Title Keyword Performance"
**Subtitle**: "제품 타이틀 내 마케팅 키워드별 BSR/판매량 + 가격대별 Top 성분"
**Tab Color**: `TAB_COLORS["Marketing Keywords"]` = `"795548"`

#### Section A: Title Keyword Performance (row 4~)

**조건**: `kw_data.get("keyword_analysis")` 존재 시

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Keyword | 22 | text | keyword name |
| B | Count | 10 | `#,##0` | `metrics["count"]` |
| C | Avg BSR | 12 | `#,##0` | `metrics["avg_bsr"]` |
| D | Avg Bought/Mo | 14 | `#,##0` | `metrics["avg_bought"]` |

데이터: `kw_data["keyword_analysis"]` dict를 순회. 이미 avg_bsr 오름차순 정렬됨.

#### Section B: Price Tier Top Ingredients (row offset: last_row + 3)

**조건**: `tier_data` dict가 비어있지 않을 때

Section title: "Price Tier Top Ingredients" (Bold)

| Column | Header | Width | Format | Source |
|--------|--------|-------|--------|--------|
| A | Price Tier | 20 | text | tier name |
| B | Products | 10 | `#,##0` | `tier["product_count"]` |
| C | Top Ingredients | 50 | text (wrap) | `", ".join(ing["name"] for ing in tier["top_ingredients"])` |

Tier order: `["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]`

### 9.4 Column Widths

```python
_set_column_widths(ws, {
    "A": 22, "B": 10, "C": 14, "D": 14,
})
```

Note: Section B의 column C (Top Ingredients)가 50으로 더 넓지만, Section A 기준 4열까지만 width 설정. Section B에서는 A~C만 사용하므로 C열은 Section A에서 14, Section B에서는 내용이 wrap_text로 처리.

### 9.5 Freeze Panes

`ws.freeze_panes = "A5"`

---

## 10. build_excel() Modification

### 10.1 Sheet Creation Order

`build_excel()` 함수 내에서 시트 생성 순서 변경:

```python
# === Insight tabs ===
_build_ingredient_ranking(wb, keyword, rankings, len(weighted_products))
if market_report:
    _build_market_insight(wb, keyword, market_report)
if analysis_data:
    customer_voice = analysis_data.get("customer_voice")
    if customer_voice:
        _build_consumer_voice(wb, customer_voice)
    badge_data = analysis_data.get("badges")
    if badge_data:
        _build_badge_analysis(wb, badge_data)
    # V6 신규 시트
    _build_sales_pricing(wb, analysis_data)

# === Analysis tabs ===
if analysis_data:
    _build_brand_positioning_sheet(wb, analysis_data)
    _build_marketing_keywords(wb, analysis_data)
_build_category_summary(wb, categories)
if rising_products:
    _build_rising_products(wb, rising_products)
_build_product_detail(wb, weighted_products)

# === Raw tabs ===
_build_raw_search(wb, keyword, search_products)
_build_raw_detail(wb, details)
```

### 10.2 desired_order Update

```python
desired_order = [
    "Market Insight",
    "Consumer Voice",
    "Badge Analysis",
    "Sales & Pricing",        # V6 신규
    "Brand Positioning",      # V6 신규
    "Marketing Keywords",     # V6 신규
    "Ingredient Ranking",
    "Category Summary",
    "Rising Products",
    "Product Detail",
    "Raw - Search Results",
    "Raw - Product Detail",
]
```

---

## 11. Edge Cases & Error Handling

### 11.1 analysis_data 자체가 None

`build_excel()`에서 `if analysis_data:` 조건 안에서만 신규 함수 호출. None이면 기존 시트만 생성.

### 11.2 개별 분석 키가 None 또는 빈 dict

각 `_build_*` 함수 내부에서 필요한 키를 `.get()`으로 추출하고, 모든 키가 비어있으면 `return` (시트 미생성).

### 11.3 리스트 데이터가 빈 리스트

- `top_sellers: []` -> Section A 헤더만 표시, 데이터 없음
- `brand_positioning: []` -> Section A 스킵, Section B/C만 표시

### 11.4 숫자 필드가 None

모든 숫자 셀은 `if value is not None:` 조건 후 기록. None이면 셀 비워둠. 기존 패턴과 동일.

### 11.5 Section 간 row offset 계산

멀티섹션 시트에서 각 섹션의 시작 row는 이전 섹션의 마지막 데이터 row + 3 (빈 행 2줄 + 섹션 타이틀 1줄).

```python
# 패턴:
row += 2  # 빈 행 2줄
section_title_row = row
ws.cell(row=row, column=1, value="Section Title")
ws.cell(row=row, column=1).font = Font(bold=True, size=11)
row += 1  # 헤더 행
# headers...
row += 1  # 데이터 시작
```

---

## 12. Implementation Order

```
Phase 1: 버그 수정 + 기존 보강
├─ 1. [ ] TAB_COLORS dict에 Consumer Voice, Badge Analysis, 신규 3개 시트 추가
│        하드코딩 → dict 참조로 변경 (_build_consumer_voice, _build_badge_analysis)
├─ 2. [ ] Product Detail URL 컬럼 수정 (column 20에 Amazon URL 기록)
├─ 3. [ ] Consumer Voice BSR 상관 섹션 추가 (_build_consumer_voice 함수 하단)
└─ 4. [ ] Badge Analysis 통계 검정 + threshold 섹션 추가 (_build_badge_analysis 함수 하단)

Phase 2: 신규 시트 구현
├─ 5. [ ] _build_sales_pricing() 함수 구현 (5개 섹션)
├─ 6. [ ] _build_brand_positioning_sheet() 함수 구현 (3개 섹션)
├─ 7. [ ] _build_marketing_keywords() 함수 구현 (2개 섹션)
└─ 8. [ ] build_excel() 수정: 신규 함수 호출 + desired_order 업데이트
```

---

## 13. Final Sheet Layout

| Order | Sheet Name | Tab Color | Group | Status |
|-------|-----------|-----------|-------|--------|
| 1 | Market Insight | E91E63 | Insight | Existing |
| 2 | Consumer Voice | FF9800 | Insight | Enhanced |
| 3 | Badge Analysis | 673AB7 | Insight | Enhanced |
| 4 | Sales & Pricing | 009688 | Insight | **New** |
| 5 | Brand Positioning | 3F51B5 | Analysis | **New** |
| 6 | Marketing Keywords | 795548 | Analysis | **New** |
| 7 | Ingredient Ranking | 1B2A4A | Analysis | Existing |
| 8 | Category Summary | 2E86AB | Analysis | Existing |
| 9 | Rising Products | 00BCD4 | Analysis | Existing |
| 10 | Product Detail | 4CAF50 | Raw | Bug Fixed |
| 11 | Raw - Search Results | FF6B35 | Raw | Existing |
| 12 | Raw - Product Detail | 9B59B6 | Raw | Existing |

---

## 14. Test Plan

### 14.1 Test Scope

| Type | Target | Method |
|------|--------|--------|
| Manual | 전체 엑셀 파일 생성 | `uv run python -c "..."` 또는 실제 `/amz` 실행 |
| Manual | 각 시트 데이터 정확성 | 엑셀 파일 열어서 확인 |
| Edge | analysis_data=None | build_excel() 호출 시 에러 없음 확인 |
| Edge | 개별 키 빈 dict | 해당 시트 생략 확인 |

### 14.2 Key Test Cases

- [ ] Product Detail 시트 column 20 (URL)에 `https://www.amazon.com/dp/{ASIN}` 형식 출력
- [ ] Consumer Voice 시트 하단에 BSR Top/Bottom Half 섹션 존재
- [ ] Badge Analysis 시트 하단에 Statistical Test + Acquisition Threshold 섹션 존재
- [ ] Sales & Pricing 시트에 5개 섹션 (Top Sellers, Price Tier, SNS, Discount, Coupon) 표시
- [ ] Brand Positioning 시트에 3개 섹션 (Brand, Manufacturer, Concentration) 표시
- [ ] Marketing Keywords 시트에 2개 섹션 (Keywords, Ingredients) 표시
- [ ] TAB_COLORS dict에서 모든 시트 색상 관리 (하드코딩 없음)
- [ ] analysis_data 전체가 None일 때 기존 시트만 정상 생성
- [ ] 시트 탭 순서가 desired_order 대로 정렬

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-09 | Initial draft | CTO Lead |
