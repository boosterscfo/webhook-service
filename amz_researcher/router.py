import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from amz_researcher.orchestrator import (
    run_analysis,
    run_keyword_analysis,
    run_research,
    _run_keyword_analysis_pipeline,
    _category_collection_callbacks,
    _trigger_category_collection,
)
from amz_researcher.services.bright_data import BrightDataService
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.ingredient_analyzer import analyze_voice_ingredient_correlation
from amz_researcher.services.product_db import ProductDBService
from amz_researcher.services.report_store import ReportStore
from amz_researcher.services.slack_sender import SlackSender
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_report_store = ReportStore(
    base_dir=settings.REPORT_DIR,
    ttl_days=settings.REPORT_TTL_DAYS,
)


@router.get("/reports/{report_id}")
async def serve_report(report_id: str):
    """Serve a stored HTML report by its ID."""
    path = _report_store.get_path(report_id)
    if path is None:
        return HTMLResponse("<h1>리포트를 찾을 수 없습니다</h1><p>만료되었거나 존재하지 않는 리포트입니다.</p>", status_code=404)
    return FileResponse(path, media_type="text/html")


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
                        "1️⃣ 카테고리 검색 → 2️⃣ 새로 수집 / 캐시 선택 → 3️⃣ 분석 & 리포트 생성"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📊 카테고리 BSR 분석*\n\n"
                        "`/amz {키워드}`\n"
                        "키워드로 카테고리를 검색하고, 선택하면 데이터 옵션이 표시됩니다.\n"
                        "• *새로 수집 후 분석* — Bright Data로 최신 데이터를 수집 후 분석\n"
                        "• *캐시 사용 (X일 전)* — 기존 수집 데이터로 즉시 분석\n"
                        "• 미수집 카테고리는 자동으로 수집이 시작됩니다.\n\n"
                        "_예시:_\n"
                        "• `/amz serum` → 카테고리 선택 → 수집 옵션 선택\n"
                        "• `/amz sunscreen` • `/amz hair oil`"
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
                        "Amazon 검색 결과를 직접 분석합니다. 카테고리 등록 없이 자유 검색.\n"
                        "유사 키워드 캐시가 있으면 기존 데이터 사용 / 새로 수집 선택이 가능합니다.\n\n"
                        "_예시:_\n"
                        "• `/amz search vitamin c serum for face`\n"
                        "• `/amz search organic hair oil`"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📋 관리 명령어*\n\n"
                        "`/amz list` — 활성 카테고리 목록"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*📄 리포트 재생성*\n\n"
                        "`/amz report {카테고리명}` — 캐시 데이터로 리포트만 재빌드\n"
                        "`/amz report-search {키워드}` — 키워드 리포트 재빌드\n\n"
                        "_리포트 템플릿 변경 후 빠르게 결과를 확인할 때 유용합니다._"
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
                        "• 카테고리 선택 시 데이터 나이와 수집 옵션이 표시됩니다.\n"
                        "• 30일 이상된 데이터는 새로 수집이 권장됩니다.\n"
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
                        "text": "Powered by Bright Data + Gemini | `/amz` 간단 요약 | `/amz help` 상세 가이드",
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
    parts = text.strip().replace("*", "").replace("~", "").replace("`", "").split()
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

    background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh, user_id)
    return {"response_type": "ephemeral", "text": f"🔍 *{keyword}* 분석 시작. 완료 시 채널에 결과가 공유됩니다."}


# ── V4: 카테고리 기반 분석 ────────────────────────────────

@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    # Slack 볼드/이탤릭/취소선/코드 마크다운 제거 (*bold*, _italic_, ~strike~, `code`)
    clean_text = text.strip().replace("*", "").replace("~", "").replace("`", "")
    parts = clean_text.split()
    if not parts:
        return {
            "response_type": "ephemeral",
            "text": (
                "*Amazon BSR Analyzer*\n\n"
                "`/amz {키워드}` — 카테고리 분석 (예: `/amz serum`)\n"
                "`/amz search {키워드}` — 키워드 검색 분석 (예: `/amz search vitamin c serum`)\n"
                "`/amz why` — Voice(-) 성분 상관관계 분석\n"
                "`/amz report {카테고리}` — 리포트만 재생성 (캐시 사용)\n"
                "`/amz report-search {키워드}` — 키워드 리포트만 재생성\n"
                "`/amz list` — 카테고리 목록\n"
                "`/amz help` — 상세 가이드"
            ),
        }

    subcommand = parts[0].lower()

    # /amz help — 상세 도움말
    if subcommand == "help":
        return _build_help_response()

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

    # /amz why — Voice(-) 성분 상관관계 분석
    if subcommand == "why":
        keyword = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if not keyword:
            background_tasks.add_task(
                _handle_why_discovery, response_url, channel_id,
            )
            return {"response_type": "ephemeral", "text": "🔬 Voice(-) 키워드 목록 로딩 중..."}
        else:
            background_tasks.add_task(
                _handle_why_analysis, keyword, response_url, channel_id,
            )
            return {"response_type": "ephemeral", "text": f"🔬 *{keyword}* 성분 상관관계 분석 중..."}

    # /amz report {category} — 캐시 기반 리포트만 재생성 (Gemini 호출 없음)
    if subcommand == "report":
        keyword = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if not keyword:
            return {
                "response_type": "ephemeral",
                "text": "사용법: `/amz report {카테고리명}`\n예: `/amz report Hair Styling Serums`",
            }
        product_db = ProductDBService("CFO")
        matches = product_db.search_categories(keyword)
        if not matches:
            return {"response_type": "ephemeral", "text": f"🔍 \"{keyword}\" 관련 카테고리를 찾을 수 없습니다."}
        cat = matches[0]
        background_tasks.add_task(
            run_analysis, cat["node_id"], cat["name"],
            response_url, channel_id, user_id, report_only=True,
        )
        return {
            "response_type": "ephemeral",
            "text": f"🔄 *{cat['name']}* 리포트 재생성 중... (Gemini 호출 없음, 캐시 사용)",
        }

    # /amz report-search {keyword} — 키워드 분석 리포트만 재생성
    if subcommand == "report-search":
        keyword = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        if not keyword:
            return {
                "response_type": "ephemeral",
                "text": "사용법: `/amz report-search {키워드}`\n예: `/amz report-search retinol serum`",
            }
        product_db = ProductDBService("CFO")
        normalized = " ".join(keyword.lower().split())
        cached = product_db.get_keyword_cache(normalized)
        if not cached or cached.get("status") != "completed":
            return {
                "response_type": "ephemeral",
                "text": f"⚠️ *\"{keyword}\"* 수집 완료된 데이터가 없습니다. `/amz search {keyword}`로 먼저 분석하세요.",
            }
        keyword_products = product_db.get_keyword_products(normalized, cached["searched_at"])
        if not keyword_products:
            return {"response_type": "ephemeral", "text": f"⚠️ *\"{keyword}\"* 제품 데이터가 없습니다."}
        background_tasks.add_task(
            _run_keyword_analysis_pipeline, keyword, keyword_products,
            response_url, channel_id, user_id, report_only=True,
        )
        return {
            "response_type": "ephemeral",
            "text": f"🔄 *\"{keyword}\"* 키워드 리포트 재생성 중... (Gemini 호출 없음, 캐시 사용)",
        }

    # /amz search {keyword} — V6 키워드 검색 분석
    if subcommand == "search":
        keyword_parts = parts[1:]
        keyword = " ".join(keyword_parts).strip()
        if not keyword:
            return {
                "response_type": "ephemeral",
                "text": "사용법: `/amz search {키워드}`\n예: `/amz search vitamin c serum for face`",
            }

        # 정확한 캐시가 있으면 바로 분석 시작
        product_db = ProductDBService("CFO")
        exact_cache = product_db.get_keyword_cache(keyword)
        if exact_cache and exact_cache.get("status") == "completed":
            background_tasks.add_task(run_keyword_analysis, keyword, response_url, channel_id, user_id)
            return {
                "response_type": "ephemeral",
                "text": f"🔍 키워드 *\"{keyword}\"* 검색 분석 시작... 완료 시 채널에 결과가 공유됩니다.",
            }

        # 정확한 캐시 없음 → 유사 키워드 추천
        similar = product_db.find_similar_keywords(keyword)
        if similar:
            from datetime import datetime

            buttons = []
            for s in similar[:4]:
                days_ago = (datetime.now() - s["searched_at"]).days
                btn_text = f"{s['keyword']} ({s['product_count']}개, {days_ago}일 전)"
                buttons.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": btn_text[:75]},
                    "action_id": f"amz_keyword_existing_{hash(s['keyword']) % 100000}",
                    "value": json.dumps({
                        "keyword": s["keyword"],
                        "response_url": response_url,
                        "channel_id": channel_id,
                    }),
                })
            # 새로 수집 버튼
            buttons.append({
                "type": "button",
                "text": {"type": "plain_text", "text": f"🆕 \"{keyword}\" 새로 수집"},
                "action_id": "amz_keyword_new",
                "value": json.dumps({
                    "keyword": keyword,
                    "response_url": response_url,
                    "channel_id": channel_id,
                }),
                "style": "primary",
            })
            return {
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":mag: *\"{keyword}\"*와 유사한 기존 분석 결과가 있습니다.\n기존 데이터로 리포트를 생성하거나, 새로 수집할 수 있습니다.",
                        },
                    },
                    {"type": "actions", "elements": buttons},
                ],
            }

        # 유사 키워드도 없음 → 바로 수집 시작
        background_tasks.add_task(run_keyword_analysis, keyword, response_url, channel_id, user_id)
        return {
            "response_type": "ephemeral",
            "text": f"🔍 키워드 *\"{keyword}\"* 검색 분석 시작... 완료 시 채널에 결과가 공유됩니다.",
        }

    # /amz prod {keyword} — V3 하위 호환
    if subcommand == "prod":
        keyword_parts = [p for p in parts[1:] if p != "--refresh"]
        keyword = " ".join(keyword_parts).strip()
        if not keyword:
            return {"response_type": "ephemeral", "text": "사용법: /amz prod {키워드}"}
        refresh = "--refresh" in parts
        background_tasks.add_task(run_research, keyword, response_url, channel_id, refresh, user_id)
        return {"response_type": "ephemeral", "text": f"🔍 *{keyword}* 분석 시작 (V3). 완료 시 채널에 결과가 공유됩니다."}

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
            "text": {"type": "plain_text", "text": f"{m['name']} [NEW]" if not m.get("is_active") else m["name"]},
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
    action_id = action.get("action_id", "")
    value = json.loads(action["value"])
    user_id = (data.get("user") or {}).get("id", "")

    # Voice-Ingredient 상관관계 분석
    if action_id.startswith("amz_why_"):
        kw = value["keyword"]
        resp_url = value["response_url"]
        ch_id = value["channel_id"]
        background_tasks.add_task(_handle_why_analysis, kw, resp_url, ch_id)
        return {"response_type": "ephemeral", "text": f"🔬 *{kw}* 분석 시작..."}

    # 키워드 검색: 기존 데이터로 리포트 생성
    if action_id.startswith("amz_keyword_existing_"):
        kw = value["keyword"]
        response_url = value["response_url"]
        channel_id = value["channel_id"]
        background_tasks.add_task(run_keyword_analysis, kw, response_url, channel_id, user_id)
        return {
            "response_type": "ephemeral",
            "text": f"🔍 기존 데이터 *\"{kw}\"* 로 분석 시작... 완료 시 채널에 결과가 공유됩니다.",
        }

    # 키워드 검색: 새로 수집
    if action_id == "amz_keyword_new":
        kw = value["keyword"]
        response_url = value["response_url"]
        channel_id = value["channel_id"]
        background_tasks.add_task(run_keyword_analysis, kw, response_url, channel_id, user_id)
        return {
            "response_type": "ephemeral",
            "text": f"🔍 키워드 *\"{kw}\"* 새로 수집 시작... 완료 시 채널에 결과가 공유됩니다.",
        }

    # 카테고리: 새로 수집 후 분석
    if action_id == "amz_cat_refresh":
        node_id = value["node_id"]
        name = value["name"]
        response_url = value["response_url"]
        channel_id = value["channel_id"]
        background_tasks.add_task(
            _trigger_category_collection, node_id, name,
            response_url, channel_id, user_id,
        )
        return {
            "response_type": "ephemeral",
            "text": f"📡 *{name}* 새로 수집 시작... 완료 시 자동으로 분석 결과를 보내드립니다.",
        }

    # 카테고리: 캐시 사용 분석
    if action_id == "amz_cat_cached":
        node_id = value["node_id"]
        name = value["name"]
        response_url = value["response_url"]
        channel_id = value["channel_id"]
        background_tasks.add_task(
            run_analysis, node_id, name, response_url, channel_id, user_id,
        )
        return {
            "response_type": "ephemeral",
            "text": f"📊 *{name}* 기존 데이터로 분석 시작... 완료 시 채널에 결과가 공유됩니다.",
        }

    # 카테고리 BSR 분석 — freshness 확인 후 선택지 제시
    node_id = value.get("node_id")
    name = value.get("name")
    response_url = value["response_url"]
    channel_id = value["channel_id"]

    logger.info("Category interact: node_id=%s, name=%s, action_id=%s", node_id, name, action_id)

    product_db = ProductDBService("CFO")
    freshness = product_db.get_category_freshness(node_id)
    logger.info("Category freshness: node_id=%s, result=%s", node_id, freshness)

    if freshness is None:
        # 미수집 카테고리 → 바로 수집 트리거
        background_tasks.add_task(
            _trigger_category_collection, node_id, name,
            response_url, channel_id, user_id,
        )
        return {
            "response_type": "ephemeral",
            "text": f"📡 *{name}* 데이터가 없습니다. 수집을 시작합니다...",
        }

    # 캐시 있음 → response_url로 선택지 전송
    background_tasks.add_task(
        _send_category_options, node_id, name, freshness,
        response_url, channel_id,
    )
    return {"text": f":mag: *{name}* 데이터 확인 중..."}


async def _send_category_options(
    node_id: str,
    name: str,
    freshness: dict,
    response_url: str,
    channel_id: str,
) -> None:
    """카테고리 freshness 기반 선택지를 response_url로 전송."""
    from datetime import datetime

    collected_at = freshness["collected_at"]
    product_count = freshness["product_count"]
    days_ago = (datetime.now() - collected_at).days
    age_text = "오늘" if days_ago == 0 else f"{days_ago}일 전"

    payload = json.dumps({
        "node_id": node_id,
        "name": name,
        "response_url": response_url,
        "channel_id": channel_id,
    })

    is_stale = days_ago >= 30
    refresh_btn = {
        "type": "button",
        "text": {"type": "plain_text", "text": "새로 수집 후 분석"},
        "action_id": "amz_cat_refresh",
        "value": payload,
    }
    cached_btn = {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": f"캐시 사용 ({age_text})",
        },
        "action_id": "amz_cat_cached",
        "value": payload,
    }
    if is_stale:
        refresh_btn["style"] = "primary"
        buttons = [refresh_btn, cached_btn]
    else:
        cached_btn["style"] = "primary"
        buttons = [cached_btn, refresh_btn]

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":mag: *{name}*\n"
                    f"현재 데이터: {product_count}개 제품, {age_text} 수집"
                ),
            },
        },
        {
            "type": "actions",
            "elements": buttons,
        },
    ]

    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    try:
        await slack.send_message(
            response_url,
            f":mag: *{name}* — {product_count}개 제품, {age_text} 수집",
            ephemeral=True,
            channel_id=channel_id,
            blocks=blocks,
        )
    except Exception:
        logger.exception("Failed to send category options for %s", name)
    finally:
        await slack.close()


# ── Voice-Ingredient Correlation Handlers ─────────────


async def _handle_why_discovery(response_url: str, channel_id: str) -> None:
    """Voice - 키워드 빈도 Top 15를 Block Kit 버튼으로 표시."""
    db = ProductDBService("CFO")
    stats = db.get_voice_keyword_stats()
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    try:
        if not stats:
            await slack.send_message(
                response_url,
                "Voice(-) 데이터가 없습니다. `/amz {카테고리}`로 리포트를 먼저 실행하세요.",
                ephemeral=True, channel_id=channel_id,
            )
            return

        buttons = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": f"{s['keyword']} ({s['count']})"},
                "action_id": f"amz_why_{s['keyword'].replace(' ', '_')}",
                "value": json.dumps({
                    "keyword": s["keyword"],
                    "response_url": response_url,
                    "channel_id": channel_id,
                }),
            }
            for s in stats
        ]

        # Block Kit 버튼은 actions 블록당 최대 5개
        action_blocks = []
        for i in range(0, len(buttons), 5):
            action_blocks.append({"type": "actions", "elements": buttons[i:i + 5]})

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Voice(-) 키워드 분석"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "분석할 키워드를 선택하세요.\n또는 `/amz why {keyword}` 로 직접 검색",
                },
            },
            *action_blocks,
        ]

        await slack.send_message(
            response_url, "Voice(-) 키워드 목록",
            ephemeral=True, channel_id=channel_id, blocks=blocks,
        )
    except Exception:
        logger.exception("Why discovery failed")
    finally:
        await slack.close()


async def _handle_why_analysis(
    keyword: str, response_url: str, channel_id: str,
) -> None:
    """키워드별 성분 상관관계 분석 -> ODM 브리프 가이드 반환."""
    db = ProductDBService("CFO")
    cache = AmzCacheService()
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    try:
        # 1. 캐시 확인
        cached = cache.get_correlation_cache(keyword)
        if cached:
            logger.info("Correlation cache hit: %s", keyword)
            await _send_why_result(slack, channel_id, cached)
            return

        # 2. 데이터 조회 + 분석
        products = db.get_all_products_with_voice()
        if not products:
            await slack.send_message(
                response_url,
                "분석 가능한 제품이 없습니다. 리포트를 먼저 실행하세요.",
                ephemeral=True, channel_id=channel_id,
            )
            return

        result = analyze_voice_ingredient_correlation(products, keyword)

        # 3. 결과 없음 -> 유사 키워드 제안
        if not result.get("enriched"):
            similar = db.find_similar_voice_keywords(keyword)
            if similar:
                buttons = [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": kw},
                        "action_id": f"amz_why_{kw.replace(' ', '_')}",
                        "value": json.dumps({
                            "keyword": kw,
                            "response_url": response_url,
                            "channel_id": channel_id,
                        }),
                    }
                    for kw in similar
                ]
                error_msg = result.get("error", f"'{keyword}' 결과 없음")
                blocks = [
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ {error_msg}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": "유사 키워드:"}},
                    {"type": "actions", "elements": buttons},
                ]
                await slack.send_message(
                    response_url, error_msg,
                    ephemeral=True, channel_id=channel_id, blocks=blocks,
                )
            else:
                await slack.send_message(
                    response_url,
                    f"⚠️ '{keyword}' 관련 데이터가 부족합니다.",
                    ephemeral=True, channel_id=channel_id,
                )
            return

        # 4. Gemini ODM 브리프 생성
        gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
        try:
            brief = await gemini.generate_odm_brief(
                keyword=keyword,
                enriched=result["enriched"],
                safe=result["safe"],
                stats={
                    "total_products": result["total_products"],
                    "with_count": result["with_count"],
                    "categories_analyzed": result["categories_analyzed"],
                },
            )
        finally:
            await gemini.close()

        # 5. 캐시 저장
        full_result = {**result, "brief": brief}
        cache.save_correlation_cache(keyword, full_result)

        # 6. 메시지 전송
        await _send_why_result(slack, channel_id, full_result)

    except Exception:
        logger.exception("Why analysis failed for '%s'", keyword)
        await slack.send_message(
            response_url,
            f"⚠️ '{keyword}' 분석 중 오류가 발생했습니다.",
            ephemeral=True, channel_id=channel_id,
        )
    finally:
        await slack.close()


async def _send_why_result(
    slack: SlackSender, channel_id: str, result: dict,
) -> None:
    """분석 결과를 본문(브리프 가이드) + thread(성분 상세)로 전송."""
    keyword = result["keyword"]
    brief = result.get("brief", {})

    # 본문: ODM 브리프 가이드
    main_text = (
        f"🔬 *\"{keyword}\" — ODM 브리프 가이드*\n"
        f"{result.get('categories_analyzed', 0)}개 카테고리, "
        f"{result.get('total_products', 0)}개 제품 분석 "
        f"({result.get('with_count', 0)}개에서 \"{keyword}\" 발견)\n\n"
        f"💡 *핵심*: {brief.get('cause', '-')}\n"
        f"📋 *브리프 제안*: \"{brief.get('brief', '-')}\"\n"
        f"⚠️ *피할 패턴*: {brief.get('avoid', '-')}\n"
        f"✅ *안전 조합*: {brief.get('safe_combo', '-')}\n\n"
        f"_🧵 성분 상세 분석은 thread 참조_"
    )

    # Thread: 성분 상세 (Slack table block)
    enriched = result.get("enriched", [])

    # table block 생성 (attachments에 넣어야 함)
    table_rows = [
        # header row
        [
            {"type": "raw_text", "text": "성분"},
            {"type": "raw_text", "text": "Ratio"},
            {"type": "raw_text", "text": "제품수"},
            {"type": "raw_text", "text": "카테고리"},
        ],
    ]
    for e in enriched:
        cats = ", ".join(e["categories"])
        table_rows.append([
            {"type": "raw_text", "text": e["ingredient"]},
            {"type": "raw_text", "text": f"{e['ratio']}x"},
            {"type": "raw_text", "text": str(e["product_count"])},
            {"type": "raw_text", "text": cats},
        ])

    table_attachments = [{
        "blocks": [{
            "type": "table",
            "column_settings": [
                {"is_wrapped": True},
                {"align": "right"},
                {"align": "right"},
                {"is_wrapped": True},
            ],
            "rows": table_rows,
        }],
    }]

    safe_list = result.get("safe", [])
    safe_str = ", ".join(
        f"{s['ingredient']} ({s['frequency_pct']}%)" for s in safe_list
    )

    detail_text = brief.get("detail", "")

    thread_text = (
        f"═══ \"{keyword}\" 성분 상관관계 상세 ═══\n\n"
        + f"═══ 상세 해석 ═══\n\n"
        + f"> {detail_text}\n\n"
        + f"═══ 안전 성분 (\"{keyword}\" 무관) ═══\n\n"
        + f"{safe_str}\n\n"
        + "_⚠️ 상관관계 ≠ 인과관계. 제형 결정 시 참고용._"
    )

    await slack.send_with_thread(
        channel_id=channel_id,
        main_text=main_text,
        thread_text=thread_text,
        thread_attachments=table_attachments,
    )


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


async def _generate_category_keywords(
    node_id: str, category_name: str, response_url: str, channel_id: str,
):
    """Gemini로 카테고리 검색 키워드 자동 생성 → DB 저장 → Slack 알림."""
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    try:
        keywords = await gemini.generate_category_keywords(category_name)
        if not keywords:
            logger.warning("Empty keywords generated for category=%s", category_name)
            return

        product_db = ProductDBService("CFO")
        product_db.update_category_keywords(node_id, keywords)
        logger.info("Category keywords saved: %s → %s", category_name, keywords)

        if response_url:
            await slack.send_message(
                response_url,
                f"🏷️ *{category_name}* 검색 키워드 설정 완료:\n`{keywords}`",
                ephemeral=True, channel_id=channel_id,
            )
    except Exception:
        logger.exception("Category keyword generation failed for %s", category_name)
    finally:
        await gemini.close()
        try:
            await slack.close()
        except Exception:
            pass


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

    # 키워드 검색 snapshot인지 확인
    product_db = ProductDBService("CFO")
    keyword_log = product_db.get_keyword_search_by_snapshot(snapshot_id)

    if keyword_log:
        logger.info(
            "Bright Data webhook: keyword search snapshot %s ready (keyword=%s)",
            snapshot_id, keyword_log["keyword"],
        )
        background_tasks.add_task(_ingest_keyword_snapshot, snapshot_id, keyword_log)
        return {"status": "accepted", "snapshot_id": snapshot_id, "type": "keyword_search"}

    # 카테고리 원샷 수집인지 확인
    category_cb = _category_collection_callbacks.get(snapshot_id)
    if category_cb:
        logger.info(
            "Bright Data webhook: category oneshot snapshot %s ready (category=%s)",
            snapshot_id, category_cb["name"],
        )
        background_tasks.add_task(_ingest_and_analyze_category, snapshot_id, category_cb)
        return {"status": "accepted", "snapshot_id": snapshot_id, "type": "category_oneshot"}

    logger.info("Bright Data webhook: snapshot %s ready, starting BSR ingestion", snapshot_id)
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
    count = 0

    async def _work() -> int:
        products = await bright_data.fetch_snapshot(snapshot_id)
        n = collector.process_snapshot(products)
        logger.info("Webhook ingestion complete: snapshot=%s, %d products", snapshot_id, n)
        return n

    try:
        count = await asyncio.wait_for(_work(), timeout=INGESTION_TIMEOUT)
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


async def _ingest_and_analyze_category(snapshot_id: str, cb: dict):
    """카테고리 원샷: snapshot fetch → DB 적재 → 분석 파이프라인 자동 실행."""
    node_id = cb["node_id"]
    name = cb["name"]
    response_url = cb.get("response_url", "")
    channel_id = cb.get("channel_id", "")
    user_id = cb.get("user_id", "")

    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    collector = DataCollector("CFO")

    try:
        products = await bright_data.fetch_snapshot(snapshot_id)
        count = collector.process_snapshot(products)
        logger.info(
            "Category oneshot ingestion complete: snapshot=%s, category=%s, %d products",
            snapshot_id, name, count,
        )
        # 콜백 제거
        _category_collection_callbacks.pop(snapshot_id, None)
        # 분석 파이프라인 자동 실행
        await run_analysis(node_id, name, response_url, channel_id, user_id)
    except Exception:
        logger.exception(
            "Category oneshot failed: snapshot=%s, category=%s", snapshot_id, name,
        )
        _category_collection_callbacks.pop(snapshot_id, None)
        slack = SlackSender(settings.AMZ_BOT_TOKEN)
        try:
            await slack.send_message(
                response_url,
                f"❌ *{name}* 수집/분석 실패",
                ephemeral=True, channel_id=channel_id,
            )
        finally:
            await slack.close()
    finally:
        await bright_data.close()


async def _ingest_keyword_snapshot(snapshot_id: str, keyword_log: dict):
    """키워드 검색 snapshot fetch → DB 적재 → 분석 파이프라인 실행."""
    keyword = keyword_log["keyword"]
    searched_at = keyword_log["searched_at"]
    response_url = keyword_log.get("response_url", "")
    channel_id = keyword_log.get("channel_id", "")

    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    collector = DataCollector("CFO")
    product_db = ProductDBService("CFO")

    try:
        # Step 1: snapshot fetch → DB 적재
        products_raw = await bright_data.fetch_snapshot(snapshot_id)
        if not products_raw:
            product_db.update_keyword_search_log(keyword, searched_at, "failed")
            logger.warning("Keyword snapshot %s returned empty for keyword=%s", snapshot_id, keyword)
            return

        count = collector.process_search_snapshot(products_raw, keyword, searched_at)
        product_db.update_keyword_search_log(keyword, searched_at, "completed", count)
        logger.info(
            "Keyword snapshot ingested: snapshot=%s, keyword=%s, %d products",
            snapshot_id, keyword, count,
        )

        # Step 2: 분석 파이프라인 실행
        keyword_products = product_db.get_keyword_products(keyword, searched_at)
        if not keyword_products:
            logger.warning("No keyword products after ingestion for keyword=%s", keyword)
            return

        await _run_keyword_analysis_pipeline(keyword, keyword_products, response_url, channel_id)

    except Exception:
        product_db.update_keyword_search_log(keyword, searched_at, "failed")
        logger.exception("Keyword snapshot ingestion failed: snapshot=%s, keyword=%s", snapshot_id, keyword)
    finally:
        await bright_data.close()
