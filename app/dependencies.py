from fastapi import Header, HTTPException

from app.config import settings


async def verify_webhook_token(x_webhook_token: str = Header(...)):
    if x_webhook_token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
