import logging

import httpx

logger = logging.getLogger(__name__)


class SlackSender:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_message(self, response_url: str, text: str):
        if not response_url:
            logger.warning("No response_url, skipping message: %s", text[:80])
            return
        try:
            resp = await self.client.post(response_url, json={
                "response_type": "in_channel",
                "text": text,
            })
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to send Slack message via response_url")

    async def upload_file(
        self, channel_id: str, file_bytes: bytes,
        filename: str, comment: str = "",
    ):
        if not channel_id or not self.bot_token:
            logger.warning("No channel_id or bot_token, skipping file upload")
            return
        try:
            resp = await self.client.post(
                "https://slack.com/api/files.upload",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                data={
                    "channels": channel_id,
                    "initial_comment": comment,
                },
                files={"file": (filename, file_bytes)},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack file upload failed: %s", data.get("error"))
        except Exception:
            logger.exception("Failed to upload file to Slack")

    async def close(self):
        await self.client.aclose()
