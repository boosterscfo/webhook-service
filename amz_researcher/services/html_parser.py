"""Browse.ai 아마존 prodDetTable HTML → dict 파서."""

import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_product_table(html: str) -> dict[str, str]:
    """아마존 prodDetTable HTML → {key: value} dict.

    Best Sellers Rank, Customer Reviews 셀은 스킵 (별도 핸들러 사용).
    """
    if not html:
        return {}
    try:
        soup = BeautifulSoup(html, "html.parser")
        result = {}
        for row in soup.select("table.prodDetTable tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            key = th.get_text(strip=True)
            if key in ("Best Sellers Rank", "Customer Reviews"):
                continue
            value = td.get_text(strip=True)
            result[key] = value
        return result
    except Exception:
        logger.exception("Failed to parse product table HTML")
        return {}


def parse_bsr(html: str) -> list[dict]:
    """item_details HTML에서 Best Sellers Rank 파싱.

    Returns:
        [{"rank": 581, "category": "Beauty & Personal Care"}, ...]
    """
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("table.prodDetTable tr"):
            th = row.find("th")
            if not th or "Best Sellers Rank" not in th.get_text():
                continue
            td = row.find("td")
            if not td:
                return []
            results = []
            for li in td.select("li"):
                text = li.get_text()
                m = re.search(r"#([\d,]+)\s+in\s+(.+?)(?:\s*\(|$)", text)
                if m:
                    rank = int(m.group(1).replace(",", ""))
                    category = m.group(2).strip()
                    results.append({"rank": rank, "category": category})
            return results
    except Exception:
        logger.exception("Failed to parse BSR from HTML")
    return []


def parse_customer_reviews(html: str) -> tuple[float | None, int | None]:
    """item_details HTML에서 별점/리뷰 수 파싱.

    Returns:
        (rating, review_count) — 파싱 실패 시 (None, None)
    """
    if not html:
        return None, None
    try:
        soup = BeautifulSoup(html, "html.parser")
        rating = None
        review_count = None

        # rating: title="X.X out of 5 stars"
        star_el = soup.find(attrs={"title": re.compile(r"out of 5 stars")})
        if star_el:
            m = re.search(r"([\d.]+)\s+out of", star_el["title"])
            if m:
                rating = float(m.group(1))

        # review_count: aria-label="N Reviews"
        review_el = soup.find(attrs={"aria-label": re.compile(r"Reviews")})
        if review_el:
            m = re.search(r"([\d,]+)", review_el["aria-label"])
            if m:
                review_count = int(m.group(1).replace(",", ""))

        return rating, review_count
    except Exception:
        logger.exception("Failed to parse customer reviews from HTML")
        return None, None
