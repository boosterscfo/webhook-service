# amazon-researcher-v3 Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: webhooks
> **Design Doc**: [amazon-researcher-v3.design.md](../02-design/features/amazon-researcher-v3.design.md)
> **Date**: 2026-03-07

---

## 1. Analysis Overview

### 1.1 Purpose

Verify that the amazon-researcher-v3 implementation (성분 정규화 + 시장 분석 리포트) matches the design document across file structure, data models, Gemini, cache, market analyzer, analyzer, Excel, Slack, and orchestrator.

### 1.2 Scope

- **Design**: `docs/02-design/features/amazon-researcher-v3.design.md` (Sections 1–11, Implementation Order)
- **Implementation**: `amz_researcher/` (models, services, orchestrator)

---

## 2. Gap Analysis by Section

### 2.1 Section 1: File Structure

| Design Item | Expected | Actual | Status |
|-------------|----------|--------|--------|
| `models.py` | Ingredient.common_name 추가 | `Ingredient.common_name: str = ""` 존재 | MATCH |
| `orchestrator.py` | 시장 분석 파이프라인, analysis_data 전달 | `build_market_analysis`, `build_excel(..., analysis_data=...)` 사용 | MATCH |
| `services/gemini.py` | 프롬프트 강화, 병렬 배치, 시장 리포트 | PROMPT title/common_name, asyncio.gather, generate_market_report | MATCH |
| `services/cache.py` | common_name, harmonize, market_report, failed_asins | get/save_ingredient_cache(common_name), harmonize_common_names, market_report_cache, get/save_failed_asins | MATCH |
| `services/analyzer.py` | _get_display_name, 동의어 맵 제거 | _get_display_name(ing), _SYNONYM_MAP 등 없음 | MATCH |
| `services/market_analyzer.py` | 신규 8개 분석 함수 | build_market_analysis + 8개 함수 구현 | MATCH |
| `services/excel_builder.py` | 4개 시트 추가, Market Insight 첫 시트 | Rising Products, Form × Price, Market Insight, Analysis Data + move_sheet | MATCH |
| `services/slack_sender.py` | channel_id fallback | `elif channel_id and self.bot_token`: chat.postMessage | MATCH |

**Score: 8/8 (100%)**

---

### 2.2 Section 2: Data Model (Ingredient)

| Field | Design | Implementation | Status |
|-------|--------|----------------|--------|
| `name` | INCI 학명 원본 | `name: str` | MATCH |
| `common_name` | 마케팅용 일반명, default "" | `common_name: str = ""` | MATCH |
| `category` | str | `category: str` | MATCH |

**Score: 3/3 (100%)**

---

### 2.3 Section 3: Gemini Service

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| 프롬프트: title/features/additional_details 참고 | Yes | PROMPT_TEMPLATE에 title, features, additional_details 명시 | MATCH |
| name/common_name 규칙 및 예시 | Yes | PROMPT에 INCI 원본 + common_name 통일 규칙·예시 포함 | MATCH |
| Gemini 입력에 title 포함 | Yes | orchestrator `title_map.get(asin, "")` 전달 | MATCH |
| 병렬 배치 | asyncio.gather | `tasks = [_extract_batch(batch)...]; asyncio.gather(*tasks, return_exceptions=True)` | MATCH |
| batch_size | 20 | 20 (default) | MATCH |
| maxOutputTokens (추출) | 32768 | 32768 | MATCH |
| responseMimeType | application/json | application/json | MATCH |
| generate_market_report | 8개 섹션, temperature 0.3, 16384 tokens | 구현됨, 8개 _dump, temperature=0.3, maxOutputTokens=16384 | MATCH |

**Score: 8/8 (100%)**

---

### 2.4 Section 4: Cache Service

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| amz_ingredient_cache common_name | SELECT/INSERT common_name | get_ingredient_cache/save_ingredient_cache에 common_name 포함 | MATCH |
| harmonize_common_names() | 다수결 + earliest extracted_at | GROUP BY ingredient_name, common_name → canonical 선택 → UPDATE | MATCH |
| get_market_report_cache(keyword, product_count) | Yes | 구현, product_count 조건 포함 | MATCH |
| save_market_report_cache(keyword, report_md, product_count) | Yes | 구현 | MATCH |
| get_failed_asins() | set[str] | 구현, amz_failed_asins 조회 | MATCH |
| save_failed_asins(asins, keyword) | Yes | 구현 | MATCH |

**Score: 6/6 (100%)**

---

### 2.5 Section 5: Market Analyzer

| Function | Design | Implementation | Status |
|----------|--------|----------------|--------|
| _price_tier | Budget/Mid/Premium/Luxury | 동일 구간 및 라벨 | MATCH |
| analyze_by_price_tier | tier → {count, top5} | 구현, product_count + top_ingredients | MATCH |
| analyze_by_bsr | 상위/하위 20%, winning | top/bottom/winning_ingredients (design은 "winning" 표기) | MATCH |
| analyze_by_brand | brand, count, avg_price, top_ingredients | 구현, 2개+ 제품만 | MATCH |
| analyze_cooccurrence | top_pairs, high_rated_exclusive | 구현 | MATCH |
| analyze_form_by_price | matrix, form_summary | matrix_data, form_summary | MATCH |
| analyze_brand_positioning | brand, avg_price, avg_bsr, segment | 구현 | MATCH |
| detect_rising_products | 리뷰 < threshold, BSR < 10000 | median_reviews, threshold 2000 cap, BSR 10000 | MATCH |
| analyze_rating_ingredients | high_only, low_only, high_top10, low_top10 | high_only_ingredients, low_only_ingredients, high_top10, low_top10 | MATCH |
| build_market_analysis | keyword, total_products, 8개 키 | 8개 키 동일 반환 | MATCH |

**Score: 10/10 (100%)**

---

### 2.6 Section 6: Analyzer

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| _get_display_name(ing) | common_name 우선, 없으면 name | `ing.common_name if ing.common_name else ing.name` | MATCH |
| _aggregate_ingredients 집계 키 | _get_display_name(ing) | 동일 사용 | MATCH |
| _normalize_ingredient_name, _INCI_RE, _SYNONYM_MAP 제거 | 제거 | 코드에 없음 | MATCH |

**Score: 3/3 (100%)**

---

### 2.7 Section 7: Excel Builder

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| 시트 순서 (최종) | 1 Market Insight … 9 Analysis Data | move_sheet로 Market Insight 맨 앞, 나머지 순서 일치 | MATCH |
| _build_rising_products | BSR, Brand, Title, Price, Reviews, Rating, Form, Top Ingredients, ASIN | 동일 컬럼 | MATCH |
| _build_form_price | Form Summary + Price Tier × Form Matrix | form_summary + matrix | MATCH |
| _build_analysis_data | 8개 섹션 헤더 + JSON | sections 8개, JSON 텍스트 출력 | MATCH |
| _build_market_insight | A4 단일 셀, Notion 복붙 | A5 단일 셀에 report_md (행만 1칸 차이) | MINOR |
| build_excel 시그니처 | market_report, rising_products, form_price_data, analysis_data | 동일 파라미터 | MATCH |

**Score: 5.5/6 (92%)** — Market Insight 셀 위치만 설계는 A4, 구현은 A5 (미세 차이).

---

### 2.8 Section 8: Slack Sender

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| send_message(response_url, text, ephemeral, channel_id) | response_url 우선, else channel_id로 chat.postMessage | 동일 분기 | MATCH |

**Score: 1/1 (100%)**

---

### 2.9 Section 9: Orchestrator

| Item | Design | Implementation | Status |
|------|--------|----------------|--------|
| Step 1–8 파이프라인 | Search → Detail → Gemini/harmonize → Weight → 시장 분석/리포트 → Excel → Slack 요약 → 파일 업로드 | 동일 순서 | MATCH |
| _msg()에 response_url + channel_id 전달 | Yes | `_msg(text, ephemeral)` 내부에서 전달 | MATCH |
| title_map, Gemini 입력에 title 포함 | Yes | title_map 생성 후 products_for_gemini에 title 포함 | MATCH |
| analysis_data = build_market_analysis(...) | Yes | 구현 | MATCH |
| build_excel(..., analysis_data=...) | Yes | 구현 | MATCH |
| 시장 리포트 `## 7.` (액션 아이템) → Slack 요약 포함 | 설계 명시 | _build_summary는 Top 5 성분만 사용, 액션 아이템 추출 없음 | **GAP** |

**Score: 5/6 (83%)**

---

### 2.10 Section 11: Implementation Order

| Phase | Design | Actual | Status |
|-------|--------|--------|--------|
| 1 | models.py Ingredient.common_name | 완료 | MATCH |
| 2 | gemini.py 프롬프트·병렬·시장 리포트 | 완료 | MATCH |
| 3 | cache.py common_name, harmonize, market_report, failed_asins | 완료 | MATCH |
| 4 | analyzer.py _get_display_name, 동의어 제거 | 완료 | MATCH |
| 5 | market_analyzer.py 8개 함수 | 완료 | MATCH |
| 6 | excel_builder.py 4시트, Market Insight 첫 시트 | 완료 | MATCH |
| 7 | slack_sender.py channel_id fallback | 완료 | MATCH |
| 8 | orchestrator.py 시장 분석 파이프라인 | 완료 (단, 액션 아이템 요약 미포함) | PARTIAL |

---

## 3. Gap Summary

### 3.1 미구현/불일치

| Priority | Item | Location | Description |
|----------|------|----------|-------------|
| **Medium** | Slack 요약에 액션 아이템 포함 | orchestrator.py | 설계: "시장 리포트에서 `## 7.` (액션 아이템) 섹션 추출 → Slack 요약에 포함". 현재 _build_summary는 Top 5 성분만 사용. report_md에서 `## 7.` 또는 "제품 기획 액션 아이템" 섹션을 파싱해 요약 텍스트에 추가 필요. |

### 3.2 Minor (선택 보완)

| Item | Design | Implementation |
|------|--------|----------------|
| Market Insight 셀 | A4 단일 셀 | A5 단일 셀 (제목/부제/안내 3행 사용) |

---

## 4. Match Rate

| Section | Score | Weight |
|---------|-------|--------|
| 1. File Structure | 8/8 | 1 |
| 2. Data Model | 3/3 | 1 |
| 3. Gemini | 8/8 | 1 |
| 4. Cache | 6/6 | 1 |
| 5. Market Analyzer | 10/10 | 1 |
| 6. Analyzer | 3/3 | 1 |
| 7. Excel Builder | 5.5/6 | 1 |
| 8. Slack Sender | 1/1 | 1 |
| 9. Orchestrator | 5/6 | 1 |

**Total: 49.5 / 51 ≈ 97.1%**

---

## 5. Recommended Actions

### 5.1 권장 (설계 완전 준수)

- **Slack 액션 아이템**: `orchestrator._build_summary` 또는 별도 헬퍼에서 `market_report`(마크다운) 문자열을 파싱해 "## 7." 또는 "제품 기획 액션 아이템" 섹션을 찾아 Slack 요약 메시지에 포함.

### 5.2 선택

- Market Insight 시트의 리포트 본문 셀을 설계대로 A4로 옮기거나, 현재 A5를 설계에 "단일 셀(데이터 영역)"로 명시해 문서만 정리.

---

## 6. Conclusion

amazon-researcher-v3 구현은 설계 대비 **약 97% 일치**한다.  
성분 정규화(common_name), Gemini 병렬·시장 리포트, 캐시(harmonize, market_report, failed_asins), market_analyzer 8개 분석, Excel 9시트(순서 포함), Slack channel_id fallback, 오케스트레이션 단계가 모두 반영되어 있다.

**미반영 사항 1건**: 시장 리포트의 액션 아이템(## 7.)을 Slack 요약에 포함하는 부분.  
이 항목을 구현하면 설계와의 일치도가 더 높아진다.

**Verdict**: 설계와 구현은 대부분 정합. 액션 아이템 Slack 포함 여부는 제품/운영 요구에 따라 보완하면 된다.
