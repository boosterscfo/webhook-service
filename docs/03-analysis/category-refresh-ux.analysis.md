# category-refresh-ux Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: webhook-service
> **Analyst**: gap-detector
> **Date**: 2026-03-11
> **Design Doc**: [category-refresh-ux.design.md](../02-design/features/category-refresh-ux.design.md)

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 문서와 구현 코드 간 일치 여부를 검증하여 Match Rate를 산출한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/category-refresh-ux.design.md`
- **Implementation Files**:
  - `amz_researcher/services/product_db.py` — `get_category_freshness()` 메서드
  - `amz_researcher/router.py` — interact 핸들러 변경, 새 action_id 핸들러, `_build_category_options()` 빌더

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Section 2.1 — `get_category_freshness()` 메서드

| 비교 항목 | Design | Implementation | Status |
|-----------|--------|----------------|--------|
| 메서드 시그니처 | `get_category_freshness(self, node_id: str) -> dict \| None` | `get_category_freshness(self, node_id: str) -> dict \| None` | MATCH |
| SQL 쿼리 | `SELECT COUNT(*) as product_count, MAX(p.collected_at) as collected_at FROM amz_products p JOIN amz_product_categories pc ON p.asin = pc.asin WHERE pc.category_node_id = %s` | 동일 | MATCH |
| DB 환경 | `MysqlConnector(self._env)` | `MysqlConnector(self._env)` | MATCH |
| read_query_table 호출 | `conn.read_query_table(query, (node_id,))` | 동일 | MATCH |
| Exception 처리 | `except Exception:` → `logger.exception(...)` → `return None` | 동일 | MATCH |
| df.empty 체크 | `if df.empty: return None` | 동일 | MATCH |
| count=0 / NULL 체크 | `if count == 0 or row["collected_at"] is None: return None` | 동일 | MATCH |
| 반환값 형식 | `{"product_count": count, "collected_at": row["collected_at"]}` | 동일 | MATCH |
| docstring | `{"product_count": int, "collected_at": datetime} or None` | `{"product_count": int, "collected_at": datetime} or None (미수집)` | MATCH |

**Section 2.1 결과: 9/9 MATCH (100%)**

### 2.2 Section 2.2.1 — `amz_category_{node_id}` 핸들러 변경

| 비교 항목 | Design | Implementation (router.py:531-554) | Status |
|-----------|--------|--------------------------------------|--------|
| node_id/name 추출 | `value.get("node_id")`, `value.get("name")` | 동일 | MATCH |
| response_url/channel_id | `value["response_url"]`, `value["channel_id"]` | 동일 | MATCH |
| ProductDBService 생성 | `ProductDBService("CFO")` | 동일 | MATCH |
| freshness 조회 | `product_db.get_category_freshness(node_id)` | 동일 | MATCH |
| None 분기: 수집 트리거 | `background_tasks.add_task(_trigger_category_collection, ...)` | 동일 | MATCH |
| None 분기: 응답 텍스트 | `📡 *{name}* 데이터가 없습니다. 수집을 시작합니다...` | 동일 | MATCH |
| None 분기: response_type | `ephemeral` | 동일 | MATCH |
| 캐시 있음: 선택지 반환 | `_build_category_options(node_id, name, freshness, response_url, channel_id)` | 동일 | MATCH |
| 핸들러 위치 (fallback) | 카테고리 분기 위치에 배치 | interact 핸들러의 마지막 fallback으로 배치됨 (amz_cat_refresh, amz_cat_cached 이후) | MATCH |

**Section 2.2.1 결과: 9/9 MATCH (100%)**

### 2.3 Section 2.2.2 — `amz_cat_refresh`, `amz_cat_cached` 핸들러

| 비교 항목 | Design | Implementation (router.py:502-529) | Status |
|-----------|--------|--------------------------------------|--------|
| `amz_cat_refresh` action_id | `if action_id == "amz_cat_refresh":` | 동일 | MATCH |
| refresh: value 추출 | `value["node_id"]`, `value["name"]`, `value["response_url"]`, `value["channel_id"]` | 동일 | MATCH |
| refresh: 태스크 | `_trigger_category_collection(node_id, name, response_url, channel_id, user_id)` | 동일 | MATCH |
| refresh: 응답 텍스트 | `📡 *{name}* 새로 수집 시작... 완료 시 자동으로 분석 결과를 보내드립니다.` | 동일 | MATCH |
| `amz_cat_cached` action_id | `if action_id == "amz_cat_cached":` | 동일 | MATCH |
| cached: value 추출 | `value["node_id"]`, `value["name"]`, `value["response_url"]`, `value["channel_id"]` | 동일 | MATCH |
| cached: 태스크 | `run_analysis(node_id, name, response_url, channel_id, user_id)` | 동일 | MATCH |
| cached: 응답 텍스트 | `📊 *{name}* 기존 데이터로 분석 시작... 완료 시 채널에 결과가 공유됩니다.` | 동일 | MATCH |
| 핸들러 순서 | 키워드 분기 아래, 카테고리 분기 위 | `amz_keyword_new` 아래, fallback `amz_category_` 위 | MATCH |

**Section 2.2.2 결과: 9/9 MATCH (100%)**

### 2.4 Section 2.2.3 — `_build_category_options()` 빌더 함수

| 비교 항목 | Design | Implementation (router.py:557-614) | Status |
|-----------|--------|--------------------------------------|--------|
| 함수 시그니처 | `_build_category_options(node_id, name, freshness, response_url, channel_id) -> dict` | 동일 | MATCH |
| datetime import | `from datetime import datetime` (함수 내 lazy import) | 동일 | MATCH |
| collected_at 추출 | `freshness["collected_at"]` | 동일 | MATCH |
| product_count 추출 | `freshness["product_count"]` | 동일 | MATCH |
| days_ago 계산 | `(datetime.now() - collected_at).days` | 동일 | MATCH |
| age_text: 0일 | `"오늘"` | 동일 | MATCH |
| age_text: N일 | `f"{days_ago}일 전"` | 동일 | MATCH |
| age_text 로직 (코드 스타일) | if/else 블록 (4줄) | 삼항 표현식 1줄: `"오늘" if days_ago == 0 else f"{days_ago}일 전"` | MATCH |
| payload JSON | `{"node_id", "name", "response_url", "channel_id"}` | 동일 | MATCH |
| Block Kit: response_type | `ephemeral` | 동일 | MATCH |
| Block Kit: section text | `:mag: *{name}*\n현재 데이터: {product_count}개 제품, {age_text} 수집` | 동일 | MATCH |
| Block Kit: 새로 수집 버튼 text | `새로 수집 후 분석` | 동일 | MATCH |
| Block Kit: 새로 수집 action_id | `amz_cat_refresh` | 동일 | MATCH |
| Block Kit: 새로 수집 style | `primary` | 동일 | MATCH |
| Block Kit: 캐시 사용 버튼 text | `캐시 사용 ({age_text})` | 동일 | MATCH |
| Block Kit: 캐시 사용 action_id | `amz_cat_cached` | 동일 | MATCH |
| docstring | 포함 | 포함 | MATCH |

**Section 2.2.3 결과: 17/17 MATCH (100%)**

### 2.5 Section 3 — Action ID 맵

| action_id | Design 동작 | Implementation | Status |
|-----------|-------------|----------------|--------|
| `amz_category_{node_id}` | **변경**: freshness 조회 → 선택지 or 바로 수집 | router.py:531-554 — freshness 분기 구현됨 | MATCH |
| `amz_cat_refresh` | **신규**: `_trigger_category_collection()` | router.py:502-515 — 구현됨 | MATCH |
| `amz_cat_cached` | **신규**: `run_analysis()` 즉시 호출 | router.py:517-529 — 구현됨 | MATCH |
| `amz_keyword_existing_{hash}` | 기존 유지 | router.py:481-489 — 기존 유지 | MATCH |
| `amz_keyword_new` | 기존 유지 | router.py:492-500 — 기존 유지 | MATCH |

**Section 3 결과: 5/5 MATCH (100%)**

### 2.6 Section 4 — Slack Block Kit 메시지

| 비교 항목 | Design | Implementation | Status |
|-----------|--------|----------------|--------|
| 캐시 있는 카테고리: section block | `:mag: *{name}*` + 제품수 + age_text | 동일 | MATCH |
| 캐시 있는 카테고리: actions block | 2버튼 (새로 수집 primary, 캐시 사용 default) | 동일 | MATCH |
| 미수집 카테고리: 텍스트 | `📡 {name} 데이터가 없습니다. 수집을 시작합니다...` | 동일 | MATCH |
| 오늘 수집: age_text | `오늘` | 동일 | MATCH |

**Section 4 결과: 4/4 MATCH (100%)**

### 2.7 변경 범위 (Section 1.3)

| 파일 | Design 변경 여부 | 실제 변경 여부 | Status |
|------|-----------------|---------------|--------|
| `product_db.py` | 변경 (메서드 추가) | `get_category_freshness()` 추가됨 | MATCH |
| `router.py` | 변경 (핸들러 수정 + 신규 2개) | interact 핸들러 분기 변경 + `amz_cat_refresh`/`amz_cat_cached` + `_build_category_options()` | MATCH |
| `orchestrator.py` | 변경 없음 | 변경 없음 | MATCH |
| `services/cache.py` | 변경 없음 | 변경 없음 | MATCH |
| `services/bright_data.py` | 변경 없음 | 변경 없음 | MATCH |
| `services/slack_sender.py` | 변경 없음 | 변경 없음 | MATCH |

**변경 범위 결과: 6/6 MATCH (100%)**

---

## 3. Match Rate Summary

```
+---------------------------------------------+
|  Overall Match Rate: 100%                    |
+---------------------------------------------+
|  Total comparison items:  59                 |
|  MATCH:                   59 (100%)          |
|  CHANGED (compatible):     0 (0%)            |
|  PARTIAL:                  0 (0%)            |
|  MISSING:                  0 (0%)            |
+---------------------------------------------+
```

| Category | Items | Match | Rate | Status |
|----------|:-----:|:-----:|:----:|:------:|
| Section 2.1 — `get_category_freshness()` | 9 | 9 | 100% | PASS |
| Section 2.2.1 — `amz_category_{node_id}` handler | 9 | 9 | 100% | PASS |
| Section 2.2.2 — `amz_cat_refresh`/`amz_cat_cached` | 9 | 9 | 100% | PASS |
| Section 2.2.3 — `_build_category_options()` | 17 | 17 | 100% | PASS |
| Section 3 — Action ID map | 5 | 5 | 100% | PASS |
| Section 4 — Slack Block Kit messages | 4 | 4 | 100% | PASS |
| Section 1.3 — Change scope | 6 | 6 | 100% | PASS |
| **Total** | **59** | **59** | **100%** | **PASS** |

---

## 4. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | PASS |
| Architecture Compliance | 100% | PASS |
| Convention Compliance | 100% | PASS |
| **Overall** | **100%** | **PASS** |

---

## 5. Implementation Quality Notes

구현이 설계와 완전히 일치하며, 다음 사항이 확인됨:

- **age_text 로직**: Design은 4줄 if/else, 구현은 삼항 표현식 1줄. 동작 동일, 코드 스타일 차이만 존재하여 MATCH 판정.
- **핸들러 배치 순서**: Design 명세 "키워드 분기 아래, 카테고리 분기 위"와 일치. `amz_keyword_new`(L492) → `amz_cat_refresh`(L502) → `amz_cat_cached`(L517) → fallback `amz_category_*`(L531).
- **기존 패턴 일관성**: `/amz search`의 유사 키워드 캐시 패턴(Section 5)과 동일한 구조로 구현됨.

---

## 6. Gaps Found

없음. 0 Critical, 0 Major, 0 Minor.

---

## 7. Recommended Actions

없음. 설계와 구현이 완전히 일치하므로 추가 조치 불필요.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-11 | Initial analysis — 100% match rate | gap-detector |
