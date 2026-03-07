import logging

from app.config import settings
from amz_researcher.models import IngredientRanking, ProductIngredients
from amz_researcher.services.browse_ai import BrowseAiService
from amz_researcher.services.cache import AmzCacheService
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.excel_builder import build_excel
from amz_researcher.services.market_analyzer import build_market_analysis
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
                new_details = await browse.run_details_batch(uncached_asins)
                cache.save_detail_cache(new_details)
                # 실패한 ASIN 기록
                succeeded_asins = {d.asin for d in new_details}
                newly_failed = [a for a in uncached_asins if a not in succeeded_asins]
                if newly_failed:
                    cache.save_failed_asins(newly_failed, keyword)
            except Exception:
                logger.warning(
                    "Browse.ai batch failed for %d ASINs, proceeding with %d cached",
                    len(uncached_asins), len(cached_details),
                )
                new_details = []
                cache.save_failed_asins(uncached_asins, keyword)
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
            cache.save_ingredient_cache(new_gemini_results)
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
        market_report = ""
        if not refresh:
            market_report = cache.get_market_report_cache(keyword, len(weighted_products)) or ""
        if market_report:
            logger.info("Market report cache hit for keyword=%s", keyword)
            await _msg("♻️ 시장 분석 리포트 캐시 사용", ephemeral=True)
        else:
            await _msg("📊 시장 분석 리포트 생성 중... (Gemini)", ephemeral=True)
            analysis_data = build_market_analysis(keyword, weighted_products, all_details)
            market_report = await gemini.generate_market_report(analysis_data)
            cache.save_market_report_cache(keyword, market_report, len(weighted_products))

        # Step 6: Excel generation
        excel_bytes = build_excel(
            keyword, weighted_products, rankings, categories,
            search_products, all_details,
            market_report=market_report,
        )

        # Step 7: Summary message
        summary = _build_summary(keyword, len(weighted_products), rankings[:10])
        if market_report:
            # 리포트에서 액션 아이템 섹션 추출하여 Slack 요약에 추가
            action_start = market_report.find("## 5.")
            if action_start == -1:
                action_start = market_report.find("# 5.")
            if action_start != -1:
                action_section = market_report[action_start:action_start + 500]
                summary += f"\n\n📊 *AI Market Insight (요약)*\n{action_section.strip()}"
            else:
                summary += "\n\n📊 AI Market Insight → Excel 'Market Insight' 시트 참조"
        await _msg(summary)

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
        await browse.close()
        await gemini.close()
        await slack.close()
