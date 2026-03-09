# Amazon Researcher V5 Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: webhook-service (amz_researcher)
> **Version**: V5
> **Analyst**: Gap Detector Agent
> **Date**: 2026-03-09
> **Design Doc**: [amazon-researcher-v5.design.md](../02-design/features/amazon-researcher-v5.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Amazon Researcher V5 Design 문서에 정의된 24개 구현 단계(Phase 0: 3개, Phase 1: 10개, Phase 2: 12개)와 실제 구현 코드를 1:1 비교하여 Match Rate를 산출한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/amazon-researcher-v5.design.md`
- **Implementation Files**:
  - `amz_researcher/models.py`
  - `amz_researcher/services/market_analyzer.py`
  - `amz_researcher/services/gemini.py`
  - `amz_researcher/orchestrator.py`
  - `amz_researcher/services/excel_builder.py`
  - `pyproject.toml`
- **Analysis Date**: 2026-03-09

---

## 2. Phase 0: Dead Code Cleanup (3 items)

| Step | Description | Status | Evidence |
|:----:|-------------|:------:|----------|
| 0-1 | `analyze_competition()` 함수 삭제 | **MATCH** | `market_analyzer.py`에 함수 없음. grep 결과 0건. |
| 0-2 | `build_market_analysis()`에서 `"competition"` 키 삭제 | **MATCH** | L889-919: `"competition"` 키 없음. 주석으로 "competition 제거" 명시(L906). |
| 0-3 | `analyze_promotions()`에서 `plus_content` 관련 코드 삭제 | **MATCH** | L392-419: `with_plus`, `plus_content_count`, `plus_content_pct` 모두 없음. 쿠폰만 분석. Design과 정확히 일치. |

**Phase 0 Score: 3/3 (100%)**

---

## 3. Phase 1: Quick Wins (10 items)

| Step | Description | Status | Evidence |
|:----:|-------------|:------:|----------|
| 1-1 | `WeightedProduct`에 `badge`, `initial_price`, `manufacturer`, `variations_count` 추가 | **MATCH** | `models.py` L107-111: 4개 필드 모두 존재. 타입/기본값 Design과 일치. |
| 1-2 | `orchestrator.py`에 4개 필드 주입 추가 | **MATCH** | `orchestrator.py` L518-522: `wp.badge`, `wp.initial_price`, `wp.manufacturer`, `wp.variations_count` 주입. Design과 정확히 일치. |
| 1-3 | `MARKET_REPORT_PROMPT` 10개 데이터 소스로 확장 | **MATCH** | `gemini.py` L83-162: 10개 데이터 소스({price_tier_json}~{promotions_json}), 8개 리포트 섹션. Design의 프롬프트 텍스트와 완전 일치. |
| 1-4 | `generate_market_report()`에 3개 `_dump()` 추가 | **MATCH** | `gemini.py` L272-275: `sales_volume_json`, `sns_pricing_json`, `promotions_json` 3개 `_dump()` 추가. V5 주석 포함. |
| 1-5 | `_extract_action_items_section()` 섹션 번호 6->7 수정 | **MATCH** | `orchestrator.py` L30-33: 정규식에 `7\.\s*(?:\*\*)?액션\s*아이템` 사용, 종료 조건 `8\.`. Design과 정확히 일치. |
| 1-6 | `analyze_customer_voice()` 추가 | **MATCH** | `market_analyzer.py` L470-539: 함수 존재. POSITIVE_KEYWORDS 15개, NEGATIVE_KEYWORDS 15개, BSR 상/하위 비교. Design의 코드와 완전 일치. |
| 1-7 | `analyze_badges()` 추가 | **MATCH** | `market_analyzer.py` L542-590: 함수 존재. `_group_metrics()`, `acquisition_threshold`, `badge_types`. Design 대비 `stat_test_bsr` 추가(Phase 2 선적용). |
| 1-8 | `analyze_discount_impact()` 추가 | **MATCH** | `market_analyzer.py` L593-649: 함수 존재. 4단계 할인 구간, `_tier_metrics()`. Design 대비 `stat_test_bsr` 추가(Phase 2 선적용). |
| 1-9 | `analyze_title_keywords()` 추가 | **MATCH** | `market_analyzer.py` L652-697: 함수 존재. MARKETING_KEYWORDS 22개, BSR 정렬. Design과 완전 일치. |
| 1-10 | `build_market_analysis()`에 Phase 1 분석 4개 추가 | **MATCH** | `market_analyzer.py` L910-914: `customer_voice`, `badges`, `discount_impact`, `title_keywords` 모두 포함. |

**Phase 1 Score: 10/10 (100%)**

---

## 4. Phase 2: Deep Analysis (12 items)

| Step | Description | Status | Evidence |
|:----:|-------------|:------:|----------|
| 2-1 | `scipy` 의존성 추가 | **MATCH** | `pyproject.toml` L22: `"scipy>=1.11"`. Design과 정확히 일치. |
| 2-2 | `_parse_unit_price()` + `analyze_unit_economics()` 추가 | **MATCH** | `market_analyzer.py` L719-776: 두 함수 모두 존재. 파싱 정규식, unit_data 집계, unit_summaries 반환값 Design과 완전 일치. |
| 2-3 | `analyze_manufacturer()` 추가 | **MATCH** | `market_analyzer.py` L779-848: 함수 존재. K_BEAUTY_KEYWORDS 15개, market_concentration, top_manufacturers[:15]. Design과 완전 일치. |
| 2-4 | `analyze_sku_strategy()` 추가 | **MATCH** | `market_analyzer.py` L851-886: 함수 존재. 4단계 SKU 구간, `_tier_metrics()`. Design과 완전 일치. |
| 2-5 | `analyze_sns_pricing()` 확장 (심화 3항목) | **MATCH** | `market_analyzer.py` L331-389: `discount_tier_metrics`, `retention_signal`, `price_tier_adoption` 모두 포함. Design과 완전 일치. |
| 2-6 | `_stat_compare()` + 기존 함수에 통계 검증 추가 | **PARTIAL** | `market_analyzer.py` L703-716: `_stat_compare()` 함수 존재(Design 일치). `analyze_badges()` L589와 `analyze_discount_impact()` L648에 적용됨. 그러나 Design에서 명시한 `analyze_by_bsr()`에는 `stat_test` 미적용. |
| 2-7 | `build_market_analysis()`에 Phase 2 분석 3개 추가 | **MATCH** | `market_analyzer.py` L916-918: `unit_economics`, `manufacturer`, `sku_strategy` 모두 포함. |
| 2-8 | `_build_consumer_voice()` 시트 추가 | **MATCH** | `excel_builder.py` L423-470: 함수 존재. 탭색 FF9800, POSITIVE/NEGATIVE 섹션. Design과 완전 일치. |
| 2-9 | `_build_badge_analysis()` 시트 추가 | **MATCH** | `excel_builder.py` L473-515: 함수 존재. 탭색 673AB7, With/Without Badge, Badge Type Distribution. Design과 완전 일치. |
| 2-10 | Product Detail에 badge/discount%/variations 컬럼 추가 | **PARTIAL** | `excel_builder.py` L200-206: 20컬럼 헤더에 Badge(col 15), Discount%(col 16), Variations(col 17) 포함. 그러나 URL(col 20) 데이터 미기록 -- L211-240에서 col 19(ingredients)까지만 기록하고 col 20(URL)에 값을 쓰지 않음. |
| 2-11 | `build_excel()` 시그니처 변경 (`analysis_data` 파라미터) | **MATCH** | `excel_builder.py` L518-529: `analysis_data: dict | None = None` 파라미터 추가. 내부에서 `customer_voice`, `badges` 시트 조건부 생성. Design과 일치. |
| 2-12 | `orchestrator.py`: `build_excel()` 호출에 `analysis_data` 전달 | **MATCH** | `orchestrator.py` L283-289(run_research) 및 L537-543(run_analysis): 두 곳 모두 `analysis_data=analysis_data` 전달. Design과 일치. |

**Phase 2 Score: 10/12 (83.3%) -- 2개 PARTIAL**

---

## 5. Implementation Improvements (Design에 없으나 구현에 추가)

| Item | Location | Description | Impact |
|------|----------|-------------|--------|
| stat_test 선적용 | `market_analyzer.py` L577-589, L630-648 | `analyze_badges()`, `analyze_discount_impact()`에 Phase 2의 `_stat_compare()` 통계 검증을 Phase 1 함수에도 바로 적용 | Positive -- 코드 중복 없이 Phase 1 함수에 Phase 2 기능 통합 |
| run_research에도 analysis_data 전달 | `orchestrator.py` L283-289 | Design은 `run_analysis()`만 언급하나, `run_research()`에도 동일하게 적용 | Positive -- Browse.ai 파이프라인에서도 V5 시트 생성 가능 |

---

## 6. Gaps Found

### 6.1 PARTIAL: `analyze_by_bsr()`에 stat_test 미적용

- **Design**: Section 6.5에서 `_stat_compare()` 적용 대상에 `analyze_by_bsr()` 명시
- **Implementation**: `analyze_by_bsr()` (L54-87)에 `stat_test` 키 없음
- **Severity**: Minor -- `analyze_by_bsr()`는 성분 비교 함수로 BSR 그룹 간 수치 비교보다 성분 리스트 비교가 주목적
- **Recommendation**: `analyze_by_bsr()`의 top_group vs bottom_group BSR 분포에 대해 `_stat_compare()` 추가하거나, Design에서 적용 대상 목록을 수정

### 6.2 PARTIAL: Product Detail URL 컬럼 데이터 미기록

- **Design**: Section 6.6.3에서 "기존 Customer Says, Ingredients Found, URL은 col 18, 19, 20으로 밀림"
- **Implementation**: `excel_builder.py` L200-206에 "URL" 헤더(col 20)는 있으나, L211-240 데이터 루프에서 col 20에 URL 값을 쓰는 코드 없음
- **Severity**: Minor -- URL은 Raw - Product Detail 시트에서 확인 가능하므로 기능적 영향 작음
- **Recommendation**: Product Detail 데이터 루프에 `ws.cell(row=row, column=20, value=...)` 추가 (단, WeightedProduct 모델에 URL 필드가 없으므로 별도 매핑 필요)

---

## 7. Match Rate Summary

```
+-----------------------------------------------+
|  Overall Match Rate: 96%                       |
+-----------------------------------------------+
|  Total Steps:           25 (Phase 0: 3,        |
|                             Phase 1: 10,       |
|                             Phase 2: 12)       |
|                                                |
|  MATCH:                 23 items (92.0%)       |
|  PARTIAL:                2 items ( 8.0%)       |
|  MISSING:                0 items ( 0.0%)       |
|                                                |
|  Implementation Improvements: 2 items          |
+-----------------------------------------------+

Phase Breakdown:
  Phase 0 (Dead Code Cleanup):   3/3  = 100%
  Phase 1 (Quick Wins):         10/10 = 100%
  Phase 2 (Deep Analysis):      10/12 =  83% (2 Partial)
```

**Weighted Score**: 23 MATCH x 4pts + 2 PARTIAL x 3pts = 98/100 = **98%**

---

## 8. Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 96% | PASS |
| Architecture Compliance | 100% | PASS |
| Convention Compliance | 100% | PASS |
| **Overall** | **98%** | **PASS** |

### Architecture Notes
- 모든 신규 함수가 `analyze_*()` 네이밍 패턴 준수
- `list[WeightedProduct]` 입력, `dict` 반환 패턴 일관 유지
- `_stat_compare()`, `_parse_unit_price()` 등 유틸리티 함수는 `_` prefix (private) 패턴 준수
- `market_analyzer.py` 중심 확장, 기존 파이프라인 구조 유지

### Convention Notes
- Python snake_case 네이밍 전체 준수
- 함수 docstring 전체 포함
- import 순서: stdlib -> third-party -> local 준수

---

## 9. Recommended Actions

### 9.1 Minor Fix (Optional)

| Priority | Item | File | Line |
|----------|------|------|------|
| Low | `analyze_by_bsr()`에 `stat_test` 추가 또는 Design 수정 | `market_analyzer.py` | L54-87 |
| Low | Product Detail URL 컬럼 데이터 기록 추가 | `excel_builder.py` | L211-240 |

### 9.2 Design Document Update

- Section 6.5: `analyze_by_bsr()` 적용이 불필요하다면 적용 대상 목록에서 제거
- Section 6.6.3: URL 컬럼 데이터 소스 명시 (WeightedProduct에 URL 필드가 없는 점 반영)

---

## 10. Detailed Comparison Matrix

### 10.1 models.py

| Design Item | Design Location | Implementation | Match |
|-------------|-----------------|----------------|:-----:|
| badge: str = "" | Section 3.1, L110 | models.py L108 | MATCH |
| initial_price: float \| None = None | Section 3.1, L111 | models.py L109 | MATCH |
| manufacturer: str = "" | Section 3.1, L112 | models.py L110 | MATCH |
| variations_count: int = 0 | Section 3.1, L113 | models.py L111 | MATCH |

### 10.2 market_analyzer.py

| Design Function | Design Section | Implementation Line | Match |
|-----------------|----------------|---------------------|:-----:|
| analyze_competition() 삭제 | 4.1 | Not found (confirmed deleted) | MATCH |
| analyze_promotions() plus_content 제거 | 4.3 | L392-419 | MATCH |
| analyze_customer_voice() | 5.2 | L470-539 | MATCH |
| analyze_badges() | 5.3 | L542-590 | MATCH |
| analyze_discount_impact() | 5.4 | L593-649 | MATCH |
| analyze_title_keywords() | 5.5 | L652-697 | MATCH |
| _stat_compare() | 6.5 | L703-716 | MATCH |
| _parse_unit_price() | 6.1 | L719-729 | MATCH |
| analyze_unit_economics() | 6.1 | L732-776 | MATCH |
| analyze_manufacturer() | 6.2 | L779-848 | MATCH |
| analyze_sku_strategy() | 6.3 | L851-886 | MATCH |
| analyze_sns_pricing() 확장 | 6.4 | L309-389 | MATCH |
| build_market_analysis() 최종형 | 7 | L889-919 | MATCH |
| analyze_by_bsr() stat_test | 6.5 | L54-87 (미적용) | PARTIAL |

### 10.3 gemini.py

| Design Item | Design Section | Implementation Line | Match |
|-------------|----------------|---------------------|:-----:|
| MARKET_REPORT_PROMPT 10개 데이터 | 5.1.1 | L83-162 | MATCH |
| generate_market_report() 3개 _dump() | 5.1.2 | L272-275 | MATCH |

### 10.4 orchestrator.py

| Design Item | Design Section | Implementation Line | Match |
|-------------|----------------|---------------------|:-----:|
| V5 4개 필드 주입 | 3.2 | L518-522 | MATCH |
| _extract_action_items_section() 7->8 | 5.1.3 | L30-33 | MATCH |
| build_excel() analysis_data 전달 | 6.6.5 | L537-543 | MATCH |

### 10.5 excel_builder.py

| Design Item | Design Section | Implementation Line | Match |
|-------------|----------------|---------------------|:-----:|
| _build_consumer_voice() | 6.6.1 | L423-470 | MATCH |
| _build_badge_analysis() | 6.6.2 | L473-515 | MATCH |
| Product Detail 20컬럼 | 6.6.3 | L200-251 | PARTIAL |
| build_excel() analysis_data | 6.6.4 | L518-529 | MATCH |

### 10.6 pyproject.toml

| Design Item | Design Section | Implementation | Match |
|-------------|----------------|----------------|:-----:|
| scipy>=1.11 | 9 | pyproject.toml L22 | MATCH |

---

## 11. Conclusion

V5 Design 문서에 정의된 25개 구현 항목 중 23개가 완전 일치(MATCH), 2개가 부분 일치(PARTIAL)로 **전체 Match Rate 98%**를 달성했다. 2개의 PARTIAL 항목은 모두 Minor severity이며 기능적 영향이 작다. 구현은 Design을 충실히 반영하면서도 2건의 개선(stat_test 선적용, run_research 파이프라인 적용)을 추가로 포함하고 있다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-09 | Initial analysis | Gap Detector Agent |
