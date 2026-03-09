# Plan: Excel Report V6 — 분석 데이터 시각화 완성 + 보고서 구조 개선

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | market_analyzer가 16개 분석을 수행하지만 엑셀 시트로 표현되는 것은 3개뿐. 13개 분석 결과가 Gemini 마크다운 텍스트에만 묻혀 필터/정렬 불가 |
| **Solution** | 핵심 분석 3개 시트 신규 추가, 기존 시트 데이터 보강, 버그 수정(URL 컬럼 누락) |
| **Function UX Effect** | 사용자가 엑셀에서 직접 가격/브랜드/키워드별 데이터를 필터링·정렬하여 즉각적인 의사결정 가능 |
| **Core Value** | 이미 계산되는 데이터를 엑셀로 노출함으로써 추가 비용 $0, 분석 활용도 60% → 90%+ 달성 |

## 1. Overview

V5에서 `market_analyzer.py`에 16개 분석 함수를 구현했으나, `excel_builder.py`가 이 중 3개(Consumer Voice, Badge Analysis, Rising Products)만 시트로 표현한다. 나머지 13개 분석 결과는 Gemini에 JSON으로 전달되어 Market Insight 마크다운 텍스트로만 존재하며, 사용자가 직접 필터/정렬/비교할 수 없다.

이번 개선은 **이미 계산되는 데이터를 엑셀로 노출**하는 것이 핵심이다. 분석 로직 추가 없이 excel_builder.py 수정만으로 완성 가능하다.

## 2. Problem Statement

### 2.1 분석 데이터 활용도 Gap

| 분석 함수 | 엑셀 시트 | 현재 상태 |
|-----------|----------|----------|
| `analyze_customer_voice()` | Consumer Voice | OK |
| `analyze_badges()` | Badge Analysis | OK |
| `detect_rising_products()` | Rising Products | OK |
| `analyze_sales_volume()` | - | **누락** — Top 셀러, 가격대별 판매량 |
| `analyze_sns_pricing()` | - | **누락** — SNS 할인율, 채택률 |
| `analyze_discount_impact()` | - | **누락** — 할인 구간별 BSR 비교 |
| `analyze_promotions()` | - | **누락** — 쿠폰 유형별 분포 |
| `analyze_by_price_tier()` | - | **누락** — 가격대별 Top 성분 |
| `analyze_brand_positioning()` | - | **누락** — 브랜드 가격 vs BSR |
| `analyze_by_brand()` | - | **누락** — 브랜드별 핵심 성분 |
| `analyze_manufacturer()` | - | **누락** — OEM별 프로파일 |
| `analyze_title_keywords()` | - | **누락** — 마케팅 키워드별 BSR |
| `analyze_unit_economics()` | - | **누락** — 단가 비교 |
| `analyze_sku_strategy()` | - | **누락** — SKU 수-BSR 관계 |
| `analyze_cooccurrence()` | - | **누락** — 성분 조합 |
| `analyze_rating_ingredients()` | - | **누락** — 고/저평점 성분 차이 |
| `analyze_by_bsr()` | - | **누락** — BSR 상위 vs 하위 성분 |

### 2.2 기존 시트 문제점

1. **Product Detail URL 컬럼 비어있음** — 헤더 "URL" (col 20) 존재하나 값 미기록 (버그)
2. **Consumer Voice — BSR 상관 데이터 미사용** — `bsr_top_half_positive/negative` 데이터 생성하지만 시트에 미표시
3. **Badge Analysis — 통계 검정 결과 미표시** — `stat_test_bsr` (p-value) 계산하지만 시트에 미표시
4. **TAB_COLORS 불일치** — Consumer Voice, Badge Analysis 색상이 dict에 없고 하드코딩

## 3. 변경사항 요약

### Phase 1: 버그 수정 + 기존 시트 보강

| # | 항목 | 변경 유형 | 상세 |
|---|------|-----------|------|
| 1 | Product Detail URL 컬럼 수정 | **버그 수정** | column 20에 ASIN 기반 Amazon URL 기록 |
| 2 | Consumer Voice BSR 상관 데이터 추가 | 보강 | Top/Bottom BSR 그룹별 키워드 빈도 섹션 추가 |
| 3 | Badge Analysis 통계 검정 표시 | 보강 | p-value, 유의성 여부, acquisition_threshold 표시 |
| 4 | TAB_COLORS 통합 | 정리 | 모든 시트 색상을 TAB_COLORS dict에서 관리 |

### Phase 2: 핵심 분석 시트 신규 추가 (3개)

| # | 시트명 | 포함 분석 | 설명 |
|---|--------|----------|------|
| 5 | **Sales & Pricing** | `sales_volume` + `sns_pricing` + `discount_impact` + `promotions` | 판매량·가격·할인·쿠폰 통합 뷰 |
| 6 | **Brand Positioning** | `brand_positioning` + `brand_analysis` + `manufacturer` | 브랜드/제조사별 가격·BSR·성분 프로파일 |
| 7 | **Marketing Keywords** | `title_keywords` + `analyze_by_price_tier()` | 마케팅 키워드별 BSR/판매량 + 가격대별 Top 성분 |

### Phase 3: 선택적 추가 (시트 과다 시 보류)

| # | 시트명 | 포함 분석 | 비고 |
|---|--------|----------|------|
| 8 | Ingredient Deep Dive | `cooccurrence` + `rating_ingredients` + `bsr_analysis` | 시트 수가 12개 초과 시 보류 |
| 9 | SKU & Unit Economics | `sku_strategy` + `unit_economics` | 데이터 양 적으면 Marketing Keywords에 통합 |

## 4. 상세 설계

### 4.1 Product Detail URL 컬럼 수정 (버그 수정)

**현상**: `excel_builder.py:200` 헤더에 "URL" 존재하나, 루프 내에서 column 20에 값을 쓰는 코드 없음.

**수정**:
```python
# excel_builder.py _build_product_detail() 루프 내 추가
url = f"https://www.amazon.com/dp/{p.asin}"
ws.cell(row=row, column=20, value=url)
```

### 4.2 Consumer Voice BSR 상관 데이터 추가

**현상**: `analyze_customer_voice()`가 `bsr_top_half_positive/negative`, `bsr_bottom_half_positive/negative` 4개 dict를 반환하지만 `_build_consumer_voice()`에서 미사용.

**수정**: Consumer Voice 시트 하단에 "BSR Top Half vs Bottom Half" 섹션 추가.

| Keyword | Top Half Count | Bottom Half Count | Difference |
|---------|---------------|-------------------|------------|

### 4.3 Badge Analysis 통계 검정 표시

**현상**: `analyze_badges()`가 `stat_test_bsr` (Mann-Whitney U), `acquisition_threshold` 반환하지만 시트 미표시.

**수정**:
- Badge Type Distribution 아래에 "Statistical Test" 섹션 추가 (p-value, significant Y/N)
- "Badge Acquisition Threshold" 섹션 추가 (min_reviews, median_reviews, min_rating)

### 4.4 TAB_COLORS 통합

**현상**: `Consumer Voice`(`FF9800`), `Badge Analysis`(`673AB7`)이 TAB_COLORS dict 밖에서 하드코딩.

**수정**: TAB_COLORS dict에 추가하고, 각 build 함수에서 dict 참조로 변경.

### 4.5 Sales & Pricing 시트 (신규)

**데이터 소스**: `analysis_data["sales_volume"]`, `analysis_data["sns_pricing"]`, `analysis_data["discount_impact"]`, `analysis_data["promotions"]`

**구성**:

**섹션 A: Top Sellers** (sales_volume.top_sellers)

| ASIN | Brand | Title | Bought/Mo | Price | BSR |
|------|-------|-------|-----------|-------|-----|

**섹션 B: Sales by Price Tier** (sales_volume.sales_by_price_tier)

| Price Tier | Count | Total Sales | Avg Sales |
|------------|-------|-------------|-----------|

**섹션 C: SNS Pricing** (sns_pricing)

| Metric | Value |
|--------|-------|
| SNS Adoption Rate | 74.3% |
| Avg Discount | 8.5% |
| SNS Avg Bought/Mo | 1,200 |
| No-SNS Avg Bought/Mo | 800 |

**섹션 D: Discount Impact** (discount_impact.tiers)

| Discount Tier | Count | Avg BSR | Avg Bought | Avg Price |
|---------------|-------|---------|------------|-----------|

**섹션 E: Coupon Types** (promotions.coupon_types)

| Coupon | Count |
|--------|-------|

### 4.6 Brand Positioning 시트 (신규)

**데이터 소스**: `analysis_data["brand_positioning"]`, `analysis_data["brand_analysis"]`, `analysis_data["manufacturer"]`

**구성**:

**섹션 A: Brand Positioning** (brand_positioning, 가격 vs BSR)

| Brand | Products | Avg Price | Avg BSR | Avg Rating | Total Reviews | Segment |
|-------|----------|-----------|---------|------------|---------------|---------|

**섹션 B: Manufacturer Profile** (manufacturer.top_manufacturers)

| Manufacturer | Products | Avg BSR | Avg Price | Avg Rating | Total Bought | K-Beauty |
|-------------|----------|---------|-----------|------------|-------------|----------|

**섹션 C: Market Concentration** (manufacturer.market_concentration)

| Metric | Value |
|--------|-------|
| Top 10 Manufacturers | X products |
| Market Share | Y% |

### 4.7 Marketing Keywords 시트 (신규)

**데이터 소스**: `analysis_data["title_keywords"]`, `analysis_data["price_tier_analysis"]`

**구성**:

**섹션 A: Title Keyword Performance** (title_keywords.keyword_analysis)

| Keyword | Count | Avg BSR | Avg Bought/Mo |
|---------|-------|---------|---------------|

**섹션 B: Price Tier Top Ingredients** (price_tier_analysis)

| Price Tier | Products | Top Ingredients |
|------------|----------|----------------|

## 5. 영향 받는 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `amz_researcher/services/excel_builder.py` | **대폭 수정** | 3개 시트 신규, 3개 시트 보강, 버그 수정 |

> **핵심: excel_builder.py 단일 파일 변경으로 완성.** market_analyzer.py, orchestrator.py, models.py 변경 불필요. `analysis_data` dict가 이미 `build_excel()`에 전달되고 있으므로, excel_builder 내에서 추가 시트를 생성하면 됨.

## 6. 시트 최종 구성 (After)

| 순서 | 시트명 | 탭 색상 | 구분 | 변경 |
|------|--------|---------|------|------|
| 1 | Market Insight | E91E63 | Insight | 기존 |
| 2 | Consumer Voice | FF9800 | Insight | **보강** |
| 3 | Badge Analysis | 673AB7 | Insight | **보강** |
| 4 | **Sales & Pricing** | (신규) | Insight | **신규** |
| 5 | **Brand Positioning** | (신규) | Analysis | **신규** |
| 6 | **Marketing Keywords** | (신규) | Analysis | **신규** |
| 7 | Ingredient Ranking | 1B2A4A | Analysis | 기존 |
| 8 | Category Summary | 2E86AB | Analysis | 기존 |
| 9 | Rising Products | 00BCD4 | Analysis | 기존 |
| 10 | Product Detail | 4CAF50 | Raw | **버그 수정** |
| 11 | Raw - Search Results | FF6B35 | Raw | 기존 |
| 12 | Raw - Product Detail | 9B59B6 | Raw | 기존 |

## 7. 구현 순서

```
Phase 1 (버그 수정 + 기존 보강)
├─ 1. Product Detail URL 컬럼 수정                    ← 5분
├─ 2. TAB_COLORS 통합 (Consumer Voice, Badge)         ← 5분
├─ 3. Consumer Voice BSR 상관 섹션 추가                ← 20분
└─ 4. Badge Analysis 통계/threshold 섹션 추가          ← 20분

Phase 2 (신규 시트 추가)
├─ 5. Sales & Pricing 시트 구현                        ← 40분
├─ 6. Brand Positioning 시트 구현                      ← 40분
├─ 7. Marketing Keywords 시트 구현                     ← 30분
├─ 8. build_excel() 시트 순서 업데이트                  ← 10분
└─ 9. desired_order 리스트에 신규 시트 추가              ← 5분
```

## 8. 의존성 추가

없음. 기존 openpyxl만 사용.

## 9. 리스크

| 리스크 | 완화 방안 |
|--------|----------|
| 시트 12개로 증가 → 사용자 탐색 부담 | 탭 색상 그룹핑(Insight/Analysis/Raw)으로 시각적 구분 |
| analysis_data 내 키가 없는 경우 (데이터 부족) | 각 build 함수에서 `analysis_data.get(key)` None 체크 후 시트 생략 |
| 섹션이 많은 시트의 레이아웃 복잡도 | 섹션 간 빈 행 2줄 + 섹션 제목 Bold로 구분 |

## 10. Success Criteria

- [ ] Product Detail 시트 URL 컬럼에 Amazon 링크가 정상 출력됨
- [ ] Consumer Voice 시트에 BSR Top/Bottom Half 키워드 비교 섹션 존재
- [ ] Badge Analysis 시트에 p-value 및 acquisition threshold 표시
- [ ] Sales & Pricing 시트에 Top Sellers, SNS, Discount, Coupon 데이터 표시
- [ ] Brand Positioning 시트에 브랜드별 + 제조사별 테이블 표시
- [ ] Marketing Keywords 시트에 키워드별 BSR/판매량 테이블 표시
- [ ] 모든 시트 탭 색상이 TAB_COLORS dict에서 관리됨
- [ ] analysis_data가 비어있어도 에러 없이 해당 시트 스킵됨
- [ ] 기존 파이프라인(run_research, run_analysis) 정상 동작

## 11. 비용 분석

| 항목 | 추가 비용 |
|------|----------|
| Gemini API | **$0** — 분석 로직 추가 없음, 기존 계산 결과 표시만 |
| 패키지 | **$0** — openpyxl 기존 사용 |
| 엑셀 파일 크기 | ~20-30KB 증가 예상 (텍스트 시트 3개 추가) |
