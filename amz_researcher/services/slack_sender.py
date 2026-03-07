import logging

import httpx

logger = logging.getLogger(__name__)


class SlackSender:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_message(
        self, response_url: str, text: str, ephemeral: bool = False,
        channel_id: str = "",
    ):
        if response_url:
            try:
                resp = await self.client.post(response_url, json={
                    "response_type": "ephemeral" if ephemeral else "in_channel",
                    "text": text,
                })
                resp.raise_for_status()
                return
            except Exception:
                logger.exception("Failed to send Slack message via response_url")
                return

        if channel_id and self.bot_token:
            try:
                resp = await self.client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={"channel": channel_id, "text": text},
                )
                resp.raise_for_status()
                return
            except Exception:
                logger.exception("Failed to send Slack message via chat.postMessage")
                return

        logger.warning("No response_url or channel_id, skipping message: %s", text[:80])

    async def upload_file(
        self, channel_id: str, file_bytes: bytes,
        filename: str, comment: str = "",
    ):
        if not channel_id or not self.bot_token:
            logger.warning("No channel_id or bot_token, skipping file upload")
            return
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        try:
            # Step 1: Get upload URL
            resp = await self.client.post(
                "https://slack.com/api/files.getUploadURLExternal",
                headers=headers,
                data={"filename": filename, "length": str(len(file_bytes))},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack getUploadURL failed: %s", data.get("error"))
                return
            upload_url = data["upload_url"]
            file_id = data["file_id"]

            # Step 2: Upload file content
            await self.client.post(
                upload_url,
                files={"file": (filename, file_bytes)},
            )

            # Step 3: Complete upload and share to channel
            resp = await self.client.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "files": [{"id": file_id, "title": filename}],
                    "channel_id": channel_id,
                    "initial_comment": comment,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack completeUpload failed: %s", data.get("error"))
        except Exception:
            logger.exception("Failed to upload file to Slack")

    async def send_dm(self, user_id: str, text: str):
        if not user_id or not self.bot_token:
            return
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        try:
            resp = await self.client.post(
                "https://slack.com/api/conversations.open",
                headers={**headers, "Content-Type": "application/json"},
                json={"users": user_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack conversations.open failed: %s", data.get("error"))
                return
            dm_channel = data["channel"]["id"]

            resp = await self.client.post(
                "https://slack.com/api/chat.postMessage",
                headers={**headers, "Content-Type": "application/json"},
                json={"channel": dm_channel, "text": text},
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to send DM to %s", user_id)

    async def close(self):
        await self.client.aclose()
