# customer-voice-dynamic-keywords Design Document

> **Summary**: Gemini Flash 1회 호출로 카테고리 맞춤 consumer voice 키워드를 동적 추출하고, 기존 BSR 상관관계 분석 파이프라인에 주입
>
> **Project**: webhook-service (amz_researcher)
> **Author**: Design Phase
> **Date**: 2026-03-11
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/customer-voice-dynamic-keywords.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 하드코딩 30개 키워드가 카테고리 무관 동일 적용 → 헤어 "frizz", 선케어 "white cast" 등 미탐지 |
| **Solution** | Gemini Flash에 전체 customer_says를 1회 전달, 카테고리 맞춤 키워드 + ASIN 매핑을 JSON으로 반환 |
| **Function/UX Effect** | 리포트의 Consumer Voice 섹션이 카테고리별 실제 소비자 언어를 반영 |
| **Core Value** | Flash 1회 $0.002로 모든 카테고리에서 정확한 소비자 인사이트 제공 |

---

## 1. Architecture Overview

### 1.1 데이터 흐름

```
orchestrator.py (async)
  │
  │  [기존] gemini.extract_ingredients()
  │  [기존] calculate_weights() → weighted_products
  │
  │  ┌─ [신규] Gemini 키워드 추출 ─────────────────────────┐
  │  │                                                       │
  │  │  gemini.extract_voice_keywords(                       │
  │  │    category_name,                                     │
  │  │    [{asin, customer_says}, ...]                       │
  │  │  )                                                    │
  │  │  → VoiceKeywordResult                                 │
  │  │    { positive: [{keyword, asins}],                    │
  │  │      negative: [{keyword, asins}] }                   │
  │  └───────────────────────────────────────────────────────┘
  │
  │  build_market_analysis(..., voice_keywords=result)
  │    └─ analyze_customer_voice(products, voice_keywords)
  │         ├─ voice_keywords 있으면 → 동적 키워드 기반 매칭
  │         └─ voice_keywords 없으면 → 기존 하드코딩 fallback
  │
  │  [기존] gemini.generate_market_report(analysis_data)
```

### 1.2 변경 범위

| 파일 | 변경 내용 | 영향도 |
|------|----------|--------|
| `models.py` | `VoiceKeyword`, `VoiceKeywordResult` Pydantic 모델 추가 | Low (추가만) |
| `gemini.py` | `extract_voice_keywords()` 메서드 추가 | Low (추가만) |
| `market_analyzer.py` | `analyze_customer_voice()` 시그니처 확장 + 동적 매칭 로직 | Medium |
| `market_analyzer.py` | `build_market_analysis()`, `build_keyword_market_analysis()` 파라미터 추가 | Low |
| `orchestrator.py` | 3곳에 Gemini 키워드 호출 삽입 | Medium |

---

## 2. Detailed Design

### 2.1 Pydantic 모델 (`models.py`)

```python
class VoiceKeyword(BaseModel):
    keyword: str
    asins: list[str] = []

class VoiceKeywordResult(BaseModel):
    positive_keywords: list[VoiceKeyword] = []
    negative_keywords: list[VoiceKeyword] = []
```

### 2.2 Gemini 프롬프트 (`gemini.py`)

#### 프롬프트 템플릿

```python
VOICE_KEYWORD_PROMPT = """아래는 아마존 "{category_name}" 카테고리 제품들의 소비자 리뷰 요약(customer_says)이다.

{customer_says_block}

위 리뷰 요약에서 이 카테고리에서 반복적으로 언급되는 핵심 키워드를 추출하라.

규칙:
1. 이 카테고리에 특화된 키워드만 추출 (generic한 "good", "bad", "nice", "love" 등 제외)
2. 각 키워드는 원문에서 실제 사용된 표현 기반으로, 1-3 단어로 간결하게
3. 긍정 키워드: 소비자가 칭찬하는 속성 (효과, 질감, 향 등)
4. 부정 키워드: 소비자가 불만을 표현하는 속성 (자극, 질감, 부작용 등)
5. 각 키워드별로 해당 키워드가 언급된 ASIN 목록을 포함
6. 긍정 10-15개, 부정 10-15개 범위로 추출
7. 2개 이상의 제품에서 언급된 키워드만 포함

JSON 출력:
{{
  "positive_keywords": [
    {{"keyword": "moisturizing", "asins": ["B0XXXX", "B0YYYY"]}},
    ...
  ],
  "negative_keywords": [
    {{"keyword": "sticky", "asins": ["B0ZZZZ"]}},
    ...
  ]
}}"""
```

#### customer_says_block 포맷

```
[B0XXXX] Customers like the moisturizing effect and lightweight texture...
[B0YYYY] Customers appreciate the gentle formula. Some mention strong smell...
```

- ASIN을 prefix로 붙여 Gemini가 ASIN 매핑을 정확히 할 수 있도록 함
- `customer_says`가 빈 제품은 제외

### 2.3 GeminiService 메서드 (`gemini.py`)

```python
async def extract_voice_keywords(
    self,
    category_name: str,
    products: list[WeightedProduct],
) -> VoiceKeywordResult | None:
    """customer_says에서 카테고리 맞춤 긍정/부정 키워드 동적 추출.

    Returns None on failure (caller falls back to hardcoded keywords).
    """
```

**설계 결정:**
- **모델**: Flash (self.url) — 키워드 추출은 경량 작업
- **temperature**: 0.1 — 일관성 (extract_ingredients와 동일)
- **responseMimeType**: `"application/json"` — structured output 강제
- **maxOutputTokens**: 4096 — 키워드 JSON은 ~1K 토큰이면 충분, 여유 확보
- **timeout**: 30초 — 기본 클라이언트 timeout 내
- **재시도**: 1회 (max_retries=1)
- **최소 제품 수**: customer_says가 있는 제품이 10개 미만이면 None 반환 → fallback

**에러 핸들링:**
1. API 호출 실패 → `logger.warning` + return None
2. JSON 파싱 실패 → `_try_repair_json` 시도 후 실패 시 return None
3. Pydantic validation 실패 → return None
4. 모든 실패 케이스에서 caller가 기존 하드코딩 키워드로 fallback

### 2.4 analyze_customer_voice 리팩토링 (`market_analyzer.py`)

#### 시그니처 변경

```python
# Before
def analyze_customer_voice(products: list[WeightedProduct]) -> dict:

# After
def analyze_customer_voice(
    products: list[WeightedProduct],
    voice_keywords: VoiceKeywordResult | None = None,
) -> dict:
```

#### 동적 키워드 매칭 로직

```python
def analyze_customer_voice(
    products: list[WeightedProduct],
    voice_keywords: VoiceKeywordResult | None = None,
) -> dict:
    with_cs = [p for p in products if p.customer_says]
    if not with_cs:
        return {}

    product_map = {p.asin: p for p in with_cs}

    if voice_keywords:
        # 동적 키워드: Gemini가 반환한 ASIN 매핑 사용
        pos_counts = {}
        for vk in voice_keywords.positive_keywords:
            matched = [product_map[a] for a in vk.asins if a in product_map]
            if matched:
                pos_counts[vk.keyword] = matched

        neg_counts = {}
        for vk in voice_keywords.negative_keywords:
            matched = [product_map[a] for a in vk.asins if a in product_map]
            if matched:
                neg_counts[vk.keyword] = matched
    else:
        # Fallback: 기존 하드코딩 키워드
        pos_counts, neg_counts = _hardcoded_keyword_match(with_cs)

    # 이하 BSR 상관관계 분석 로직은 동일 (기존 코드 재사용)
    ...
```

#### 하드코딩 fallback 분리

```python
def _hardcoded_keyword_match(
    products: list[WeightedProduct],
) -> tuple[dict, dict]:
    """기존 하드코딩 키워드 매칭. fallback용."""
    POSITIVE_KEYWORDS = [
        "effective", "moisturizing", "gentle", "lightweight", ...
    ]
    NEGATIVE_KEYWORDS = [
        "sticky", "strong smell", "irritation", "greasy", ...
    ]
    pos_counts = {kw: [] for kw in POSITIVE_KEYWORDS}
    neg_counts = {kw: [] for kw in NEGATIVE_KEYWORDS}
    for p in products:
        text = p.customer_says.lower()
        for kw in POSITIVE_KEYWORDS:
            if kw in text:
                pos_counts[kw].append(p)
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                neg_counts[kw].append(p)
    # 빈 키워드 제거
    pos_counts = {k: v for k, v in pos_counts.items() if v}
    neg_counts = {k: v for k, v in neg_counts.items() if v}
    return pos_counts, neg_counts
```

#### 출력 포맷 (호환성 유지)

반환 dict 구조는 기존과 **완전히 동일**:

```python
{
    "total_with_customer_says": int,
    "positive_keywords": {
        "keyword_name": {"count": int, "avg_bsr": int|None, "avg_rating": float},
        ...
    },
    "negative_keywords": { ... },
    "bsr_top_half_positive": {"keyword": count, ...},
    "bsr_top_half_negative": { ... },
    "bsr_bottom_half_positive": { ... },
    "bsr_bottom_half_negative": { ... },
}
```

Excel builder, HTML report builder, Gemini 리포트 프롬프트 모두 변경 불필요.

### 2.5 build_market_analysis 파라미터 추가 (`market_analyzer.py`)

```python
# Before
def build_market_analysis(keyword, weighted_products, details) -> dict:
def build_keyword_market_analysis(keyword, weighted_products, details) -> dict:

# After
def build_market_analysis(keyword, weighted_products, details, voice_keywords=None) -> dict:
def build_keyword_market_analysis(keyword, weighted_products, details, voice_keywords=None) -> dict:
```

내부에서 `analyze_customer_voice(weighted_products, voice_keywords)` 호출.
기존 호출부에서 `voice_keywords`를 전달하지 않으면 None → 기존 동작 그대로.

### 2.6 orchestrator.py 연동 (3곳)

#### 패턴 (3곳 모두 동일)

```python
# 기존: build_market_analysis 직전에 추가
# weighted_products가 준비된 후, build_market_analysis 호출 전

voice_keywords = await gemini.extract_voice_keywords(
    category_name,  # 또는 keyword/normalized_keyword
    weighted_products,
)

analysis_data = build_market_analysis(
    keyword, weighted_products, all_details,
    voice_keywords=voice_keywords,
)
```

#### 수정 위치

| 함수 | 라인 | keyword 파라미터 |
|------|------|-----------------|
| `run_analysis()` | L400 직전 | `keyword` |
| `run_category_analysis()` | L727 직전 | `category_name` |
| `run_keyword_search_analysis()` | L1079 직전 | `normalized_keyword` |

---

## 3. Error Handling & Fallback

### 3.1 Fallback 체인

```
Gemini 호출 성공 → VoiceKeywordResult → 동적 키워드 분석
        ↓ 실패
Gemini 재시도 1회
        ↓ 실패
return None → analyze_customer_voice의 voice_keywords=None
        ↓
기존 하드코딩 30개 키워드 매칭 (_hardcoded_keyword_match)
```

### 3.2 실패 조건별 처리

| 조건 | 처리 |
|------|------|
| customer_says 있는 제품 < 10개 | Gemini 호출 스킵, 하드코딩 fallback |
| API 호출 실패 (네트워크/타임아웃) | 1회 재시도 후 None 반환 |
| JSON 파싱 실패 | `_try_repair_json` 시도 → 실패 시 None |
| Pydantic validation 실패 | None 반환 |
| ASIN 매핑 불일치 | `product_map`에 없는 ASIN 무시 (silent skip) |

---

## 4. Cost Analysis

| 항목 | 값 |
|------|-----|
| 모델 | gemini-2.5-flash |
| Input tokens (100개 제품) | ~8,500 |
| Output tokens (키워드 JSON) | ~1,000 |
| 1회 호출 비용 | ~$0.002 |
| 월간 추가 비용 (300건) | ~$0.60 |
| 기존 Pro 리포트 대비 | 2% 추가 |

---

## 5. Implementation Order

| Step | 파일 | 작업 | 의존성 |
|------|------|------|--------|
| 1 | `models.py` | `VoiceKeyword`, `VoiceKeywordResult` 모델 추가 | 없음 |
| 2 | `gemini.py` | `VOICE_KEYWORD_PROMPT` + `extract_voice_keywords()` 메서드 | Step 1 |
| 3 | `market_analyzer.py` | `_hardcoded_keyword_match()` 분리 + `analyze_customer_voice()` 리팩토링 | Step 1 |
| 4 | `market_analyzer.py` | `build_market_analysis()` / `build_keyword_market_analysis()` 파라미터 추가 | Step 3 |
| 5 | `orchestrator.py` | 3곳에 `extract_voice_keywords` 호출 삽입 | Step 2, 4 |
| 6 | 검증 | 실제 카테고리 데이터로 E2E 테스트 | Step 5 |

---

## 6. Testing Strategy

### 6.1 단위 검증

- `extract_voice_keywords()`: 실제 카테고리 데이터로 호출, JSON 파싱 + Pydantic 검증
- `analyze_customer_voice()`: 동적 키워드 전달 시 출력 포맷 호환성 확인
- `analyze_customer_voice()`: `voice_keywords=None` 시 기존 하드코딩 동작 확인

### 6.2 E2E 검증

- 스킨케어 카테고리: 기존 하드코딩과 유사한 키워드가 추출되는지 확인
- 헤어케어 카테고리: "frizz", "tangling", "shine" 등 카테고리 고유 키워드 추출 확인
- 선케어 카테고리: "white cast", "SPF", "reapply" 등 확인

### 6.3 Fallback 검증

- Gemini API 키 무효화 시 하드코딩 fallback 동작 확인
- customer_says가 10개 미만인 경우 fallback 동작 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial design | Design Phase |
