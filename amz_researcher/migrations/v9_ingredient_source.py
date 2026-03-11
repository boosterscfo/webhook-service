"""V9: amz_ingredient_cache에 source 컬럼 추가.

Gemini 성분 추출 시 출처 구분:
- "featured": title/features에서만 확인된 성분
- "inci": 전성분(ingredients_raw)에서만 확인된 성분
- "both": 양쪽 모두에서 확인된 성분
- "": 레거시 (source 미분류)
"""
import logging

from app.config import settings
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

ALTER_SQLS = [
    "ALTER TABLE amz_ingredient_cache ADD COLUMN source VARCHAR(20) DEFAULT '' AFTER category",
]


def run_migration(environment: str = "CFO"):
    with MysqlConnector(environment) as conn:
        for sql in ALTER_SQLS:
            try:
                conn.cursor.execute(sql)
                logger.info("Executed: %s", sql.strip()[:80])
            except Exception as e:
                if "Duplicate column name" in str(e):
                    logger.info("Column already exists, skipping")
                else:
                    raise
        conn.connection.commit()
    print("✅ source column added to amz_ingredient_cache")


if __name__ == "__main__":
    run_migration()
