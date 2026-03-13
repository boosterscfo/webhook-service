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
        blocks: list[dict] | None = None,
    ):
        """Send a message. text is required (fallback for notifications). blocks is optional Block Kit."""
        payload: dict = {
            "response_type": "ephemeral" if ephemeral else "in_channel",
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks

        if response_url:
            try:
                resp = await self.client.post(response_url, json=payload)
                resp.raise_for_status()
                return
            except Exception:
                logger.warning("response_url failed, falling back to chat.postMessage")

        if channel_id and self.bot_token:
            try:
                body: dict = {"channel": channel_id, "text": text}
                if blocks:
                    body["blocks"] = blocks
                resp = await self.client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
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

    async def send_with_thread(
        self,
        channel_id: str,
        main_text: str,
        thread_text: str,
        main_blocks: list[dict] | None = None,
        thread_blocks: list[dict] | None = None,
        thread_attachments: list[dict] | None = None,
    ) -> None:
        """본문 메시지 전송 후, 같은 thread에 상세 메시지 전송."""
        if not channel_id or not self.bot_token:
            logger.warning("No channel_id or bot_token for thread message")
            return

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        try:
            # 1. 본문 전송
            main_body: dict = {"channel": channel_id, "text": main_text}
            if main_blocks:
                main_body["blocks"] = main_blocks
            resp = await self.client.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json=main_body,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Main message failed: %s", data.get("error"))
                return

            thread_ts = data.get("ts")
            if not thread_ts:
                logger.error("No ts in main message response")
                return

            # 2. Thread에 상세 전송
            thread_body: dict = {
                "channel": channel_id,
                "text": thread_text,
                "thread_ts": thread_ts,
            }
            if thread_blocks:
                thread_body["blocks"] = thread_blocks
            if thread_attachments:
                thread_body["attachments"] = thread_attachments
            resp = await self.client.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json=thread_body,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Thread message failed: %s", data.get("error"))
        except Exception:
            logger.exception("Failed to send message with thread")

    async def close(self):
        await self.client.aclose()
