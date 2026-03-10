import asyncio
import json
import logging

import httpx

from amz_researcher.models import GeminiResponse, ProductIngredients

logger = logging.getLogger(__name__)


def _try_repair_json(text: str) -> str | None:
    """잘린 JSON을 복구 시도. 마지막 완전한 product까지 파싱."""
    # 마지막 완전한 product 블록의 끝(}])을 찾아 잘라냄
    last_complete = text.rfind("}]")
    if last_complete == -1:
        return None
    truncated = text[:last_complete + 2]
    # 열린 배열/객체 닫기
    open_braces = truncated.count("{") - truncated.count("}")
    open_brackets = truncated.count("[") - truncated.count("]")
    truncated += "}" * open_braces + "]" * open_brackets
    try:
        json.loads(truncated)
        return truncated
    except json.JSONDecodeError:
        return None

PROMPT_TEMPLATE = """아래는 아마존에서 수집한 제품 목록이다.
각 제품에는 INCI 전성분 리스트와 제품 특성 정보가 포함되어 있다.

작업:
1. INCI 전성분에서 마케팅적으로 강조할 만한 핵심 성분을 선별하라.
2. 제품 title, features, additional_details도 참고하여 성분의 맥락을 파악하라.
   - title에 명시된 핵심 성분(예: "with Biotin & Argan Oil")은 반드시 포함
   - ingredients_raw가 비어있어도 title/features에서 성분을 추출할 수 있다

규칙:
1. name: INCI 전성분에 표기된 원본 성분명 그대로 기록
   (예: "Argania Spinosa Kernel Oil", "Rosmarinus Officinalis Leaf Extract")
2. common_name: 소비자/마케팅에서 쓰는 핵심 일반명으로 통일
   핵심 원칙:
   - 같은 식물/성분 기원이면 부위(Leaf, Seed, Fruit, Kernel, Root)와 무관하게 동일한 common_name 사용
   - 형태(Extract, Oil)만 구분. 단, 같은 식물의 Extract 계열은 하나로 통일
   - INCI 학명, 일반명, 대소문자, 오타 등 표기가 달라도 같은 성분이면 반드시 동일한 common_name
   - 라벨에 일반명만 적혀 있어도(예: "Rosemary") 적절한 common_name으로 분류
   예시:
     "Argania Spinosa Kernel Oil" → "Argan Oil"
     "Rosmarinus Officinalis Leaf Extract" → "Rosemary Extract"
     "Rosmarinus Officinalis (Rosemary) Leaf Extract" → "Rosemary Extract"
     "ROSMARINUS OFFICINALIS LEAF EXTRACT" → "Rosemary Extract"
     "Rosemary" → "Rosemary Extract"
     "Rosmarinus Officinalis Leaf Oil" → "Rosemary Oil"
     "Tocopherol" → "Vitamin E"
     "Tocopheryl Acetate" → "Vitamin E"
     "Biotin" → "Biotin"
     "Cocos Nucifera Oil" → "Coconut Oil"
     "Helianthus Annuus Seed Oil" → "Sunflower Oil"
     "Helianthus Annuus (Sunflower) Seed Oil" → "Sunflower Oil"
3. 각 성분에 카테고리 부여:
   Natural Oil / Essential Oil / Vitamin / Protein / Peptide /
   Active/Functional / Hair Growth Complex / Silicone / Botanical /
   Pharmaceutical / Humectant / Other
4. 용매(Water), 방부제(Phenoxyethanol, Ethylhexylglycerin), 향료(Fragrance/Parfum/Linalool 등) 등 기본 성분은 제외
5. 화학적으로 식별 가능한 물질만 추출
6. JSON만 출력:

{{
  "products": [
    {{
      "asin": "제품ASIN",
      "ingredients": [
        {{"name": "Argania Spinosa Kernel Oil", "common_name": "Argan Oil", "category": "Natural Oil"}}
      ]
    }}
  ]
}}

제품 목록:
{products_json}"""


MARKET_REPORT_PROMPT = """아래는 아마존 "{keyword}" 카테고리의 시장 분석 데이터이다.
총 {total_products}개 제품을 분석한 결과이다.

## 분석 데이터

### 1. 가격대별 성분 전략
{price_tier_json}

### 2. BSR 상위 vs 하위 제품 성분 비교
{bsr_json}

### 3. 주요 브랜드 프로파일
{brand_json}

### 4. 성분 조합 분석 (Co-occurrence)
{cooccurrence_json}

### 5. 브랜드 포지셔닝 (가격 vs BSR)
{brand_positioning_json}

### 6. 급성장 제품 (리뷰 적지만 BSR 우수)
{rising_products_json}

### 7. 고평점 vs 저평점 성분 비교
{rating_ingredients_json}

### 8. 월간 판매량 분석
{sales_volume_json}

### 9. {section9_title}
{section9_json}

### 10. 쿠폰/프로모션 분석
{promotions_json}

### 11. 소비자 리뷰 키워드 분석 (Consumer Voice)
{customer_voice_json}

### 12. 배지 보유/미보유 성과 비교 (Badge Analysis)
{badges_json}

---

위 데이터를 바탕으로 시장 분석 리포트를 작성하라.

반드시 아래 10개 섹션을 포함:

## Executive Summary
- 3-4줄로 이 시장의 핵심을 요약 (시장 규모감, 지배적 가격대, 핵심 성분 트렌드, 최대 기회)
- 바로 실행 가능한 1-sentence 전략 제안
- 형식: 짧고 임팩트 있게, 의사결정자가 이것만 읽어도 핵심을 파악할 수 있도록

1. **시장 요약 (Market Overview)**
   - 가격대 분포와 성분 트렌드 한줄 요약
   - 시장의 성숙도 판단

2. **가격대별 성분 전략 (Pricing & Ingredient Strategy)**
   - 각 가격대에서 필수 성분 vs 차별화 성분
   - 가격 프리미엄을 정당화하는 성분은 무엇인가

3. **승리 공식 (Winning Formula)**
   - BSR 상위 제품에만 있는 성분과 그 의미
   - 고평점(4.5+) 전용 성분 vs 저평점(<4.3) 전용 성분의 차이와 해석
   - 추천 포뮬레이션 방향 (구체적 성분 조합 제시)

4. **경쟁 환경 & 브랜드 포지셔닝 (Competitive Landscape)**
   - 브랜드별 가격-BSR 포지셔닝 분석
   - 세그먼트별(Budget/Mid/Premium/Luxury) 주요 플레이어
   - 아직 비어있는 시장 기회

5. **급성장 제품 & 트렌드 (Rising Products)**
   - 리뷰 적지만 BSR 좋은 제품들의 공통점 분석
   - 신규 브랜드/K-뷰티 등 트렌드 시그널
   - 이 제품들이 성공하는 이유 추론

6. **판매량 & 경쟁 전략 (Sales & Competitive Tactics)**
   - 가격대별 판매량 차이와 전략적 의미
   - {section6_guidance}
   - 쿠폰/프로모션 사용 현황과 BSR 영향

7. **소비자 인식 & 배지 효과 (Consumer Voice & Badge Impact)**
   - 긍정/부정 리뷰 키워드 Top 5와 BSR 상관관계
   - 소비자가 실제로 중시하는 속성(향, 효과, 질감 등)
   - Badge(Amazon's Choice/Best Seller) 보유 제품의 성과 차이
   - Badge 획득 전략 제안

8. **액션 아이템 (Action Items)**
   - 바로 실행할 수 있는 3-5개 구체적 제안
   - 각 제안에 근거 데이터 명시
   - 타겟 가격대 명시

9. **리스크 & 주의사항 (Risks)**
   - 과포화 세그먼트 경고
   - 피해야 할 포지셔닝

형식: 마크다운. Executive Summary를 가장 먼저 작성하고, 이후 번호 섹션을 순서대로 작성.
각 섹션에 구체적 수치와 성분명을 반드시 포함.
데이터에 있는 수치만 인용하라. JSON이 아닌 마크다운 텍스트로 출력하라."""


class GeminiService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gemini-2.5-flash"
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{self.model}:generateContent"
        )
        self.client = httpx.AsyncClient(timeout=120.0)

    async def extract_ingredients(
        self, products: list[dict], batch_size: int = 20,
    ) -> list[ProductIngredients]:
        batches = [
            products[i:i + batch_size]
            for i in range(0, len(products), batch_size)
        ]
        logger.info(
            "Gemini extraction: %d products → %d batches (parallel)",
            len(products), len(batches),
        )

        tasks = [self._extract_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[ProductIngredients] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Gemini batch %d/%d failed: %s", i + 1, len(batches), result)
            else:
                all_results.extend(result)

        logger.info("Gemini total: %d/%d products extracted", len(all_results), len(products))
        return all_results

    async def _extract_batch(
        self, products: list[dict], max_retries: int = 1,
    ) -> list[ProductIngredients]:
        products_json = json.dumps(products, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(products_json=products_json)
        text = ""

        for attempt in range(1 + max_retries):
            try:
                resp = await self.client.post(
                    self.url,
                    params={"key": self.api_key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 32768,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                resp.raise_for_status()

                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )

                parsed = GeminiResponse.model_validate_json(text)
                return parsed.products

            except Exception:
                # 잘린 JSON 복구 시도 (재요청 전에)
                if text:
                    repaired = _try_repair_json(text)
                    if repaired:
                        try:
                            parsed = GeminiResponse.model_validate_json(repaired)
                            logger.warning(
                                "Gemini JSON repaired: %d/%d products recovered",
                                len(parsed.products), len(products),
                            )
                            return parsed.products
                        except Exception:
                            pass

                if attempt < max_retries:
                    logger.warning("Gemini parse failed, retrying (attempt %d)", attempt + 1)
                    continue
                logger.exception("Gemini extraction failed after retries")
                return []

        return []

    async def generate_market_report(self, analysis_data: dict) -> str:
        """시장 분석 데이터를 기반으로 AI 인사이트 리포트 생성."""
        def _dump(key: str) -> str:
            return json.dumps(analysis_data.get(key, {}), ensure_ascii=False, indent=2)

        # 키워드 검색: listing_tactics 사용, BSR 분석: sns_pricing 사용
        has_listing_tactics = bool(analysis_data.get("listing_tactics"))
        if has_listing_tactics:
            section9_title = "리스팅 전술 분석 (Listing Tactics: Sponsored, Coupon, A+ Content)"
            section9_json = _dump("listing_tactics")
            section6_guidance = "Sponsored 광고 비율, 쿠폰/할인 전략, A+ Content 채택률 등 리스팅 전술 분석"
        else:
            section9_title = "Subscribe & Save 가격 분석"
            section9_json = _dump("sns_pricing")
            section6_guidance = "SNS(Subscribe & Save) 채택 현황과 재구매 유도 효과"

        prompt = MARKET_REPORT_PROMPT.format(
            keyword=analysis_data["keyword"],
            total_products=analysis_data["total_products"],
            price_tier_json=_dump("price_tier_analysis"),
            bsr_json=_dump("bsr_analysis"),
            brand_json=_dump("brand_analysis"),
            cooccurrence_json=_dump("cooccurrence_analysis"),
            brand_positioning_json=_dump("brand_positioning"),
            rising_products_json=_dump("rising_products"),
            rating_ingredients_json=_dump("rating_ingredients"),
            sales_volume_json=_dump("sales_volume"),
            section9_title=section9_title,
            section9_json=section9_json,
            section6_guidance=section6_guidance,
            promotions_json=_dump("promotions"),
            customer_voice_json=_dump("customer_voice"),
            badges_json=_dump("badges"),
        )

        max_retries = 2
        for attempt in range(max_retries):
            try:
                resp = await self.client.post(
                    self.url,
                    params={"key": self.api_key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.3,
                            "maxOutputTokens": 16384,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                if text:
                    return text
                logger.warning("Market report empty response (attempt %d/%d)", attempt + 1, max_retries)
            except Exception:
                logger.warning("Market report generation failed (attempt %d/%d)", attempt + 1, max_retries)
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
        logger.error("Market report generation failed after %d attempts", max_retries)
        return ""

    async def generate_category_keywords(self, category_name: str) -> str:
        """카테고리명으로 검색용 키워드(한/영 별칭) 생성. 쉼표 구분 문자열 반환."""
        prompt = (
            f"Task: Generate search keywords for Amazon category.\n"
            f"Output format: english1, english2, english3, 한글1, 한글2, 한글3\n"
            f"IMPORTANT: You MUST include both English AND Korean (한글) keywords.\n\n"
            f"Facial Serums → facial serum, serum, ampoule, essence, 세럼, 앰플, 에센스, 페이셜세럼\n"
            f"Sun Skin Care → sunscreen, sunblock, SPF, UV protection, 선크림, 자외선차단, 선케어, 선블록\n"
            f"Lip Balms & Moisturizers → lip balm, lip care, chapstick, 립밤, 립케어, 립크림, 입술보습\n"
            f"{category_name} →"
        )
        try:
            resp = await self.client.post(
                self.url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 512,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()
            # 후처리: "Category → keywords" 형식에서 화살표 이후만 추출
            if "→" in text:
                text = text.split("→", 1)[1].strip()
            # 잘린 키워드 제거 (한글 2자 이하, 영어 2자 이하)
            parts = [p.strip().rstrip(",") for p in text.split(",")]
            cleaned = [p for p in parts if p and len(p) > 2]
            return ", ".join(cleaned)
        except Exception:
            logger.exception("Category keyword generation failed for '%s'", category_name)
            return ""

    async def close(self):
        await self.client.aclose()
