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
