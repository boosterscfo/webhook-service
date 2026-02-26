import logging
from typing import Optional

from slack_sdk import WebClient

from app.config import settings

logger = logging.getLogger(__name__)


class SlackNotifier:
    @staticmethod
    def _get_token(bot_name: str) -> str:
        return getattr(settings, f"{bot_name.upper()}_BOT_TOKEN")

    @staticmethod
    def send(
        text: str,
        blocks: list,
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
        bot_name: str = "BOOSTA",
    ) -> dict:
        client = WebClient(token=SlackNotifier._get_token(bot_name))

        try:
            if user_id is not None:
                response = client.conversations_open(users=user_id)
                channel_id = response["channel"]["id"]

            if channel_id is not None:
                result = client.chat_postMessage(
                    text=text, blocks=blocks, channel=channel_id
                )
                return result
        except Exception:
            logger.exception("Slack API error (bot=%s, channel=%s, user=%s)", bot_name, channel_id, user_id)
            raise

        return {"text": "No channel or user specified"}

    @staticmethod
    def notify(
        text: str,
        header: str,
        body: Optional[str] = None,
        footer: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        url_button: Optional[dict] = None,
        bot_name: str = "BOOSTA",
    ) -> dict:
        """Send a structured Slack notification with header, body, footer, and optional URL button.

        When both user_id and channel_id are provided, user_id takes priority (DM first policy).
        """
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        ]
        divider = {"type": "divider"}

        if body:
            blocks.append(divider)
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": body}}
            )

        if footer:
            blocks.append(divider)
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": footer}}
            )

        if url_button:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": url_button.get("text", "Click"),
                                "emoji": url_button.get("emoji", True),
                            },
                            "value": "click_to_link",
                            "url": url_button.get("url", ""),
                        }
                    ],
                }
            )

        if user_id is not None:
            return SlackNotifier.send(text, blocks, user_id=user_id, bot_name=bot_name)
        elif channel_id is not None:
            return SlackNotifier.send(
                text, blocks, channel_id=channel_id, bot_name=bot_name
            )

        return {"text": "No channel or user specified"}

    @staticmethod
    def find_slackid(email: str) -> Optional[str]:
        from lib.mysql_connector import MysqlConnector

        try:
            with MysqlConnector("BOOSTA") as conn:
                query = (
                    "SELECT slack_id FROM admin.flex_users "
                    "WHERE slack_id IS NOT NULL AND slack_id != '' "
                    "AND email = %s"
                )
                df = conn.read_query_table(query, (email,))
        except Exception:
            logger.exception("Failed to look up Slack ID for email=%s", email)
            return None

        if df.empty:
            logger.debug("No Slack ID found for email=%s", email)
            return None
        return df["slack_id"].iloc[0]
