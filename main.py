import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.router import router
from amz_researcher.router import router as amz_router
from amz_researcher.services.report_store import ReportStore
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: cleanup expired reports
    store = ReportStore(base_dir=settings.REPORT_DIR, ttl_days=settings.REPORT_TTL_DAYS)
    deleted = store.cleanup_expired()
    if deleted:
        logging.getLogger(__name__).info("Startup: cleaned up %d expired reports", deleted)
    yield


app = FastAPI(title="Webhooks Service", lifespan=lifespan)
app.include_router(router)
app.include_router(amz_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
