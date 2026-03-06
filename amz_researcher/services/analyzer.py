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
    position: int, reviews: int, rating: float, volume: int,
    max_position: int, max_reviews: int, max_volume: int,
) -> float:
    pos_norm = 1 - (position - 1) / max_position if max_position > 0 else 0
    rev_norm = reviews / max_reviews if max_reviews > 0 else 0
    rat_norm = rating / 5.0
    vol_norm = volume / max_volume if max_volume > 0 else 0
    return pos_norm * 0.2 + rev_norm * 0.3 + rat_norm * 0.2 + vol_norm * 0.3


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


def _aggregate_ingredients(
    weighted_products: list[WeightedProduct],
) -> list[IngredientRanking]:
    ingredient_data: dict[str, dict] = {}

    for wp in weighted_products:
        for ing in wp.ingredients:
            key = ing.name
            if key not in ingredient_data:
                ingredient_data[key] = {
                    "category": ing.category,
                    "total_weight": 0.0,
                    "product_count": 0,
                    "prices": [],
                }
            data = ingredient_data[key]
            data["total_weight"] += wp.composite_weight
            data["product_count"] += 1
            if wp.price is not None:
                data["prices"].append(wp.price)

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

    volumes = [detail_map[p.asin].volume for p in search_products if p.asin in detail_map]
    max_volume = max(volumes) if volumes else 1

    weighted_products = []
    for sp in search_products:
        detail = detail_map.get(sp.asin)
        volume = detail.volume if detail else 0

        weight = _compute_composite_weight(
            sp.position, sp.reviews, sp.rating, volume,
            max_position, max_reviews, max_volume,
        )

        ingredients = ingredient_map.get(sp.asin, [])

        weighted_products.append(WeightedProduct(
            asin=sp.asin,
            title=sp.title,
            position=sp.position,
            price=sp.price,
            reviews=sp.reviews,
            rating=sp.rating,
            volume=volume,
            composite_weight=weight,
            ingredients=ingredients,
        ))

    weighted_products.sort(key=lambda p: p.composite_weight, reverse=True)

    rankings = _aggregate_ingredients(weighted_products)
    categories = _aggregate_categories(rankings, weighted_products)

    return weighted_products, rankings, categories
