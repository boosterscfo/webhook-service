import hashlib
import hmac
import time
from typing import Optional

from fastapi import Header, HTTPException, Request

from app.config import settings

TIMESTAMP_TOLERANCE = 300  # 5 minutes


async def verify_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
    x_webhook_token: Optional[str] = Header(None),
):
    # Mode 1: HMAC-SHA256 signature verification
    if x_webhook_signature and x_webhook_timestamp:
        if not settings.WEBHOOK_SECRET:
            raise HTTPException(
                status_code=500, detail="WEBHOOK_SECRET not configured"
            )

        try:
            ts = int(x_webhook_timestamp)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid timestamp")

        if abs(time.time() - ts) > TIMESTAMP_TOLERANCE:
            raise HTTPException(status_code=401, detail="Request expired")

        body = await request.body()

        sig_basestring = f"{x_webhook_timestamp}.{body.decode('utf-8')}"
        expected = hmac.new(
            settings.WEBHOOK_SECRET.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        received = x_webhook_signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, received):
            raise HTTPException(status_code=401, detail="Invalid signature")

        return

    # Mode 2: Legacy static token
    if x_webhook_token:
        if x_webhook_token != settings.WEBHOOK_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid webhook token")
        return

    raise HTTPException(status_code=401, detail="Authentication required")
