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
    refresh: bool = False


@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    parts = text.strip().split()
    if not parts:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz prod {키워드} (예: /amz prod hair serum)",
        }

    subcommand = parts[0].lower()
    if subcommand != "prod":
        return {
            "response_type": "ephemeral",
            "text": f"알 수 없는 명령: {subcommand}\n사용법: /amz prod {{키워드}}",
        }

    refresh = "--refresh" in parts
    keyword_parts = [p for p in parts[1:] if p != "--refresh"]
    keyword = " ".join(keyword_parts).strip()
    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz prod {키워드} [--refresh]",
        }

    background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh)
    cache_msg = " (캐시 무시)" if refresh else ""
    return {
        "response_type": "in_channel",
        "text": f"🔍 *{keyword}* 분석 시작{cache_msg}. 약 10~15분 소요됩니다.",
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
        run_research, keyword, req.response_url, req.channel_id, req.refresh,
    )
    return {"status": "started", "keyword": keyword, "refresh": req.refresh}
