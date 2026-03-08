"""주간 배치 수집 엔트리포인트.

Usage:
    python -m amz_researcher.jobs.collect                  # 전체 활성 카테고리
    python -m amz_researcher.jobs.collect 11058281          # 특정 카테고리만
    python -m amz_researcher.jobs.collect 11058281 3591081  # 여러 카테고리
"""
import asyncio
import logging
import sys

from app.config import settings
from amz_researcher.services.bright_data import BrightDataService, BrightDataError
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.product_db import ProductDBService
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)


async def run_collection(category_node_ids: list[str] | None = None):
    """카테고리별 BSR Top 100 수집 → DB 적재."""
    product_db = ProductDBService("CFO")
    collector = DataCollector("CFO")
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )

    try:
        if category_node_ids:
            urls = []
            for nid in category_node_ids:
                with MysqlConnector("CFO") as conn:
                    df = conn.read_query_table(
                        "SELECT url FROM amz_categories WHERE node_id = %s AND is_active = TRUE",
                        (nid,),
                    )
                if not df.empty:
                    urls.append(df.iloc[0]["url"])
                else:
                    logger.warning("Category node_id=%s not found or inactive", nid)
        else:
            urls = product_db.get_all_active_category_urls()

        if not urls:
            logger.warning("No active categories to collect")
            return

        logger.info("Starting collection for %d categories: %s", len(urls), urls)
        products = await bright_data.collect_categories(urls)
        count = collector.process_snapshot(products)
        logger.info("Collection complete: %d products processed", count)

    except (BrightDataError, TimeoutError) as e:
        logger.error("Collection failed: %s", e)
    except Exception:
        logger.exception("Unexpected error during collection")
    finally:
        await bright_data.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    node_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(run_collection(node_ids))
