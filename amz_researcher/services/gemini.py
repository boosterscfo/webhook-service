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
2. 제품 특성(features, additional_details)도 참고하여 성분의 맥락을 파악하라.

규칙:
1. 성분명은 영문 표준명으로 통일 (예: 아르간오일 → Argan Oil)
2. 같은 성분의 다른 이름은 가장 널리 쓰이는 이름으로 통일
   (예: Vitamin B7 = Biotin → "Biotin", Tocopherol = Vitamin E → "Vitamin E")
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
        {{"name": "Argan Oil", "category": "Natural Oil"}}
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

---

위 데이터를 바탕으로, **제품 기획팀**을 위한 시장 분석 리포트를 작성하라.

반드시 아래 5개 섹션을 포함:

1. **시장 요약 (Market Overview)**
   - 가격대 분포와 성분 트렌드 한줄 요약
   - 시장의 성숙도 판단

2. **가격대별 성분 전략 (Pricing & Ingredient Strategy)**
   - 각 가격대에서 필수 성분 vs 차별화 성분
   - 가격 프리미엄을 정당화하는 성분은 무엇인가

3. **승리 공식 (Winning Formula)**
   - BSR 상위 제품에만 있는 성분과 그 의미
   - 높은 평점 제품의 성분 조합 패턴
   - 추천 포뮬레이션 방향 (구체적 성분 조합 제시)

4. **경쟁 환경 & 화이트 스페이스 (Competitive Landscape)**
   - 주요 브랜드의 포지셔닝 분석
   - 아직 비어있는 시장 기회 (가격대 × 성분 조합)

5. **제품 기획 액션 아이템 (Action Items)**
   - 바로 실행할 수 있는 3-5개 구체적 제안
   - 각 제안에 근거 데이터 명시

형식: 마크다운. 각 섹션에 구체적 수치와 성분명을 반드시 포함.
JSON이 아닌 마크다운 텍스트로 출력하라."""


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
        self, products: list[dict], batch_size: int = 25,
    ) -> list[ProductIngredients]:
        all_results: list[ProductIngredients] = []

        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(products) + batch_size - 1) // batch_size
            logger.info("Gemini batch %d/%d (%d products)", batch_num, total_batches, len(batch))

            result = await self._extract_batch(batch)
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
                            "maxOutputTokens": 16384,
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
        prompt = MARKET_REPORT_PROMPT.format(
            keyword=analysis_data["keyword"],
            total_products=analysis_data["total_products"],
            price_tier_json=json.dumps(
                analysis_data["price_tier_analysis"], ensure_ascii=False, indent=2,
            ),
            bsr_json=json.dumps(
                analysis_data["bsr_analysis"], ensure_ascii=False, indent=2,
            ),
            brand_json=json.dumps(
                analysis_data["brand_analysis"], ensure_ascii=False, indent=2,
            ),
            cooccurrence_json=json.dumps(
                analysis_data["cooccurrence_analysis"], ensure_ascii=False, indent=2,
            ),
        )

        try:
            resp = await self.client.post(
                self.url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 8192,
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
            return text
        except Exception:
            logger.exception("Market report generation failed")
            return ""

    async def close(self):
        await self.client.aclose()
