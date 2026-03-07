# Plan: Amazon Researcher V3 — 성분 정규화 + 시장 분석 리포트

## 1. Overview

V2(데이터 구조 + MySQL 캐시) 위에 **성분명 정규화**, **AI 시장 분석**, **Excel 고도화**를 추가한다.
Gemini가 INCI 학명과 마케팅용 일반명을 동시에 추출하고, 수집된 데이터로 8개 섹션의 시장 분석 리포트를 자동 생성한다.

## 2. Problem Statement

### V2 이후 발견된 문제

1. **성분명 분산**: 같은 성분이 INCI 학명/일반명/오타/대소문자 등 다양한 형태로 추출되어 랭킹에서 분리됨 (예: Rosemary 4개 변형 → 각각 3~4개 제품으로 Top10 진입 실패, 합산 시 12개)
2. **시장 인사이트 부재**: 성분 랭킹만 제공하고, 가격대별/BSR별/브랜드별 전략적 분석이 없음
3. **Gemini 속도**: 순차 배치 처리로 6배치 기준 ~5분 소요
4. **Gemini JSON 잘림**: 배치 크기 대비 출력 토큰 부족으로 파싱 실패

## 3. 변경사항 요약

| # | 항목 | AS-IS (V2) | TO-BE (V3) |
|---|------|------------|------------|
| 1 | 성분 모델 | `name`, `category` | `name`(INCI) + `common_name`(일반명) + `category` |
| 2 | 성분 정규화 | 수동 동의어 맵 | Gemini 프롬프트 기반 + DB 다수결 harmonize |
| 3 | Gemini 입력 | `ingredients_raw`, `features`, `additional_details` | + `title` 추가 |
| 4 | Gemini 처리 | 순차 배치 | `asyncio.gather` 병렬 배치 |
| 5 | Gemini 토큰 | 16384 | 32768 (성분 추출), 16384 (시장 리포트) |
| 6 | 시장 분석 | 없음 | 8개 섹션 데이터 생성 + AI 리포트 |
| 7 | Excel 시트 | 5개 | 9개 (Market Insight, Rising Products, Form x Price, Analysis Data 추가) |
| 8 | 실패 ASIN | 매번 재시도 | `amz_failed_asins` 테이블로 스킵 |
| 9 | Slack 전송 | `response_url` 필수 | `channel_id` fallback (`chat.postMessage`) |

## 4. 성분 정규화 전략

### 4.1 Gemini 프롬프트 강화

- `name`: INCI 전성분 원본 그대로 (예: `Argania Spinosa Kernel Oil`)
- `common_name`: 마케팅용 일반명 (예: `Argan Oil`)
- 규칙: 같은 식물/성분이면 부위(Leaf, Seed, Fruit) 무관하게 동일 `common_name`
- 형태(Extract, Oil)만 구분

### 4.2 DB 다수결 harmonize

캐시 저장 후 `harmonize_common_names()` 실행:
- 같은 `ingredient_name`에 여러 `common_name`이 있으면 → 최다 빈도 선택
- 동수 시 → 먼저 수집된(earliest `extracted_at`) 것 우선
- `amz_ingredient_cache` 테이블 UPDATE

## 5. 시장 분석 구조

### 5.1 데이터 생성 (`market_analyzer.py`)

| 분석 함수 | 설명 |
|-----------|------|
| `analyze_by_price_tier` | 가격대별(Budget/Mid/Premium/Luxury) 주요 성분 Top 5 |
| `analyze_by_bsr` | BSR 상위 20% vs 하위 20% 성분 비교 |
| `analyze_by_brand` | 브랜드별 핵심 성분 프로파일 |
| `analyze_cooccurrence` | 자주 함께 쓰이는 성분 쌍 |
| `analyze_form_by_price` | 제형 x 가격대 매트릭스 |
| `analyze_brand_positioning` | 브랜드 가격 vs BSR 포지셔닝 |
| `detect_rising_products` | 리뷰 적지만 BSR 우수한 급성장 제품 |
| `analyze_rating_ingredients` | 고평점(4.5+) vs 저평점(<4.3) 전용 성분 |

### 5.2 AI 리포트 (`gemini.generate_market_report`)

8개 분석 데이터를 Gemini에 전달하여 마크다운 리포트 생성:
1. 시장 요약
2. 가격대별 성분 전략
3. 제형 트렌드
4. 승리 공식
5. 경쟁 환경
6. 급성장 제품
7. 액션 아이템
8. 리스크

### 5.3 캐시

`amz_market_report_cache` 테이블: keyword + product_count 기준 캐시

## 6. Excel 시트 구성 (V3)

| 순서 | 시트명 | 설명 |
|------|--------|------|
| 1 | Market Insight | AI 시장 분석 리포트 (단일 셀, Notion 복붙 지원) |
| 2 | Ingredient Ranking | 성분 가중치 랭킹 |
| 3 | Category Summary | 성분 카테고리별 요약 |
| 4 | Product Detail | 제품별 가중치 + 성분 |
| 5 | Rising Products | 급성장 제품 목록 |
| 6 | Form x Price | 제형별 성과 + 가격대 매트릭스 |
| 7 | Raw - Search Results | 검색 원본 데이터 |
| 8 | Raw - Product Detail | 상세 원본 데이터 |
| 9 | Analysis Data | Gemini에 전달한 분석 원본 JSON |

## 7. 영향 받는 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `models.py` | 수정 | `Ingredient.common_name` 필드 추가 |
| `services/gemini.py` | 수정 | 프롬프트 강화, 병렬 배치, 시장 리포트 생성 |
| `services/cache.py` | 수정 | `common_name` 컬럼, `harmonize_common_names()`, 시장 리포트/실패 ASIN 캐시 |
| `services/analyzer.py` | 수정 | `_get_display_name()` (common_name 우선 표시) |
| `services/market_analyzer.py` | 신규 | 8개 시장 분석 함수 |
| `services/excel_builder.py` | 수정 | 4개 시트 추가, Market Insight 첫 시트 |
| `services/slack_sender.py` | 수정 | `channel_id` fallback |
| `orchestrator.py` | 수정 | 시장 분석 파이프라인, `analysis_data` 전달 |

## 8. DB 변경

```sql
ALTER TABLE amz_ingredient_cache ADD COLUMN common_name VARCHAR(255) DEFAULT '';

CREATE TABLE amz_failed_asins (
    asin VARCHAR(20) PRIMARY KEY,
    keyword VARCHAR(200),
    failed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE amz_market_report_cache (
    keyword VARCHAR(200) NOT NULL,
    product_count INT NOT NULL,
    report LONGTEXT,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_keyword (keyword)
);
```

## 9. Success Criteria

- [x] 같은 성분이 다른 이름으로 분산되지 않고 하나로 합산
- [x] Gemini 배치 병렬 처리로 처리 시간 50% 이상 단축
- [x] 시장 분석 리포트가 Excel 첫 시트에 포함
- [x] Analysis Data 시트에서 AI에 전달된 원본 데이터 확인 가능
- [x] Rising Products 시트에서 급성장 제품 즉시 파악
- [x] 실패한 ASIN 재시도 방지로 크레딧 절약
