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
    max_products: int = 100


@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    keyword = text.strip()
    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz {키워드} (예: /amz hair serum)",
        }

    background_tasks.add_task(run_research, keyword, response_url, channel_id)
    return {
        "response_type": "in_channel",
        "text": f"🔍 *{keyword}* 검색 시작합니다 (상위 100개). 약 10~15분 소요됩니다.",
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
        run_research, keyword, req.response_url, req.channel_id,
    )
    return {"status": "started", "keyword": keyword}
