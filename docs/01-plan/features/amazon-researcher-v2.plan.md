# Plan: Amazon Researcher V2 — 데이터 구조 변경 + MySQL 캐시 전략

## 1. Overview

Browse.ai 상세 크롤링 데이터 구조가 변경됨에 따라, 파싱/평가/캐시 로직을 전면 개편한다.
타사 제품 정보를 MySQL에 적재하여 browse.ai 크레딧을 절약하고, 확장 가능한 데이터 저장 구조를 구축한다.

- **트리거**: Slack `/amz prod {keyword}` → 캐시 우선 조회 → 필요 시 browse.ai 호출
- **캐시 무시**: `/amz prod {keyword} --refresh` → 전체 재수집
- **DB**: CFO 호스트 MySQL (`lib/mysql_connector.py` 활용)

## 2. Problem Statement

### 현재 문제점

1. **Browse.ai 데이터 구조 변경**: 상세 크롤링 결과가 `capturedTexts` flat 구조에서 CSV 형태(`name`, `newText`, `previousText`)로 변경됨. 기존 파싱 로직(`texts.get("title")` 등)이 동작하지 않음.

2. **판매량(Volume) 데이터 부재**: `volume` 필드가 더 이상 제공되지 않아 가중치 계산에서 Volume(30%) 비중이 무의미함.

3. **크레딧 낭비**: 동일 키워드 재검색 시 매번 browse.ai API를 호출하여 크레딧이 소모됨. 제품 정보는 잘 변하지 않는 특성상 캐시가 효과적.

4. **데이터 확장성 부족**: 현재 성분(ingredients)만 추출하지만, features/measurements/item_details 등 풍부한 데이터가 수집되므로 향후 활용을 위해 구조화 저장이 필요함.

## 3. 변경사항 요약

| # | 항목 | AS-IS | TO-BE |
|---|------|-------|-------|
| 1 | Detail 데이터 구조 | `capturedTexts` flat dict | CSV rows: `name/newText/previousText` |
| 2 | 파싱 대상 필드 | `title`, `top_highlights`, `features` | `ingredients`, `features`, `measurements`, `item_details`, `details` |
| 3 | 가중치: Volume(30%) | `parse_volume("1K+ bought")` | **제거** → BSR 랭킹으로 대체 |
| 4 | 가중치: BSR | 미사용 | BSR 순위 파싱 후 가중치 반영 |
| 5 | 가중치: Rating | `rating/5.0 * 0.2` | 유지 (검색 결과의 별점 활용) |
| 6 | 캐시 | `/tmp` 파일 체크포인트 (24h) | MySQL DB 캐시 (30일) |
| 7 | 명령어 | `/amz {keyword}` | `/amz prod {keyword}` + `--refresh` 옵션 |
| 8 | 데이터 저장 | 임시 파일만 | MySQL에 검색결과/상세정보/분석결과 영구 저장 |

## 4. Browse.ai 실제 응답 구조 (API 테스트 확인됨)

### 4.1 Detail 크롤링 응답 형태

기존과 동일하게 `capturedTexts` dict 형태. 단, 필드가 변경됨:

```json
// 기존 (AS-IS): title, top_highlights, features, measurements, bsr, volumn
// 신규 (TO-BE): ingredients, features, measurements, item_details, details, _STATUS, _PREV_*
"capturedTexts": {
    "ingredients": "Cyclopentasiloxane, Dimethicone, ...",      // plain text
    "features": "<h1>Features & Specs</h1><table>...</table>",  // HTML
    "measurements": "<h1>Measurements</h1><table>...</table>",  // HTML
    "item_details": "<h1>Item details</h1><table>...</table>",  // HTML (BSR, Reviews 포함)
    "details": "<h1>Additional details</h1><table>...</table>", // HTML
    "_STATUS": "CHANGED",
    "_PREV_item_details": "..."                                  // 이전 버전 (무시)
}
```

**삭제된 필드**: `title`, `top_highlights`, `volume` (→ title은 검색 결과에서 취득, volume은 BSR로 대체)

### 4.2 핵심 파싱 전략

HTML은 모두 동일 패턴: `<table class="a-keyvalue prodDetTable"><tr><th>Key</th><td>Value</td></tr></table>`

| 필드 | 형태 | 파싱 방법 | 추출 데이터 |
|------|------|-----------|------------|
| `ingredients` | plain text | 쉼표 split → trim | INCI 전성분 리스트 |
| `features` | HTML `<table>` | th/td → dict | `{"Product Benefits": "Frizz Control", "Hair Type": "All", ...}` |
| `measurements` | HTML `<table>` | th/td → dict | `{"Liquid Volume": "100 Milliliters", ...}` |
| `item_details` | HTML `<table>` + 특수 셀 | th/td → dict + BSR/Reviews 별도 파싱 | Brand, ASIN, BSR, Rating, Reviews |
| `details` | HTML `<table>` | th/td → dict | `{"Material Type Free": "Mineral Oil Free, ..."}` |

**JSON만 저장** (HTML 원본 미저장):
- HTML 구조가 매우 규칙적 — 파싱이 사실상 무손실
- 100개 제품 기준 ~400KB(HTML) vs ~30KB(JSON) 용량 차이
- JSON 컬럼으로 `features->"$.Hair Type"` 직접 SQL 쿼리 가능
- 파싱 실패 시 로그에 HTML 원본 출력 (디버그용)

### 4.3 BSR 파싱 규칙

`item_details`의 `Best Sellers Rank` 셀에서:
- `#581 in Beauty & Personal Care` → category BSR = 581
- `#1 in Hair Styling Serums` → subcategory BSR = 1
- 여러 카테고리가 `<li>` 리스트로 존재 → 전체 카테고리 BSR (가장 큰 카테고리)을 가중치에 사용

### 4.4 별점/리뷰 파싱 규칙

`item_details`의 `Customer Reviews` 셀에서:
- `title="4.6 out of 5 stars"` 또는 `aria-hidden` span에서 `4.6` → rating
- `aria-label="1,285 Reviews"` 또는 `(1,285)` → review_count = 1285
- 검색 결과의 rating/reviews와 교차 검증 가능 (상세 데이터가 더 정확)

## 5. 가중치 계산 변경

### AS-IS

```
Weight = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
```

### TO-BE

Volume 데이터가 없으므로 BSR 순위 + Rating으로 대체:

```
Weight = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)
```

| 요소 | 비중 | 정규화 | 근거 |
|------|------|--------|------|
| Position | 20% | `1 - (pos-1)/max_pos` | 검색 순위 (기존 유지) |
| Reviews | 25% | `reviews/max_reviews` | 리뷰 수 (30→25%로 하향) |
| Rating | 15% | `rating/5.0` | 별점 (20→15%로 하향, 차별성 낮음) |
| BSR | 40% | `1 - (bsr_rank-1)/max_bsr` | 베스트셀러 순위 (핵심 지표) |

**BSR 없는 제품 처리**: BSR 파싱 실패 시 `bsr_rank = max_bsr + 1` (최하위 취급)

## 6. MySQL 캐시 전략

### 6.1 DB 연결

CFO 호스트의 MySQL을 사용. `lib/mysql_connector.py`의 `MysqlConnector("CFO")` 활용.

### 6.2 테이블 설계

#### 2개 테이블이 적절한 이유

| 관점 | 평가 |
|------|------|
| **데이터 관계** | 키워드↔ASIN은 다대다. 같은 ASIN이 여러 키워드 검색에 등장. 검색 결과(position 등)는 키워드별, 상세 정보는 ASIN별로 분리가 자연스러움 |
| **캐시 효율** | 키워드 A에서 크롤링한 ASIN을 키워드 B에서 재활용 가능. 상세 크롤링 크레딧 추가 절약 |
| **갱신 주기** | 검색 순위(position)는 자주 변동, 제품 상세(ingredients 등)는 거의 불변 → 테이블별 TTL 분리 가능 |
| **3번째 테이블?** | 분석 결과(rankings, categories)는 캐시 데이터로 재계산 가능 → 별도 테이블 불필요 |

**결론: 2개 테이블이 최적.**

#### `amz_search_cache` — 키워드별 검색 결과 캐시

```sql
CREATE TABLE amz_search_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(200) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    position INT NOT NULL,
    title VARCHAR(500) DEFAULT '',
    price DECIMAL(10,2) DEFAULT NULL,
    price_raw VARCHAR(50) DEFAULT '',
    reviews INT DEFAULT 0,
    reviews_raw VARCHAR(50) DEFAULT '',
    rating DECIMAL(3,2) DEFAULT 0.00,
    sponsored TINYINT(1) DEFAULT 0,
    product_link VARCHAR(1000) DEFAULT '',
    searched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_keyword_asin (keyword, asin),
    INDEX idx_keyword_searched (keyword, searched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### `amz_product_detail` — ASIN별 상세 정보 캐시 (JSON only, HTML 미저장)

```sql
CREATE TABLE amz_product_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    asin VARCHAR(20) NOT NULL,
    -- 전성분 (plain text, 파싱 불필요)
    ingredients_raw TEXT,
    -- 파싱된 JSON (HTML 원본 미저장 — 규칙적 구조이므로 무손실 파싱)
    features JSON COMMENT '{"Product Benefits":"Frizz Control","Hair Type":"All",...}',
    measurements JSON COMMENT '{"Liquid Volume":"100 Milliliters",...}',
    item_details JSON COMMENT '{"Brand Name":"MAREE","Manufacturer":"MAREE","GTIN":"...","ASIN":"..."}',
    additional_details JSON COMMENT '{"Material Type Free":"Mineral Oil Free, ..."}',
    -- item_details에서 추출한 핵심 필드 (직접 쿼리/정렬용)
    bsr_category INT DEFAULT NULL COMMENT '전체 카테고리 BSR (예: 581)',
    bsr_subcategory INT DEFAULT NULL COMMENT '서브카테고리 BSR (예: 1)',
    bsr_category_name VARCHAR(200) DEFAULT '' COMMENT '예: Beauty & Personal Care',
    bsr_subcategory_name VARCHAR(200) DEFAULT '' COMMENT '예: Hair Styling Serums',
    rating DECIMAL(3,2) DEFAULT NULL COMMENT '상세 페이지 별점 (예: 4.60)',
    review_count INT DEFAULT NULL COMMENT '상세 페이지 리뷰 수 (예: 1285)',
    brand VARCHAR(200) DEFAULT '',
    manufacturer VARCHAR(200) DEFAULT '',
    crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_asin (asin),
    INDEX idx_crawled_at (crawled_at),
    INDEX idx_bsr_category (bsr_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 캐시 정책 (30일)

```
1. /amz prod [keyword] 수신
2. amz_search_cache에서 keyword로 조회
   - 30일 이내 데이터 존재 → 캐시된 ASIN 목록 사용 (browse.ai 검색 크레딧 절약)
   - 없음 → browse.ai 검색 실행 → 결과를 amz_search_cache에 저장
3. 각 ASIN에 대해 amz_product_detail 조회
   - 30일 이내 데이터 존재 → 캐시 사용 (browse.ai 상세 크레딧 절약)
   - 없음 → 미캐시 ASIN만 모아서 browse.ai 상세 크롤링 → 결과 저장
4. 전체 데이터로 분석 실행
```

### 6.4 `--refresh` 옵션

`/amz prod [keyword] --refresh` 수신 시:
- 캐시 무시, 모든 데이터를 browse.ai에서 새로 수집
- 기존 캐시 데이터는 upsert로 갱신 (DELETE 아님)

## 7. 명령어 변경

### AS-IS

```
/amz {keyword}         → 검색 + 분석
```

### TO-BE

```
/amz prod {keyword}              → 캐시 우선 조회 + 분석
/amz prod {keyword} --refresh    → 캐시 무시 + 전체 재수집
```

### 파싱 로직

```python
# text = "prod hair serum --refresh"
parts = text.strip().split()
# subcommand = parts[0]  → "prod"
# refresh = "--refresh" in parts
# keyword = " ".join(p for p in parts[1:] if p != "--refresh")
```

향후 `/amz` 하위 명령어 확장 가능 (예: `/amz trend`, `/amz compare`).

## 8. 데이터 저장 전략 (확장성)

### 원칙

- **JSON만 저장**: HTML 원본 미저장. `prodDetTable`이 규칙적 `th/td` 구조이므로 파싱이 무손실
- **전성분 보관**: `ingredients_raw`에 INCI 전성분 텍스트 저장 (현재는 마케팅 성분만 분석하지만 향후 전성분 분석 가능)
- **구조화 저장**: features, measurements 등을 key-value JSON으로 파싱하여 저장 → 향후 SQL 쿼리로 특정 속성 필터링 가능
- **핵심 필드 추출**: BSR, rating, review_count, brand는 전용 컬럼으로 추출 → WHERE/ORDER BY 쿼리 가능
- **파싱 실패 시**: 로그에 HTML 원본 출력 (디버그용), JSON에는 빈 dict `{}` 저장

### 파싱 결과 JSON 예시

```json
// features
{
    "Product Benefits": "Frizz Control",
    "Hair Type": "All",
    "Scent Name": "Light",
    "Item Form": "Oil"
}

// measurements
{
    "Liquid Volume": "100 Milliliters",
    "Number of Items": "1",
    "Unit Count": "3.4 Fluid Ounces"
}

// item_details (BSR, rating, review_count는 별도 컬럼에도 추출)
{
    "Brand Name": "MAREE",
    "Manufacturer": "MAREE",
    "GTIN": "00810177352815",
    "ASIN": "B0FGXG294L",
    "bsr": [
        {"rank": 581, "category": "Beauty & Personal Care"},
        {"rank": 1, "category": "Hair Styling Serums"}
    ],
    "rating": 4.6,
    "review_count": 1285
}

// additional_details
{
    "Material Type Free": "Mineral Oil Free, Paraben Free, Phthalate Free, Sulfate Free"
}
```

## 9. 영향 받는 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `amz_researcher/models.py` | **수정** | ProductDetail 모델 전면 변경, 신규 모델 추가 |
| `amz_researcher/services/browse_ai.py` | **수정** | 상세 결과 파싱 로직 전면 변경 (CSV→구조화) |
| `amz_researcher/services/analyzer.py` | **수정** | 가중치 공식 변경 (Volume→BSR), Rating 비중 조정 |
| `amz_researcher/services/gemini.py` | **수정** | 성분 추출 입력 변경 (ingredients_raw + features 활용) |
| `amz_researcher/services/excel_builder.py` | **수정** | Volume→BSR 컬럼 변경, Raw 시트 구조 변경 |
| `amz_researcher/services/cache.py` | **신규** | MySQL 캐시 서비스 (검색/상세 조회·저장) |
| `amz_researcher/services/html_parser.py` | **신규** | Browse.ai HTML 테이블 파싱 유틸리티 |
| `amz_researcher/orchestrator.py` | **수정** | 캐시 전략 적용, --refresh 처리, 파이프라인 변경 |
| `amz_researcher/router.py` | **수정** | `/amz prod` 서브커맨드 파싱, --refresh 옵션 |
| `amz_researcher/services/checkpoint.py` | **제거 가능** | MySQL 캐시로 대체 (또는 중간 실패 복구용 유지) |

## 10. Implementation Order

| Phase | 작업 | 파일 | 의존성 |
|-------|------|------|--------|
| 1 | MySQL 테이블 DDL 작성 + 실행 | SQL scripts | 없음 |
| 2 | Models 변경 (ProductDetail v2, CacheEntry 등) | `models.py` | 없음 |
| 3 | HTML 파서 신규 작성 (features/measurements/item_details) | `html_parser.py` | 없음 |
| 4 | Browse.ai 파싱 로직 변경 (CSV 구조 대응) | `browse_ai.py` | Phase 2, 3 |
| 5 | MySQL 캐시 서비스 구현 | `cache.py` | Phase 2 |
| 6 | Analyzer 가중치 공식 변경 (BSR + Rating 반영) | `analyzer.py` | Phase 2 |
| 7 | Gemini 입력 변경 (ingredients_raw 활용) | `gemini.py` | Phase 2 |
| 8 | Excel builder 컬럼 변경 (Volume→BSR, Raw 시트) | `excel_builder.py` | Phase 2, 6 |
| 9 | Orchestrator 캐시 전략 적용 | `orchestrator.py` | Phase 4, 5, 6, 7 |
| 10 | Router 서브커맨드 + --refresh 파싱 | `router.py` | Phase 9 |

## 11. 환경 변수 변경

기존 환경 변수 유지. 추가 불필요 (CFO DB 설정은 이미 `config.py`에 존재).

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browse.ai 응답 구조 재변경 | 파싱 실패 | HTML 원본 저장으로 재파싱 가능 |
| BSR 필드 없는 제품 | 가중치 왜곡 | 최하위 기본값 + BSR 없는 비율 로깅 |
| CFO DB 연결 실패 | 캐시 사용 불가 | fallback: 캐시 없이 browse.ai 직접 호출 |
| HTML 구조 변경 (아마존 페이지) | 파싱 실패 | `previousText` fallback (plain text) 활용 |
| 대량 데이터 MySQL 적재 | 느린 응답 | batch upsert + connection pooling |

## 13. Success Criteria

- [ ] `/amz prod hair serum` 실행 시 캐시 미존재 → browse.ai 호출 → MySQL 저장 → 분석 완료
- [ ] 동일 키워드 30일 내 재실행 시 browse.ai 호출 없이 캐시에서 분석 완료
- [ ] `--refresh` 옵션 시 캐시 무시하고 전체 재수집
- [ ] BSR 기반 가중치로 분석 결과 정확도 향상
- [ ] HTML 원본 + 파싱 결과 모두 MySQL에 저장되어 향후 확장 가능
- [ ] 기존 `/amz` 명령어 하위 호환 (또는 명확한 마이그레이션 안내)
