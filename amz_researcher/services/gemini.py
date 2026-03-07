import json
import logging

import httpx

from amz_researcher.models import GeminiResponse, ProductIngredients

logger = logging.getLogger(__name__)

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


class GeminiService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gemini-2.5-flash"
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{self.model}:generateContent"
        )
        self.client = httpx.AsyncClient(timeout=60.0)

    async def extract_ingredients(
        self, products: list[dict], max_retries: int = 1,
    ) -> list[ProductIngredients]:
        products_json = json.dumps(products, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(products_json=products_json)

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
                logger.info(
                    "Gemini extracted ingredients for %d products",
                    len(parsed.products),
                )
                return parsed.products

            except Exception:
                if attempt < max_retries:
                    logger.warning("Gemini parse failed, retrying (attempt %d)", attempt + 1)
                    continue
                logger.exception("Gemini extraction failed after retries")
                return []

        return []

    async def close(self):
        await self.client.aclose()
