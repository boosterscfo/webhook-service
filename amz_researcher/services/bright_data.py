import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class BrightDataError(Exception):
    pass


class BrightDataService:
    """Bright Data Web Scraper API 클라이언트."""

    def __init__(self, api_token: str, dataset_id: str):
        self.api_token = api_token
        self.dataset_id = dataset_id
        self.base_url = "https://api.brightdata.com/datasets/v3"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def trigger_collection(
        self, category_urls: list[str], limit_per_input: int = 100,
    ) -> str:
        """수집 트리거 → snapshot_id 반환."""
        url = (
            f"{self.base_url}/trigger"
            f"?dataset_id={self.dataset_id}"
            f"&type=discover_new"
            f"&discover_by=best_sellers_url"
            f"&limit_per_input={limit_per_input}"
        )
        body = [{"category_url": cat_url} for cat_url in category_urls]

        resp = await self.client.post(url, headers=self._headers(), json=body)
        if resp.status_code != 200:
            raise BrightDataError(f"Trigger failed: {resp.status_code} {resp.text[:300]}")

        data = resp.json()
        snapshot_id = data.get("snapshot_id")
        if not snapshot_id:
            raise BrightDataError(f"No snapshot_id in response: {data}")
        return snapshot_id

    async def poll_snapshot(
        self, snapshot_id: str,
        poll_interval: int = 10,
        max_attempts: int = 30,
    ) -> list[dict]:
        """스냅샷 결과 폴링. 완료 시 JSON 배열 반환."""
        url = f"{self.base_url}/snapshot/{snapshot_id}?format=json"

        for attempt in range(max_attempts):
            await asyncio.sleep(poll_interval)
            resp = await self.client.get(url, headers=self._headers())

            if resp.status_code == 200:
                data = resp.json()
                logger.info("Snapshot %s ready: %d products", snapshot_id, len(data))
                return data

            if resp.status_code == 202:
                if attempt % 5 == 4:
                    logger.info("Snapshot %s still processing (attempt %d/%d)", snapshot_id, attempt + 1, max_attempts)
                continue

            logger.warning("Unexpected status %d for snapshot %s: %s", resp.status_code, snapshot_id, resp.text[:200])

        raise TimeoutError(f"Snapshot {snapshot_id} not ready after {max_attempts * poll_interval}s")

    async def collect_categories(
        self, category_urls: list[str], limit_per_input: int = 100,
    ) -> list[dict]:
        """trigger + poll 한번에 수행."""
        snapshot_id = await self.trigger_collection(category_urls, limit_per_input)
        logger.info("Collection triggered: snapshot_id=%s, %d categories", snapshot_id, len(category_urls))
        return await self.poll_snapshot(snapshot_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def close(self):
        await self.client.aclose()
