# customer-voice-dynamic-keywords Planning Document

> **Summary**: 하드코딩된 30개 키워드 사전을 Gemini AI 기반 동적 키워드 추출로 전환하여 카테고리별 맞춤 소비자 리뷰 분석 제공
>
> **Project**: webhook-service (amz_researcher)
> **Author**: CTO
> **Date**: 2026-03-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 15개 긍정/15개 부정 키워드가 하드코딩되어 모든 카테고리에 동일 적용. 헤어 제품의 "frizz", "tangling" 등 카테고리 고유 키워드를 놓치고, 단순 `in` 매칭으로 문맥을 무시함 |
| **Solution** | Gemini Flash에 전체 customer_says 텍스트를 한 번에 전달하여 카테고리 맞춤 긍정/부정 키워드를 동적 추출한 뒤, 기존 BSR 상관관계 분석 로직은 그대로 유지 |
| **Function/UX Effect** | 카테고리별 실제 소비자 언어를 반영한 키워드가 리포트에 표시되어 시장 인사이트 정확도 향상 |
| **Core Value** | 하드코딩 유지보수 제거 + 카테고리 무관 범용 분석 품질 확보 (Flash 1회 호출로 비용 $0.01 이하) |

---

## 1. Overview

### 1.1 Purpose

`analyze_customer_voice()` 함수의 키워드 매칭을 하드코딩 사전에서 Gemini AI 동적 추출로 전환한다. 카테고리에 따라 적합한 키워드가 자동으로 추출되어, 모든 카테고리에서 의미 있는 소비자 리뷰 분석을 제공한다.

### 1.2 Background

**현재 문제점:**

1. **카테고리 불일치**: `POSITIVE_KEYWORDS`와 `NEGATIVE_KEYWORDS`가 스킨케어 중심으로 하드코딩됨
   - 헤어 제품: "frizz", "tangling", "split ends", "shine" 등 미탐지
   - 선케어: "white cast", "reapply", "sweat-proof" 등 미탐지
   - 바디케어: "absorption", "fragrance lasting", "dry skin" 등 미탐지

2. **단순 문자열 매칭**: `if kw in text` 방식으로 문맥 무시
   - "no irritation"과 "irritation" 둘 다 긍정으로 잡힘 (부분 매칭)
   - "not greasy at all"이 "greasy"로 부정 분류

3. **확장 불가**: 새 카테고리 추가 시마다 키워드 사전 수동 업데이트 필요

**customer_says 데이터 특성:**
- Amazon이 리뷰를 요약하여 제공하는 짧은 텍스트 (보통 100-300자)
- 제품당 1개. 100개 제품 기준 총 10K-30K 문자
- 예: "Customers like the moisturizing effect and lightweight texture. Some mention it feels sticky after application."

### 1.3 Related Documents

- 기존 구현: `amz_researcher/services/market_analyzer.py` L556-625
- Gemini 서비스: `amz_researcher/services/gemini.py`
- 모델: `amz_researcher/models.py` (`WeightedProduct.customer_says`)

---

## 2. Scope

### 2.1 In Scope

- [ ] Gemini Flash를 활용한 카테고리별 동적 키워드 추출 메서드 구현
- [ ] `analyze_customer_voice()` 함수를 동적 키워드 기반으로 리팩토링 (async 전환)
- [ ] 기존 BSR 상관관계 분석 로직 유지 (출력 포맷 호환)
- [ ] `build_market_analysis()` / `build_keyword_market_analysis()` 호출부 async 연동
- [ ] 에러 발생 시 기존 하드코딩 키워드로 fallback

### 2.2 Out of Scope

- Gemini Batch API (24시간 비동기) 사용: 실시간 분석 파이프라인과 부적합
- customer_says 텍스트 자체의 감성 분석 (AI가 각 리뷰 전체를 평가): 비용 과다
- 리포트 프롬프트(`MARKET_REPORT_PROMPT`) 변경: 현재 customer_voice JSON 포맷으로 충분
- title_keywords 분석의 동적 키워드 전환: 별도 피처로 진행

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 카테고리명 + customer_says 텍스트를 입력으로 Gemini가 긍정/부정 키워드를 추출 | High | Pending |
| FR-02 | 추출된 키워드로 기존 BSR 상관관계/빈도 분석 수행 (출력 포맷 동일) | High | Pending |
| FR-03 | Gemini 호출 실패 시 기존 하드코딩 키워드로 fallback | High | Pending |
| FR-04 | 키워드는 긍정 10-15개, 부정 10-15개 범위로 추출 | Medium | Pending |
| FR-05 | 각 키워드에 confidence score 또는 출현 빈도 포함 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | Gemini 호출 1회, 응답 시간 10초 이내 | 로그 타임스탬프 |
| Cost | 100개 제품 기준 $0.01 이하 (Flash 사용) | API 사용량 모니터링 |
| Reliability | Gemini 실패 시 fallback으로 기존 결과 보장 | 에러 로그 + 결과 확인 |
| Compatibility | 기존 `customer_voice` JSON 출력 포맷 유지 | 리포트 생성 검증 |

---

## 4. Technical Approach

### 4.1 처리 전략 비교

| 방식 | 설명 | 토큰 사용 | 비용(100제품) | 장점 | 단점 |
|------|------|-----------|-------------|------|------|
| **A. 전체 1회 호출** | 모든 customer_says를 하나의 프롬프트로 | ~8K in, ~1K out | ~$0.002 | 최소 비용, 컨텍스트 공유 | 프롬프트 크기 제한 가능성 |
| B. 배치 호출 (20개씩) | 20개 제품씩 나눠서 5회 호출 | ~10K in, ~3K out | ~$0.003 | 안정적 | 키워드 중복/불일치 |
| C. 개별 호출 | 제품별 1회씩 100회 호출 | ~50K in, ~10K out | ~$0.01 | 정밀 | 비용/시간 비효율 |
| D. 2단계 (샘플 + 매칭) | 대표 20개로 키워드 추출 후 전체 적용 | ~3K in, ~1K out | ~$0.001 | 초저비용 | 대표성 리스크 |

**선정: A안 (전체 1회 호출)**

근거:
- customer_says는 제품당 100-300자. 100개 기준 총 10K-30K 문자 = ~5K-10K 토큰
- Gemini Flash 컨텍스트 윈도우 1M 토큰 대비 1% 미만
- 전체 텍스트를 한 번에 보내면 카테고리 전체 패턴을 파악하여 더 정확한 키워드 추출
- Flash 가격 $0.15/1M input + $0.60/1M output = 1회 호출 $0.002 이하

### 4.2 프롬프트 설계

```
카테고리: "{category_name}"

아래는 이 카테고리의 아마존 제품 100개에 대한 소비자 리뷰 요약(customer_says)이다.

[ASIN_1] Customers like the moisturizing effect...
[ASIN_2] Customers appreciate the lightweight formula...
...

이 카테고리의 소비자 리뷰에서 반복적으로 언급되는 핵심 키워드를 추출하라.

규칙:
1. 이 카테고리에 특화된 키워드만 추출 (generic한 "good", "bad" 등 제외)
2. 각 키워드는 원문에서 실제 사용된 표현 기반
3. 긍정/부정 분류는 해당 키워드가 리뷰에서 긍정적 맥락인지 부정적 맥락인지로 판단
4. 각 키워드별로 해당 키워드가 언급된 ASIN 목록을 포함

JSON 출력:
{
  "positive_keywords": [
    {"keyword": "moisturizing", "asins": ["B0XXXX", "B0YYYY"]},
    ...
  ],
  "negative_keywords": [
    {"keyword": "sticky", "asins": ["B0ZZZZ"]},
    ...
  ]
}
```

**핵심 설계 포인트:**
- ASIN을 키와 함께 반환받아 후처리에서 BSR/Rating 매칭 가능 (기존 로직 재사용)
- `responseMimeType: "application/json"` 사용하여 structured output 강제
- temperature 0.1로 일관성 확보 (기존 `extract_ingredients`와 동일)

### 4.3 아키텍처: 기존 GeminiService에 메서드 추가

```python
# gemini.py에 추가
async def extract_customer_voice_keywords(
    self,
    category_name: str,
    products: list[dict],  # [{"asin": str, "customer_says": str}]
) -> dict:
    """customer_says에서 카테고리 맞춤 긍정/부정 키워드 추출."""
```

**별도 클래스 불필요한 이유:**
- 기존 `GeminiService`가 Flash/Pro 분리, httpx 클라이언트 관리, 에러 핸들링을 이미 갖춤
- `extract_ingredients()`와 동일한 패턴 (products 입력 -> structured JSON 출력)
- 새 메서드 하나로 충분

### 4.4 analyze_customer_voice 리팩토링

```
현재 (동기):
  analyze_customer_voice(products) -> dict
    - 하드코딩 키워드 매칭
    - BSR 상관관계 계산

변경 후 (비동기):
  analyze_customer_voice(products, keyword_data) -> dict
    - keyword_data: Gemini가 반환한 {keyword -> [asin]} 매핑
    - 동일한 BSR 상관관계 계산 로직 유지
    - keyword_data가 None이면 기존 하드코딩 fallback
```

**호출부 변경:**

`build_market_analysis()` / `build_keyword_market_analysis()` 에서:
1. Gemini 키워드 추출을 먼저 수행 (기존 리포트 생성 전)
2. 추출 결과를 `analyze_customer_voice()`에 전달
3. orchestrator.py의 호출 순서는 변경 불필요 (build_market_analysis 내부에서 처리)

단, `build_market_analysis` 자체가 동기 함수이므로, 두 가지 선택지가 있다:

| 방식 | 설명 | 변경 범위 |
|------|------|----------|
| **A. orchestrator에서 선호출** | orchestrator에서 Gemini 호출 후 결과를 build_market_analysis에 전달 | orchestrator 3곳 수정 |
| B. build_market_analysis를 async로 | 함수 자체를 async로 변환 | 호출부 전체 수정 필요 |

**선정: A안** - orchestrator에서 Gemini 키워드를 미리 추출하고 `build_market_analysis()`에 `voice_keywords` 파라미터로 전달. 기존 함수 시그니처에 optional 파라미터 추가만으로 하위 호환성 유지.

---

## 5. Success Criteria

### 5.1 Definition of Done

- [ ] GeminiService에 `extract_customer_voice_keywords()` 메서드 구현
- [ ] `analyze_customer_voice()`가 동적 키워드로 분석 수행
- [ ] Gemini 실패 시 기존 하드코딩 키워드 fallback 동작 확인
- [ ] 기존 리포트 출력 포맷 호환 (`customer_voice` JSON 구조 동일)
- [ ] 스킨케어 외 카테고리(헤어, 선케어 등)에서 카테고리 고유 키워드 추출 검증
- [ ] orchestrator.py 3곳(BSR 분석, 카테고리 분석, 키워드 검색 분석) 연동 완료

### 5.2 Quality Criteria

- [ ] Flash 1회 호출 비용 $0.01 이하 (100개 제품 기준)
- [ ] 응답 시간 기존 대비 10초 이내 추가
- [ ] 기존 테스트/분석 파이프라인 정상 동작

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Gemini API 응답 실패/타임아웃 | High | Low | 하드코딩 키워드 fallback + 재시도 1회 |
| JSON 파싱 실패 (키워드 포맷 불일치) | Medium | Low | `responseMimeType: "application/json"` + Pydantic validation |
| 키워드 품질 저하 (generic 키워드 추출) | Medium | Medium | 프롬프트에 카테고리 특화 지시 + few-shot 예시 |
| ASIN 매핑 오류 (Gemini가 잘못된 ASIN 반환) | Medium | Low | 반환된 ASIN을 products dict에서 검증, 미매칭 무시 |
| customer_says가 없는 제품 비율 높음 | Low | Medium | with_cs 필터링 (기존 로직) + 최소 10개 미만 시 fallback |

---

## 7. Architecture Considerations

### 7.1 Project Level

이 프로젝트는 **Dynamic** 레벨에 해당 (FastAPI + 도메인별 서비스 + lib 공유).

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| AI 모델 | Flash / Pro | Flash | 키워드 추출은 경량 작업, Pro 대비 8x 저렴 |
| 호출 방식 | 1회 전체 / 배치 / 개별 | 1회 전체 | 100개 제품 customer_says = ~8K 토큰, Flash 컨텍스트 1% 미만 |
| 코드 위치 | GeminiService 메서드 / 별도 서비스 | GeminiService 메서드 | 기존 패턴 일관성, 인프라 재사용 |
| Gemini 호출 시점 | orchestrator / build_market_analysis 내부 | orchestrator | 동기 함수 시그니처 유지, 명시적 async 흐름 |
| fallback | 하드코딩 키워드 / 빈 결과 | 하드코딩 키워드 | 무장애 분석 보장 |

### 7.3 데이터 흐름

```
orchestrator.py (async)
  │
  ├─ gemini.extract_customer_voice_keywords(category, products)
  │    └─ Flash 1회 호출 → {"positive_keywords": [...], "negative_keywords": [...]}
  │
  ├─ build_market_analysis(keyword, products, details, voice_keywords=...)
  │    └─ analyze_customer_voice(products, voice_keywords)
  │         ├─ voice_keywords 있으면: 동적 키워드 기반 매칭
  │         └─ voice_keywords 없으면: 기존 하드코딩 fallback
  │
  └─ gemini.generate_market_report(analysis_data)
       └─ customer_voice JSON 포함 (포맷 동일)
```

---

## 8. Cost Analysis

### Gemini Flash 가격 (2026.03 기준)

| 항목 | 단가 |
|------|------|
| Input | $0.15 / 1M tokens |
| Output | $0.60 / 1M tokens |

### 100개 제품 기준 추정

| 항목 | 토큰 수 | 비용 |
|------|---------|------|
| 프롬프트 (지시문) | ~500 tokens | - |
| customer_says (100개) | ~5,000-8,000 tokens | - |
| **총 Input** | **~8,500 tokens** | **$0.0013** |
| **총 Output** (키워드 JSON) | **~1,000 tokens** | **$0.0006** |
| **1회 호출 총 비용** | | **$0.0019** |

기존 파이프라인에서 이미 Gemini Pro 리포트 생성($0.05-0.10)을 수행하므로, Flash 1회 추가는 무시할 수 있는 수준.

---

## 9. Implementation Plan

### Phase 1: Gemini 키워드 추출 메서드 (1일)

1. `gemini.py`에 `extract_customer_voice_keywords()` 메서드 추가
2. 프롬프트 작성 + `responseMimeType: "application/json"` 적용
3. Pydantic 모델로 응답 검증 (`models.py`에 `VoiceKeyword`, `VoiceKeywordResponse` 추가)

### Phase 2: analyze_customer_voice 리팩토링 (1일)

1. `analyze_customer_voice()` 시그니처에 `voice_keywords` 파라미터 추가
2. 동적 키워드 기반 매칭 로직 구현
3. fallback 로직 구현 (voice_keywords=None 시 기존 하드코딩)

### Phase 3: orchestrator 연동 (0.5일)

1. `run_analysis()` (BSR 분석) 내 Gemini 키워드 호출 추가
2. `run_category_analysis()` 내 동일 처리
3. `run_keyword_search_analysis()` 내 동일 처리
4. `build_market_analysis()` / `build_keyword_market_analysis()` 에 `voice_keywords` 전달

### Phase 4: 테스트 및 검증 (0.5일)

1. 스킨케어 카테고리로 기존 결과 대비 검증
2. 헤어케어 등 비스킨케어 카테고리에서 동적 키워드 품질 확인
3. Gemini 실패 시 fallback 동작 확인

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`customer-voice-dynamic-keywords.design.md`)
2. [ ] 구현 시작
3. [ ] 실제 카테고리 데이터로 E2E 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial draft | CTO |
