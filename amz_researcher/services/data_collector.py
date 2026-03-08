import json
import logging
from datetime import date, datetime

import pandas as pd

from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)


class DataCollector:
    """Bright Data 수집 데이터를 DB에 적재."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def process_snapshot(
        self, products: list[dict], snapshot_date: date | None = None,
    ) -> int:
        """수집 데이터를 amz_products + amz_products_history에 적재.

        Returns:
            적재된 제품 수
        """
        if not products:
            return 0
        snapshot_date = snapshot_date or date.today()

        # 1. amz_products upsert
        product_rows = [self._map_product(p) for p in products]
        df_products = pd.DataFrame(product_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_products, "amz_products")
        logger.info("Upserted %d products to amz_products", len(product_rows))

        # 2. amz_products_history append
        history_rows = [self._map_history(p, snapshot_date) for p in products]
        df_history = pd.DataFrame(history_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_history, "amz_products_history")
        logger.info("Upserted %d rows to amz_products_history", len(history_rows))

        # 3. amz_product_categories 매핑
        cat_rows = self._map_categories(products, snapshot_date)
        if cat_rows:
            df_cats = pd.DataFrame(cat_rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df_cats, "amz_product_categories")
            logger.info("Upserted %d product-category mappings", len(cat_rows))

        logger.info("Processed %d products (snapshot: %s)", len(products), snapshot_date)
        return len(products)

    def _map_product(self, raw: dict) -> dict:
        """Bright Data 응답 → amz_products 행."""
        buybox = raw.get("buybox_prices") or {}
        sns = buybox.get("sns_price") or {}
        sns_price = sns.get("base_price")

        return {
            "asin": raw["asin"],
            "title": (raw.get("title") or "")[:500],
            "brand": (raw.get("brand") or "")[:200],
            "description": raw.get("description") or "",
            "initial_price": raw.get("initial_price"),
            "final_price": raw.get("final_price"),
            "currency": raw.get("currency", "USD"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "root_bs_rank": raw.get("root_bs_rank"),
            "root_bs_category": raw.get("root_bs_category"),
            "subcategory_ranks": json.dumps(raw.get("subcategory_rank") or [], ensure_ascii=False),
            "ingredients": raw.get("ingredients") or "",
            "features": json.dumps(raw.get("features") or [], ensure_ascii=False),
            "product_details": json.dumps(raw.get("product_details") or [], ensure_ascii=False),
            "manufacturer": raw.get("manufacturer") or "",
            "department": raw.get("department") or "",
            "image_url": raw.get("image_url") or "",
            "url": raw.get("url") or "",
            "badge": raw.get("badge") or "",
            "bought_past_month": raw.get("bought_past_month"),
            "is_available": raw.get("is_available", True),
            "categories": json.dumps(raw.get("categories") or [], ensure_ascii=False),
            "customer_says": raw.get("customer_says") or "",
            "unit_price": buybox.get("unit_price") or "",
            "sns_price": sns_price,
            "variations_count": len(raw.get("variations") or []),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
            "plus_content": bool(raw.get("plus_content")),
            "collected_at": datetime.now(),
        }

    def _map_history(self, raw: dict, snapshot_date: date) -> dict:
        """Bright Data 응답 → amz_products_history 행."""
        return {
            "asin": raw["asin"],
            "snapshot_date": snapshot_date,
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "final_price": raw.get("final_price"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bought_past_month": raw.get("bought_past_month"),
            "badge": raw.get("badge") or "",
            "root_bs_rank": raw.get("root_bs_rank"),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
        }

    def _map_categories(self, products: list[dict], snapshot_date: date) -> list[dict]:
        """origin_url에서 카테고리 node_id를 추출하여 매핑 행 생성."""
        rows = []
        for p in products:
            origin = p.get("origin_url") or ""
            node_id = origin.rstrip("/").split("/")[-1] if origin else ""
            if node_id and node_id.isdigit():
                rows.append({
                    "asin": p["asin"],
                    "category_node_id": node_id,
                    "collected_at": snapshot_date,
                })
        return rows
