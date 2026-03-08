"""시장 분석 데이터 생성.

WeightedProduct + ProductDetail 데이터를 기반으로
가격대별/BSR별/브랜드별/성분조합 분석을 수행한다.
"""

from collections import Counter, defaultdict

from amz_researcher.models import (
    ProductDetail,
    WeightedProduct,
)
from amz_researcher.services.analyzer import _get_display_name


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
            tier_ingredients[tier][_get_display_name(ing)] += 1

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
            top_counter[_get_display_name(ing)] += 1
    for p in bottom_group:
        for ing in p.ingredients:
            bottom_counter[_get_display_name(ing)] += 1

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
            bd["ingredients"][_get_display_name(ing)] += 1

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
        names = sorted(set(_get_display_name(ing) for ing in p.ingredients))
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


def analyze_brand_positioning(
    products: list[WeightedProduct],
    details: list[ProductDetail],
) -> list[dict]:
    """브랜드 포지셔닝: 가격 vs BSR."""
    detail_map = {d.asin: d for d in details}
    brand_data: dict[str, dict] = defaultdict(lambda: {
        "prices": [], "bsr_values": [], "ratings": [], "reviews": [],
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
        bd["reviews"].append(p.reviews)
        if p.bsr_category is not None:
            bd["bsr_values"].append(p.bsr_category)

    result = []
    for brand, bd in brand_data.items():
        prices = bd["prices"]
        bsr_vals = bd["bsr_values"]
        if not prices or not bsr_vals:
            continue
        avg_price = round(sum(prices) / len(prices), 2)
        result.append({
            "brand": brand,
            "product_count": bd["product_count"],
            "avg_price": avg_price,
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)),
            "avg_rating": round(sum(bd["ratings"]) / len(bd["ratings"]), 2),
            "total_reviews": sum(bd["reviews"]),
            "segment": _price_tier(avg_price),
        })

    result.sort(key=lambda x: x["avg_bsr"])
    return result


def detect_rising_products(
    products: list[WeightedProduct],
    details: list[ProductDetail],
) -> list[dict]:
    """신제품/급성장 제품 탐지: 리뷰 적지만 BSR 좋은 제품."""
    detail_map = {d.asin: d for d in details}
    median_reviews = sorted(p.reviews for p in products)[len(products) // 2]
    threshold = min(median_reviews, 2000)

    rising = []
    for p in products:
        if p.bsr_category is None or p.reviews >= threshold:
            continue
        if p.bsr_category > 10000:
            continue
        d = detail_map.get(p.asin)
        brand = d.brand if d and d.brand else "Unknown"
        ingredients_top3 = ", ".join(
            ing.common_name or ing.name for ing in p.ingredients[:3]
        )
        rising.append({
            "asin": p.asin,
            "title": p.title[:80],
            "brand": brand,
            "price": p.price,
            "reviews": p.reviews,
            "rating": p.rating,
            "bsr": p.bsr_category,
            "top_ingredients": ingredients_top3,
        })

    rising.sort(key=lambda x: x["bsr"])
    return rising[:15]


def analyze_rating_ingredients(
    products: list[WeightedProduct],
) -> dict:
    """고평점(4.5+) vs 저평점(<4.3) 제품의 성분 비교."""
    high_counter: Counter = Counter()
    low_counter: Counter = Counter()
    high_count = 0
    low_count = 0

    for p in products:
        names = [_get_display_name(ing) for ing in p.ingredients]
        if p.rating >= 4.5:
            high_count += 1
            for n in names:
                high_counter[n] += 1
        elif p.rating < 4.3:
            low_count += 1
            for n in names:
                low_counter[n] += 1

    high_only = [
        {"name": name, "count": count}
        for name, count in high_counter.most_common()
        if name not in low_counter and count >= 3
    ][:10]

    low_only = [
        {"name": name, "count": count}
        for name, count in low_counter.most_common()
        if name not in high_counter and count >= 2
    ][:10]

    return {
        "high_rated_count": high_count,
        "low_rated_count": low_count,
        "high_only_ingredients": high_only,
        "low_only_ingredients": low_only,
        "high_top10": [
            {"name": n, "count": c} for n, c in high_counter.most_common(10)
        ],
        "low_top10": [
            {"name": n, "count": c} for n, c in low_counter.most_common(10)
        ],
    }


# ── V4 신규 분석 ──────────────────────────────────────────


def analyze_sns_pricing(products: list[WeightedProduct]) -> dict:
    """Subscribe & Save 할인 분석."""
    with_sns = [p for p in products if p.sns_price is not None and p.price]
    without_sns = [p for p in products if p.sns_price is None]

    discounts = []
    for p in with_sns:
        discount_pct = (1 - p.sns_price / p.price) * 100 if p.price > 0 else 0
        discounts.append({
            "asin": p.asin,
            "title": p.title[:60],
            "price": p.price,
            "sns_price": p.sns_price,
            "discount_pct": round(discount_pct, 1),
        })
    discounts.sort(key=lambda x: x["discount_pct"], reverse=True)

    avg_discount = (
        round(sum(d["discount_pct"] for d in discounts) / len(discounts), 1)
        if discounts else 0
    )

    return {
        "total_products": len(products),
        "with_sns_count": len(with_sns),
        "without_sns_count": len(without_sns),
        "sns_adoption_pct": round(len(with_sns) / len(products) * 100, 1) if products else 0,
        "avg_discount_pct": avg_discount,
        "top_discounts": discounts[:10],
    }


def analyze_competition(products: list[WeightedProduct]) -> dict:
    """판매자 수 기반 경쟁 강도 분석."""
    seller_counts = [p.number_of_sellers for p in products]
    if not seller_counts:
        return {}

    single_seller = sum(1 for s in seller_counts if s <= 1)
    multi_seller = sum(1 for s in seller_counts if s > 1)
    high_competition = sum(1 for s in seller_counts if s >= 5)

    return {
        "total_products": len(products),
        "single_seller_count": single_seller,
        "multi_seller_count": multi_seller,
        "high_competition_count": high_competition,
        "avg_sellers": round(sum(seller_counts) / len(seller_counts), 1),
        "max_sellers": max(seller_counts),
    }


def analyze_promotions(products: list[WeightedProduct]) -> dict:
    """쿠폰/프로모션 분석."""
    with_coupon = [p for p in products if p.coupon]
    with_plus = [p for p in products if p.plus_content]

    coupon_types: Counter = Counter()
    for p in with_coupon:
        coupon_types[p.coupon] += 1

    # 쿠폰 유무에 따른 평균 BSR 비교
    coupon_bsr = [p.bsr_category for p in with_coupon if p.bsr_category is not None]
    no_coupon_bsr = [
        p.bsr_category for p in products
        if not p.coupon and p.bsr_category is not None
    ]

    return {
        "total_products": len(products),
        "coupon_count": len(with_coupon),
        "coupon_pct": round(len(with_coupon) / len(products) * 100, 1) if products else 0,
        "plus_content_count": len(with_plus),
        "plus_content_pct": round(len(with_plus) / len(products) * 100, 1) if products else 0,
        "coupon_types": [
            {"coupon": c, "count": n} for c, n in coupon_types.most_common(10)
        ],
        "avg_bsr_with_coupon": (
            round(sum(coupon_bsr) / len(coupon_bsr)) if coupon_bsr else None
        ),
        "avg_bsr_without_coupon": (
            round(sum(no_coupon_bsr) / len(no_coupon_bsr)) if no_coupon_bsr else None
        ),
    }


def analyze_sales_volume(products: list[WeightedProduct]) -> dict:
    """월간 판매량(bought_past_month) 분석."""
    with_sales = [p for p in products if p.bought_past_month is not None]
    if not with_sales:
        return {}

    total_sales = sum(p.bought_past_month for p in with_sales)
    with_sales.sort(key=lambda p: p.bought_past_month, reverse=True)

    top_sellers = [
        {
            "asin": p.asin,
            "title": p.title[:60],
            "brand": p.brand,
            "bought_past_month": p.bought_past_month,
            "price": p.price,
            "bsr": p.bsr_category,
        }
        for p in with_sales[:10]
    ]

    # 가격대별 판매량
    tier_sales: dict[str, list[int]] = defaultdict(list)
    for p in with_sales:
        tier = _price_tier(p.price)
        tier_sales[tier].append(p.bought_past_month)

    tier_summary = {
        tier: {
            "count": len(sales),
            "total_sales": sum(sales),
            "avg_sales": round(sum(sales) / len(sales)),
        }
        for tier, sales in tier_sales.items()
    }

    return {
        "total_products_with_data": len(with_sales),
        "total_monthly_sales": total_sales,
        "avg_monthly_sales": round(total_sales / len(with_sales)),
        "top_sellers": top_sellers,
        "sales_by_price_tier": tier_summary,
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
        "brand_positioning": analyze_brand_positioning(weighted_products, details),
        "rising_products": detect_rising_products(weighted_products, details),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
        # V4 신규 분석
        "sales_volume": analyze_sales_volume(weighted_products),
        "sns_pricing": analyze_sns_pricing(weighted_products),
        "competition": analyze_competition(weighted_products),
        "promotions": analyze_promotions(weighted_products),
    }
