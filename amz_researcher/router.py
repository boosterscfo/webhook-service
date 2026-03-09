import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Form, Request
from pydantic import BaseModel

from amz_researcher.orchestrator import run_analysis, run_keyword_analysis, run_research
from amz_researcher.services.bright_data import BrightDataService
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.product_db import ProductDBService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_help_response() -> dict:
    """상세 도움말 Block Kit 응답 생성."""
    return {
        "response_type": "ephemeral",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Amazon BSR Analyzer — 상세 가이드"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Amazon Best Sellers 카테고리별 Top 100 제품을 수집하고,\n"
                        "Gemini AI로 성분을 추출·분석하여 시장 인사이트 리포트를 생성합니다.\n\n"
                        "*전체 워크플로우:*\n"
                        "1️⃣ 카테고리 등록 (`/amz add`) → 2️⃣ 데이터 수집 (`/amz refresh`) → 3️⃣ 분석 (`/amz {키워드}`)"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📊 분석 실행*\n\n"
                        "`/amz {키워드}`\n"
                        "키워드와 매칭되는 카테고리를 검색하고, 선택하면 분석을 시작합니다.\n"
                        "• 성분 추출 (Gemini Flash) → 가중치 랭킹 → 시장 리포트 → Excel 파일 생성\n"
                        "• 결과는 Slack 메시지 + Excel 첨부로 전달됩니다.\n\n"
                        "_예시:_\n"
                        "• `/amz serum` — serum 관련 카테고리 검색\n"
                        "• `/amz sunscreen` — 자외선 차단제 카테고리 검색\n"
                        "• `/amz hair oil` — 여러 단어 키워드도 가능"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*🔍 키워드 검색 분석*\n\n"
                        "`/amz search {키워드}`\n"
                        "Amazon 검색 결과를 분석합니다. 카테고리 등록 없이 자유롭게 검색 가능.\n"
                        "7일 내 동일 키워드 재검색 시 캐시를 사용합니다.\n\n"
                        "_예시:_\n"
                        "• `/amz search vitamin c serum for face`\n"
                        "• `/amz search organic hair oil`\n"
                        "• `/amz search korean skincare set`"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📋 카테고리 관리*\n\n"
                        "`/amz list`\n"
                        "현재 등록된 모든 카테고리와 node_id를 표시합니다.\n\n"
                        "`/amz add {카테고리명} {Amazon BSR URL}`\n"
                        "새 카테고리를 등록합니다. URL은 Amazon Best Sellers 페이지 주소입니다.\n\n"
                        "_예시:_\n"
                        "• `/amz add Hair Oils https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281`\n"
                        "• `/amz add Face Moisturizers https://www.amazon.com/Best-Sellers/zgbs/beauty/11062741`\n\n"
                        "_카테고리명에 공백이 있어도 따옴표 없이 입력하세요. 마지막 인자가 URL로 인식됩니다._"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*🔄 데이터 수집*\n\n"
                        "`/amz refresh`\n"
                        "등록된 전체 카테고리의 BSR Top 100 데이터를 Bright Data로 수집합니다.\n"
                        "수집이 완료되면 webhook으로 자동 DB 적재됩니다.\n\n"
                        "`/amz refresh {키워드}`\n"
                        "특정 카테고리만 선택적으로 수집합니다.\n\n"
                        "_예시:_\n"
                        "• `/amz refresh` — 전체 카테고리 수집 (수 분 소요)\n"
                        "• `/amz refresh serum` — serum 카테고리만 수집"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📈 분석 리포트 구성*\n\n"
                        "Excel 파일에 포함되는 시트:\n"
                        "• *V4 Raw* — 수집된 원본 제품 데이터\n"
                        "• *Ingredient Rankings* — 성분별 가중치 점수 랭킹\n"
                        "• *Market Insight* — AI 시장 분석 리포트\n\n"
                        "_Score = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)_"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*💡 팁*\n\n"
                        "• 데이터는 캐시되어 재분석 시 빠르게 처리됩니다.\n"
                        "• 최신 데이터가 필요하면 `/amz refresh`로 먼저 수집하세요.\n"
                        "• 분석 완료까지 보통 1~2분 소요됩니다.\n"
                        "• `/amz` (인자 없음)으로 간단 요약을 볼 수 있습니다."
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Powered by Bright Data + Gemini Flash | `/amz` 간단 요약 | `/amz help` 상세 가이드",
                    },
                ],
            },
        ],
    }


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
    """V3 키워드 기반 분석 (향후 제거 예정)."""
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
            "text": (
                "*Amazon BSR Analyzer*\n\n"
                "`/amz {키워드}` — 분석 실행 (예: `/amz serum`)\n"
                "`/amz list` — 카테고리 목록\n"
                "`/amz refresh` — 데이터 수집\n"
                "`/amz help` — 상세 가이드"
            ),
        }

    subcommand = parts[0].lower()

    # /amz help — 상세 도움말
    if subcommand == "help":
        return _build_help_response()

    # /amz add {name} {url}
    if subcommand == "add":
        if len(parts) < 3:
            return {
                "response_type": "ephemeral",
                "text": "사용법: `/amz add {카테고리명} {Amazon Best Sellers URL}`\n예: `/amz add \"Hair Oils\" https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281`",
            }
        # URL은 마지막 파트, 나머지가 이름
        url = parts[-1]
        name = " ".join(parts[1:-1])
        if not url.startswith("http"):
            return {"response_type": "ephemeral", "text": "❌ 마지막 인자는 Amazon URL이어야 합니다."}
        product_db = ProductDBService("CFO")
        result = product_db.add_category(name, url)
        if result["ok"]:
            return {
                "response_type": "in_channel",
                "text": f"✅ 카테고리 추가 완료: *{result['name']}* (`{result['node_id']}`)\n다음 수집 시 자동 포함됩니다.",
            }
        return {"response_type": "ephemeral", "text": f"❌ 추가 실패: {result['error']}"}

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

    # /amz refresh [keyword]
    if subcommand == "refresh":
        keyword = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if keyword:
            # 특정 카테고리만 수집
            product_db = ProductDBService("CFO")
            matches = product_db.search_categories(keyword)
            if not matches:
                return {"response_type": "ephemeral", "text": f"🔍 \"{keyword}\" 관련 카테고리를 찾을 수 없습니다."}
            cat = matches[0]
            url = product_db.get_category_url(cat["node_id"])
            if not url:
                return {"response_type": "ephemeral", "text": "❌ 카테고리 URL을 찾을 수 없습니다."}
            background_tasks.add_task(_run_manual_collection, [url])
            return {"response_type": "ephemeral", "text": f"🔄 *{cat['name']}* 수집 트리거됨. 완료까지 수 분 소요."}
        # 전체 수집
        background_tasks.add_task(_run_manual_collection)
        return {"response_type": "ephemeral", "text": "🔄 전체 카테고리 수집 트리거됨. 완료까지 수 분 소요."}

    # /amz search {keyword} — V6 키워드 검색 분석
    if subcommand == "search":
        keyword_parts = parts[1:]
        keyword = " ".join(keyword_parts).strip()
        if not keyword:
            return {
                "response_type": "ephemeral",
                "text": "사용법: `/amz search {키워드}`\n예: `/amz search vitamin c serum for face`",
            }
        background_tasks.add_task(run_keyword_analysis, keyword, response_url, channel_id)
        return {
            "response_type": "in_channel",
            "text": f"🔍 키워드 *\"{keyword}\"* 검색 분석 시작... (1-3분 소요)",
        }

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


async def _run_manual_collection(urls: list[str] | None = None):
    """수동 수집 트리거 — trigger만 보내고 종료 (webhook으로 수신).

    Args:
        urls: 수집할 카테고리 URL 목록. None이면 전체 활성 카테고리.
    """
    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    product_db = ProductDBService("CFO")
    try:
        if urls is None:
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
