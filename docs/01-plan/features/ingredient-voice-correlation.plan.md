# Voice-Ingredient Correlation — ODM Brief Guide

> **Summary**: 소비자 부정 피드백(Voice -)과 전성분(INCI)의 상관관계를 분석하여, PM이 ODM 브리프에 바로 활용할 수 있는 제형 방향 가이드를 Slack 커맨드로 제공한다.
>
> **Project**: amz_researcher (webhook-service)
> **Author**: Plan Plus
> **Date**: 2026-03-12
> **Status**: Draft → **v0.3 Pivot**

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | PM이 ODM에 제형 방향을 전달할 때 "끈적이지 않게 해주세요" 수준의 감각적 요청만 가능. 데이터 근거가 없어 ODM 설득력이 약하고, 동일 불만이 반복되는 제품이 출시됨 |
| **Solution** | Voice - 키워드별 성분 enrichment 분석 → Gemini가 ODM 브리프용 제형 방향 가이드를 자동 생성하는 `/amz why` 커맨드 |
| **Function/UX Effect** | `/amz why` → 부정 키워드 목록 → 클릭 → "원인 패턴 + 브리프 제안 + 피할 패턴 + 안전 조합" 4줄 가이드를 즉시 수신. 성분명 몰라도 사용 가능 |
| **Core Value** | PM이 성분 전문가가 아니어도 데이터 기반 ODM 브리프를 작성할 수 있음 — "아마존 847개 제품 분석 결과, sticky 피드백의 주 원인은 고분자 보습제 + 중량 유화제 조합" |

---

## User Intent Discovery

| Item | Answer |
|------|--------|
| **Core Problem** | PM → ODM 브리프의 데이터 근거 부재. 감각적 요청("끈적이지 않게")을 데이터 기반 방향 제시("고분자 보습 베이스 회피, 경량 유화 시스템 요청")로 전환 |
| **Target User** | 제품 기획자 (PM) — 성분 전문가가 아님. ODM에 제형 방향을 전달하는 역할 |
| **Success Criteria** | (1) PM이 성분명을 몰라도 브리프 가이드를 얻을 수 있음 (2) 가이드를 ODM 브리프에 복붙 가능 (3) 5-8초 내 반환 |
| **UX** | `/amz why` (discovery) + `/amz why {keyword}` (분석) — 2단계 진입 |

---

## Alternatives Explored

| Approach | Description | Pros | Cons | Selected |
|----------|-------------|------|------|:--------:|
| A: 성분 테이블 중심 | enrichment 결과를 성분명 + ratio로 표시 | 정확한 데이터 | PM이 성분명으로 행동 불가 | ✗ |
| B: Gemini 화학 해석 | 성분 테이블 + 화학적 원리 설명 | 전문적 | PM에게 너무 기술적 | ✗ |
| **C: ODM 브리프 가이드** | enrichment 분석 → Gemini가 PM 언어로 브리프 생성 | 즉시 행동 가능 | Gemini 의존 | **✓** |

**선택 근거**: PM의 실제 워크플로우는 "성분 파악"이 아니라 "ODM에 방향 전달". 성분 테이블은 thread 상세에 보존하되, 본문은 PM이 바로 쓸 수 있는 브리프 가이드로 제공. Gemini 역할을 "화학 해석"에서 "PM 언어 번역"으로 전환.

---

## YAGNI Review

### V1 In Scope

- [x] INCI 파싱 + enrichment 분석 — 핵심 분석 엔진 (내부, PM에게 노출 최소화)
- [x] **Gemini ODM 브리프 가이드 생성** — 원인 패턴 / 브리프 제안 / 피할 패턴 / 안전 조합
- [x] `/amz why {keyword}` 슬랙 커맨드 — 분석 인터페이스
- [x] `/amz why` (키워드 없이) discovery 모드 — 진입 장벽 제거
- [x] 결과 없음 시 유사 키워드 제안 — dead-end 방지
- [x] Slack 본문(브리프 가이드) + thread(성분 상세) 분리
- [x] Lazy cache (24h TTL) — 반복 조회 효율화
- [x] 전체 카테고리 크로스 분석

### Out of Scope

- 특정 카테고리 한정 분석 (`/amz why sticky in Serums`) — V2
- 성분 동의어 사전 — V2
- HTML 리포트 내 섹션 추가
- Voice + (긍정) 상관관계 분석
- `--share` 채널 공유 옵션 — V2

---

## 1. Overview

### 1.1 Purpose

아마존 제품의 전성분(INCI)과 소비자 부정 피드백(Voice -)의 통계적 상관관계를 분석하고, 그 결과를 **PM이 ODM 브리프에 바로 활용할 수 있는 제형 방향 가이드**로 변환하여 슬랙 커맨드로 제공한다. 성분 분석은 내부 엔진으로 동작하되, PM에게는 액셔너블한 인사이트만 전달한다.

### 1.2 Background

- 현재 `ingredients`(전성분)와 `voice_negative`(부정 키워드)가 제품별로 `amz_products` 테이블에 수집되어 있음
- 분석 가능 현황: 1,545개 제품 중 **410개가 양쪽 데이터 모두 보유**
  - 주요 카테고리: Eye Masks(57), Facial Serums(53), Hair Shampoo(51), Night Creams(49), Eye Treatment(41)
  - Voice 데이터 미수집 카테고리는 기존 리포트 파이프라인 실행 시 자동 채워짐
- Facial Serums 프로토타입: "sticky feeling"에 대해 유의미한 성분 상관관계 확인

### 1.3 Design Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| PM이 성분명을 모름 | Gemini가 성분 패턴을 PM 언어로 번역 | "hydrogenated lecithin" → "중량 유화제 계열" |
| PM이 성분을 ODM에 지시하지 않음 | 브리프 가이드 형태로 출력 | "저분자 보습 베이스, 경량 유화 시스템 요청" → 복붙 가능 |
| 키워드를 미리 알아야 진입 가능 | `/amz why` discovery 모드 추가 | PM이 어떤 Voice - 키워드가 있는지 모르면 못 씀 |
| 결과 없음 시 dead-end | 유사 키워드 제안 | 탐색 연속성 |
| Slack 메시지 너무 김 | 본문(브리프 가이드 4줄) + thread(성분 상세) | 본문만 봐도 행동 가능 |
| 반복 조회 비효율 | Lazy cache (24h TTL) | 기존 `cache.py` 패턴 재활용 |

---

## 2. Scope

### 2.1 In Scope

- [ ] INCI 전성분 텍스트 파싱 (쉼표 구분, 정규화, 괄호 처리)
- [ ] Voice - 키워드별 enrichment 분석 (with/without 빈도 비교, ratio 계산)
- [ ] 전체 카테고리 크로스 분석 (횡단)
- [ ] **Gemini ODM 브리프 가이드 생성** (원인 패턴 → 브리프 제안 → 피할 패턴 → 안전 조합)
- [ ] `/amz why {keyword}` 슬랙 커맨드 구현
- [ ] `/amz why` discovery 모드 — Voice - 키워드 빈도 Top 15 + Block Kit 버튼
- [ ] 결과 없음 시 유사 키워드 제안
- [ ] Slack 본문(브리프 가이드) + thread(성분 상세) 분리
- [ ] Lazy cache (MySQL, 24h TTL)

### 2.2 Out of Scope

- 카테고리 필터링 옵션 (`/amz why sticky in Serums`)
- 성분 동의어 사전 (retinol ↔ retinaldehyde 등)
- HTML 리포트 내 섹션 추가
- Voice + (긍정) 상관관계 분석
- `--share` 채널 공유 옵션

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | INCI 텍스트를 쉼표 기준으로 파싱, 소문자 정규화, 앞뒤 공백 제거 | High |
| FR-02 | 괄호 내 성분 처리: "water (aqua)" → "water" (괄호 내용은 alias로 보존 가능) | Medium |
| FR-03 | Voice - 키워드 fuzzy 매칭: "sticky"로 검색 시 "sticky feeling", "stickiness" 등 포함 | High |
| FR-04 | Enrichment 계산: with 그룹 / without 그룹 성분 빈도 비교, ratio = with% / without% | High |
| FR-05 | 필터 조건: 최소 3개 제품에서 발견, ratio > 2.0x | High |
| FR-06 | 전체 카테고리 크로스: 모든 활성 카테고리 제품을 대상으로 분석 | High |
| FR-07 | 카테고리별 그룹핑: 동일 성분이 여러 카테고리에서 과대표현 시 카테고리 목록 표시 (thread 상세) | Medium |
| **FR-08** | **Gemini ODM 브리프 가이드**: enrichment Top 10을 PM 언어로 변환. 4-part 출력: (1) 핵심 원인 패턴 1줄 (2) ODM 브리프 제안 1줄 (3) 피할 패턴 1줄 (4) 안전 조합 1줄 | **High** |
| FR-09 | Gemini 프롬프트: 성분의 기능적 분류(유화제, 보습제 등)로 묶어 설명. 개별 성분명 나열 지양. 할루시네이션 방지 지시 포함 | High |
| FR-10 | 안전 조합: 부정 키워드와 상관관계 없는 고빈도 성분을 기능 카테고리로 묶어 제시 | Medium |
| FR-11 | `/amz why {keyword}` 슬랙 커맨드 등록, ephemeral 즉시 응답 + background 분석 | High |
| FR-12 | **본문**: 브리프 가이드 4줄 (복붙 가능). **Thread**: 성분 상세 테이블 + Gemini 상세 해석 + 면책 문구 | High |
| FR-13 | "상관관계 ≠ 인과관계" 면책 문구 thread 하단 표시 | High |
| FR-14 | `/amz why` (키워드 없이): Voice - 키워드 빈도순 Top 15를 Block Kit 버튼으로 표시. 버튼 클릭 시 해당 키워드 분석 실행 | High |
| FR-15 | 결과 없음 시: 입력 키워드와 유사한 Voice - 키워드 Top 5를 제안 (contains 기반 매칭) | High |
| FR-16 | Lazy cache: 키워드별 분석 결과를 MySQL에 24시간 TTL로 캐시. 기존 `cache.py` 패턴 재활용 | Medium |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| Performance | 첫 조회: 전체 카테고리 분석 + Gemini 응답 포함 8초 이내. 캐시 히트 시 1초 이내 |
| Cost | Gemini Flash 1회 호출 ($0.001 이하), 캐시 히트 시 Gemini 호출 없음 |
| Reliability | INCI 데이터 없는 제품은 자동 제외, 분석 대상 수 명시 |

---

## 4. Architecture

### 4.1 File Layout

```
amz_researcher/
  services/
    ingredient_analyzer.py   ← NEW: INCI 파싱 + enrichment 분석
  router.py                  ← MOD: "why" subcommand + interact 핸들러 추가
  services/
    gemini.py                ← MOD: generate_odm_brief() 추가
    product_db.py            ← MOD: 전체 카테고리 제품 일괄 조회 + Voice 키워드 통계
    cache.py                 ← MOD: correlation 캐시 get/save 추가
```

### 4.2 Data Flow

```
[Flow A: Discovery 모드]
/amz why (키워드 없이)
    ↓
router.py: keyword 없음 감지
    ↓
product_db: get_voice_keyword_stats()
    → Voice - 키워드별 빈도 집계 (GROUP BY + COUNT)
    ↓
slack: Block Kit 버튼 메시지 반환
    → "분석할 키워드를 선택하세요" + 버튼 15개
    ↓
사용자 버튼 클릭 → /slack/amz/interact
    → action_id: "amz_why_{keyword}"
    → Flow B로 진입

[Flow B: 분석 모드]
/amz why sticky (또는 버튼 클릭)
    ↓
router.py: subcommand "why" + keyword 파싱
    ↓
[0] cache.py: get_correlation_cache(keyword)
    → HIT → 캐시 결과 반환 (skip 1-3)
    → MISS ↓
    ↓ (background task)
[1] product_db: get_all_products_with_voice()
    → ingredients + voice_negative 보유 제품 필터
    ↓
[2] ingredient_analyzer: enrichment 계산
    - parse_inci(raw) → list[str]
    - fuzzy keyword matching (contains)
    - 카테고리별 with/without 빈도 비교
    - ratio > 2.0x + min 3개 필터
    - Top 10 의심 성분 + 안전 성분 도출
    ↓
[3] gemini: generate_odm_brief()
    - enrichment Top 10 + 안전 성분 전달
    - "PM이 ODM에 전달할 브리프 가이드" 생성 요청
    - 성분을 기능 카테고리로 묶어 설명 지시
    - 4-part 구조: 핵심 원인 / 브리프 제안 / 피할 패턴 / 안전 조합
    ↓
[3.5] cache.py: save_correlation_cache(keyword, result) — 24h TTL
    ↓
[4] slack: 2단계 메시지 반환
    [본문] ODM 브리프 가이드 — 4줄 (복붙 가능)
    [thread] 성분 상세 — 테이블 + Gemini 상세 해석 + 면책 문구

[Flow C: 결과 없음]
분석 결과 없음 (표본 부족 or 매칭 키워드 없음)
    ↓
product_db: find_similar_voice_keywords(keyword)
    → contains 기반 유사 키워드 Top 5
    ↓
slack: "'{keyword}' 결과 없음. 유사 키워드:" + Block Kit 버튼
```

### 4.3 Key Functions

```python
# ingredient_analyzer.py (NEW)

def parse_inci(raw: str) -> list[str]:
    """INCI 전성분 텍스트를 성분 리스트로 파싱."""
    # 쉼표 구분, 소문자, trim, 괄호 처리

def analyze_voice_ingredient_correlation(
    products: list[dict],  # [{ingredients, voice_negative, category}]
    target_keyword: str,
    min_products: int = 3,
    min_ratio: float = 2.0,
) -> dict:
    """키워드별 성분 enrichment 분석. 내부 엔진."""
    # Returns: {enriched: [...], safe: [...], stats: {...}}

# product_db.py (MOD)

async def get_voice_keyword_stats(self) -> list[dict]:
    """Voice - 키워드 빈도 통계. [{keyword, count, categories}]"""

async def get_all_products_with_voice(self) -> list[dict]:
    """전체 활성 카테고리 제품의 ingredients + voice_negative 조회."""

async def find_similar_voice_keywords(self, keyword: str) -> list[str]:
    """contains 기반 유사 Voice - 키워드 검색. Top 5."""

# cache.py (MOD)

async def get_correlation_cache(self, keyword: str) -> dict | None:
    """24h TTL 기준 캐시 조회."""

async def save_correlation_cache(self, keyword: str, result: dict) -> None:
    """분석 결과 JSON 캐시 저장."""

# gemini.py (MOD)

async def generate_odm_brief(
    self, keyword: str, enriched: list[dict], safe: list[dict]
) -> dict:
    """Enrichment 결과를 PM용 ODM 브리프 가이드로 변환.

    Returns:
        {
            "cause": "고분자 보습제 + 중량 유화제 조합이 끈적임의 주 원인",
            "brief": "저분자 보습 베이스, 경량 유화 시스템 요청",
            "avoid": "고분자 HA + 레시틴 계열 유화제 동시 사용",
            "safe": "나이아신아마이드, 스쿠알란, 센텔라 베이스",
            "detail": "... (thread용 상세 해석)"
        }
    """

# router.py (MOD)

# /amz why → discovery (Block Kit 버튼)
# /amz why {keyword} → background task
# /slack/amz/interact action_id: "amz_why_{keyword}" → 분석 실행
```

### 4.4 Slack Output Format

**[본문 메시지 — ODM 브리프 가이드]**

```
🔬 *"sticky" — ODM 브리프 가이드*
12개 카테고리, 410개 제품 분석 (53개에서 "sticky" 발견)

💡 *핵심*: 고분자 보습제 + 중량 유화제 조합이 끈적임의 주 원인
📋 *브리프 제안*: "저분자 보습 베이스, 경량 유화 시스템 요청"
⚠️ *피할 패턴*: 고분자 HA + 레시틴 계열 유화제 동시 사용
✅ *안전 조합*: 나이아신아마이드, 스쿠알란, 센텔라 베이스

_🧵 성분 상세 분석은 thread 참조_
```

**[thread — 성분 상세 (선택적 열람)]**

```
═══ "sticky" 성분 상관관계 상세 ═══

| 성분 | 기능 분류 | Ratio | 제품수 | 카테고리 |
|------|----------|-------|--------|---------|
| potassium hyaluronate | 고분자 보습제 | 15.3x | 19 | Serums |
| hydrogenated lecithin | 유화제 | 9.5x | 24 | Serums |
| carbomer | 점증제 | 3.5x | 22 | Creams, Serums |
| acrylates copolymer | 피막형성제 | 4.2x | 18 | Moisturizers |
| peg-100 stearate | 유화제 | 3.1x | 15 | Creams |
...

═══ 상세 해석 ═══

> 고분자 히알루론산(potassium hyaluronate)은 수분 보유력이
> 높아 피부 표면에 점성 막을 형성합니다.
> hydrogenated lecithin은 유화 안정제로, 높은 농도에서
> 무거운 텍스처를 만들 수 있습니다.
> 이 두 계열의 동시 사용이 끈적임의 주요 패턴입니다.

═══ 안전 성분 (sticky 무관) ═══

niacinamide (활성), squalane (유연제), centella asiatica (진정),
tea tree oil (항균), vitamin e (항산화)

_⚠️ 상관관계 ≠ 인과관계. 제형 결정 시 참고용._
_📅 캐시: 2026-03-13 14:30 · 24시간 후 갱신_
```

**[Discovery 모드 — /amz why]**

```
🔬 *Voice(-) 키워드 분석*
12개 카테고리, 410개 제품 기준

분석할 키워드를 선택하세요:

[sticky (53)] [greasy (41)] [burning (38)] [breakout (35)]
[drying (29)] [irritation (27)] [pilling (24)] [smell (21)]
[heavy (19)] [oily (17)] [redness (15)] [flaking (12)]
...

또는 `/amz why {keyword}` 로 직접 검색
```

### 4.5 Gemini Prompt Design

```
너는 화장품 제형 전문가이다. 아래 데이터를 기반으로
제품 기획자(PM)가 ODM에 전달할 브리프 가이드를 작성하라.

PM은 성분 전문가가 아니다. 개별 성분명(INCI) 대신
기능적 분류(고분자 보습제, 경량 유화제, 점증제 등)로
묶어서 설명하라.

## 입력 데이터
키워드: "{keyword}"
의심 성분 (enrichment ratio 높은 순):
{enriched_list}

안전 성분 (해당 키워드와 무관):
{safe_list}

## 출력 형식 (각 항목 1줄, 한국어)
1. 핵심: [이 키워드의 주 원인 패턴 — 기능 분류로]
2. 브리프 제안: [ODM에 전달할 제형 방향 — 복붙 가능한 톤]
3. 피할 패턴: [회피해야 할 성분 조합 — 기능 분류로]
4. 안전 조합: [사용해도 안전한 성분 베이스 — 기능 분류로]

## 규칙
- 확실하지 않으면 언급하지 마라
- 추측이나 일반론 금지, 데이터에 근거한 해석만
- 성분의 기능 분류가 불분명하면 "미분류"로 표기
```

---

## 5. Implementation Order

```
Phase 1: ingredient_analyzer.py 신규 작성        [핵심 엔진]
  - parse_inci() 함수
  - analyze_voice_ingredient_correlation() 함수
  - 단위 테스트: Facial Serums "sticky" 데이터로 검증

Phase 2: product_db.py 수정                     [데이터 조회]
  - get_all_products_with_voice() 함수 추가
  - get_voice_keyword_stats() 함수 추가 (discovery 모드용)
  - find_similar_voice_keywords() 함수 추가 (결과 없음 대응)

Phase 3: cache.py 수정                          [캐시 레이어]
  - get_correlation_cache() / save_correlation_cache() 추가
  - 기존 amz_market_report_cache 패턴 따름, TTL 24h

Phase 4: gemini.py 수정                         [브리프 생성]
  - generate_odm_brief() 함수 추가
  - 프롬프트 설계 (기능 분류 기반, 할루시네이션 방지)

Phase 5: router.py 수정                         [슬랙 연동]
  - "why" subcommand 파싱 (키워드 유/무 분기)
  - discovery 모드: Block Kit 버튼 메시지
  - 분석 모드: background task + 본문(브리프)/thread(상세) 분리
  - interact 핸들러: "amz_why_{keyword}" action 처리
  - 결과 없음: 유사 키워드 제안 + Block Kit 버튼

Phase 6: 통합 테스트                            [E2E 검증]
  - /amz why (discovery) → 버튼 표시 확인
  - /amz why sticky → 브리프 가이드 + thread 상세 확인
  - /amz why xyzabc → 결과 없음 + 유사 키워드 제안 확인
  - 브리프 가이드가 PM 언어인지 (성분명 아닌 기능 분류) 확인
  - 캐시 히트/미스 시나리오 확인
```

---

## 6. Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gemini 기능 분류 오류 (성분→기능 매핑) | High | 프롬프트에 "불분명하면 미분류" 지시 + 프로토타입 검증 |
| Gemini 할루시네이션 (근거 없는 인과 주장) | High | "확실하지 않으면 언급하지 마라" + thread에 원본 데이터 병기 |
| INCI 파싱 품질 (비표준 구분자) | Medium | 세미콜론/슬래시도 fallback 구분자로 처리 |
| 표본 크기 부족 (키워드별 3-5개) | Medium | min_products 필터 + "표본 N개" 명시 |
| Brand confounding | Medium | V1은 면책 문구로 대응, V2에서 brand 보정 |
| 사용자가 키워드를 모름 | High | discovery 모드로 해결 |
| 브리프 가이드 품질 편차 | Medium | 프롬프트 고정 + 출력 형식 강제 + 캐시로 일관성 유지 |

---

## 7. Brainstorming Log

| Phase | Decision | Rationale |
|-------|----------|-----------|
| Phase 1 | Core Problem = 제형 설계 인사이트 | PM이 성분 선정 시 데이터 근거 필요 |
| Phase 1 | Target = PM | 슬랙에서 빠른 조회, 기획서 반영 |
| Phase 1 | UX = `/amz why {keyword}` | 전체 카테고리 크로스 분석이 더 유용 |
| Phase 2 | 실시간 + Gemini (Approach C) | 숫자만으로는 부족, 해석이 핵심 가치 |
| UX Review | Discovery 모드 추가 | 키워드를 몰라야 정상 — 진입 장벽 제거 |
| UX Review | 요약/상세 분리 | Slack 메시지 길면 안 읽힘 |
| UX Review | Lazy cache 채택 | 기존 cache.py 패턴 재활용 |
| UX Review | 결과 없음 → 유사 키워드 제안 | dead-end 방지 |
| **Pivot** | **성분 중심 → ODM 브리프 가이드 중심** | PM은 성분 전문가가 아님. 실제 행동은 "ODM에 방향 전달". 성분 테이블은 thread 상세로 보존하되 본문은 즉시 행동 가능한 가이드로 |
| **Pivot** | **Gemini 역할: 화학 해석 → PM 언어 번역** | 개별 성분명 대신 기능 분류(고분자 보습제, 경량 유화제)로 묶어 설명 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-12 | Initial draft via Plan Plus | Plan Plus |
| 0.2 | 2026-03-12 | UX 개선: discovery 모드, 요약/thread 분리, lazy cache, 유사 키워드 제안 | UX Review |
| 0.3 | 2026-03-13 | **Pivot: 성분 중심 → ODM 브리프 가이드 중심.** Gemini 역할 전환, Slack 출력 재설계, 프롬프트 설계 추가 | Product Review |
