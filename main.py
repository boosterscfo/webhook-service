from fastapi import FastAPI

from app.router import router

app = FastAPI(title="Webhooks Service")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
