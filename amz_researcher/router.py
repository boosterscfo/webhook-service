import json
import logging

from fastapi import APIRouter, BackgroundTasks, Form
from pydantic import BaseModel

from amz_researcher.orchestrator import run_analysis, run_research
from amz_researcher.services.bright_data import BrightDataService
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.product_db import ProductDBService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class ResearchRequest(BaseModel):
    keyword: str
    response_url: str = ""
    channel_id: str = ""
    refresh: bool = False


# ── V3 (하위 호환, 향후 제거) ────────────────────────────

@router.post("/slack/amz/legacy")
async def slack_amz_legacy(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    """V3 Browse.ai 기반 (향후 제거 예정)."""
    parts = text.strip().split()
    if not parts:
        return {"response_type": "ephemeral", "text": "사용법: /amz prod {키워드}"}

    subcommand = parts[0].lower()
    if subcommand != "prod":
        return {"response_type": "ephemeral", "text": f"알 수 없는 명령: {subcommand}"}

    refresh = "--refresh" in parts
    keyword_parts = [p for p in parts[1:] if p != "--refresh"]
    keyword = " ".join(keyword_parts).strip()
    if not keyword:
        return {"response_type": "ephemeral", "text": "사용법: /amz prod {키워드} [--refresh]"}

    background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh)
    return {"response_type": "in_channel", "text": f"🔍 *{keyword}* 분석 시작. 약 10~15분 소요됩니다."}


# ── V4: 카테고리 기반 분석 ────────────────────────────────

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
            "text": "사용법:\n• `/amz {키워드}` — 카테고리 검색 → 분석\n• `/amz list` — 카테고리 목록\n• `/amz refresh` — 수동 데이터 수집",
        }

    subcommand = parts[0].lower()

    # /amz list
    if subcommand == "list":
        product_db = ProductDBService("CFO")
        categories = product_db.list_categories()
        if not categories:
            return {"response_type": "ephemeral", "text": "등록된 카테고리가 없습니다."}
        lines = [f"• {c['name']} (`{c['node_id']}`)" for c in categories]
        return {
            "response_type": "ephemeral",
            "text": f"📋 등록된 카테고리 ({len(categories)}개):\n" + "\n".join(lines),
        }

    # /amz refresh
    if subcommand == "refresh":
        background_tasks.add_task(_run_manual_collection)
        return {"response_type": "ephemeral", "text": "🔄 수동 수집 트리거됨. 완료까지 수 분 소요."}

    # /amz prod {keyword} — V3 하위 호환
    if subcommand == "prod":
        keyword_parts = [p for p in parts[1:] if p != "--refresh"]
        keyword = " ".join(keyword_parts).strip()
        if not keyword:
            return {"response_type": "ephemeral", "text": "사용법: /amz prod {키워드}"}
        refresh = "--refresh" in parts
        background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh)
        return {"response_type": "in_channel", "text": f"🔍 *{keyword}* 분석 시작 (V3). 약 10~15분 소요됩니다."}

    # /amz {keyword} — V4 카테고리 검색 → 버튼
    keyword = " ".join(parts)
    product_db = ProductDBService("CFO")
    matches = product_db.search_categories(keyword)

    if not matches:
        return {
            "response_type": "ephemeral",
            "text": f"🔍 \"{keyword}\" 관련 카테고리를 찾을 수 없습니다.\n`/amz list`로 전체 목록을 확인하세요.",
        }

    # Block Kit 버튼으로 카테고리 제시
    buttons = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": m["name"]},
            "action_id": f"amz_category_{m['node_id']}",
            "value": json.dumps({
                "node_id": m["node_id"],
                "name": m["name"],
                "response_url": response_url,
                "channel_id": channel_id,
            }),
        }
        for m in matches[:5]
    ]
    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"🔍 *\"{keyword}\"* 관련 카테고리:"},
            },
            {"type": "actions", "elements": buttons},
        ],
    }


@router.post("/slack/amz/interact")
async def slack_amz_interact(
    background_tasks: BackgroundTasks,
    payload: str = Form(""),
):
    """Slack Block Kit 버튼 클릭 콜백."""
    data = json.loads(payload)
    actions = data.get("actions", [])
    if not actions:
        return {"text": "No action received"}

    action = actions[0]
    value = json.loads(action["value"])
    node_id = value["node_id"]
    name = value["name"]
    response_url = value["response_url"]
    channel_id = value["channel_id"]

    background_tasks.add_task(run_analysis, node_id, name, response_url, channel_id)
    return {
        "response_type": "in_channel",
        "text": f"📊 *{name}* BSR Top 100 분석 시작... (수초~1분 소요)",
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


async def _run_manual_collection():
    """수동 수집 트리거 (Slack /amz refresh용)."""
    from amz_researcher.jobs.collect import run_collection
    await run_collection()
