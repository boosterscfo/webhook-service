# Plan: Amazon Researcher V5 — 분석 고도화 (데이터 기반 인사이트 강화)

## 1. Overview

V4에서 구축한 Bright Data 수집 인프라(874개 제품, 10개 카테고리)를 기반으로,
**수집은 되지만 분석에 활용되지 않는 데이터**를 체계적으로 분석하여 시장 인사이트 품질을 대폭 향상시킨다.

## 2. Problem Statement

### V4 현재 상태

V4는 데이터 수집 인프라는 우수하나, **분석 활용도가 수집 데이터의 ~60% 수준**:

1. **AI 리포트 데이터 누락**: `MARKET_REPORT_PROMPT`가 7개 데이터만 사용 → V4에서 추가한 `sales_volume`, `sns_pricing`, `promotions` 3개 분석이 Gemini에 전달되지 않음
2. **customer_says 미활용**: 97.8% 보유율의 Amazon AI 리뷰 요약 — 가장 가치 높은 소비자 인사이트 데이터가 Excel에 raw text로만 출력
3. **badge 분석 부재**: "Amazon's Choice" 547건(62.6%) — 배지 보유 제품의 특성 분석 없음
4. **가격 전략 분석 부족**: 할인율(initial vs final), oz당 단가(unit_price), title 마케팅 키워드 등 전환 시그널 미분석
5. **죽은 코드 존재**: `analyze_competition()`(number_of_sellers 전부 1), `plus_content` 비교(98.1% TRUE) 등 무의미한 분석 함수 잔존

### DB 실태 조사 결과 (2026-03-09)

| 필드 | 보유율 | 판정 |
|------|:------:|:----:|
| `customer_says` | 97.8% | ✅ 즉시 활용 |
| `badge` | 64.0% | ✅ 즉시 활용 |
| `unit_price` | 97.8% | ✅ 즉시 활용 |
| `initial_price` + `final_price` | 98.4% (할인 41.7%) | ✅ 즉시 활용 |
| `sns_price` | 93.5% (실할인 74.3%) | ✅ 즉시 활용 |
| `manufacturer` | 98.3% | ✅ 즉시 활용 |
| `variations_count` | 73.2% | ✅ 즉시 활용 |
| `categories` | 100% | ✅ 즉시 활용 |
| `country_of_origin` | 0% | ❌ 수집 안됨 |
| `item_weight` | 0% | ❌ 수집 안됨 |
| `number_of_sellers` | 100% = 1 | ❌ 분산 없음 |
| `plus_content` | 98.1% TRUE | ❌ 분산 없음 |
| `department` | 99.5% 동일값 | ❌ 분산 없음 |
| `product_details` 내 Skin/Hair Type | 미포함 | ❌ 메타 데이터만 |
| `amz_products_history` | 스냅샷 1개 | ❌ 시계열 불가 (4주 후) |

## 3. 변경사항 요약

### Phase 0: 죽은 코드 정리

| # | 항목 | AS-IS | TO-BE |
|---|------|-------|-------|
| 1 | `analyze_competition()` | number_of_sellers 전부 1 → 무의미한 결과 | 제거 또는 비활성화 |
| 2 | `build_market_analysis()`의 `"competition"` 키 | 빈 데이터 AI 리포트에 노이즈 | 제거 |
| 3 | `analyze_promotions()` 내 plus_content 비교 | 98.1% TRUE → 의미 없는 비교 | 해당 비교 로직 제거 |

### Phase 1: Quick Wins (AI 리포트 + 신규 분석 5건)

| # | 항목 | 변경 유형 | 데이터 근거 |
|---|------|-----------|------------|
| 1 | AI 리포트에 V4 분석 데이터 포함 | 수정 | sales_volume/sns/promotions 93%+ |
| 2 | customer_says 키워드 분석 | **신규** | 97.8% 보유, 영문 리뷰 요약 |
| 3 | badge 분석 | **신규** | 64% 보유, Amazon's Choice 547건 |
| 4 | 할인율(initial vs final) 분석 | **신규** | 할인 제품 364건(41.7%) |
| 5 | title 마케팅 키워드 분석 | **신규** | title 100% 보유 |

### Phase 2: 심화 분석 (단가/OEM/SKU/통계)

| # | 항목 | 변경 유형 | 데이터 근거 |
|---|------|-----------|------------|
| 6 | unit_price 파싱 + 단가 분석 | **신규** | 97.8%, "$0.36/ounce" 형태 |
| 7 | manufacturer(OEM) 분석 | **신규** | 98.3%, Kenvue 46건 등 |
| 8 | variations_count SKU 전략 분석 | **신규** | 73.2%, 0~11+ 분포 다양 |
| 9 | SNS 가격 심화 분석 | 수정 | 실할인 649건(74.3%) |
| 10 | 통계적 유의성 검증 | 수정 | 기존 분석 신뢰도 보강 |
| 11 | Excel 시트 확장 | 수정 | 위 분석 결과 시각화 |

### Phase 3: 데이터 축적 후 (4주+, 별도 계획)

| # | 항목 | 선행 조건 |
|---|------|-----------|
| 12 | 시계열 분석 (BSR 트렌드, 가격 변동) | 히스토리 4주+ 확보 |
| 13 | 카테고리 교차 분석 | Phase 2 완료 |
| 14 | BSR 예측 모델 | 시계열 + 피처 확보 |

## 4. 상세 설계

### 4.1 AI 리포트 V4 데이터 포함

**현상**: `gemini.py`의 `MARKET_REPORT_PROMPT`에 7개 섹션만 전달. V4에서 `build_market_analysis()`가 생성하는 `sales_volume`, `sns_pricing`, `promotions` 3개 결과가 누락.

**변경**:
- `MARKET_REPORT_PROMPT`에 3개 데이터 섹션 추가
- `generate_market_report()` 메서드에서 추가 데이터 포맷팅
- 리포트 출력 섹션도 확장 (판매량 전략, SNS/재구매 전략, 프로모션 전략)

### 4.2 customer_says 키워드 분석

**데이터**: 874건 중 855건(97.8%) 보유. 영문 리뷰 요약 텍스트.
- 샘플: "Customers find the astringent effective at cleaning skin and pores..."

**분석 방식**: Gemini 호출 없이 키워드 사전 기반 (비용 절감)
- 사전 정의 키워드:
  - Positive: "effective", "moisturizing", "gentle", "lightweight", "absorbs quickly", "hydrating", "brightening", "smooth", "refreshing", "no irritation"
  - Negative: "sticky", "strong smell", "irritation", "greasy", "breakout", "drying", "burning", "broke out", "allergic", "thin"
- BSR 상위 50% vs 하위 50%의 키워드 빈도 비교
- 각 키워드 보유 제품의 평균 BSR/평점 계산

### 4.3 badge 분석

**데이터**: 559건(64%) 보유. "Amazon's Choice" 547건, "#1 Best Seller" 6건.

**분석 항목**:
- badge 종류별 분포
- badge 보유 vs 미보유 제품의 평균 BSR, 가격, 리뷰수, 평점 비교
- badge 획득 조건 역추론 (최소 리뷰수, 최소 평점 threshold)

### 4.4 할인율 분석

**데이터**: 할인 제품 364건(41.7%), 미할인 495건, 가격 미수집 14건.

**분석 항목**:
- 할인율 구간별 (0%, 1-15%, 16-30%, 31%+) BSR/판매량 비교
- 할인 표시 유무에 따른 전환 시그널
- 할인율과 BSR/bought_past_month의 상관관계

### 4.5 title 마케팅 키워드 분석

**데이터**: title 100% 보유.

**분석 항목**:
- 사전 정의 마케팅 키워드: "Organic", "Natural", "Korean", "Vegan", "Sulfate-Free", "Dermatologist", "Clinical", "Hyaluronic", "Retinol", "Vitamin C", "Collagen", "Niacinamide", "Salicylic", "SPF", "Cruelty-Free", "Fragrance-Free"
- 각 키워드 보유 제품 수, 평균 BSR, 평균 bought_past_month
- 키워드 조합별 성과 비교

### 4.6 unit_price 파싱 + 단가 분석

**데이터**: 855건(97.8%). 형태: "$0.36 / ounce", "$5.60 / fluid ounce", "$0.58 / count"

**분석 항목**:
- 문자열 파싱: 금액 + 단위 추출
- 동일 단위 기준 단가 비교 (ounce, fluid ounce, count 등 단위별 그룹)
- 절대가격 vs 단가 중 BSR과 더 높은 상관관계를 갖는 것 식별

### 4.7 manufacturer(OEM) 분석

**데이터**: 859건(98.3%). Kenvue 46건, CeraVe 29건, DECIEM 26건, Medicube 11건 등.

**분석 항목**:
- OEM/제조사별 Top 100 진입 제품 수
- 제조사별 평균 BSR, 평균 가격, 핵심 성분 프로파일
- K-Beauty OEM 식별 (Medicube, Cosrx 등)
- 제조사 집중도 (상위 10개 제조사의 시장 점유율)

### 4.8 variations_count SKU 전략 분석

**데이터**: 0개: 234건, 1-3: 380건, 4-10: 224건, 11+: 36건.

**분석 항목**:
- SKU 수 구간별 평균 BSR, 판매량 비교
- 최적 SKU 수 추론 (BSR이 가장 좋은 구간)
- 카테고리별 SKU 전략 차이

### 4.9 SNS 심화 분석

**데이터**: 실할인 649건(74.3%), 동일가 165건, 미제공 57건.

**분석 항목** (기존 `analyze_sns_pricing()` 확장):
- SNS 할인율 구간별 BSR/판매량 비교
- SNS 채택 제품의 bought_past_month 평균 vs 미채택 (재구매 프록시)
- 가격대별 SNS 채택률 비교

### 4.10 통계적 유의성 검증

**대상**: `analyze_by_bsr()`, `analyze_rating_ingredients()`, 신규 분석 함수들

**추가 내용**:
- 그룹 간 비교에 Mann-Whitney U test (비모수 검정)
- 성분 유무에 Fisher's exact test
- p-value 부여 → 유의미하지 않은 결과 표시

### 4.11 Excel 시트 확장

**추가 시트/데이터**:
- "Consumer Voice" — customer_says 키워드 분석 결과
- "Badge Analysis" — badge 보유/미보유 비교
- "Market Insight"에 추가 섹션 (할인율, title 키워드, OEM, SKU)
- 기존 "Product Detail" 시트에 badge, 할인율 컬럼 추가

## 5. 영향 받는 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `amz_researcher/services/gemini.py` | 수정 | MARKET_REPORT_PROMPT 확장, V4 데이터 포맷팅 추가 |
| `amz_researcher/services/market_analyzer.py` | **대폭 수정** | 6개 분석 함수 신규 추가, 2개 기존 함수 수정, 1개 제거 |
| `amz_researcher/models.py` | 수정 | WeightedProduct에 badge, initial_price 필드 추가 |
| `amz_researcher/orchestrator.py` | 수정 | 신규 분석 결과 build_market_analysis에 통합, WeightedProduct 필드 주입 |
| `amz_researcher/services/excel_builder.py` | 수정 | Consumer Voice 시트 추가, Product Detail 컬럼 추가 |

## 6. 신규 함수 목록

| 함수명 | 파일 | 설명 |
|--------|------|------|
| `analyze_customer_voice()` | `market_analyzer.py` | customer_says 키워드 빈도/감성 분석 |
| `analyze_badges()` | `market_analyzer.py` | badge 보유/미보유 성과 비교 |
| `analyze_discount_impact()` | `market_analyzer.py` | 할인율 구간별 BSR/판매량 비교 |
| `analyze_title_keywords()` | `market_analyzer.py` | title 마케팅 키워드-성과 상관 |
| `analyze_unit_economics()` | `market_analyzer.py` | unit_price 파싱 + 단가 비교 |
| `analyze_manufacturer()` | `market_analyzer.py` | OEM/제조사별 프로파일 |
| `analyze_sku_strategy()` | `market_analyzer.py` | variations_count-BSR 관계 |

## 7. 제거/수정 항목

| 항목 | 파일 | 조치 |
|------|------|------|
| `analyze_competition()` | `market_analyzer.py` | 제거 (number_of_sellers 전부 1) |
| `build_market_analysis()`의 `"competition"` 키 | `market_analyzer.py` | 제거 |
| `analyze_promotions()` 내 plus_content 비교 | `market_analyzer.py` | 해당 비교 로직 제거 |

## 8. 구현 순서

```
Phase 0 (30분) — 죽은 코드 정리
├─ analyze_competition() 제거
├─ "competition" 키 제거
└─ plus_content 비교 로직 제거

Phase 1 (1주차) — Quick Wins
├─ 1. AI 리포트 V4 데이터 추가                    ← 2h
├─ 2. customer_says 키워드 분석                   ← 4h
├─ 3. badge 분석                                 ← 3h
├─ 4. 할인율 분석                                 ← 2h
└─ 5. title 키워드 분석                            ← 3h

Phase 2 (2주차) — 심화 분석
├─ 6. unit_price 파싱/단가 분석                    ← 4h
├─ 7. manufacturer(OEM) 분석                      ← 4h
├─ 8. variations_count SKU 전략 분석               ← 3h
├─ 9. SNS 심화 분석                               ← 3h
├─ 10. 통계적 유의성 검증                           ← 1d
└─ 11. Excel 시트 확장                             ← 1d
```

## 9. 의존성 추가

| 패키지 | 용도 | Phase |
|--------|------|:-----:|
| `scipy` | Mann-Whitney U test, Fisher's exact test | Phase 2 |

> 기존 패키지(pandas, openpyxl, httpx, pydantic)로 Phase 1 전체 구현 가능. scipy는 Phase 2 통계 검정에만 필요.

## 10. Success Criteria

### Phase 1

- [ ] AI 리포트가 10개 데이터 소스 기반으로 생성됨 (기존 7개 → 10개)
- [ ] customer_says 분석 결과가 build_market_analysis에 포함
- [ ] badge 보유/미보유 제품 간 BSR/가격/리뷰 비교 데이터 생성
- [ ] 할인율 구간별 BSR 비교 데이터 생성
- [ ] title 키워드별 BSR/판매량 비교 데이터 생성
- [ ] analyze_competition() 제거 후 기존 파이프라인 정상 동작

### Phase 2

- [ ] unit_price 파싱 성공률 90% 이상
- [ ] manufacturer별 제품수/BSR 프로파일 생성
- [ ] SKU 수-BSR 관계 분석 데이터 생성
- [ ] 기존 BSR/Rating 비교 분석에 p-value 부여
- [ ] Excel에 Consumer Voice 시트 추가

## 11. 비용 분석

| 항목 | 추가 비용 |
|------|----------|
| Gemini API | **$0 추가** — customer_says 분석은 키워드 사전 기반 (Gemini 미사용) |
| 인프라 | **$0 추가** — 기존 DB/서버 그대로 사용 |
| 패키지 | scipy 추가 (무료) |

> AI 리포트 프롬프트 확장으로 Gemini 입력 토큰이 ~30% 증가하나, 월 $1 미만 수준.

## 12. 리스크

| 리스크 | 완화 방안 |
|--------|----------|
| AI 리포트 프롬프트 길이 증가 → 품질 저하 | 섹션별 데이터 요약 후 전달, maxOutputTokens 유지 |
| customer_says 키워드 사전의 완성도 | 초기 사전 → 실행 후 키워드 누락 검토 → 반복 개선 |
| unit_price 파싱 실패 (예외적 형식) | 정규식 기반 파싱 + 파싱 실패 로깅 → 파싱률 모니터링 |
| 통계 검정에서 대부분 유의하지 않음 | 표본 크기(N=874) 고려, 유의 수준 0.05 적용, 결과 투명하게 보고 |

## 13. Phase 3 예고 (별도 Plan)

히스토리 스냅샷이 4주 이상 축적되면 별도 Plan으로 진행:
- BSR 트렌드 분석 (4주 이동평균, 상승/하락 분류)
- 가격 변동 패턴 (가격 인하 → BSR 변화 상관)
- Momentum Products 탐지 (BSR 연속 개선)
- 카테고리 교차 분석
- BSR 예측 모델 (회귀 분석)
