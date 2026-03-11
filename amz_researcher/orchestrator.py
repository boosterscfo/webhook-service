import json
import logging
import re

from app.config import settings
from amz_researcher.models import (
    BrightDataProduct,
    IngredientRanking,
    ProductDetail,
    ProductIngredients,
    SearchProduct,
    VoiceKeyword,
    VoiceKeywordResult,
    WeightedProduct,
)
from amz_researcher.services.browse_ai import BrowseAiService
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.product_db import ProductDBService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.bright_data import BrightDataService
from amz_researcher.services.data_collector import DataCollector
from amz_researcher.services.excel_builder import build_excel, build_keyword_excel
from amz_researcher.services.html_report_builder import build_html, build_keyword_html
from amz_researcher.services.market_analyzer import build_market_analysis, build_keyword_market_analysis
from amz_researcher.services.report_store import ReportStore
from amz_researcher.services.slack_sender import SlackSender

logger = logging.getLogger(__name__)

_report_store = ReportStore(
    base_dir=settings.REPORT_DIR,
    ttl_days=settings.REPORT_TTL_DAYS,
)


def _load_cached_voice_keywords(
    weighted_products: list[WeightedProduct],
    db: ProductDBService,
) -> VoiceKeywordResult | None:
    """DB에서 기존 voice 키워드를 로드하여 VoiceKeywordResult로 복원.

    customer_says가 있는 제품의 80% 이상이 캐시되어 있으면 사용.
    """
    with_cs = [p for p in weighted_products if p.customer_says]
    if len(with_cs) < 10:
        return None
    asins = [p.asin for p in with_cs]
    cached = db.load_voice_keywords(asins)
    if not cached:
        return None
    coverage = len(cached) / len(asins)
    if coverage < 0.8:
        logger.info("Voice keywords cache coverage %.0f%% < 80%%, re-extracting", coverage * 100)
        return None
    # per-product → keyword→asins 역변환
    pos_map: dict[str, list[str]] = {}
    neg_map: dict[str, list[str]] = {}
    for asin, kws in cached.items():
        for kw in kws.get("positive", []):
            pos_map.setdefault(kw, []).append(asin)
        for kw in kws.get("negative", []):
            neg_map.setdefault(kw, []).append(asin)
    result = VoiceKeywordResult(
        positive_keywords=[VoiceKeyword(keyword=k, asins=v) for k, v in pos_map.items()],
        negative_keywords=[VoiceKeyword(keyword=k, asins=v) for k, v in neg_map.items()],
    )
    # WeightedProduct에 주입
    for wp in weighted_products:
        if wp.asin in cached:
            wp.voice_positive = cached[wp.asin].get("positive", [])
            wp.voice_negative = cached[wp.asin].get("negative", [])
    logger.info(
        "Voice keywords loaded from cache: %d pos, %d neg (%.0f%% coverage)",
        len(result.positive_keywords), len(result.negative_keywords), coverage * 100,
    )
    return result


def _apply_voice_keywords(
    voice_keywords: VoiceKeywordResult | None,
    weighted_products: list[WeightedProduct],
    db: ProductDBService,
) -> None:
    """VoiceKeywordResult를 제품별로 역변환하여 WeightedProduct에 주입하고 DB 저장."""
    if not voice_keywords:
        return
    asin_kw: dict[str, dict[str, list[str]]] = {}
    for vk in voice_keywords.positive_keywords:
        for asin in vk.asins:
            asin_kw.setdefault(asin, {"positive": [], "negative": []})
            asin_kw[asin]["positive"].append(vk.keyword)
    for vk in voice_keywords.negative_keywords:
        for asin in vk.asins:
            asin_kw.setdefault(asin, {"positive": [], "negative": []})
            asin_kw[asin]["negative"].append(vk.keyword)
    # WeightedProduct에 주입
    for wp in weighted_products:
        if wp.asin in asin_kw:
            wp.voice_positive = asin_kw[wp.asin]["positive"]
            wp.voice_negative = asin_kw[wp.asin]["negative"]
    # DB 저장
    if db:
        db.save_voice_keywords(asin_kw)


def _extract_executive_summary(report_md: str) -> dict:
    """시장 리포트 마크다운에서 Executive Summary를 구조화하여 추출.

    Returns: {"overview": str, "strategy": str}
    - overview: 시장 요약 단락
    - strategy: **즉각적인 전략 제안:** 이후 내용
    """
    result = {"overview": "", "strategy": ""}
    if not report_md or not report_md.strip():
        return result
    m = re.search(
        r"(?:^|\n)##\s*Executive\s*Summary\s*\n(.*?)(?=\n###\s|\n---|\n\d+\.\s|\n##\s|\Z)",
        report_md,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return result
    text = m.group(1).strip()

    # "**즉각적인 전략 제안" 으로 분리
    strategy_m = re.search(
        r"\*\*즉각적인\s*전략\s*제안[^*]*\*\*[:\s]*(.*)",
        text,
        re.DOTALL,
    )
    if strategy_m:
        result["overview"] = text[: strategy_m.start()].strip()
        result["strategy"] = strategy_m.group(1).strip()
    else:
        result["overview"] = text
    # Slack section 블록 최대 3000자 제한
    result["overview"] = result["overview"][:2000]
    result["strategy"] = result["strategy"][:1000]
    return result


def _sanitize_for_slack(text: str) -> str:
    """마크다운 텍스트를 Slack mrkdwn 호환 형식으로 변환."""
    # **bold** → *bold*
    text = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text)
    # __italic__ → _italic_
    text = re.sub(r"__([^_]+)__", r"_\1_", text)
    return text


def _build_report_blocks(
    label: str,
    report_url: str,
    exec_parts: dict,
    requester: str = "",
    report_type: str = "BSR",
) -> tuple[str, list[dict]]:
    """Executive Summary + 리포트 버튼을 Block Kit으로 구성.

    Returns: (fallback_text, blocks)
    """
    mention_prefix = f"{requester} " if requester else ""
    blocks: list[dict] = []

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"{label} {report_type} 분석 리포트", "emoji": True},
    })

    # 요청자 멘션
    if requester:
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f":mag:  {requester} 님이 요청한 분석입니다."},
            ],
        })

    blocks.append({"type": "divider"})

    # 시장 요약
    overview = _sanitize_for_slack(exec_parts.get("overview", ""))
    if overview:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": overview},
        })
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{label}* 분석이 완료되었습니다."},
        })

    # 전략 제안
    strategy = _sanitize_for_slack(exec_parts.get("strategy", ""))
    if strategy:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":bulb: *즉각적인 전략 제안*\n{strategy}"},
        })

    # 리포트 CTA
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": ":chart_with_upwards_trend:  인사이트 리포트 보기", "emoji": True},
                "url": report_url,
                "style": "primary",
            },
        ],
    })
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": "차트·테이블로 시장 데이터를 인터랙티브하게 확인할 수 있습니다."},
        ],
    })

    fallback_text = f"{mention_prefix}{label} {report_type} 분석 리포트: {report_url}"
    return fallback_text, blocks


def _extract_action_items_section(report_md: str) -> str:
    """시장 리포트 마크다운에서 '액션 아이템' 섹션만 추출 (다음 번호 섹션 또는 ## 전까지)."""
    if not report_md or not report_md.strip():
        return ""
    # "N. **액션 아이템 (Action Items)**" 형식 → 다음 번호 섹션 / ## / 끝까지
    m = re.search(
        r"(?:^|\n)(?:##\s*)?\d+\.\s*(?:\*\*)?액션\s*아이템.*?\n(.*?)(?=\n(?:##\s*)?\d+\.|\n##\s|\Z)",
        report_md,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        text = m.group(1).strip()
        return text[:2000] if len(text) > 2000 else text
    return ""


def _build_summary_text(
    keyword: str, product_count: int, top_rankings: list[IngredientRanking],
) -> str:
    """Fallback용 플레인 텍스트 요약 (알림/접근성)."""
    lines = []
    for r in top_rankings[:5]:
        avg_price_str = f"${r.avg_price:.0f}" if r.avg_price else "-"
        lines.append(
            f"  {r.rank}. *{r.ingredient}*  |  "
            f"Score {r.weighted_score:.2f}  |  "
            f"{r.product_count}개 제품  |  {avg_price_str}"
        )
    rankings_text = "\n".join(lines)
    return (
        f"*Amazon \"{keyword}\" 성분 분석 완료*\n"
        f"{product_count}개 제품 분석 | Gemini Flash\n\n"
        f"*Top 5 성분*\n{rankings_text}\n\n"
        f"_Score = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)_\n"
        f"_자세한 내용은 첨부 Excel 파일의 Market Insight 시트를 참조하세요._"
    )


def _build_summary_blocks(
    keyword: str,
    product_count: int,
    top_rankings: list[IngredientRanking],
    market_report: str,
) -> tuple[str, list[dict]]:
    """Block Kit 블록으로 요약 구성. (fallback_text, blocks) 반환."""
    lines = []
    for r in top_rankings[:5]:
        avg_price_str = f"${r.avg_price:.0f}" if r.avg_price else "-"
        lines.append(
            f"• {r.rank}. *{r.ingredient}*  Score {r.weighted_score:.2f}  "
            f"| {r.product_count}개 제품 | {avg_price_str}"
        )
    rankings_mrkdwn = "\n".join(lines)
    action_md = _extract_action_items_section(market_report)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f'Amazon "{keyword}" 성분 분석 완료', "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{product_count}개 제품 분석 | Gemini Flash",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Top 5 성분*\n{rankings_mrkdwn}\n\n_Score = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)_",
            },
        },
    ]
    if action_md:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*액션 아이템*\n{action_md}",
            },
        })
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": "자세한 내용은 첨부 Excel 파일의 Market Insight 시트를 참조하세요."},
        ],
    })

    fallback_text = _build_summary_text(keyword, product_count, top_rankings)
    return fallback_text, blocks


async def run_research(
    keyword: str, response_url: str, channel_id: str,
    refresh: bool = False, user_id: str = "",
):
    browse = BrowseAiService(
        api_key=settings.BROWSE_AI_API_KEY,
        search_robot_id=settings.AMZ_SEARCH_ROBOT_ID,
        detail_robot_id=settings.AMZ_DETAIL_ROBOT_ID,
    )
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    cache = AmzCacheService("CFO")

    async def _msg(text: str, ephemeral: bool = False):
        await slack.send_message(response_url, text, ephemeral=ephemeral, channel_id=channel_id)

    try:
        # Step 1: Search (캐시 우선)
        search_products = None
        if not refresh:
            search_products = cache.get_search_cache(keyword)
        if search_products:
            logger.info("Search cache hit: %d products", len(search_products))
            await _msg(
                f"♻️ 캐시 사용: {len(search_products)}개 제품. 상세 정보 확인 중...",
                ephemeral=True,
            )
        else:
            search_products = await browse.run_search(keyword)
            cache.save_search_cache(keyword, search_products)
            await _msg(
                f"✅ 검색 완료: {len(search_products)}개 제품. 상세 크롤링 시작...",
                ephemeral=True,
            )

        # Step 2: Detail (캐시 우선, 실패 ASIN 제외, 미캐시만 크롤링)
        asins = [p.asin for p in search_products]
        cached_details = {}
        failed_asins = set()
        if not refresh:
            cached_details = cache.get_detail_cache(asins)
            failed_asins = cache.get_failed_asins()
        uncached_asins = [
            a for a in asins
            if a not in cached_details and a not in failed_asins
        ]
        skipped_count = len([a for a in asins if a in failed_asins])
        if skipped_count:
            logger.info("Skipping %d previously failed ASINs", skipped_count)

        if uncached_asins:
            try:
                new_details, failures = await browse.run_details_batch(uncached_asins)
                if not cache.save_detail_cache(new_details):
                    logger.error("Detail cache save failed — %d results may be lost", len(new_details))
                # 실패 원인별로 분류 저장
                for reason, failed_list in failures.items():
                    cache.save_failed_asins(failed_list, keyword, reason=reason)
            except Exception:
                logger.warning(
                    "Browse.ai batch failed for %d ASINs, proceeding with %d cached",
                    len(uncached_asins), len(cached_details),
                )
                new_details = []
                # 배치 전체 실패 → 일시적 실패로 기록 (재시도 가능)
                cache.save_failed_asins(uncached_asins, keyword, reason="batch_error")
            all_details = list(cached_details.values()) + new_details
            await _msg(
                f"📦 상세 정보: 캐시 {len(cached_details)}개 + 신규 {len(new_details)}개"
                f" (스킵 {skipped_count + len(uncached_asins) - len(new_details)}개)",
                ephemeral=True,
            )
        else:
            all_details = list(cached_details.values())
            await _msg(
                f"♻️ 상세 정보 전체 캐시 사용: {len(all_details)}개"
                + (f" (실패 {skipped_count}개 스킵)" if skipped_count else ""),
                ephemeral=True,
            )

        if not all_details:
            await _msg(
                f"⚠️ *{keyword}* 상세 정보를 가져올 수 없어 분석을 중단합니다. "
                f"(캐시 0개, 크롤링 실패)",
                ephemeral=True,
            )
            logger.warning("No details available for keyword=%s, aborting", keyword)
            return

        # Step 3: Gemini 성분 추출 (캐시 우선)
        detail_asins = [d.asin for d in all_details]
        cached_ingredients = {}
        if not refresh:
            cached_ingredients = cache.get_ingredient_cache(detail_asins)
        uncached_detail_asins = [a for a in detail_asins if a not in cached_ingredients]

        if uncached_detail_asins:
            await _msg(
                f"🧪 성분 추출 중... (캐시 {len(cached_ingredients)}개, "
                f"신규 {len(uncached_detail_asins)}개 → Gemini Flash)",
                ephemeral=True,
            )
            detail_map = {d.asin: d for d in all_details}
            title_map = {p.asin: p.title for p in search_products}
            products_for_gemini = [
                {
                    "asin": asin,
                    "title": title_map.get(asin, ""),
                    "ingredients_raw": detail_map[asin].ingredients_raw,
                    "features": detail_map[asin].features,
                    "additional_details": detail_map[asin].additional_details,
                }
                for asin in uncached_detail_asins
            ]
            new_gemini_results = await gemini.extract_ingredients(products_for_gemini)
            # 추출 성공한 것만 캐시 (빈 결과는 캐시하지 않음)
            extracted_asins = {r.asin for r in new_gemini_results}
            failed_extraction = len(uncached_detail_asins) - len(extracted_asins)
            if failed_extraction:
                logger.warning(
                    "Gemini extraction failed for %d/%d ASINs, not caching failures",
                    failed_extraction, len(uncached_detail_asins),
                )
            if new_gemini_results:
                if not cache.save_ingredient_cache(new_gemini_results):
                    logger.error("Ingredient cache save failed — %d results may be lost", len(new_gemini_results))
                cache.harmonize_common_names()
            # 캐시 + 신규 병합
            gemini_results = new_gemini_results + [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]
        else:
            await _msg(
                f"♻️ 성분 추출 전체 캐시 사용: {len(cached_ingredients)}개",
                ephemeral=True,
            )
            gemini_results = [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]

        # Step 4: Weight calculation
        weighted_products, rankings, categories = calculate_weights(
            search_products, all_details, gemini_results,
        )

        # Step 5: AI 시장 분석 리포트 (캐시 우선)
        _db = ProductDBService("CFO")
        voice_keywords = _load_cached_voice_keywords(weighted_products, _db)
        if voice_keywords:
            await _msg("♻️ Consumer Voice 키워드 캐시 사용", ephemeral=True)
        else:
            await _msg("🗣️ Consumer Voice 키워드 추출 중... (Gemini)", ephemeral=True)
            voice_keywords = await gemini.extract_voice_keywords(keyword, weighted_products)
            _apply_voice_keywords(voice_keywords, weighted_products, _db)
        title_keywords = await gemini.extract_title_keywords(keyword, weighted_products)
        analysis_data = build_market_analysis(keyword, weighted_products, all_details, voice_keywords=voice_keywords, title_keywords=title_keywords)

        market_report = ""
        if not refresh:
            market_report = cache.get_market_report_cache(keyword, len(weighted_products)) or ""
        if market_report:
            logger.info("Market report cache hit for keyword=%s", keyword)
            await _msg("♻️ 시장 분석 리포트 캐시 사용", ephemeral=True)
        else:
            await _msg("📊 시장 분석 리포트 생성 중... (Gemini)", ephemeral=True)
            market_report = await gemini.generate_market_report(analysis_data)
            cache.save_market_report_cache(keyword, market_report, len(weighted_products))

        # Step 6: Excel generation
        excel_bytes = build_excel(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            rising_products=analysis_data.get("rising_products"),
            analysis_data=analysis_data,
        )

        # Step 7: Summary message (Block Kit)
        fallback_text, summary_blocks = _build_summary_blocks(
            keyword, len(weighted_products), rankings[:10], market_report,
        )
        await slack.send_message(
            response_url, fallback_text,
            ephemeral=False, channel_id=channel_id,
            blocks=summary_blocks,
        )

        # Step 8: File upload
        filename = f"{keyword.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, filename,
            comment="📊 상세 분석 엑셀 파일",
        )
        logger.info("Research completed for keyword=%s", keyword)

    except Exception as e:
        logger.exception("Research failed for keyword=%s", keyword)
        await _msg(f"❌ *{keyword}* 분석 실패: {e!s}", ephemeral=True)
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Research 에러 발생\n키워드: {keyword}\n에러: {e!s}",
            )
    finally:
        for client in (browse, gemini, slack):
            try:
                await client.close()
            except Exception:
                logger.warning("Failed to close %s", type(client).__name__)


# ── V4: DB 기반 분석 파이프라인 ──────────────────────────


def _parse_db_row(row: dict) -> dict:
    """DB 조회 결과(dict)를 BrightDataProduct 생성자 인자로 변환."""
    import math

    result = dict(row)
    # JSON 문자열 → Python 객체
    for field in ("features", "categories", "subcategory_ranks", "product_details"):
        val = result.get(field)
        if isinstance(val, str):
            try:
                result[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[field] = []
    # pandas NaN → None 변환
    for key, val in result.items():
        if isinstance(val, float) and math.isnan(val):
            result[key] = None
    return result


# product_details에서 measurements로 분류할 키
_MEASUREMENT_KEYS = {
    "Product Dimensions", "Package Dimensions", "Item Weight",
    "Item Dimensions LxWxH", "Units",
}


def _product_details_to_dicts(
    product_details: list[dict],
) -> tuple[dict, dict, dict]:
    """Bright Data product_details [{type, value}] → (features, measurements, additional) 분리."""
    features: dict = {}
    measurements: dict = {}
    additional: dict = {}
    # 메타/중복 키는 additional로
    _META_KEYS = {"ASIN", "Best Sellers Rank", "Customer Reviews", "Manufacturer"}
    for item in product_details:
        key = item.get("type", "")
        val = item.get("value", "")
        if not key:
            continue
        if key in _MEASUREMENT_KEYS:
            measurements[key] = val
        elif key in _META_KEYS:
            additional[key] = val
        else:
            features[key] = val
    return features, measurements, additional


def _adapt_for_analyzer(
    products: list[BrightDataProduct],
) -> tuple[list[SearchProduct], list[ProductDetail]]:
    """BrightDataProduct → 기존 analyzer가 기대하는 SearchProduct + ProductDetail 변환."""
    search_products = []
    details = []
    for i, p in enumerate(products):
        price_str = f"${p.final_price:.2f}" if p.final_price is not None else ""
        search_products.append(SearchProduct(
            position=i + 1,
            title=p.title,
            asin=p.asin,
            price=p.final_price,
            price_raw=price_str,
            reviews=p.reviews_count,
            reviews_raw=str(p.reviews_count) if p.reviews_count else "",
            rating=p.rating,
            product_link=p.url,
            bought_past_month=p.bought_past_month,
        ))
        # product_details [{type, value}] → features/measurements/additional 분리
        features_dict, meas_dict, add_dict = _product_details_to_dicts(p.product_details)
        # subcategory_ranks에서 첫 번째 서브카테고리 추출
        sub_rank = None
        sub_name = ""
        if p.subcategory_ranks:
            first_sub = p.subcategory_ranks[0]
            sub_rank = first_sub.get("subcategory_rank")
            sub_name = first_sub.get("subcategory_name", "")
        details.append(ProductDetail(
            asin=p.asin,
            ingredients_raw=p.ingredients,
            features=features_dict,
            measurements=meas_dict,
            additional_details=add_dict,
            bsr_category=p.bs_rank,
            bsr_category_name=p.bs_category,
            bsr_subcategory=sub_rank,
            bsr_subcategory_name=sub_name,
            rating=p.rating,
            review_count=p.reviews_count,
            brand=p.brand,
            manufacturer=p.manufacturer,
            product_url=p.url,
        ))
    return search_products, details


# ── 원샷 카테고리 수집 → 분석 콜백 저장소 ──────────────
# snapshot_id → {node_id, name, response_url, channel_id, user_id}
_category_collection_callbacks: dict[str, dict] = {}


async def _trigger_category_collection(
    node_id: str,
    name: str,
    response_url: str,
    channel_id: str,
    user_id: str = "",
):
    """미수집 카테고리의 Bright Data 수집을 트리거하고 콜백 정보를 저장."""
    product_db = ProductDBService("CFO")
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    url = product_db.get_category_url(node_id)
    if not url:
        await slack.send_message(
            response_url,
            f"❌ *{name}* 카테고리 URL을 찾을 수 없습니다.",
            ephemeral=True, channel_id=channel_id,
        )
        await slack.close()
        return

    bright_data = BrightDataService(
        api_token=settings.BRIGHT_DATA_API_TOKEN,
        dataset_id=settings.BRIGHT_DATA_DATASET_ID,
    )
    try:
        notify_url = f"{settings.WEBHOOK_BASE_URL}/webhook/brightdata"
        snapshot_id = await bright_data.trigger_collection(
            [url], notify_url=notify_url,
        )
        # 콜백 정보 저장 (webhook 수신 시 자동 분석용)
        _category_collection_callbacks[snapshot_id] = {
            "node_id": node_id,
            "name": name,
            "response_url": response_url,
            "channel_id": channel_id,
            "user_id": user_id,
        }
        # is_active 전환
        product_db.activate_category(node_id)

        await slack.send_message(
            response_url,
            f"📡 *{name}* 데이터 수집 시작... 완료 시 자동으로 분석 결과를 보내드립니다.",
            ephemeral=True, channel_id=channel_id,
        )
    except Exception:
        logger.exception("Category collection trigger failed for %s", name)
        await slack.send_message(
            response_url,
            f"❌ *{name}* 수집 트리거 실패",
            ephemeral=True, channel_id=channel_id,
        )
    finally:
        await bright_data.close()
        await slack.close()


async def run_analysis(
    category_node_id: str,
    category_name: str,
    response_url: str,
    channel_id: str,
    user_id: str = "",
    report_only: bool = False,
):
    """V4 DB 기반 분석 파이프라인. report_only=True면 Gemini 호출 없이 캐시로 리포트만 재빌드."""
    product_db = ProductDBService("CFO")
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    cache = AmzCacheService("CFO")

    async def _msg(text: str, ephemeral: bool = False):
        await slack.send_message(response_url, text, ephemeral=ephemeral, channel_id=channel_id)

    try:
        # Step 1: DB에서 제품 조회
        raw_products = product_db.get_products_by_category(category_node_id)
        if not raw_products:
            # 미수집 카테고리 → Bright Data 원샷 수집 트리거
            await _trigger_category_collection(
                category_node_id, category_name,
                response_url, channel_id, user_id,
            )
            return

        products = [BrightDataProduct(**_parse_db_row(r)) for r in raw_products]
        await _msg(
            f"📦 {len(products)}개 제품 로드 완료. {'리포트 재생성 중...' if report_only else '성분 분석 중...'}",
            ephemeral=True,
        )

        # Step 2: Gemini 성분 추출 (report_only면 캐시만 사용)
        asins = [p.asin for p in products]
        cached_ingredients = cache.get_ingredient_cache(asins)
        uncached = [p for p in products if p.asin not in cached_ingredients]

        if uncached and not report_only:
            await _msg(
                f"🧪 성분 추출 중... (캐시 {len(cached_ingredients)}개, "
                f"신규 {len(uncached)}개 → Gemini Flash)",
                ephemeral=True,
            )
            products_for_gemini = [
                {
                    "asin": p.asin,
                    "title": p.title,
                    "ingredients_raw": p.ingredients,
                    "features": p.features,
                    "additional_details": {},
                }
                for p in uncached
            ]
            new_results = await gemini.extract_ingredients(products_for_gemini)
            extracted_asins = {r.asin for r in new_results}
            failed_extraction = len(uncached) - len(extracted_asins)
            if failed_extraction:
                logger.warning(
                    "Gemini extraction failed for %d/%d ASINs",
                    failed_extraction, len(uncached),
                )
            if new_results:
                cache.save_ingredient_cache(new_results)
                cache.harmonize_common_names()
            gemini_results = new_results + [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]
        else:
            if report_only and uncached:
                logger.info("report_only: skipping %d uncached ASINs", len(uncached))
            await _msg(
                f"♻️ 성분 추출 캐시 사용: {len(cached_ingredients)}개",
                ephemeral=True,
            )
            gemini_results = [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]

        # Step 3: 가중치 계산 (기존 analyzer 재사용)
        search_products, all_details = _adapt_for_analyzer(products)
        weighted_products, rankings, categories = calculate_weights(
            search_products, all_details, gemini_results,
        )

        # V4 확장 필드를 WeightedProduct에 주입
        bright_map = {p.asin: p for p in products}
        for wp in weighted_products:
            bp = bright_map.get(wp.asin)
            if bp:
                wp.sns_price = bp.sns_price
                wp.unit_price = bp.unit_price
                wp.number_of_sellers = bp.number_of_sellers
                wp.coupon = bp.coupon
                wp.plus_content = bp.plus_content
                wp.customer_says = bp.customer_says
                # V5 신규
                wp.badge = bp.badge
                wp.initial_price = bp.initial_price
                wp.manufacturer = bp.manufacturer
                wp.variations_count = bp.variations_count

        # Step 4: 시장 분석 리포트
        voice_keywords = _load_cached_voice_keywords(weighted_products, product_db)
        if voice_keywords:
            await _msg("♻️ Consumer Voice 키워드 캐시 사용", ephemeral=True)
        else:
            await _msg("🗣️ Consumer Voice 키워드 추출 중... (Gemini)", ephemeral=True)
            voice_keywords = await gemini.extract_voice_keywords(category_name, weighted_products)
            _apply_voice_keywords(voice_keywords, weighted_products, product_db)
        title_keywords = await gemini.extract_title_keywords(category_name, weighted_products)
        analysis_data = build_market_analysis(category_name, weighted_products, all_details, voice_keywords=voice_keywords, title_keywords=title_keywords)

        market_report = cache.get_market_report_cache(category_name, len(weighted_products)) or ""
        if market_report:
            logger.info("Market report cache hit for category=%s", category_name)
            await _msg("♻️ 시장 분석 리포트 캐시 사용", ephemeral=True)
        elif report_only:
            logger.warning("report_only but no cached market report for %s", category_name)
            await _msg("⚠️ 캐시된 시장 분석 리포트가 없습니다. `/amz` 명령으로 전체 분석을 먼저 실행하세요.", ephemeral=True)
            return
        else:
            await _msg("📊 시장 분석 리포트 생성 중... (Gemini)", ephemeral=True)
            market_report = await gemini.generate_market_report(analysis_data)
            cache.save_market_report_cache(category_name, market_report, len(weighted_products))

        # Step 5: Excel + HTML
        excel_bytes = build_excel(
            category_name, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            rising_products=analysis_data.get("rising_products"),
            analysis_data=analysis_data,
        )
        html_bytes = build_html(
            category_name, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            rising_products=analysis_data.get("rising_products"),
            analysis_data=analysis_data,
        )

        # Step 6: Executive Summary + 리포트 URL + Excel
        requester = f"<@{user_id}>" if user_id else ""
        report_id = _report_store.save(html_bytes, label=category_name)
        report_url = f"{settings.WEBHOOK_BASE_URL}/reports/{report_id}"
        exec_parts = _extract_executive_summary(market_report)
        report_fallback, report_blocks = _build_report_blocks(
            category_name, report_url, exec_parts, requester, report_type="BSR",
        )
        await slack.send_message(
            response_url, report_fallback,
            ephemeral=False, channel_id=channel_id,
            blocks=report_blocks,
        )
        excel_filename = f"{category_name.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, excel_filename,
            comment="📋 원본 데이터 엑셀",
        )
        logger.info("Analysis completed for category=%s (%d products)", category_name, len(products))

    except Exception as e:
        logger.exception("Analysis failed for category=%s", category_name)
        await _msg(f"❌ *{category_name}* 분석 실패: {e!s}", ephemeral=True)
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Analysis 에러\n카테고리: {category_name}\n에러: {e!s}",
            )
    finally:
        for client in (gemini, slack):
            try:
                await client.close()
            except Exception:
                logger.warning("Failed to close %s", type(client).__name__)


# ── V6: 키워드 검색 분석 파이프라인 ──────────────────────


def _safe_num(val):
    """pandas NaN / None → None 방어."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


def _prepare_for_gemini(keyword_product: dict) -> dict:
    """키워드 검색 결과를 Gemini 성분 추출 입력으로 변환.

    키워드 검색 API에는 ingredients 전용 필드가 없으므로
    description → ingredients_raw로 매핑하여 Gemini가 추출하도록 함.
    """
    features_raw = keyword_product.get("features", "[]")
    if isinstance(features_raw, str):
        try:
            features = json.loads(features_raw)
        except (json.JSONDecodeError, TypeError):
            features = []
    else:
        features = features_raw or []

    return {
        "asin": keyword_product["asin"],
        "title": keyword_product.get("title", ""),
        "ingredients_raw": keyword_product.get("description", ""),
        "features": features,
        "additional_details": {},
    }


def _adapt_search_for_analyzer(
    keyword_products: list[dict],
) -> tuple[list[SearchProduct], list[ProductDetail]]:
    """키워드 검색 결과(DB dict) → SearchProduct + ProductDetail 변환."""
    search_products = []
    details = []

    for row in keyword_products:
        price = _safe_num(row.get("price"))
        price_str = f"${price:.2f}" if price is not None else ""
        bought = _safe_num(row.get("bought_past_month"))
        bought_int = int(bought) if bought is not None else None

        search_products.append(SearchProduct(
            position=row.get("position", 0),
            title=row.get("title", ""),
            asin=row["asin"],
            price=price,
            price_raw=price_str,
            reviews=int(_safe_num(row.get("reviews_count")) or 0),
            reviews_raw=str(int(_safe_num(row.get("reviews_count")) or 0)),
            rating=float(_safe_num(row.get("rating")) or 0),
            sponsored=bool(row.get("sponsored", 0)),
            product_link=row.get("product_url", ""),
            bought_past_month=bought_int,
        ))

        # features: JSON string → list → dict 변환
        features_raw = row.get("features", "[]")
        if isinstance(features_raw, str):
            try:
                features_list = json.loads(features_raw)
            except (json.JSONDecodeError, TypeError):
                features_list = []
        else:
            features_list = features_raw or []
        features_dict = {f"Feature {i+1}": f for i, f in enumerate(features_list)} if isinstance(features_list, list) else {}

        bsr = _safe_num(row.get("bsr"))
        if bsr is not None:
            bsr = int(bsr)

        details.append(ProductDetail(
            asin=row["asin"],
            ingredients_raw=row.get("description", ""),
            features=features_dict,
            measurements={},
            additional_details={},
            bsr_category=bsr,
            bsr_category_name=row.get("bsr_category", ""),
            rating=float(row.get("rating") or 0),
            review_count=row.get("reviews_count") or 0,
            brand=row.get("brand", ""),
            manufacturer=row.get("manufacturer", ""),
            product_url=row.get("product_url", ""),
        ))

    return search_products, details


async def run_keyword_analysis(
    keyword: str,
    response_url: str,
    channel_id: str,
    user_id: str = "",
):
    """V6 키워드 검색: 캐시 HIT → 즉시 분석, MISS → Bright Data 트리거 후 종료 (webhook 콜백 대기)."""
    product_db = ProductDBService("CFO")
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    normalized_keyword = " ".join(keyword.lower().split())

    async def _msg(text: str, ephemeral: bool = False):
        await slack.send_message(response_url, text, ephemeral=ephemeral, channel_id=channel_id)

    try:
        # Step 1: 캐시 확인
        cached = product_db.get_keyword_cache(normalized_keyword)

        if cached and cached.get("status") == "collecting":
            from datetime import datetime
            elapsed = (datetime.now() - cached["searched_at"]).total_seconds()
            if elapsed < 600:  # 10분 미만
                await _msg(
                    f"⏳ *\"{keyword}\"* 검색이 이미 진행 중입니다. 잠시 후 다시 시도하세요.",
                    ephemeral=True,
                )
                return
            # 10분 초과 → timeout, 재수집 허용

        keyword_products = []
        searched_at = None

        if cached and cached.get("status") == "completed":
            # 캐시 HIT → 즉시 분석 파이프라인
            searched_at = cached["searched_at"]
            keyword_products = product_db.get_keyword_products(normalized_keyword, searched_at)
            if keyword_products:
                from datetime import datetime
                days_ago = (datetime.now() - searched_at).days
                await _msg(
                    f"♻️ 캐시 사용 ({days_ago}일 전 수집, {len(keyword_products)}개 제품). 분석 시작...",
                    ephemeral=True,
                )

        if keyword_products:
            # 캐시 HIT → 분석 파이프라인 즉시 실행
            await _run_keyword_analysis_pipeline(keyword, keyword_products, response_url, channel_id, user_id)
            return

        # 캐시 MISS → Bright Data 트리거 (비동기, webhook 콜백 대기)
        bright_data = BrightDataService(
            api_token=settings.BRIGHT_DATA_API_TOKEN,
            dataset_id=settings.BRIGHT_DATA_DATASET_ID,
        )
        try:
            notify_url = f"{settings.WEBHOOK_BASE_URL}/webhook/brightdata"
            snapshot_id = await bright_data.trigger_keyword_search(
                normalized_keyword, notify_url=notify_url,
            )
            searched_at = product_db.save_keyword_search_log(
                normalized_keyword,
                snapshot_id=snapshot_id,
                response_url=response_url,
                channel_id=channel_id,
            )
            await _msg(
                f"📡 *\"{keyword}\"* Bright Data 수집 시작... 완료 시 자동으로 분석 결과를 보내드립니다.",
                ephemeral=True,
            )
            logger.info(
                "Keyword search triggered (async): keyword=%s, snapshot_id=%s, notify=%s",
                normalized_keyword, snapshot_id, notify_url,
            )
        except Exception:
            if searched_at:
                product_db.update_keyword_search_log(normalized_keyword, searched_at, "failed")
            raise
        finally:
            await bright_data.close()

    except Exception as e:
        logger.exception("Keyword analysis trigger failed for keyword=%s", keyword)
        await _msg(f"❌ *\"{keyword}\"* 검색 분석 실패: {e!s}", ephemeral=True)
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Keyword Analysis 에러\n키워드: {keyword}\n에러: {e!s}",
            )
    finally:
        try:
            await slack.close()
        except Exception:
            logger.warning("Failed to close SlackSender")


async def _run_keyword_analysis_pipeline(
    keyword: str,
    keyword_products: list[dict],
    response_url: str,
    channel_id: str,
    user_id: str = "",
    report_only: bool = False,
):
    """키워드 검색 분석 파이프라인. report_only=True면 Gemini 호출 없이 캐시로 리포트만 재빌드."""
    normalized_keyword = " ".join(keyword.lower().split())
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)
    cache = AmzCacheService("CFO")
    product_db = ProductDBService("CFO")

    async def _msg(text: str, ephemeral: bool = False):
        await slack.send_message(response_url, text, ephemeral=ephemeral, channel_id=channel_id)

    try:
        # Step 1: 성분 보완 (2-Layer)
        asins = [p["asin"] for p in keyword_products]
        cached_ingredients = cache.get_ingredient_cache(asins)
        uncached_asins = [a for a in asins if a not in cached_ingredients]

        if uncached_asins and not report_only:
            await _msg(
                f"🧪 성분 캐시 {len(cached_ingredients)}건 매칭 / {len(uncached_asins)}건 Gemini 추출 중...",
                ephemeral=True,
            )
            product_map = {p["asin"]: p for p in keyword_products}
            products_for_gemini = [
                _prepare_for_gemini(product_map[asin])
                for asin in uncached_asins
                if asin in product_map
            ]
            new_results = await gemini.extract_ingredients(products_for_gemini)
            extracted_asins = {r.asin for r in new_results}
            failed_extraction = len(uncached_asins) - len(extracted_asins)
            if failed_extraction:
                logger.warning(
                    "Gemini extraction failed for %d/%d ASINs (keyword search)",
                    failed_extraction, len(uncached_asins),
                )
            if new_results:
                cache.save_ingredient_cache(new_results)
                cache.harmonize_common_names()
            gemini_results = new_results + [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]
        else:
            if report_only and uncached_asins:
                logger.info("report_only: skipping %d uncached ASINs", len(uncached_asins))
            await _msg(
                f"♻️ 성분 추출 캐시 사용: {len(cached_ingredients)}개",
                ephemeral=True,
            )
            gemini_results = [
                ProductIngredients(asin=asin, ingredients=ings)
                for asin, ings in cached_ingredients.items()
            ]

        # Step 2: 가중치 계산
        search_products, all_details = _adapt_search_for_analyzer(keyword_products)
        weighted_products, rankings, categories = calculate_weights(
            search_products, all_details, gemini_results,
        )

        # V4 확장 필드 주입
        kp_map = {p["asin"]: p for p in keyword_products}
        for wp in weighted_products:
            kp = kp_map.get(wp.asin)
            if kp:
                bsr_val = _safe_num(kp.get("bsr"))
                wp.bsr_category = int(bsr_val) if bsr_val is not None else None
                wp.badge = kp.get("badge", "") or ""
                wp.initial_price = _safe_num(kp.get("initial_price"))
                wp.sns_price = _safe_num(kp.get("sns_price"))
                wp.manufacturer = kp.get("manufacturer", "") or ""
                wp.variations_count = int(_safe_num(kp.get("variations_count")) or 0)
                wp.coupon = str(kp.get("coupon", "") or "")
                wp.plus_content = bool(kp.get("plus_content", 0))
                wp.customer_says = str(kp.get("customer_says", "") or "")
                wp.number_of_sellers = int(_safe_num(kp.get("number_of_sellers")) or 1)
                bpm = _safe_num(kp.get("bought_past_month"))
                wp.bought_past_month = int(bpm) if bpm is not None else None

        # Step 3: 시장 분석 (BSR 의존 분석 제외)
        voice_keywords = _load_cached_voice_keywords(weighted_products, product_db)
        if voice_keywords:
            await _msg("♻️ Consumer Voice 키워드 캐시 사용", ephemeral=True)
        else:
            await _msg("🗣️ Consumer Voice 키워드 추출 중... (Gemini)", ephemeral=True)
            voice_keywords = await gemini.extract_voice_keywords(normalized_keyword, weighted_products)
            _apply_voice_keywords(voice_keywords, weighted_products, product_db)
        title_keywords = await gemini.extract_title_keywords(normalized_keyword, weighted_products)
        analysis_data = build_keyword_market_analysis(normalized_keyword, weighted_products, all_details, voice_keywords=voice_keywords, title_keywords=title_keywords)

        market_report = cache.get_market_report_cache(normalized_keyword, len(weighted_products)) or ""
        if market_report:
            logger.info("Market report cache hit for keyword=%s", normalized_keyword)
            await _msg("♻️ 시장 분석 리포트 캐시 사용", ephemeral=True)
        elif report_only:
            logger.warning("report_only but no cached market report for keyword=%s", normalized_keyword)
            await _msg("⚠️ 캐시된 시장 분석 리포트가 없습니다. `/amz search` 명령으로 전체 분석을 먼저 실행하세요.", ephemeral=True)
            return
        else:
            await _msg("📊 시장 분석 리포트 생성 중... (Gemini)", ephemeral=True)
            market_report = await gemini.generate_market_report(analysis_data)
            cache.save_market_report_cache(normalized_keyword, market_report, len(weighted_products))

        # Step 4: Excel + HTML 생성
        excel_bytes = build_keyword_excel(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            analysis_data=analysis_data,
        )
        html_bytes = build_keyword_html(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            analysis_data=analysis_data,
        )

        # Step 5: Executive Summary + 리포트 URL + Excel
        requester = f"<@{user_id}>" if user_id else ""
        report_id = _report_store.save(html_bytes, label=keyword)
        report_url = f"{settings.WEBHOOK_BASE_URL}/reports/{report_id}"
        exec_parts = _extract_executive_summary(market_report)
        report_fallback, report_blocks = _build_report_blocks(
            keyword, report_url, exec_parts, requester, report_type="키워드",
        )
        await slack.send_message(
            response_url, report_fallback,
            ephemeral=False, channel_id=channel_id,
            blocks=report_blocks,
        )
        excel_filename = f"keyword_{keyword.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, excel_filename,
            comment="📋 원본 데이터 엑셀",
        )
        logger.info("Keyword analysis completed for keyword=%s (%d products)", keyword, len(keyword_products))

    except Exception as e:
        logger.exception("Keyword analysis pipeline failed for keyword=%s", keyword)
        await _msg(f"❌ *\"{keyword}\"* 검색 분석 실패: {e!s}", ephemeral=True)
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Keyword Analysis 에러\n키워드: {keyword}\n에러: {e!s}",
            )
    finally:
        for client in (gemini, slack):
            try:
                await client.close()
            except Exception:
                logger.warning("Failed to close %s", type(client).__name__)
