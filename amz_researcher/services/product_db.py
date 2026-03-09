import logging

from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)


class ProductDBService:
    """amz_products / amz_categories DB 조회 서비스."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def search_categories(self, keyword: str) -> list[dict]:
        """키워드로 카테고리 fuzzy 검색. is_active=TRUE만."""
        query = (
            "SELECT node_id, name, url, keywords "
            "FROM amz_categories WHERE is_active = TRUE"
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
                })
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
        """특정 카테고리의 URL 반환."""
        query = "SELECT url FROM amz_categories WHERE node_id = %s AND is_active = TRUE"
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

    def add_category(self, name: str, url: str) -> dict:
        """Amazon Best Sellers URL로 카테고리 추가. node_id는 URL에서 추출."""
        import re
        m = re.search(r"/(\d+)(?:\?|$)", url)
        if not m:
            return {"ok": False, "error": "URL에서 node_id를 추출할 수 없습니다."}
        node_id = m.group(1)

        query = """
            INSERT INTO amz_categories (node_id, name, url, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON DUPLICATE KEY UPDATE name=VALUES(name), url=VALUES(url), is_active=TRUE
        """
        try:
            with MysqlConnector(self._env) as conn:
                conn.cursor.execute(query, (node_id, name, url))
                conn.connection.commit()
        except Exception:
            logger.exception("Failed to add category %s", name)
            return {"ok": False, "error": "DB 저장 실패"}
        return {"ok": True, "node_id": node_id, "name": name}
