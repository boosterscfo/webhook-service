import json
import logging
import math
from datetime import datetime, timedelta

import pandas as pd

from amz_researcher.models import Ingredient, ProductDetail, ProductIngredients, SearchProduct
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 30

# ── Failed ASIN retry policy ─────────────────
MAX_RETRY_COUNT = 3          # 일시적 실패 최대 재시도 횟수
RETRY_COOLDOWN_DAYS = 7      # 재시도 대기 기간 (일)

# 구조적 실패 → 즉시 영구 스킵
PERMANENT_REASONS = frozenset({"not_found", "blocked", "asin_invalid"})
# 일시적 실패 → MAX_RETRY_COUNT까지 재시도 허용
TRANSIENT_REASONS = frozenset({"timeout", "batch_error", "browse_ai_failure", "network_error"})


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

    def save_detail_cache(self, details: list[ProductDetail]) -> bool:
        """상세 정보를 캐시에 저장 (upsert). 성공 시 True."""
        if not details:
            return True
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
            return True
        except Exception:
            logger.exception("Failed to save detail cache")
            return False

    # ── Failed ASIN Management ──────────────────────

    def get_failed_asins(self) -> set[str]:
        """스킵해야 할 ASIN 목록 조회.

        스킵 조건:
        - 구조적 실패 (not_found, blocked 등) → 영구 스킵
        - 일시적 실패 + retry_count >= MAX_RETRY_COUNT → 스킵
        - 일시적 실패 + 쿨다운 기간 내 → 스킵 (아직 대기 중)

        재시도 대상 (반환하지 않음):
        - 일시적 실패 + retry_count < MAX_RETRY_COUNT + 쿨다운 경과
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(
                    "SELECT asin, reason, retry_count, last_failed_at "
                    "FROM amz_failed_asins"
                )
            if df.empty:
                return set()

            skip = set()
            now = datetime.now()
            cooldown_cutoff = now - timedelta(days=RETRY_COOLDOWN_DAYS)

            for _, row in df.iterrows():
                reason = row["reason"] or "browse_ai_failure"
                retry_count = int(row["retry_count"] or 0)
                last_failed = row["last_failed_at"]

                # 구조적 실패 → 영구 스킵
                if reason in PERMANENT_REASONS:
                    skip.add(row["asin"])
                    continue

                # 일시적 실패: 재시도 한도 초과 → 스킵
                if retry_count >= MAX_RETRY_COUNT:
                    skip.add(row["asin"])
                    continue

                # 일시적 실패: 쿨다운 기간 내 → 스킵 (아직 대기)
                if last_failed and last_failed >= cooldown_cutoff:
                    skip.add(row["asin"])
                    continue

                # 그 외 → 재시도 대상 (skip에 추가하지 않음)

            return skip
        except Exception:
            logger.exception("Failed to read failed ASINs")
            return set()

    def save_failed_asins(
        self, asins: list[str], keyword: str = "",
        reason: str = "browse_ai_failure",
    ) -> None:
        """실패 ASIN 기록. 기존 레코드가 있으면 retry_count 증가."""
        if not asins:
            return
        now = datetime.now()

        # 기존 실패 기록 조회
        existing: dict[str, int] = {}
        try:
            placeholders = ",".join(["%s"] * len(asins))
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(
                    f"SELECT asin, retry_count FROM amz_failed_asins "
                    f"WHERE asin IN ({placeholders})",
                    tuple(asins),
                )
            if not df.empty:
                existing = dict(zip(df["asin"], df["retry_count"].astype(int)))
        except Exception:
            logger.debug("Could not read existing failed ASINs, treating as new")

        rows = [
            {
                "asin": a,
                "keyword": keyword,
                "last_failed_at": now,
                "reason": reason,
                "retry_count": existing.get(a, 0) + (1 if a in existing else 0),
            }
            for a in asins
        ]
        try:
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df, "amz_failed_asins")
            logger.info("Failed ASINs saved: %d (reason=%s)", len(asins), reason)
        except Exception:
            logger.exception("Failed to save failed ASINs")

    # ── Ingredient Cache (Gemini) ────────────────────

    def get_ingredient_cache(self, asins: list[str]) -> dict[str, list[Ingredient]]:
        """Gemini 추출 성분 캐시 조회. {asin: [Ingredient]} 반환.

        성분은 BSR 재수집(가격/순위 갱신)과 무관하게 변하지 않으므로
        TTL(30일)만으로 유효성 판단. collected_at 기반 stale 비교 제거.
        """
        if not asins:
            return {}
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        placeholders = ",".join(["%s"] * len(asins))
        query = (
            f"SELECT asin, ingredient_name, common_name, category, "
            f"COALESCE(source, '') as source "
            f"FROM amz_ingredient_cache "
            f"WHERE asin IN ({placeholders}) AND extracted_at >= %s"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (*asins, cutoff))
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
                    source=row.get("source", ""),
                ))
        return result

    def save_ingredient_cache(self, gemini_results: list[ProductIngredients]) -> bool:
        """Gemini 추출 성분을 캐시에 저장. 성분 0개인 제품도 마커 저장. 성공 시 True."""
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
                        "source": ing.source or "",
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
            return True
        try:
            # delete & insert: 프롬프트 변경 시 성분 목록이 달라질 수 있으므로
            # 기존 행을 삭제 후 새로 삽입 (유령 데이터 방지)
            asins = list({pi.asin for pi in gemini_results})
            placeholders = ",".join(["%s"] * len(asins))
            df = pd.DataFrame(rows)
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(
                    f"DELETE FROM amz_ingredient_cache WHERE asin IN ({placeholders})",
                    asins,
                )
                conn.upsert_data(df, "amz_ingredient_cache")
            logger.info("Ingredient cache saved: %d ingredients from %d products",
                       len(rows), len(gemini_results))
            return True
        except Exception:
            logger.exception("Failed to save ingredient cache")
            return False

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

    def _get_data_freshness(self, category_name: str) -> datetime | None:
        """카테고리 제품의 최신 collected_at 조회.

        collected_at은 Bright Data에서 실제 새 데이터를 수집한 시점.
        updated_at은 upsert 시 값이 동일해도 갱신되므로 부적합.
        """
        query = """
            SELECT MAX(p.collected_at) as latest
            FROM amz_products p
            JOIN amz_product_categories pc ON p.asin = pc.asin
            JOIN amz_categories c ON pc.category_node_id = c.node_id
            WHERE c.name = %s
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (category_name,))
            if df.empty or df.iloc[0]["latest"] is None:
                return None
            return pd.Timestamp(df.iloc[0]["latest"]).to_pydatetime()
        except Exception:
            logger.exception("Failed to get data freshness for %s", category_name)
            return None

    def get_market_report_cache(self, keyword: str, product_count: int) -> str | None:
        """시장 리포트 캐시 조회.

        무효화 조건:
        - TTL 30일 초과
        - 제품 수가 다름
        - 캐시 생성 이후 제품 데이터가 업데이트됨
        """
        cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
        query = (
            "SELECT report_md, generated_at FROM amz_market_report_cache "
            "WHERE keyword = %s AND product_count = %s AND generated_at >= %s"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (keyword, product_count, cutoff))
            if df.empty:
                return None

            generated_at = pd.Timestamp(df.iloc[0]["generated_at"]).to_pydatetime()

            # 데이터 freshness 체크: 제품이 캐시 이후에 업데이트되었으면 무효화
            data_updated = self._get_data_freshness(keyword)
            if data_updated and data_updated > generated_at:
                logger.info(
                    "Market report cache stale: keyword=%s, "
                    "cached=%s, data_updated=%s",
                    keyword, generated_at, data_updated,
                )
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
