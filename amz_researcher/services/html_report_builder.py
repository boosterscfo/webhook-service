"""HTML Insight Report builder for AMZ Researcher.

Generates a self-contained HTML file with all data embedded as JSON.
JavaScript renders all sections dynamically from REPORT_DATA.
"""
from __future__ import annotations

import json

from amz_researcher.models import (
    CategorySummary,
    IngredientRanking,
    ProductDetail,
    SearchProduct,
    WeightedProduct,
)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _ranking_to_dict(r: IngredientRanking) -> dict:
    return {
        "rank": r.rank,
        "ingredient": r.ingredient,
        "weighted_score": r.weighted_score,
        "product_count": r.product_count,
        "avg_weight": r.avg_weight,
        "category": r.category,
        "avg_price": r.avg_price,
        "price_range": r.price_range,
        "key_insight": r.key_insight,
    }


def _category_to_dict(c: CategorySummary) -> dict:
    return {
        "category": c.category,
        "total_weighted_score": c.total_weighted_score,
        "type_count": c.type_count,
        "mention_count": c.mention_count,
        "avg_price": c.avg_price,
        "price_range": c.price_range,
        "top_ingredients": c.top_ingredients,
    }


def _product_to_dict(p: WeightedProduct) -> dict:
    return {
        "asin": p.asin,
        "title": p.title,
        "position": p.position,
        "price": p.price,
        "reviews": p.reviews,
        "rating": p.rating,
        "bsr_category": p.bsr_category,
        "composite_weight": p.composite_weight,
        "bought_past_month": p.bought_past_month,
        "brand": p.brand,
        "sns_price": p.sns_price,
        "unit_price": p.unit_price,
        "badge": p.badge,
        "initial_price": p.initial_price,
        "manufacturer": p.manufacturer,
        "coupon": p.coupon,
        "plus_content": p.plus_content,
        "customer_says": p.customer_says,
        "variations_count": p.variations_count,
        "ingredients": [
            {"name": i.name, "common_name": i.common_name, "category": i.category}
            for i in p.ingredients
        ],
    }


def _search_to_dict(p: SearchProduct) -> dict:
    return {
        "position": p.position,
        "title": p.title,
        "asin": p.asin,
        "price": p.price,
        "price_raw": p.price_raw,
        "reviews": p.reviews,
        "rating": p.rating,
        "sponsored": p.sponsored,
        "bought_past_month": p.bought_past_month,
    }


def _detail_to_dict(d: ProductDetail) -> dict:
    return {
        "asin": d.asin,
        "brand": d.brand,
        "bsr_category": d.bsr_category,
        "rating": d.rating,
        "review_count": d.review_count,
        "ingredients_raw": d.ingredients_raw,
        "manufacturer": d.manufacturer,
    }


def _serialize_report_data(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str,
    rising_products: list[dict] | None,
    analysis_data: dict | None,
    report_type: str,
) -> dict:
    """Common serialization for both report types."""
    from datetime import datetime

    return {
        "keyword": keyword,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "report_type": report_type,
        "total_products": len(weighted_products),
        "market_report": market_report,
        "rankings": [_ranking_to_dict(r) for r in rankings],
        "categories": [_category_to_dict(c) for c in categories],
        "rising_products": rising_products or [],
        "products": [_product_to_dict(p) for p in weighted_products],
        "search_products": [_search_to_dict(p) for p in search_products],
        "details": [_detail_to_dict(d) for d in details],
        "analysis": analysis_data or {},
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_html(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str = "",
    rising_products: list[dict] | None = None,
    analysis_data: dict | None = None,
) -> bytes:
    """Category BSR analysis -> 12-section HTML report."""
    report_data = _serialize_report_data(
        keyword, weighted_products, rankings, categories,
        search_products, details, market_report,
        rising_products, analysis_data, "category",
    )
    return _render(report_data)


def build_keyword_html(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str = "",
    analysis_data: dict | None = None,
) -> bytes:
    """Keyword search analysis -> 9-section HTML report (no Badge, Brand Positioning, Rising Products)."""
    report_data = _serialize_report_data(
        keyword, weighted_products, rankings, categories,
        search_products, details, market_report,
        None, analysis_data, "keyword",
    )
    return _render(report_data)


def _render(report_data: dict) -> bytes:
    json_str = json.dumps(report_data, ensure_ascii=False, default=str)
    html = _HTML_TEMPLATE.replace("const REPORT_DATA = {};", f"const REPORT_DATA = {json_str};")
    # Inline Chart.js bundle for offline use
    html = html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>',
        f"<script>{_get_chartjs_bundle()}</script>",
    )
    return html.encode("utf-8")


def _get_chartjs_bundle() -> str:
    """Load Chart.js UMD bundle from assets directory."""
    from pathlib import Path
    asset_path = Path(__file__).parent.parent / "assets" / "chart.min.js"
    if asset_path.exists():
        return asset_path.read_text(encoding="utf-8")
    # Fallback: return empty string with console warning
    return 'console.warn("Chart.js bundle not found at amz_researcher/assets/chart.min.js");'


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title id="page-title">AMZ Insight Report</title>
  <style>
    /* ===== DESIGN TOKENS ===== */
    :root {
      --color-market-insight:    #E91E63;
      --color-consumer-voice:    #FF9800;
      --color-badge-analysis:    #673AB7;
      --color-sales-pricing:     #009688;
      --color-brand-positioning: #3F51B5;
      --color-marketing-kw:      #795548;
      --color-ingredient-rank:   #1B2A4A;
      --color-ingredient-rank-light: #2E4A7A;
      --color-category-summary:  #2E86AB;
      --color-rising-products:   #00BCD4;
      --color-product-detail:    #4CAF50;
      --color-raw-search:        #FF6B35;
      --color-raw-detail:        #9B59B6;

      --color-bg-page:    #0F1117;
      --color-bg-card:    #1A1D27;
      --color-bg-sidebar: #13151F;
      --color-bg-input:   #22253A;
      --color-bg-row-alt: #1E2130;
      --color-bg-hover:   #20233A;

      --color-text-primary:   #F0F2F8;
      --color-text-secondary: #B0B8CA;
      --color-text-muted:     #4D5468;
      --color-positive:  #22C55E;
      --color-negative:  #EF4444;
      --color-border:    #2A2D3E;

      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: "SF Mono", "Fira Code", monospace;

      --sidebar-width: 220px;
      --header-height: 56px;
      --radius-sm: 4px;
      --radius-md: 8px;
      --radius-lg: 12px;
      --radius-full: 9999px;
    }

    /* ===== RESET ===== */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body {
      font-family: var(--font-sans);
      font-size: 14px;
      line-height: 1.5;
      color: var(--color-text-primary);
      background: var(--color-bg-page);
      min-height: 100vh;
    }

    /* ===== HEADER ===== */
    .header {
      position: fixed;
      top: 0; left: 0; right: 0;
      height: var(--header-height);
      background: var(--color-bg-sidebar);
      border-bottom: 1px solid var(--color-border);
      display: flex;
      align-items: center;
      padding: 0 20px;
      z-index: 100;
      gap: 16px;
    }
    .header-logo {
      font-size: 15px;
      font-weight: 700;
      color: var(--color-text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header-logo-dot {
      width: 8px; height: 8px;
      background: #E91E63;
      border-radius: 50%;
    }
    .header-keyword {
      background: rgba(233, 30, 99, 0.15);
      color: #E91E63;
      border: 1px solid rgba(233, 30, 99, 0.3);
      padding: 3px 10px;
      border-radius: var(--radius-full);
      font-size: 13px;
      font-weight: 600;
    }
    .header-meta {
      color: var(--color-text-muted);
      font-size: 12px;
      margin-left: auto;
    }
    .back-to-top {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      color: var(--color-text-secondary);
      padding: 5px 12px;
      border-radius: var(--radius-md);
      cursor: pointer;
      font-size: 12px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .back-to-top:hover { color: var(--color-text-primary); border-color: #666; }
    .hamburger {
      display: none; background: none; border: 1px solid var(--color-border);
      color: var(--color-text-secondary); padding: 4px 10px; border-radius: var(--radius-md);
      cursor: pointer; font-size: 18px; line-height: 1;
    }
    .hamburger:hover { color: var(--color-text-primary); border-color: #666; }
    @media (max-width: 1023px) { .hamburger { display: block; } }

    /* ===== SIDEBAR ===== */
    .sidebar {
      position: fixed;
      top: var(--header-height);
      left: 0;
      bottom: 0;
      width: var(--sidebar-width);
      background: var(--color-bg-sidebar);
      border-right: 1px solid var(--color-border);
      overflow-y: auto;
      z-index: 50;
      padding: 16px 0;
    }
    .sidebar::-webkit-scrollbar { width: 4px; }
    .sidebar::-webkit-scrollbar-track { background: transparent; }
    .sidebar::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }

    .nav-group-label {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--color-text-muted);
      padding: 8px 16px 4px;
      margin-top: 8px;
    }
    .nav-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 16px;
      cursor: pointer;
      color: var(--color-text-secondary);
      font-size: 13px;
      text-decoration: none;
      transition: all 0.15s;
      border-left: 3px solid transparent;
      position: relative;
    }
    .nav-item:hover { color: var(--color-text-primary); background: rgba(255,255,255,0.04); }
    .nav-item.active { color: var(--color-text-primary); }
    .nav-dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      border: 1.5px solid currentColor;
      flex-shrink: 0;
      transition: all 0.15s;
    }
    .nav-item.active .nav-dot { border: none; }

    /* ===== MAIN CONTENT ===== */
    .main {
      margin-left: var(--sidebar-width);
      margin-top: var(--header-height);
      padding: 0;
    }

    /* ===== SECTION ===== */
    .section {
      padding: 40px 32px 56px;
      border-bottom: 1px solid var(--color-border);
      max-width: 1200px;
    }
    .section-header {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 28px;
      padding-left: 12px;
      border-left: 3px solid var(--section-color, #666);
    }
    .section-title {
      font-size: 20px;
      font-weight: 700;
      color: var(--color-text-primary);
    }
    .section-subtitle {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin-top: 3px;
    }

    /* ===== CARDS ===== */
    .card {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: 16px;
    }
    .card-grid { display: grid; gap: 16px; }
    .card-grid-2 { grid-template-columns: repeat(2, 1fr); }
    .card-grid-3 { grid-template-columns: repeat(3, 1fr); }
    .card-grid-4 { grid-template-columns: repeat(4, 1fr); }
    .card-grid-5 { grid-template-columns: repeat(5, 1fr); }

    .kpi-card {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: 20px;
      transition: transform 0.15s, box-shadow 0.15s;
    }
    .kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
    .kpi-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--color-text-secondary);
      margin-bottom: 8px;
    }
    .kpi-value { font-size: 28px; font-weight: 700; color: var(--color-text-primary); line-height: 1; }
    .kpi-sub { font-size: 12px; color: var(--color-text-muted); margin-top: 6px; }

    /* ===== RANK CARDS ===== */
    .rank-card {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: 20px 16px;
      text-align: center;
      position: relative;
      transition: transform 0.15s, box-shadow 0.15s;
    }
    .rank-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
    .rank-number { position: absolute; top: 10px; left: 12px; font-size: 11px; font-weight: 700; color: var(--color-text-muted); }
    .rank-card.rank-1 { border-color: rgba(255,215,0,0.3); }
    .rank-card.rank-1 .rank-number { color: #FFD700; }
    .rank-card.rank-2 { border-color: rgba(192,192,192,0.3); }
    .rank-card.rank-2 .rank-number { color: #C0C0C0; }
    .rank-card.rank-3 { border-color: rgba(205,127,50,0.3); }
    .rank-card.rank-3 .rank-number { color: #CD7F32; }
    .rank-name { font-size: 14px; font-weight: 700; margin: 8px 0 4px; }
    .rank-score { font-size: 26px; font-weight: 700; color: var(--section-color, #666); line-height: 1; }
    .rank-score-label { font-size: 10px; color: var(--color-text-muted); }
    .rank-count { font-size: 12px; color: var(--color-text-secondary); margin-top: 6px; }

    /* ===== TABLES ===== */
    .table-wrapper {
      overflow-x: auto;
      border-radius: var(--radius-md);
      border: 1px solid var(--color-border);
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead th {
      background: rgba(255,255,255,0.04);
      padding: 10px 12px;
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--color-text-secondary);
      border-bottom: 1px solid var(--color-border);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
      transition: color 0.15s;
    }
    thead th:hover { color: var(--color-text-primary); }
    thead th .sort-icon { margin-left: 4px; opacity: 0.4; font-size: 10px; }
    thead th.sorted .sort-icon { opacity: 1; }
    tbody tr { border-bottom: 1px solid var(--color-bg-row-alt); transition: background 0.1s; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:nth-child(even) { background: rgba(255,255,255,0.02); }
    tbody tr:hover { background: var(--color-bg-hover); }
    td { padding: 9px 12px; color: var(--color-text-primary); vertical-align: middle; }
    td.muted { color: var(--color-text-secondary); }
    td.mono { font-family: var(--font-mono); font-size: 12px; }

    /* ===== BADGES / PILLS ===== */
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: var(--radius-full);
      font-size: 11px;
      font-weight: 600;
      line-height: 1.6;
    }
    .badge-positive { background: rgba(34,197,94,0.15); color: #22C55E; }
    .badge-negative { background: rgba(239,68,68,0.15); color: #EF4444; }
    .badge-budget   { background: rgba(100,116,139,0.2); color: #94A3B8; }
    .badge-mid      { background: rgba(59,130,246,0.2); color: #60A5FA; }
    .badge-premium  { background: rgba(168,85,247,0.2); color: #C084FC; }
    .badge-luxury   { background: rgba(234,179,8,0.2); color: #FBBF24; }
    .badge-kbeauty  { background: rgba(233,30,99,0.15); color: #F06292; }

    /* ===== CHARTS ===== */
    .chart-container {
      position: relative;
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: 20px;
    }
    canvas { max-width: 100%; }

    /* ===== SUBSECTION ===== */
    .subsection { margin-top: 32px; }
    .subsection-title {
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--color-text-muted);
      margin-bottom: 12px;
    }

    /* ===== SEARCH INPUT ===== */
    .search-input {
      background: var(--color-bg-input);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: 7px 12px;
      font-size: 13px;
      color: var(--color-text-primary);
      font-family: var(--font-sans);
      outline: none;
      transition: border-color 0.15s;
      width: 240px;
    }
    .search-input:focus { border-color: #555; }
    .search-input::placeholder { color: var(--color-text-muted); }

    /* ===== MARKDOWN RENDER ===== */
    .markdown-body h1 { font-size: 20px; font-weight: 700; margin: 24px 0 12px; color: var(--color-text-primary); }
    .markdown-body h2 { font-size: 16px; font-weight: 700; margin: 20px 0 10px; color: var(--color-text-primary); }
    .markdown-body h3 { font-size: 14px; font-weight: 700; margin: 16px 0 8px; color: var(--color-text-primary); }
    .markdown-body p { margin: 8px 0; color: var(--color-text-secondary); line-height: 1.7; }
    .markdown-body ul, .markdown-body ol { padding-left: 20px; margin: 8px 0; }
    .markdown-body li { margin: 4px 0; color: var(--color-text-secondary); line-height: 1.6; }
    .markdown-body strong { color: var(--color-text-primary); font-weight: 600; }
    .markdown-body hr { border: none; border-top: 1px solid var(--color-border); margin: 20px 0; }
    .markdown-section {
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      margin-bottom: 8px;
      overflow: hidden;
    }
    .markdown-section summary {
      padding: 14px 16px;
      cursor: pointer;
      font-size: 15px;
      font-weight: 700;
      color: var(--color-text-primary);
      background: rgba(255,255,255,0.03);
      list-style: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      user-select: none;
    }
    .markdown-section summary::-webkit-details-marker { display: none; }
    .markdown-section summary::after { content: '\25BE'; font-size: 12px; color: var(--color-text-muted); }
    .markdown-section[open] summary::after { content: '\25B4'; }
    .markdown-section-body { padding: 0 16px 16px; }

    /* ===== CONSUMER VOICE BARS ===== */
    .kw-bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
    .kw-bar-label { width: 120px; font-size: 13px; color: var(--color-text-secondary); flex-shrink: 0; }
    .kw-bar-track { flex: 1; height: 8px; background: rgba(255,255,255,0.06); border-radius: var(--radius-full); overflow: hidden; }
    .kw-bar-fill { height: 100%; border-radius: var(--radius-full); transition: width 0.4s ease; }
    .kw-bar-count { width: 32px; text-align: right; font-size: 12px; font-weight: 600; color: var(--color-text-primary); }
    .kw-bar-bsr { width: 60px; text-align: right; font-size: 11px; color: var(--color-text-muted); }

    /* ===== RISING PRODUCT CARDS ===== */
    .rising-card {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      padding: 16px;
      transition: border-color 0.15s, transform 0.15s;
    }
    .rising-card:hover { border-color: rgba(0,188,212,0.4); transform: translateY(-2px); }
    .rising-bsr { font-size: 11px; font-weight: 700; color: #00BCD4; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
    .rising-brand { font-size: 11px; color: var(--color-text-muted); margin-bottom: 4px; }
    .rising-title {
      font-size: 13px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 8px;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }
    .rising-metrics { display: flex; gap: 12px; font-size: 12px; color: var(--color-text-secondary); }
    .rising-ingredients { font-size: 11px; color: var(--color-text-muted); margin-top: 8px; }

    /* ===== STAT BOX ===== */
    .stat-box {
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
    }
    .stat-box-label { color: var(--color-text-secondary); }
    .stat-box-value { font-weight: 600; color: var(--color-text-primary); }

    /* ===== TWO COL LAYOUT ===== */
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }
    .two-col-left-wide { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; align-items: start; }

    /* ===== SIGNIFICANT TAG ===== */
    .sig-tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: var(--radius-full); font-size: 11px; font-weight: 600; }
    .sig-tag.yes { background: rgba(34,197,94,0.15); color: #22C55E; }
    .sig-tag.no { background: rgba(100,116,139,0.15); color: #94A3B8; }

    /* ===== TOOLBAR ===== */
    .toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }

    /* ===== PAGINATION ===== */
    .pagination { display: flex; align-items: center; gap: 6px; margin-top: 16px; justify-content: flex-end; flex-wrap: wrap; }
    .page-btn {
      background: var(--color-bg-card);
      border: 1px solid var(--color-border);
      color: var(--color-text-secondary);
      padding: 5px 10px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      font-size: 12px;
      transition: all 0.1s;
    }
    .page-btn:hover, .page-btn.active { color: var(--color-text-primary); border-color: #555; }
    .page-info { font-size: 12px; color: var(--color-text-muted); padding: 0 8px; }

    /* ===== RAW SECTION ===== */
    .raw-banner {
      background: rgba(255,107,53,0.08);
      border: 1px solid rgba(255,107,53,0.25);
      border-radius: var(--radius-md);
      padding: 10px 16px;
      font-size: 12px;
      color: rgba(255,107,53,0.9);
      margin-bottom: 16px;
    }

    /* ===== EMPTY STATE ===== */
    .empty-state {
      text-align: center;
      padding: 48px 24px;
      color: var(--color-text-muted);
      font-size: 13px;
    }

    /* ===== RESPONSIVE ===== */
    @media (max-width: 1023px) {
      .sidebar { transform: translateX(-100%); transition: transform 0.2s; }
      .sidebar.open { transform: translateX(0); }
      .main { margin-left: 0; }
      .card-grid-5 { grid-template-columns: repeat(3, 1fr); }
      .card-grid-4 { grid-template-columns: repeat(2, 1fr); }
      .two-col, .two-col-left-wide { grid-template-columns: 1fr; }
    }
    @media (max-width: 767px) {
      .section { padding: 24px 16px 40px; }
      .card-grid-5 { grid-template-columns: repeat(2, 1fr); }
      .card-grid-3 { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>

<!-- HEADER -->
<header class="header">
  <div class="header-logo">
    <div class="header-logo-dot"></div>
    AMZ Insight
  </div>
  <span class="header-keyword" id="header-keyword"></span>
  <span class="header-meta" id="header-meta"></span>
  <button class="hamburger" id="hamburger" onclick="document.getElementById('sidebar').classList.toggle('open')" aria-label="Toggle navigation">&#9776;</button>
  <a href="#market-insight" class="back-to-top">&#8593; Top</a>
</header>

<!-- SIDEBAR -->
<nav class="sidebar" id="sidebar">
  <div id="sidebar-nav"></div>
</nav>

<!-- MAIN CONTENT -->
<main class="main" id="main-content">
  <!-- Sections injected by JS -->
</main>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script>
// ============================================================
// DATA INJECTION POINT
// ============================================================
const REPORT_DATA = {};

// ============================================================
// XSS SAFETY
// ============================================================
function esc(str) {
  if (str == null) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

// Normalize keyword data: dict {"kw": {count, ...}} or {"kw": count} → array [{keyword, count, ...}]
function normalizeKws(kws) {
  if (!kws) return [];
  if (Array.isArray(kws)) return kws;
  return Object.entries(kws).map(([k, v]) =>
    typeof v === 'object' ? { keyword: k, ...v } : { keyword: k, count: v }
  );
}

function fmt(n, digits) {
  if (n == null || n === '') return '-';
  const num = parseFloat(n);
  if (isNaN(num)) return String(n);
  if (digits !== undefined) return num.toFixed(digits);
  return num.toLocaleString();
}

function fmtPrice(n) {
  if (n == null || n === '') return '-';
  const num = parseFloat(n);
  if (isNaN(num)) return '-';
  return '$' + num.toFixed(2);
}

function formatRankedIngredients(raw) {
  if (!raw) return '';
  const items = (typeof raw === 'string' ? raw.split(',') : Array.isArray(raw) ? raw.map(i => i.name || i) : []).map(s => s.trim()).filter(Boolean);
  const medals = ['🥇','🥈','🥉'];
  return items.map((name, i) => {
    const badge = i < 3 ? `<span style="margin-right:2px">${medals[i]}</span>` : `<span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:rgba(255,255,255,0.08);text-align:center;line-height:18px;font-size:10px;font-weight:700;color:var(--color-text-muted);margin-right:3px">${i+1}</span>`;
    return `<span style="display:inline-flex;align-items:center;padding:2px 8px 2px 4px;margin:2px;border-radius:12px;background:rgba(255,255,255,0.05);font-size:11px;white-space:nowrap">${badge}${esc(name)}</span>`;
  }).join('');
}

// ============================================================
// MARKDOWN RENDERER
// ============================================================
function renderMarkdown(text) {
  if (!text) return '<p class="empty-state">No market report available.</p>';
  const lines = text.split('\n');
  const result = [];
  let inUl = false, inOl = false;

  for (let line of lines) {
    if (/^#### (.+)/.test(line)) {
      closeLists(); result.push('<h4>' + line.replace(/^#### /, '') + '</h4>');
    } else if (/^### (.+)/.test(line)) {
      closeLists(); result.push('<h3>' + line.replace(/^### /, '') + '</h3>');
    } else if (/^## (.+)/.test(line)) {
      closeLists(); result.push('<H2>' + line.replace(/^## /, '') + '</H2>');
    } else if (/^# (.+)/.test(line)) {
      closeLists(); result.push('<h1>' + applyInline(line.replace(/^# /, '')) + '</h1>');
    } else if (/^---$/.test(line.trim())) {
      closeLists(); result.push('<hr>');
    } else if (/^\s*[\-\*] (.+)/.test(line)) {
      const depth = line.search(/\S/);
      if (!inUl) { result.push('<ul>'); inUl = true; }
      const indent = depth > 0 ? ` style="margin-left:${depth * 10}px"` : '';
      result.push('<li' + indent + '>' + applyInline(line.replace(/^\s*[\-\*] /, '')) + '</li>');
    } else if (/^\s*\d+\.\s+(.+)/.test(line)) {
      const depth = line.search(/\S/);
      if (!inOl) { result.push('<ol>'); inOl = true; }
      const olIndent = depth > 0 ? ` style="margin-left:${depth * 10}px"` : '';
      result.push('<li' + olIndent + '>' + applyInline(line.replace(/^\s*\d+\.\s+/, '')) + '</li>');
    } else if (line.trim() === '') {
      closeLists();
    } else {
      closeLists();
      result.push('<p>' + applyInline(line) + '</p>');
    }
  }
  closeLists();
  return result.join('\n');

  function closeLists() {
    if (inUl) { result.push('</ul>'); inUl = false; }
    if (inOl) { result.push('</ol>'); inOl = false; }
  }

  function applyInline(s) {
    return s
      .replace(/`(.+?)`/g, '<code style="background:var(--color-surface-2);padding:1px 5px;border-radius:3px;font-size:0.9em">$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>');
  }
}

function markdownToSections(text) {
  if (!text) return '<p class="empty-state">No market report available.</p>';
  const lines = text.split('\n');
  const sections = [];
  let currentTitle = null;
  let currentLines = [];

  for (const line of lines) {
    if (/^## (.+)/.test(line)) {
      if (currentTitle !== null) {
        sections.push({ title: currentTitle, body: currentLines.join('\n') });
      }
      currentTitle = line.replace(/^## /, '').trim();
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }
  if (currentTitle !== null) {
    sections.push({ title: currentTitle, body: currentLines.join('\n') });
  }

  if (sections.length === 0) {
    return '<div class="markdown-body">' + renderMarkdown(text) + '</div>';
  }

  return sections.map(s =>
    `<details class="markdown-section" open>
      <summary>${esc(s.title)}</summary>
      <div class="markdown-section-body markdown-body">${renderMarkdown(s.body)}</div>
    </details>`
  ).join('\n');
}

// ============================================================
// TABLE CONTROLLER
// ============================================================
class TableController {
  constructor({ data, columns, container, pageSize = 100, searchInput = null, filterInput = null }) {
    this.allData = data;
    this.filtered = [...data];
    this.columns = columns;
    this.container = container;
    this.pageSize = pageSize;
    this.currentPage = 1;
    this.sortCol = -1;
    this.sortDir = 'desc';
    this.searchQuery = '';
    this.filterQuery = '';
    this._searchInput = searchInput;
    this._filterInput = filterInput;

    if (searchInput) {
      let timer;
      searchInput.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => { this.searchQuery = searchInput.value.toLowerCase(); this._applyFilters(); }, 300);
      });
    }
    if (filterInput) {
      filterInput.addEventListener('change', () => { this.filterQuery = filterInput.value.toLowerCase(); this._applyFilters(); });
    }
  }

  _applyFilters() {
    this.filtered = this.allData.filter(row => {
      const matchSearch = !this.searchQuery || this.columns.some(c => {
        const val = typeof c.value === 'function' ? c.value(row) : row[c.key];
        return String(val || '').toLowerCase().includes(this.searchQuery);
      });
      const matchFilter = !this.filterQuery || (() => {
        const fc = this.columns.find(c => c.filterKey);
        if (!fc) return true;
        const val = typeof fc.value === 'function' ? fc.value(row) : row[fc.filterKey || fc.key];
        return String(val || '').toLowerCase().includes(this.filterQuery);
      })();
      return matchSearch && matchFilter;
    });
    if (this.sortCol >= 0) this._sort();
    this.currentPage = 1;
    this._render();
  }

  _sort() {
    const col = this.columns[this.sortCol];
    this.filtered.sort((a, b) => {
      let va = typeof col.value === 'function' ? col.value(a) : a[col.key];
      let vb = typeof col.value === 'function' ? col.value(b) : b[col.key];
      va = (va == null || va === '-') ? (this.sortDir === 'asc' ? Infinity : -Infinity) : parseFloat(va) || va;
      vb = (vb == null || vb === '-') ? (this.sortDir === 'asc' ? Infinity : -Infinity) : parseFloat(vb) || vb;
      if (va < vb) return this.sortDir === 'asc' ? -1 : 1;
      if (va > vb) return this.sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  setSort(colIndex) {
    if (this.sortCol === colIndex) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortCol = colIndex;
      this.sortDir = 'desc';
    }
    this._sort();
    this.currentPage = 1;
    this._render();
  }

  _render() {
    const start = (this.currentPage - 1) * this.pageSize;
    const pageData = this.filtered.slice(start, start + this.pageSize);
    const tbody = this.container.querySelector('tbody');
    tbody.innerHTML = pageData.map(row =>
      '<tr>' + this.columns.map(c => {
        const raw = typeof c.value === 'function' ? c.value(row) : row[c.key];
        const html = typeof c.render === 'function' ? c.render(raw, row) : esc(raw);
        const cls = c.className ? ` class="${c.className}"` : '';
        return `<td${cls}>${html}</td>`;
      }).join('') + '</tr>'
    ).join('');

    const pager = this.container.querySelector('.pagination');
    if (pager) {
      const total = this.filtered.length;
      const pages = Math.ceil(total / this.pageSize);
      if (pages <= 1) { pager.innerHTML = ''; return; }
      let html = '';
      html += `<span class="page-info">${start + 1}–${Math.min(start + this.pageSize, total)} / ${total}</span>`;
      html += `<button class="page-btn" onclick="this.closest('[data-tc]').__tc.goPage(${this.currentPage - 1})" ${this.currentPage === 1 ? 'disabled' : ''}>&lt;</button>`;
      const range = this._pageRange(this.currentPage, pages);
      for (const p of range) {
        if (p === '...') html += `<span class="page-info">...</span>`;
        else html += `<button class="page-btn ${p === this.currentPage ? 'active' : ''}" onclick="this.closest('[data-tc]').__tc.goPage(${p})">${p}</button>`;
      }
      html += `<button class="page-btn" onclick="this.closest('[data-tc]').__tc.goPage(${this.currentPage + 1})" ${this.currentPage === pages ? 'disabled' : ''}>&gt;</button>`;
      pager.innerHTML = html;
    }

    const ths = this.container.querySelectorAll('thead th');
    ths.forEach((th, i) => {
      th.classList.remove('sorted');
      const icon = th.querySelector('.sort-icon');
      if (icon) icon.textContent = '\u2195';
      if (i === this.sortCol) {
        th.classList.add('sorted');
        if (icon) icon.textContent = this.sortDir === 'asc' ? '\u2191' : '\u2193';
      }
    });
  }

  _pageRange(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [];
    if (current > 3) { pages.push(1); if (current > 4) pages.push('...'); }
    for (let i = Math.max(1, current - 2); i <= Math.min(total, current + 2); i++) pages.push(i);
    if (current < total - 2) { if (current < total - 3) pages.push('...'); pages.push(total); }
    return pages;
  }

  goPage(p) {
    const pages = Math.ceil(this.filtered.length / this.pageSize);
    if (p < 1 || p > pages) return;
    this.currentPage = p;
    this._render();
  }

  init() {
    this.container.setAttribute('data-tc', '1');
    this.container.__tc = this;
    const ths = this.container.querySelectorAll('thead th');
    ths.forEach((th, i) => {
      if (this.columns[i] && this.columns[i].sortable !== false) {
        th.addEventListener('click', () => this.setSort(i));
      }
    });
    this._render();
  }
}

// ============================================================
// SECTION: MARKET INSIGHT
// ============================================================
function renderMarketInsight(data) {
  const el = document.getElementById('market-insight');
  if (!el) return;
  el.querySelector('.section-body').innerHTML = markdownToSections(data.market_report);
}

// ============================================================
// SECTION: CONSUMER VOICE
// ============================================================
function renderConsumerVoice(data) {
  const el = document.getElementById('consumer-voice');
  if (!el) return;
  const cv = data.analysis && data.analysis.customer_voice;
  if (!cv) { el.style.display = 'none'; return; }

  const posKws = normalizeKws(cv.positive_keywords);
  const negKws = normalizeKws(cv.negative_keywords);
  const maxPos = posKws.length ? Math.max(...posKws.map(k => k.count || 0)) : 1;
  const maxNeg = negKws.length ? Math.max(...negKws.map(k => k.count || 0)) : 1;

  const posEl = el.querySelector('#cv-positive-bars');
  const negEl = el.querySelector('#cv-negative-bars');

  if (posEl) {
    posEl.innerHTML = posKws.slice(0, 15).map(k =>
      `<div class="kw-bar-row">
        <div class="kw-bar-label">${esc(k.keyword || k.word || k.term || '')}</div>
        <div class="kw-bar-track"><div class="kw-bar-fill" style="width:${Math.round((k.count||0)/maxPos*100)}%;background:var(--color-positive)"></div></div>
        <div class="kw-bar-count">${k.count||0}</div>
      </div>`
    ).join('');
  }

  if (negEl) {
    negEl.innerHTML = negKws.slice(0, 15).map(k =>
      `<div class="kw-bar-row">
        <div class="kw-bar-label">${esc(k.keyword || k.word || k.term || '')}</div>
        <div class="kw-bar-track"><div class="kw-bar-fill" style="width:${Math.round((k.count||0)/maxNeg*100)}%;background:var(--color-negative)"></div></div>
        <div class="kw-bar-count">${k.count||0}</div>
      </div>`
    ).join('');
  }

  // BSR Correlation chart — only for category type
  const bsrSubsection = el.querySelector('#cv-bsr-subsection');
  if (bsrSubsection) {
    if (data.report_type === 'keyword') {
      bsrSubsection.style.display = 'none';
    } else {
      const topKws = normalizeKws(cv.bsr_top_half_keywords || cv.bsr_top_half_positive);
      const botKws = normalizeKws(cv.bsr_bottom_half_keywords || cv.bsr_bottom_half_positive);
      const allKws = [...new Set([...topKws.map(k => k.keyword), ...botKws.map(k => k.keyword)])].slice(0, 10);
      const topMap = Object.fromEntries(topKws.map(k => [k.keyword, k.count || 0]));
      const botMap = Object.fromEntries(botKws.map(k => [k.keyword, k.count || 0]));
      const ctx = el.querySelector('#bsr-correlation-chart');
      if (ctx && allKws.length) {
        new Chart(ctx, {
          type: 'bar',
          data: {
            labels: allKws,
            datasets: [
              { label: 'BSR Top Half', data: allKws.map(k => topMap[k] || 0), backgroundColor: 'rgba(34,197,94,0.7)' },
              { label: 'BSR Bottom Half', data: allKws.map(k => botMap[k] || 0), backgroundColor: 'rgba(239,68,68,0.6)' },
            ]
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#8B92A5', font: { size: 11 } } } },
            scales: {
              x: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
              y: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
            }
          }
        });
      }
    }
  }
}

// ============================================================
// SECTION: BADGE ANALYSIS
// ============================================================
function renderBadgeAnalysis(data) {
  const el = document.getElementById('badge-analysis');
  if (!el) return;
  if (data.report_type === 'keyword') { el.style.display = 'none'; return; }
  const bd = data.analysis && data.analysis.badges;
  if (!bd) { el.style.display = 'none'; return; }

  const wb = bd.with_badge || {};
  const nb = bd.without_badge || {};
  const threshold = bd.acquisition_threshold || {};
  const statTest = bd.stat_test_bsr || {};
  const rawBt = bd.badge_types || [];
  // Normalize: array of {badge,count} → dict {badge: count}
  const badgeTypes = Array.isArray(rawBt)
    ? Object.fromEntries(rawBt.map(b => [b.badge || b.type || '', b.count || 0]))
    : rawBt;

  const withBadgeEl = el.querySelector('#badge-with');
  if (withBadgeEl) {
    withBadgeEl.innerHTML = `
      <div class="kpi-label">With Badge</div>
      <div class="kpi-value">${fmt(wb.count)}</div>
      <div class="kpi-sub">products</div>
      <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div><div class="kpi-label" style="font-size:10px">Avg BSR</div><div style="font-size:18px;font-weight:700;color:#C084FC">${fmt(wb.avg_bsr)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Price</div><div style="font-size:18px;font-weight:700;color:#C084FC">${fmtPrice(wb.avg_price)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Rating</div><div style="font-size:18px;font-weight:700;color:#C084FC">${fmt(wb.avg_rating,1)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Reviews</div><div style="font-size:18px;font-weight:700;color:#C084FC">${fmt(wb.avg_reviews)}</div></div>
      </div>`;
  }

  const noBadgeEl = el.querySelector('#badge-without');
  if (noBadgeEl) {
    noBadgeEl.innerHTML = `
      <div class="kpi-label">Without Badge</div>
      <div class="kpi-value" style="color:var(--color-text-secondary)">${fmt(nb.count)}</div>
      <div class="kpi-sub">products</div>
      <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div><div class="kpi-label" style="font-size:10px">Avg BSR</div><div style="font-size:18px;font-weight:700">${fmt(nb.avg_bsr)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Price</div><div style="font-size:18px;font-weight:700">${fmtPrice(nb.avg_price)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Rating</div><div style="font-size:18px;font-weight:700">${fmt(nb.avg_rating,1)}</div></div>
        <div><div class="kpi-label" style="font-size:10px">Avg Reviews</div><div style="font-size:18px;font-weight:700">${fmt(nb.avg_reviews)}</div></div>
      </div>`;
  }

  const threshEl = el.querySelector('#badge-threshold');
  if (threshEl && Object.keys(threshold).length) {
    threshEl.innerHTML = Object.entries(threshold).map(([k, v]) =>
      `<div class="stat-box"><span class="stat-box-label">${esc(k.replace(/_/g,' '))}</span><span class="stat-box-value">${esc(v)}</span></div>`
    ).join('');
  }

  const statEl = el.querySelector('#badge-stat');
  if (statEl) {
    const pval = statTest.p_value;
    const sig = pval != null && pval < 0.05;
    statEl.innerHTML = `
      <div style="font-size:11px;color:var(--color-text-muted);margin-bottom:6px">STATISTICAL TEST (Mann-Whitney U)</div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        ${pval != null ? `<span style="font-size:13px;color:var(--color-text-secondary)">p-value: <strong style="color:var(--color-text-primary)">${pval}</strong></span>` : ''}
        <span class="sig-tag ${sig ? 'yes' : 'no'}">${sig ? '\u2713 Significant (p < 0.05)' : 'Not significant'}</span>
      </div>
      ${statTest.note ? `<div style="font-size:12px;color:var(--color-text-muted);margin-top:6px">${esc(statTest.note)}</div>` : ''}`;
  }

  const ctx = el.querySelector('#badge-donut-chart');
  if (ctx && Object.keys(badgeTypes).length) {
    const labels = Object.keys(badgeTypes);
    const values = labels.map(k => badgeTypes[k]);
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data: values, backgroundColor: ['#C084FC','#FBBF24','#818CF8','#34D399','#F87171'], borderWidth: 0 }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#8B92A5', font: { size: 11 }, padding: 12 } }
        }
      }
    });

    const listEl = el.querySelector('#badge-type-list');
    if (listEl) {
      listEl.innerHTML = labels.map(k =>
        `<div class="stat-box"><span class="stat-box-label">${esc(k)}</span><span class="stat-box-value">${esc(badgeTypes[k])}</span></div>`
      ).join('');
    }
  }
}

// ============================================================
// SECTION: SALES & PRICING
// ============================================================
function renderSalesPricing(data) {
  const el = document.getElementById('sales-pricing');
  if (!el) return;
  const sv = data.analysis && data.analysis.sales_volume;
  const sns = data.analysis && data.analysis.sns_pricing;
  const disc = data.analysis && data.analysis.discount_impact;
  const promo = data.analysis && data.analysis.promotions;
  if (!sv && !sns && !disc) { el.style.display = 'none'; return; }

  // Top Sellers table
  const tsEl = el.querySelector('#top-sellers-tbody');
  if (tsEl && sv && sv.top_sellers) {
    tsEl.innerHTML = sv.top_sellers.map(p =>
      `<tr>
        <td class="mono">${esc(p.asin)}</td>
        <td>${esc(p.brand)}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.title)}</td>
        <td><strong>${p.bought_past_month != null ? fmt(p.bought_past_month)+'+' : '-'}</strong></td>
        <td>${fmtPrice(p.price)}</td>
        <td>${fmt(p.bsr_category || p.bsr)}</td>
      </tr>`
    ).join('');
  }

  // Price tier chart
  const ptCtx = el.querySelector('#price-tier-chart');
  const rawPriceTiers = sv && (sv.price_tiers || sv.sales_by_price_tier);
  if (ptCtx && rawPriceTiers) {
    const tiers = rawPriceTiers;
    const labels = Object.keys(tiers);
    new Chart(ptCtx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ label: 'Products', data: labels.map(k => tiers[k].count || tiers[k]), backgroundColor: 'rgba(0,150,136,0.7)', borderRadius: 4 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
          y: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } }
        }
      }
    });
  }

  // SNS stats
  const snsEl = el.querySelector('#sns-stats');
  if (snsEl && sns) {
    // Field names: sns_adoption_pct (0-100), avg_discount_pct (0-100), retention_signal.sns_avg_bought
    const adoptPct = sns.sns_adoption_pct != null ? sns.sns_adoption_pct : (sns.adoption_rate != null ? sns.adoption_rate * 100 : null);
    const discPct = sns.avg_discount_pct != null ? sns.avg_discount_pct : (sns.avg_discount != null ? sns.avg_discount * 100 : null);
    const ret = sns.retention_signal || {};
    const items = [
      ['SNS Adoption Rate', adoptPct != null ? Math.round(adoptPct) + '%' : '-'],
      ['Avg SNS Discount', discPct != null ? discPct.toFixed(1) + '%' : '-'],
      ['SNS Avg Bought/Mo', ret.sns_avg_bought || sns.sns_avg_bought],
      ['No-SNS Avg Bought/Mo', ret.no_sns_avg_bought || sns.no_sns_avg_bought],
      ['With SNS Count', sns.with_sns_count],
      ['Without SNS Count', sns.without_sns_count],
    ];
    const adoptEl = snsEl.querySelector('#sns-adoption-value');
    if (adoptEl) adoptEl.textContent = adoptPct != null ? Math.round(adoptPct) + '%' : '-';
    const listEl = snsEl.querySelector('#sns-stat-list');
    if (listEl) {
      listEl.innerHTML = items.slice(1).map(([label, val]) =>
        `<div class="stat-box"><span class="stat-box-label">${esc(label)}</span><span class="stat-box-value"${label.includes('SNS Avg') ? ' style="color:#22C55E"' : ''}>${esc(val)}</span></div>`
      ).join('');
    }
  }

  // Discount impact chart
  const discCtx = el.querySelector('#discount-chart');
  if (discCtx && disc && disc.tiers) {
    // Normalize: dict {"tier_name": {avg_bsr, ...}} or array [{tier, avg_bsr, ...}]
    const rawTiers = disc.tiers;
    const tiers = Array.isArray(rawTiers)
      ? rawTiers
      : Object.entries(rawTiers).map(([k, v]) => ({ tier: k, ...v }));
    const labels = tiers.map(t => t.tier || t.label || '');
    new Chart(discCtx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Avg BSR', data: tiers.map(t => t.avg_bsr || 0), backgroundColor: 'rgba(0,150,136,0.7)', borderRadius: 3 },
          { label: 'Avg Bought/Mo', data: tiers.map(t => t.avg_bought || 0), backgroundColor: 'rgba(100,116,139,0.6)', borderRadius: 3 },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8B92A5', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
          y: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } }
        }
      }
    });
  }

  // Coupon distribution
  const couponEl = el.querySelector('#coupon-tbody');
  const rawCoupons = promo && (promo.coupon_distribution || promo.coupon_types);
  if (couponEl && rawCoupons) {
    // Normalize: array [{coupon, count}] or dict {type: count}
    const couponRows = Array.isArray(rawCoupons)
      ? rawCoupons.map(c => [c.coupon || c.type || '', c.count || 0])
      : Object.entries(rawCoupons);
    couponEl.innerHTML = couponRows.map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`
    ).join('');
  }
}

// ============================================================
// SECTION: BRAND POSITIONING
// ============================================================
function renderBrandPositioning(data) {
  const el = document.getElementById('brand-positioning');
  if (!el) return;
  const rawBp = data.analysis && data.analysis.brand_positioning;
  const mfr = data.analysis && data.analysis.manufacturer;
  if (!rawBp) { el.style.display = 'none'; return; }
  // brand_positioning can be array directly or {positioning: [...]}
  const bp = { positioning: Array.isArray(rawBp) ? rawBp : (rawBp.positioning || []) };

  function segmentBadge(seg) {
    if (!seg) return '';
    const cls = { budget: 'badge-budget', mid: 'badge-mid', premium: 'badge-premium', luxury: 'badge-luxury' };
    const key = seg.toLowerCase();
    const c = Object.keys(cls).find(k => key.includes(k)) || 'badge-mid';
    return `<span class="badge ${cls[c]}">${esc(seg)}</span>`;
  }

  // Scatter chart: Price vs BSR
  const scatterCtx = el.querySelector('#brand-scatter-chart');
  if (scatterCtx && bp.positioning) {
    const segColors = { budget: '#94A3B8', mid: '#60A5FA', premium: '#C084FC', luxury: '#FBBF24' };
    const scatterData = bp.positioning.filter(b => b.avg_price && b.avg_bsr).map(b => ({
      x: b.avg_price, y: b.avg_bsr, label: b.brand,
      r: Math.min(Math.max((b.product_count || 1) * 2, 4), 18),
      seg: (b.segment || 'mid').toLowerCase(),
    }));
    const datasets = Object.entries(segColors).map(([seg, color]) => ({
      label: seg.charAt(0).toUpperCase() + seg.slice(1),
      data: scatterData.filter(d => d.seg.includes(seg)).map(d => ({ x: d.x, y: d.y, r: d.r })),
      backgroundColor: color + '99',
      borderColor: color,
      borderWidth: 1,
      pointLabels: scatterData.filter(d => d.seg.includes(seg)).map(d => d.label),
      pointCounts: scatterData.filter(d => d.seg.includes(seg)).map(d => Math.round(d.r / 2)),
    }));
    const scatterChart = new Chart(scatterCtx, {
      type: 'bubble',
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: { title: { display: true, text: 'Avg Price ($)', color: '#8B92A5' }, grid: { color: '#2A2D3E' }, ticks: { color: '#8B92A5' } },
          y: { title: { display: true, text: 'Avg BSR (lower = better)', color: '#8B92A5' }, reverse: true, grid: { color: '#2A2D3E' }, ticks: { color: '#8B92A5' } },
        },
        plugins: {
          legend: { position: 'bottom', labels: { color: '#8B92A5', font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                const ds = ctx.dataset;
                const lbl = ds.pointLabels && ds.pointLabels[ctx.dataIndex] || '';
                const cnt = ds.pointCounts && ds.pointCounts[ctx.dataIndex] || '';
                return `${lbl} (${cnt}ea): $${ctx.parsed.x.toFixed(0)} / BSR ${ctx.parsed.y.toLocaleString()}`;
              }
            }
          }
        }
      }
    });
  }

  const brandTbody = el.querySelector('#brand-tbody');
  if (brandTbody && bp.positioning) {
    brandTbody.innerHTML = bp.positioning.map(b =>
      `<tr>
        <td>${esc(b.brand)}</td>
        <td>${fmt(b.product_count)}</td>
        <td>${fmtPrice(b.avg_price)}</td>
        <td>${fmt(b.avg_bsr)}</td>
        <td>${fmt(b.avg_rating,1)}</td>
        <td>${segmentBadge(b.segment)}</td>
      </tr>`
    ).join('');
  }

  const mc = (mfr && mfr.market_concentration) || bp.market_concentration || {};
  const mcStatsEl = el.querySelector('#mc-stats');
  if (mcStatsEl) {
    mcStatsEl.innerHTML = [
      ['Total Brands', mc.total_brands],
      ['Top 10 Market Share', mc.top10_share_pct != null ? Math.round(mc.top10_share_pct) + '%' : (mc.top10_share != null ? Math.round(mc.top10_share * 100) + '%' : null)],
      ['K-Beauty Brands', mc.kbeauty_count != null ? `<span class="badge badge-kbeauty">${mc.kbeauty_count}</span>` : null],
    ].filter(([,v]) => v != null).map(([l, v]) =>
      `<div class="stat-box"><span class="stat-box-label">${esc(l)}</span><span class="stat-box-value">${typeof v === 'string' && v.startsWith('<') ? v : esc(v)}</span></div>`
    ).join('');
  }

  const concCtx = el.querySelector('#concentration-chart');
  const mcShare = mc.top10_share_pct != null ? mc.top10_share_pct : (mc.top10_share != null ? mc.top10_share * 100 : null);
  if (concCtx && mcShare != null) {
    const top10 = Math.round(mcShare > 1 ? mcShare : mcShare * 100);
    new Chart(concCtx, {
      type: 'doughnut',
      data: {
        labels: ['Top 10 Brands', 'Others'],
        datasets: [{ data: [top10, 100 - top10], backgroundColor: ['#818CF8','rgba(100,116,139,0.4)'], borderWidth: 0 }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#8B92A5', font: { size: 11 } } }
        }
      }
    });
  }

  const mfrTbody = el.querySelector('#manufacturer-tbody');
  if (mfrTbody && mfr && mfr.top_manufacturers) {
    mfrTbody.innerHTML = mfr.top_manufacturers.map(m =>
      `<tr>
        <td>${esc(m.manufacturer)}</td>
        <td>${fmt(m.product_count)}</td>
        <td>${fmt(m.avg_bsr)}</td>
        <td>${m.is_kbeauty ? '<span class="badge badge-kbeauty">K-Beauty</span>' : '-'}</td>
      </tr>`
    ).join('');
  }
}

// ============================================================
// SECTION: MARKETING KEYWORDS
// ============================================================
function renderMarketingKeywords(data) {
  const el = document.getElementById('marketing-keywords');
  if (!el) return;
  const tk = data.analysis && data.analysis.title_keywords;
  const pta = data.analysis && data.analysis.price_tier_analysis;
  if (!tk && !pta) { el.style.display = 'none'; return; }

  const kwCtx = el.querySelector('#keywords-chart');
  if (kwCtx && tk && tk.keyword_analysis) {
    // Normalize: dict {"kw": {count, avg_bsr, ...}} or array [{keyword, count, ...}]
    const rawKws = tk.keyword_analysis;
    const kwArr = Array.isArray(rawKws)
      ? rawKws
      : Object.entries(rawKws).map(([k, v]) => ({ keyword: k, ...v }));
    const kws = kwArr.slice(0, 20).sort((a, b) => (a.avg_bsr || 0) - (b.avg_bsr || 0));
    kwCtx.parentElement.style.height = Math.max(320, kws.length * 28) + 'px';
    new Chart(kwCtx, {
      type: 'bar',
      data: {
        labels: kws.map(k => k.keyword || k.word || ''),
        datasets: [{ label: 'Avg BSR', data: kws.map(k => k.avg_bsr || 0), backgroundColor: 'rgba(121,85,72,0.7)', borderRadius: 3 }]
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
          y: { ticks: { color: '#8B92A5', font: { size: 11 }, autoSkip: false }, grid: { color: '#2A2D3E' } }
        }
      }
    });
  }

  const ptiTbody = el.querySelector('#price-tier-ing-tbody');
  if (ptiTbody && pta) {
    const tiers = Array.isArray(pta) ? pta : (pta.tiers || Object.entries(pta).map(([k, v]) => ({ tier: k, ...v })));
    const badges = { budget: 'badge-budget', mid: 'badge-mid', premium: 'badge-premium', luxury: 'badge-luxury' };
    ptiTbody.innerHTML = tiers.map(t => {
      const tierKey = Object.keys(badges).find(k => String(t.tier || '').toLowerCase().includes(k)) || 'mid';
      return `<tr>
        <td><span class="badge ${badges[tierKey]}">${esc(t.tier)}</span></td>
        <td>${fmt(t.product_count || t.count)}</td>
        <td class="muted">${esc(Array.isArray(t.top_ingredients) ? t.top_ingredients.map(i => i.name || i).join(', ') : (t.top_ingredients || ''))}</td>
      </tr>`;
    }).join('');
  }
}

// ============================================================
// SECTION: INGREDIENT RANKING
// ============================================================
function renderIngredientRanking(data) {
  const el = document.getElementById('ingredient-ranking');
  if (!el) return;
  if (!data.rankings || !data.rankings.length) { el.style.display = 'none'; return; }

  const top5 = data.rankings.slice(0, 5);
  const heroEl = el.querySelector('#ingredient-hero');
  if (heroEl) {
    heroEl.innerHTML = top5.map((r, i) => {
      const rankClass = i < 3 ? ` rank-${i+1}` : '';
      return `<div class="rank-card${rankClass}">
        <div class="rank-number">#${r.rank || i+1}</div>
        <div class="rank-name">${esc(r.ingredient)}</div>
        <div class="rank-score">${fmt(r.weighted_score,1)}</div>
        <div class="rank-score-label">weighted score</div>
        <div class="rank-count">${fmt(r.product_count)} products</div>
        ${r.category ? `<div style="margin-top:8px"><span class="badge badge-mid">${esc(r.category)}</span></div>` : ''}
        ${r.key_insight ? `<div style="font-size:11px;color:var(--color-text-muted);margin-top:8px">${esc(r.key_insight)}</div>` : ''}
      </div>`;
    }).join('');
  }

  const categories = [...new Set(data.rankings.map(r => r.category).filter(Boolean))];
  const catFilter = el.querySelector('#cat-filter');
  if (catFilter) {
    catFilter.innerHTML = '<option value="">All categories</option>' +
      categories.map(c => `<option>${esc(c)}</option>`).join('');
  }

  const tableEl = el.querySelector('#ingredient-table-wrap');
  if (tableEl) {
    const searchInput = el.querySelector('#ing-search');
    const tc = new TableController({
      data: data.rankings,
      pageSize: 100,
      columns: [
        { key: 'rank', header: 'Rank', sortable: true },
        { key: 'ingredient', header: 'Ingredient', render: (v) => `<strong>${esc(v)}</strong>` },
        { key: 'weighted_score', header: 'Weighted Score', render: (v) => fmt(v, 3) },
        { key: 'product_count', header: '# Products' },
        { key: 'avg_weight', header: 'Avg Weight', render: (v) => fmt(v, 3) },
        { key: 'category', header: 'Category', filterKey: 'category', render: (v) => v ? `<span class="badge badge-mid">${esc(v)}</span>` : '' },
        { key: 'avg_price', header: 'Avg Price', render: (v) => fmtPrice(v) },
        { key: 'key_insight', header: 'Key Insight', className: 'muted', sortable: false },
      ],
      container: tableEl,
      searchInput: searchInput,
    });

    if (catFilter) {
      catFilter.addEventListener('change', () => {
        tc.filterQuery = catFilter.value.toLowerCase();
        const savedFilter = tc._filterInput;
        tc._filterInput = null;
        tc.columns[5].filterKey = 'category';
        tc.filtered = tc.allData.filter(row => {
          const matchSearch = !tc.searchQuery || tc.columns.some(c => {
            const val = row[c.key];
            return String(val || '').toLowerCase().includes(tc.searchQuery);
          });
          const matchFilter = !tc.filterQuery || String(row.category || '').toLowerCase().includes(tc.filterQuery);
          return matchSearch && matchFilter;
        });
        if (tc.sortCol >= 0) tc._sort();
        tc.currentPage = 1;
        tc._render();
        tc._filterInput = savedFilter;
      });
    }

    tc.init();
  }
}

// ============================================================
// SECTION: CATEGORY SUMMARY
// ============================================================
function renderCategorySummary(data) {
  const el = document.getElementById('category-summary');
  if (!el) return;
  if (!data.categories || !data.categories.length) { el.style.display = 'none'; return; }

  const sorted = [...data.categories].sort((a, b) => (b.total_weighted_score || 0) - (a.total_weighted_score || 0));

  const ctx = el.querySelector('#category-chart');
  if (ctx) {
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map(c => c.category),
        datasets: [{ label: 'Total Weighted Score', data: sorted.map(c => c.total_weighted_score), backgroundColor: 'rgba(46,134,171,0.7)', borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } },
          y: { ticks: { color: '#8B92A5' }, grid: { color: '#2A2D3E' } }
        }
      }
    });
  }

  const tbody = el.querySelector('#category-tbody');
  if (tbody) {
    tbody.innerHTML = sorted.map(c =>
      `<tr>
        <td><strong>${esc(c.category)}</strong></td>
        <td>${fmt(c.total_weighted_score,2)}</td>
        <td>${fmt(c.type_count)}</td>
        <td>${fmt(c.mention_count)}</td>
        <td>${fmtPrice(c.avg_price)}</td>
        <td>${formatRankedIngredients(c.top_ingredients)}</td>
      </tr>`
    ).join('');
  }
}

// ============================================================
// SECTION: RISING PRODUCTS
// ============================================================
function renderRisingProducts(data) {
  const el = document.getElementById('rising-products');
  if (!el) return;
  if (data.report_type === 'keyword') { el.style.display = 'none'; return; }
  if (!data.rising_products || !data.rising_products.length) { el.style.display = 'none'; return; }

  const container = el.querySelector('#rising-grid');
  if (container) {
    container.innerHTML = data.rising_products.map(p =>
      `<div class="rising-card">
        <div class="rising-bsr">BSR: ${fmt(p.bsr || p.bsr_category)}</div>
        <div class="rising-brand">${esc(p.brand || '')}</div>
        <div class="rising-title">${esc(p.title || '')}</div>
        <div class="rising-metrics">
          <span>${fmtPrice(p.price)}</span>
          ${p.rating ? `<span>&#9733;${fmt(p.rating,1)}</span>` : ''}
          ${p.reviews != null ? `<span>${fmt(p.reviews)}r</span>` : ''}
        </div>
        ${p.top_ingredients ? `<div class="rising-ingredients">Ingredients: ${esc(Array.isArray(p.top_ingredients) ? p.top_ingredients.join(', ') : p.top_ingredients)}</div>` : ''}
      </div>`
    ).join('');
  }
}

// ============================================================
// SECTION: PRODUCT DETAIL
// ============================================================
function renderProductDetail(data) {
  const el = document.getElementById('product-detail');
  if (!el) return;
  if (!data.products || !data.products.length) { el.style.display = 'none'; return; }

  const searchInput = el.querySelector('#pd-search');
  const tableEl = el.querySelector('#product-detail-table-wrap');

  const tc = new TableController({
    data: data.products,
    pageSize: 25,
    columns: [
      { key: 'asin', header: 'ASIN', className: 'mono' },
      { key: 'brand', header: 'Brand' },
      { key: 'title', header: 'Title', render: (v) => `<span style="max-width:220px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:help" title="${esc(v)}">${esc(v)}</span>`, sortable: false },
      { key: 'price', header: 'Price', render: (v) => fmtPrice(v) },
      { key: 'customer_says', header: 'Customer Says', sortable: false, render: (v) => { if (!v) return ''; let clean = v.replace(/Customers?\s*find\s*(this)?\s*:?\s*/gi, '').trim(); if (clean) clean = clean[0].toUpperCase() + clean.slice(1); return `<span style="max-width:200px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:help" title="${esc(clean)}">${esc(clean)}</span>`; } },
      { key: 'sns_price', header: 'SNS Price', render: (v) => fmtPrice(v) },
      { key: 'bought_past_month', header: 'Bought/Mo', render: (v) => v != null ? fmt(v) : '-' },
      { key: 'reviews', header: 'Reviews', render: (v) => fmt(v) },
      { key: 'rating', header: 'Rating', render: (v) => fmt(v,1) },
      { key: 'bsr_category', header: 'BSR', render: (v) => fmt(v) },
      { key: 'composite_weight', header: 'Weight', render: (v) => fmt(v,3) },
      { key: 'unit_price', header: 'Unit Price' },
      { key: 'coupon', header: 'Coupon' },
      { key: 'badge', header: 'Badge' },
      { key: 'plus_content', header: 'A+', render: (v) => v ? '<span class="badge badge-positive">Yes</span>' : '' },
      { key: 'variations_count', header: 'Vars', render: (v) => fmt(v) },
    ],
    container: tableEl,
    searchInput: searchInput,
  });
  tc.init();
}

// ============================================================
// SECTION: RAW SEARCH
// ============================================================
function renderRawSearch(data) {
  const el = document.getElementById('raw-search');
  if (!el) return;
  if (!data.search_products || !data.search_products.length) { el.style.display = 'none'; return; }

  const searchInput = el.querySelector('#rs-search');
  const tableEl = el.querySelector('#raw-search-table-wrap');

  const tc = new TableController({
    data: data.search_products,
    pageSize: 25,
    columns: [
      { key: 'position', header: '#' },
      { key: 'asin', header: 'ASIN', className: 'mono' },
      { key: 'title', header: 'Title', sortable: false, render: (v) => `<span style="max-width:320px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:help" title="${esc(v)}">${esc(v)}</span>` },
      { key: 'price_raw', header: 'Price' },
      { key: 'reviews', header: 'Reviews', render: (v) => fmt(v) },
      { key: 'rating', header: 'Rating', render: (v) => fmt(v,1) },
      { key: 'sponsored', header: 'Sponsored', render: (v) => v ? '<span class="badge badge-negative">Sponsored</span>' : '' },
      { key: 'bought_past_month', header: 'Bought/Mo', render: (v) => v != null ? fmt(v) : '-' },
    ],
    container: tableEl,
    searchInput: searchInput,
  });
  tc.init();
}

// ============================================================
// SECTION: RAW DETAIL
// ============================================================
function renderRawDetail(data) {
  const el = document.getElementById('raw-detail');
  if (!el) return;
  if (!data.details || !data.details.length) { el.style.display = 'none'; return; }

  const searchInput = el.querySelector('#rd-search');
  const tableEl = el.querySelector('#raw-detail-table-wrap');

  const tc = new TableController({
    data: data.details,
    pageSize: 25,
    columns: [
      { key: 'asin', header: 'ASIN', className: 'mono' },
      { key: 'brand', header: 'Brand' },
      { key: 'bsr_category', header: 'BSR', render: (v) => fmt(v) },
      { key: 'rating', header: 'Rating', render: (v) => fmt(v,1) },
      { key: 'review_count', header: 'Reviews', render: (v) => fmt(v) },
      { key: 'manufacturer', header: 'Manufacturer' },
      { key: 'ingredients_raw', header: 'Ingredients Raw', sortable: false, render: (v) => v ? `<span style="max-width:300px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(v)}">${esc(v)}</span>` : '' },
    ],
    container: tableEl,
    searchInput: searchInput,
  });
  tc.init();
}

// ============================================================
// SIDEBAR NAVIGATION
// ============================================================
function buildSidebar(data) {
  const SECTIONS = [
    { group: 'Story', items: [
      { id: 'market-insight',    label: 'Market Insight',     color: 'var(--color-market-insight)' },
      { id: 'consumer-voice',    label: 'Consumer Voice',     color: 'var(--color-consumer-voice)' },
      { id: 'badge-analysis',    label: 'Badge Analysis',     color: 'var(--color-badge-analysis)' },
    ]},
    { group: 'Analysis', items: [
      { id: 'sales-pricing',     label: 'Sales & Pricing',    color: 'var(--color-sales-pricing)' },
      { id: 'brand-positioning', label: 'Brand Positioning',  color: 'var(--color-brand-positioning)' },
      { id: 'marketing-keywords',label: 'Marketing Keywords', color: 'var(--color-marketing-kw)' },
      { id: 'ingredient-ranking',label: 'Ingredient Ranking', color: 'var(--color-ingredient-rank-light)' },
      { id: 'category-summary',  label: 'Category Summary',   color: 'var(--color-category-summary)' },
      { id: 'rising-products',   label: 'Rising Products',    color: 'var(--color-rising-products)' },
    ]},
    { group: 'Data', items: [
      { id: 'product-detail',    label: 'Product Detail',     color: 'var(--color-product-detail)' },
      { id: 'raw-search',        label: 'Raw - Search',       color: 'var(--color-raw-search)' },
      { id: 'raw-detail',        label: 'Raw - Detail',       color: 'var(--color-raw-detail)' },
    ]},
  ];

  const nav = document.getElementById('sidebar-nav');
  let html = '';
  for (const group of SECTIONS) {
    const visibleItems = group.items.filter(item => {
      const el = document.getElementById(item.id);
      return el && el.style.display !== 'none';
    });
    if (!visibleItems.length) continue;
    html += `<div class="nav-group-label">${esc(group.group)}</div>`;
    for (const item of visibleItems) {
      html += `<a class="nav-item" href="#${item.id}" data-color="${item.color}" data-section="${item.id}">
        <span class="nav-dot" style="border-color:${item.color}"></span>
        ${esc(item.label)}
      </a>`;
    }
  }
  nav.innerHTML = html;

  // Active nav on click
  nav.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', () => {
      nav.querySelectorAll('.nav-item').forEach(l => {
        l.classList.remove('active');
        l.style.borderLeftColor = 'transparent';
        const dot = l.querySelector('.nav-dot');
        if (dot) { dot.style.background = ''; dot.style.borderColor = l.dataset.color; }
      });
      link.classList.add('active');
      link.style.borderLeftColor = link.dataset.color;
      const dot = link.querySelector('.nav-dot');
      if (dot) { dot.style.background = link.dataset.color; dot.style.borderColor = ''; }
    });
  });

  // Intersection Observer
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        nav.querySelectorAll('.nav-item').forEach(link => {
          const active = link.dataset.section === id;
          link.classList.toggle('active', active);
          link.style.borderLeftColor = active ? link.dataset.color : 'transparent';
          const dot = link.querySelector('.nav-dot');
          if (dot) {
            dot.style.background = active ? link.dataset.color : '';
            dot.style.borderColor = active ? '' : link.dataset.color;
          }
        });
        break;
      }
    }
  }, { rootMargin: '-50% 0px -49% 0px', threshold: 0 });

  document.querySelectorAll('section.section').forEach(s => observer.observe(s));

  // Activate first visible
  const firstLink = nav.querySelector('.nav-item');
  if (firstLink) {
    firstLink.classList.add('active');
    firstLink.style.borderLeftColor = firstLink.dataset.color;
    const dot = firstLink.querySelector('.nav-dot');
    if (dot) { dot.style.background = firstLink.dataset.color; dot.style.borderColor = ''; }
  }
}

// ============================================================
// MAIN SECTIONS HTML BUILDER
// ============================================================
function buildSectionsHTML() {
  return `
  <!-- ==================== MARKET INSIGHT ==================== -->
  <section class="section" id="market-insight" style="--section-color:var(--color-market-insight)">
    <div class="section-header">
      <div>
        <div class="section-title">Market Insight</div>
        <div class="section-subtitle">AI-generated market analysis &middot; Powered by Gemini</div>
      </div>
    </div>
    <div class="markdown-body section-body"></div>
  </section>

  <!-- ==================== CONSUMER VOICE ==================== -->
  <section class="section" id="consumer-voice" style="--section-color:var(--color-consumer-voice)">
    <div class="section-header">
      <div>
        <div class="section-title">Consumer Voice</div>
        <div class="section-subtitle">Keyword frequency from Amazon AI review summaries</div>
      </div>
    </div>
    <div class="two-col">
      <div>
        <div class="subsection-title">Positive Keywords</div>
        <div id="cv-positive-bars"></div>
      </div>
      <div>
        <div class="subsection-title">Negative Keywords</div>
        <div id="cv-negative-bars"></div>
      </div>
    </div>
    <div class="subsection" id="cv-bsr-subsection">
      <div class="subsection-title">BSR Correlation &mdash; Top Half vs Bottom Half</div>
      <div class="chart-container" style="height:280px">
        <canvas id="bsr-correlation-chart"></canvas>
      </div>
    </div>
  </section>

  <!-- ==================== BADGE ANALYSIS ==================== -->
  <section class="section" id="badge-analysis" style="--section-color:var(--color-badge-analysis)">
    <div class="section-header">
      <div>
        <div class="section-title">Badge Analysis</div>
        <div class="section-subtitle">Amazon's Choice &amp; Best Seller impact on market performance</div>
      </div>
    </div>
    <div class="two-col-left-wide">
      <div>
        <div class="card-grid card-grid-2" style="margin-bottom:20px">
          <div class="kpi-card" id="badge-with" style="border-top:2px solid var(--color-badge-analysis)"></div>
          <div class="kpi-card" id="badge-without"></div>
        </div>
        <div class="subsection-title">Acquisition Threshold</div>
        <div id="badge-threshold" style="display:grid;gap:6px;margin-bottom:16px"></div>
        <div id="badge-stat" style="padding:14px 16px;background:var(--color-bg-card);border:1px solid var(--color-border);border-radius:var(--radius-md)"></div>
      </div>
      <div>
        <div class="subsection-title">Badge Type Distribution</div>
        <div class="chart-container" style="padding-top:12px">
          <canvas id="badge-donut-chart" height="200"></canvas>
        </div>
        <div id="badge-type-list" style="margin-top:12px;display:grid;gap:6px"></div>
      </div>
    </div>
  </section>

  <!-- ==================== SALES & PRICING ==================== -->
  <section class="section" id="sales-pricing" style="--section-color:var(--color-sales-pricing)">
    <div class="section-header">
      <div>
        <div class="section-title">Sales &amp; Pricing</div>
        <div class="section-subtitle">Revenue patterns, discount mechanics &amp; promotions analysis</div>
      </div>
    </div>
    <div class="subsection-title">Top Sellers by Monthly Volume</div>
    <div class="table-wrapper" style="margin-bottom:32px">
      <table>
        <thead><tr><th>ASIN</th><th>Brand</th><th>Title</th><th>Bought/Mo</th><th>Price</th><th>BSR</th></tr></thead>
        <tbody id="top-sellers-tbody"></tbody>
      </table>
    </div>
    <div class="subsection">
      <div class="subsection-title">Sales by Price Tier</div>
      <div class="chart-container" style="height:220px">
        <canvas id="price-tier-chart"></canvas>
      </div>
    </div>
    <div class="subsection">
      <div class="subsection-title">Discount Impact on BSR</div>
      <div class="chart-container" style="height:240px">
        <canvas id="discount-chart"></canvas>
      </div>
    </div>
    <div class="two-col" style="margin-top:40px">
      <div>
        <div class="subsection-title">Coupon Distribution</div>
        <div class="table-wrapper">
          <table>
            <thead><tr><th>Coupon Type</th><th>Count</th></tr></thead>
            <tbody id="coupon-tbody"></tbody>
          </table>
        </div>
      </div>
      <div id="sns-stats">
        <div class="subsection-title">Subscribe &amp; Save Adoption</div>
        <div style="display:grid;gap:8px">
          <div class="kpi-card" style="border-top:2px solid var(--color-sales-pricing)">
            <div class="kpi-label">SNS Adoption Rate</div>
            <div class="kpi-value" id="sns-adoption-value">-</div>
          </div>
          <div id="sns-stat-list" style="display:grid;gap:6px"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ==================== BRAND POSITIONING ==================== -->
  <section class="section" id="brand-positioning" style="--section-color:var(--color-brand-positioning)">
    <div class="section-header">
      <div>
        <div class="section-title">Brand Positioning</div>
        <div class="section-subtitle">Price vs BSR analysis &amp; competitive segmentation</div>
      </div>
    </div>
    <div class="subsection-title">Price vs BSR — Brand Scatter</div>
    <div class="chart-container" style="height:320px;margin-bottom:24px">
      <canvas id="brand-scatter-chart"></canvas>
    </div>
    <div class="two-col-left-wide">
      <div>
        <div class="subsection-title">Brand Performance</div>
        <div class="table-wrapper">
          <table>
            <thead><tr><th>Brand</th><th>Products</th><th>Avg Price</th><th>Avg BSR</th><th>Avg Rating</th><th>Segment</th></tr></thead>
            <tbody id="brand-tbody"></tbody>
          </table>
        </div>
        <div class="subsection">
          <div class="subsection-title">Top Manufacturers</div>
          <div class="table-wrapper">
            <table>
              <thead><tr><th>Manufacturer</th><th>Products</th><th>Avg BSR</th><th>K-Beauty</th></tr></thead>
              <tbody id="manufacturer-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
      <div>
        <div class="subsection-title">Market Concentration</div>
        <div class="chart-container">
          <canvas id="concentration-chart" height="180"></canvas>
        </div>
        <div id="mc-stats" style="margin-top:12px;display:grid;gap:6px"></div>
      </div>
    </div>
  </section>

  <!-- ==================== MARKETING KEYWORDS ==================== -->
  <section class="section" id="marketing-keywords" style="--section-color:var(--color-marketing-kw)">
    <div class="section-header">
      <div>
        <div class="section-title">Marketing Keywords</div>
        <div class="section-subtitle">Title keywords correlated with BSR performance</div>
      </div>
    </div>
    <div class="subsection-title">Keyword Performance (sorted by Avg BSR &mdash; lower is better)</div>
    <div class="chart-container" style="height:320px">
      <canvas id="keywords-chart"></canvas>
    </div>
    <div class="subsection">
      <div class="subsection-title">Price Tier Top Ingredients</div>
      <div class="table-wrapper">
        <table>
          <thead><tr><th>Price Tier</th><th>Products</th><th>Top Ingredients</th></tr></thead>
          <tbody id="price-tier-ing-tbody"></tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- ==================== INGREDIENT RANKING ==================== -->
  <section class="section" id="ingredient-ranking" style="--section-color:var(--color-ingredient-rank-light)">
    <div class="section-header">
      <div>
        <div class="section-title">Ingredient Ranking</div>
        <div class="section-subtitle">Weighted Score = Bought/Mo(30%) + BSR(25%) + Reviews(20%) + Position(15%) + Rating(10%)</div>
      </div>
    </div>
    <div class="card-grid card-grid-5" id="ingredient-hero" style="margin-bottom:32px"></div>
    <div class="toolbar">
      <input class="search-input" type="text" id="ing-search" placeholder="Search ingredient...">
      <select class="search-input" id="cat-filter" style="width:auto;cursor:pointer"><option value="">All categories</option></select>
    </div>
    <div data-tc="1" id="ingredient-table-wrap">
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Rank <span class="sort-icon">&#8597;</span></th>
              <th>Ingredient <span class="sort-icon">&#8597;</span></th>
              <th>Weighted Score <span class="sort-icon sorted">&#8595;</span></th>
              <th># Products <span class="sort-icon">&#8597;</span></th>
              <th>Avg Weight <span class="sort-icon">&#8597;</span></th>
              <th>Category</th>
              <th>Avg Price <span class="sort-icon">&#8597;</span></th>
              <th>Key Insight</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="pagination"></div>
    </div>
  </section>

  <!-- ==================== CATEGORY SUMMARY ==================== -->
  <section class="section" id="category-summary" style="--section-color:var(--color-category-summary)">
    <div class="section-header">
      <div>
        <div class="section-title">Category Summary</div>
        <div class="section-subtitle">Ingredient category rollup by weighted market score</div>
      </div>
    </div>
    <div class="chart-container" style="height:300px;margin-bottom:24px">
      <canvas id="category-chart"></canvas>
    </div>
    <div class="table-wrapper">
      <table>
        <thead><tr><th>Category</th><th>Score</th><th>Types</th><th>Mentions</th><th>Avg Price</th><th>Top Ingredients</th></tr></thead>
        <tbody id="category-tbody"></tbody>
      </table>
    </div>
  </section>

  <!-- ==================== RISING PRODUCTS ==================== -->
  <section class="section" id="rising-products" style="--section-color:var(--color-rising-products)">
    <div class="section-header">
      <div>
        <div class="section-title">Rising Products</div>
        <div class="section-subtitle">Low reviews + high BSR rank &mdash; new entrants to watch</div>
      </div>
    </div>
    <div class="card-grid card-grid-2" id="rising-grid"></div>
  </section>

  <!-- ==================== PRODUCT DETAIL ==================== -->
  <section class="section" id="product-detail" style="--section-color:var(--color-product-detail)">
    <div class="section-header">
      <div>
        <div class="section-title">Product Detail</div>
        <div class="section-subtitle">Full product data table with all columns</div>
      </div>
    </div>
    <div class="toolbar">
      <input class="search-input" type="text" id="pd-search" placeholder="Search by title or ASIN...">
    </div>
    <div data-tc="1" id="product-detail-table-wrap">
      <div class="table-wrapper">
        <table style="min-width:1400px">
          <thead>
            <tr>
              <th>ASIN <span class="sort-icon">&#8597;</span></th>
              <th>Brand <span class="sort-icon">&#8597;</span></th>
              <th>Title</th>
              <th>Price <span class="sort-icon">&#8597;</span></th>
              <th>Customer Says</th>
              <th>SNS Price <span class="sort-icon">&#8597;</span></th>
              <th>Bought/Mo <span class="sort-icon">&#8597;</span></th>
              <th>Reviews <span class="sort-icon">&#8597;</span></th>
              <th>Rating <span class="sort-icon">&#8597;</span></th>
              <th>BSR <span class="sort-icon">&#8597;</span></th>
              <th>Weight <span class="sort-icon">&#8597;</span></th>
              <th>Unit Price</th>
              <th>Coupon</th>
              <th>Badge</th>
              <th>A+</th>
              <th>Vars <span class="sort-icon">&#8597;</span></th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="pagination"></div>
    </div>
  </section>

  <!-- ==================== RAW SEARCH ==================== -->
  <section class="section" id="raw-search" style="--section-color:var(--color-raw-search)">
    <div class="section-header">
      <div>
        <div class="section-title">Raw - Search</div>
        <div class="section-subtitle">Original search crawl data</div>
      </div>
    </div>
    <div class="raw-banner">&#9888; Raw data &mdash; unprocessed</div>
    <div class="toolbar">
      <input class="search-input" type="text" id="rs-search" placeholder="Search...">
    </div>
    <div data-tc="1" id="raw-search-table-wrap">
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>ASIN <span class="sort-icon">&#8597;</span></th>
              <th>Title</th>
              <th>Price</th>
              <th>Reviews <span class="sort-icon">&#8597;</span></th>
              <th>Rating <span class="sort-icon">&#8597;</span></th>
              <th>Sponsored</th>
              <th>Bought/Mo <span class="sort-icon">&#8597;</span></th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="pagination"></div>
    </div>
  </section>

  <!-- ==================== RAW DETAIL ==================== -->
  <section class="section" id="raw-detail" style="--section-color:var(--color-raw-detail)">
    <div class="section-header">
      <div>
        <div class="section-title">Raw - Detail</div>
        <div class="section-subtitle">Parsed product page data</div>
      </div>
    </div>
    <div class="raw-banner">&#9888; Raw data &mdash; unprocessed</div>
    <div class="toolbar">
      <input class="search-input" type="text" id="rd-search" placeholder="Search...">
    </div>
    <div data-tc="1" id="raw-detail-table-wrap">
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ASIN <span class="sort-icon">&#8597;</span></th>
              <th>Brand <span class="sort-icon">&#8597;</span></th>
              <th>BSR <span class="sort-icon">&#8597;</span></th>
              <th>Rating <span class="sort-icon">&#8597;</span></th>
              <th>Reviews <span class="sort-icon">&#8597;</span></th>
              <th>Manufacturer</th>
              <th>Ingredients Raw</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="pagination"></div>
    </div>
  </section>
  `;
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  const D = REPORT_DATA;

  // Page title & header
  document.title = 'AMZ Insight Report \u2014 ' + (D.keyword || '');
  document.getElementById('header-keyword').textContent = D.keyword || '';
  document.getElementById('header-meta').textContent = (D.date || '') + ' \u00b7 ' + (D.total_products || 0) + ' products analyzed';

  // Build sections HTML
  document.getElementById('main-content').innerHTML = buildSectionsHTML();

  // Render each section (isolated try-catch so one failure doesn't block others)
  const renderers = [
    renderMarketInsight, renderConsumerVoice, renderBadgeAnalysis,
    renderSalesPricing, renderBrandPositioning, renderMarketingKeywords,
    renderIngredientRanking, renderCategorySummary, renderRisingProducts,
    renderProductDetail, renderRawSearch, renderRawDetail,
  ];
  for (const fn of renderers) {
    try { fn(D); } catch (e) { console.error('[' + fn.name + ']', e); }
  }

  // Build sidebar after sections are rendered (so visibility is determined)
  buildSidebar(D);
});
</script>
</body>
</html>"""
