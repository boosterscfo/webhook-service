import json
import logging
import math
from datetime import datetime, timedelta

import pandas as pd

from amz_researcher.models import Ingredient, ProductDetail, ProductIngredients, SearchProduct
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
            def _int_or_none(v):
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return None
                return int(v)

            def _float_or_none(v):
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return None
                return float(v)

            def _str_or_empty(v):
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return ""
                return str(v)

            def _json_or_empty(v):
                if not v or (isinstance(v, float) and math.isnan(v)):
                    return {}
                return json.loads(v)

            result[row["asin"]] = ProductDetail(
                asin=row["asin"],
                ingredients_raw=_str_or_empty(row["ingredients_raw"]),
                features=_json_or_empty(row["features"]),
                measurements=_json_or_empty(row["measurements"]),
                item_details=_json_or_empty(row["item_details"]),
                additional_details=_json_or_empty(row["additional_details"]),
                bsr_category=_int_or_none(row["bsr_category"]),
                bsr_subcategory=_int_or_none(row["bsr_subcategory"]),
                bsr_category_name=_str_or_empty(row["bsr_category_name"]),
                bsr_subcategory_name=_str_or_empty(row["bsr_subcategory_name"]),
                rating=_float_or_none(row["rating"]),
                review_count=_int_or_none(row["review_count"]),
                brand=_str_or_empty(row["brand"]),
                manufacturer=_str_or_empty(row["manufacturer"]),
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

    # ── Failed ASIN Management ──────────────────────

    def get_failed_asins(self) -> set[str]:
        """실패 ASIN 목록 조회. 한번 실패한 ASIN은 재수집하지 않는다."""
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table("SELECT asin FROM amz_failed_asins")
            return set(df["asin"].tolist()) if not df.empty else set()
        except Exception:
            logger.exception("Failed to read failed ASINs")
            return set()

    def save_failed_asins(self, asins: list[str], keyword: str = "") -> None:
        """실패 ASIN 기록."""
        if not asins:
            return
        now = datetime.now()
        rows = [
            {"asin": a, "keyword": keyword, "failed_at": now, "reason": "browse_ai_failure"}
            for a in asins
        ]
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_failed_asins")
            logger.info("Failed ASINs saved: %d", len(asins))
        except Exception:
            logger.exception("Failed to save failed ASINs")

    # ── Ingredient Cache (Gemini) ────────────────────

    def get_ingredient_cache(self, asins: list[str]) -> dict[str, list[Ingredient]]:
        """Gemini 추출 성분 캐시 조회. {asin: [Ingredient]} 반환."""
        if not asins:
            return {}
        placeholders = ",".join(["%s"] * len(asins))
        query = (
            f"SELECT asin, ingredient_name, common_name, category "
            f"FROM amz_ingredient_cache WHERE asin IN ({placeholders})"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, tuple(asins))
        except Exception:
            logger.exception("Failed to read ingredient cache")
            return {}
        if df.empty:
            return {}
        result: dict[str, list[Ingredient]] = {}
        for _, row in df.iterrows():
            asin = row["asin"]
            if asin not in result:
                result[asin] = []
            if row["ingredient_name"] != "_NONE_":
                result[asin].append(Ingredient(
                    name=row["ingredient_name"],
                    common_name=row["common_name"] or row["ingredient_name"],
                    category=row["category"],
                ))
        return result

    def save_ingredient_cache(self, gemini_results: list[ProductIngredients]) -> None:
        """Gemini 추출 성분을 캐시에 저장. 성분 0개인 제품도 마커 저장."""
        rows = []
        now = datetime.now()
        for pi in gemini_results:
            if pi.ingredients:
                for ing in pi.ingredients:
                    rows.append({
                        "asin": pi.asin,
                        "ingredient_name": ing.name,
                        "common_name": ing.common_name or ing.name,
                        "category": ing.category,
                        "extracted_at": now,
                    })
            else:
                rows.append({
                    "asin": pi.asin,
                    "ingredient_name": "_NONE_",
                    "common_name": "",
                    "category": "",
                    "extracted_at": now,
                })
        if not rows:
            return
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_ingredient_cache")
            logger.info("Ingredient cache saved: %d ingredients from %d products",
                       len(rows), len(gemini_results))
        except Exception:
            logger.exception("Failed to save ingredient cache")

    def harmonize_common_names(self) -> int:
        """common_name 자동 보정: 같은 name에 다른 common_name → 다수결 통일.

        동수면 먼저 수집된(extracted_at이 빠른) 값 우선.
        Returns: 보정된 레코드 수.
        """
        query = """
            SELECT ingredient_name, common_name, COUNT(*) as cnt,
                   MIN(extracted_at) as first_seen
            FROM amz_ingredient_cache
            WHERE ingredient_name != '_NONE_' AND common_name != ''
            GROUP BY ingredient_name, common_name
            ORDER BY ingredient_name, cnt DESC, first_seen ASC
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query)
        except Exception:
            logger.exception("Failed to read for harmonization")
            return 0

        if df.empty:
            return 0

        # 각 ingredient_name별 대표 common_name 결정
        canonical: dict[str, str] = {}
        for _, row in df.iterrows():
            inci = row["ingredient_name"]
            if inci not in canonical:
                # ORDER BY cnt DESC, first_seen ASC이므로 첫 번째가 대표
                canonical[inci] = row["common_name"]

        # 불일치 레코드 업데이트
        updated = 0
        try:
            with MysqlConnector(self._env) as conn:
                for inci, canon in canonical.items():
                    update_q = (
                        "UPDATE amz_ingredient_cache "
                        "SET common_name = %s "
                        "WHERE ingredient_name = %s AND common_name != %s"
                    )
                    conn.cursor.execute(update_q, (canon, inci, canon))
                    updated += conn.cursor.rowcount
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to harmonize common names")
            return 0

        if updated:
            logger.info("Harmonized %d ingredient records", updated)
        return updated

    # ── Market Report Cache ──────────────────────────

    def get_market_report_cache(self, keyword: str, product_count: int) -> str | None:
        """시장 리포트 캐시 조회. 제품 수가 같을 때만 반환."""
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        query = (
            "SELECT report_md FROM amz_market_report_cache "
            "WHERE keyword = %s AND product_count = %s AND generated_at >= %s"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (keyword, product_count, cutoff))
            if df.empty:
                return None
            return df.iloc[0]["report_md"]
        except Exception:
            logger.exception("Failed to read market report cache")
            return None

    def save_market_report_cache(
        self, keyword: str, report_md: str, product_count: int,
    ) -> None:
        """시장 리포트 캐시 저장."""
        if not report_md:
            return
        now = datetime.now()
        rows = [{
            "keyword": keyword,
            "report_md": report_md,
            "product_count": product_count,
            "generated_at": now,
        }]
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_market_report_cache")
            logger.info("Market report cache saved: keyword=%s", keyword)
        except Exception:
            logger.exception("Failed to save market report cache")
