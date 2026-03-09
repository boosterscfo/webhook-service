"""주간 배치 수집 엔트리포인트.

Usage:
    python -m amz_researcher.jobs.collect                  # 전체 활성 카테고리 (async, webhook 수신)
    python -m amz_researcher.jobs.collect 11058281          # 특정 카테고리만
    python -m amz_researcher.jobs.collect --sync             # 동기 polling 방식 (fallback)
"""
import asyncio
import logging
import sys

from app.config import settings
from amz_researcher.services.bright_data import BrightDataService, BrightDataError
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.product_db import ProductDBService
from amz_researcher.services.slack_sender import SlackSender
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)


async def run_collection(
    category_node_ids: list[str] | None = None,
    sync_mode: bool = False,
):
    """카테고리별 BSR Top 100 수집.

    Args:
        sync_mode: True면 polling으로 대기. False면 trigger만 보내고 종료 (webhook 수신).
    """
    product_db = ProductDBService("CFO")
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

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

        if sync_mode:
            # Polling 방식: trigger → poll → DB 적재
            logger.info("Starting SYNC collection for %d categories", len(urls))
            products = await bright_data.collect_categories(urls)
            try:
                collector = DataCollector("CFO")
                count = collector.process_snapshot(products)
                logger.info("Collection complete: %d products processed", count)
            except Exception as db_err:
                logger.exception("DB ingestion failed after collection")
                await slack.send_dm(
                    settings.AMZ_ADMIN_SLACK_ID,
                    f"[AMZ] DB ingestion failed: {db_err}",
                )
        else:
            # Async 방식: trigger만 보내고 종료 (webhook으로 수신)
            notify_url = f"{settings.WEBHOOK_BASE_URL}/webhook/brightdata"
            snapshot_id = await bright_data.trigger_collection(
                urls, notify_url=notify_url,
            )
            logger.info(
                "Collection triggered (async): snapshot_id=%s, %d categories, notify=%s",
                snapshot_id, len(urls), notify_url,
            )

    except (BrightDataError, TimeoutError) as e:
        logger.error("Collection failed: %s", e)
        await slack.send_dm(
            settings.AMZ_ADMIN_SLACK_ID,
            f"[AMZ] Collection failed: {e}",
        )
    except Exception:
        logger.exception("Unexpected error during collection")
    finally:
        await bright_data.close()
        await slack.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = sys.argv[1:]
    sync_mode = "--sync" in args
    node_ids = [a for a in args if not a.startswith("--")] or None
    asyncio.run(run_collection(node_ids, sync_mode=sync_mode))
