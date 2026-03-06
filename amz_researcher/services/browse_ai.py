import asyncio
import logging
import re
from urllib.parse import quote_plus, unquote

import httpx

from amz_researcher.models import ProductDetail, SearchProduct

logger = logging.getLogger(__name__)

BASE_URL = "https://api.browse.ai/v2"


def extract_asin(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m:
        return m.group(1)
    decoded = unquote(url)
    m = re.search(r"/dp/([A-Z0-9]{10})", decoded)
    if m:
        return m.group(1)
    return None


def parse_reviews(s: str) -> int:
    if not s:
        return 0
    s = s.strip().strip("()")
    s = s.replace(",", "")
    if s.upper().endswith("K"):
        return int(float(s[:-1]) * 1000)
    try:
        return int(float(s))
    except ValueError:
        return 0


def parse_volume(s: str) -> int:
    if not s:
        return 0
    m = re.search(r"([\d.]+)\s*K\+", s, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"(\d+)\+", s)
    if m:
        return int(m.group(1))
    return 0


def parse_price(s: str) -> float | None:
    if not s:
        return None
    m = re.search(r"\$\s*([\d,]+\.?\d*)", s)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def parse_search_results(raw_items: list[dict]) -> list[SearchProduct]:
    products = []
    for item in raw_items:
        status = item.get("_STATUS", "")
        if status == "REMOVED":
            continue
        position = item.get("Position")
        if not position:
            continue
        try:
            pos = int(position)
        except (ValueError, TypeError):
            continue

        link = item.get("Product Link", "") or ""
        asin = extract_asin(link)
        if not asin:
            continue

        price_raw = item.get("Price", "") or ""
        reviews_raw = item.get("Reviews", "") or ""

        products.append(SearchProduct(
            position=pos,
            title=item.get("Title", "") or "",
            asin=asin,
            price=parse_price(price_raw),
            price_raw=price_raw,
            reviews=parse_reviews(reviews_raw),
            reviews_raw=reviews_raw,
            rating=float(item.get("Rating", 0) or 0),
            sponsored=bool(item.get("Sponsored")),
            product_link=link,
        ))

    products.sort(key=lambda p: p.position)
    return products


class BrowseAiService:
    def __init__(self, api_key: str, search_robot_id: str, detail_robot_id: str):
        self.api_key = api_key
        self.search_robot_id = search_robot_id
        self.detail_robot_id = detail_robot_id
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def _create_task(self, robot_id: str, input_params: dict) -> str:
        resp = await self.client.post(
            f"/robots/{robot_id}/tasks",
            json={"inputParameters": input_params},
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("result", {}).get("id")
        if not task_id:
            raise RuntimeError(f"No task ID in response: {data}")
        return task_id

    async def _check_task(self, robot_id: str, task_id: str) -> dict:
        resp = await self.client.get(f"/robots/{robot_id}/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json().get("result", {})

    async def _poll_task(
        self, robot_id: str, task_id: str,
        max_attempts: int = 20, interval: int = 30,
    ) -> dict:
        current_id = task_id
        for _ in range(max_attempts):
            await asyncio.sleep(interval)
            result = await self._check_task(robot_id, current_id)
            status = result.get("status", "")

            if status == "successful":
                return result
            elif status == "failed":
                retry_id = result.get("retriedByTaskId")
                if retry_id:
                    logger.info("Task %s failed, following retry → %s", current_id, retry_id)
                    current_id = retry_id
                    continue
                error_msg = result.get("userFriendlyError", "Unknown error")
                raise RuntimeError(f"Browse.ai task failed: {error_msg}")

        raise TimeoutError(f"Polling timeout after {max_attempts * interval}s")

    async def run_search(
        self, keyword: str, max_products: int = 30,
    ) -> list[SearchProduct]:
        encoded = quote_plus(keyword)
        amazon_url = f"https://www.amazon.com/s?k={encoded}"
        task_id = await self._create_task(
            self.search_robot_id,
            {"amazon_url": amazon_url},
        )
        logger.info("Search task created: %s for keyword=%s", task_id, keyword)

        result = await self._poll_task(self.search_robot_id, task_id)
        raw_items = result.get("capturedLists", {}).get("products", [])
        if not raw_items:
            raw_items = result.get("capturedLists", {})
            if isinstance(raw_items, dict):
                for v in raw_items.values():
                    if isinstance(v, list):
                        raw_items = v
                        break
                else:
                    raw_items = []

        products = parse_search_results(raw_items)[:max_products]
        logger.info("Search completed: %d products parsed (max %d)", len(products), max_products)
        return products

    async def run_detail(self, asin: str) -> ProductDetail | None:
        try:
            task_id = await self._create_task(
                self.detail_robot_id,
                {"originUrl": f"https://www.amazon.com/dp/{asin}"},
            )
            result = await self._poll_task(self.detail_robot_id, task_id)
            texts = result.get("capturedTexts", {})
            return ProductDetail(
                asin=asin,
                title=texts.get("title") or "",
                top_highlights=texts.get("top_highlights") or "",
                features=texts.get("features") or "",
                measurements=texts.get("measurements") or "",
                bsr=texts.get("bsr") or "",
                volume_raw=texts.get("volumn") or "",
                volume=parse_volume(texts.get("volumn") or ""),
                product_url=f"https://www.amazon.com/dp/{asin}",
            )
        except Exception:
            logger.exception("Detail crawl failed for ASIN=%s", asin)
            return None

    async def _create_bulk_run(
        self, robot_id: str, input_params_list: list[dict], title: str = "",
    ) -> str:
        resp = await self.client.post(
            f"/robots/{robot_id}/bulk-runs",
            json={
                "title": title,
                "inputParameters": input_params_list,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        bulk_run_id = (
            data.get("result", {}).get("bulkRun", {}).get("id")
        )
        if not bulk_run_id:
            raise RuntimeError(f"No bulk run ID in response: {data}")
        return bulk_run_id

    async def _poll_bulk_run(
        self, robot_id: str, bulk_run_id: str,
        max_attempts: int = 40, interval: int = 30,
    ) -> dict:
        for attempt in range(max_attempts):
            await asyncio.sleep(interval)
            resp = await self.client.get(
                f"/robots/{robot_id}/bulk-runs/{bulk_run_id}",
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            status = result.get("status", "")
            total = result.get("totalTaskCount", 0)
            success = result.get("successfulTaskCount", 0)
            failed = result.get("failedTaskCount", 0)
            logger.info(
                "Bulk run %s: status=%s, %d/%d done (%d failed)",
                bulk_run_id, status, success + failed, total, failed,
            )
            if status in ("completed", "finished"):
                return result
            if success + failed >= total and total > 0:
                return result
        raise TimeoutError(
            f"Bulk run polling timeout after {max_attempts * interval}s"
        )

    async def _fetch_bulk_tasks(
        self, robot_id: str, bulk_run_id: str,
    ) -> list[dict]:
        tasks = []
        page = 1
        while True:
            resp = await self.client.get(
                f"/robots/{robot_id}/tasks",
                params={
                    "robotBulkRunId": bulk_run_id,
                    "status": "successful",
                    "page": page,
                    "pageSize": 10,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("robotTasks", {}).get("items", [])
            if not items:
                break
            tasks.extend(items)
            total = data.get("result", {}).get("robotTasks", {}).get("totalCount", 0)
            if len(tasks) >= total:
                break
            page += 1
        return tasks

    async def run_details_batch(
        self, asins: list[str],
    ) -> list[ProductDetail]:
        if not asins:
            return []

        input_params_list = [
            {"originUrl": f"https://www.amazon.com/dp/{asin}"}
            for asin in asins
        ]
        bulk_run_id = await self._create_bulk_run(
            self.detail_robot_id,
            input_params_list,
            title=f"detail-batch-{len(asins)}",
        )
        logger.info(
            "Bulk run created: %s for %d ASINs", bulk_run_id, len(asins),
        )

        await self._poll_bulk_run(self.detail_robot_id, bulk_run_id)

        raw_tasks = await self._fetch_bulk_tasks(
            self.detail_robot_id, bulk_run_id,
        )
        logger.info("Bulk run tasks fetched: %d successful", len(raw_tasks))

        details = []
        for task in raw_tasks:
            try:
                texts = task.get("capturedTexts", {})
                input_url = (
                    task.get("inputParameters", {}).get("originUrl", "")
                )
                asin = extract_asin(input_url)
                if not asin:
                    continue
                details.append(ProductDetail(
                    asin=asin,
                    title=texts.get("title") or "",
                    top_highlights=texts.get("top_highlights") or "",
                    features=texts.get("features") or "",
                    measurements=texts.get("measurements") or "",
                    bsr=texts.get("bsr") or "",
                    volume_raw=texts.get("volumn") or "",
                    volume=parse_volume(texts.get("volumn") or ""),
                    product_url=f"https://www.amazon.com/dp/{asin}",
                ))
            except Exception:
                logger.exception("Failed to parse bulk task: %s", task.get("id"))

        logger.info("Detail batch: %d/%d succeeded", len(details), len(asins))
        return details

    async def close(self):
        await self.client.aclose()
