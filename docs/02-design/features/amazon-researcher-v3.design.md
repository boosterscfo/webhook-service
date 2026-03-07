# Design: Amazon Researcher V3 — 성분 정규화 + 시장 분석 리포트

> Plan: `docs/01-plan/features/amazon-researcher-v3.plan.md`
> V2 Design: `docs/02-design/features/amazon-researcher-v2.design.md`

---

## 1. File Structure (V2 대비 변경사항)

```
amz_researcher/
├── models.py                        # Ingredient.common_name 추가
├── orchestrator.py                  # 시장 분석 파이프라인, analysis_data 전달
└── services/
    ├── gemini.py                    # 프롬프트 강화, asyncio.gather 병렬, 시장 리포트
    ├── cache.py                     # common_name, harmonize, market_report, failed_asins
    ├── analyzer.py                  # _get_display_name (common_name 우선)
    ├── market_analyzer.py           # 신규: 8개 시장 분석 함수
    ├── excel_builder.py             # 4개 시트 추가, Market Insight 첫 시트
    └── slack_sender.py              # channel_id fallback
```

---

## 2. Data Model 변경

### `Ingredient` (models.py)

```python
class Ingredient(BaseModel):
    name: str           # INCI 학명 원본 (예: "Argania Spinosa Kernel Oil")
    common_name: str = ""  # 마케팅용 일반명 (예: "Argan Oil")
    category: str
```

---

## 3. Gemini Service 변경 (`services/gemini.py`)

### 3.1 프롬프트 변경

```
작업:
1. INCI 전성분에서 핵심 성분 선별
2. title, features, additional_details 참고하여 성분 맥락 파악
   - title에 명시된 핵심 성분은 반드시 포함
   - ingredients_raw 비어있어도 title/features에서 추출 가능

규칙:
1. name: INCI 전성분 원본 그대로
2. common_name: 마케팅용 일반명으로 통일
   - 같은 식물이면 부위 무관하게 동일 common_name
   - 형태(Extract, Oil)만 구분
   예: "Argania Spinosa Kernel Oil" → "Argan Oil"
       "Rosmarinus Officinalis Leaf Extract" → "Rosemary Extract"
       "Tocopherol" / "Tocopheryl Acetate" → "Vitamin E"
```

JSON 출력:
```json
{
  "products": [
    {
      "asin": "...",
      "ingredients": [
        {"name": "Argania Spinosa Kernel Oil", "common_name": "Argan Oil", "category": "Natural Oil"}
      ]
    }
  ]
}
```

### 3.2 Gemini 입력 데이터

```python
products_for_gemini = [
    {
        "asin": asin,
        "title": title_map.get(asin, ""),      # V3 추가
        "ingredients_raw": detail.ingredients_raw,
        "features": detail.features,
        "additional_details": detail.additional_details,
    }
]
```

### 3.3 병렬 배치 처리

```python
async def extract_ingredients(self, products, batch_size=20):
    batches = [products[i:i+batch_size] for i in range(0, len(products), batch_size)]
    tasks = [self._extract_batch(batch) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 실패 배치는 로그 후 스킵, 성공분만 수집
```

- `batch_size`: 25 → 20 (JSON 잘림 방지)
- `maxOutputTokens`: 16384 → 32768
- `responseMimeType`: `application/json` (구조화 출력)

### 3.4 시장 리포트 생성

```python
async def generate_market_report(self, analysis_data: dict) -> str:
    # 8개 분석 섹션 JSON을 프롬프트에 삽입
    # temperature=0.3, maxOutputTokens=16384
    # 마크다운 텍스트 출력
```

8개 섹션: 시장 요약, 가격대별 전략, 제형 트렌드, 승리 공식, 경쟁 환경, 급성장 제품, 액션 아이템, 리스크

---

## 4. Cache Service 변경 (`services/cache.py`)

### 4.1 Ingredient 캐시: common_name 지원

```sql
ALTER TABLE amz_ingredient_cache ADD COLUMN common_name VARCHAR(255) DEFAULT '';
```

- `get_ingredient_cache`: `common_name` SELECT/반환
- `save_ingredient_cache`: `common_name` INSERT

### 4.2 harmonize_common_names()

```python
def harmonize_common_names(self) -> int:
    # 1. GROUP BY ingredient_name, common_name → COUNT
    # 2. 각 ingredient_name에 대해 최다 빈도 common_name 선택
    # 3. 동수 시 earliest extracted_at 우선
    # 4. UPDATE 불일치 레코드
```

### 4.3 시장 리포트 캐시

```python
def get_market_report_cache(self, keyword, product_count) -> str | None
def save_market_report_cache(self, keyword, report, product_count)
```

### 4.4 실패 ASIN 추적

```python
def get_failed_asins(self) -> set[str]
def save_failed_asins(self, asins, keyword)
```

---

## 5. Market Analyzer (`services/market_analyzer.py`) — 신규

### Public Interface

```python
def build_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
        "form_price_matrix": analyze_form_by_price(weighted_products, details),
        "brand_positioning": analyze_brand_positioning(weighted_products, details),
        "rising_products": detect_rising_products(weighted_products, details),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
    }
```

### 분석 함수 상세

| 함수 | 입력 | 출력 | 로직 |
|------|------|------|------|
| `analyze_by_price_tier` | weighted_products | {tier: {count, top5}} | Budget/Mid/Premium/Luxury 4구간 |
| `analyze_by_bsr` | weighted_products | {top, bottom, winning} | 상위/하위 20% 비교 |
| `analyze_by_brand` | products, details | [{brand, count, avg_price, top_ingredients}] | 2개+ 제품 브랜드만 |
| `analyze_cooccurrence` | weighted_products | {top_pairs, high_rated_exclusive} | 성분 쌍 빈도 |
| `analyze_form_by_price` | products, details | {matrix, form_summary} | Item Form x 가격대 |
| `analyze_brand_positioning` | products, details | [{brand, avg_price, avg_bsr, segment}] | 가격-BSR 매핑 |
| `detect_rising_products` | products, details | [{asin, title, bsr, reviews, ...}] | 리뷰 < median & BSR < 10000 |
| `analyze_rating_ingredients` | weighted_products | {high_only, low_only, high_top10, low_top10} | 4.5+ vs <4.3 |

### 가격대 구간

```python
def _price_tier(price):
    if price < 10: return "Budget (<$10)"
    if price < 25: return "Mid ($10-25)"
    if price < 50: return "Premium ($25-50)"
    return "Luxury ($50+)"
```

---

## 6. Analyzer 변경 (`services/analyzer.py`)

### common_name 기반 집계

```python
def _get_display_name(ing) -> str:
    return ing.common_name if ing.common_name else ing.name
```

- `_aggregate_ingredients`: `_get_display_name(ing)`을 집계 키로 사용
- `_normalize_ingredient_name`, `_INCI_RE`, `_SYNONYM_MAP` 제거 (Gemini 기반으로 대체)

---

## 7. Excel Builder 변경 (`services/excel_builder.py`)

### 시트 순서 (V3)

| # | 시트명 | 설명 | 비고 |
|---|--------|------|------|
| 1 | Market Insight | AI 리포트 (단일 셀 A4, Notion 복붙) | `wb.move_sheet`로 맨 앞 |
| 2 | Ingredient Ranking | 성분 가중치 랭킹 | 기존 |
| 3 | Category Summary | 카테고리 요약 | 기존 |
| 4 | Product Detail | 제품별 데이터 | 기존 |
| 5 | Rising Products | 급성장 제품 (BSR/Brand/Form/Ingredients) | 신규 |
| 6 | Form x Price | 제형 성과 + 가격대 매트릭스 | 신규 |
| 7 | Raw - Search Results | 검색 원본 | 기존 |
| 8 | Raw - Product Detail | 상세 원본 | 기존 |
| 9 | Analysis Data | Gemini 입력 원본 JSON (8개 섹션) | 신규 |

### 신규 함수

```python
def _build_rising_products(wb, rising: list[dict])
    # BSR, Brand, Title, Price, Reviews, Rating, Form, Top Ingredients, ASIN

def _build_form_price(wb, form_data: dict)
    # Part 1: Form Summary (form, count, avg_price, avg_rating, avg_reviews, avg_bsr)
    # Part 2: Price Tier x Form Matrix

def _build_analysis_data(wb, analysis_data: dict)
    # 8개 분석 섹션의 JSON을 섹션별 헤더 + JSON 텍스트로 출력

def _build_market_insight(wb, keyword, report_md)
    # A4 단일 셀에 전체 마크다운 리포트 (Notion 복붙 지원)
```

### build_excel 시그니처

```python
def build_excel(
    keyword, weighted_products, rankings, categories,
    search_products, details,
    market_report="",
    rising_products=None,
    form_price_data=None,
    analysis_data=None,
) -> bytes
```

---

## 8. Slack Sender 변경 (`services/slack_sender.py`)

### channel_id fallback

```python
async def send_message(self, response_url, text, ephemeral=False, channel_id=""):
    if response_url:
        # 기존: response_url POST
    elif channel_id:
        # fallback: chat.postMessage API
```

---

## 9. Orchestrator 변경 (`orchestrator.py`)

### V3 파이프라인

```
Step 1: Search (캐시 우선)
Step 2: Detail (캐시 우선, 실패 ASIN 스킵)
Step 3: Gemini 성분 추출 (캐시 우선, 병렬 배치) + harmonize
Step 4: Weight calculation
Step 5: 시장 분석 데이터 생성 + AI 리포트 (캐시 우선)
Step 6: Excel 생성 (analysis_data 포함)
Step 7: Slack 요약 메시지 (액션 아이템 포함)
Step 8: Excel 파일 업로드
```

### 주요 변경점

- `_msg()` 헬퍼: `response_url` + `channel_id` 전달
- `title_map` 생성: Gemini 입력에 `title` 포함
- `analysis_data = build_market_analysis(keyword, weighted_products, all_details)`
- `build_excel(..., analysis_data=analysis_data)`
- 시장 리포트에서 `## 7.` (액션 아이템) 섹션 추출 → Slack 요약에 포함

---

## 10. Sequence Diagram (V3)

```
Slack      Router    Orchestrator    Cache     BrowseAi    Gemini
  |          |            |            |          |          |
  |--/amz--->|            |            |          |          |
  |<-200 OK--|            |            |          |          |
  |          |--run_research---------->|          |          |
  |          |            |--search--->|          |          |
  |          |            |<--cache----|          |          |
  |          |            |--detail--->| (skip failed ASINs) |
  |          |            |<--cache----|          |          |
  |          |            |--ingredients-->|      |          |
  |          |            |<--cache-------|      |          |
  |          |            |--uncached (parallel)----------->|
  |          |            |<--gemini results----------------|
  |          |            |--harmonize-->|        |          |
  |          |            |             |        |          |
  |          |            |--market analysis (local calc)   |
  |          |            |--market report (cache or Gemini)|
  |          |            |             |        |          |
  |          |            |--build_excel (9 sheets)         |
  |          |            |--slack summary + file upload    |
```

---

## 11. Implementation Order

| Phase | 파일 | 작업 |
|-------|------|------|
| 1 | `models.py` | `Ingredient.common_name` 추가 |
| 2 | `services/gemini.py` | 프롬프트 강화 + 병렬 배치 + 시장 리포트 |
| 3 | `services/cache.py` | common_name, harmonize, market_report, failed_asins |
| 4 | `services/analyzer.py` | `_get_display_name`, 동의어 맵 제거 |
| 5 | `services/market_analyzer.py` | 8개 분석 함수 신규 |
| 6 | `services/excel_builder.py` | 4개 시트 추가, Market Insight 첫 시트 |
| 7 | `services/slack_sender.py` | channel_id fallback |
| 8 | `orchestrator.py` | 시장 분석 파이프라인, analysis_data 전달 |
