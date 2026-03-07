import json
import logging
from datetime import datetime, timedelta

import pandas as pd

from amz_researcher.models import ProductDetail, SearchProduct
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 30


class AmzCacheService:
    """MySQL 기반 Amazon 데이터 캐시 서비스."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    # ── Search Cache ─────────────────────────────────

    def get_search_cache(self, keyword: str) -> list[SearchProduct] | None:
        """30일 이내 검색 캐시 조회. 없으면 None."""
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        query = (
            "SELECT * FROM amz_search_cache "
            "WHERE keyword = %s AND searched_at >= %s "
            "ORDER BY position"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (keyword, cutoff))
        except Exception:
            logger.exception("Failed to read search cache")
            return None
        if df.empty:
            return None
        return [
            SearchProduct(
                position=int(row["position"]),
                title=row["title"] or "",
                asin=row["asin"],
                price=float(row["price"]) if row["price"] is not None else None,
                price_raw=row["price_raw"] or "",
                reviews=int(row["reviews"]),
                reviews_raw=row["reviews_raw"] or "",
                rating=float(row["rating"]),
                sponsored=bool(row["sponsored"]),
                product_link=row["product_link"] or "",
            )
            for _, row in df.iterrows()
        ]

    def save_search_cache(self, keyword: str, products: list[SearchProduct]) -> None:
        """검색 결과를 캐시에 저장 (upsert)."""
        if not products:
            return
        now = datetime.now()
        rows = [
            {
                "keyword": keyword,
                "asin": p.asin,
                "position": p.position,
                "title": p.title,
                "price": p.price,
                "price_raw": p.price_raw,
                "reviews": p.reviews,
                "reviews_raw": p.reviews_raw,
                "rating": p.rating,
                "sponsored": int(p.sponsored),
                "product_link": p.product_link,
                "searched_at": now,
            }
            for p in products
        ]
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_search_cache")
            logger.info("Search cache saved: keyword=%s, %d products", keyword, len(products))
        except Exception:
            logger.exception("Failed to save search cache")

    # ── Product Detail Cache ─────────────────────────

    def get_detail_cache(self, asins: list[str]) -> dict[str, ProductDetail]:
        """30일 이내 상세 캐시 조회. {asin: ProductDetail} 반환."""
        if not asins:
            return {}
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        placeholders = ",".join(["%s"] * len(asins))
        query = (
            f"SELECT * FROM amz_product_detail "
            f"WHERE asin IN ({placeholders}) AND crawled_at >= %s"
        )
        params = (*asins, cutoff)
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, params)
        except Exception:
            logger.exception("Failed to read detail cache")
            return {}
        result = {}
        for _, row in df.iterrows():
            result[row["asin"]] = ProductDetail(
                asin=row["asin"],
                ingredients_raw=row["ingredients_raw"] or "",
                features=json.loads(row["features"]) if row["features"] else {},
                measurements=json.loads(row["measurements"]) if row["measurements"] else {},
                item_details=json.loads(row["item_details"]) if row["item_details"] else {},
                additional_details=json.loads(row["additional_details"]) if row["additional_details"] else {},
                bsr_category=int(row["bsr_category"]) if row["bsr_category"] is not None else None,
                bsr_subcategory=int(row["bsr_subcategory"]) if row["bsr_subcategory"] is not None else None,
                bsr_category_name=row["bsr_category_name"] or "",
                bsr_subcategory_name=row["bsr_subcategory_name"] or "",
                rating=float(row["rating"]) if row["rating"] is not None else None,
                review_count=int(row["review_count"]) if row["review_count"] is not None else None,
                brand=row["brand"] or "",
                manufacturer=row["manufacturer"] or "",
            )
        return result

    def save_detail_cache(self, details: list[ProductDetail]) -> None:
        """상세 정보를 캐시에 저장 (upsert)."""
        if not details:
            return
        now = datetime.now()
        rows = [
            {
                "asin": d.asin,
                "ingredients_raw": d.ingredients_raw,
                "features": json.dumps(d.features, ensure_ascii=False),
                "measurements": json.dumps(d.measurements, ensure_ascii=False),
                "item_details": json.dumps(d.item_details, ensure_ascii=False),
                "additional_details": json.dumps(d.additional_details, ensure_ascii=False),
                "bsr_category": d.bsr_category,
                "bsr_subcategory": d.bsr_subcategory,
                "bsr_category_name": d.bsr_category_name,
                "bsr_subcategory_name": d.bsr_subcategory_name,
                "rating": d.rating,
                "review_count": d.review_count,
                "brand": d.brand,
                "manufacturer": d.manufacturer,
                "crawled_at": now,
            }
            for d in details
        ]
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_product_detail")
            logger.info("Detail cache saved: %d products", len(details))
        except Exception:
            logger.exception("Failed to save detail cache")
