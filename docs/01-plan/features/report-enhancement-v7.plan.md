# Report Enhancement V7 Planning Document

> **Summary**: 리포트의 가격 투명성, 제품 접근성, 성분 분석 정밀도, 집계 데이터 드릴다운 기능을 개선하여 사용자가 더 빠르고 정확한 의사결정을 내릴 수 있도록 한다.
>
> **Project**: amz_researcher (webhook-service)
> **Author**: CTO Lead
> **Date**: 2026-03-11
> **Status**: Draft

---

## Executive Summary
 
| Perspective | Content |
|-------------|---------|
| **Problem** | 리포트가 할인 정보, 제품 링크, 성분 출처 구분, 집계 상세를 제공하지 않아 사용자가 외부에서 추가 확인 작업을 해야 한다. SNS 가격 분석은 실무 활용도가 낮고, 세그먼트별 할인 전략 분석이 부재하다 |
| **Solution** | 5개 요구사항(가격+할인율, 타이틀 하이퍼링크, Featured vs INCI 성분 분리, 드릴다운, SNS→할인 분석 대체)을 모델-분석-렌더링 전 계층에 걸쳐 구현 |
| **Function/UX Effect** | 가격 투명성 확보, 원클릭 제품 접근, 마케팅 성분 즉시 식별, 전성분 확인 가능, 집계 수치 클릭 시 개별 제품 확인, 세그먼트별 할인 전략 파악 |
| **Core Value** | 리포트 하나로 의사결정 완결 -- 외부 도구/탭 전환 없이 분석부터 제품 확인까지 원스톱, 할인 전략 벤치마킹 |

---

## 1. Overview

### 1.1 Purpose

AMZ Researcher의 Excel/HTML 리포트를 개선하여 (1) 가격 할인 정보 가시화, (2) 제품 타이틀에서 Amazon 페이지 직접 접근, (3) 마케팅 성분과 전성분의 출처 구분, (4) 집계 수치에서 개별 제품으로의 드릴다운 기능을 제공한다.

### 1.2 Background

- 현재 Excel Product Detail 시트에 `Discount%` 컬럼(col 16)은 있으나, `initial_price` 자체가 별도 컬럼으로 노출되지 않아 할인 맥락 파악이 어렵다.
- 제품 타이틀이 plain text여서 Amazon 페이지 확인 시 ASIN을 복사해 브라우저에서 검색해야 한다.
- Gemini가 INCI + features/title에서 성분을 한꺼번에 추출하므로, 브랜드가 의도적으로 마케팅하는 성분과 전성분 기반 성분을 구분할 수 없다.
- Brand Positioning, Ingredient Ranking 등 집계 테이블에서 "2 products"라고 표시되면, 어떤 제품인지 확인할 방법이 없다.

### 1.3 리포트 유형별 적용 범위

이 프로젝트에는 **카테고리 분석 리포트**와 **키워드 검색 리포트** 두 종류가 있으며, 시트/섹션 구성이 다르다:

| 구분 | 카테고리 분석 | 키워드 검색 |
|------|-------------|-----------|
| **진입점** | `build_excel()` / `build_html()` | `build_keyword_excel()` / `build_keyword_html()` |
| **Excel 시트 수** | 12시트 | 9시트 (Badge/Brand Positioning/Rising Products 제외) |
| **Brand Positioning** | O | X |
| **Badge Analysis** | O | X |
| **Rising Products** | O | X |
| **분석 데이터** | `build_market_analysis()` | `build_keyword_market_analysis()` |

**요구사항별 적용 범위**:

| REQ | 카테고리 | 키워드 | 비고 |
|-----|:-------:|:------:|------|
| REQ-1 (Price) | O | O | 양쪽 Product Detail 동일 적용 |
| REQ-2 (Hyperlink) | O | O | Product Detail + Raw Search (키워드에는 Rising Products 없음) |
| REQ-3 (Ingredients) | O | O | 양쪽 동일 적용 |
| REQ-4 (Drilldown) | O | 부분 | 키워드에는 Brand Positioning 없으므로 Ingredient/Category만 |
| REQ-5 (SNS→Discount) | O | O | `build_keyword_market_analysis()`에서도 `analyze_sns_pricing()` 호출 중 (line 1115) |

### 1.4 Related Documents

- `docs/01-plan/features/excel-report-v6.plan.md`
- `docs/01-plan/features/html-insight-report.plan.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] REQ-1: Excel/HTML에 Initial Price 컬럼 추가 및 할인율 표시 개선
- [ ] REQ-2: Excel/HTML에서 제품 타이틀을 Amazon 링크로 변환
- [ ] REQ-3: Gemini 프롬프트/모델/분석/렌더링에서 Featured vs INCI 성분 분리 + Product Detail에서 전성분 확인 가능
- [ ] REQ-4: HTML 집계 테이블에 드릴다운(개별 제품 목록) 기능 추가
- [ ] REQ-5: SNS Price 분석/표시 제거, 세그먼트별 할인율 분석으로 대체
- [ ] 기존 리포트와의 하위 호환성 유지

### 2.2 Out of Scope

- Gemini 모델 자체 변경 (Flash/Pro 선택)
- 성분 데이터 재수집 (기존 캐시된 데이터는 레거시로 처리)
- HTML 리포트의 전체 UI 리디자인
- SNS Price 관련 DB 컬럼 삭제 (데이터는 유지, 리포트에서만 제거)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Excel Product Detail에 `Initial Price` 컬럼을 Price 옆에 추가하고, HTML에서도 initial_price를 별도 표시 | High | Pending |
| FR-02 | HTML Product Detail에서 Price 컬럼에 `$29.99 ~~$39.99~~ (-25%)` 형태로 통합 표시 | High | Pending |
| FR-03 | Excel 타이틀 셀에 HYPERLINK 수식 삽입 (`=HYPERLINK("url","title")`) | High | Pending |
| FR-04 | HTML 타이틀을 `<a href="https://www.amazon.com/dp/{ASIN}" target="_blank">` 링크로 변환 | High | Pending |
| FR-05 | Ingredient 모델에 `source` 필드 추가 (`featured` / `inci` / `both`) | High | Pending |
| FR-06 | Gemini 프롬프트에 source 구분 출력 지시 추가 | High | Pending |
| FR-07 | Ingredient Ranking 테이블에 `Source` 컬럼 추가 (Featured/INCI/Both 배지) | Medium | Pending |
| FR-08 | HTML에서 Featured Ingredients 전용 요약 카드/섹션 추가 | Medium | Pending |
| FR-09 | Brand Positioning 테이블의 `product_count` 셀 클릭 시 해당 브랜드 제품 목록 드릴다운 | High | Pending |
| FR-10 | Ingredient Ranking 테이블의 `# Products` 셀 클릭 시 해당 성분 포함 제품 목록 드릴다운 | High | Pending |
| FR-11 | Category Summary 테이블의 집계 수치에 드릴다운 지원 | Medium | Pending |
| FR-12 | 기존 캐시된 성분 데이터(source 필드 없음)와의 하위 호환 처리 | High | Pending |
| FR-13 | Excel/HTML Product Detail에서 전성분(INCI) 목록을 확인할 수 있는 형태로 표시 | High | Pending |
| FR-14 | SNS Price 컬럼을 Excel Product Detail, HTML Product Detail에서 제거 | Medium | Pending |
| FR-15 | SNS Pricing 분석 섹션(Sales & Pricing 내)을 제거 | Medium | Pending |
| FR-16 | 세그먼트별 할인율 분석 추가 (Budget/Mid/Premium/Luxury별 평균 할인율, 할인 제품 비율) | High | Pending |
| FR-17 | Gemini Market Report 프롬프트에서 SNS 섹션을 세그먼트별 할인 전략 분석으로 대체 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | HTML 리포트 렌더링 시간 기존 대비 20% 이내 증가 | 50+ 제품 리포트 브라우저 측정 |
| Compatibility | source 필드 없는 레거시 캐시 데이터에서 에러 없이 동작 | 기존 캐시 기반 테스트 |
| UX | 드릴다운 패널이 테이블 스크롤 컨텍스트를 유지 | 수동 검증 |

---

## 4. Detailed Design per Requirement

### 4.1 REQ-1: Price with Initial Price (Discount Rate)

#### 4.1.1 Current State Analysis

**Excel (`excel_builder.py`)**:
- Product Detail 시트 headers (line 206-213): `"Price"` = col 4, `"Discount%"` = col 16
- `initial_price`는 Discount% 계산에만 사용 (line 241-243), 별도 컬럼 미노출
- col 4에 `p.price`만 표시 (line 224-225)

**HTML (`html_report_builder.py`)**:
- `_product_to_dict` (line 54): `initial_price`를 JSON으로 직렬화하고 있음
- Product Detail TableController (line 1740): Price 컬럼은 `fmtPrice(v)`만 렌더링
- `initial_price`를 별도 컬럼이나 복합 표시로 사용하지 않음

**Model (`models.py`)**:
- `WeightedProduct.initial_price: float | None = None` (line 124) -- 이미 존재

#### 4.1.2 Implementation Plan

**Excel 변경**:

> **⚠️ 컬럼 시프트 충돌 주의**: REQ-5에서 `SNS Price` (현재 col 5)를 제거하고, REQ-1에서 `Initial Price`를 col 5에 삽입한다. 두 작업을 **같은 Phase에서 동시 처리**하면 시프트가 상쇄되어 기존 col 6 이후 컬럼 번호는 변경 없음. → **Implementation Order에서 Phase 2에 REQ-1 + REQ-5의 Excel 컬럼 변경을 합쳐서 처리**.

1. `SNS Price` 컬럼 (col 5) 제거
2. 같은 col 5 자리에 `"Initial Price"` 컬럼 삽입
3. 결과: Price(col 4) → Initial Price(col 5, 구 SNS 자리) → Bought/Mo(col 6) ... — **기존 col 6 이후 번호 변동 없음**
4. `initial_price` 셀에 `$#,##0.00` 포맷 적용
5. `Discount%` 컬럼은 기존 위치 유지

**HTML 변경**:
1. Product Detail TableController의 Price 컬럼 `render` 함수를 복합 렌더링으로 변경:
   ```javascript
   render: (v, row) => {
     let html = fmtPrice(v);
     if (row.initial_price && row.initial_price > v) {
       const disc = Math.round((1 - v / row.initial_price) * 100);
       html += ` <span class="price-original">${fmtPrice(row.initial_price)}</span>`;
       html += ` <span class="badge badge-negative">-${disc}%</span>`;
     }
     return html;
   }
   ```
2. CSS에 `.price-original` 스타일 추가 (취소선, muted color)

#### 4.1.3 Impact Range

| File | Change Type | Lines Affected |
|------|------------|----------------|
| `excel_builder.py` | headers 배열 수정, 컬럼 삽입, 번호 시프트 | ~206-264 |
| `html_report_builder.py` | Price render 함수 교체, CSS 추가 | ~1740, CSS section |

---

### 4.2 REQ-2: Product Title Hyperlinks

#### 4.2.1 Current State Analysis

**Excel**:
- col 3 = Title (plain text, line 223), col 22 = URL (line 252-253)
- URL은 `https://www.amazon.com/dp/{ASIN}` 형식으로 이미 생성

**HTML**:
- Product Detail: `truncate(v, 'lg')` (line 1739) -- plain text
- Raw Search: `truncate(v, 'xl')` (line 1779) -- plain text
- Rising Products: `esc(p.title || '')` (line 1710) -- plain text

#### 4.2.2 Implementation Plan

**Excel 변경**:
1. Title 셀에 openpyxl의 HYPERLINK 수식 적용 대신, **셀에 hyperlink 속성 직접 설정** (openpyxl native):
   ```python
   title_cell = ws.cell(row=row, column=3, value=p.title)
   title_cell.hyperlink = f"https://www.amazon.com/dp/{p.asin}"
   title_cell.style = "Hyperlink"  # 파란색+밑줄 기본 스타일
   ```
2. 기존 URL 컬럼(col 22, 시프트 후 col 23)은 유지 (하위 호환)

**HTML 변경**:
1. Product Detail, Raw Search, Rising Products에서 title 렌더 함수 변경:
   ```javascript
   render: (v, row) => {
     const url = `https://www.amazon.com/dp/${row.asin}`;
     return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="product-link">${truncate(v, 'lg')}</a>`;
   }
   ```
2. CSS에 `.product-link` 스타일 추가 (hover underline, color inherit)

#### 4.2.3 Security Considerations

- URL은 고정 패턴 `https://www.amazon.com/dp/{ASIN}`이며, ASIN은 영숫자 10자리로 제한됨
- `rel="noopener noreferrer"` 적용으로 target blank 보안 처리
- ASIN 값은 Bright Data에서 수집된 데이터이므로 XSS 위험 낮음 (esc() 함수로 이미 이스케이프)
- 추가로 ASIN 형식 검증 가드 추가: `/^B0[A-Z0-9]{8}$/` 패턴 불일치 시 링크 생성 안 함

#### 4.2.4 Impact Range

| File | Change Type | Lines Affected |
|------|------------|----------------|
| `excel_builder.py` | Title 셀 hyperlink 속성 추가 | ~223 |
| `html_report_builder.py` | 3개 섹션의 title render 변경, CSS 추가 | ~1739, ~1779, ~1710 |

---

### 4.3 REQ-3: Ingredients Analysis Overhaul (Featured vs INCI)

#### 4.3.1 Problem Statement

현재 Gemini가 `ingredients_raw`(전성분)와 `features`/`title`(마케팅 강조 성분)을 **단일 리스트**로 추출한다. 그 결과:
- 브랜드가 의도적으로 마케팅하는 핵심 성분(title/features에 명시)과 전성분 리스트에만 있는 성분을 구분할 수 없음
- Product 팀의 인사이트: "features에서 추출된 성분 = 브랜드가 강조하는 must-have 성분"이므로 이를 별도로 식별해야 함

#### 4.3.2 Current Data Flow

```
products_for_gemini (orchestrator.py)
  = { asin, title, ingredients_raw, features, additional_details }
       |
       v
Gemini PROMPT_TEMPLATE (gemini.py line 35-86)
  "INCI 전성분에서 핵심 성분을 선별하라"
  "title/features에서도 성분을 추출할 수 있다"
       |
       v
GeminiResponse.products -> list[ProductIngredients]
  ProductIngredients.ingredients -> list[Ingredient]
    Ingredient(name, common_name, category)  <-- source 필드 없음
       |
       v
analyzer.py calculate_weights -> WeightedProduct.ingredients
       |
       v
excel_builder / html_report_builder
```

#### 4.3.3 Architecture Decision

**Option A**: Gemini 프롬프트를 2회 호출 (Featured용 + INCI용) -- 비용 2배, 지연 2배
**Option B**: 단일 호출에서 `source` 필드를 출력하도록 프롬프트 수정 -- **선택**
**Option C**: 후처리로 title/features 문자열 매칭 -- 부정확, 유지보수 어려움

**선택 근거 (Option B)**:
- Gemini 호출 비용/지연 증가 없음
- 프롬프트에 이미 "title에 명시된 핵심 성분은 반드시 포함" 지시가 있으므로, 출력에 `source` 필드만 추가하면 됨
- JSON 스키마에 `source` 필드를 추가하는 것은 Gemini에게 명확한 구조적 지시

#### 4.3.4 Implementation Plan

**Phase 3-1: Model 변경 (`models.py`)**:
```python
class Ingredient(BaseModel):
    name: str
    common_name: str = ""
    category: str
    source: str = ""  # "featured", "inci", "both", "" (legacy)

class WeightedProduct(BaseModel):
    # ... existing fields ...
    ingredients_raw: str = ""  # NEW: DB amz_products.ingredients 원본 텍스트
```
- `Ingredient.source` 기본값 `""` -- 기존 캐시 데이터 호환
- `WeightedProduct.ingredients_raw` 기본값 `""` -- 없는 경우 빈 문자열

**Phase 3-1b: `ingredients_raw` 데이터 전달 경로**:
```
DB: amz_products.ingredients (TEXT)
  |
  v
product_db.py: get_products_by_category() / get_keyword_products()
  → SELECT에 ingredients 컬럼 포함 확인 (현재 미확인 → 추가 필요 가능)
  |
  v
orchestrator.py: calculate_weights() 또는 WeightedProduct 매핑 시
  → row["ingredients"] → WeightedProduct.ingredients_raw 매핑 추가
  |
  v
html_report_builder.py: _product_to_dict()
  → "ingredients_raw": p.ingredients_raw 직렬화 추가
  |
  v
HTML JS: Product Detail 테이블에서 확장 UI로 표시
```
- 키워드 검색 플로우(`build_keyword_market_analysis`)에서도 동일하게 전달 필요

**Phase 3-2: Gemini 프롬프트 변경 (`gemini.py`)**:
- `PROMPT_TEMPLATE` 규칙에 source 분류 지시 추가:
  ```
  7. source: 성분이 어디에서 확인되었는지 분류
     - "featured": title 또는 features에서만 언급된 성분
     - "inci": ingredients_raw(전성분)에서만 확인된 성분
     - "both": title/features와 ingredients_raw 양쪽에서 확인된 성분
  ```
- JSON 출력 예시에 `source` 필드 추가:
  ```json
  {"name": "Argania Spinosa Kernel Oil", "common_name": "Argan Oil", "category": "Natural Oil", "source": "both"}
  ```

**Phase 3-3: 분석 계층 (`analyzer.py`)**:
- `_aggregate_ingredients`: source 정보를 IngredientRanking에 전달
- `IngredientRanking` 모델에 `source_breakdown` 필드 추가 (optional):
  ```python
  class IngredientRanking(BaseModel):
      # ... existing fields ...
      featured_count: int = 0    # featured 또는 both인 제품 수
      inci_only_count: int = 0   # inci-only인 제품 수
  ```

**Phase 3-4: Excel 렌더링 (`excel_builder.py`)**:
- Product Detail 시트에 2개 성분 컬럼 제공:
  - `Featured Ingredients`: source가 `featured` 또는 `both`인 성분만 (마케팅 소구 성분)
  - `Full Ingredients (INCI)`: 전성분 목록 (DB의 `ingredients_raw` 원본 텍스트)
- 기존 "Ingredients Found" 컬럼을 "Featured Ingredients"로 변경
- 새 컬럼 "Full Ingredients (INCI)" 추가: `amz_products.ingredients` 원본 텍스트 그대로 표시
  - WeightedProduct 모델에 `ingredients_raw: str = ""` 필드 추가 필요

**Phase 3-5a: `_product_to_dict` 직렬화 업데이트 (`html_report_builder.py`)**:
- 현재: `"ingredients": [{"name", "common_name", "category"}]`
- 변경: `"ingredients": [{"name", "common_name", "category", "source"}]` -- source 추가
- 신규: `"ingredients_raw": p.ingredients_raw` -- 전성분 원본 텍스트 추가
- `_ranking_to_dict`에도 `featured_count`, `inci_only_count` 추가

**Phase 3-5b: HTML 렌더링 (`html_report_builder.py`)**:
- Ingredient Ranking 테이블에 Source 컬럼 추가 (badge 표시)
- "Featured Ingredients" 요약 카드 추가 (Ingredient Ranking 섹션 상단):
  - source = "featured" 또는 "both"인 성분만 필터
  - Top 10 Featured Ingredients 표시
  - "These are ingredients brands actively market in titles and feature bullets"
- **Product Detail에서 전성분 확인**:
  - Ingredients 컬럼을 "Featured" 태그가 붙은 성분 + 확장(expand) 버튼으로 표시
  - 클릭 시 전성분(INCI) 목록(`ingredients_raw`)이 드롭다운으로 펼쳐짐
  - 또는 별도 "INCI" 컬럼을 truncated로 표시 + hover/click으로 전체 확인

**Phase 3-6: 하위 호환**:
- `Ingredient.source` 기본값 `""` -- Pydantic 역직렬화 시 누락 필드 허용
- 기존 캐시 데이터: source가 빈 문자열로 로드됨 -> 렌더링 시 "Unknown" 또는 미표시
- 새 Gemini 호출 시에만 source 포함 -> 점진적 마이그레이션

#### 4.3.5 Risk: Gemini 출력 안정성

- Gemini가 `source` 필드를 누락하거나 잘못된 값을 줄 수 있음
- **완화**: Pydantic `source: str = ""` 기본값으로 파싱 실패 방지
- **완화**: `responseMimeType: "application/json"` + JSON 스키마 예시로 구조 강제
- **완화**: 후처리 검증 -- source 값이 `{"featured", "inci", "both", ""}` 외이면 `""` 처리

#### 4.3.6 Impact Range

| File | Change Type | Lines Affected |
|------|------------|----------------|
| `models.py` | Ingredient에 source 필드, IngredientRanking에 featured/inci count, WeightedProduct에 ingredients_raw | ~72-76, ~101-130, ~132-141 |
| `gemini.py` | PROMPT_TEMPLATE 규칙 + 출력 예시 수정 | ~35-86 |
| `analyzer.py` | _aggregate_ingredients에서 source 집계, ingredients_raw 전달 | ~64-116 |
| `excel_builder.py` | Featured Ingredients + Full INCI 2컬럼 표시 | ~220-253 |
| `html_report_builder.py` | Ingredient Ranking Source 컬럼, Featured 카드, Product Detail 전성분 확장 | ~1576-1648, ~1725-1760 |
| `product_db.py` / `data_collector.py` | ingredients_raw를 WeightedProduct로 전달 | 쿼리/매핑 추가 |

---

### 4.4 REQ-4: Drilldown for Aggregated Items

#### 4.4.1 Current State Analysis

**TableController 클래스** (line 859-960):
- 페이지네이션, 정렬, 검색, 필터 기능 내장
- 셀 클릭 이벤트 핸들링 없음
- 드릴다운/확장 기능 없음

**드릴다운이 필요한 섹션** (리포트 유형별):

| Section | Aggregation Field | 카테고리 | 키워드 | What Users Want to See |
|---------|------------------|:-------:|:------:|----------------------|
| Brand Positioning | `product_count` | O | X (시트 없음) | 해당 브랜드의 모든 제품 (ASIN, title, price, BSR) |
| Ingredient Ranking | `product_count` | O | O | 해당 성분 포함 제품 목록 |
| Category Summary | `type_count`, `mention_count` | O | O | 해당 카테고리의 성분 목록, 관련 제품 |

**Excel 대응 방안**:
- Excel은 인라인 드릴다운이 불가능하므로 **별도 대응하지 않음**
- 대신 Product Detail 시트의 Brand/Ingredients 컬럼을 Excel 필터로 활용 가능
- 이 가이드를 리포트 내 설명 텍스트로 안내 (예: "Product Detail 시트에서 Brand 컬럼을 필터링하여 개별 제품을 확인하세요")

#### 4.4.2 UX Design: Inline Drilldown Panel

**접근 방식**: 클릭 가능한 숫자 -> 테이블 행 아래에 인라인 패널 확장

```
| Brand        | Products | Avg Price | ...
|--------------|----------|-----------|----
| BrandX       | [3] <-click
| +--------------------------------------------------+
| | ASIN       | Title          | Price  | BSR     |
| | B0XXXXX    | Product One... | $29.99 | 1,234   |
| | B0YYYYY    | Product Two... | $34.99 | 2,567   |
| | B0ZZZZZ    | Product Thr... | $19.99 | 5,890   |
| +--------------------------------------------------+
| BrandY       | [2]
```

**대안 고려**:
- Modal/Popup: 컨텍스트 이동으로 UX 단절
- Tooltip: 정보량 부족
- 새 섹션으로 이동: 스크롤 위치 상실
- **인라인 확장 (선택)**: 테이블 컨텍스트 유지, 빠른 확인/닫기

#### 4.4.3 Implementation Plan

**Phase 4-1: TableController 확장**:
```javascript
class TableController {
  constructor({ ..., drilldown = null }) {
    // drilldown: { key: 'product_count', matchKey: 'brand',
    //              sourceData: data.products, columns: [...] }
    this.drilldown = drilldown;
  }

  _render() {
    // 기존 렌더링 + drilldown 가능 셀에 클릭 핸들러
    // 셀 클릭 시 <tr class="drilldown-row"> 삽입
  }
}
```

**Phase 4-2: 드릴다운 데이터 매핑**:
- `REPORT_DATA.products`가 이미 모든 제품 데이터를 포함하고 있음
- Brand 드릴다운: `products.filter(p => p.brand === clickedBrand)`
- Ingredient 드릴다운: `products.filter(p => p.ingredients.some(i => i.common_name === clickedIngredient || i.name === clickedIngredient))`
- Category 드릴다운: `products.filter(p => p.ingredients.some(i => i.category === clickedCategory))`

**Phase 4-3: 드릴다운 패널 렌더링**:
```javascript
_renderDrilldown(row, parentTr) {
  const matchedProducts = this.drilldown.sourceData.filter(
    p => p[this.drilldown.matchKey] === row[this.drilldown.matchKey]
  );

  const drilldownTr = document.createElement('tr');
  drilldownTr.className = 'drilldown-row';
  drilldownTr.innerHTML = `
    <td colspan="${this.columns.length}">
      <div class="drilldown-panel">
        <table class="drilldown-table">
          <thead><tr>
            <th>ASIN</th><th>Title</th><th>Price</th><th>BSR</th><th>Rating</th>
          </tr></thead>
          <tbody>${matchedProducts.map(p => `
            <tr>
              <td class="mono">${p.asin}</td>
              <td><a href="https://www.amazon.com/dp/${p.asin}" target="_blank">${truncate(p.title, 'lg')}</a></td>
              <td>${fmtPrice(p.price)}</td>
              <td>${fmt(p.bsr_category)}</td>
              <td>${fmt(p.rating, 1)}</td>
            </tr>
          `).join('')}</tbody>
        </table>
      </div>
    </td>`;
  parentTr.after(drilldownTr);
}
```

**Phase 4-4: CSS**:
```css
.drilldown-row { background: var(--color-bg-input); }
.drilldown-panel { padding: 12px 16px; max-height: 300px; overflow-y: auto; }
.drilldown-table { width: 100%; font-size: 12px; }
.drilldown-trigger { cursor: pointer; color: var(--color-positive); text-decoration: underline; }
```

**Phase 4-5: Brand Positioning 적용**:
- `product_count` 컬럼의 render를 클릭 가능한 링크로 변경
- drilldown 설정:
  ```javascript
  drilldown: {
    triggerKey: 'product_count',
    matchFn: (row, product) => product.brand === row.brand,
    sourceData: data.products,
  }
  ```

**Phase 4-6: Ingredient Ranking 적용**:
- `product_count` 컬럼에 drilldown 연결
- matchFn: `product.ingredients.some(i => getDisplayName(i) === row.ingredient)`

#### 4.4.4 Impact Range

| File | Change Type | Lines Affected |
|------|------------|----------------|
| `html_report_builder.py` | TableController 확장, 3개 섹션 drilldown 설정, CSS 추가 | ~859-960, ~1460-1475, ~1608-1647, CSS |

---

### 4.5 REQ-5: SNS Price 제거 + 세그먼트별 할인율 분석

#### 4.5.1 제거 대상

**Excel (`excel_builder.py`)**:
- Product Detail 시트: `SNS Price` 컬럼 (현재 col 5, line 226-227) 제거
- Sales & Pricing 시트:
  - SNS Pricing 섹션 (line 810-830 `elif sns:` 분기) 제거
  - 빈 공간 체크 조건문 수정: `if not any([sales, sns, lt, discount, promos])` (line 681) → `sns` 제거
  - 제거된 SNS 분기 위치에 Discount Strategy by Segment 테이블 삽입

**HTML (`html_report_builder.py`)**:
- Product Detail TableController: `sns_price` 컬럼 (line 1742) 제거
- Sales & Pricing 섹션:
  - SNS 채택률/할인율 카드 (line 1323-1334 `if (sns && sns.sns_adoption_pct > 0)` 분기) 제거
  - `const sns = data.analysis && data.analysis.sns_pricing` (line 1246) → `discount_analysis` 참조로 변경
  - 빈 섹션 체크 `if (!sv && !sns && !disc && !lt)` (line 1250) → `sns` 제거, `discountSeg` (새 변수) 추가

**Gemini (`gemini.py`) — 전수 조사 결과**:
- `generate_market_report()` (line 297-306): BSR 분석 시 `has_listing_tactics` 분기:
  - `has_listing_tactics=True` → Section 9 = "리스팅 전술 분석", `section6_guidance` = "Sponsored/쿠폰/A+ 분석"
  - `has_listing_tactics=False` → Section 9 = "Subscribe & Save 가격 분석", `section6_guidance` = "SNS 채택 현황" ← **이 분기 전체 수정 필요**
- 변경:
  1. `has_listing_tactics=False` 분기의 `section9_title` → `"세그먼트별 할인 전략 분석"`
  2. `section9_json` → `_dump("discount_analysis")` (기존 `_dump("sns_pricing")`)
  3. `section6_guidance` → `"세그먼트별 할인율, 할인/비할인 판매량 비교"` (기존 SNS 멘션)
  4. `MARKET_REPORT_PROMPT` 내 Section 9 설명 텍스트도 SNS → Discount로 변경

**Market Analyzer (`market_analyzer.py`)**:
- `analyze_sns_pricing()` 함수 (line 316-394): 호출 중단 (함수 자체는 유지, 호출만 제거)
- `build_market_analysis()` (line 1147): `"sns_pricing": analyze_sns_pricing(...)` → `"discount_analysis": analyze_discount_by_segment(...)`
- `build_keyword_market_analysis()` (line 1115): 동일하게 교체 ← **키워드 플로우 누락 방지**

**Serialization (`html_report_builder.py`)**:
- `_product_to_dict`: `sns_price` 필드는 JSON에 유지 (하위 호환), 렌더링 컬럼만 제거

#### 4.5.2 추가: 세그먼트별 할인율 분석

**새 분석 함수 (`market_analyzer.py`)**:
```python
def analyze_discount_by_segment(products: list[WeightedProduct]) -> dict:
    """세그먼트(Budget/Mid/Premium/Luxury)별 할인 전략 분석."""
    # 각 세그먼트별:
    # - 할인 제품 비율 (initial_price > final_price인 제품 수 / 총 제품 수)
    # - 평균 할인율
    # - 최대 할인율
    # - 할인 유무에 따른 Bought/Mo 평균 비교
    # - 할인 가격 구간 분포
```

**데이터 구조**:
```json
{
  "discount_analysis": {
    "overall": {
      "total_products": 50,
      "discounted_count": 32,
      "discount_rate": 64.0,
      "avg_discount_pct": 18.5
    },
    "by_segment": {
      "Budget": {
        "total": 15, "discounted": 8, "discount_rate": 53.3,
        "avg_discount_pct": 12.1, "max_discount_pct": 25.0,
        "avg_bought_discounted": 5200, "avg_bought_non_discounted": 3100
      },
      "Mid": { ... },
      "Premium": { ... },
      "Luxury": { ... }
    }
  }
}
```

**Excel 표시 (Sales & Pricing 시트)**:
- 기존 SNS 섹션 위치에 "Discount Strategy by Segment" 테이블 삽입
- 컬럼: Segment, Total, Discounted, Discount Rate, Avg Discount%, Max Discount%, Avg Bought (Discounted vs Non-discounted)

**HTML 표시 (Sales & Pricing 섹션)**:
- SNS 카드 대신 "Discount Strategy by Segment" 카드 표시
- 세그먼트별 바 차트 (할인율) + 테이블
- 할인/비할인 제품의 판매량 비교 인사이트

**Gemini Market Report**:
- BSR 분석 시 Section 9를 `"세그먼트별 할인 전략 분석"` 으로 변경
- `discount_analysis` 데이터를 전달하여 세그먼트별 할인 인사이트 생성

#### 4.5.3 Impact Range

| File | Change Type | Lines Affected |
|------|------------|----------------|
| `excel_builder.py` | SNS Price 컬럼 제거 (Phase 2), SNS 섹션→Discount 대체, 조건문 수정 | ~226-227, ~675-681, ~810-830 |
| `html_report_builder.py` | sns_price 컬럼 제거 (Phase 2), SNS 카드→Discount 대체, 변수/조건문 수정 | ~1246-1250, ~1323-1334, ~1742 |
| `market_analyzer.py` | `analyze_discount_by_segment()` 신규, `build_market_analysis()` + `build_keyword_market_analysis()` 교체 | ~316-394, ~1115, ~1147, 신규 |
| `gemini.py` | `has_listing_tactics=False` 분기 전체: section9_title, section9_json, section6_guidance | ~297-306 |

---

## 5. Success Criteria

### 5.1 Definition of Done

- [ ] REQ-1: Excel/HTML에서 Initial Price + Discount% 표시 확인
- [ ] REQ-2: Excel 타이틀 클릭 시 Amazon 페이지 오픈 확인
- [ ] REQ-2: HTML 타이틀 클릭 시 새 탭에서 Amazon 페이지 오픈 확인
- [ ] REQ-3: 새 Gemini 추출 결과에 source 필드 포함 확인
- [ ] REQ-3: 기존 캐시 데이터로 리포트 생성 시 에러 없음 확인
- [ ] REQ-3: Featured Ingredients 카드가 HTML에 표시 확인
- [ ] REQ-4: Brand Positioning에서 product_count 클릭 시 드릴다운 동작 확인
- [ ] REQ-4: Ingredient Ranking에서 product_count 클릭 시 드릴다운 동작 확인
- [ ] REQ-5: SNS Price 컬럼/섹션이 Excel/HTML에서 완전히 제거 확인
- [ ] REQ-5: 세그먼트별 할인율 분석 테이블이 Sales & Pricing에 표시 확인
- [ ] REQ-3: Product Detail에서 전성분(INCI) 목록 확인 가능 여부 검증
- [ ] 50+ 제품 리포트에서 성능 저하 없음 확인

### 5.2 Quality Criteria

- [ ] 기존 리포트 기능 regression 없음
- [ ] ASIN 형식 검증으로 잘못된 URL 생성 방지
- [ ] Gemini source 필드 누락 시 graceful fallback 동작

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Gemini가 source 필드를 정확히 분류하지 못함 | Medium | Medium | 프롬프트에 명확한 예시 제공 + 후처리 검증 + 기본값 fallback |
| Excel 컬럼 시프트로 기존 매크로/자동화 스크립트 깨짐 | Low | Low | 컬럼 헤더 기반 매칭 권장, 릴리즈 노트 명시 |
| 드릴다운 패널이 대량 제품(100+) 시 느려짐 | Medium | Low | 드릴다운 내 maxRows 제한 (상위 20개 + "and N more" 표시) |
| 기존 성분 캐시에 source 없어 Featured 분석 불완전 | Medium | High | 캐시 재생성 트리거 제공, 레거시 데이터는 "Unknown" 표시 |
| openpyxl hyperlink 셀이 일부 스프레드시트에서 미동작 | Low | Low | 대안으로 URL 컬럼 유지 |
| SNS 제거 시 기존 리포트와 컬럼 위치 불일치 | Low | Medium | 컬럼 헤더 기반 참조 권장, 릴리즈 노트 명시 |
| 할인 데이터 부족 (initial_price 미수집 제품) | Medium | Medium | initial_price 없는 제품은 할인 분석에서 제외, 분석 대상 수 명시 |

---

## 7. Architecture Considerations

### 7.1 Project Level

이 프로젝트는 도메인 모듈 구조(amz_researcher 패키지)를 사용하며, CLAUDE.md의 "프로젝트급 도메인" 분류에 해당한다. 이번 변경은 기존 구조 내에서 수행되며 새 패키지 생성은 불필요하다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 성분 source 구분 방식 | 2회 호출 / 프롬프트 수정 / 후처리 매칭 | 프롬프트 수정 | 비용/지연 증가 없음, 정확도 높음 |
| 드릴다운 UX | Modal / Inline / New Section | Inline Expand | 컨텍스트 유지, UX 단절 없음 |
| Excel 타이틀 링크 | HYPERLINK 수식 / 셀 hyperlink 속성 | 셀 hyperlink 속성 | openpyxl native, 더 안정적 |
| HTML 가격 표시 | 별도 컬럼 / 복합 렌더링 | 복합 렌더링 | 컬럼 수 증가 방지, 가독성 향상 |
| SNS Price 대체 | SNS 유지+할인 추가 / SNS 제거+할인 대체 | SNS 제거+할인 대체 | 실무 활용도 기반 의사결정, 세그먼트 할인 분석이 더 유효 |
| 전성분 표시 방식 | 별도 컬럼 / 확장 UI | Excel: 별도 컬럼, HTML: 확장 UI | Excel은 셀 복사 편의, HTML은 화면 공간 절약 |

### 7.3 Data Flow (변경 후)

```
Gemini Prompt (source 지시 추가)
  |
  v
Ingredient(name, common_name, category, source)  <-- NEW: source field
  |
  v
analyzer.py: _aggregate_ingredients
  -> IngredientRanking (+ featured_count, inci_only_count)
  |
  v
Excel: Featured Ingredients 컬럼 + Full INCI 컬럼 (별도)
HTML:  Source badge in Ingredient Ranking table
       Featured Ingredients summary card
       Product Detail: Featured 태그 + INCI 확장 UI

market_analyzer.py: analyze_discount_by_segment() <-- NEW
  -> discount_analysis (overall + by_segment)
  |
  v
Excel: Discount Strategy by Segment 테이블 (SNS 섹션 대체)
HTML:  Discount Strategy 카드 + 바 차트 (SNS 카드 대체)

Products data (REPORT_DATA.products)
  -> used by drilldown panels in Brand/Ingredient/Category sections
```

---

## 8. Implementation Order

의존성과 리스크를 고려한 구현 순서:

> **⚠️ 핵심 의존성**: REQ-1(Initial Price 삽입)과 REQ-5(SNS Price 제거)가 Excel 같은 col 5 위치에서 충돌하므로 **Phase 2에서 통합 처리**한다.

```
Phase 1: REQ-2 (Title Hyperlinks)              [독립, 낮은 리스크]
  - excel_builder.py: hyperlink 속성 추가
  - html_report_builder.py: 3개 섹션 title 렌더 변경
    (카테고리: Product Detail + Raw Search + Rising Products)
    (키워드: Product Detail + Raw Search)
  - 테스트: Excel/HTML 양쪽 리포트에서 링크 동작 확인

Phase 2: REQ-1 + REQ-5 Excel 컬럼 (통합)       [컬럼 시프트 충돌 해결]
  - excel_builder.py: SNS Price(col 5) 제거 + 같은 자리에 Initial Price 삽입
    → 기존 col 6 이후 번호 변동 없음 (시프트 상쇄)
  - html_report_builder.py: Price 복합 렌더링, sns_price 컬럼 제거
  - 테스트: 할인 있는/없는 제품, SNS 컬럼 부재 확인

Phase 3: REQ-3 (Ingredients Overhaul)          [핵심, 높은 복잡도]
  - 3-1: models.py — Ingredient.source, WeightedProduct.ingredients_raw 추가
  - 3-2: product_db.py/orchestrator.py — ingredients_raw 전달 경로 구축
  - 3-3: gemini.py 프롬프트 수정 (source 분류 지시)
  - 3-4: analyzer.py source 집계
  - 3-5a: html_report_builder.py _product_to_dict 직렬화 (source, ingredients_raw)
  - 3-5b: html_report_builder.py Ingredient Ranking Source 컬럼 + Featured 카드
  - 3-5c: html_report_builder.py Product Detail 전성분 확장 UI
  - 3-6: excel_builder.py Featured Ingredients + Full INCI 2컬럼
  - 3-7: 하위 호환 테스트 (레거시 캐시 데이터)
  - 테스트: Gemini 실제 호출로 source 출력 확인
  - ※ 카테고리/키워드 양쪽 플로우 모두 적용

Phase 4: REQ-5 분석 계층 (SNS→Discount)        [Phase 2 Excel 이후]
  - 4-1: market_analyzer.py: analyze_discount_by_segment() 신규 작성
  - 4-2: market_analyzer.py: build_market_analysis() + build_keyword_market_analysis()
         → sns_pricing → discount_analysis 교체 (양쪽 플로우)
  - 4-3: excel_builder.py: Sales & Pricing SNS 섹션 → Discount 테이블
         (조건문 `if not any([sales, sns, ...])` → sns 제거)
  - 4-4: html_report_builder.py: SNS 카드 → Discount 카드 (조건문 수정 포함)
  - 4-5: gemini.py: has_listing_tactics=False 분기 전체 수정
         (section9_title, section9_json, section6_guidance)
  - 테스트: SNS 흔적 전수 제거 확인 + 할인 분석 데이터 검증

Phase 5: REQ-4 (Drilldown)                    [Phase 1 이후, HTML only]
  - 5-1: TableController drilldown 확장 (공통 인프라)
  - 5-2: Brand Positioning 적용 (카테고리 리포트만)
  - 5-3: Ingredient Ranking 적용 (양쪽 리포트)
  - 5-4: Category Summary 적용 (양쪽 리포트)
  - 테스트: 카테고리/키워드 각각 드릴다운 동작 확인
  - ※ Excel에서는 별도 대응 없음 (필터 가이드 안내)
```

**의존성 그래프**:
```
Phase 1 (Hyperlink) ──────────────────┐
                                      ├─→ Phase 5 (Drilldown)
Phase 2 (Price+SNS컬럼) ──→ Phase 4 (SNS분석→Discount) ─┘
Phase 3 (Ingredients) ─── 독립 진행 가능
```

Phase 1, 2는 병렬 가능. Phase 3도 독립 진행 가능하나 가장 복잡하므로 먼저 시작. Phase 4는 Phase 2의 Excel SNS 제거 이후 분석 계층 교체. Phase 5는 Phase 1의 hyperlink 패턴을 드릴다운 패널에도 재사용.

---

## 9. Next Steps

1. [ ] 이 Plan 문서 리뷰 및 승인
2. [ ] Design 문서 작성 (`report-enhancement-v7.design.md`)
3. [ ] Phase 1-2 병렬 구현 착수
4. [ ] Phase 3 Gemini 프롬프트 변경 후 소수 제품으로 출력 검증
5. [ ] Phase 4 드릴다운 프로토타입 구현
6. [ ] 전체 통합 테스트 (50+ 제품 리포트)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial draft - 4 requirements analysis and plan | CTO Lead |
| 0.2 | 2026-03-11 | REQ-5 추가 (SNS 제거 + 세그먼트별 할인 분석), REQ-3에 전성분 확인 기능 추가 | CTO Lead |
| 0.3 | 2026-03-11 | 7가지 검토 결과 반영: 키워드 리포트 적용 범위, ingredients_raw 전달 경로, 컬럼 시프트 충돌 해결, Excel 드릴다운 대응, _product_to_dict 직렬화, Gemini SNS 분기 전수 조사, Sales & Pricing 조건문 | CTO Lead |
