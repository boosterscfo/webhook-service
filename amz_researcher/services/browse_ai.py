import asyncio
import logging
import re
from urllib.parse import quote_plus, unquote

import httpx

from amz_researcher.models import ProductDetail, SearchProduct
from amz_researcher.services.html_parser import (
    parse_bsr,
    parse_customer_reviews,
    parse_product_table,
)

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


def _classify_html_sections(texts: dict) -> dict[str, str]:
    """Browse.ai capturedTexts를 <h1> 헤딩 기반으로 올바른 섹션에 재배치.

    Browse.ai 로봇이 키를 뒤섞어 반환하는 경우(~26%) 대비,
    키 이름 대신 HTML 내부 <h1> 태그의 섹션명으로 분류한다.
    """
    sections: dict[str, str] = {
        "item_details": "",
        "features": "",
        "measurements": "",
        "additional_details": "",
        "ingredients": texts.get("ingredients") or "",
    }

    heading_map = {
        "Item details": "item_details",
        "Features": "features",
        "Measurements": "measurements",
        "Additional details": "additional_details",
    }

    html_keys = ("item_details", "features", "measurements", "details")
    for key in html_keys:
        html = texts.get(key) or ""
        if not html:
            continue
        # <h1> 헤딩으로 섹션 판별
        matched = False
        for heading, section_key in heading_map.items():
            if heading in html:
                sections[section_key] = html
                matched = True
                break
        if not matched:
            # 헤딩이 없는 HTML은 원래 키 위치에 유지
            fallback_key = "additional_details" if key == "details" else key
            if not sections[fallback_key]:
                sections[fallback_key] = html

    return sections


def parse_detail_from_captured_texts(asin: str, texts: dict) -> ProductDetail:
    """capturedTexts dict → ProductDetail 변환.

    <h1> 헤딩 기반으로 섹션을 재분류한 후 파싱한다.
    """
    sections = _classify_html_sections(texts)

    ingredients_raw = sections["ingredients"]
    features = parse_product_table(sections["features"])
    measurements = parse_product_table(sections["measurements"])
    additional_details = parse_product_table(sections["additional_details"])

    item_details_html = sections["item_details"]
    item_details = parse_product_table(item_details_html)
    bsr_list = parse_bsr(item_details_html)
    rating, review_count = parse_customer_reviews(item_details_html)

    bsr_category = bsr_list[0]["rank"] if len(bsr_list) > 0 else None
    bsr_category_name = bsr_list[0]["category"] if len(bsr_list) > 0 else ""
    bsr_subcategory = bsr_list[1]["rank"] if len(bsr_list) > 1 else None
    bsr_subcategory_name = bsr_list[1]["category"] if len(bsr_list) > 1 else ""

    if bsr_list:
        item_details["bsr"] = bsr_list
    if rating is not None:
        item_details["rating"] = rating
    if review_count is not None:
        item_details["review_count"] = review_count

    return ProductDetail(
        asin=asin,
        ingredients_raw=ingredients_raw,
        features=features,
        measurements=measurements,
        item_details=item_details,
        additional_details=additional_details,
        bsr_category=bsr_category,
        bsr_subcategory=bsr_subcategory,
        bsr_category_name=bsr_category_name,
        bsr_subcategory_name=bsr_subcategory_name,
        rating=rating,
        review_count=review_count,
        brand=item_details.get("Brand Name", ""),
        manufacturer=item_details.get("Manufacturer", ""),
        product_url=f"https://www.amazon.com/dp/{asin}",
    )


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

    async def run_search(self, keyword: str) -> list[SearchProduct]:
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

        products = parse_search_results(raw_items)
        logger.info("Search completed: %d products parsed", len(products))
        return products

    async def run_detail(self, asin: str) -> ProductDetail | None:
        try:
            task_id = await self._create_task(
                self.detail_robot_id,
                {"originUrl": f"https://www.amazon.com/dp/{asin}"},
            )
            result = await self._poll_task(self.detail_robot_id, task_id)
            texts = result.get("capturedTexts", {})
            return parse_detail_from_captured_texts(asin, texts)
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
        max_attempts: int = 20, interval: int = 30,
    ) -> list[dict]:
        all_tasks: list[dict] = []

        for _ in range(max_attempts):
            await asyncio.sleep(interval)
            resp = await self.client.get(
                f"/robots/{robot_id}/bulk-runs/{bulk_run_id}",
            )
            resp.raise_for_status()
            result = resp.json().get("result", {})
            bulk_run = result.get("bulkRun", {})
            status = bulk_run.get("status", "")
            total = bulk_run.get("tasksCount", 0)
            success = bulk_run.get("successfulTasks", 0)
            failed = bulk_run.get("failedTasks", 0)
            logger.info(
                "Bulk run %s: status=%s, %d/%d done (%d failed)",
                bulk_run_id, status, success + failed, total, failed,
            )

            if status in ("completed", "finished"):
                robot_tasks = result.get("robotTasks", {})
                items = robot_tasks.get("items", [])
                all_tasks.extend(items)

                has_more = robot_tasks.get("hasMore", False)
                page = 2
                while has_more:
                    resp = await self.client.get(
                        f"/robots/{robot_id}/bulk-runs/{bulk_run_id}",
                        params={"page": page},
                    )
                    resp.raise_for_status()
                    page_result = resp.json().get("result", {})
                    page_tasks = page_result.get("robotTasks", {})
                    page_items = page_tasks.get("items", [])
                    if not page_items:
                        break
                    all_tasks.extend(page_items)
                    has_more = page_tasks.get("hasMore", False)
                    page += 1

                return all_tasks

        raise TimeoutError(
            f"Bulk run polling timeout after {max_attempts * interval}s"
        )

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

        raw_tasks = await self._poll_bulk_run(self.detail_robot_id, bulk_run_id)

        details = []
        for task in raw_tasks:
            if task.get("status") != "successful":
                continue
            try:
                texts = task.get("capturedTexts", {})
                input_url = (
                    task.get("inputParameters", {}).get("originUrl", "")
                )
                asin = extract_asin(input_url)
                if not asin:
                    continue
                details.append(parse_detail_from_captured_texts(asin, texts))
            except Exception:
                logger.exception("Failed to parse bulk task: %s", task.get("id"))

        logger.info("Detail batch: %d/%d succeeded", len(details), len(asins))
        return details

    async def close(self):
        await self.client.aclose()
