# Category Refresh UX Design Document

> **Feature**: category-refresh-ux
> **Plan**: `docs/01-plan/features/category-refresh-ux.plan.md`
> **Date**: 2026-03-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 카테고리 선택 시 캐시 데이터로 바로 분석이 시작되어, 사용자가 데이터 최신성을 판단하거나 새로 수집할지 선택할 수 없다 |
| **Solution** | `router.py` interact 핸들러에서 카테고리 클릭 시 freshness 조회 후 선택지 Block Kit 응답을 중간 단계로 추가 |
| **Function/UX Effect** | 캐시 있는 카테고리는 "새로 수집 / 캐시 사용(X일 전)" 2버튼 제시. 미수집은 기존처럼 바로 수집 |
| **Core Value** | 변경 파일 2개(`router.py`, `product_db.py`), orchestrator/cache/bright_data 변경 없이 기존 플로우 재활용 |

---

## 1. Architecture Overview

### 1.1 현재 플로우 (AS-IS)

```
/amz {keyword}
  → slack_amz(): 카테고리 검색 → Block Kit 버튼 응답
  → [사용자 클릭]
  → slack_amz_interact(): amz_category_{node_id} 매칭
  → run_analysis(node_id, name, ...)
     → 제품 있음: 바로 분석 (캐시 데이터)
     → 제품 없음: _trigger_category_collection() → webhook 콜백 → 자동 분석
```

### 1.2 변경 플로우 (TO-BE)

```
/amz {keyword}
  → slack_amz(): 카테고리 검색 → Block Kit 버튼 응답 (변경 없음)
  → [사용자 클릭]
  → slack_amz_interact(): amz_category_{node_id} 매칭
  → [NEW] get_category_freshness(node_id)
     → 데이터 없음: _trigger_category_collection() (기존 원샷)
     → 데이터 있음: Block Kit 선택지 응답
        → [사용자 클릭: "새로 수집"]
           → amz_cat_refresh: _trigger_category_collection() → webhook → 자동 분석
        → [사용자 클릭: "캐시 사용"]
           → amz_cat_cached: run_analysis() 즉시 실행
```

### 1.3 변경 범위

| 파일 | 변경 | 규모 |
|------|------|------|
| `amz_researcher/services/product_db.py` | `get_category_freshness()` 추가 | +15줄 |
| `amz_researcher/router.py` | interact 핸들러 분기 변경 + 새 action_id 2개 | ~60줄 수정 |
| `amz_researcher/orchestrator.py` | 변경 없음 | - |
| `amz_researcher/services/cache.py` | 변경 없음 | - |
| `amz_researcher/services/bright_data.py` | 변경 없음 | - |
| `amz_researcher/services/slack_sender.py` | 변경 없음 | - |

---

## 2. Detailed Design

### 2.1 `product_db.py` — `get_category_freshness()` 추가

```python
def get_category_freshness(self, node_id: str) -> dict | None:
    """카테고리 데이터 freshness 조회.

    Returns:
        {"product_count": int, "collected_at": datetime} or None
    """
    query = """
        SELECT COUNT(*) as product_count,
               MAX(p.collected_at) as collected_at
        FROM amz_products p
        JOIN amz_product_categories pc ON p.asin = pc.asin
        WHERE pc.category_node_id = %s
    """
    try:
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query, (node_id,))
    except Exception:
        logger.exception("Failed to get freshness for category %s", node_id)
        return None
    if df.empty:
        return None
    row = df.iloc[0]
    count = int(row["product_count"])
    if count == 0 or row["collected_at"] is None:
        return None
    return {"product_count": count, "collected_at": row["collected_at"]}
```

**설계 근거:**
- `cache.py`의 `_get_data_freshness()`는 `category_name` 기반이라 node_id로 직접 조회하는 별도 메서드 필요
- `amz_product_categories` 테이블에 `category_node_id` 인덱스가 있어 ms 단위 응답
- `collected_at`이 NULL이거나 count=0이면 None 반환 (미수집 분기로 처리)

### 2.2 `router.py` — interact 핸들러 변경

#### 2.2.1 기존 `amz_category_{node_id}` 핸들러 변경

**현재 코드** (`router.py:502-512`):
```python
# 카테고리 BSR 분석
node_id = value.get("node_id")
name = value.get("name")
response_url = value["response_url"]
channel_id = value["channel_id"]

background_tasks.add_task(run_analysis, node_id, name, response_url, channel_id, user_id)
return {
    "response_type": "ephemeral",
    "text": f"📊 *{name}* BSR Top 100 분석 시작...",
}
```

**변경 후:**
```python
# 카테고리 BSR 분석 — freshness 확인 후 선택지 제시
node_id = value.get("node_id")
name = value.get("name")
response_url = value["response_url"]
channel_id = value["channel_id"]

product_db = ProductDBService("CFO")
freshness = product_db.get_category_freshness(node_id)

if freshness is None:
    # 미수집 카테고리 → 바로 수집 트리거 (기존 원샷 동작)
    background_tasks.add_task(
        _trigger_category_collection, node_id, name,
        response_url, channel_id, user_id,
    )
    return {
        "response_type": "ephemeral",
        "text": f"📡 *{name}* 데이터가 없습니다. 수집을 시작합니다...",
    }

# 캐시 있음 → 선택지 제시
return _build_category_options(
    node_id, name, freshness, response_url, channel_id,
)
```

#### 2.2.2 새 action_id 핸들러 2개 추가

interact 핸들러에 기존 키워드 분기 아래, 카테고리 분기 위에 삽입:

```python
# 카테고리: 새로 수집 후 분석
if action_id == "amz_cat_refresh":
    node_id = value["node_id"]
    name = value["name"]
    response_url = value["response_url"]
    channel_id = value["channel_id"]
    background_tasks.add_task(
        _trigger_category_collection, node_id, name,
        response_url, channel_id, user_id,
    )
    return {
        "response_type": "ephemeral",
        "text": f"📡 *{name}* 새로 수집 시작... 완료 시 자동으로 분석 결과를 보내드립니다.",
    }

# 카테고리: 캐시 사용 분석
if action_id == "amz_cat_cached":
    node_id = value["node_id"]
    name = value["name"]
    response_url = value["response_url"]
    channel_id = value["channel_id"]
    background_tasks.add_task(
        run_analysis, node_id, name, response_url, channel_id, user_id,
    )
    return {
        "response_type": "ephemeral",
        "text": f"📊 *{name}* 기존 데이터로 분석 시작... 완료 시 채널에 결과가 공유됩니다.",
    }
```

#### 2.2.3 Block Kit 선택지 빌더 함수

```python
def _build_category_options(
    node_id: str,
    name: str,
    freshness: dict,
    response_url: str,
    channel_id: str,
) -> dict:
    """카테고리 freshness 기반 '새로 수집' / '캐시 사용' 선택지 Block Kit 응답."""
    from datetime import datetime

    collected_at = freshness["collected_at"]
    product_count = freshness["product_count"]
    days_ago = (datetime.now() - collected_at).days

    if days_ago == 0:
        age_text = "오늘"
    else:
        age_text = f"{days_ago}일 전"

    payload = json.dumps({
        "node_id": node_id,
        "name": name,
        "response_url": response_url,
        "channel_id": channel_id,
    })

    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":mag: *{name}*\n"
                        f"현재 데이터: {product_count}개 제품, {age_text} 수집"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "새로 수집 후 분석"},
                        "action_id": "amz_cat_refresh",
                        "value": payload,
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": f"캐시 사용 ({age_text})",
                        },
                        "action_id": "amz_cat_cached",
                        "value": payload,
                    },
                ],
            },
        ],
    }
```

---

## 3. Action ID 맵 (전체)

| action_id | 기존/신규 | 동작 |
|-----------|-----------|------|
| `amz_category_{node_id}` | **변경** | freshness 조회 → 선택지 or 바로 수집 |
| `amz_cat_refresh` | **신규** | `_trigger_category_collection()` → webhook → 자동 분석 |
| `amz_cat_cached` | **신규** | `run_analysis()` 즉시 호출 |
| `amz_keyword_existing_{hash}` | 기존 유지 | 기존 키워드 데이터로 분석 |
| `amz_keyword_new` | 기존 유지 | 새 키워드 수집 |

---

## 4. Slack Block Kit 메시지 설계

### 4.1 캐시 있는 카테고리 선택 시

```
┌──────────────────────────────────────────┐
│ :mag: Hair Serums                        │
│ 현재 데이터: 98개 제품, 3일 전 수집         │
│                                          │
│ [새로 수집 후 분석]  [캐시 사용 (3일 전)]    │
│  (primary/blue)      (default/gray)      │
└──────────────────────────────────────────┘
```

### 4.2 미수집 카테고리 (데이터 없음)

선택지 없이 바로 수집 트리거 — 기존 원샷 동작과 동일:
```
📡 Hair Serums 데이터가 없습니다. 수집을 시작합니다...
```

### 4.3 오늘 수집된 경우

```
┌──────────────────────────────────────────┐
│ :mag: Hair Serums                        │
│ 현재 데이터: 98개 제품, 오늘 수집           │
│                                          │
│ [새로 수집 후 분석]  [캐시 사용 (오늘)]      │
└──────────────────────────────────────────┘
```

---

## 5. 기존 패턴과의 일관성

`/amz search` 키워드 유사 캐시 패턴 (`router.py:363-414`)과 동일한 구조:

| 요소 | 키워드 검색 (기존) | 카테고리 (신규) |
|------|-------------------|----------------|
| 트리거 | 유사 키워드 캐시 존재 | 카테고리 데이터 존재 |
| 선택지 | 기존 데이터 버튼 + 새로 수집 버튼 | 캐시 사용 버튼 + 새로 수집 버튼 |
| 새로 수집 action_id | `amz_keyword_new` | `amz_cat_refresh` |
| 캐시 사용 action_id | `amz_keyword_existing_{hash}` | `amz_cat_cached` |
| value 포맷 | `{keyword, response_url, channel_id}` | `{node_id, name, response_url, channel_id}` |

---

## 6. Edge Cases

| Case | 처리 |
|------|------|
| freshness 조회 실패 (DB 에러) | `get_category_freshness()` → None → 수집 트리거 (fail-safe) |
| 동일 카테고리 중복 수집 요청 | `_trigger_category_collection`이 snapshot_id 기반으로 콜백 관리. 중복 트리거 시 별도 snapshot 생성됨 (Bright Data 측 처리). Phase 1에서는 중복 방지 미구현 (FR-06 Low priority) |
| collected_at이 매우 오래됨 (30일+) | days_ago 표시만 변경, 별도 정책 없음. 캐시 TTL은 리포트 캐시(`cache.py`)에서 관리 |
| `_trigger_category_collection` 후 "새로 수집" 완료 전 다시 같은 카테고리 클릭 | freshness는 이전 데이터 기준. 선택지 다시 표시됨. 중복 수집 가능하나 upsert라 데이터 무결성 문제 없음 |

---

## 7. Implementation Order

| Phase | 작업 | 파일 | 의존 |
|-------|------|------|------|
| 1 | `get_category_freshness()` 메서드 추가 | `product_db.py` | 없음 |
| 2 | `_build_category_options()` 빌더 함수 추가 | `router.py` | 없음 |
| 3 | `amz_cat_refresh`, `amz_cat_cached` 핸들러 추가 | `router.py` | Phase 1 |
| 4 | 기존 `amz_category_{node_id}` 핸들러를 freshness 분기로 변경 | `router.py` | Phase 1, 2, 3 |
| 5 | curl 테스트 (interact endpoint) | - | Phase 4 |

---

## 8. Test Plan

| # | 시나리오 | 검증 |
|---|---------|------|
| 1 | 미수집 카테고리 클릭 | 바로 수집 트리거 메시지 확인 |
| 2 | 수집된 카테고리 클릭 | 선택지 Block Kit (제품수, X일전) 표시 확인 |
| 3 | "캐시 사용" 클릭 | 기존과 동일하게 분석 시작 메시지 |
| 4 | "새로 수집" 클릭 | 수집 트리거 메시지 → webhook 콜백 후 자동 분석 |
| 5 | 오늘 수집된 카테고리 | "오늘" 텍스트 표시 확인 |
| 6 | `/amz refresh` 기존 기능 | 변경 없이 정상 동작 |
| 7 | `/amz search` 기존 기능 | 변경 없이 정상 동작 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-11 | Initial design | CTO |
