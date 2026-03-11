"""V8: 제품별 consumer voice 키워드 컬럼 추가.

Gemini 동적 추출된 긍정/부정 키워드를 제품별로 저장.
JSON 배열 형태: ["moisturizing", "lightweight", ...]
"""
import logging

from app.config import settings
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

ALTER_SQLS = [
    "ALTER TABLE amz_products ADD COLUMN voice_positive JSON DEFAULT NULL",
    "ALTER TABLE amz_products ADD COLUMN voice_negative JSON DEFAULT NULL",
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
    print("✅ voice_positive, voice_negative columns added to amz_products")


if __name__ == "__main__":
    run_migration()
