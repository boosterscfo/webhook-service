# One-Shot Category Flow Planning Document

> **Summary**: 미수집 카테고리 선택 시 Bright Data 수집 -> DB 저장 -> 분석 -> 리포트까지 원샷 플로우 구현
>
> **Project**: webhooks (amz_researcher)
> **Author**: CTO
> **Date**: 2026-03-10
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

136개 Beauty 카테고리가 DB에 시딩되었으나(is_active=FALSE), 현재 `/amz {keyword}` -> 버튼 클릭 -> `run_analysis` 플로우는 이미 수집된 product 데이터가 있다고 가정한다. 미수집 카테고리 선택 시 빈 결과 또는 에러가 발생하는 문제를 해결한다.

### 1.2 Background

- 136개 Beauty 카테고리가 `amz_categories` 테이블에 `is_active=FALSE`로 시딩 완료
- `search_categories()`는 전체 카테고리(active/inactive 무관)를 검색하므로 미수집 카테고리도 버튼에 노출됨
- `run_analysis()`는 `get_products_by_category()`로 DB 조회 -> 제품이 없으면 "수집된 제품이 없습니다" 메시지 후 종료
- `/amz add`는 136개 시딩으로 인해 수동 URL 등록 기능이 불필요해짐
- 기존 키워드 검색(`/amz search`)에는 이미 "캐시 MISS -> Bright Data 트리거 -> webhook 콜백 -> 분석" 패턴이 구현되어 있음 (`run_keyword_analysis` 참조)

### 1.3 Related Documents

- `docs/01-plan/features/amazon-researcher-v5.plan.md`
- `docs/02-design/features/amazon-researcher-v5.design.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 미수집 카테고리 원샷 플로우 (수집 -> DB 저장 -> 분석 -> 리포트)
- [ ] `/amz add` 명령어 제거
- [ ] is_active 상태 자동 관리 (수집 트리거 시 TRUE로 전환)
- [ ] 검색 결과에 수집 여부 표시 (버튼 라벨에 상태 반영)
- [ ] `/amz list` 변경 (전체 카테고리 표시, active/inactive 구분)
- [ ] 도움말 텍스트 업데이트 (`/amz help`, `/amz` 빈 입력)

### 2.2 Out of Scope

- 카테고리 삭제/비활성화 기능
- 카테고리 자동 수집 스케줄링 (cron)
- 여러 카테고리 동시 원샷 수집

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 미수집 카테고리 버튼 클릭 시 Bright Data 수집 트리거 -> webhook 콜백 -> 분석 -> 리포트 원샷 플로우 | High | Pending |
| FR-02 | 수집 트리거 시 해당 카테고리를 `is_active=TRUE`로 자동 전환 | High | Pending |
| FR-03 | 검색 결과 버튼에 수집 여부 표시 (예: "Hair Oils" vs "Hair Oils [NEW]") | Medium | Pending |
| FR-04 | `/amz add` 명령어 제거 및 관련 코드 정리 | Medium | Pending |
| FR-05 | `/amz list`를 전체 카테고리 표시로 변경, active 여부 구분 | Low | Pending |
| FR-06 | 도움말 텍스트에서 `/amz add` 제거 및 원샷 플로우 설명 추가 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 사용자 경험 | 원샷 플로우 시 진행 상태 피드백 (수집중... -> 분석중...) | Slack 메시지 확인 |
| 안정성 | 수집 실패 시 사용자에게 명확한 에러 메시지 | 에러 시나리오 테스트 |
| 일관성 | 기존 keyword 검색의 비동기 패턴과 동일한 구조 | 코드 리뷰 |

---

## 4. Technical Design Overview

### 4.1 핵심 아이디어: 기존 패턴 재활용

키워드 검색(`/amz search`)에 이미 구현된 비동기 패턴을 카테고리 BSR 수집에 적용:

```
[기존 keyword 검색 패턴]
run_keyword_analysis() -> 캐시 MISS -> trigger_keyword_search() -> snapshot_id
  -> save_keyword_search_log(status='collecting')
  -> webhook 콜백 -> _ingest_keyword_snapshot() -> 분석 파이프라인

[신규 카테고리 원샷 패턴]
run_analysis() -> 제품 없음 -> trigger_collection(category_url) -> snapshot_id
  -> save_category_collection_log(status='collecting')  -- 신규
  -> webhook 콜백 -> _ingest_snapshot() -> run_analysis() 재호출
```

### 4.2 변경 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `amz_researcher/orchestrator.py` | `run_analysis()`에 "제품 없음 -> 수집 트리거" 분기 추가 |
| `amz_researcher/router.py` | `/amz add` 제거, webhook 콜백에 카테고리 수집 완료 후 분석 자동 실행 로직 추가 |
| `amz_researcher/services/product_db.py` | `activate_category()`, `save_category_collection_log()`, `get_category_collection_by_snapshot()` 추가 |
| `amz_researcher/router.py` | 버튼 라벨에 is_active 상태 표시 |

### 4.3 원샷 플로우 시퀀스

```
User: /amz serum
  -> search_categories("serum") -- 전체 카테고리 검색 (active/inactive 무관)
  -> 버튼 표시 (is_active=FALSE 카테고리는 "[NEW]" 라벨)

User: 버튼 클릭 (미수집 카테고리)
  -> interact 핸들러 -> run_analysis(node_id, name, ...)
  -> Step 1: get_products_by_category() -> 빈 결과
  -> Step 2 (NEW): 카테고리 URL 조회 -> trigger_collection([url])
       -> activate_category(node_id) -- is_active=TRUE 전환
       -> save_category_collection_log(snapshot_id, node_id, response_url, channel_id, user_id)
       -> Slack: "데이터 수집 시작... 완료 시 자동 분석 결과를 보내드립니다."
       -> return (종료, webhook 콜백 대기)

Bright Data -> POST /webhook/brightdata
  -> brightdata_webhook() -> snapshot_id 수신
  -> (기존) keyword 검색 로그 확인 -> 없음
  -> (NEW) category collection 로그 확인 -> 있음!
  -> _ingest_snapshot() -> 제품 DB 적재 완료
  -> (NEW) run_analysis(node_id, name, response_url, channel_id, user_id) 자동 호출
  -> 분석 -> 리포트 -> Slack 메시지
```

### 4.4 DB 변경

신규 테이블 또는 기존 테이블 확장 옵션:

**Option A: 기존 `_collection_callbacks` dict를 DB 테이블로 전환**

현재 `_collection_callbacks`는 인메모리 dict로 서버 재시작 시 유실됨. 카테고리 수집 콜백 정보를 DB에 저장하면 안정적.

```sql
CREATE TABLE amz_category_collection_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    snapshot_id VARCHAR(100) NOT NULL,
    category_node_id VARCHAR(50) NOT NULL,
    response_url TEXT,
    channel_id VARCHAR(50),
    user_id VARCHAR(50),
    status ENUM('collecting', 'completed', 'failed') DEFAULT 'collecting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_snapshot (snapshot_id)
);
```

**Option B: 인메모리 dict 유지 (단순)**

현재와 동일하게 `_collection_callbacks`에 node_id, user_id를 추가 저장. 서버 재시작 리스크는 수용.

**권장: Option B (인메모리)**
- 카테고리 수집은 수 분 내 완료되므로 서버 재시작 리스크가 낮음
- 키워드 검색은 DB 로그를 쓰지만, 그것은 캐시 관리 목적이 주임
- 기존 `_collection_callbacks` dict를 확장하는 것이 가장 간단

### 4.5 `/amz add` 제거 영향 분석

| 코드 위치 | 내용 | 처리 |
|-----------|------|------|
| `router.py` L261-283 | `/amz add` 분기 | 삭제 |
| `router.py` L558-587 | `_generate_category_keywords()` | 유지 (시딩 시 별도로 호출 가능) |
| `product_db.py` L260-280 | `add_category()` | 삭제 (시딩은 마이그레이션에서 처리) |
| `router.py` 도움말 텍스트 | `/amz add` 언급 | 제거 |

### 4.6 `get_category_url()` 수정

현재 `get_category_url()`은 `is_active=TRUE` 조건이 있어 미수집 카테고리의 URL을 가져올 수 없음. 원샷 플로우에서는 inactive 카테고리의 URL도 필요하므로 조건 제거 또는 별도 메서드 추가 필요.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Bright Data 수집 실패 시 사용자가 무한 대기 | Medium | Low | 타임아웃 후 에러 메시지 전송 (기존 `_ingest_snapshot`에 5분 타임아웃 있음) |
| 서버 재시작으로 콜백 정보 유실 | Low | Low | Option B 선택 시 수용 가능. 필요 시 Option A로 전환 |
| 동일 카테고리 중복 수집 요청 | Low | Medium | 수집 중 상태 체크 (인메모리 dict에 이미 snapshot_id가 있으면 "수집 중" 메시지 반환) |
| `is_active` 전환 후 refresh 명령에 포함 | Low | High | 의도적 동작. 한번 수집하면 이후 refresh 대상에 포함되는 것이 자연스러움 |

---

## 6. Success Criteria

### 6.1 Definition of Done

- [ ] 미수집 카테고리 버튼 클릭 시 수집 -> 분석 -> 리포트 자동 완료
- [ ] 수집 완료 후 해당 카테고리가 is_active=TRUE로 전환
- [ ] `/amz add` 제거 완료
- [ ] 검색 결과 버튼에 수집 여부가 시각적으로 구분됨
- [ ] 기존 활성 카테고리의 분석 플로우가 변경 없이 동작

### 6.2 Quality Criteria

- [ ] 기존 테스트 통과
- [ ] 미수집 카테고리 E2E 시나리오 수동 테스트 완료
- [ ] 코드 리뷰 완료

---

## 7. Implementation Order

1. **Phase 1**: `product_db.py`에 `activate_category()`, `get_category_url_any()` 추가
2. **Phase 2**: `orchestrator.py`의 `run_analysis()`에 원샷 분기 추가
3. **Phase 3**: `router.py`의 webhook 콜백에 카테고리 수집 완료 후 분석 자동 실행
4. **Phase 4**: `router.py` 버튼 라벨에 is_active 상태 표시
5. **Phase 5**: `/amz add` 제거 및 도움말 업데이트

---

## 8. Next Steps

1. [ ] Write design document (`oneshot-category-flow.design.md`)
2. [ ] Team review and approval
3. [ ] Start implementation

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-10 | Initial draft | CTO |
