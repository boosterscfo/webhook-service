"""제품 기획팀용 시장 분석 데이터 생성.

WeightedProduct + ProductDetail 데이터를 기반으로
가격대별/BSR별/브랜드별/성분조합 분석을 수행한다.
"""

from collections import Counter, defaultdict

from amz_researcher.models import (
    ProductDetail,
    WeightedProduct,
)


def _price_tier(price: float | None) -> str:
    if price is None:
        return "Unknown"
    if price < 10:
        return "Budget (<$10)"
    if price < 25:
        return "Mid ($10-25)"
    if price < 50:
        return "Premium ($25-50)"
    return "Luxury ($50+)"


def analyze_by_price_tier(
    products: list[WeightedProduct],
) -> dict:
    """가격대별 주요 성분 Top 5 비교."""
    tier_ingredients: dict[str, Counter] = defaultdict(Counter)
    tier_counts: dict[str, int] = Counter()

    for p in products:
        tier = _price_tier(p.price)
        tier_counts[tier] += 1
        for ing in p.ingredients:
            tier_ingredients[tier][ing.name] += 1

    result = {}
    for tier in ["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]:
        top5 = tier_ingredients[tier].most_common(5)
        result[tier] = {
            "product_count": tier_counts[tier],
            "top_ingredients": [
                {"name": name, "count": count} for name, count in top5
            ],
        }
    return result


def analyze_by_bsr(
    products: list[WeightedProduct],
) -> dict:
    """BSR 상위 20% vs 하위 20% 성분 비교."""
    with_bsr = [p for p in products if p.bsr_category is not None]
    if len(with_bsr) < 5:
        return {"top": [], "bottom": [], "winning_ingredients": []}

    with_bsr.sort(key=lambda p: p.bsr_category)
    cutoff = max(len(with_bsr) // 5, 1)
    top_group = with_bsr[:cutoff]
    bottom_group = with_bsr[-cutoff:]

    top_counter: Counter = Counter()
    bottom_counter: Counter = Counter()
    for p in top_group:
        for ing in p.ingredients:
            top_counter[ing.name] += 1
    for p in bottom_group:
        for ing in p.ingredients:
            bottom_counter[ing.name] += 1

    winning = [
        name for name, _ in top_counter.most_common()
        if name not in bottom_counter
    ]

    return {
        "top_count": len(top_group),
        "bottom_count": len(bottom_group),
        "top": [{"name": n, "count": c} for n, c in top_counter.most_common(10)],
        "bottom": [{"name": n, "count": c} for n, c in bottom_counter.most_common(10)],
        "winning_ingredients": winning[:10],
    }


def analyze_by_brand(
    products: list[WeightedProduct],
    details: list[ProductDetail],
) -> list[dict]:
    """브랜드별 핵심 성분 프로파일."""
    detail_map = {d.asin: d for d in details}

    brand_data: dict[str, dict] = defaultdict(lambda: {
        "prices": [],
        "ratings": [],
        "bsr_values": [],
        "ingredients": Counter(),
        "product_count": 0,
    })

    for p in products:
        d = detail_map.get(p.asin)
        brand = d.brand if d and d.brand else "Unknown"
        if brand == "Unknown":
            continue
        bd = brand_data[brand]
        bd["product_count"] += 1
        if p.price is not None:
            bd["prices"].append(p.price)
        bd["ratings"].append(p.rating)
        if p.bsr_category is not None:
            bd["bsr_values"].append(p.bsr_category)
        for ing in p.ingredients:
            bd["ingredients"][ing.name] += 1

    result = []
    for brand, bd in brand_data.items():
        if bd["product_count"] < 2:
            continue
        prices = bd["prices"]
        result.append({
            "brand": brand,
            "product_count": bd["product_count"],
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_rating": round(sum(bd["ratings"]) / len(bd["ratings"]), 2),
            "avg_bsr": (
                round(sum(bd["bsr_values"]) / len(bd["bsr_values"]))
                if bd["bsr_values"] else None
            ),
            "top_ingredients": [
                name for name, _ in bd["ingredients"].most_common(5)
            ],
        })

    result.sort(key=lambda x: x["product_count"], reverse=True)
    return result[:15]


def analyze_cooccurrence(
    products: list[WeightedProduct],
) -> dict:
    """성분 조합 분석 — 자주 함께 쓰이는 성분 쌍."""
    pair_counter: Counter = Counter()
    high_rated_pairs: Counter = Counter()
    low_rated_pairs: Counter = Counter()

    for p in products:
        names = sorted(set(ing.name for ing in p.ingredients))
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair = (names[i], names[j])
                pair_counter[pair] += 1
                if p.rating >= 4.5:
                    high_rated_pairs[pair] += 1
                elif p.rating < 4.0:
                    low_rated_pairs[pair] += 1

    top_pairs = [
        {"pair": list(pair), "count": count}
        for pair, count in pair_counter.most_common(10)
    ]

    high_only = [
        {"pair": list(pair), "count": count}
        for pair, count in high_rated_pairs.most_common()
        if pair not in low_rated_pairs
    ][:5]

    return {
        "top_pairs": top_pairs,
        "high_rated_exclusive": high_only,
    }


def build_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    """전체 시장 분석 데이터 생성."""
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
    }
