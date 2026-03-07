import logging

from app.config import settings
from amz_researcher.models import IngredientRanking
from amz_researcher.services.browse_ai import BrowseAiService
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.excel_builder import build_excel
from amz_researcher.services.slack_sender import SlackSender

logger = logging.getLogger(__name__)


def _build_summary(
    keyword: str, product_count: int, top_rankings: list[IngredientRanking],
) -> str:
    lines = []
    for r in top_rankings:
        avg_price_str = f"${r.avg_price:.0f}" if r.avg_price else "N/A"
        lines.append(
            f" {r.rank}. *{r.ingredient}* [{r.category}]\n"
            f"     Score: {r.weighted_score:.2f} | "
            f"{r.product_count}개 제품 | 평균가 {avg_price_str}"
        )
    rankings_text = "\n".join(lines)

    return (
        f'🧪 Amazon "{keyword}" 성분 분석 완료\n'
        f"분석 대상: {product_count}개 제품 | Powered by Gemini Flash\n\n"
        f"{rankings_text}\n\n"
        f"Score = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%)\n"
        f"성분 추출: 마케팅 소구 기준 (INCI 전성분 아님)"
    )


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

    try:
        # Step 1: Search (캐시 우선)
        search_products = None
        if not refresh:
            search_products = cache.get_search_cache(keyword)
        if search_products:
            logger.info("Search cache hit: %d products", len(search_products))
            await slack.send_message(
                response_url,
                f"♻️ 캐시 사용: {len(search_products)}개 제품. 상세 정보 확인 중...",
                ephemeral=True,
            )
        else:
            search_products = await browse.run_search(keyword)
            cache.save_search_cache(keyword, search_products)
            await slack.send_message(
                response_url,
                f"✅ 검색 완료: {len(search_products)}개 제품. 상세 크롤링 시작...",
                ephemeral=True,
            )

        # Step 2: Detail (캐시 우선, 미캐시 ASIN만 크롤링)
        asins = [p.asin for p in search_products]
        cached_details = {}
        if not refresh:
            cached_details = cache.get_detail_cache(asins)
        uncached_asins = [a for a in asins if a not in cached_details]

        if uncached_asins:
            new_details = await browse.run_details_batch(uncached_asins)
            cache.save_detail_cache(new_details)
            all_details = list(cached_details.values()) + new_details
            await slack.send_message(
                response_url,
                f"📦 상세 정보: 캐시 {len(cached_details)}개 + 신규 {len(new_details)}개",
                ephemeral=True,
            )
        else:
            all_details = list(cached_details.values())
            await slack.send_message(
                response_url,
                f"♻️ 상세 정보 전체 캐시 사용: {len(all_details)}개",
                ephemeral=True,
            )

        # Step 3: Gemini 성분 추출
        await slack.send_message(response_url, "🧪 성분 추출 중... (Gemini Flash)", ephemeral=True)
        products_for_gemini = [
            {
                "asin": d.asin,
                "ingredients_raw": d.ingredients_raw,
                "features": d.features,
                "additional_details": d.additional_details,
            }
            for d in all_details
        ]
        gemini_results = await gemini.extract_ingredients(products_for_gemini)

        # Step 4: Weight calculation
        weighted_products, rankings, categories = calculate_weights(
            search_products, all_details, gemini_results,
        )

        # Step 5: Excel generation
        excel_bytes = build_excel(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
        )

        # Step 6: Summary message
        summary = _build_summary(keyword, len(weighted_products), rankings[:10])
        await slack.send_message(response_url, summary)

        # Step 7: File upload
        filename = f"{keyword.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(
            channel_id, excel_bytes, filename,
            comment="📊 상세 분석 엑셀 파일",
        )
        logger.info("Research completed for keyword=%s", keyword)

    except Exception as e:
        logger.exception("Research failed for keyword=%s", keyword)
        await slack.send_message(
            response_url, f"❌ *{keyword}* 분석 실패: {e!s}",
            ephemeral=True,
        )
        admin_id = settings.AMZ_ADMIN_SLACK_ID
        if admin_id:
            await slack.send_dm(
                admin_id,
                f"🚨 AMZ Research 에러 발생\n키워드: {keyword}\n에러: {e!s}",
            )
    finally:
        await browse.close()
        await gemini.close()
        await slack.close()
