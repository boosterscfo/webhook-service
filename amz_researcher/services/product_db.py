import json
import logging
from datetime import datetime

from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)


class ProductDBService:
    """amz_products / amz_categories DB 조회 서비스."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def search_categories(self, keyword: str) -> list[dict]:
        """키워드로 카테고리 fuzzy 검색. 전체 카테고리 대상."""
        query = (
            "SELECT node_id, name, url, keywords, is_active, depth "
            "FROM amz_categories"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query)
        except Exception:
            logger.exception("Failed to search categories")
            return []
        if df.empty:
            return []

        keyword_lower = keyword.lower()
        results = []
        for _, row in df.iterrows():
            name = (row["name"] or "").lower()
            kws = (row["keywords"] or "").lower()
            if keyword_lower in name or keyword_lower in kws:
                results.append({
                    "node_id": row["node_id"],
                    "name": row["name"],
                    "url": row["url"],
                    "is_active": bool(row["is_active"]),
                    "depth": int(row["depth"]) if row["depth"] is not None else 0,
                })
        # 깊은 카테고리(더 구체적인) 우선 정렬
        results.sort(key=lambda x: -x["depth"])
        return results

    def get_products_by_category(self, category_node_id: str) -> list[dict]:
        """카테고리별 제품 조회 (amz_product_categories JOIN amz_products)."""
        query = """
            SELECT p.*
            FROM amz_products p
            JOIN amz_product_categories pc ON p.asin = pc.asin
            WHERE pc.category_node_id = %s
            ORDER BY p.bs_rank ASC
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (category_node_id,))
        except Exception:
            logger.exception("Failed to get products for category %s", category_node_id)
            return []
        if df.empty:
            return []
        return df.to_dict("records")

    def get_category_url(self, node_id: str) -> str | None:
        """특정 카테고리의 URL 반환 (active 여부 무관)."""
        query = "SELECT url FROM amz_categories WHERE node_id = %s"
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (node_id,))
        except Exception:
            logger.exception("Failed to get category URL for %s", node_id)
            return None
        return df.iloc[0]["url"] if not df.empty else None

    def get_all_active_category_urls(self) -> list[str]:
        """활성 카테고리의 URL 목록 반환 (수집 job용)."""
        query = "SELECT url FROM amz_categories WHERE is_active = TRUE"
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query)
        except Exception:
            logger.exception("Failed to get active category URLs")
            return []
        return df["url"].tolist() if not df.empty else []

    def list_categories(self) -> list[dict]:
        """전체 활성 카테고리 목록."""
        query = (
            "SELECT node_id, name, keywords FROM amz_categories "
            "WHERE is_active = TRUE ORDER BY name"
        )
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query)
        except Exception:
            logger.exception("Failed to list categories")
            return []
        return df.to_dict("records") if not df.empty else []

    def get_category_freshness(self, node_id: str) -> dict | None:
        """카테고리 데이터 freshness 조회.

        Returns:
            {"product_count": int, "collected_at": datetime} or None (미수집)
        """
        query = """
            SELECT COUNT(*) as product_count,
                   MAX(p.collected_at) as collected_at
            FROM amz_products p
            JOIN amz_product_categories pc ON p.asin = pc.asin
            WHERE pc.category_node_id = %s
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (node_id,))
        except Exception:
            logger.exception("Failed to get freshness for category %s", node_id)
            return None
        if df.empty:
            return None
        row = df.iloc[0]
        count = int(row["product_count"])
        if count == 0 or row["collected_at"] is None:
            return None
        return {"product_count": count, "collected_at": row["collected_at"]}

    # ── 키워드 유사 검색 ──────────────────────────────

    def find_similar_keywords(self, keyword: str, limit: int = 5) -> list[dict]:
        """DB에 수집 완료된 유사 키워드 검색.

        단어 단위로 LIKE 매칭하여 일치 단어 수 기준 정렬.
        Returns: [{keyword, product_count, searched_at, match_score}, ...]
        """
        from app.config import settings

        normalized = " ".join(keyword.lower().split())
        words = normalized.split()
        if not words:
            return []

        # 각 단어를 LIKE로 매칭하고, 일치 단어 수를 score로 계산
        score_expr = " + ".join(
            [f"(keyword LIKE %s)" for _ in words]
        )
        like_params = [f"%{w}%" for w in words]

        # 최소 1단어 이상 매칭, 정확히 일치하는 키워드는 제외
        query = f"""
            SELECT keyword, product_count, searched_at,
                   ({score_expr}) AS match_score
            FROM amz_keyword_search_log
            WHERE status = 'completed'
              AND searched_at >= NOW() - INTERVAL %s DAY
              AND keyword != %s
              AND ({score_expr}) >= 1
            ORDER BY match_score DESC, searched_at DESC
            LIMIT %s
        """
        params = tuple(like_params) + (settings.AMZ_KEYWORD_CACHE_DAYS, normalized) + tuple(like_params) + (limit,)

        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, params)
        except Exception:
            logger.exception("Failed to find similar keywords for %s", keyword)
            return []

        if df.empty:
            return []

        # 중복 키워드 제거 (가장 최근 것만)
        seen = set()
        results = []
        for row in df.to_dict("records"):
            kw = row["keyword"]
            if kw not in seen:
                seen.add(kw)
                results.append(row)
        return results

    # ── 키워드 검색 캐시 ──────────────────────────────

    def get_keyword_cache(self, keyword: str) -> dict | None:
        """7일 이내 키워드 검색 캐시 조회.

        Returns:
            {keyword, product_count, searched_at, status, snapshot_id} or None
        """
        from app.config import settings

        normalized = " ".join(keyword.lower().split())
        query = """
            SELECT keyword, product_count, searched_at, status, snapshot_id
            FROM amz_keyword_search_log
            WHERE keyword = %s
              AND searched_at >= NOW() - INTERVAL %s DAY
            ORDER BY searched_at DESC
            LIMIT 1
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (normalized, settings.AMZ_KEYWORD_CACHE_DAYS))
        except Exception:
            logger.exception("Failed to get keyword cache for %s", keyword)
            return None
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def get_keyword_products(self, keyword: str, searched_at) -> list[dict]:
        """캐시된 키워드 검색 결과 조회."""
        normalized = " ".join(keyword.lower().split())
        query = """
            SELECT * FROM amz_keyword_products
            WHERE keyword = %s AND searched_at = %s
            ORDER BY position ASC
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (normalized, searched_at))
        except Exception:
            logger.exception("Failed to get keyword products for %s", keyword)
            return []
        return df.to_dict("records") if not df.empty else []

    def save_keyword_search_log(
        self, keyword: str, snapshot_id: str = "",
        response_url: str = "", channel_id: str = "",
    ):
        """검색 로그 INSERT (status='collecting'). searched_at 반환."""
        from datetime import datetime

        normalized = " ".join(keyword.lower().split())
        searched_at = datetime.now()
        query = """
            INSERT INTO amz_keyword_search_log
                (keyword, snapshot_id, response_url, channel_id, status, searched_at)
            VALUES (%s, %s, %s, %s, 'collecting', %s)
        """
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (normalized, snapshot_id, response_url, channel_id, searched_at))
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to save keyword search log for %s", keyword)
            raise
        return searched_at

    def get_keyword_search_by_snapshot(self, snapshot_id: str) -> dict | None:
        """snapshot_id로 키워드 검색 로그 조회 (webhook 콜백용)."""
        query = """
            SELECT keyword, snapshot_id, response_url, channel_id, status, searched_at
            FROM amz_keyword_search_log
            WHERE snapshot_id = %s
            ORDER BY searched_at DESC
            LIMIT 1
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, (snapshot_id,))
        except Exception:
            logger.exception("Failed to get keyword search by snapshot %s", snapshot_id)
            return None
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def update_keyword_search_log(
        self, keyword: str, searched_at, status: str, product_count: int = 0,
    ):
        """검색 로그 상태 업데이트."""
        normalized = " ".join(keyword.lower().split())
        query = """
            UPDATE amz_keyword_search_log
            SET status = %s, product_count = %s
            WHERE keyword = %s AND searched_at = %s
        """
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (status, product_count, normalized, searched_at))
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to update keyword search log for %s", keyword)

    def activate_category(self, node_id: str) -> None:
        """카테고리를 is_active=TRUE로 전환."""
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(
                    "UPDATE amz_categories SET is_active = TRUE WHERE node_id = %s",
                    (node_id,),
                )
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to activate category %s", node_id)

    def update_category_keywords(self, node_id: str, keywords: str) -> bool:
        """카테고리 검색 키워드 업데이트."""
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(
                    "UPDATE amz_categories SET keywords = %s WHERE node_id = %s",
                    (keywords[:500], node_id),
                )
                conn.connection.commit()
            return True
        except Exception:
            logger.exception("Failed to update keywords for node_id=%s", node_id)
            return False

    def save_voice_keywords(self, asin_keywords: dict[str, dict[str, list[str]]]) -> int:
        """제품별 voice 키워드 DB 저장.

        Args:
            asin_keywords: {asin: {"positive": [...], "negative": [...]}}

        Returns:
            업데이트된 행 수.
        """
        if not asin_keywords:
            return 0
        query = """
            UPDATE amz_products
            SET voice_positive = %s, voice_negative = %s
            WHERE asin = %s
        """
        updated = 0
        try:
            with MysqlConnector(self._env) as conn:
                for asin, kws in asin_keywords.items():
                    pos = json.dumps(kws.get("positive", []), ensure_ascii=False)
                    neg = json.dumps(kws.get("negative", []), ensure_ascii=False)
                    conn.cursor.execute(query, (pos, neg, asin))
                    updated += conn.cursor.rowcount
                conn.connection.commit()
            logger.info("Saved voice keywords for %d products", updated)
        except Exception:
            logger.exception("Failed to save voice keywords")
        return updated

    def load_voice_keywords(self, asins: list[str]) -> dict[str, dict[str, list[str]]]:
        """DB에서 제품별 voice 키워드 로드.

        Returns:
            {asin: {"positive": [...], "negative": [...]}} — 키워드가 있는 제품만.
        """
        if not asins:
            return {}
        placeholders = ",".join(["%s"] * len(asins))
        query = f"""
            SELECT asin, voice_positive, voice_negative
            FROM amz_products
            WHERE asin IN ({placeholders})
              AND voice_positive IS NOT NULL
        """
        try:
            with MysqlConnector(self._env) as conn:
                df = conn.read_query_table(query, tuple(asins))
        except Exception:
            logger.exception("Failed to load voice keywords")
            return {}
        if df.empty:
            return {}
        result = {}
        for _, row in df.iterrows():
            pos = row["voice_positive"]
            neg = row["voice_negative"]
            if isinstance(pos, str):
                pos = json.loads(pos)
            if isinstance(neg, str):
                neg = json.loads(neg)
            result[row["asin"]] = {
                "positive": pos or [],
                "negative": neg or [],
            }
        return result

    # ── 리포트 요청 로그 ──────────────────────────────

    def log_request_start(
        self,
        user_id: str,
        channel_id: str,
        request_type: str,
        query_value: str,
    ) -> int | None:
        """요청 시작 로그. INSERT 후 id 반환."""
        query = """
            INSERT INTO amz_report_request_log
                (user_id, channel_id, request_type, query_value, status, requested_at)
            VALUES (%s, %s, %s, %s, 'started', %s)
        """
        now = datetime.now()
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (user_id, channel_id, request_type, query_value, now))
                conn.connection.commit()
                return conn.cursor.lastrowid
        except Exception:
            logger.exception("Failed to log request start")
            return None

    def log_request_complete(
        self,
        log_id: int,
        product_count: int = 0,
        report_id: str = "",
        duration_sec: float | None = None,
    ) -> None:
        """요청 완료 로그 업데이트."""
        query = """
            UPDATE amz_report_request_log
            SET status = 'completed', product_count = %s, report_id = %s,
                duration_sec = %s, completed_at = %s
            WHERE id = %s
        """
        now = datetime.now()
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (product_count, report_id, duration_sec, now, log_id))
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to log request complete")

    def log_request_failed(self, log_id: int, error: str = "") -> None:
        """요청 실패 로그 업데이트."""
        query = """
            UPDATE amz_report_request_log
            SET status = 'failed', error_message = %s, completed_at = %s
            WHERE id = %s
        """
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (error[:500], datetime.now(), log_id))
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to log request failure")
