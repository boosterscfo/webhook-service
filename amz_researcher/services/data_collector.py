import json
import logging
from datetime import date, datetime

import pandas as pd

from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

# 모회사/OEM → 실제 소비자 브랜드 매핑
# key: Bright Data brand 값 (대소문자 무시), value: title에서 매칭할 브랜드 목록
_BRAND_MAPPINGS: dict[str, list[str]] = {
    # 글로벌 대기업
    "kenvue": ["Neutrogena", "Aveeno", "Clean & Clear"],
    "galderma": ["Cetaphil", "Differin"],
    "procter & gamble": ["Olay"],
    "procter & gamble - haba hub": ["Olay"],
    "unilever": ["Dove", "Vaseline", "Pond's", "Noxzema", "Nexxus", "TRESemmé", "St. Ives"],
    "unilever intl": ["Vaseline"],
    "beiersdorf, inc.": ["NIVEA", "Eucerin", "Aquaphor", "Coppertone"],
    "kao usa inc.": ["Bioré", "Biore", "John Frieda", "Jergens", "Curél"],
    "edgewell personal care brands, llc": ["Banana Boat", "Hawaiian Tropic"],
    "l'oreal usa": ["CeraVe"],
    "l'oreal/cerave": ["CeraVe"],
    "factory eu - france cosmetique active production": ["La Roche-Posay"],
    "factory eu - france cosmetique active production (c.a.p) (lidv)": ["La Roche-Posay"],
    "amazonus/losqh": ["La Roche-Posay"],
    "deciem": ["The Ordinary"],
    "crown laboratories": ["PanOxyl", "Blue Lizard"],
    "amazonus/sk45i": ["PanOxyl", "Blue Lizard"],
    "burt's bees, inc.": ["Burt's Bees"],
    "blistex inc": ["Blistex", "Stridex"],
    "hero cosmetics": ["Mighty Patch", "Hero Cosmetics"],
    "the honest company": ["Honest Beauty"],
    "the honest company beauty": ["Honest Beauty"],
    # 한국 모회사 / OEM
    "apr": ["medicube", "Medicube"],
    "benow inc.": ["numbuzin"],
    "cosrx inc.": ["COSRX"],
    "mainspring america, inc. dba direct cosmetics": ["COSRX"],
    "boosters co., ltd.": ["EQQUALBERRY"],
    "boosters": ["EQQUALBERRY"],
    "theone cosmetic co.,ltd": ["EQQUALBERRY"],
    "amorepacific corporation": ["AESTURA", "Illiyoon", "LANEIGE"],
    "amorepacific us, inc. - laneige": ["LANEIGE"],
    "vtcosmetics": ["VT COSMETICS", "VT"],
    "mantong": ["TOSOWOONG"],
    "kolmar": ["ANUA", "MEDIHEAL", "Dr.Althea"],
    "kolmar korea co., ltd.": ["ANUA", "Abib"],
    "kolmar korea co. ltd": ["MEDITHERAPY"],
    "kolmar korea": ["ROUND LAB"],
    "cosmax, inc.": ["ANUA", "Anua"],
    "cosmax inc.": ["SUNGBOON EDITOR"],
    "cosmax, inc": ["Anua"],
    "cosmax.inc.": ["Abib"],
    "cosmax": ["ROUND LAB", "Beauty of Joseon", "Anua"],
    "cosmecca korea co., ltd": ["ANUA", "Anua"],
    "cosmecca korea co.,ltd.": ["Beauty of Joseon"],
    "cosmecca korea": ["Dr.Melaxin"],
    "cosmecca korea co., ltd. / cosmax, inc.": ["ANUA"],
    "john paul mitchell systems": ["Paul Mitchell"],
    "dickinson brands": ["Dickinson's", "T.N. Dickinson's", "Humphreys"],
    # Amazon 자체
    "amazon.com services llc.": ["Amazon Basics"],
    "amazon.com services, inc.": ["Amazon Basics"],
    "amazonus/thczr": ["Thayers"],
    "amazonus/beih7": ["Aquaphor"],
    "amazonus/burbp": ["Burt's Bees"],
    "amazonus/emcw9": ["AcneFree"],
    "amazonus/lorcd": ["L'Oreal"],
    "amazonus/vatpf": ["Vanicream"],
    # 기타
    "e.l.f. cosmetics": ["e.l.f."],
    "neutrogena corporation": ["Neutrogena"],
    "nivea for men": ["NIVEA"],
    "johnson & johnson": ["Neutrogena"],
    "johnson & johnson consumer products": ["Aveeno"],
    "johnson and johnson": ["OGX"],
    "church & dwight co., inc.": ["Viviscal"],
    "church and dwight co.": ["Mighty Patch"],
    "e.t. browne drug co., inc.": ["Palmer's"],
    "e.t. browne drug company inc.": ["Palmer's"],
    "e.t. browne drug company, inc.": ["Palmer's"],
    "elida beauty": ["POND'S"],
    "coty inc.": ["CoverGirl"],
    "naos": ["Bioderma"],
    "farouk systems inc": ["CHI"],
}


def _resolve_brand(raw_brand: str, title: str) -> str:
    """모회사/OEM 브랜드를 title 기반으로 실제 소비자 브랜드로 보정."""
    candidates = _BRAND_MAPPINGS.get(raw_brand.lower())
    if not candidates:
        return raw_brand

    title_lower = title.lower()
    # 긴 이름부터 매칭 (e.g. "Clean & Clear" before "Clean")
    for brand in sorted(candidates, key=len, reverse=True):
        if title_lower.startswith(brand.lower()):
            return brand
    # title 시작에 없으면 원본 유지
    return raw_brand


class DataCollector:
    """Bright Data 수집 데이터를 DB에 적재."""

    def __init__(self, environment: str = "CFO"):
        self._env = environment

    def process_snapshot(
        self, products: list[dict], snapshot_date: date | None = None,
    ) -> int:
        """수집 데이터를 amz_products + amz_products_history에 적재.

        Returns:
            적재된 제품 수
        """
        if not products:
            return 0
        snapshot_date = snapshot_date or date.today()

        # 1. amz_products upsert
        product_rows = [self._map_product(p) for p in products]
        df_products = pd.DataFrame(product_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_products, "amz_products")
        logger.info("Upserted %d products to amz_products", len(product_rows))

        # 2. amz_products_history append
        history_rows = [self._map_history(p, snapshot_date) for p in products]
        df_history = pd.DataFrame(history_rows)
        with MysqlConnector(self._env) as conn:
            conn.upsert_data(df_history, "amz_products_history")
        logger.info("Upserted %d rows to amz_products_history", len(history_rows))

        # 3. amz_product_categories 매핑
        cat_rows = self._map_categories(products, snapshot_date)
        if cat_rows:
            df_cats = pd.DataFrame(cat_rows)
            with MysqlConnector(self._env) as conn:
                conn.upsert_data(df_cats, "amz_product_categories")
            logger.info("Upserted %d product-category mappings", len(cat_rows))

        logger.info("Processed %d products (snapshot: %s)", len(products), snapshot_date)
        return len(products)

    def _map_product(self, raw: dict) -> dict:
        """Bright Data 응답 → amz_products 행."""
        buybox = raw.get("buybox_prices") or {}
        sns = buybox.get("sns_price") or {}
        sns_price = sns.get("base_price")

        title = (raw.get("title") or "")[:500]
        raw_brand = (raw.get("brand") or "")[:200]
        brand = _resolve_brand(raw_brand, title)

        return {
            "asin": raw["asin"],
            "title": title,
            "brand": brand,
            "description": raw.get("description") or "",
            "initial_price": raw.get("initial_price"),
            "final_price": raw.get("final_price"),
            "currency": raw.get("currency", "USD"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "root_bs_rank": raw.get("root_bs_rank"),
            "root_bs_category": raw.get("root_bs_category"),
            "subcategory_ranks": json.dumps(raw.get("subcategory_rank") or [], ensure_ascii=False),
            "ingredients": raw.get("ingredients") or "",
            "features": json.dumps(raw.get("features") or [], ensure_ascii=False),
            "product_details": json.dumps(raw.get("product_details") or [], ensure_ascii=False),
            "manufacturer": raw.get("manufacturer") or "",
            "department": raw.get("department") or "",
            "image_url": raw.get("image_url") or "",
            "url": raw.get("url") or "",
            "badge": raw.get("badge") or "",
            "bought_past_month": raw.get("bought_past_month"),
            "is_available": raw.get("is_available", True),
            "categories": json.dumps(raw.get("categories") or [], ensure_ascii=False),
            "customer_says": raw.get("customer_says") or "",
            "unit_price": buybox.get("unit_price") or "",
            "sns_price": sns_price,
            "variations_count": len(raw.get("variations") or []),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
            "plus_content": bool(raw.get("plus_content")),
            "collected_at": datetime.now(),
        }

    def _map_history(self, raw: dict, snapshot_date: date) -> dict:
        """Bright Data 응답 → amz_products_history 행."""
        return {
            "asin": raw["asin"],
            "snapshot_date": snapshot_date,
            "bs_rank": raw.get("bs_rank"),
            "bs_category": raw.get("bs_category"),
            "final_price": raw.get("final_price"),
            "rating": raw.get("rating"),
            "reviews_count": raw.get("reviews_count"),
            "bought_past_month": raw.get("bought_past_month"),
            "badge": raw.get("badge") or "",
            "root_bs_rank": raw.get("root_bs_rank"),
            "number_of_sellers": raw.get("number_of_sellers") or 1,
            "coupon": raw.get("coupon") or "",
        }

    def process_search_snapshot(
        self,
        products: list[dict],
        keyword: str,
        searched_at: datetime,
    ) -> int:
        """키워드 검색 결과를 amz_keyword_products에 적재.

        Args:
            products: Bright Data API 응답 (JSON array)
            keyword: 정규화된 검색 키워드
            searched_at: 검색 시각 (캐시 키)

        Returns:
            적재된 제품 수
        """
        if not products:
            return 0

        rows = []
        for i, raw in enumerate(products):
            title = (raw.get("title") or "")[:500]
            raw_brand = (raw.get("brand") or "")[:200]
            brand = _resolve_brand(raw_brand, title)

            # customer_says / customers_say fallback
            customer_says = raw.get("customer_says") or raw.get("customers_say") or ""

            rows.append({
                "keyword": keyword,
                "asin": raw.get("asin", ""),
                "title": title,
                "brand": brand,
                "manufacturer": (raw.get("manufacturer") or "")[:200],
                "price": raw.get("final_price"),
                "initial_price": raw.get("initial_price"),
                "currency": raw.get("currency", "USD"),
                "rating": raw.get("rating") or 0,
                "reviews_count": raw.get("reviews_count") or 0,
                "bsr": raw.get("root_bs_rank"),
                "bsr_category": (raw.get("root_bs_category") or "")[:200],
                "position": i + 1,
                "sponsored": 1 if raw.get("sponsored") else 0,
                "badge": (raw.get("badge") or "")[:100],
                "bought_past_month": raw.get("bought_past_month"),
                "coupon": (raw.get("coupon") or "")[:200],
                "customer_says": customer_says,
                "plus_content": 1 if raw.get("plus_content") else 0,
                "number_of_sellers": raw.get("number_of_sellers") or 1,
                "variations_count": len(raw.get("variations") or []) if isinstance(raw.get("variations"), list) else (raw.get("variations_count") or 0),
                "image_url": (raw.get("image_url") or "")[:500],
                "product_url": (raw.get("url") or "")[:500],
                "features": json.dumps(raw.get("features") or [], ensure_ascii=False),
                "description": raw.get("description") or "",
                "categories": json.dumps(raw.get("categories") or [], ensure_ascii=False),
                "searched_at": searched_at,
            })

        df = pd.DataFrame(rows)
        with MysqlConnector(self._env) as conn:
            # 동일 keyword + searched_at 기존 데이터 삭제 후 INSERT
            conn.delete_and_insert(
                df, "amz_keyword_products",
                where="keyword = %s AND searched_at = %s",
                where_params=(keyword, searched_at),
            )
        logger.info(
            "Inserted %d keyword products (keyword=%s, searched_at=%s)",
            len(rows), keyword, searched_at,
        )
        return len(rows)

    def _map_categories(self, products: list[dict], snapshot_date: date) -> list[dict]:
        """origin_url에서 카테고리 node_id를 추출하여 매핑 행 생성."""
        rows = []
        for p in products:
            origin = p.get("origin_url") or ""
            node_id = origin.rstrip("/").split("/")[-1] if origin else ""
            if node_id and node_id.isdigit():
                rows.append({
                    "asin": p["asin"],
                    "category_node_id": node_id,
                    "collected_at": snapshot_date,
                })
        return rows
