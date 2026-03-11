"""시장 분석 데이터 생성.

WeightedProduct + ProductDetail 데이터를 기반으로
가격대별/BSR별/브랜드별/성분조합 분석을 수행한다.
"""

import re
from collections import Counter, defaultdict

from amz_researcher.models import (
    ProductDetail,
    VoiceKeywordResult,
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

    # V5: 상위/하위 BSR 통계 검증
    top_bsr = [float(p.bsr_category) for p in top_group]
    bottom_bsr = [float(p.bsr_category) for p in bottom_group]

    return {
        "top_count": len(top_group),
        "bottom_count": len(bottom_group),
        "top": [{"name": n, "count": c} for n, c in top_counter.most_common(10)],
        "bottom": [{"name": n, "count": c} for n, c in bottom_counter.most_common(10)],
        "winning_ingredients": winning[:10],
        "stat_test_bsr": _stat_compare(top_bsr, bottom_bsr),
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
    """Subscribe & Save 할인 분석 (V5 확장)."""
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

    # V5 심화: SNS 할인율 구간별 BSR 비교
    def _sns_tier(pct: float) -> str:
        if pct <= 0:
            return "No Discount"
        if pct <= 5:
            return "1-5%"
        if pct <= 10:
            return "6-10%"
        return "11%+"

    sns_tiers: dict[str, list] = defaultdict(list)
    for p in with_sns:
        pct = (1 - p.sns_price / p.price) * 100 if p.price > 0 else 0
        sns_tiers[_sns_tier(pct)].append(p)

    tier_metrics = {}
    for tier_name, group in sns_tiers.items():
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        tier_metrics[tier_name] = {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    # V5 심화: SNS 채택 vs 미채택 bought_past_month 비교
    sns_bought = [p.bought_past_month for p in with_sns if p.bought_past_month is not None]
    no_sns_bought = [p.bought_past_month for p in without_sns if p.bought_past_month is not None]

    # V5 심화: 가격대별 SNS 채택률
    price_tier_sns: dict[str, dict] = defaultdict(lambda: {"total": 0, "with_sns": 0})
    for p in products:
        tier = _price_tier(p.price)
        price_tier_sns[tier]["total"] += 1
        if p.sns_price is not None:
            price_tier_sns[tier]["with_sns"] += 1

    return {
        "total_products": len(products),
        "with_sns_count": len(with_sns),
        "without_sns_count": len(without_sns),
        "sns_adoption_pct": round(len(with_sns) / len(products) * 100, 1) if products else 0,
        "avg_discount_pct": avg_discount,
        "top_discounts": discounts[:10],
        # V5 심화
        "discount_tier_metrics": tier_metrics,
        "retention_signal": {
            "sns_avg_bought": round(sum(sns_bought) / len(sns_bought)) if sns_bought else None,
            "no_sns_avg_bought": round(sum(no_sns_bought) / len(no_sns_bought)) if no_sns_bought else None,
        },
        "price_tier_adoption": {
            tier: {
                "total": d["total"],
                "with_sns": d["with_sns"],
                "adoption_pct": round(d["with_sns"] / d["total"] * 100, 1) if d["total"] > 0 else 0,
            }
            for tier, d in price_tier_sns.items()
        },
    }


def analyze_listing_tactics(products: list[WeightedProduct]) -> dict:
    """키워드 검색 리스팅 전술 분석 — Sponsored, Coupon, A+ Content, Strikethrough 등."""
    if not products:
        return {}

    total = len(products)

    # --- Ad Pressure ---
    sponsored_products = [p for p in products if getattr(p, "sponsored", False)]
    sponsored_count = len(sponsored_products)

    # Position-group breakdown for sponsored ads
    pos_groups = [
        ("Top 10", 1, 10),
        ("11-20", 11, 20),
        ("21-30", 21, 30),
        ("31+", 31, 9999),
    ]
    ad_by_position = {}
    for label, lo, hi in pos_groups:
        in_range = [p for p in products if lo <= p.position <= hi]
        sp_in_range = [p for p in in_range if getattr(p, "sponsored", False)]
        if in_range:
            ad_by_position[label] = {
                "total": len(in_range),
                "sponsored": len(sp_in_range),
                "sponsored_pct": round(len(sp_in_range) / len(in_range) * 100, 1),
            }

    # --- Coupon & Discount ---
    with_coupon = [p for p in products if p.coupon]
    with_strikethrough = [
        p for p in products
        if p.initial_price is not None and p.price is not None and p.initial_price > p.price
    ]

    coupon_types: Counter = Counter()
    for p in with_coupon:
        coupon_types[p.coupon] += 1

    # Performance: coupon vs no-coupon avg bought
    coupon_bought = [p.bought_past_month for p in with_coupon if p.bought_past_month]
    no_coupon_bought = [p.bought_past_month for p in products if not p.coupon and p.bought_past_month]

    # --- Content Quality ---
    with_plus = [p for p in products if p.plus_content]
    reviews_list = [p.reviews for p in products if p.reviews > 0]
    ratings_list = [p.rating for p in products if p.rating > 0]

    return {
        "total_products": total,
        "ad_pressure": {
            "sponsored_count": sponsored_count,
            "sponsored_pct": round(sponsored_count / total * 100, 1),
            "by_position": ad_by_position,
        },
        "coupon_discount": {
            "coupon_count": len(with_coupon),
            "coupon_pct": round(len(with_coupon) / total * 100, 1),
            "strikethrough_count": len(with_strikethrough),
            "strikethrough_pct": round(len(with_strikethrough) / total * 100, 1),
            "top_coupons": [
                {"coupon": c, "count": n} for c, n in coupon_types.most_common(5)
            ],
            "avg_bought_with_coupon": (
                round(sum(coupon_bought) / len(coupon_bought)) if coupon_bought else None
            ),
            "avg_bought_without_coupon": (
                round(sum(no_coupon_bought) / len(no_coupon_bought)) if no_coupon_bought else None
            ),
        },
        "content_quality": {
            "plus_content_count": len(with_plus),
            "plus_content_pct": round(len(with_plus) / total * 100, 1),
            "avg_reviews": round(sum(reviews_list) / len(reviews_list)) if reviews_list else 0,
            "median_reviews": sorted(reviews_list)[len(reviews_list) // 2] if reviews_list else 0,
            "avg_rating": round(sum(ratings_list) / len(ratings_list), 2) if ratings_list else 0,
        },
    }


def analyze_promotions(products: list[WeightedProduct]) -> dict:
    """쿠폰/프로모션 분석."""
    with_coupon = [p for p in products if p.coupon]

    coupon_types: Counter = Counter()
    for p in with_coupon:
        coupon_types[p.coupon] += 1

    coupon_bsr = [p.bsr_category for p in with_coupon if p.bsr_category is not None]
    no_coupon_bsr = [
        p.bsr_category for p in products
        if not p.coupon and p.bsr_category is not None
    ]

    return {
        "total_products": len(products),
        "coupon_count": len(with_coupon),
        "coupon_pct": round(len(with_coupon) / len(products) * 100, 1) if products else 0,
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


# ── V5 신규 분석 ──────────────────────────────────────────


def _hardcoded_keyword_match(
    products: list[WeightedProduct],
) -> tuple[dict[str, list[WeightedProduct]], dict[str, list[WeightedProduct]]]:
    """기존 하드코딩 키워드 매칭. Gemini fallback용."""
    POSITIVE_KEYWORDS = [
        "effective", "moisturizing", "gentle", "lightweight", "absorbs quickly",
        "hydrating", "brightening", "smooth", "refreshing", "no irritation",
        "love", "soft", "clean", "works well", "great value",
    ]
    NEGATIVE_KEYWORDS = [
        "sticky", "strong smell", "irritation", "greasy", "breakout",
        "drying", "burning", "broke out", "allergic", "thin",
        "oily", "too thick", "stinging", "rash", "waste",
    ]
    pos_counts: dict[str, list[WeightedProduct]] = {}
    neg_counts: dict[str, list[WeightedProduct]] = {}
    for p in products:
        text = p.customer_says.lower()
        for kw in POSITIVE_KEYWORDS:
            if kw in text:
                pos_counts.setdefault(kw, []).append(p)
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                neg_counts.setdefault(kw, []).append(p)
    return pos_counts, neg_counts


def analyze_customer_voice(
    products: list[WeightedProduct],
    voice_keywords: VoiceKeywordResult | None = None,
) -> dict:
    """customer_says 키워드 빈도/감성 분석.

    voice_keywords가 있으면 Gemini 동적 키워드 사용, 없으면 하드코딩 fallback.
    """
    with_cs = [p for p in products if p.customer_says]
    if not with_cs:
        return {}

    product_map = {p.asin: p for p in with_cs}

    if voice_keywords:
        # 동적 키워드: Gemini가 반환한 ASIN 매핑 사용
        pos_counts: dict[str, list[WeightedProduct]] = {}
        for vk in voice_keywords.positive_keywords:
            matched = [product_map[a] for a in vk.asins if a in product_map]
            if matched:
                pos_counts[vk.keyword] = matched

        neg_counts: dict[str, list[WeightedProduct]] = {}
        for vk in voice_keywords.negative_keywords:
            matched = [product_map[a] for a in vk.asins if a in product_map]
            if matched:
                neg_counts[vk.keyword] = matched
    else:
        # Fallback: 기존 하드코딩 키워드
        pos_counts, neg_counts = _hardcoded_keyword_match(with_cs)

    all_keywords = list(pos_counts.keys()) + list(neg_counts.keys())

    def _kw_stats(products_with_kw: list[WeightedProduct]) -> dict:
        if not products_with_kw:
            return {"count": 0, "avg_bsr": None, "avg_rating": None}
        bsr_vals = [p.bsr_category for p in products_with_kw if p.bsr_category is not None]
        return {
            "count": len(products_with_kw),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_rating": round(
                sum(p.rating for p in products_with_kw) / len(products_with_kw), 2
            ),
        }

    sorted_by_bsr = sorted(
        [p for p in with_cs if p.bsr_category is not None],
        key=lambda p: p.bsr_category,
    )
    mid = len(sorted_by_bsr) // 2
    top_half = sorted_by_bsr[:mid] if mid > 0 else []
    bottom_half = sorted_by_bsr[mid:] if mid > 0 else []

    def _group_keyword_freq(
        group: list[WeightedProduct],
        kw_map: dict[str, list[WeightedProduct]],
    ) -> dict[str, int]:
        group_asins = {p.asin for p in group}
        freq: dict[str, int] = {}
        for kw, prods in kw_map.items():
            count = sum(1 for p in prods if p.asin in group_asins)
            if count > 0:
                freq[kw] = count
        return freq

    return {
        "total_with_customer_says": len(with_cs),
        "positive_keywords": {
            kw: _kw_stats(prods) for kw, prods in pos_counts.items() if prods
        },
        "negative_keywords": {
            kw: _kw_stats(prods) for kw, prods in neg_counts.items() if prods
        },
        "bsr_top_half_positive": _group_keyword_freq(top_half, pos_counts),
        "bsr_top_half_negative": _group_keyword_freq(top_half, neg_counts),
        "bsr_bottom_half_positive": _group_keyword_freq(bottom_half, pos_counts),
        "bsr_bottom_half_negative": _group_keyword_freq(bottom_half, neg_counts),
    }


def analyze_badges(products: list[WeightedProduct]) -> dict:
    """badge 보유/미보유 제품 성과 비교 분석."""
    with_badge = [p for p in products if p.badge]
    without_badge = [p for p in products if not p.badge]

    badge_types: Counter = Counter()
    for p in with_badge:
        badge_types[p.badge] += 1

    def _group_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_price": None, "avg_reviews": None, "avg_rating": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        prices = [p.price for p in group if p.price is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_reviews": round(sum(p.reviews for p in group) / len(group)),
            "avg_rating": round(sum(p.rating for p in group) / len(group), 2),
        }

    threshold = {}
    if with_badge:
        reviews_list = [p.reviews for p in with_badge]
        ratings_list = [p.rating for p in with_badge]
        threshold = {
            "min_reviews": min(reviews_list),
            "median_reviews": sorted(reviews_list)[len(reviews_list) // 2],
            "min_rating": min(ratings_list),
            "median_rating": round(
                sorted(ratings_list)[len(ratings_list) // 2], 1
            ),
        }

    # V5 Phase 2: 통계 검증
    badge_bsr = [float(p.bsr_category) for p in with_badge if p.bsr_category is not None]
    no_badge_bsr = [float(p.bsr_category) for p in without_badge if p.bsr_category is not None]

    return {
        "total_products": len(products),
        "with_badge": _group_metrics(with_badge),
        "without_badge": _group_metrics(without_badge),
        "badge_types": [
            {"badge": b, "count": c} for b, c in badge_types.most_common()
        ],
        "acquisition_threshold": threshold,
        "stat_test_bsr": _stat_compare(badge_bsr, no_badge_bsr),
    }


def analyze_discount_impact(products: list[WeightedProduct]) -> dict:
    """할인율(initial_price vs final_price) 구간별 BSR/판매량 비교."""

    def _discount_tier(pct: float) -> str:
        if pct <= 0:
            return "No Discount (0%)"
        if pct <= 15:
            return "Light (1-15%)"
        if pct <= 30:
            return "Medium (16-30%)"
        return "Heavy (31%+)"

    tiers: dict[str, list[WeightedProduct]] = defaultdict(list)

    for p in products:
        if p.initial_price is not None and p.price is not None and p.initial_price > 0:
            discount_pct = (1 - p.price / p.initial_price) * 100
            tier = _discount_tier(discount_pct)
        else:
            tier = "No Discount (0%)"
        tiers[tier].append(p)

    def _tier_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None, "avg_price": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        prices = [p.price for p in group if p.price is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        }

    tier_order = ["No Discount (0%)", "Light (1-15%)", "Medium (16-30%)", "Heavy (31%+)"]

    # V5 Phase 2: 통계 검증 (할인 vs 미할인)
    discount_bsr = [
        float(p.bsr_category) for p in products
        if p.initial_price is not None and p.price is not None
        and p.initial_price > p.price and p.bsr_category is not None
    ]
    no_discount_bsr = [
        float(p.bsr_category) for p in products
        if (p.initial_price is None or p.initial_price <= (p.price or 0))
        and p.bsr_category is not None
    ]

    return {
        "total_products": len(products),
        "tiers": {
            tier: _tier_metrics(tiers.get(tier, []))
            for tier in tier_order
        },
        "stat_test_bsr": _stat_compare(discount_bsr, no_discount_bsr),
    }


def analyze_title_keywords(products: list[WeightedProduct]) -> dict:
    """title 내 마케팅 키워드별 BSR/판매량 비교."""
    MARKETING_KEYWORDS = [
        "Organic", "Natural", "Korean", "Vegan", "Sulfate-Free",
        "Dermatologist", "Clinical", "Hyaluronic", "Retinol", "Vitamin C",
        "Collagen", "Niacinamide", "Salicylic", "SPF", "Cruelty-Free",
        "Fragrance-Free", "Paraben-Free", "Gluten-Free", "Alcohol-Free",
        "Sensitive", "Anti-Aging", "Moisturizing",
    ]

    keyword_products: dict[str, list[WeightedProduct]] = {kw: [] for kw in MARKETING_KEYWORDS}

    for p in products:
        title_lower = p.title.lower()
        for kw in MARKETING_KEYWORDS:
            if kw.lower() in title_lower:
                keyword_products[kw].append(p)

    def _kw_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    results = {
        kw: _kw_metrics(prods)
        for kw, prods in keyword_products.items()
        if prods
    }

    sorted_results = dict(
        sorted(
            results.items(),
            key=lambda x: x[1].get("avg_bsr") or float("inf"),
        )
    )

    return {
        "total_products": len(products),
        "keyword_analysis": sorted_results,
    }


# ── V5 Phase 2: Deep Analysis ────────────────────────────


def _stat_compare(group_a: list[float], group_b: list[float]) -> dict:
    """두 그룹 간 Mann-Whitney U test. p-value와 유의성 판정 반환."""
    if len(group_a) < 5 or len(group_b) < 5:
        return {"p_value": None, "significant": None, "note": "insufficient_sample"}
    try:
        from scipy.stats import mannwhitneyu
        stat, p_value = mannwhitneyu(group_a, group_b, alternative="two-sided")
        return {
            "p_value": round(float(p_value), 4),
            "significant": bool(p_value < 0.05),
            "u_statistic": round(float(stat), 2),
        }
    except Exception:
        return {"p_value": None, "significant": None, "note": "test_failed"}


def _parse_unit_price(unit_price_str: str) -> tuple[float | None, str | None]:
    """'$0.36 / ounce' -> (0.36, 'ounce'). 파싱 실패 시 (None, None)."""
    if not unit_price_str:
        return None, None
    m = re.match(r"\$?([\d.]+)\s*/\s*(.+)", unit_price_str.strip())
    if m:
        try:
            return float(m.group(1)), m.group(2).strip().lower()
        except ValueError:
            return None, None
    return None, None


def analyze_unit_economics(products: list[WeightedProduct]) -> dict:
    """unit_price 파싱 + 동일 단위 기준 단가 비교."""
    unit_data: dict[str, list[dict]] = defaultdict(list)
    parse_success = 0
    parse_fail = 0

    for p in products:
        price_val, unit = _parse_unit_price(p.unit_price)
        if price_val is not None and unit is not None:
            parse_success += 1
            unit_data[unit].append({
                "asin": p.asin,
                "title": p.title[:60],
                "unit_price": price_val,
                "final_price": p.price,
                "bsr": p.bsr_category,
                "bought": p.bought_past_month,
            })
        elif p.unit_price:
            parse_fail += 1

    unit_summaries = {}
    for unit, items in unit_data.items():
        if len(items) < 3:
            continue
        prices = [i["unit_price"] for i in items]
        bsr_vals = [i["bsr"] for i in items if i["bsr"] is not None]
        items_sorted = sorted(items, key=lambda x: x["unit_price"])
        unit_summaries[unit] = {
            "count": len(items),
            "avg_unit_price": round(sum(prices) / len(prices), 3),
            "min_unit_price": round(min(prices), 3),
            "max_unit_price": round(max(prices), 3),
            "cheapest": items_sorted[0],
            "most_expensive": items_sorted[-1],
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
        }

    return {
        "parse_success": parse_success,
        "parse_fail": parse_fail,
        "parse_rate": round(parse_success / (parse_success + parse_fail) * 100, 1)
            if (parse_success + parse_fail) > 0 else 0,
        "units": unit_summaries,
    }


def analyze_manufacturer(
    products: list[WeightedProduct],
    details: list[ProductDetail],
) -> dict:
    """제조사(OEM)별 프로파일 분석."""
    detail_map = {d.asin: d for d in details}
    mfr_data: dict[str, dict] = defaultdict(lambda: {
        "products": [],
        "bsr_values": [],
        "prices": [],
        "ratings": [],
        "bought_values": [],
    })

    for p in products:
        mfr = p.manufacturer
        if not mfr:
            d = detail_map.get(p.asin)
            mfr = d.manufacturer if d else ""
        if not mfr or mfr.lower() in ("unknown", ""):
            continue
        md = mfr_data[mfr]
        md["products"].append(p.asin)
        if p.bsr_category is not None:
            md["bsr_values"].append(p.bsr_category)
        if p.price is not None:
            md["prices"].append(p.price)
        md["ratings"].append(p.rating)
        if p.bought_past_month is not None:
            md["bought_values"].append(p.bought_past_month)

    K_BEAUTY_KEYWORDS = [
        "medicube", "cosrx", "beauty of joseon", "laneige", "innisfree",
        "missha", "etude", "tonymoly", "some by mi", "klairs",
        "purito", "neogen", "banila co", "heimish", "dr.jart",
    ]

    results = []
    for mfr, md in mfr_data.items():
        if len(md["products"]) < 2:
            continue
        prices = md["prices"]
        bsr_vals = md["bsr_values"]
        bought_vals = md["bought_values"]
        is_kbeauty = any(kw in mfr.lower() for kw in K_BEAUTY_KEYWORDS)
        results.append({
            "manufacturer": mfr,
            "product_count": len(md["products"]),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
            "avg_rating": round(sum(md["ratings"]) / len(md["ratings"]), 2),
            "total_bought": sum(bought_vals) if bought_vals else None,
            "is_kbeauty": is_kbeauty,
        })

    results.sort(key=lambda x: x["product_count"], reverse=True)

    top10_count = sum(r["product_count"] for r in results[:10])
    total = len([p for p in products if p.manufacturer])

    return {
        "total_manufacturers": len(results),
        "top_manufacturers": results[:15],
        "market_concentration": {
            "top10_products": top10_count,
            "total_products": total,
            "top10_share_pct": round(top10_count / total * 100, 1) if total > 0 else 0,
        },
        "kbeauty_manufacturers": [r for r in results if r["is_kbeauty"]],
    }


def analyze_sku_strategy(products: list[WeightedProduct]) -> dict:
    """variations_count(SKU 수) 구간별 BSR/판매량 비교."""

    def _sku_tier(count: int) -> str:
        if count == 0:
            return "Single (0)"
        if count <= 3:
            return "Few (1-3)"
        if count <= 10:
            return "Medium (4-10)"
        return "Many (11+)"

    tiers: dict[str, list[WeightedProduct]] = defaultdict(list)
    for p in products:
        tier = _sku_tier(p.variations_count)
        tiers[tier].append(p)

    def _tier_metrics(group: list[WeightedProduct]) -> dict:
        if not group:
            return {"count": 0, "avg_bsr": None, "avg_bought": None}
        bsr_vals = [p.bsr_category for p in group if p.bsr_category is not None]
        bought_vals = [p.bought_past_month for p in group if p.bought_past_month is not None]
        return {
            "count": len(group),
            "avg_bsr": round(sum(bsr_vals) / len(bsr_vals)) if bsr_vals else None,
            "avg_bought": round(sum(bought_vals) / len(bought_vals)) if bought_vals else None,
        }

    tier_order = ["Single (0)", "Few (1-3)", "Medium (4-10)", "Many (11+)"]
    return {
        "total_products": len(products),
        "tiers": {
            tier: _tier_metrics(tiers.get(tier, []))
            for tier in tier_order
        },
    }


def build_keyword_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
    voice_keywords: VoiceKeywordResult | None = None,
) -> dict:
    """키워드 검색 전용 시장 분석. BSR 의존 분석 2개 제외.

    제외 항목:
    - rising_products: BSR < 10,000 로직 무의미
    - badges: Mann-Whitney U 검정 무의미
    """
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "brand_positioning": analyze_brand_positioning(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
        "sales_volume": analyze_sales_volume(weighted_products),
        "listing_tactics": analyze_listing_tactics(weighted_products),
        "sns_pricing": analyze_sns_pricing(weighted_products),
        "promotions": analyze_promotions(weighted_products),
        "customer_voice": analyze_customer_voice(weighted_products, voice_keywords),
        "discount_impact": analyze_discount_impact(weighted_products),
        "title_keywords": analyze_title_keywords(weighted_products),
        "unit_economics": analyze_unit_economics(weighted_products),
        "manufacturer": analyze_manufacturer(weighted_products, details),
        "sku_strategy": analyze_sku_strategy(weighted_products),
    }


def build_market_analysis(
    keyword: str,
    weighted_products: list[WeightedProduct],
    details: list[ProductDetail],
    voice_keywords: VoiceKeywordResult | None = None,
) -> dict:
    """전체 시장 분석 데이터 생성."""
    return {
        "keyword": keyword,
        "total_products": len(weighted_products),
        # 기존 V4 분석 (7개)
        "price_tier_analysis": analyze_by_price_tier(weighted_products),
        "bsr_analysis": analyze_by_bsr(weighted_products),
        "brand_analysis": analyze_by_brand(weighted_products, details),
        "cooccurrence_analysis": analyze_cooccurrence(weighted_products),
        "brand_positioning": analyze_brand_positioning(weighted_products, details),
        "rising_products": detect_rising_products(weighted_products, details),
        "rating_ingredients": analyze_rating_ingredients(weighted_products),
        # V4 분석 (competition 제거)
        "sales_volume": analyze_sales_volume(weighted_products),
        "sns_pricing": analyze_sns_pricing(weighted_products),
        "promotions": analyze_promotions(weighted_products),
        # V5 Phase 1 신규
        "customer_voice": analyze_customer_voice(weighted_products, voice_keywords),
        "badges": analyze_badges(weighted_products),
        "discount_impact": analyze_discount_impact(weighted_products),
        "title_keywords": analyze_title_keywords(weighted_products),
        # V5 Phase 2 신규
        "unit_economics": analyze_unit_economics(weighted_products),
        "manufacturer": analyze_manufacturer(weighted_products, details),
        "sku_strategy": analyze_sku_strategy(weighted_products),
    }
