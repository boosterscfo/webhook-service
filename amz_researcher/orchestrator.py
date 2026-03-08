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
)
from amz_researcher.services.browse_ai import BrowseAiService
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.product_db import ProductDBService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.excel_builder import build_excel
from amz_researcher.services.market_analyzer import build_market_analysis
from amz_researcher.services.slack_sender import SlackSender

logger = logging.getLogger(__name__)


def _extract_action_items_section(report_md: str) -> str:
    """시장 리포트 마크다운에서 '7. 제품 기획 액션 아이템' 섹션만 추출 (다음 8. 또는 ## 전까지)."""
    if not report_md or not report_md.strip():
        return ""
    # "7. **제품 기획 액션 아이템 (Action Items)**" 또는 "## 7." 형식 → 다음 "8." / "## 8" / 끝까지
    m = re.search(
        r"(?:^|\n)(?:##\s*)?7\.\s*(?:\*\*)?(?:제품\s*기획\s*액션\s*아이템|액션\s*아이템).*?\n(.*?)(?=\n(?:##\s*)?8\.|\n##\s|\Z)",
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
                "text": f"*제품 기획 액션 아이템*\n{action_md}",
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
    refresh: bool = False,
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
        analysis_data = build_market_analysis(keyword, weighted_products, all_details)

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
            form_price_data=analysis_data.get("form_price_matrix"),
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


def _product_details_to_dict(product_details: list[dict]) -> dict:
    """Bright Data product_details [{type, value}] → dict 변환."""
    return {
        item.get("type", ""): item.get("value", "")
        for item in product_details
        if item.get("type")
    }


def _adapt_for_analyzer(
    products: list[BrightDataProduct],
) -> tuple[list[SearchProduct], list[ProductDetail]]:
    """BrightDataProduct → 기존 analyzer가 기대하는 SearchProduct + ProductDetail 변환."""
    search_products = []
    details = []
    for i, p in enumerate(products):
        search_products.append(SearchProduct(
            position=i + 1,
            title=p.title,
            asin=p.asin,
            price=p.final_price,
            reviews=p.reviews_count,
            rating=p.rating,
            bought_past_month=p.bought_past_month,
        ))
        # product_details [{type, value}] → dict for features
        features_dict = _product_details_to_dict(p.product_details)
        details.append(ProductDetail(
            asin=p.asin,
            ingredients_raw=p.ingredients,
            features=features_dict,
            bsr_category=p.bs_rank,
            bsr_category_name=p.bs_category,
            rating=p.rating,
            review_count=p.reviews_count,
            brand=p.brand,
            manufacturer=p.manufacturer,
        ))
    return search_products, details


async def run_analysis(
    category_node_id: str,
    category_name: str,
    response_url: str,
    channel_id: str,
):
    """V4 DB 기반 분석 파이프라인. 카테고리 선택 후 호출."""
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
            await _msg(f"⚠️ *{category_name}* 카테고리에 수집된 제품이 없습니다. `/amz refresh`로 수집을 시작하세요.")
            return

        products = [BrightDataProduct(**_parse_db_row(r)) for r in raw_products]
        await _msg(
            f"📦 {len(products)}개 제품 로드 완료. 성분 분석 중...",
            ephemeral=True,
        )

        # Step 2: Gemini 성분 추출 (캐시 우선)
        asins = [p.asin for p in products]
        cached_ingredients = cache.get_ingredient_cache(asins)
        uncached = [p for p in products if p.asin not in cached_ingredients]

        if uncached:
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
            await _msg(
                f"♻️ 성분 추출 전체 캐시 사용: {len(cached_ingredients)}개",
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

        # Step 4: 시장 분석 리포트
        analysis_data = build_market_analysis(category_name, weighted_products, all_details)

        market_report = cache.get_market_report_cache(category_name, len(weighted_products)) or ""
        if market_report:
            logger.info("Market report cache hit for category=%s", category_name)
            await _msg("♻️ 시장 분석 리포트 캐시 사용", ephemeral=True)
        else:
            await _msg("📊 시장 분석 리포트 생성 중... (Gemini)", ephemeral=True)
            market_report = await gemini.generate_market_report(analysis_data)
            cache.save_market_report_cache(category_name, market_report, len(weighted_products))

        # Step 5: Excel
        excel_bytes = build_excel(
            category_name, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
            rising_products=analysis_data.get("rising_products"),
            form_price_data=analysis_data.get("form_price_matrix"),
        )

        # Step 6: Slack 요약
        fallback_text, summary_blocks = _build_summary_blocks(
            category_name, len(weighted_products), rankings[:10], market_report,
        )
        await slack.send_message(
            response_url, fallback_text,
            ephemeral=False, channel_id=channel_id,
            blocks=summary_blocks,
        )

        # Step 7: 파일 업로드
        filename = f"{category_name.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, filename,
            comment="📊 상세 분석 엑셀 파일",
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
