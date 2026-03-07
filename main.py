import logging

from fastapi import FastAPI

from app.router import router
from amz_researcher.router import router as amz_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = FastAPI(title="Webhooks Service")
app.include_router(router)
app.include_router(amz_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
