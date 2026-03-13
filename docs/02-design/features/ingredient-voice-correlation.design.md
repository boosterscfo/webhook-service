# Voice-Ingredient Correlation — ODM Brief Guide: Design Document

> **Feature**: ingredient-voice-correlation
> **Plan**: `docs/01-plan/features/ingredient-voice-correlation.plan.md` (v0.3)
> **Date**: 2026-03-13
> **Status**: Design

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | PM이 ODM에 제형 방향을 전달할 때 데이터 근거 없이 감각적 요청만 가능 |
| **Solution** | Voice - 키워드별 성분 enrichment 분석 → Gemini가 ODM 브리프용 가이드 자동 생성 |
| **Function/UX Effect** | `/amz why` → 키워드 선택 → 4줄 브리프 가이드 즉시 수신 (본문) + 성분 상세 (thread) |
| **Core Value** | PM이 성분 전문가가 아니어도 데이터 기반 ODM 브리프를 작성할 수 있음 |

---

## 1. File Changes Overview

| File | Action | Description |
|------|--------|-------------|
| `amz_researcher/services/ingredient_analyzer.py` | **NEW** | INCI 파싱 + enrichment 분석 엔진 |
| `amz_researcher/services/product_db.py` | MOD | Voice 키워드 통계/조회 함수 3개 추가 |
| `amz_researcher/services/cache.py` | MOD | correlation 캐시 get/save 2개 추가 |
| `amz_researcher/services/gemini.py` | MOD | `generate_odm_brief()` 1개 추가 |
| `amz_researcher/services/slack_sender.py` | MOD | `send_with_thread()` 1개 추가 |
| `amz_researcher/router.py` | MOD | "why" subcommand + interact 핸들러 추가 |

**신규 DB 테이블**: 없음. 캐시는 기존 `amz_market_report_cache` 테이블에 `type` 컬럼 분기로 재활용하거나, 별도 `amz_correlation_cache` 테이블 생성.

---

## 2. Detailed Design

### 2.1 ingredient_analyzer.py (NEW)

순수 함수 모듈. 외부 의존성 없이 데이터만 받아 분석.

```python
"""INCI 전성분 파싱 + Voice-Ingredient enrichment 분석."""

import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


def parse_inci(raw: str) -> list[str]:
    """INCI 전성분 텍스트를 정규화된 성분 리스트로 파싱.

    Rules:
        - 쉼표 기준 분리 (fallback: 세미콜론, 슬래시)
        - 소문자 정규화, 앞뒤 공백 제거
        - 괄호 내용 제거: "water (aqua)" → "water"
        - 빈 문자열, 숫자만 있는 항목 필터
    """
    if not raw or not raw.strip():
        return []

    # 구분자 결정: 쉼표가 2개 이상이면 쉼표 기준, 아니면 세미콜론/슬래시 시도
    if raw.count(",") >= 2:
        parts = raw.split(",")
    elif raw.count(";") >= 2:
        parts = raw.split(";")
    elif raw.count("/") >= 2:
        parts = raw.split("/")
    else:
        parts = raw.split(",")

    result = []
    for part in parts:
        # 괄호 내용 제거
        cleaned = re.sub(r"\s*\([^)]*\)", "", part)
        cleaned = cleaned.strip().lower()
        # 빈 문자열, 숫자만, 너무 짧은 것(1글자) 필터
        if cleaned and len(cleaned) > 1 and not cleaned.isdigit():
            result.append(cleaned)
    return result


def analyze_voice_ingredient_correlation(
    products: list[dict],
    target_keyword: str,
    min_products: int = 3,
    min_ratio: float = 2.0,
) -> dict:
    """키워드별 성분 enrichment 분석.

    Args:
        products: [{asin, ingredients, voice_negative, bs_category}]
                  - ingredients: str (INCI raw text)
                  - voice_negative: list[str] (Voice - 키워드 리스트)
        target_keyword: 분석 대상 Voice - 키워드 (e.g., "sticky")
        min_products: 최소 제품 수 필터
        min_ratio: 최소 enrichment ratio 필터

    Returns:
        {
            "keyword": str,
            "total_products": int,        # 분석 대상 전체 제품 수
            "with_count": int,            # 키워드 보유 제품 수
            "without_count": int,         # 키워드 미보유 제품 수
            "categories_analyzed": int,   # 분석된 카테고리 수
            "enriched": [                 # ratio 높은 순 정렬, 최대 10개
                {
                    "ingredient": str,
                    "with_pct": float,    # with 그룹에서의 출현율 (0-100)
                    "without_pct": float, # without 그룹에서의 출현율 (0-100)
                    "ratio": float,       # with_pct / without_pct
                    "product_count": int, # with 그룹에서 발견된 제품 수
                    "categories": list[str],  # 출현 카테고리 목록
                },
            ],
            "safe": [                     # 키워드 무관 고빈도 성분, 최대 5개
                {
                    "ingredient": str,
                    "frequency_pct": float,  # 전체 출현율
                },
            ],
        }
    """
    keyword_lower = target_keyword.lower()

    # 1. with/without 그룹 분리 (fuzzy: contains 매칭)
    with_group = []  # target_keyword를 voice_negative에 포함하는 제품
    without_group = []
    for p in products:
        voice_neg = p.get("voice_negative") or []
        has_keyword = any(keyword_lower in kw.lower() for kw in voice_neg)
        parsed = parse_inci(p.get("ingredients") or "")
        if not parsed:
            continue
        entry = {
            "asin": p["asin"],
            "ingredients": parsed,
            "category": p.get("bs_category", "Unknown"),
        }
        if has_keyword:
            with_group.append(entry)
        else:
            without_group.append(entry)

    if len(with_group) < min_products:
        return {
            "keyword": target_keyword,
            "total_products": len(with_group) + len(without_group),
            "with_count": len(with_group),
            "without_count": len(without_group),
            "categories_analyzed": 0,
            "enriched": [],
            "safe": [],
            "error": f"표본 부족: '{target_keyword}' 포함 제품 {len(with_group)}개 (최소 {min_products}개 필요)",
        }

    # 2. 성분별 빈도 계산
    with_freq = defaultdict(lambda: {"count": 0, "categories": set()})
    without_freq = defaultdict(int)

    for entry in with_group:
        seen = set()
        for ing in entry["ingredients"]:
            if ing not in seen:
                with_freq[ing]["count"] += 1
                with_freq[ing]["categories"].add(entry["category"])
                seen.add(ing)

    for entry in without_group:
        seen = set()
        for ing in entry["ingredients"]:
            if ing not in seen:
                without_freq[ing] += 1
                seen.add(ing)

    # 3. Enrichment ratio 계산
    n_with = len(with_group)
    n_without = len(without_group)
    enriched = []

    for ing, data in with_freq.items():
        with_pct = (data["count"] / n_with) * 100
        without_count = without_freq.get(ing, 0)
        without_pct = (without_count / n_without) * 100 if n_without > 0 else 0

        # without_pct가 0이면 ratio 계산 불가 → 높은 고정값
        if without_pct == 0:
            ratio = 99.0 if with_pct > 0 else 0
        else:
            ratio = with_pct / without_pct

        if data["count"] >= min_products and ratio >= min_ratio:
            enriched.append({
                "ingredient": ing,
                "with_pct": round(with_pct, 1),
                "without_pct": round(without_pct, 1),
                "ratio": round(ratio, 1),
                "product_count": data["count"],
                "categories": sorted(data["categories"]),
            })

    enriched.sort(key=lambda x: x["ratio"], reverse=True)
    enriched = enriched[:10]

    # 4. 안전 성분 도출 (전체에서 고빈도이나 enriched에 없는 것)
    total_products = n_with + n_without
    all_freq = defaultdict(int)
    for entry in with_group + without_group:
        seen = set()
        for ing in entry["ingredients"]:
            if ing not in seen:
                all_freq[ing] += 1
                seen.add(ing)

    enriched_names = {e["ingredient"] for e in enriched}
    safe_candidates = [
        {"ingredient": ing, "frequency_pct": round((cnt / total_products) * 100, 1)}
        for ing, cnt in all_freq.items()
        if ing not in enriched_names and cnt >= total_products * 0.15
    ]
    safe_candidates.sort(key=lambda x: x["frequency_pct"], reverse=True)
    safe = safe_candidates[:5]

    # 5. 분석된 카테고리 수
    all_categories = set()
    for entry in with_group + without_group:
        all_categories.add(entry["category"])

    return {
        "keyword": target_keyword,
        "total_products": total_products,
        "with_count": n_with,
        "without_count": n_without,
        "categories_analyzed": len(all_categories),
        "enriched": enriched,
        "safe": safe,
    }
```

---

### 2.2 product_db.py (MOD) — 함수 3개 추가

기존 클래스 `ProductDBService`에 추가. 모두 **sync** 메서드 (기존 패턴 준수).

```python
def get_all_products_with_voice(self) -> list[dict]:
    """ingredients + voice_negative 모두 보유한 전체 제품 조회.

    Returns:
        [{asin, ingredients, voice_negative, bs_category}]
        - voice_negative는 list[str]로 파싱된 상태
    """
    query = """
        SELECT asin, ingredients, voice_negative, bs_category
        FROM amz_products
        WHERE ingredients IS NOT NULL AND ingredients != ''
          AND voice_negative IS NOT NULL
          AND voice_negative != CAST('null' AS JSON)
          AND JSON_LENGTH(voice_negative) > 0
    """
    try:
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query)
    except Exception:
        logger.exception("Failed to get products with voice")
        return []
    if df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        neg = row["voice_negative"]
        if isinstance(neg, str):
            neg = json.loads(neg)
        result.append({
            "asin": row["asin"],
            "ingredients": row["ingredients"],
            "voice_negative": neg or [],
            "bs_category": row["bs_category"] or "Unknown",
        })
    return result


def get_voice_keyword_stats(self) -> list[dict]:
    """Voice - 키워드 빈도 통계 (discovery 모드용).

    voice_negative는 JSON 배열이므로 Python에서 집계.

    Returns:
        [{keyword, count}] — count 내림차순, 상위 15개
    """
    products = self.get_all_products_with_voice()
    keyword_count: dict[str, int] = {}
    for p in products:
        for kw in p.get("voice_negative", []):
            kw_lower = kw.lower().strip()
            if kw_lower:
                keyword_count[kw_lower] = keyword_count.get(kw_lower, 0) + 1

    stats = [{"keyword": k, "count": v} for k, v in keyword_count.items()]
    stats.sort(key=lambda x: x["count"], reverse=True)
    return stats[:15]


def find_similar_voice_keywords(self, keyword: str) -> list[str]:
    """contains 기반 유사 Voice - 키워드 검색 (결과 없음 대응).

    Returns:
        유사 키워드 최대 5개 (빈도순)
    """
    stats = self.get_voice_keyword_stats()
    keyword_lower = keyword.lower()
    similar = [
        s["keyword"] for s in stats
        if keyword_lower in s["keyword"] or s["keyword"] in keyword_lower
    ]
    # contains 매칭 안 되면 단어 단위 부분 매칭
    if not similar:
        words = keyword_lower.split()
        similar = [
            s["keyword"] for s in stats
            if any(w in s["keyword"] for w in words)
        ]
    return similar[:5]
```

**성능 참고**: `get_voice_keyword_stats()`와 `find_similar_voice_keywords()`는 `get_all_products_with_voice()`를 호출하므로, discovery 모드에서 전체 제품을 조회한다. ~410개 제품이므로 1-2초 이내. 향후 캐시 적용 가능하지만 V1에서는 불필요.

---

### 2.3 cache.py (MOD) — 함수 2개 추가

기존 `CacheService` 클래스에 추가. `amz_market_report_cache` 테이블 패턴 재활용.

**캐시 저장소**: 별도 테이블 `amz_correlation_cache` 생성.

```sql
CREATE TABLE IF NOT EXISTS amz_correlation_cache (
    keyword VARCHAR(100) PRIMARY KEY,
    result_json LONGTEXT NOT NULL,
    generated_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

```python
CORRELATION_CACHE_TTL_HOURS = 24


def get_correlation_cache(self, keyword: str) -> dict | None:
    """24h TTL 기준 correlation 분석 결과 캐시 조회.

    Returns:
        캐시된 분석 결과 dict 또는 None (미스/만료)
    """
    cutoff = datetime.now() - timedelta(hours=CORRELATION_CACHE_TTL_HOURS)
    query = (
        "SELECT result_json, generated_at FROM amz_correlation_cache "
        "WHERE keyword = %s AND generated_at >= %s"
    )
    try:
        with MysqlConnector(self._env) as conn:
            df = conn.read_query_table(query, (keyword.lower(), cutoff))
        if df.empty:
            return None
        return json.loads(df.iloc[0]["result_json"])
    except Exception:
        logger.exception("Failed to read correlation cache")
        return None


def save_correlation_cache(self, keyword: str, result: dict) -> None:
    """Correlation 분석 결과를 캐시에 저장 (upsert)."""
    if not result:
        return
    rows = [{
        "keyword": keyword.lower(),
        "result_json": json.dumps(result, ensure_ascii=False),
        "generated_at": datetime.now(),
    }]
    try:
        df = pd.DataFrame(rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df, "amz_correlation_cache")
        logger.info("Correlation cache saved: keyword=%s", keyword)
    except Exception:
        logger.exception("Failed to save correlation cache")
```

---

### 2.4 gemini.py (MOD) — generate_odm_brief() 추가

기존 `GeminiService` 클래스에 추가. Flash 모델 사용 (비용 최소화).

```python
async def generate_odm_brief(
    self,
    keyword: str,
    enriched: list[dict],
    safe: list[dict],
    stats: dict,
) -> dict:
    """Enrichment 결과를 PM용 ODM 브리프 가이드로 변환.

    Args:
        keyword: Voice - 키워드 (e.g., "sticky")
        enriched: enrichment 상위 성분 리스트 [{ingredient, ratio, categories, ...}]
        safe: 안전 성분 리스트 [{ingredient, frequency_pct}]
        stats: {total_products, with_count, categories_analyzed}

    Returns:
        {
            "cause": "고분자 보습제 + 중량 유화제 조합이 끈적임의 주 원인",
            "brief": "저분자 보습 베이스, 경량 유화 시스템 요청",
            "avoid": "고분자 HA + 레시틴 계열 유화제 동시 사용",
            "safe_combo": "나이아신아마이드, 스쿠알란, 센텔라 베이스",
            "detail": "... (thread용 상세 해석, 2-3 문단)"
        }
    """
    enriched_lines = "\n".join(
        f"- {e['ingredient']} (ratio: {e['ratio']}x, "
        f"카테고리: {', '.join(e['categories'])})"
        for e in enriched
    )
    safe_lines = "\n".join(
        f"- {s['ingredient']} (출현율: {s['frequency_pct']}%)"
        for s in safe
    )

    prompt = f"""너는 화장품 제형 전문가이다. 아래 데이터를 기반으로
제품 기획자(PM)가 ODM에 전달할 브리프 가이드를 작성하라.

PM은 성분 전문가가 아니다. 개별 성분명(INCI) 대신
기능적 분류(고분자 보습제, 경량 유화제, 점증제 등)로
묶어서 설명하라.

## 입력 데이터
키워드: "{keyword}"
분석 대상: {stats['total_products']}개 제품, {stats['with_count']}개에서 "{keyword}" 발견

의심 성분 (enrichment ratio 높은 순):
{enriched_lines}

안전 성분 (해당 키워드와 무관):
{safe_lines}

## 출력 형식 (JSON)
{{
  "cause": "[이 키워드의 주 원인 패턴 — 기능 분류로, 1줄]",
  "brief": "[ODM에 전달할 제형 방향 — 복붙 가능한 톤, 1줄]",
  "avoid": "[회피해야 할 성분 조합 — 기능 분류로, 1줄]",
  "safe_combo": "[사용해도 안전한 성분 베이스 — 기능 분류로, 1줄]",
  "detail": "[상세 해석 — 왜 이 패턴이 문제인지, 어떤 대안이 있는지, 2-3문단]"
}}

## 규칙
- 확실하지 않으면 언급하지 마라
- 추측이나 일반론 금지, 위 데이터에 근거한 해석만
- 성분의 기능 분류가 불분명하면 "미분류"로 표기
- cause/brief/avoid/safe_combo는 각각 반드시 1줄로"""

    for attempt in range(2):
        try:
            resp = await self.client.post(
                self.url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 4096,
                        "responseMimeType": "application/json",
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if not text:
                logger.warning("Empty ODM brief response (attempt %d)", attempt + 1)
                continue
            result = json.loads(text)
            logger.info("ODM brief generated for '%s'", keyword)
            return result
        except Exception:
            if attempt == 0:
                logger.warning("ODM brief generation failed, retrying")
                continue
            logger.exception("ODM brief generation failed after retries")

    # Fallback: Gemini 실패 시 기본값
    return {
        "cause": "분석 데이터를 기반으로 자동 해석을 생성하지 못했습니다",
        "brief": "상세 성분 데이터를 참고하여 ODM과 직접 논의하세요",
        "avoid": "thread의 성분 상세 테이블을 참고하세요",
        "safe_combo": ", ".join(s["ingredient"] for s in safe[:5]),
        "detail": "",
    }
```

---

### 2.5 slack_sender.py (MOD) — send_with_thread() 추가

본문 메시지 전송 후 thread_ts를 받아 thread에 상세 메시지를 전송하는 메서드.

```python
async def send_with_thread(
    self,
    channel_id: str,
    main_text: str,
    thread_text: str,
    main_blocks: list[dict] | None = None,
    thread_blocks: list[dict] | None = None,
) -> None:
    """본문 메시지 전송 후, 같은 thread에 상세 메시지 전송.

    1. chat.postMessage로 본문 전송 → ts 획득
    2. ts를 thread_ts로 사용하여 thread에 상세 전송
    """
    if not channel_id or not self.bot_token:
        logger.warning("No channel_id or bot_token for thread message")
        return

    headers = {
        "Authorization": f"Bearer {self.bot_token}",
        "Content-Type": "application/json",
    }

    try:
        # 1. 본문 전송
        main_body: dict = {"channel": channel_id, "text": main_text}
        if main_blocks:
            main_body["blocks"] = main_blocks
        resp = await self.client.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=main_body,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.error("Main message failed: %s", data.get("error"))
            return

        thread_ts = data.get("ts")
        if not thread_ts:
            logger.error("No ts in main message response")
            return

        # 2. Thread에 상세 전송
        thread_body: dict = {
            "channel": channel_id,
            "text": thread_text,
            "thread_ts": thread_ts,
        }
        if thread_blocks:
            thread_body["blocks"] = thread_blocks
        resp = await self.client.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=thread_body,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.error("Thread message failed: %s", data.get("error"))
    except Exception:
        logger.exception("Failed to send message with thread")
```

---

### 2.6 router.py (MOD) — "why" subcommand + interact 핸들러

#### 2.6.1 Subcommand 분기 추가

기존 subcommand 파싱 로직에 `"why"` 분기 추가:

```python
# 기존 subcommand 분기 내에 추가
if subcommand == "why":
    keyword = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
    if not keyword:
        # Discovery 모드
        background_tasks.add_task(
            _handle_why_discovery, response_url, channel_id
        )
        return {"response_type": "ephemeral", "text": "🔬 Voice(-) 키워드 목록 로딩 중..."}
    else:
        # 분석 모드
        background_tasks.add_task(
            _handle_why_analysis, keyword, response_url, channel_id
        )
        return {"response_type": "ephemeral", "text": f"🔬 *{keyword}* 성분 상관관계 분석 중..."}
```

#### 2.6.2 Discovery 모드 핸들러

```python
async def _handle_why_discovery(response_url: str, channel_id: str) -> None:
    """Voice - 키워드 빈도 Top 15를 Block Kit 버튼으로 표시."""
    db = ProductDBService()
    stats = db.get_voice_keyword_stats()

    if not stats:
        slack = SlackSender(settings.AMZ_BOT_TOKEN)
        try:
            await slack.send_message(
                response_url,
                "Voice(-) 데이터가 없습니다. `/amz {카테고리}`로 리포트를 먼저 실행하세요.",
                ephemeral=True,
                channel_id=channel_id,
            )
        finally:
            await slack.close()
        return

    buttons = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": f"{s['keyword']} ({s['count']})"},
            "action_id": f"amz_why_{s['keyword'].replace(' ', '_')}",
            "value": json.dumps({
                "keyword": s["keyword"],
                "response_url": response_url,
                "channel_id": channel_id,
            }),
        }
        for s in stats
    ]

    # Block Kit 버튼은 actions 블록당 최대 5개 → 3행으로 분리
    action_blocks = []
    for i in range(0, len(buttons), 5):
        action_blocks.append({"type": "actions", "elements": buttons[i:i + 5]})

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Voice(-) 키워드 분석"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "분석할 키워드를 선택하세요.\n또는 `/amz why {keyword}` 로 직접 검색",
            },
        },
        *action_blocks,
    ]

    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    try:
        await slack.send_message(
            response_url,
            "Voice(-) 키워드 목록",
            ephemeral=True,
            channel_id=channel_id,
            blocks=blocks,
        )
    finally:
        await slack.close()
```

#### 2.6.3 분석 모드 핸들러

```python
async def _handle_why_analysis(
    keyword: str, response_url: str, channel_id: str
) -> None:
    """키워드별 성분 상관관계 분석 → ODM 브리프 가이드 반환."""
    db = ProductDBService()
    cache = CacheService()
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    try:
        # 1. 캐시 확인
        cached = cache.get_correlation_cache(keyword)
        if cached:
            logger.info("Correlation cache hit: %s", keyword)
            await _send_why_result(slack, channel_id, cached)
            return

        # 2. 데이터 조회 + 분석
        products = db.get_all_products_with_voice()
        if not products:
            await slack.send_message(
                response_url,
                "분석 가능한 제품이 없습니다. 리포트를 먼저 실행하세요.",
                ephemeral=True, channel_id=channel_id,
            )
            return

        result = analyze_voice_ingredient_correlation(products, keyword)

        # 3. 결과 없음 → 유사 키워드 제안
        if not result.get("enriched"):
            similar = db.find_similar_voice_keywords(keyword)
            if similar:
                buttons = [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": kw},
                        "action_id": f"amz_why_{kw.replace(' ', '_')}",
                        "value": json.dumps({
                            "keyword": kw,
                            "response_url": response_url,
                            "channel_id": channel_id,
                        }),
                    }
                    for kw in similar
                ]
                error_msg = result.get("error", f"'{keyword}' 결과 없음")
                blocks = [
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ {error_msg}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": "유사 키워드:"}},
                    {"type": "actions", "elements": buttons},
                ]
                await slack.send_message(
                    response_url, error_msg,
                    ephemeral=True, channel_id=channel_id, blocks=blocks,
                )
            else:
                await slack.send_message(
                    response_url,
                    f"⚠️ '{keyword}' 관련 데이터가 부족합니다.",
                    ephemeral=True, channel_id=channel_id,
                )
            return

        # 4. Gemini ODM 브리프 생성
        gemini = GeminiService(settings.GEMINI_API_KEY)
        try:
            brief = await gemini.generate_odm_brief(
                keyword=keyword,
                enriched=result["enriched"],
                safe=result["safe"],
                stats={
                    "total_products": result["total_products"],
                    "with_count": result["with_count"],
                    "categories_analyzed": result["categories_analyzed"],
                },
            )
        finally:
            await gemini.client.aclose()

        # 5. 캐시 저장
        full_result = {**result, "brief": brief}
        cache.save_correlation_cache(keyword, full_result)

        # 6. 메시지 전송
        await _send_why_result(slack, channel_id, full_result)

    except Exception:
        logger.exception("Why analysis failed for '%s'", keyword)
        await slack.send_message(
            response_url,
            f"⚠️ '{keyword}' 분석 중 오류가 발생했습니다.",
            ephemeral=True, channel_id=channel_id,
        )
    finally:
        await slack.close()
```

#### 2.6.4 결과 전송 (본문 + thread)

```python
async def _send_why_result(
    slack: SlackSender, channel_id: str, result: dict
) -> None:
    """분석 결과를 본문(브리프 가이드) + thread(성분 상세)로 전송."""
    keyword = result["keyword"]
    brief = result.get("brief", {})

    # === 본문: ODM 브리프 가이드 ===
    main_text = (
        f"🔬 *\"{keyword}\" — ODM 브리프 가이드*\n"
        f"{result.get('categories_analyzed', 0)}개 카테고리, "
        f"{result.get('total_products', 0)}개 제품 분석 "
        f"({result.get('with_count', 0)}개에서 \"{keyword}\" 발견)\n\n"
        f"💡 *핵심*: {brief.get('cause', '-')}\n"
        f"📋 *브리프 제안*: \"{brief.get('brief', '-')}\"\n"
        f"⚠️ *피할 패턴*: {brief.get('avoid', '-')}\n"
        f"✅ *안전 조합*: {brief.get('safe_combo', '-')}\n\n"
        f"_🧵 성분 상세 분석은 thread 참조_"
    )

    # === Thread: 성분 상세 ===
    enriched = result.get("enriched", [])
    table_lines = ["| 성분 | 기능 분류 | Ratio | 제품수 | 카테고리 |",
                    "|------|----------|-------|--------|---------|"]
    for e in enriched:
        cats = ", ".join(e["categories"])
        table_lines.append(
            f"| {e['ingredient']} | - | {e['ratio']}x | {e['product_count']} | {cats} |"
        )

    safe_list = result.get("safe", [])
    safe_str = ", ".join(f"{s['ingredient']} ({s['frequency_pct']}%)" for s in safe_list)

    detail_text = brief.get("detail", "")

    thread_text = (
        f"═══ \"{keyword}\" 성분 상관관계 상세 ═══\n\n"
        f"{chr(10).join(table_lines)}\n\n"
        f"═══ 상세 해석 ═══\n\n"
        f"> {detail_text}\n\n"
        f"═══ 안전 성분 (\"{keyword}\" 무관) ═══\n\n"
        f"{safe_str}\n\n"
        f"_⚠️ 상관관계 ≠ 인과관계. 제형 결정 시 참고용._"
    )

    await slack.send_with_thread(
        channel_id=channel_id,
        main_text=main_text,
        thread_text=thread_text,
    )
```

#### 2.6.5 Interact 핸들러 확장

기존 `/slack/amz/interact` 핸들러에 `amz_why_` prefix 처리 추가:

```python
# 기존 interact 핸들러 내 action_id 분기에 추가
if action_id.startswith("amz_why_"):
    value = json.loads(action["value"])
    keyword = value["keyword"]
    resp_url = value["response_url"]
    ch_id = value["channel_id"]
    background_tasks.add_task(_handle_why_analysis, keyword, resp_url, ch_id)
    return {"text": f"🔬 *{keyword}* 분석 시작..."}
```

---

## 3. DB Migration

```sql
-- amz_correlation_cache 테이블 생성
CREATE TABLE IF NOT EXISTS amz_correlation_cache (
    keyword VARCHAR(100) NOT NULL,
    result_json LONGTEXT NOT NULL,
    generated_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (keyword)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 4. Implementation Order

| Phase | File | Task | 의존성 |
|-------|------|------|--------|
| 1 | `ingredient_analyzer.py` | parse_inci() + analyze_voice_ingredient_correlation() | 없음 |
| 2 | `product_db.py` | get_all_products_with_voice(), get_voice_keyword_stats(), find_similar_voice_keywords() | 없음 |
| 3 | DB | amz_correlation_cache 테이블 생성 | 없음 |
| 3 | `cache.py` | get_correlation_cache(), save_correlation_cache() | DB 테이블 |
| 4 | `gemini.py` | generate_odm_brief() | 없음 |
| 5 | `slack_sender.py` | send_with_thread() | 없음 |
| 6 | `router.py` | "why" subcommand + interact + 결과 포맷팅 | Phase 1-5 전체 |
| 7 | E2E 테스트 | `/amz why`, `/amz why sticky`, 캐시 시나리오 | Phase 6 |

---

## 5. Error Handling

| Scenario | Handling |
|----------|----------|
| ingredients/voice_negative 데이터 없음 | "리포트를 먼저 실행하세요" 안내 메시지 |
| 키워드 매칭 제품 < 3개 | "표본 부족" 메시지 + 유사 키워드 제안 |
| Gemini API 실패 | Fallback dict 반환 (성분 상세 테이블은 정상 표시) |
| 캐시 읽기/쓰기 실패 | 무시하고 실시간 분석 진행 (graceful degradation) |
| SlackSender thread 전송 실패 | 로그 기록, 사용자에게 에러 노출 안 함 |

---

## 6. Testing Checklist

- [ ] `parse_inci()`: 쉼표/세미콜론/괄호 케이스 검증
- [ ] `analyze_voice_ingredient_correlation()`: Facial Serums "sticky" 프로토타입 데이터로 enriched 결과 확인
- [ ] `get_all_products_with_voice()`: curl로 API 호출 → 410개 근처 결과 확인
- [ ] `/amz why` (discovery): Block Kit 버튼 15개 표시 확인
- [ ] `/amz why sticky` (분석): 본문 4줄 + thread 상세 확인
- [ ] `/amz why xyzabc` (결과 없음): 유사 키워드 버튼 제안 확인
- [ ] 캐시 히트: 동일 키워드 2회 조회 시 1초 이내 응답
- [ ] Gemini 실패 시: fallback 메시지 + 성분 테이블은 정상 표시
