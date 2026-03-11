"""캐시 DB 데이터로 report-enhancement-v7 HTML 리포트를 로컬 생성 & 브라우저 열기.

Usage:
    # 카테고리 목록 확인
    uv run python test_report_local.py --list

    # 카테고리 기반 리포트 생성
    uv run python test_report_local.py --category "Hair Styling Serums"

    # 키워드 검색 기반 리포트 생성
    uv run python test_report_local.py --keyword "vitamin c serum"

    # 생성만 (브라우저 안 열기)
    uv run python test_report_local.py --category "Hair Styling Serums" --no-open
"""
import argparse
import json
import logging
import sys
import webbrowser
from pathlib import Path

from amz_researcher.models import (
    BrightDataProduct,
    ProductIngredients,
)
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.product_db import ProductDBService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.market_analyzer import build_market_analysis, build_keyword_market_analysis
from amz_researcher.services.html_report_builder import build_html, build_keyword_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ENV = "CFO"


def _parse_db_row(row: dict) -> dict:
    """DB dict → BrightDataProduct 생성자 인자 변환."""
    import math
    result = dict(row)
    for field in ("features", "categories", "subcategory_ranks", "product_details"):
        val = result.get(field)
        if isinstance(val, str):
            try:
                result[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[field] = []
    for key, val in result.items():
        if isinstance(val, float) and math.isnan(val):
            result[key] = None
    return result


_MEASUREMENT_KEYS = {
    "Product Dimensions", "Package Dimensions", "Item Weight",
    "Item Dimensions LxWxH", "Units",
}


def _product_details_to_dicts(product_details):
    from amz_researcher.models import ProductDetail
    features, measurements, additional = {}, {}, {}
    _META_KEYS = {"ASIN", "Best Sellers Rank", "Customer Reviews", "Manufacturer"}
    for item in product_details:
        key = item.get("type", "")
        val = item.get("value", "")
        if not key:
            continue
        if key in _MEASUREMENT_KEYS:
            measurements[key] = val
        elif key in _META_KEYS:
            additional[key] = val
        else:
            features[key] = val
    return features, measurements, additional


def _adapt_for_analyzer(products):
    from amz_researcher.models import SearchProduct, ProductDetail
    from amz_researcher.services.data_collector import resolve_brand
    search_products, details = [], []
    for i, p in enumerate(products):
        price_str = f"${p.final_price:.2f}" if p.final_price is not None else ""
        search_products.append(SearchProduct(
            position=i + 1,
            title=p.title,
            asin=p.asin,
            price=p.final_price,
            price_raw=price_str,
            reviews=p.reviews_count,
            reviews_raw=str(p.reviews_count) if p.reviews_count else "",
            rating=p.rating,
            product_link=p.url,
            bought_past_month=p.bought_past_month,
        ))
        features_dict, meas_dict, add_dict = _product_details_to_dicts(p.product_details)
        sub_rank, sub_name = None, ""
        if p.subcategory_ranks:
            first_sub = p.subcategory_ranks[0]
            sub_rank = first_sub.get("subcategory_rank")
            sub_name = first_sub.get("subcategory_name", "")
        details.append(ProductDetail(
            asin=p.asin,
            ingredients_raw=p.ingredients,
            features=features_dict,
            measurements=meas_dict,
            additional_details=add_dict,
            bsr_category=p.bs_rank,
            bsr_category_name=p.bs_category,
            bsr_subcategory=sub_rank,
            bsr_subcategory_name=sub_name,
            rating=p.rating,
            review_count=p.reviews_count,
            brand=resolve_brand(p.brand, p.title),
            manufacturer=p.manufacturer,
            product_url=p.url,
        ))
    return search_products, details


def list_categories():
    db = ProductDBService(ENV)
    cats = db.list_categories()
    if not cats:
        print("활성 카테고리 없음")
        return
    print(f"\n{'='*60}")
    print(f"활성 카테고리 ({len(cats)}개)")
    print(f"{'='*60}")
    for c in cats:
        freshness = db.get_category_freshness(c["node_id"])
        count = freshness["product_count"] if freshness else 0
        print(f"  [{c['node_id']}] {c['name']} ({count}개 제품)")
    print()


def generate_category_report(category_name: str) -> Path | None:
    db = ProductDBService(ENV)
    cache = AmzCacheService(ENV)

    # 카테고리 검색
    cats = db.search_categories(category_name)
    if not cats:
        print(f"카테고리 '{category_name}'를 찾을 수 없습니다. --list로 확인하세요.")
        return None

    cat = cats[0]
    node_id = cat["node_id"]
    name = cat["name"]
    print(f"카테고리: {name} (node_id={node_id})")

    # DB에서 제품 로드
    raw_products = db.get_products_by_category(node_id)
    if not raw_products:
        print(f"제품 데이터 없음 (node_id={node_id})")
        return None
    products = [BrightDataProduct(**_parse_db_row(r)) for r in raw_products]
    print(f"제품 로드: {len(products)}개")

    # 캐시된 성분 로드
    asins = [p.asin for p in products]
    cached_ingredients = cache.get_ingredient_cache(asins)
    print(f"성분 캐시: {len(cached_ingredients)}/{len(asins)}개 ASIN")

    gemini_results = [
        ProductIngredients(asin=asin, ingredients=ings)
        for asin, ings in cached_ingredients.items()
    ]

    # 가중치 계산
    search_products, all_details = _adapt_for_analyzer(products)
    weighted_products, rankings, categories = calculate_weights(
        search_products, all_details, gemini_results,
    )

    # V7 확장 필드 주입
    bright_map = {p.asin: p for p in products}
    for wp in weighted_products:
        bp = bright_map.get(wp.asin)
        if bp:
            wp.sns_price = bp.sns_price
            wp.unit_price = bp.unit_price
            wp.number_of_sellers = bp.number_of_sellers
            wp.coupon = bp.coupon
            wp.plus_content = bp.plus_content
            wp.customer_says = bp.customer_says
            wp.badge = bp.badge
            wp.initial_price = bp.initial_price
            wp.manufacturer = bp.manufacturer
            wp.variations_count = bp.variations_count
            wp.ingredients_raw = bp.ingredients or ""

    # voice keywords 로드
    voice_kw_data = db.load_voice_keywords(asins)
    for wp in weighted_products:
        if wp.asin in voice_kw_data:
            wp.voice_positive = voice_kw_data[wp.asin].get("positive", [])
            wp.voice_negative = voice_kw_data[wp.asin].get("negative", [])

    # 시장 분석
    analysis_data = build_market_analysis(name, weighted_products, all_details)
    print(f"시장 분석 완료")

    # 캐시된 마켓 리포트
    market_report = cache.get_market_report_cache(name, len(weighted_products)) or ""
    if market_report:
        print(f"마켓 리포트 캐시 사용 ({len(market_report)} chars)")
    else:
        print("⚠️  캐시된 마켓 리포트 없음 (Executive Summary 없이 생성)")

    # HTML 빌드
    html_bytes = build_html(
        name, weighted_products, rankings, categories,
        search_products, all_details,
        market_report=market_report,
        rising_products=analysis_data.get("rising_products"),
        analysis_data=analysis_data,
    )
    print(f"HTML 생성: {len(html_bytes):,} bytes")

    # 파일 저장
    out_dir = Path("data/test_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace(" ", "_").replace("/", "_")
    out_path = out_dir / f"{safe_name}_v7_test.html"
    out_path.write_bytes(html_bytes)
    print(f"저장: {out_path}")
    return out_path


def generate_keyword_report(keyword: str) -> Path | None:
    db = ProductDBService(ENV)
    cache = AmzCacheService(ENV)

    # 키워드 캐시 확인
    kw_cache = db.get_keyword_cache(keyword)
    if not kw_cache:
        print(f"키워드 '{keyword}' 캐시 없음. Slack에서 /amz search {keyword}를 먼저 실행하세요.")
        return None

    searched_at = kw_cache["searched_at"]
    print(f"키워드: {keyword} (searched_at={searched_at})")

    # 키워드 제품 로드
    raw_products = db.get_keyword_products(keyword, searched_at)
    if not raw_products:
        print("제품 데이터 없음")
        return None

    # 키워드 제품은 amz_keyword_products 테이블에서 오므로 BrightDataProduct 형식으로 변환
    from amz_researcher.models import SearchProduct, ProductDetail
    search_products = []
    details_list = []
    for r in raw_products:
        sp = SearchProduct(
            position=int(r.get("position", 0)),
            title=r.get("title", ""),
            asin=r.get("asin", ""),
            price=float(r["price"]) if r.get("price") is not None else None,
            price_raw=r.get("price_raw", ""),
            reviews=int(r.get("reviews", 0)),
            reviews_raw=r.get("reviews_raw", ""),
            rating=float(r.get("rating", 0)),
            product_link=r.get("product_link", ""),
            bought_past_month=int(r["bought_past_month"]) if r.get("bought_past_month") is not None else None,
        )
        search_products.append(sp)

    asins = [sp.asin for sp in search_products]
    print(f"제품 로드: {len(search_products)}개")

    # 상세 캐시
    detail_cache = cache.get_detail_cache(asins)
    details_list = list(detail_cache.values())
    print(f"상세 캐시: {len(details_list)}/{len(asins)}개")

    # 성분 캐시
    cached_ingredients = cache.get_ingredient_cache(asins)
    print(f"성분 캐시: {len(cached_ingredients)}/{len(asins)}개")
    gemini_results = [
        ProductIngredients(asin=asin, ingredients=ings)
        for asin, ings in cached_ingredients.items()
    ]

    # 가중치 계산
    weighted_products, rankings, categories = calculate_weights(
        search_products, details_list, gemini_results,
    )

    # V7 확장 필드 주입 (detail_cache에서)
    for wp in weighted_products:
        d = detail_cache.get(wp.asin)
        if d:
            wp.manufacturer = d.manufacturer
            wp.ingredients_raw = d.ingredients_raw or ""

    # 시장 분석
    normalized = " ".join(keyword.lower().split())
    analysis_data = build_keyword_market_analysis(normalized, weighted_products, details_list)
    print("시장 분석 완료")

    # 캐시된 마켓 리포트
    market_report = cache.get_market_report_cache(normalized, len(weighted_products)) or ""
    if market_report:
        print(f"마켓 리포트 캐시 사용 ({len(market_report)} chars)")
    else:
        print("⚠️  캐시된 마켓 리포트 없음")

    # HTML 빌드
    html_bytes = build_keyword_html(
        normalized, weighted_products, rankings, categories,
        search_products, details_list,
        market_report=market_report,
        analysis_data=analysis_data,
    )
    print(f"HTML 생성: {len(html_bytes):,} bytes")

    # 파일 저장
    out_dir = Path("data/test_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = normalized.replace(" ", "_")
    out_path = out_dir / f"{safe_name}_keyword_v7_test.html"
    out_path.write_bytes(html_bytes)
    print(f"저장: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="캐시 DB로 v7 HTML 리포트 로컬 테스트")
    parser.add_argument("--list", action="store_true", help="활성 카테고리 목록")
    parser.add_argument("--category", "-c", type=str, help="카테고리명으로 BSR 리포트 생성")
    parser.add_argument("--keyword", "-k", type=str, help="키워드로 검색 리포트 생성")
    parser.add_argument("--no-open", action="store_true", help="브라우저 자동 열기 비활성화")
    args = parser.parse_args()

    if args.list:
        list_categories()
        return

    if not args.category and not args.keyword:
        parser.print_help()
        return

    if args.category:
        out_path = generate_category_report(args.category)
    else:
        out_path = generate_keyword_report(args.keyword)

    if out_path and not args.no_open:
        abs_path = out_path.resolve()
        url = f"file://{abs_path}"
        print(f"\n브라우저에서 열기: {url}")
        webbrowser.open(url)


if __name__ == "__main__":
    main()
