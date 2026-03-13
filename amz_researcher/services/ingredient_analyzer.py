"""INCI 전성분 파싱 + Voice-Ingredient enrichment 분석."""

import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


def parse_inci(raw: str) -> list[str]:
    """INCI 전성분 텍스트를 정규화된 성분 리스트로 파싱.

    Rules:
        - 쉼표 기준 분리 (fallback: 세미콜론)
        - 소문자 정규화, 앞뒤 공백 제거
        - 괄호 내용 제거: "water (aqua)" -> "water"
        - 빈 문자열, 숫자만 있는 항목 필터
    """
    if not raw or not raw.strip():
        return []

    if raw.count(",") >= 2:
        parts = raw.split(",")
    elif raw.count(";") >= 2:
        parts = raw.split(";")
    else:
        parts = raw.split(",")

    result = []
    for part in parts:
        cleaned = re.sub(r"\s*\([^)]*\)", "", part)
        cleaned = cleaned.strip().lower()
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
        target_keyword: 분석 대상 Voice - 키워드 (e.g., "sticky")
        min_products: 최소 제품 수 필터
        min_ratio: 최소 enrichment ratio 필터

    Returns:
        분석 결과 dict (enriched, safe, stats 포함)
    """
    keyword_lower = target_keyword.lower()

    # 1. with/without 그룹 분리 (fuzzy: contains 매칭)
    with_group = []
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
            "error": (
                f"표본 부족: '{target_keyword}' 포함 제품 "
                f"{len(with_group)}개 (최소 {min_products}개 필요)"
            ),
        }

    # 2. 성분별 빈도 계산
    with_freq: dict[str, dict] = defaultdict(lambda: {"count": 0, "categories": set()})
    without_freq: dict[str, int] = defaultdict(int)

    for entry in with_group:
        seen: set[str] = set()
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

    # 4. 안전 성분 도출
    total_products = n_with + n_without
    all_freq: dict[str, int] = defaultdict(int)
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

    # 5. 카테고리 수
    all_categories: set[str] = set()
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
