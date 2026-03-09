# HTML Insight Report Planning Document

> **Summary**: Excel 리포트를 인터랙티브 HTML 리포트로 전환하여 시각화 및 UX 개선
>
> **Project**: amz_researcher
> **Author**: CTO
> **Date**: 2026-03-09
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 12시트 Excel 파일로 전달되는 Amazon 시장 분석 결과를 단일 HTML 파일(인라인 CSS/JS)로 전환한다. 사용자는 Slack에서 파일을 다운로드하여 브라우저에서 열면 인터랙티브 차트, 탭 네비게이션, 필터링이 가능한 리포트를 확인할 수 있다.

### 1.2 Background

- Excel은 모바일에서 열기 어렵고, 차트가 없어 데이터 해석에 시간이 걸림
- 현재 Block Kit 요약(Top 5 성분)은 정보량이 제한적
- 시장 분석 데이터(`analysis_data` dict)가 이미 구조화되어 있어 시각화 진입장벽이 낮음
- Jinja2가 이미 의존성에 포함되어 있어 템플릿 렌더링 인프라 준비 완료

### 1.3 Related Documents

- `docs/01-plan/features/amazon-researcher-v5.plan.md` (현재 12시트 구조 정의)
- `docs/01-plan/features/excel-report-v6.plan.md` (키워드 검색 9시트)

---

## 2. Scope

### 2.1 In Scope

- [x] 단일 HTML 파일 생성기 (`html_builder.py`) 구현
- [x] Chart.js 기반 인터랙티브 차트 (인라인 CDN 또는 base64 임베딩)
- [x] 12개 탭 네비게이션 (기존 Excel 시트 1:1 매핑)
- [x] 키워드 검색용 9탭 변형 지원
- [x] Slack 파일 업로드 (`.html` 파일)
- [x] Jinja2 템플릿 기반 렌더링
- [x] 기존 `build_excel()` / `build_keyword_excel()` 유지 (optional raw data export)

### 2.2 Out of Scope

- 호스팅 페이지 (URL 공유 방식) -- 향후 고려
- PDF 변환
- 실시간 데이터 업데이트
- 사용자 인증/접근 제어

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 단일 self-contained HTML 파일 생성 (외부 의존성 없이 브라우저에서 작동) | High | Pending |
| FR-02 | 12개 탭 네비게이션 (Market Insight ~ Raw Product Detail) | High | Pending |
| FR-03 | Chart.js 차트: 가격대별 성분 분포, BSR 분석, 브랜드 포지셔닝 스캐터, 판매량 바 차트 | High | Pending |
| FR-04 | 테이블 정렬/필터 (Product Detail, Ingredient Ranking) | Medium | Pending |
| FR-05 | 키워드 검색용 9탭 변형 (`build_keyword_html()`) | High | Pending |
| FR-06 | Slack 업로드 시 `.html` 파일로 전달 | High | Pending |
| FR-07 | Market Insight 탭: Gemini 마크다운 리포트를 HTML 렌더링 | High | Pending |
| FR-08 | 반응형 디자인 (모바일 뷰 기본 지원) | Medium | Pending |
| FR-09 | 다크/라이트 모드 토글 | Low | Pending |
| FR-10 | Excel 다운로드 버튼 (기존 Excel은 별도 업로드로 유지) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | HTML 파일 크기 < 2MB (50개 제품 기준) | 파일 크기 측정 |
| Performance | 생성 시간 < 3초 (Jinja2 렌더링) | 로그 타이밍 |
| Compatibility | Chrome, Safari, Firefox 최신 2버전 | 수동 테스트 |
| Accessibility | 테이블 시맨틱 HTML, aria-label 차트 | 코드 리뷰 |

---

## 4. Architecture Decision

### 4.1 Single HTML File vs Hosted Page

| Option | Pros | Cons | Recommendation |
|--------|------|------|:--------------:|
| **Single HTML (inline all)** | Slack 파일 업로드 그대로 사용, 오프라인 열기 가능, 인프라 불필요 | 파일 크기 증가 (Chart.js ~200KB gzip), CDN 의존 시 오프라인 불가 | **Selected** |
| Hosted Page (S3 + presigned URL) | 무한 확장, 실시간 업데이트 가능 | S3 인프라 필요, URL 만료 관리, 추가 비용 | Phase 2 고려 |
| Hybrid (hosted + offline fallback) | 양쪽 장점 | 복잡도 높음 | Not now |

**결정**: Single HTML 파일. Chart.js는 CDN `<script>` 태그로 포함하되, `integrity` 속성으로 보안 보장. 오프라인 사용이 필수가 아니므로 CDN 방식 채택 (파일 크기 절약).

### 4.2 Chart.js vs Alternatives

| Library | Size (min+gzip) | Self-contained | License | Recommendation |
|---------|:---------------:|:--------------:|---------|:--------------:|
| **Chart.js 4.x** | ~67KB | CDN OK | MIT | **Selected** |
| ECharts | ~300KB | 무거움 | Apache 2.0 | Too heavy |
| Plotly.js | ~1MB | 매우 무거움 | MIT | Too heavy |
| Lightweight SVG (D3 subset) | ~30KB | 직접 구현 필요 | BSD | 개발 비용 높음 |

**결정**: Chart.js 4.x CDN. 가볍고, 반응형 기본 지원, 풍부한 차트 타입.

### 4.3 Jinja2 Template Approach

```
amz_researcher/
  templates/
    report/
      base.html.j2          # HTML skeleton, CSS, JS, tab nav
      tabs/
        market_insight.html.j2
        consumer_voice.html.j2
        badge_analysis.html.j2
        sales_pricing.html.j2
        brand_positioning.html.j2
        marketing_keywords.html.j2
        ingredient_ranking.html.j2
        category_summary.html.j2
        rising_products.html.j2
        product_detail.html.j2
        raw_search.html.j2
        raw_detail.html.j2
  services/
    html_builder.py          # build_html(), build_keyword_html()
```

- `base.html.j2`: Chart.js CDN script, 공통 CSS (변수 기반 다크모드), 탭 네비게이션 JS
- 각 탭 파일: 해당 시트의 테이블 + 차트를 Jinja2 매크로로 구성
- `html_builder.py`: `build_excel()`과 동일한 시그니처, `analysis_data` dict를 Jinja2 context로 직접 전달

### 4.4 Data Layer Strategy: `build_excel()` 유지 vs Shared Data Layer

| Option | Pros | Cons | Recommendation |
|--------|------|------|:--------------:|
| **Keep `build_excel()` as-is, add `build_html()` parallel** | 최소 변경, 기존 안정성 유지, 독립 배포 가능 | 두 빌더 간 데이터 전처리 중복 | **Phase 1** |
| Shared data layer (ReportData dataclass) | DRY, 포맷 추가 쉬움 | 리팩토링 범위 넓음, 기존 코드 변경 위험 | Phase 2 |

**결정**: Phase 1에서는 `build_html()`을 `build_excel()`과 병렬로 추가한다. 두 함수는 동일한 `analysis_data` dict을 입력으로 받으므로 데이터 중복은 최소화된다. `build_excel()`의 openpyxl 특화 전처리(스타일, 셀 포맷)는 HTML에 불필요하므로 공유할 코드가 실제로 적다.

Phase 2에서 `ReportData` dataclass로 통합 리팩토링을 검토한다.

---

## 5. Integration Strategy

### 5.1 Orchestrator 변경

`orchestrator.py`의 `run_analysis()` / `run_keyword_analysis_pipeline()` 흐름:

```
현재:
  Step 5: build_excel() -> excel_bytes
  Step 7: upload_file(excel_bytes, "*.xlsx")

변경:
  Step 5a: build_html() -> html_bytes    # NEW (primary)
  Step 5b: build_excel() -> excel_bytes  # 유지 (secondary)
  Step 7a: upload_file(html_bytes, "*.html", comment="Interactive Report")  # NEW
  Step 7b: upload_file(excel_bytes, "*.xlsx", comment="Raw Data Excel")     # 유지
```

- HTML이 primary report, Excel은 raw data backup
- Block Kit 메시지의 context 텍스트를 "HTML 리포트 참조"로 업데이트

### 5.2 SlackSender 변경

`upload_file()`은 파일 확장자에 무관하게 동작하므로 변경 불필요. `.html` 파일도 Slack files API로 정상 업로드된다.

### 5.3 Tab-to-Chart Mapping

| Tab | Primary Chart | Chart Type | Data Source (analysis_data key) |
|-----|---------------|------------|--------------------------------|
| Market Insight | -- (마크다운 렌더링) | -- | `market_report` (str) |
| Consumer Voice | Positive/Negative 키워드 빈도 | Horizontal Bar | `customer_voice` |
| Badge Analysis | Badge vs No-Badge 비교 | Grouped Bar | `badges` |
| Sales & Pricing | 가격대별 판매량, SNS 채택률 | Stacked Bar + Doughnut | `sales_volume`, `sns_pricing` |
| Brand Positioning | 가격 vs BSR 스캐터 | Scatter | `brand_positioning` |
| Marketing Keywords | 키워드별 BSR 성과 | Horizontal Bar | `title_keywords` |
| Ingredient Ranking | Top 20 성분 가중치 | Horizontal Bar | `rankings` (list) |
| Category Summary | 카테고리 파이 차트 | Pie/Doughnut | `categories` (list) |
| Rising Products | -- (테이블 only) | -- | `rising_products` |
| Product Detail | -- (sortable table) | -- | `weighted_products` (list) |
| Raw Search | -- (table) | -- | `search_products` (list) |
| Raw Detail | -- (table) | -- | `details` (list) |

---

## 6. Implementation Phases

### Phase 1: Core HTML Report (MVP)

**목표**: 기본 탭 네비게이션 + 주요 5개 탭 차트 + Product Detail 정렬 테이블

| Task | Files | Effort |
|------|-------|--------|
| Jinja2 base template + CSS + tab JS | `templates/report/base.html.j2` | 1일 |
| Ingredient Ranking 탭 (bar chart) | `tabs/ingredient_ranking.html.j2` | 0.5일 |
| Sales & Pricing 탭 (stacked bar) | `tabs/sales_pricing.html.j2` | 0.5일 |
| Brand Positioning 탭 (scatter) | `tabs/brand_positioning.html.j2` | 0.5일 |
| Market Insight 탭 (마크다운 HTML 변환) | `tabs/market_insight.html.j2` | 0.5일 |
| Product Detail 탭 (sortable table) | `tabs/product_detail.html.j2` | 0.5일 |
| `html_builder.py` + orchestrator 연동 | `services/html_builder.py`, `orchestrator.py` | 0.5일 |
| 나머지 7개 탭 (테이블 위주) | `tabs/*.html.j2` | 1일 |

**소계**: ~5일

### Phase 2: Polish + Keyword Variant

| Task | Files | Effort |
|------|-------|--------|
| `build_keyword_html()` 9탭 변형 | `html_builder.py` | 0.5일 |
| Consumer Voice 감성 차트 | `tabs/consumer_voice.html.j2` | 0.5일 |
| Badge Analysis 비교 차트 | `tabs/badge_analysis.html.j2` | 0.5일 |
| 다크모드 CSS 변수 | `base.html.j2` | 0.5일 |
| 테이블 검색/필터 JS | `base.html.j2` (공통 JS) | 0.5일 |

**소계**: ~2.5일

### Phase 3: Shared Data Layer (Optional Refactoring)

| Task | Files | Effort |
|------|-------|--------|
| `ReportData` dataclass 정의 | `models.py` | 0.5일 |
| `build_report_data()` 함수 추출 | `services/report_data.py` | 1일 |
| `build_excel()` 리팩토링 | `excel_builder.py` | 1일 |
| `build_html()` 리팩토링 | `html_builder.py` | 0.5일 |

**소계**: ~3일 (필요 시)

---

## 7. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| HTML 파일 크기 2MB 초과 (대량 제품) | Medium | Low | Product Detail 100행 제한 + "show more" JS 토글 |
| Chart.js CDN 다운 시 차트 미표시 | Low | Low | `<noscript>` fallback 테이블, CDN fallback URL |
| Slack에서 .html 미리보기 불가 | Low | High | 이미 .xlsx도 미리보기 불가, 다운로드 후 열기 UX 동일 |
| Jinja2 템플릿 유지보수 복잡도 | Medium | Medium | 매크로로 반복 패턴 추출, 탭별 파일 분리 |
| Market Insight 마크다운 렌더링 품질 | Low | Medium | `markdown` 라이브러리로 서버사이드 변환 또는 JS marked.js CDN |
| `build_excel()` 대비 데이터 불일치 | Medium | Low | 동일 `analysis_data` 입력 사용, 통합 테스트로 검증 |

---

## 8. Success Criteria

### 8.1 Definition of Done

- [x] `build_html()` 함수가 self-contained HTML bytes를 반환
- [x] 12탭(카테고리) / 9탭(키워드) 네비게이션 정상 작동
- [x] 최소 5개 탭에 Chart.js 인터랙티브 차트 포함
- [x] Product Detail 테이블 컬럼 정렬 가능
- [x] Slack 파일 업로드 후 브라우저에서 정상 렌더링
- [x] 기존 Excel 기능 regression 없음

### 8.2 Quality Criteria

- [x] HTML 파일 크기 < 2MB (50개 제품 기준)
- [x] Chrome/Safari/Firefox 렌더링 정상
- [x] Jinja2 렌더링 < 3초

---

## User Stories

### US-01: 카테고리 분석 HTML 수신

> **As a** Slack 사용자,
> **I want to** `/amz collagen` → 카테고리 선택 후 HTML 파일을 받고 싶다,
> **So that** 브라우저에서 즉시 열어 차트와 테이블로 시장 인사이트를 확인할 수 있다.

**Acceptance Criteria**:
- 분석 완료 후 Slack에 `.html` 파일이 첨부된다
- HTML 파일은 별도 서버 없이 브라우저에서 열린다
- 12개 탭 네비게이션이 모두 정상 렌더링된다

### US-02: 키워드 검색 HTML 수신

> **As a** Slack 사용자,
> **I want to** `/amz search collagen peptide` 결과를 HTML로 받고 싶다,
> **So that** 키워드 분석(9 탭)도 동일한 대시보드 형식으로 탐색할 수 있다.

**Acceptance Criteria**:
- 키워드 검색 결과에도 HTML 파일이 생성된다
- 9탭 변형이 카테고리 분석의 12탭과 별도로 올바르게 렌더링된다
- 데이터가 없는 섹션은 에러 없이 숨겨진다

### US-03: 차트로 트렌드 파악

> **As a** 마케팅 담당자,
> **I want to** 성분 랭킹, 가격 분포, 브랜드 포지셔닝을 차트로 보고 싶다,
> **So that** Excel 수식 없이 주요 트렌드를 한눈에 파악하고 보고서에 활용할 수 있다.

**Acceptance Criteria**:
- 성분 랭킹 가로 바 차트가 상위 20개 성분을 표시한다
- 가격대별 판매량 차트가 표시된다
- 브랜드 포지셔닝 산점도가 가격 vs BSR 축으로 표시된다

### US-04: 상품 테이블 필터 및 정렬

> **As a** 분석가,
> **I want to** 상품 목록 테이블에서 텍스트 필터와 컬럼 정렬을 사용하고 싶다,
> **So that** 관심 있는 경쟁 상품을 빠르게 좁혀볼 수 있다.

**Acceptance Criteria**:
- 텍스트 입력으로 상품명·브랜드 실시간 필터가 동작한다
- 컬럼 헤더 클릭으로 오름차순/내림차순 정렬이 토글된다
- 100개 초과 행은 "더 보기" 버튼으로 표시한다

### US-05: 모바일에서 요약 확인

> **As a** 이해관계자,
> **I want to** 스마트폰에서 HTML 파일을 열어 핵심 지표를 보고 싶다,
> **So that** 이동 중에도 분석 결과를 빠르게 확인할 수 있다.

**Acceptance Criteria**:
- 375px 이상 뷰포트에서 레이아웃이 깨지지 않는다
- 탭 내비게이션이 모바일에서 스크롤 가능하다
- 차트가 화면 너비에 맞게 자동 조정된다

---

## MoSCoW Prioritization

| 우선순위 | 기능 | 이유 |
|----------|------|------|
| **Must** | `html_builder.py` — analysis_data → HTML 변환 | 핵심 딜리버리 |
| **Must** | 카테고리 분석 12탭 렌더링 | 기본 사용 케이스 |
| **Must** | 키워드 검색 9탭 변형 | 두 번째 주요 사용 케이스 |
| **Must** | 탭 내비게이션 JS | 12탭 탐색 필수 |
| **Must** | self-contained HTML (인라인 CSS/JS) | 오프라인/방화벽 환경 대응 |
| **Must** | Slack 파이프라인 연결 (HTML 파일 전송) | 사용자 경험 연속성 |
| **Must** | analysis_data 키 누락 시 graceful 생략 | 데이터 부족 케이스 안정성 |
| **Should** | 성분 랭킹 바 차트 | 가장 자주 보는 데이터 |
| **Should** | 가격대별 분포 차트 | 의사결정 핵심 지표 |
| **Should** | 브랜드 포지셔닝 산점도 | 차별화 인사이트 |
| **Should** | 상품 테이블 텍스트 필터 + 정렬 | 분석가 작업 효율 |
| **Should** | 반응형 모바일 레이아웃 | 이해관계자 공유 시나리오 |
| **Could** | 다크모드 토글 | 사용자 편의 |
| **Could** | Market Insight 마크다운 HTML 렌더링 | 가독성 향상 |
| **Could** | 테이블 CSV 다운로드 버튼 | 데이터 수출 대안 |
| **Won't** | 실시간 데이터 갱신 | 정적 스냅샷으로 충분 |
| **Won't** | 퍼블릭 URL 호스팅 | 인프라 범위 초과 |
| **Won't** | PDF 내보내기 | 브라우저 인쇄로 대체 가능 |

---

## Migration Strategy (Excel → HTML)

### Phase 1 — v1: 병행 제공 (현재 계획)

- Slack에 HTML(primary) + Excel(secondary) 모두 전송
- Excel을 "Raw Data" 레이블로 위치 재정의
- 사용자 피드백 수집 기간 (2-4주)

### Phase 2 — v2 (조건부): HTML 기본, Excel 옵션

- 기본 첨부 파일을 HTML로 변경
- Excel은 사용자 명시 요청 시에만 전송 (`/amz collagen --excel` 플래그 검토)
- 진행 조건: 사용자 피드백에서 "Excel 필요" 비율 < 20%

### Phase 3 — v3 (미래): HTML 단독

- `build_excel()` 파이프라인 제거 (유지보수 부담 해소)
- HTML 내 테이블별 CSV 다운로드 버튼으로 원시 데이터 수출 지원
- 진행 조건: Phase 2 안정화 + 팀 합의

---

## Success Metrics

| 지표 | 기준 | 측정 방법 |
|------|------|----------|
| HTML 생성 성공률 | >= 99% (분석 데이터 정상 시) | 에러 로그 모니터링 |
| 파일 크기 | < 2MB (50 상품 기준) | 파일 시스템 측정 |
| 생성 시간 | < 3초 (Jinja2 렌더링 단독) | 로컬 타이밍 테스트 |
| 브라우저 호환성 | Chrome/Safari/Firefox 렌더링 정상 | 수동 크로스브라우저 확인 |
| 사용자 채택 | "HTML이 Excel보다 유용" 비율 > 70% | 슬랙 피드백 또는 간단한 설문 |
| 공유 사이클 단축 | 이해관계자 공유 시 추가 가공 불필요 비율 > 80% | 정성 피드백 |

---

## 9. Next Steps

1. [ ] Design document 작성 (`html-insight-report.design.md`)
2. [ ] Jinja2 base template 프로토타입
3. [ ] Chart.js 차트 프로토타입 (1개 탭)
4. [ ] orchestrator 연동 구현

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-09 | Initial draft | CTO |
