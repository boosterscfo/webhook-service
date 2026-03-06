import logging

from fastapi import APIRouter, BackgroundTasks, Form
from pydantic import BaseModel

from amz_researcher.orchestrator import run_research

logger = logging.getLogger(__name__)
router = APIRouter()


class ResearchRequest(BaseModel):
    keyword: str
    response_url: str = ""
    channel_id: str = ""
    max_products: int = 30


@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    parts = text.strip().rsplit(maxsplit=1)
    max_products = 30
    if len(parts) == 2 and parts[1].isdigit():
        keyword = parts[0]
        max_products = min(int(parts[1]), 100)
    else:
        keyword = text.strip()

    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz {키워드} [개수] (예: /amz hair serum 50)",
        }

    background_tasks.add_task(
        run_research, keyword, response_url, channel_id, max_products,
    )
    return {
        "response_type": "in_channel",
        "text": (
            f"🔍 *{keyword}* 검색 시작합니다 (상위 {max_products}개). "
            f"약 10~15분 소요됩니다."
        ),
    }


@router.post("/research")
async def research_test(
    background_tasks: BackgroundTasks,
    req: ResearchRequest,
):
    keyword = req.keyword.strip()
    if not keyword:
        return {"error": "keyword is required"}

    background_tasks.add_task(
        run_research, keyword, req.response_url, req.channel_id, req.max_products,
    )
    return {"status": "started", "keyword": keyword, "max_products": req.max_products}
