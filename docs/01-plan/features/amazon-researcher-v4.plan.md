# Plan: Amazon Researcher V4 — Bright Data 전환 + 데이터 파이프라인

## 1. Overview

Browse.ai 실시간 크롤링을 **Bright Data Web Scraper API** 기반 주간 배치 수집으로 전환한다.
Beauty & Personal Care 카테고리 BSR Top 100 제품을 정기 수집하여 DB에 적재하고,
사용자 요청 시 DB 조회 → Gemini 분석 → Excel/Slack 응답으로 **대기 시간을 5~10분에서 수초로 단축**한다.

## 2. Problem Statement

### V3까지의 문제

1. **Browse.ai 불안정**: timeout, blocked, 섹션 뒤섞김(~26%) 등 크롤링 실패 빈번
2. **실시간 크롤링 대기**: 사용자 요청 → Browse.ai 크롤링 → 5~10분 대기
3. **가비지 데이터**: 키워드 검색 기반이라 스폰서/무관 제품 포함
4. **비용 비효율**: 같은 키워드 반복 요청 시 매번 Browse.ai 크레딧 소모
5. **트렌드 분석 불가**: 스냅샷 데이터만 있어 BSR/가격 변동 추적 불가

## 3. 변경사항 요약

| # | 항목 | AS-IS (V3) | TO-BE (V4) |
|---|------|------------|------------|
| 1 | 데이터 소스 | Browse.ai (실시간 크롤링) | Bright Data Web Scraper API (주간 배치) |
| 2 | 수집 트리거 | 사용자 요청 시 | 주 1회 cron job |
| 3 | 데이터 기준 | 키워드 검색 결과 | BSR Top 100 (카테고리별) |
| 4 | 응답 시간 | 5~10분 | 수초~1분 (DB 조회 + Gemini만) |
| 5 | 데이터 저장 | 캐시 (최신만) | 히스토리 (시계열 추적) |
| 6 | 카테고리 선택 | 키워드 자유 입력 | Slack 버튼/드롭다운으로 선택 |
| 7 | Browse.ai 의존 | 전체 파이프라인 | 완전 제거 |

## 4. 아키텍처

### 4.1 데이터 수집 파이프라인 (주 1회)

```
[Cron Job: 주 1회]
  → Bright Data API: discover_by=best_sellers_url
  → 카테고리별 BSR Top 100 수집 (JSON)
  → amz_products 테이블 upsert (최신 상태)
  → amz_products_history 테이블 append (시계열)
  → 수집 완료 로그
```

### 4.2 분석 파이프라인 (사용자 요청)

```
[Slack: /amz hair growth]
  → amz_categories 테이블에서 fuzzy match
  → 매칭 카테고리 Slack 버튼으로 제시
  → 사용자 선택
  → amz_products에서 해당 카테고리 제품 조회
  → Gemini 성분 분석 (기존 파이프라인 재사용)
  → Excel + Slack 응답
```

### 4.3 Bright Data API 호출

```python
# Endpoint: Amazon Products - Discover by best sellers url
POST https://api.brightdata.com/datasets/v3/trigger
  ?dataset_id=gd_l7q7dkf244hwjntr0
  &type=discover_new
  &discover_by=best_sellers_url
  &limit_per_input=100

Headers:
  Authorization: Bearer {BRIGHT_DATA_API_TOKEN}
  Content-Type: application/json

Body:
[
  {"url": "https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281"},
  {"url": "https://www.amazon.com/Best-Sellers/zgbs/beauty/11057651"},
  ...
]

Response: {"snapshot_id": "snap_xxxxx"}

# 결과 조회 (폴링)
GET https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}?format=json
```

## 5. DB 설계

### 5.1 amz_categories (카테고리 마스터)

```sql
CREATE TABLE amz_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    node_id VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    parent_node_id VARCHAR(20),
    url VARCHAR(500) NOT NULL,
    keywords VARCHAR(500) DEFAULT '',    -- fuzzy match용 검색어
    depth INT DEFAULT 0,                 -- 카테고리 깊이
    is_active BOOLEAN DEFAULT TRUE,      -- 수집 대상 여부
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 5.2 amz_products (최신 스냅샷)

```sql
CREATE TABLE amz_products (
    asin VARCHAR(20) PRIMARY KEY,
    title VARCHAR(500),
    brand VARCHAR(200),
    description TEXT,
    initial_price DECIMAL(10,2),
    final_price DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'USD',
    rating DECIMAL(3,2),
    reviews_count INT,
    bs_rank INT,
    bs_category VARCHAR(200),
    root_bs_rank INT,
    root_bs_category VARCHAR(200),
    ingredients TEXT,
    features JSON,
    product_details JSON,
    manufacturer VARCHAR(200),
    department VARCHAR(200),
    image_url VARCHAR(1000),
    url VARCHAR(1000),
    badge VARCHAR(100),
    bought_past_month INT,
    is_available BOOLEAN DEFAULT TRUE,
    country_of_origin VARCHAR(100),
    item_weight VARCHAR(100),
    categories JSON,                      -- 카테고리 경로
    collected_at DATETIME,                -- Bright Data 수집 시각
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 5.3 amz_products_history (시계열)

```sql
CREATE TABLE amz_products_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    asin VARCHAR(20) NOT NULL,
    snapshot_date DATE NOT NULL,
    bs_rank INT,
    bs_category VARCHAR(200),
    final_price DECIMAL(10,2),
    rating DECIMAL(3,2),
    reviews_count INT,
    bought_past_month INT,
    badge VARCHAR(100),
    INDEX idx_asin_date (asin, snapshot_date),
    UNIQUE KEY uk_asin_date (asin, snapshot_date)
);
```

## 6. 카테고리 초기 시딩

| 카테고리명 | Node ID | URL 경로 |
|-----------|---------|----------|
| Hair Growth Products | 11058281 | zgbs/beauty/11058281 |
| Hair Loss Shampoos | 3591081 | zgbs/beauty/3591081 |
| Skin Care | 11060451 | zgbs/beauty/11060451 |
| Facial Cleansing | 11060901 | zgbs/beauty/11060901 |
| Vitamins & Supplements | 3764441 | zgbs/hpc/3764441 |

> 초기 5개 카테고리로 시작, 필요에 따라 확장

## 7. Slack 인터랙션 변경

### 7.1 카테고리 선택 플로우

```
사용자: /amz hair
봇:     🔍 "hair" 관련 카테고리:
        [Hair Growth Products]  [Hair Loss Shampoos]

사용자: (버튼 클릭)
봇:     📊 Hair Growth Products BSR Top 100 분석 중... (Gemini)
봇:     ✅ 분석 완료 (100개 제품)
        [Excel 파일 첨부]
```

### 7.2 새 Slack 명령어

| 명령어 | 설명 |
|--------|------|
| `/amz {keyword}` | 카테고리 검색 → 선택 → 분석 |
| `/amz list` | 등록된 카테고리 목록 |
| `/amz trend {asin}` | (향후) 특정 제품 BSR/가격 추이 |
| `/amz refresh` | 수동 데이터 갱신 트리거 |

## 8. 영향 받는 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `services/bright_data.py` | **신규** | Bright Data API 클라이언트 |
| `services/data_collector.py` | **신규** | 주간 수집 + DB 적재 로직 |
| `services/cache.py` | 수정 | amz_products 조회로 변경 |
| `orchestrator.py` | **대폭 수정** | Browse.ai 제거, DB 조회 기반으로 전환 |
| `services/browse_ai.py` | **삭제** | Bright Data로 완전 대체 |
| `services/html_parser.py` | **삭제** | 구조화된 JSON이므로 파싱 불필요 |
| `jobs/amz_collect.py` | **신규** | 주간 cron job 엔트리포인트 |
| `main.py` | 수정 | Slack 인터랙션 핸들러 추가 (버튼 콜백) |

## 9. 비용 분석

| 항목 | Browse.ai (현재) | Bright Data (전환 후) |
|------|-----------------|---------------------|
| 단가 | ~$0.10/task | ~$0.01/record |
| 주 1회 수집 (5카테고리 × 100) | - | ~$5 |
| 월 비용 | 요청 빈도 따라 가변 | **~$20 고정** |
| 실패 재시도 비용 | 추가 과금 | 거의 없음 |

## 10. 마이그레이션 전략

1. **Phase 1**: Bright Data 연동 + amz_products 적재 (Browse.ai와 병행)
2. **Phase 2**: orchestrator를 DB 조회 기반으로 전환
3. **Phase 3**: Browse.ai 코드 제거, Slack 인터랙션 변경
4. **Phase 4**: amz_products_history 기반 트렌드 기능 (향후)

## 11. Success Criteria

- [ ] Bright Data API로 주 1회 자동 수집 동작
- [ ] 카테고리별 BSR Top 100 제품이 amz_products에 적재
- [ ] `/amz {keyword}` 요청 시 5초 이내 응답 시작
- [ ] Browse.ai 코드 완전 제거
- [ ] 수집 이력이 amz_products_history에 누적
- [ ] Slack 카테고리 선택 UI 동작

## 12. 환경 변수 추가

```
BRIGHT_DATA_API_TOKEN=xxx
BRIGHT_DATA_DATASET_ID=gd_l7q7dkf244hwjntr0
```
