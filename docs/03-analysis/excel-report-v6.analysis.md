# excel-report-v6 Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: webhook-service (amz_researcher)
> **Analyst**: gap-detector
> **Date**: 2026-03-09
> **Design Doc**: [excel-report-v6.design.md](../02-design/features/excel-report-v6.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Verify that `excel_builder.py` implementation matches all V6 design specifications (Sections 3-12).

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/excel-report-v6.design.md` (Sections 3-12)
- **Implementation Path**: `amz_researcher/services/excel_builder.py`
- **Analysis Date**: 2026-03-09

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **100%** | ✅ |

---

## 3. Section-by-Section Gap Analysis

### 3.1 Section 3: TAB_COLORS Consolidation

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| 12 entries in TAB_COLORS dict | Lines 27-40: exactly 12 entries | ✅ |
| Market Insight: "E91E63" | `"Market Insight": "E91E63"` | ✅ |
| Consumer Voice: "FF9800" | `"Consumer Voice": "FF9800"` | ✅ |
| Badge Analysis: "673AB7" | `"Badge Analysis": "673AB7"` | ✅ |
| Sales & Pricing: "009688" | `"Sales & Pricing": "009688"` | ✅ |
| Brand Positioning: "3F51B5" | `"Brand Positioning": "3F51B5"` | ✅ |
| Marketing Keywords: "795548" | `"Marketing Keywords": "795548"` | ✅ |
| Ingredient Ranking: "1B2A4A" | `"Ingredient Ranking": "1B2A4A"` | ✅ |
| Category Summary: "2E86AB" | `"Category Summary": "2E86AB"` | ✅ |
| Rising Products: "00BCD4" | `"Rising Products": "00BCD4"` | ✅ |
| Product Detail: "4CAF50" | `"Product Detail": "4CAF50"` | ✅ |
| Raw - Search Results: "FF6B35" | `"Raw - Search Results": "FF6B35"` | ✅ |
| Raw - Product Detail: "9B59B6" | `"Raw - Product Detail": "9B59B6"` | ✅ |
| Consumer Voice uses TAB_COLORS (no hardcode) | Line 436: `TAB_COLORS["Consumer Voice"]` | ✅ |
| Badge Analysis uses TAB_COLORS (no hardcode) | Line 536: `TAB_COLORS["Badge Analysis"]` | ✅ |

**Score: 15/15 (100%)**

### 3.2 Section 4: Product Detail URL Bug Fix

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Column 20 header "URL" exists | Line 211: `"URL"` in headers list | ✅ |
| URL format: `https://www.amazon.com/dp/{asin}` | Line 248: `f"https://www.amazon.com/dp/{p.asin}"` | ✅ |
| Written to column 20 after column 19 (Ingredients) | Lines 246-249: column 19 then column 20 | ✅ |

**Score: 3/3 (100%)**

### 3.3 Section 5: Consumer Voice BSR Enhancement

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| BSR section after existing Positive/Negative | Lines 481-525: after `_style_data_rows` for main data | ✅ |
| Data sources: 4 keys (bsr_top_half_positive/negative, bsr_bottom_half_positive/negative) | Lines 482-485 | ✅ |
| 2 blank rows before section | Line 488: `row += 2` | ✅ |
| Section title "BSR Correlation: Top Half vs Bottom Half" (Bold) | Line 489: exact text, line 490: `Font(bold=True, size=11)` | ✅ |
| Headers: Keyword, Type, Top Half Count, Bottom Half Count, Difference | Line 493: exact match | ✅ |
| Positive keywords iterated with Type="Positive" | Lines 501-510 | ✅ |
| Negative keywords iterated with Type="Negative" | Lines 513-522 | ✅ |
| Top Half Count from bsr_top_half_{type} | Lines 501, 507 (top_count) | ✅ |
| Bottom Half Count from bsr_bottom_half_{type} | Lines 502, 514: `.get(kw, 0)` | ✅ |
| Difference = top - bottom | Lines 509, 521 | ✅ |
| Skip if bsr_top_half_positive is None/empty | Line 487: `if bsr_top_pos or bsr_top_neg:` | ✅ |
| Skip row if both counts are 0 | Lines 503-504, 515-516 | ✅ |

**Score: 12/12 (100%)**

### 3.4 Section 6: Badge Analysis Enhancement

#### Section A: Statistical Test

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Data source: `badge_data["stat_test_bsr"]` | Line 576: `badge_data.get("stat_test_bsr")` | ✅ |
| Skip if stat_test is None | Line 577: `if stat_test is not None:` | ✅ |
| 2 blank rows | Line 578: `row += 2` | ✅ |
| Title "Statistical Test: Badge vs No-Badge BSR" (Bold) | Line 579: exact text | ✅ |
| Headers: "Test" / "Value" | Lines 584-585 | ✅ |
| Row: Method = "Mann-Whitney U Test" | Lines 591-592 | ✅ |
| Row: U Statistic with None check | Lines 596-598 | ✅ |
| Row: p-value with number_format "0.0000" | Lines 602-607 | ✅ |
| p-value shows note if insufficient_sample/test_failed | Lines 604-605 | ✅ |
| Row: Significant "Yes"/"No"/"N/A" | Lines 611-617 | ✅ |

#### Section B: Acquisition Threshold

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Data source: `badge_data["acquisition_threshold"]` | Line 623: `badge_data.get("acquisition_threshold") or {}` | ✅ |
| Skip if empty dict | Line 624: `if threshold:` | ✅ |
| 2 blank rows | Line 625: `row += 2` | ✅ |
| Title "Badge Acquisition Threshold" (Bold) | Line 626: exact text | ✅ |
| Headers: "Metric" / "Value" | Lines 630-631 | ✅ |
| Minimum Reviews with "#,##0" format | Lines 636-638 | ✅ |
| Median Reviews with "#,##0" format | Lines 640-642 | ✅ |
| Minimum Rating | Lines 644-646 | ✅ |
| Median Rating | Lines 648-650 | ✅ |

**Score: 19/19 (100%)**

### 3.5 Section 7: Sales & Pricing Sheet

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Function signature: `_build_sales_pricing(wb, analysis_data)` | Line 663 | ✅ |
| Data extraction: sales, sns, discount, promos | Lines 664-667 | ✅ |
| Guard: all 4 empty -> return | Lines 670-671 | ✅ |
| Title: "Sales & Pricing -- Revenue, Discounts & Promotions" | Line 679 | ✅ |
| Subtitle exact match | Line 680 | ✅ |
| Tab color from TAB_COLORS | Line 674 | ✅ |

#### Section A: Top Sellers

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `sales.get("top_sellers")` | Line 688 | ✅ |
| 6 columns: ASIN, Brand, Title, Bought/Mo, Price, BSR | Lines 693 | ✅ |
| Bought/Mo format "#,##0" | Line 705 | ✅ |
| Price format "$#,##0.00" | Line 707 | ✅ |
| BSR format "#,##0" | Line 709 | ✅ |

#### Section B: Sales by Price Tier

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `sales.get("sales_by_price_tier")` | Line 715 | ✅ |
| Section title "Sales by Price Tier" (Bold) | Lines 718-719 | ✅ |
| 4 columns: Price Tier, Count, Total Sales, Avg Sales | Line 722 | ✅ |
| Tier order matches design | Line 729 | ✅ |
| Number formats: #,##0 for Count/Total/Avg | Lines 736-740 | ✅ |

#### Section C: SNS Pricing Summary

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `sns` not empty | Line 747 | ✅ |
| Section title "Subscribe & Save Pricing" | Line 749 | ✅ |
| Key-Value vertical table (Metric/Value) | Lines 753-754 | ✅ |
| 6 metric rows match design | Lines 761-768 | ✅ |
| retention_signal nested access | Line 759 | ✅ |

#### Section D: Discount Impact

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `discount.get("tiers")` | Lines 780-781 | ✅ |
| Section title "Discount Impact on BSR" | Line 783 | ✅ |
| 5 columns match design | Line 787 | ✅ |
| Tier order matches design | Line 794 | ✅ |
| Avg Price format "$#,##0.00" | Line 807 | ✅ |

#### Section E: Coupon Types

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `promos.get("coupon_types")` and non-empty | Line 814-815 | ✅ |
| Section title "Coupon Type Distribution" | Line 818 | ✅ |
| 2 columns: Coupon, Count | Lines 821-822 | ✅ |
| Count format "#,##0" | Line 830 | ✅ |

#### Sheet-level

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Column widths: A=22, B=16, C=40, D=14, E=12, F=10 | Lines 837-839 | ✅ |
| Freeze panes "A5" | Line 836 | ✅ |

**Score: 32/32 (100%)**

### 3.6 Section 8: Brand Positioning Sheet

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Function name: `_build_brand_positioning_sheet` | Line 843 | ✅ |
| Data extraction: positioning (list), mfr (dict) | Lines 844-845 | ✅ |
| Guard: both empty -> return | Lines 847-848 | ✅ |
| Title exact match | Line 856 | ✅ |
| Subtitle exact match | Line 857 | ✅ |
| Tab color from TAB_COLORS | Line 851 | ✅ |

#### Section A: Brand Positioning

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| 7 columns: Brand, Products, Avg Price, Avg BSR, Avg Rating, Total Reviews, Segment | Line 869 | ✅ |
| Avg Price "$#,##0.00" | Line 881 | ✅ |
| Avg BSR "#,##0" | Line 883 | ✅ |
| Avg Rating "0.00" | Line 885 | ✅ |
| Total Reviews "#,##0" | Line 887 | ✅ |

#### Section B: Top Manufacturers

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `mfr.get("top_manufacturers")` | Lines 894-895 | ✅ |
| Section title "Top Manufacturers" | Line 897 | ✅ |
| 7 columns match design | Line 901 | ✅ |
| K-Beauty: "Y" if is_kbeauty else "" | Line 920 | ✅ |
| Total Bought "#,##0" | Line 919 | ✅ |

#### Section C: Market Concentration

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `mfr.get("market_concentration")` | Lines 926-927 | ✅ |
| Section title "Market Concentration" | Line 929 | ✅ |
| Total Manufacturers from `mfr["total_manufacturers"]` | Lines 939-941 | ✅ |
| Top 10 Products from `mc["top10_products"]` | Lines 944-946 | ✅ |
| Total Products from `mc["total_products"]` | Lines 948-950 | ✅ |
| Top 10 Market Share with % suffix | Lines 954-956 | ✅ |

#### Sheet-level

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Column widths: A=24, B=10, C=12, D=12, E=10, F=14, G=18 | Lines 962-963 | ✅ |
| Freeze panes "A5" | Line 961 | ✅ |

**Score: 24/24 (100%)**

### 3.7 Section 9: Marketing Keywords Sheet

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Function name: `_build_marketing_keywords` | Line 968 | ✅ |
| Data extraction: kw_data, tier_data | Lines 969-970 | ✅ |
| Guard: both empty -> return | Lines 972-973 | ✅ |
| Title exact match | Line 981 | ✅ |
| Subtitle exact match | Line 982 | ✅ |
| Tab color from TAB_COLORS | Line 976 | ✅ |

#### Section A: Title Keyword Performance

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `kw_data.get("keyword_analysis")` | Lines 989-990 | ✅ |
| 4 columns: Keyword, Count, Avg BSR, Avg Bought/Mo | Line 995 | ✅ |
| All formats "#,##0" | Lines 1005-1009 | ✅ |

#### Section B: Price Tier Top Ingredients

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Condition: `tier_data` non-empty | Line 1016 | ✅ |
| Section title "Price Tier Top Ingredients" | Line 1018 | ✅ |
| 3 columns: Price Tier, Products, Top Ingredients | Line 1022 | ✅ |
| Tier order matches design | Line 1029 | ✅ |
| Top Ingredients joined with ", " | Line 1038 | ✅ |
| Wrap text for ingredients | Line 1040: `WRAP_ALIGN` | ✅ |

#### Sheet-level

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Column widths: A=22, B=10, C=14, D=14 | Lines 1047-1048 | ✅ |
| Freeze panes "A5" | Line 1046 | ✅ |

**Score: 17/17 (100%)**

### 3.8 Section 10: build_excel() Modification

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| Insight group: ingredient_ranking, market_insight, consumer_voice, badge_analysis, sales_pricing | Lines 1068-1078 | ✅ |
| Analysis group: brand_positioning_sheet, marketing_keywords | Lines 1081-1083 | ✅ |
| category_summary after analysis group | Line 1084 | ✅ |
| rising_products conditional | Lines 1085-1086 | ✅ |
| product_detail after rising_products | Line 1087 | ✅ |
| Raw group: raw_search, raw_detail | Lines 1090-1091 | ✅ |
| `_build_sales_pricing` called within `if analysis_data:` | Line 1078 (inside block from line 1071) | ✅ |
| `_build_brand_positioning_sheet` in separate `if analysis_data:` | Lines 1081-1083 | ✅ |
| desired_order: 12 entries, exact match | Lines 1094-1107 | ✅ |
| Sheet reorder logic | Lines 1109-1112 | ✅ |

**Score: 10/10 (100%)**

### 3.9 Section 11: Edge Cases

| Design Item | Implementation | Status |
|-------------|---------------|:------:|
| analysis_data=None: only old sheets | Lines 1071, 1081: guarded by `if analysis_data:` | ✅ |
| Individual key None/empty: `.get() or {}` pattern | Lines 664-667, 844-845, 969-970 | ✅ |
| All sub-keys empty -> return (no sheet) | Lines 670-671, 847-848, 972-973 | ✅ |
| Empty list: Section A skipped if `positioning` is empty | Line 864: `if positioning:` | ✅ |
| None number fields: `if value is not None:` pattern | Applied consistently throughout | ✅ |
| Section row offset: `row += 2` between sections | All multi-section sheets follow pattern | ✅ |

**Score: 6/6 (100%)**

### 3.10 Section 12: Implementation Order Checklist

| Checklist Item | Implemented | Status |
|----------------|------------|:------:|
| 1. TAB_COLORS consolidation + hardcoding removal | Lines 27-40, 436, 536 | ✅ |
| 2. Product Detail URL column 20 | Lines 247-249 | ✅ |
| 3. Consumer Voice BSR section | Lines 481-528 | ✅ |
| 4. Badge Analysis stat test + threshold | Lines 575-659 | ✅ |
| 5. _build_sales_pricing() | Lines 662-839 | ✅ |
| 6. _build_brand_positioning_sheet() | Lines 842-964 | ✅ |
| 7. _build_marketing_keywords() | Lines 967-1049 | ✅ |
| 8. build_excel() call order + desired_order | Lines 1052-1117 | ✅ |

**Score: 8/8 (100%)**

---

## 4. Match Rate Summary

```
Total Design Items Compared: 146
  MATCH:   146 (100%)
  PARTIAL:   0 (  0%)
  MISSING:   0 (  0%)

Overall Match Rate: 100%
```

---

## 5. Differences Found

### 5.1 Missing Features (Design O, Implementation X)

None.

### 5.2 Added Features (Design X, Implementation O)

| Item | Location | Description | Impact |
|------|----------|-------------|--------|
| Defensive `.get()` on dict values | Throughout new functions | Implementation uses `.get()` consistently even where design shows direct key access | Positive -- prevents KeyError |
| `isinstance` guard in ingredient join | Line 1038 | `isinstance(ing, dict) and "name" in ing` guard not in design | Positive -- prevents TypeError on malformed data |

### 5.3 Changed Features (Design != Implementation)

None. All design specifications are faithfully implemented.

---

## 6. Implementation Improvements Over Design

| # | Improvement | Location | Description |
|---|-------------|----------|-------------|
| 1 | Defensive dict access | All new `_build_*` functions | Design uses `top_sellers[i]["asin"]` direct access; implementation uses `ts.get("asin")` safe access |
| 2 | Type guard in ingredient join | Line 1038 | Protects against non-dict entries in `top_ingredients` list |
| 3 | Comment annotations | Lines 26, 247, 431, 531, 575, 622, 662, 842, 967, 1052 | Each design item annotated with `# Item N:` comments for traceability |

---

## 7. Convention Compliance

| Category | Convention | Compliance | Notes |
|----------|-----------|:----------:|-------|
| Function naming | snake_case with `_` prefix for private | 100% | All new functions follow existing pattern |
| Constants | UPPER_SNAKE_CASE | 100% | TAB_COLORS, HEADER_FILL, etc. |
| Design pattern | _write_title -> headers -> data loop -> _style_data_rows -> _set_column_widths | 100% | All 3 new sheets follow pattern |
| Graceful degradation | `.get() or {}` + early return | 100% | Matches design principle |
| Section separation | 2 blank rows + Bold title | 100% | All multi-section sheets |

---

## 8. Recommended Actions

No immediate actions required. Match rate is 100%.

### Documentation Note

The 2 implementation improvements (defensive `.get()` access, type guard in ingredient join) are beneficial additions that do not require design document updates. They follow the project's existing defensive coding pattern.

---

## 9. Next Steps

- [x] Gap analysis complete
- [ ] Manual test: run full excel generation with real data
- [ ] Verify all 12 tab colors render correctly in Excel
- [ ] Write completion report (`excel-report-v6.report.md`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-09 | Initial gap analysis | gap-detector |
