# dynamic-marketing-keywords Design Document

> **Summary**: Gemini Flash 1회 호출로 카테고리 맞춤 마케팅 키워드를 동적 추출하고, 기존 title keyword BSR/판매량 분석 파이프라인에 주입
>
> **Project**: webhook-service (amz_researcher)
> **Author**: Design Phase
> **Date**: 2026-03-11
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/dynamic-marketing-keywords.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 하드코딩 22개 스킨케어 마케팅 키워드가 카테고리 무관 동일 적용 |
| **Solution** | Gemini Flash에 전체 title을 1회 전달, 카테고리 맞춤 키워드 리스트를 JSON으로 반환 |
| **Function/UX Effect** | 리포트의 Title Keywords 섹션이 카테고리별 실제 마케팅 트렌드를 반영 |
| **Core Value** | Flash 1회 $0.001로 모든 카테고리에서 정확한 마케팅 키워드 분석 제공 |

---

## 1. Architecture Overview

### 1.1 데이터 흐름

```
orchestrator.py (async)
  |
  |  [기존] gemini.extract_voice_keywords()
  |
  |  [신규] Gemini 마케팅 키워드 추출
  |  |
  |  |  gemini.extract_title_keywords(
  |  |    category_name,
  |  |    weighted_products,
  |  |  )
  |  |  -> TitleKeywordResult
  |  |    { keywords: ["Organic", "Vegan", "Hyaluronic Acid", ...] }
  |  |
  |
  |  build_market_analysis(..., title_keywords=result)
  |    -> analyze_title_keywords(products, title_keywords)
  |         |-- title_keywords 있으면 -> 동적 키워드로 title 매칭
  |         |-- title_keywords 없으면 -> 기존 하드코딩 fallback
  |
  |  [기존] gemini.generate_market_report(analysis_data)
```

### 1.2 변경 범위

| 파일 | 변경 내용 | 영향도 |
|------|----------|--------|
| `models.py` | `TitleKeywordResult` Pydantic 모델 추가 | Low (추가만) |
| `gemini.py` | `extract_title_keywords()` 메서드 추가 | Low (추가만) |
| `market_analyzer.py` | `analyze_title_keywords()` 시그니처 확장 + 동적 매칭 로직 | Medium |
| `market_analyzer.py` | `build_market_analysis()`, `build_keyword_market_analysis()` 파라미터 추가 | Low |
| `orchestrator.py` | 3곳에 Gemini 키워드 호출 삽입 | Medium |

---

## 2. Detailed Design

### 2.1 Pydantic 모델 (`models.py`)

```python
class TitleKeywordResult(BaseModel):
    keywords: list[str] = []
```

단순한 문자열 리스트. customer_voice와 달리 긍정/부정 분류가 불필요하고, ASIN 매핑도 코드에서 title 매칭으로 수행.

### 2.2 Gemini 프롬프트 (`gemini.py`)

#### 프롬프트 템플릿

```python
TITLE_KEYWORD_PROMPT = """아래는 아마존 "{category_name}" 카테고리 제품 {count}개의 제목(title)이다.

{title_block}

이 카테고리의 제품 제목에서 반복적으로 사용되는 핵심 마케팅 키워드를 추출하라.

규칙:
1. 이 카테고리에 특화된 마케팅 키워드만 추출
2. 포함 대상: 성분명 (Hyaluronic Acid, Retinol 등), 인증/클레임 (Organic, Vegan 등), 제품 특성 (Fragrance-Free, Waterproof 등)
3. 브랜드명, 제품 유형(Cream, Serum 등), 숫자(100ml, 2-Pack 등)는 제외
4. 각 키워드는 1-3 단어로 간결하게
5. 15-25개 범위로 추출
6. 3개 이상의 제품 제목에서 사용된 키워드만 포함

JSON 출력:
{{
  "keywords": ["keyword1", "keyword2", ...]
}}"""
```

#### title_block 포맷

```
CeraVe Moisturizing Cream | Organic Hyaluronic Acid Body and Face...
Neutrogena Hydro Boost Water Gel, Fragrance-Free, Lightweight...
```

- title만 나열 (ASIN 불필요 - 매칭은 코드에서 수행)
- 빈 title 제외

### 2.3 GeminiService 메서드 (`gemini.py`)

```python
async def extract_title_keywords(
    self,
    category_name: str,
    products: list[WeightedProduct],
) -> TitleKeywordResult | None:
    """title에서 카테고리 맞춤 마케팅 키워드 동적 추출.

    Returns None on failure (caller falls back to hardcoded keywords).
    """
```

**설계 결정:**
- **모델**: Flash (self.url) -- 키워드 추출은 경량 작업
- **temperature**: 0.1 -- 일관성
- **responseMimeType**: `"application/json"` -- structured output 강제
- **maxOutputTokens**: 4096 -- 키워드 JSON은 ~200 토큰이면 충분, 여유 확보
- **thinkingConfig**: `{"thinkingBudget": 0}` -- thinking 비활성화 (단순 추출)
- **재시도**: 1회 (for attempt in range(2))
- **최소 제품 수**: title이 있는 제품이 10개 미만이면 None 반환

**에러 핸들링:**
1. API 호출 실패 -> `logger.warning` + retry 1회 후 return None
2. JSON 파싱 실패 -> return None
3. Pydantic validation 실패 -> return None
4. 모든 실패 케이스에서 caller가 기존 하드코딩 키워드로 fallback

### 2.4 analyze_title_keywords 리팩토링 (`market_analyzer.py`)

#### 시그니처 변경

```python
# Before
def analyze_title_keywords(products: list[WeightedProduct]) -> dict:

# After
def analyze_title_keywords(
    products: list[WeightedProduct],
    title_keywords: TitleKeywordResult | None = None,
) -> dict:
```

#### 동적 키워드 매칭 로직

```python
def analyze_title_keywords(
    products: list[WeightedProduct],
    title_keywords: TitleKeywordResult | None = None,
) -> dict:
    if title_keywords and title_keywords.keywords:
        marketing_keywords = title_keywords.keywords
    else:
        # Fallback: 기존 하드코딩 키워드
        marketing_keywords = [
            "Organic", "Natural", "Korean", "Vegan", "Sulfate-Free",
            "Dermatologist", "Clinical", "Hyaluronic", "Retinol", "Vitamin C",
            "Collagen", "Niacinamide", "Salicylic", "SPF", "Cruelty-Free",
            "Fragrance-Free", "Paraben-Free", "Gluten-Free", "Alcohol-Free",
            "Sensitive", "Anti-Aging", "Moisturizing",
        ]

    keyword_products: dict[str, list[WeightedProduct]] = {kw: [] for kw in marketing_keywords}

    for p in products:
        title_lower = p.title.lower()
        for kw in marketing_keywords:
            if kw.lower() in title_lower:
                keyword_products[kw].append(p)

    # ... 이하 기존 _kw_metrics, sorting 로직 동일
```

#### 출력 포맷 (호환성 유지)

반환 dict 구조는 기존과 **완전히 동일**:

```python
{
    "total_products": int,
    "keyword_analysis": {
        "keyword_name": {"count": int, "avg_bsr": int|None, "avg_bought": int|None},
        ...
    },
}
```

Excel builder, HTML report builder, Gemini 리포트 프롬프트 모두 변경 불필요.

### 2.5 build 함수 파라미터 추가 (`market_analyzer.py`)

```python
# Before
def build_market_analysis(keyword, weighted_products, details, voice_keywords=None) -> dict:
def build_keyword_market_analysis(keyword, weighted_products, details, voice_keywords=None) -> dict:

# After
def build_market_analysis(keyword, weighted_products, details, voice_keywords=None, title_keywords=None) -> dict:
def build_keyword_market_analysis(keyword, weighted_products, details, voice_keywords=None, title_keywords=None) -> dict:
```

내부에서 `analyze_title_keywords(weighted_products, title_keywords)` 호출.
기존 호출부에서 `title_keywords`를 전달하지 않으면 None -> 기존 동작 그대로.

### 2.6 orchestrator.py 연동 (3곳)

#### 패턴 (3곳 모두 동일)

voice_keywords 추출 직후, build_market_analysis 호출 전에 삽입:

```python
# voice_keywords 추출 직후 추가
title_keywords = await gemini.extract_title_keywords(
    category_name,  # 또는 keyword/normalized_keyword
    weighted_products,
)

analysis_data = build_market_analysis(
    keyword, weighted_products, all_details,
    voice_keywords=voice_keywords,
    title_keywords=title_keywords,
)
```

#### 수정 위치

| 함수 | 라인 | keyword 파라미터 |
|------|------|-----------------|
| `run_analysis()` | L480 직전 | `keyword` |
| `run_category_analysis()` | L814 직전 | `category_name` |
| `run_keyword_search_analysis()` | L1173 직전 | `normalized_keyword` |

---

## 3. Error Handling & Fallback

### 3.1 Fallback 체인

```
Gemini 호출 성공 -> TitleKeywordResult -> 동적 키워드 분석
        | 실패
Gemini 재시도 1회
        | 실패
return None -> analyze_title_keywords의 title_keywords=None
        |
기존 하드코딩 22개 키워드 매칭
```

### 3.2 실패 조건별 처리

| 조건 | 처리 |
|------|------|
| title이 있는 제품 < 10개 | Gemini 호출 스킵, 하드코딩 fallback |
| API 호출 실패 (네트워크/타임아웃) | 1회 재시도 후 None 반환 |
| JSON 파싱 실패 | None 반환 |
| Pydantic validation 실패 | None 반환 |
| 추출된 키워드가 0개 | None 반환 (하드코딩 fallback) |

---

## 4. Cost Analysis

| 항목 | 값 |
|------|-----|
| 모델 | gemini-2.5-flash |
| Input tokens (100개 제품) | ~5,000 |
| Output tokens (키워드 JSON) | ~200 |
| 1회 호출 비용 | ~$0.001 |
| 월간 추가 비용 (300건) | ~$0.30 |
| 기존 Pro 리포트 대비 | 1% 추가 |

---

## 5. Implementation Order

| Step | 파일 | 작업 | 의존성 |
|------|------|------|--------|
| 1 | `models.py` | `TitleKeywordResult` 모델 추가 | 없음 |
| 2 | `gemini.py` | `extract_title_keywords()` 메서드 추가 | Step 1 |
| 3 | `market_analyzer.py` | `analyze_title_keywords()` 시그니처 확장 + fallback 분리 | Step 1 |
| 4 | `market_analyzer.py` | `build_market_analysis()` / `build_keyword_market_analysis()` 파라미터 추가 | Step 3 |
| 5 | `orchestrator.py` | 3곳에 `extract_title_keywords` 호출 삽입 | Step 2, 4 |

---

## 6. Testing Strategy

### 6.1 단위 검증

- `extract_title_keywords()`: 실제 카테고리 데이터로 호출, JSON 파싱 + Pydantic 검증
- `analyze_title_keywords()`: 동적 키워드 전달 시 출력 포맷 호환성 확인
- `analyze_title_keywords()`: `title_keywords=None` 시 기존 하드코딩 동작 확인

### 6.2 E2E 검증

- 스킨케어 카테고리: 기존 하드코딩과 유사한 키워드가 추출되는지 확인
- 식품 카테고리: "Non-GMO", "Keto", "Probiotic" 등 카테고리 고유 키워드 확인
- 전자제품 카테고리: "Wireless", "Bluetooth", "Rechargeable" 등 확인

### 6.3 Fallback 검증

- Gemini API 실패 시 하드코딩 fallback 동작 확인
- title이 10개 미만인 경우 fallback 동작 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial design | Design Phase |
