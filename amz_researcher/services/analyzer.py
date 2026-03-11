from collections import defaultdict

from amz_researcher.models import (
    CategorySummary,
    IngredientRanking,
    ProductDetail,
    ProductIngredients,
    SearchProduct,
    WeightedProduct,
)


def _compute_composite_weight(
    position: int, reviews: int, rating: float, bsr_category: int | None,
    max_position: int, max_reviews: int, max_bsr: int,
    bought_past_month: int | None = None, max_bought: int = 1,
) -> float:
    """Weight 계산.

    bought_past_month 있으면 V4 가중치:
      BoughtPastMonth(30%) + BSR(25%) + Reviews(20%) + Rating(10%) + Position(15%)
    없으면 V3 호환:
      Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)
    """
    pos_norm = 1 - (position - 1) / max_position if max_position > 0 else 0
    rev_norm = reviews / max_reviews if max_reviews > 0 else 0
    rat_norm = rating / 5.0
    bsr = bsr_category if bsr_category is not None else (max_bsr + 1)
    bsr_norm = 1 - (bsr - 1) / max_bsr if max_bsr > 0 else 0
    bsr_norm = max(bsr_norm, 0)

    if bought_past_month is not None and max_bought > 0:
        bought_norm = bought_past_month / max_bought
        return (
            bought_norm * 0.30
            + bsr_norm * 0.25
            + rev_norm * 0.20
            + pos_norm * 0.15
            + rat_norm * 0.10
        )

    return pos_norm * 0.2 + rev_norm * 0.25 + rat_norm * 0.15 + bsr_norm * 0.4


def _generate_key_insight(
    rank: int, product_count: int, weighted_score: float, avg_weight: float,
) -> str:
    if rank <= 3:
        return "Top-tier: dominant across high-performing products"
    if product_count >= 4:
        return f"Broadly adopted ({product_count} products)"
    if avg_weight > 0.4:
        return "High avg weight — niche but in top products"
    if product_count == 1 and weighted_score > 0.3:
        return "Single-product signal — monitor trend"
    return ""


def _get_display_name(ing) -> str:
    """성분의 표시명 반환: common_name 우선, 없으면 name."""
    return ing.common_name if ing.common_name else ing.name


def _aggregate_ingredients(
    weighted_products: list[WeightedProduct],
) -> list[IngredientRanking]:
    ingredient_data: dict[str, dict] = {}

    for wp in weighted_products:
        for ing in wp.ingredients:
            # INCI 전용 성분은 랭킹 제외 (featured/both/legacy만 분석)
            if ing.source == "inci":
                continue
            key = _get_display_name(ing)
            if key not in ingredient_data:
                ingredient_data[key] = {
                    "category": ing.category,
                    "total_weight": 0.0,
                    "product_count": 0,
                    "prices": [],
                    "featured_count": 0,
                    "inci_only_count": 0,
                }
            data = ingredient_data[key]
            data["total_weight"] += wp.composite_weight
            data["product_count"] += 1
            if wp.price is not None:
                data["prices"].append(wp.price)
            if ing.source in ("featured", "both"):
                data["featured_count"] += 1

    rankings = []
    for name, data in ingredient_data.items():
        prices = data["prices"]
        avg_price = sum(prices) / len(prices) if prices else None
        price_range = ""
        if prices:
            lo, hi = min(prices), max(prices)
            price_range = f"${lo:.0f} – ${hi:.0f}"

        avg_weight = (
            data["total_weight"] / data["product_count"]
            if data["product_count"] > 0 else 0
        )

        rankings.append(IngredientRanking(
            ingredient=name,
            weighted_score=data["total_weight"],
            product_count=data["product_count"],
            avg_weight=avg_weight,
            category=data["category"],
            avg_price=avg_price,
            price_range=price_range,
            featured_count=data["featured_count"],
            inci_only_count=data["inci_only_count"],
        ))

    rankings.sort(key=lambda r: r.weighted_score, reverse=True)
    for i, r in enumerate(rankings, 1):
        r.rank = i
        r.key_insight = _generate_key_insight(
            r.rank, r.product_count, r.weighted_score, r.avg_weight,
        )

    return rankings


def _aggregate_categories(
    rankings: list[IngredientRanking],
    weighted_products: list[WeightedProduct],
) -> list[CategorySummary]:
    cat_data: dict[str, dict] = defaultdict(lambda: {
        "total_score": 0.0,
        "types": set(),
        "mentions": 0,
        "prices": [],
    })

    for r in rankings:
        d = cat_data[r.category]
        d["total_score"] += r.weighted_score
        d["types"].add(r.ingredient)
        d["mentions"] += r.product_count
        if r.avg_price is not None:
            d["prices"].append(r.avg_price)

    summaries = []
    for cat, d in cat_data.items():
        prices = d["prices"]
        avg_price = sum(prices) / len(prices) if prices else None
        price_range = ""
        if prices:
            lo, hi = min(prices), max(prices)
            price_range = f"${lo:.0f} – ${hi:.0f}"

        top_ings = sorted(
            [r for r in rankings if r.category == cat],
            key=lambda r: r.weighted_score,
            reverse=True,
        )
        top_names = ", ".join(r.ingredient for r in top_ings[:5])

        summaries.append(CategorySummary(
            category=cat,
            total_weighted_score=d["total_score"],
            type_count=len(d["types"]),
            mention_count=d["mentions"],
            avg_price=avg_price,
            price_range=price_range,
            top_ingredients=top_names,
        ))

    summaries.sort(key=lambda s: s.total_weighted_score, reverse=True)
    return summaries


def calculate_weights(
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    gemini_results: list[ProductIngredients],
) -> tuple[list[WeightedProduct], list[IngredientRanking], list[CategorySummary]]:
    detail_map = {d.asin: d for d in details}
    ingredient_map = {g.asin: g.ingredients for g in gemini_results}

    max_position = max((p.position for p in search_products), default=1)
    max_reviews = max((p.reviews for p in search_products), default=1)

    bsr_values = [
        detail_map[p.asin].bsr_category
        for p in search_products
        if p.asin in detail_map and detail_map[p.asin].bsr_category is not None
    ]
    max_bsr = max(bsr_values) if bsr_values else 1

    bought_values = [
        p.bought_past_month
        for p in search_products
        if p.bought_past_month is not None
    ]
    max_bought = max(bought_values) if bought_values else 0

    weighted_products = []
    for sp in search_products:
        detail = detail_map.get(sp.asin)
        bsr_category = detail.bsr_category if detail else None
        bsr_subcategory = detail.bsr_subcategory if detail else None
        rating = (detail.rating if detail and detail.rating else sp.rating)

        weight = _compute_composite_weight(
            sp.position, sp.reviews, rating, bsr_category,
            max_position, max_reviews, max_bsr,
            bought_past_month=sp.bought_past_month,
            max_bought=max_bought,
        )

        ingredients = ingredient_map.get(sp.asin, [])

        weighted_products.append(WeightedProduct(
            asin=sp.asin,
            title=sp.title,
            position=sp.position,
            price=sp.price,
            reviews=sp.reviews,
            rating=rating,
            bsr_category=bsr_category,
            bsr_subcategory=bsr_subcategory,
            composite_weight=weight,
            ingredients=ingredients,
            bought_past_month=sp.bought_past_month,
            brand=detail.brand if detail else "",
            sponsored=sp.sponsored,
        ))

    weighted_products.sort(key=lambda p: p.composite_weight, reverse=True)

    rankings = _aggregate_ingredients(weighted_products)
    categories = _aggregate_categories(rankings, weighted_products)

    return weighted_products, rankings, categories
