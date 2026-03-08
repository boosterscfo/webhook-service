import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Form, Request
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
    """수동 수집 트리거 — trigger만 보내고 종료 (webhook으로 수신)."""
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    product_db = ProductDBService("CFO")
    try:
        urls = product_db.get_all_active_category_urls()
        if not urls:
            logger.warning("No active categories to collect")
            return

        notify_url = f"{settings.WEBHOOK_BASE_URL}/webhook/brightdata"
        snapshot_id = await bright_data.trigger_collection(
            urls, notify_url=notify_url,
        )
        logger.info(
            "Collection triggered (async): snapshot_id=%s, %d categories, notify=%s",
            snapshot_id, len(urls), notify_url,
        )
    except Exception:
        logger.exception("Manual collection trigger failed")
    finally:
        await bright_data.close()


# ── Bright Data 웹훅 콜백 ────────────────────────────────

@router.post("/webhook/brightdata")
async def brightdata_webhook(
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Bright Data 수집 완료 콜백. snapshot_id를 받아 데이터를 fetch → DB 적재."""
    body = await request.json()
    snapshot_id = body.get("snapshot_id")
    status = body.get("status")

    if not snapshot_id:
        logger.warning("Bright Data webhook: no snapshot_id in body: %s", body)
        return {"status": "ignored", "reason": "no snapshot_id"}

    if status and status != "ready":
        logger.info("Bright Data webhook: snapshot %s status=%s (not ready)", snapshot_id, status)
        return {"status": "ignored", "reason": f"status={status}"}

    logger.info("Bright Data webhook: snapshot %s ready, starting ingestion", snapshot_id)
    background_tasks.add_task(_ingest_snapshot, snapshot_id)
    return {"status": "accepted", "snapshot_id": snapshot_id}


# ingestion 전체 타임아웃(초). 초과 시 태스크 취소 후 리소스 정리
INGESTION_TIMEOUT = 300  # 5분


async def _ingest_snapshot(snapshot_id: str):
    """Bright Data 스냅샷 fetch → DB 적재. 타임아웃 시 취소되어 리소스 해제."""
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    collector = DataCollector("CFO")

    async def _work() -> None:
        products = await bright_data.fetch_snapshot(snapshot_id)
        count = collector.process_snapshot(products)
        logger.info("Webhook ingestion complete: snapshot=%s, %d products", snapshot_id, count)

    try:
        await asyncio.wait_for(_work(), timeout=INGESTION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(
            "Webhook ingestion timeout (cancelled): snapshot=%s, limit=%ds",
            snapshot_id,
            INGESTION_TIMEOUT,
        )
    except asyncio.CancelledError:
        logger.warning("Webhook ingestion cancelled: snapshot=%s", snapshot_id)
    except Exception:
        logger.exception("Webhook ingestion failed: snapshot=%s", snapshot_id)
    finally:
        await bright_data.close()
