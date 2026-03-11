# report-enhancement-v7 Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: amz_researcher (webhook-service)
> **Analyst**: Claude (gap-detector)
> **Date**: 2026-03-11
> **Design Doc**: [report-enhancement-v7.design.md](../02-design/features/report-enhancement-v7.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design document의 5개 REQ (5 Phase) 구현 완성도를 검증한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/report-enhancement-v7.design.md`
- **Implementation Files**: `models.py`, `orchestrator.py`, `gemini.py`, `analyzer.py`, `excel_builder.py`, `html_report_builder.py`, `market_analyzer.py`
- **Analysis Date**: 2026-03-11
- **Comparison Items**: 60

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **100%** | ✅ |

```
+-------------------------------------------------+
|  Overall Match Rate: 100%                       |
+-------------------------------------------------+
|  MATCH:          60 items (100%)                 |
|  PARTIAL:         0 items (  0%)                 |
|  MISSING:         0 items (  0%)                 |
|  CHANGED:         0 items (  0%)                 |
+-------------------------------------------------+
```

---

## 3. Gap Analysis by REQ / Phase

### 3.1 REQ-1 (Phase 1): Title Hyperlinks

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 1 | Excel Product Detail: title cell hyperlink `https://www.amazon.com/dp/{ASIN}` | `excel_builder.py:232-234` - ASIN_PATTERN guard + hyperlink + "Hyperlink" style | MATCH |
| 2 | Excel Raw Search: title cell hyperlink | `excel_builder.py:304-306` - identical pattern | MATCH |
| 3 | HTML Product Detail: `<a>` tag with `target="_blank" rel="noopener noreferrer"` + `isValidAsin` guard | `html_report_builder.py:1904-1911` - exact match | MATCH |
| 4 | HTML Raw Search: same pattern with `truncate(v, 'xl')` | `html_report_builder.py:1980-1987` - exact match | MATCH |
| 5 | HTML Rising Products: title wrapped in `<a>` with ASIN validation | `html_report_builder.py:1875` - exact match | MATCH |
| 6 | HTML drilldown panel: product links in drill table | `html_report_builder.py:1064` - exact match | MATCH |
| 7 | CSS `.product-link` style (color: positive, no decoration, hover underline) | `html_report_builder.py:616-617` - exact match | MATCH |
| 8 | `isValidAsin()` JS function + Python `ASIN_PATTERN` regex | `html_report_builder.py:776`, `excel_builder.py:26` - exact match | MATCH |

**Phase 1 Score: 8/8 (100%)**

---

### 3.2 REQ-2 (Phase 2): Initial Price + Discount Rate, SNS Removal

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 9 | Excel headers: `SNS Price` -> `Initial Price` at col 5 | `excel_builder.py:209` - "Initial Price" at position 5 | MATCH |
| 10 | Excel col 5 data: `p.initial_price` with `$#,##0.00` format | `excel_builder.py:237-238` | MATCH |
| 11 | Excel Discount%: `(1 - price / initial_price) * 100` at col 16 | `excel_builder.py:252-254` - includes `initial_price > 0` guard | MATCH |
| 12 | HTML Product Detail: SNS Price column removed | No `sns_price` header in renderProductDetail columns | MATCH |
| 13 | HTML Price: composite render with `<span class="price-original">` + discount badge | `html_report_builder.py:1913-1918` - exact match | MATCH |
| 14 | CSS `.price-original` (line-through, muted, 0.85em) | `html_report_builder.py:512` - exact match | MATCH |
| 15 | Excel col_count: 22 -> 23 | `excel_builder.py:196` (`col_count = 23` via headers array length) | MATCH |
| 16 | Column widths updated (E:12, U:40, V:50, W:14) | `excel_builder.py:270-276` - exact match | MATCH |

**Phase 2 Score: 8/8 (100%)**

---

### 3.3 REQ-3 (Phase 3): Featured vs INCI Ingredients Separation

#### 3.3.1 Model Changes

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 17 | `Ingredient.source: str = ""` with values "featured"/"inci"/"both"/"" | `models.py:76` - exact match | MATCH |
| 18 | `WeightedProduct.ingredients_raw: str = ""` | `models.py:132` - exact match | MATCH |
| 19 | `IngredientRanking.featured_count: int = 0` | `models.py:145` - exact match | MATCH |
| 20 | `IngredientRanking.inci_only_count: int = 0` | `models.py:146` - exact match | MATCH |

#### 3.3.2 Data Pipeline

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 21 | orchestrator.py category flow: `wp.ingredients_raw = bp.ingredients or ""` | `orchestrator.py:808` - exact match | MATCH |
| 22 | orchestrator.py keyword flow: `wp.ingredients_raw = str(kp.get("ingredients", "") or "")` | `orchestrator.py:1171` - exact match | MATCH |

#### 3.3.3 Gemini Prompt

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 23 | PROMPT_TEMPLATE rule 7: source classification ("featured"/"inci"/"both") | `gemini.py:73-77` - exact match | MATCH |
| 24 | JSON example includes `"source"` field | `gemini.py:84-85` - exact match | MATCH |

#### 3.3.4 Analyzer

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 25 | `_aggregate_ingredients`: initialize `featured_count: 0`, `inci_only_count: 0` | `analyzer.py:78-79` - exact match | MATCH |
| 26 | source counting: `if ing.source in ("featured", "both")` -> featured_count++ | `analyzer.py:87-88` - exact match | MATCH |
| 27 | source counting: `elif ing.source == "inci"` -> inci_only_count++ | `analyzer.py:89-90` - exact match | MATCH |
| 28 | `IngredientRanking` constructor: pass featured_count, inci_only_count | `analyzer.py:114-115` - exact match | MATCH |

#### 3.3.5 HTML Serialization & Rendering

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 29 | `_product_to_dict`: ingredients include `"source": i.source` | `html_report_builder.py:73` - exact match | MATCH |
| 30 | `_product_to_dict`: include `"ingredients_raw": p.ingredients_raw` | `html_report_builder.py:76` - exact match | MATCH |
| 31 | `_ranking_to_dict`: include `featured_count`, `inci_only_count` | `html_report_builder.py:34-35` - exact match | MATCH |
| 32 | Ingredient Ranking: Source column with badge rendering | `html_report_builder.py:1753-1761` - exact match | MATCH |
| 33 | Featured Ingredients card (top 10, kpi-grid) | `html_report_builder.py:1696-1713` - exact match | MATCH |
| 34 | HTML template: `<div id="featured-ingredients-card">` before ingredient-hero | `html_report_builder.py:2329` - exact match | MATCH |
| 35 | Product Detail: Featured column (source filter + legacy fallback) | `html_report_builder.py:1936-1946` - exact match | MATCH |
| 36 | Product Detail: Full INCI column (truncate 80 + expand onclick) | `html_report_builder.py:1948-1954` - exact match | MATCH |
| 37 | CSS `.inci-expand` + `.inci-expand.expanded` | `html_report_builder.py:498-499` - exact match | MATCH |

#### 3.3.6 Excel

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 38 | col 21 "Featured Ingredients": source filter with legacy fallback | `excel_builder.py:222-228, 262` - exact match | MATCH |
| 39 | col 22 "Full Ingredients (INCI)": `p.ingredients_raw` | `excel_builder.py:263` - exact match | MATCH |
| 40 | col 23 "URL": shifted from col 22 | `excel_builder.py:264-265` - exact match | MATCH |

**Phase 3 Score: 24/24 (100%)**

---

### 3.4 REQ-5 (Phase 4): SNS -> Discount Segment Analysis

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 41 | `analyze_discount_by_segment()` function signature and logic | `market_analyzer.py:399-455` - exact match to design | MATCH |
| 42 | Return structure: `{overall: {total_products, discounted_count, discount_rate, avg_discount_pct}, by_segment: {...}}` | `market_analyzer.py:445-455` - exact match | MATCH |
| 43 | `build_market_analysis`: `"discount_analysis"` key replaces `"sns_pricing"` | `market_analyzer.py:1174` - exact match | MATCH |
| 44 | `build_keyword_market_analysis`: same replacement | `market_analyzer.py:1206` - exact match | MATCH |
| 45 | `analyze_sns_pricing` function retained (not deleted) | `market_analyzer.py:316` - still exists, call removed | MATCH |
| 46 | Excel `_build_sales_pricing`: `disc_seg = analysis_data.get("discount_analysis")` | `excel_builder.py:690` - exact match | MATCH |
| 47 | Excel empty check: `if not any([sales, disc_seg, lt, discount, promos])` | `excel_builder.py:696` - exact match | MATCH |
| 48 | Excel "Discount Strategy by Segment" table with 8 headers | `excel_builder.py:827-853` - exact match | MATCH |
| 49 | Excel overall summary row | `excel_builder.py:860-867` - exact match | MATCH |
| 50 | HTML: `discSeg = data.analysis && data.analysis.discount_analysis` | `html_report_builder.py:1343` - exact match | MATCH |
| 51 | HTML empty check: `if (!sv && !discSeg && !disc && !lt)` | `html_report_builder.py:1347` - exact match | MATCH |
| 52 | HTML KPI cards + segment comparison table | `html_report_builder.py:1419-1450` - exact match | MATCH |
| 53 | `gemini.py`: `has_listing_tactics=False` -> `section9_title = "세그먼트별 할인 전략 분석"` | `gemini.py:310-312` - exact match | MATCH |
| 54 | `gemini.py`: `section9_json = _dump("discount_analysis")` | `gemini.py:311` - exact match | MATCH |

**Phase 4 Score: 14/14 (100%)**

---

### 3.5 REQ-4 (Phase 5): Drilldown for Aggregated Items

| # | Design Spec | Implementation | Status |
|---|-------------|---------------|--------|
| 55 | TableController: `drilldown` parameter in constructor | `html_report_builder.py:879` - exact match | MATCH |
| 56 | `_toggleDrilldown` method with close/toggle/panel/limit 20 | `html_report_builder.py:1032-1082` - exact match | MATCH |
| 57 | Brand Positioning: drilldown on `product_count`, matchFn by brand | `html_report_builder.py:1583-1587` - exact match | MATCH |
| 58 | Ingredient Ranking: drilldown on `product_count`, matchFn by common_name | `html_report_builder.py:1768-1775` - exact match | MATCH |
| 59 | Category Summary: drilldown on `type_count`, matchFn by category | `html_report_builder.py:1847-1854` - exact match | MATCH |
| 60 | CSS: `.drilldown-row`, `.drilldown-panel`, `.drilldown-table`, `.drilldown-trigger` | `html_report_builder.py:619-626` - exact match | MATCH |

**Phase 5 Score: 6/6 (100%)**

---

## 4. Differences Found

None. All 60 comparison items match the design document.

> **Re-verification (2026-03-11)**: The PARTIAL gap from v1.0 (`_ranking_to_dict` missing `featured_count`/`inci_only_count`) has been fixed. Both fields are now serialized at `html_report_builder.py:34-35`, enabling the Featured Ingredients card and Source column badge to render correctly.

---

## 5. Implementation Improvements (Design X, Implementation O)

No undocumented additions found. Implementation follows the design precisely.

---

## 6. Match Rate Summary by File

| File | Items Checked | Match | Partial | Missing |
|------|:------------:|:-----:|:-------:|:-------:|
| models.py | 4 | 4 | 0 | 0 |
| orchestrator.py | 2 | 2 | 0 | 0 |
| gemini.py | 4 | 4 | 0 | 0 |
| analyzer.py | 4 | 4 | 0 | 0 |
| excel_builder.py | 14 | 14 | 0 | 0 |
| html_report_builder.py | 28 | 28 | 0 | 0 |
| market_analyzer.py | 4 | 4 | 0 | 0 |
| **Total** | **60** | **60** | **0** | **0** |

---

## 7. Recommended Actions

No actions required. All 60 design items are fully implemented.

---

## 8. Security & Error Handling Compliance

| Design Requirement | Implementation | Status |
|-------------------|---------------|--------|
| `rel="noopener noreferrer"` on all external links | All 5 link locations include it | MATCH |
| ASIN validation before URL generation (JS + Python) | `isValidAsin()` + `ASIN_PATTERN.match()` | MATCH |
| `esc()` for user-generated text in HTML | Used throughout drilldown panel, cards | MATCH |
| Legacy compatibility (source="" default) | Pydantic defaults + fallback rendering | MATCH |
| Drilldown panel max 20 rows | `_toggleDrilldown` maxRows=20 | MATCH |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-11 | Initial gap analysis (98%, 1 PARTIAL) | Claude (gap-detector) |
| 1.1 | 2026-03-11 | Re-verification: _ranking_to_dict fix confirmed, 100% match | Claude (gap-detector) |
