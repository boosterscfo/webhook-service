# Category Refresh UX Planning Document

> **Summary**: 카테고리 선택 후 바로 분석하는 대신, "새로 수집" vs "캐시 사용 (X일 전)" 선택지를 제공하여 사용자가 데이터 freshness를 제어할 수 있게 한다.
>
> **Project**: webhooks (amz_researcher)
> **Author**: CTO
> **Date**: 2026-03-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 카테고리 선택 시 캐시 데이터로 바로 분석이 시작되어, 사용자가 데이터 최신성을 판단하거나 새로 수집할지 선택할 수 없다. `/amz refresh`라는 별도 명령어가 있지만 분석 플로우와 분리되어 있어 사용이 번거롭다. |
| **Solution** | 카테고리 버튼 클릭 후 중간 단계를 추가하여, 캐시 freshness 정보와 함께 "새로 수집" / "캐시 사용" 버튼을 제시한다. 새로 수집 선택 시 기존 원샷 수집 플로우를 재활용한다. |
| **Function/UX Effect** | 카테고리 선택이 2단계(카테고리 선택 -> 수집 옵션 선택)로 변경되나, 사용자는 데이터 나이를 확인하고 의사결정할 수 있다. 캐시가 없는 미수집 카테고리는 기존처럼 바로 수집이 트리거된다. |
| **Core Value** | 온디맨드 수집 방식에서 사용자에게 데이터 최신성 제어권을 부여하여, 불필요한 수집 비용을 줄이면서도 필요 시 최신 데이터를 확보할 수 있다. |

---

## 1. Overview

### 1.1 Purpose

현재 `/amz {keyword}` -> 카테고리 버튼 클릭 시, `run_analysis()`가 DB에 저장된 기존 데이터로 바로 분석을 시작한다. BSR 데이터는 정기 수집이 아닌 온디맨드 방식이므로, 데이터가 며칠~몇 주 전 것일 수 있다. 사용자가 데이터 나이를 인지하고 "새로 수집할지" vs "기존 데이터로 분석할지" 선택할 수 있는 UX를 제공한다.

### 1.2 Background

- BSR 데이터 수집은 Bright Data API를 통한 온디맨드 방식 (정기 cron 없음)
- `/amz refresh` 명령어가 존재하지만, 분석 플로우와 분리되어 있어 "refresh 후 다시 /amz {keyword}" 2단계 조작이 필요
- 키워드 검색(`/amz search`)에는 이미 유사한 패턴이 있음: 유사 키워드 캐시가 있을 때 "기존 데이터 사용" vs "새로 수집" 버튼을 제시 (router.py L363-414)
- 카테고리 원샷 수집 플로우가 이미 구현되어 있음 (orchestrator.py `_trigger_category_collection`)

### 1.3 Related Documents

- `docs/01-plan/features/oneshot-category-flow.plan.md` - 미수집 카테고리 원샷 플로우
- `docs/01-plan/features/amazon-researcher-v4.plan.md` - V4 카테고리 기반 분석

---

## 2. Scope

### 2.1 In Scope

- [ ] 카테고리 선택 후 "새로 수집" vs "캐시 사용 (X일 전)" 선택 UI
- [ ] 카테고리별 데이터 freshness (최신 collected_at) 조회 메서드
- [ ] "새로 수집" 선택 시 Bright Data 수집 트리거 -> 수집 완료 후 자동 분석
- [ ] "캐시 사용" 선택 시 기존 분석 플로우 즉시 실행
- [ ] 미수집 카테고리(데이터 없음)는 선택지 없이 바로 수집 트리거 (기존 동작 유지)
- [ ] interact 핸들러에 새 action_id 처리 추가

### 2.2 Out of Scope

- 정기 수집 스케줄링 (cron) 도입
- `/amz refresh` 명령어 제거 (유지, 전체 카테고리 일괄 수집용)
- 캐시 TTL 정책 변경 (기존 30일 유지)
- 키워드 검색(`/amz search`) 플로우 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 카테고리 버튼 클릭 시, 해당 카테고리의 데이터 freshness를 조회하여 "새로 수집" + "캐시 사용 (X일 전, Y개 제품)" 버튼을 Block Kit으로 제시 | High | Pending |
| FR-02 | "새로 수집" 버튼 클릭 시 Bright Data 수집 트리거 후 완료 시 자동 분석 (기존 `_trigger_category_collection` 재활용) | High | Pending |
| FR-03 | "캐시 사용" 버튼 클릭 시 기존 `run_analysis()` 즉시 실행 | High | Pending |
| FR-04 | 미수집 카테고리(collected_at이 없거나 제품 수 0)는 선택지 없이 바로 수집 트리거 (기존 원샷 동작 유지) | High | Pending |
| FR-05 | freshness 정보에 제품 수(product_count)와 최신 수집일(collected_at) 포함 | Medium | Pending |
| FR-06 | 수집 중 상태일 때 동일 카테고리 재수집 요청 방지 (중복 트리거 차단) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 응답 속도 | freshness 조회가 카테고리 선택 응답에 3초 이내 포함 | Slack ephemeral 응답 시간 측정 |
| 사용자 경험 | 선택지 메시지가 명확하고 데이터 나이가 직관적으로 표시됨 | 사용자 피드백 |
| 하위 호환 | 기존 `/amz refresh` 명령어가 정상 동작 | 기존 기능 테스트 |

---

## 4. Current Flow Analysis

### 4.1 현재 카테고리 선택 -> 분석 플로우

```
User: /amz serum
  -> slack_amz() 핸들러
  -> product_db.search_categories("serum") -- 전체 카테고리 fuzzy 검색
  -> Block Kit 버튼 응답 (최대 5개 카테고리)

User: 버튼 클릭 ("Hair Serums")
  -> slack_amz_interact() 핸들러
  -> action_id가 "amz_category_{node_id}" 매칭
  -> value에서 node_id, name, response_url, channel_id 추출
  -> run_analysis(node_id, name, response_url, channel_id, user_id) 호출
     -> Step 1: get_products_by_category(node_id)
        -> 제품 있음: 바로 분석 시작 (캐시 데이터 사용)
        -> 제품 없음: _trigger_category_collection() 원샷 수집
```

### 4.2 변경 후 플로우 (Proposed)

```
User: /amz serum
  -> (기존과 동일) 카테고리 버튼 표시

User: 버튼 클릭 ("Hair Serums")
  -> slack_amz_interact() 핸들러
  -> action_id가 "amz_category_{node_id}" 매칭
  -> [NEW] freshness 조회: get_category_freshness(node_id)
     -> 데이터 없음: 바로 수집 트리거 (기존 원샷 동작)
     -> 데이터 있음: 선택지 Block Kit 응답
        ┌─────────────────────────────────────────────┐
        │ Hair Serums — 데이터 옵션                      │
        │                                              │
        │ 현재 데이터: 98개 제품, 3일 전 수집              │
        │                                              │
        │ [새로 수집]  [캐시 사용 (3일 전)]                │
        └─────────────────────────────────────────────┘

User: "새로 수집" 클릭
  -> action_id: "amz_category_refresh"
  -> _trigger_category_collection() 호출 (기존 원샷 플로우)
  -> 수집 완료 후 자동 분석

User: "캐시 사용 (3일 전)" 클릭
  -> action_id: "amz_category_cached"
  -> run_analysis() 바로 호출 (기존 동작)
```

---

## 5. Technical Design Points

### 5.1 새 메서드: `get_category_freshness()`

`product_db.py`에 추가. 카테고리별 최신 collected_at과 제품 수를 반환.

```python
def get_category_freshness(self, node_id: str) -> dict | None:
    """카테고리 데이터 freshness 조회.

    Returns:
        {"product_count": int, "collected_at": datetime} or None (미수집)
    """
    query = """
        SELECT COUNT(*) as product_count, MAX(p.collected_at) as latest
        FROM amz_products p
        JOIN amz_product_categories pc ON p.asin = pc.asin
        WHERE pc.category_node_id = %s
    """
```

참고: `cache.py`의 `_get_data_freshness()`는 category_name 기반이므로 node_id 기반 메서드가 별도로 필요.

### 5.2 Slack Block Kit 메시지 설계

카테고리 버튼 클릭 후 응답으로 제시되는 선택지 메시지:

```json
{
  "response_type": "ephemeral",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": ":mag: *Hair Serums* 분석 옵션\n현재 데이터: 98개 제품, 3일 전 수집"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "새로 수집 후 분석"},
          "action_id": "amz_category_refresh",
          "value": "{\"node_id\": \"...\", \"name\": \"...\", ...}",
          "style": "primary"
        },
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "캐시 사용 (3일 전)"},
          "action_id": "amz_category_cached",
          "value": "{\"node_id\": \"...\", \"name\": \"...\", ...}"
        }
      ]
    }
  ]
}
```

### 5.3 interact 핸들러 변경

`slack_amz_interact()`에 두 개의 새 action_id 분기 추가:

| action_id | 동작 |
|-----------|------|
| `amz_category_{node_id}` | (변경) freshness 조회 -> 선택지 응답 또는 바로 수집 |
| `amz_category_refresh` | (신규) Bright Data 수집 트리거 -> 자동 분석 |
| `amz_category_cached` | (신규) 기존 `run_analysis()` 즉시 호출 |

### 5.4 플로우 분기 로직

기존 `amz_category_{node_id}` 핸들러에서:

```python
# 카테고리 버튼 클릭 시
freshness = product_db.get_category_freshness(node_id)

if freshness is None or freshness["product_count"] == 0:
    # 미수집 카테고리 -> 바로 수집 트리거 (기존 원샷 동작)
    background_tasks.add_task(
        _trigger_category_collection, node_id, name, ...)
    return {"text": "데이터 수집 시작..."}
else:
    # 캐시 있음 -> 선택지 제시
    days_ago = (datetime.now() - freshness["collected_at"]).days
    return _build_refresh_options(node_id, name, freshness, days_ago, ...)
```

---

## 6. Impact Analysis

### 6.1 변경 파일 목록

| 파일 | 변경 내용 | 변경 규모 |
|------|-----------|-----------|
| `amz_researcher/router.py` | interact 핸들러에 freshness 분기 및 새 action_id 처리 추가 | Medium |
| `amz_researcher/services/product_db.py` | `get_category_freshness()` 메서드 추가 | Small |
| `amz_researcher/orchestrator.py` | 변경 없음 (기존 `run_analysis`, `_trigger_category_collection` 재활용) | None |
| `amz_researcher/services/cache.py` | 변경 없음 | None |
| `amz_researcher/services/bright_data.py` | 변경 없음 | None |
| `amz_researcher/services/slack_sender.py` | 변경 없음 | None |

### 6.2 기존 기능 영향

| 기능 | 영향 |
|------|------|
| `/amz {keyword}` 카테고리 검색 | 변경 없음 (1단계는 동일) |
| 카테고리 버튼 클릭 -> 분석 | 변경됨 (중간 선택 단계 추가) |
| `/amz refresh` | 변경 없음 |
| `/amz search` | 변경 없음 |
| `/amz report` | 변경 없음 |
| Bright Data webhook 콜백 | 변경 없음 (기존 원샷 플로우 재활용) |

---

## 7. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 선택 단계 추가로 UX 복잡도 증가 | Medium | Medium | 미수집 카테고리는 선택 없이 바로 수집, 데이터 나이 정보를 직관적으로 표시 |
| Slack ephemeral 응답 시간 내 freshness DB 조회 | Low | Low | 단순 COUNT + MAX 쿼리, 인덱스 활용으로 ms 단위 응답 |
| interact 핸들러에서 freshness 조회가 Slack 3초 제한에 걸림 | Medium | Low | interact 응답은 이미 동기식으로 처리 중이며, DB 조회는 빠름. 필요 시 background task로 전환 |
| "새로 수집" 클릭 후 기존 캐시가 유실되는 것 아닌지 혼란 | Low | Low | 새 수집은 기존 데이터를 upsert하므로 유실 없음. 안내 문구에 명시 |

---

## 8. Success Criteria

### 8.1 Definition of Done

- [ ] 기존 데이터가 있는 카테고리 선택 시 "새로 수집" / "캐시 사용" 선택지가 표시됨
- [ ] "캐시 사용" 클릭 시 기존과 동일하게 분석 즉시 실행
- [ ] "새로 수집" 클릭 시 Bright Data 수집 -> 완료 후 자동 분석
- [ ] 미수집 카테고리는 기존과 동일하게 바로 수집 트리거
- [ ] 데이터 나이(X일 전)와 제품 수가 정확히 표시됨
- [ ] 기존 `/amz refresh`, `/amz search` 등 다른 기능에 영향 없음

### 8.2 Quality Criteria

- [ ] 기존 카테고리 분석 E2E 동작 확인
- [ ] 미수집 카테고리 원샷 플로우 동작 확인
- [ ] "새로 수집" 플로우 E2E 동작 확인
- [ ] 코드 리뷰 완료

---

## 9. Implementation Order

1. **Phase 1**: `product_db.py`에 `get_category_freshness()` 추가
2. **Phase 2**: `router.py`의 `slack_amz_interact()`에서 기존 `amz_category_{node_id}` 핸들러를 freshness 분기 로직으로 변경
3. **Phase 3**: `router.py`에 `amz_category_refresh`, `amz_category_cached` action_id 핸들러 추가
4. **Phase 4**: Block Kit 선택지 메시지 빌더 함수 구현
5. **Phase 5**: E2E 테스트

---

## 10. Next Steps

1. [ ] Write design document (`category-refresh-ux.design.md`)
2. [ ] Team review and approval
3. [ ] Start implementation

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial draft | CTO |
