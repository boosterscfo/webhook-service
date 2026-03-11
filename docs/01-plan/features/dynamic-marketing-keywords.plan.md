# dynamic-marketing-keywords Planning Document

> **Summary**: `analyze_title_keywords()`의 하드코딩된 22개 마케팅 키워드를 Gemini Flash 기반 동적 추출로 전환하여 카테고리별 맞춤 제품 타이틀 키워드 분석 제공
>
> **Project**: webhook-service (amz_researcher)
> **Author**: CTO
> **Date**: 2026-03-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 22개 마케팅 키워드가 스킨케어 전용으로 하드코딩되어 모든 카테고리에 동일 적용. 식품의 "Gluten-Free", "Non-GMO", 전자제품의 "Bluetooth", "Wireless" 등 카테고리 고유 키워드를 놓침 |
| **Solution** | Gemini Flash에 제품 title 텍스트를 1회 전달하여 카테고리 맞춤 마케팅 키워드를 동적 추출한 뒤, 기존 BSR/판매량 비교 분석 로직은 그대로 유지 |
| **Function/UX Effect** | 카테고리별 실제 마케팅 트렌드를 반영한 키워드가 리포트에 표시되어 경쟁 분석 정확도 향상 |
| **Core Value** | 하드코딩 유지보수 제거 + 카테고리 무관 범용 분석 품질 확보 (Flash 1회 호출로 비용 $0.002 이하) |

---

## 1. Overview

### 1.1 Purpose

`analyze_title_keywords()` 함수의 키워드 매칭을 하드코딩 사전에서 Gemini AI 동적 추출로 전환한다. 카테고리에 따라 적합한 마케팅 키워드가 자동으로 추출되어, 모든 카테고리에서 의미 있는 제목 키워드 분석을 제공한다.

### 1.2 Background

**현재 문제점:**

1. **카테고리 불일치**: `MARKETING_KEYWORDS`가 스킨케어/뷰티 중심으로 하드코딩됨
   - 식품: "Non-GMO", "Gluten-Free", "Keto", "Probiotic" 등 미탐지
   - 전자제품: "Wireless", "Bluetooth", "Rechargeable", "Waterproof" 등 미탐지
   - 헤어케어: "Biotin", "Keratin", "Color-Safe", "Heat Protection" 등 미탐지

2. **단순 문자열 매칭**: `if kw.lower() in title_lower` 방식으로 부분 매칭
   - "Organic" 검색 시 "Organically" 도 매칭
   - 카테고리 무관하게 "SPF"가 식품 타이틀에서도 검색

3. **확장 불가**: 새 카테고리 추가 시마다 키워드 사전 수동 업데이트 필요

**기존 customer-voice-dynamic-keywords와의 관계:**
- customer_voice는 리뷰 요약(customer_says)에서 감성 키워드 추출
- title_keywords는 제품 제목(title)에서 마케팅 키워드 추출
- 동일한 Gemini Flash 1회 호출 패턴 적용 가능

### 1.3 Related Documents

- 기존 구현: `amz_researcher/services/market_analyzer.py` L774-819
- 참고 패턴: `docs/01-plan/features/customer-voice-dynamic-keywords.plan.md`
- 참고 디자인: `docs/02-design/features/customer-voice-dynamic-keywords.design.md`
- Gemini 서비스: `amz_researcher/services/gemini.py`
- 모델: `amz_researcher/models.py` (`WeightedProduct.title`)

---

## 2. Scope

### 2.1 In Scope

- [ ] Gemini Flash를 활용한 카테고리별 동적 마케팅 키워드 추출 메서드 구현
- [ ] `analyze_title_keywords()` 함수를 동적 키워드 기반으로 리팩토링
- [ ] 기존 BSR/판매량 비교 분석 로직 유지 (출력 포맷 호환)
- [ ] `build_market_analysis()` / `build_keyword_market_analysis()` 호출부 연동
- [ ] 에러 발생 시 기존 하드코딩 키워드로 fallback
- [ ] orchestrator.py에서 voice_keywords와 동일한 선호출 패턴 적용

### 2.2 Out of Scope

- 키워드별 ASIN 매핑: title_keywords는 title 텍스트 매칭이므로 ASIN 매핑은 코드에서 수행
- 리포트 프롬프트(`MARKET_REPORT_PROMPT`) 변경: 현재 title_keywords JSON 포맷으로 충분
- customer_voice 동적 키워드와의 통합: 각각 독립적 추출 유지 (관심사 분리)
- DB 캐싱: title_keywords는 카테고리 맞춤 키워드 리스트만 필요, 제품별 캐싱 불필요

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 카테고리명 + 제품 title 텍스트를 입력으로 Gemini가 마케팅 키워드 15-25개를 추출 | High | Pending |
| FR-02 | 추출된 키워드로 기존 BSR/판매량 비교 분석 수행 (출력 포맷 동일) | High | Pending |
| FR-03 | Gemini 호출 실패 시 기존 하드코딩 22개 키워드로 fallback | High | Pending |
| FR-04 | orchestrator에서 선호출 후 build_market_analysis에 파라미터 전달 | High | Pending |
| FR-05 | 키워드는 1-3 단어의 마케팅 클레임/성분/특성 형태 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | Gemini 호출 1회, 응답 시간 10초 이내 | 로그 타임스탬프 |
| Cost | 100개 제품 기준 $0.002 이하 (Flash 사용) | API 사용량 모니터링 |
| Reliability | Gemini 실패 시 fallback으로 기존 결과 보장 | 에러 로그 + 결과 확인 |
| Compatibility | 기존 `title_keywords` JSON 출력 포맷 유지 | 리포트 생성 검증 |

---

## 4. Technical Approach

### 4.1 처리 전략: customer-voice 패턴 재사용

customer-voice-dynamic-keywords에서 검증된 패턴을 그대로 적용:

1. **orchestrator에서 선호출**: Gemini Flash로 카테고리 맞춤 키워드 리스트 추출
2. **파라미터 전달**: `build_market_analysis(..., title_keywords=result)`
3. **analyze_title_keywords()에서 사용**: `title_keywords` 파라미터가 있으면 동적 키워드, 없으면 하드코딩 fallback

**차이점 (voice vs title):**

| 항목 | customer_voice | title_keywords |
|------|---------------|----------------|
| 입력 데이터 | customer_says (리뷰 요약) | title (제품 제목) |
| 키워드 유형 | 감성 키워드 (긍정/부정) | 마케팅 키워드 (단일 리스트) |
| ASIN 매핑 | Gemini가 반환 | 코드에서 title 매칭으로 수행 |
| Pydantic 모델 | VoiceKeywordResult (positive/negative) | TitleKeywordResult (keywords 리스트) |
| 캐싱 | DB에 제품별 캐싱 | 불필요 (키워드 리스트만) |

### 4.2 프롬프트 설계

```
카테고리: "{category_name}"

아래는 이 카테고리의 아마존 제품 {n}개의 제목(title)이다.

[B0XXXX] CeraVe Moisturizing Cream | Organic Hyaluronic Acid ...
[B0YYYY] Neutrogena Hydro Boost | Fragrance-Free ...
...

이 카테고리의 제품 제목에서 반복적으로 사용되는 핵심 마케팅 키워드를 추출하라.

규칙:
1. 이 카테고리에 특화된 마케팅 키워드만 추출
2. 성분명 (Hyaluronic Acid, Retinol 등), 인증/클레임 (Organic, Vegan 등),
   제품 특성 (Fragrance-Free, Waterproof 등) 포함
3. 브랜드명은 제외
4. 각 키워드는 1-3 단어로 간결하게
5. 15-25개 범위로 추출
6. 3개 이상의 제품에서 사용된 키워드만 포함

JSON 출력:
{
  "keywords": ["Organic", "Hyaluronic Acid", "Fragrance-Free", ...]
}
```

### 4.3 아키텍처: GeminiService에 메서드 추가

```python
# gemini.py에 추가
async def extract_title_keywords(
    self,
    category_name: str,
    products: list[WeightedProduct],
) -> TitleKeywordResult | None:
    """title에서 카테고리 맞춤 마케팅 키워드 동적 추출."""
```

### 4.4 analyze_title_keywords 리팩토링

```
현재 (동기):
  analyze_title_keywords(products) -> dict
    - 하드코딩 22개 키워드 매칭
    - BSR/판매량 비교

변경 후 (동기):
  analyze_title_keywords(products, title_keywords) -> dict
    - title_keywords: Gemini가 반환한 키워드 리스트
    - 동일한 BSR/판매량 비교 로직 유지
    - title_keywords가 None이면 기존 하드코딩 fallback
```

---

## 5. Success Criteria

### 5.1 Definition of Done

- [ ] Pydantic 모델 `TitleKeywordResult` 구현
- [ ] GeminiService에 `extract_title_keywords()` 메서드 구현
- [ ] `analyze_title_keywords()`가 동적 키워드로 분석 수행
- [ ] Gemini 실패 시 기존 하드코딩 키워드 fallback 동작 확인
- [ ] 기존 리포트 출력 포맷 호환 (`title_keywords` JSON 구조 동일)
- [ ] orchestrator.py 3곳 연동 완료

### 5.2 Quality Criteria

- [ ] Flash 1회 호출 비용 $0.002 이하 (100개 제품 기준)
- [ ] 응답 시간 기존 대비 5초 이내 추가
- [ ] 기존 분석 파이프라인 정상 동작

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Gemini API 응답 실패/타임아웃 | High | Low | 하드코딩 키워드 fallback + 재시도 1회 |
| JSON 파싱 실패 | Medium | Low | `responseMimeType: "application/json"` + Pydantic validation |
| 키워드 품질 저하 (generic 키워드) | Medium | Medium | 프롬프트에 카테고리 특화 지시 + "3개 이상 제품" 필터 |
| 브랜드명이 키워드에 포함 | Low | Medium | 프롬프트에 "브랜드명 제외" 명시 |
| title이 없는 제품 | Low | Low | title이 빈 제품은 제외 |

---

## 7. Architecture Considerations

### 7.1 Project Level

이 프로젝트는 **Dynamic** 레벨에 해당 (FastAPI + 도메인별 서비스 + lib 공유).

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| AI 모델 | Flash / Pro | Flash | 키워드 추출은 경량 작업, Pro 대비 8x 저렴 |
| 호출 방식 | 1회 전체 / 배치 | 1회 전체 | 100개 제품 title = ~5K 토큰, Flash 컨텍스트 1% 미만 |
| 코드 위치 | GeminiService 메서드 / 별도 서비스 | GeminiService 메서드 | customer_voice와 동일 패턴 |
| Gemini 호출 시점 | orchestrator / build_market_analysis 내부 | orchestrator | 동기 함수 시그니처 유지, customer_voice와 동일 패턴 |
| fallback | 하드코딩 키워드 / 빈 결과 | 하드코딩 키워드 | 무장애 분석 보장 |
| 캐싱 | DB 캐싱 / 없음 | 없음 | title_keywords는 단순 리스트, voice처럼 제품별 캐싱 불필요 |

### 7.3 데이터 흐름

```
orchestrator.py (async)
  |
  |  [기존] gemini.extract_voice_keywords(category, products)
  |
  |  [신규] gemini.extract_title_keywords(category, products)
  |    -> TitleKeywordResult { keywords: ["Organic", "Vegan", ...] }
  |
  |  build_market_analysis(..., voice_keywords=..., title_keywords=...)
  |    -> analyze_title_keywords(products, title_keywords)
  |         |-- title_keywords 있으면: 동적 키워드 기반 매칭
  |         |-- title_keywords 없으면: 기존 하드코딩 fallback
  |
  |  [기존] gemini.generate_market_report(analysis_data)
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
| 프롬프트 (지시문) | ~300 tokens | - |
| title (100개) | ~3,000-5,000 tokens | - |
| **총 Input** | **~5,000 tokens** | **$0.0008** |
| **총 Output** (키워드 JSON) | **~200 tokens** | **$0.0001** |
| **1회 호출 총 비용** | | **$0.0009** |

기존 파이프라인에서 이미 Gemini Pro 리포트 생성 + voice keywords Flash 호출을 수행하므로, Flash 1회 추가는 무시할 수 있는 수준.

---

## 9. Implementation Plan

### Phase 1: Pydantic 모델 + Gemini 메서드 (0.5일)

1. `models.py`에 `TitleKeywordResult` 모델 추가
2. `gemini.py`에 `extract_title_keywords()` 메서드 추가
3. 프롬프트 작성 + `responseMimeType: "application/json"` 적용

### Phase 2: analyze_title_keywords 리팩토링 (0.5일)

1. `analyze_title_keywords()` 시그니처에 `title_keywords` 파라미터 추가
2. 동적 키워드 기반 매칭 로직 구현
3. fallback 로직 (title_keywords=None 시 기존 하드코딩)

### Phase 3: orchestrator + build 함수 연동 (0.5일)

1. `build_market_analysis()`, `build_keyword_market_analysis()`에 `title_keywords` 파라미터 추가
2. orchestrator.py 3곳에 Gemini 키워드 호출 삽입

### Phase 4: 검증 (0.5일)

1. 스킨케어 카테고리로 기존 결과 대비 검증
2. 비스킨케어 카테고리에서 동적 키워드 품질 확인
3. Gemini 실패 시 fallback 동작 확인

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`dynamic-marketing-keywords.design.md`)
2. [ ] 구현 시작
3. [ ] Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial draft | CTO |
