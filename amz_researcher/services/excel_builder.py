import json
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from amz_researcher.models import (
    CategorySummary,
    IngredientRanking,
    ProductDetail,
    SearchProduct,
    WeightedProduct,
)

# Styling constants
HEADER_FILL = PatternFill("solid", fgColor="1B2A4A")
HEADER_FONT = Font(name="Arial", size=11, bold=True, color="FFFFFF")
ACCENT_FILL = PatternFill("solid", fgColor="F5F7FA")
BORDER_BOTTOM = Border(bottom=Side(style="thin", color="D0D5DD"))
TITLE_FONT = Font(name="Arial", size=14, bold=True, color="1B2A4A")
SUBTITLE_FONT = Font(name="Arial", size=10, color="666666")
DATA_FONT = Font(name="Arial", size=10)
WRAP_ALIGN = Alignment(wrap_text=True, vertical="top")
DEFAULT_ALIGN = Alignment(vertical="center")

TAB_COLORS = {
    "Ingredient Ranking": "1B2A4A",
    "Category Summary": "2E86AB",
    "Product Detail": "4CAF50",
    "Raw - Search Results": "FF6B35",
    "Raw - Product Detail": "9B59B6",
    "Rising Products": "00BCD4",
    "Form × Price": "FF9800",
    "Market Insight": "E91E63",
    "Analysis Data": "795548",
}


def _style_header_row(ws, row: int, col_count: int):
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = DEFAULT_ALIGN


def _style_data_rows(ws, start_row: int, end_row: int, col_count: int):
    for r in range(start_row, end_row + 1):
        for c in range(1, col_count + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = DATA_FONT
            cell.border = BORDER_BOTTOM
            cell.alignment = DEFAULT_ALIGN
            if (r - start_row) % 2 == 1:
                cell.fill = ACCENT_FILL


def _write_title(ws, title: str, subtitle: str, col_count: int):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = TITLE_FONT

    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=col_count)
        sub_cell = ws.cell(row=2, column=1, value=subtitle)
        sub_cell.font = SUBTITLE_FONT


def _set_column_widths(ws, widths: dict[str, float]):
    for col_letter, width in widths.items():
        ws.column_dimensions[col_letter].width = width


def _dict_to_text(d: dict) -> str:
    """{"Hair Type": "All", ...} → "Hair Type: All\nItem Form: Oil" """
    return "\n".join(f"{k}: {v}" for k, v in d.items() if not isinstance(v, (list, dict)))


def _build_ingredient_ranking(
    wb: Workbook, keyword: str,
    rankings: list[IngredientRanking],
    product_count: int,
):
    ws = wb.active
    ws.title = "Ingredient Ranking"
    ws.sheet_properties.tabColor = TAB_COLORS["Ingredient Ranking"]

    col_count = 9
    title = f"{keyword.title()} Ingredient Analysis — Weighted by Market Performance"
    subtitle = (
        f"Weight = Position(20%) + Reviews(25%) + Rating(15%) + BSR(40%) "
        f"| {product_count} products, {len(rankings)} ingredients"
    )
    _write_title(ws, title, subtitle, col_count)

    desc = (
        "Weighted Score: 해당 성분을 포함하는 모든 제품의 Composite Weight 합산. "
        "높을수록 시장 성과가 좋은 제품에 많이 사용됨. "
        "Avg Weight: 제품당 평균 가중치. # Products가 적어도 Avg Weight가 높으면 Top 제품에 집중된 성분."
    )
    desc_cell = ws.cell(row=3, column=1, value=desc)
    desc_cell.font = Font(name="Arial", size=9, italic=True, color="666666")
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=col_count)

    headers = [
        "Rank", "Ingredient", "Weighted Score", "# Products",
        "Avg Weight", "Category", "Avg Price", "Price Range", "Key Insight",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=5, column=c, value=h)
    _style_header_row(ws, 5, col_count)

    for i, r in enumerate(rankings):
        row = 6 + i
        ws.cell(row=row, column=1, value=r.rank)
        ws.cell(row=row, column=2, value=r.ingredient)
        ws.cell(row=row, column=3, value=r.weighted_score).number_format = "0.000"
        ws.cell(row=row, column=4, value=r.product_count)
        ws.cell(row=row, column=5, value=r.avg_weight).number_format = "0.000"
        ws.cell(row=row, column=6, value=r.category)
        if r.avg_price is not None:
            ws.cell(row=row, column=7, value=r.avg_price).number_format = "$#,##0.00"
        ws.cell(row=row, column=8, value=r.price_range)
        ws.cell(row=row, column=9, value=r.key_insight)

    end_row = 5 + len(rankings)
    _style_data_rows(ws, 6, end_row, col_count)
    ws.freeze_panes = "A6"
    _set_column_widths(ws, {
        "A": 7, "B": 28, "C": 15, "D": 12, "E": 13,
        "F": 20, "G": 12, "H": 18, "I": 42,
    })


def _build_category_summary(wb: Workbook, categories: list[CategorySummary]):
    ws = wb.create_sheet("Category Summary")
    ws.sheet_properties.tabColor = TAB_COLORS["Category Summary"]

    col_count = 7
    _write_title(
        ws,
        "Ingredient Category Summary",
        "성분을 기능별 카테고리(Natural Oil, Vitamin, Botanical 등)로 그룹핑한 요약",
        col_count,
    )

    desc = (
        "Total Weighted Score: 카테고리 내 모든 성분의 가중치 합산 — 시장에서 해당 카테고리의 영향력. "
        "# Types: 고유 성분 수. # Mentions: 전체 제품에서 등장한 횟수 합계."
    )
    desc_cell = ws.cell(row=3, column=1, value=desc)
    desc_cell.font = Font(name="Arial", size=9, italic=True, color="666666")
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=col_count)

    headers = [
        "Category", "Total Weighted Score", "# Types",
        "# Mentions", "Avg Price", "Price Range", "Top Ingredients",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, cat in enumerate(categories):
        row = 5 + i
        ws.cell(row=row, column=1, value=cat.category)
        ws.cell(row=row, column=2, value=cat.total_weighted_score).number_format = "0.000"
        ws.cell(row=row, column=3, value=cat.type_count)
        ws.cell(row=row, column=4, value=cat.mention_count)
        if cat.avg_price is not None:
            ws.cell(row=row, column=5, value=cat.avg_price).number_format = "$#,##0.00"
        ws.cell(row=row, column=6, value=cat.price_range)
        ws.cell(row=row, column=7, value=cat.top_ingredients)

    end_row = 4 + len(categories)
    _style_data_rows(ws, 5, end_row, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {
        "A": 22, "B": 20, "C": 10, "D": 12, "E": 12, "F": 18, "G": 45,
    })


def _build_product_detail(wb: Workbook, products: list[WeightedProduct]):
    ws = wb.create_sheet("Product Detail")
    ws.sheet_properties.tabColor = TAB_COLORS["Product Detail"]

    col_count = 10
    _write_title(
        ws,
        "Product-Level Data with Weight Breakdown",
        "각 제품의 시장 성과 지표와 Gemini가 추출한 핵심 성분 목록",
        col_count,
    )

    desc = (
        "Composite Weight: Position(20%)+Reviews(25%)+Rating(15%)+BSR(40%) 종합 점수. "
        "BSR(Category): Amazon 전체 카테고리 베스트셀러 순위 (낮을수록 잘 팔림). "
        "BSR(Sub): 서브카테고리 순위."
    )
    desc_cell = ws.cell(row=3, column=1, value=desc)
    desc_cell.font = Font(name="Arial", size=9, italic=True, color="666666")
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=col_count)

    headers = [
        "ASIN", "Title", "Position", "Price", "Reviews",
        "Rating", "BSR (Category)", "BSR (Sub)", "Composite Weight", "Ingredients Found",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, p in enumerate(products):
        row = 5 + i
        ingredients_str = ", ".join(ing.name for ing in p.ingredients)
        ws.cell(row=row, column=1, value=p.asin)
        ws.cell(row=row, column=2, value=p.title)
        ws.cell(row=row, column=3, value=p.position)
        if p.price is not None:
            ws.cell(row=row, column=4, value=p.price).number_format = "$#,##0.00"
        ws.cell(row=row, column=5, value=p.reviews).number_format = "#,##0"
        ws.cell(row=row, column=6, value=p.rating)
        if p.bsr_category is not None:
            ws.cell(row=row, column=7, value=p.bsr_category).number_format = "#,##0"
        if p.bsr_subcategory is not None:
            ws.cell(row=row, column=8, value=p.bsr_subcategory).number_format = "#,##0"
        ws.cell(row=row, column=9, value=p.composite_weight).number_format = "0.000"
        ws.cell(row=row, column=10, value=ingredients_str)

    end_row = 4 + len(products)
    _style_data_rows(ws, 5, end_row, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {
        "A": 14, "B": 50, "C": 10, "D": 10, "E": 10,
        "F": 8, "G": 14, "H": 10, "I": 16, "J": 50,
    })


def _build_raw_search(wb: Workbook, keyword: str, products: list[SearchProduct]):
    ws = wb.create_sheet("Raw - Search Results")
    ws.sheet_properties.tabColor = TAB_COLORS["Raw - Search Results"]

    col_count = 8
    title = f'Amazon Search Results — "{keyword}" (Raw Data, {len(products)} products)'
    _write_title(
        ws, title,
        "Browse.ai가 수집한 Amazon 검색 결과 원본. Position은 검색 페이지 노출 순서.",
        col_count,
    )

    headers = [
        "Position", "Title", "ASIN", "Price",
        "Reviews", "Rating", "Sponsored", "Product Link",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=3, column=c, value=h)
    _style_header_row(ws, 3, col_count)

    for i, p in enumerate(products):
        row = 4 + i
        ws.cell(row=row, column=1, value=p.position)
        ws.cell(row=row, column=2, value=p.title)
        ws.cell(row=row, column=3, value=p.asin)
        ws.cell(row=row, column=4, value=p.price_raw)
        ws.cell(row=row, column=5, value=p.reviews_raw)
        ws.cell(row=row, column=6, value=p.rating)
        ws.cell(row=row, column=7, value="Yes" if p.sponsored else "")
        ws.cell(row=row, column=8, value=p.product_link)

    end_row = 3 + len(products)
    _style_data_rows(ws, 4, end_row, col_count)
    ws.freeze_panes = "A4"
    _set_column_widths(ws, {
        "A": 10, "B": 60, "C": 14, "D": 12, "E": 12, "F": 8, "G": 12, "H": 50,
    })


def _build_raw_detail(wb: Workbook, details: list[ProductDetail]):
    ws = wb.create_sheet("Raw - Product Detail")
    ws.sheet_properties.tabColor = TAB_COLORS["Raw - Product Detail"]

    col_count = 10
    _write_title(
        ws,
        "Amazon Product Detail — Parsed Data (Raw)",
        "각 ASIN의 상세 페이지에서 파싱한 원본 데이터. Ingredients(raw)는 INCI 전성분 텍스트.",
        col_count,
    )

    headers = [
        "ASIN", "Brand", "BSR Category", "BSR Subcategory",
        "Rating", "Reviews", "Ingredients (raw)",
        "Features", "Measurements", "Additional Details",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=3, column=c, value=h)
    _style_header_row(ws, 3, col_count)

    for i, d in enumerate(details):
        row = 4 + i
        ws.cell(row=row, column=1, value=d.asin)
        ws.cell(row=row, column=2, value=d.brand)
        if d.bsr_category is not None:
            bsr_cat_str = f"#{d.bsr_category} in {d.bsr_category_name}"
            ws.cell(row=row, column=3, value=bsr_cat_str)
        if d.bsr_subcategory is not None:
            bsr_sub_str = f"#{d.bsr_subcategory} in {d.bsr_subcategory_name}"
            ws.cell(row=row, column=4, value=bsr_sub_str)
        if d.rating is not None:
            ws.cell(row=row, column=5, value=d.rating)
        if d.review_count is not None:
            ws.cell(row=row, column=6, value=d.review_count).number_format = "#,##0"

        ing_cell = ws.cell(row=row, column=7, value=d.ingredients_raw)
        ing_cell.alignment = WRAP_ALIGN
        feat_cell = ws.cell(row=row, column=8, value=_dict_to_text(d.features))
        feat_cell.alignment = WRAP_ALIGN
        meas_cell = ws.cell(row=row, column=9, value=_dict_to_text(d.measurements))
        meas_cell.alignment = WRAP_ALIGN
        add_cell = ws.cell(row=row, column=10, value=_dict_to_text(d.additional_details))
        add_cell.alignment = WRAP_ALIGN

        ws.row_dimensions[row].height = 80

    end_row = 3 + len(details)
    _style_data_rows(ws, 4, end_row, col_count)
    ws.freeze_panes = "A4"
    _set_column_widths(ws, {
        "A": 14, "B": 16, "C": 30, "D": 30, "E": 8, "F": 10,
        "G": 50, "H": 35, "I": 30, "J": 35,
    })


def _build_rising_products(wb: Workbook, rising: list[dict]):
    ws = wb.create_sheet("Rising Products")
    ws.sheet_properties.tabColor = TAB_COLORS["Rising Products"]

    col_count = 9
    _write_title(
        ws,
        "Rising Products — Low Reviews, High BSR",
        "리뷰 수가 중앙값 미만이면서 BSR 10,000 이내인 제품. 신규 진입자 또는 급성장 중인 제품 후보.",
        col_count,
    )

    headers = [
        "BSR", "Brand", "Title", "Price", "Reviews",
        "Rating", "Form", "Top Ingredients", "ASIN",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, p in enumerate(rising):
        row = 5 + i
        ws.cell(row=row, column=1, value=p["bsr"]).number_format = "#,##0"
        ws.cell(row=row, column=2, value=p["brand"])
        ws.cell(row=row, column=3, value=p["title"])
        if p["price"] is not None:
            ws.cell(row=row, column=4, value=p["price"]).number_format = "$#,##0.00"
        ws.cell(row=row, column=5, value=p["reviews"]).number_format = "#,##0"
        ws.cell(row=row, column=6, value=p["rating"])
        ws.cell(row=row, column=7, value=p["form"])
        ws.cell(row=row, column=8, value=p["top_ingredients"])
        ws.cell(row=row, column=9, value=p["asin"])

    end_row = 4 + len(rising)
    _style_data_rows(ws, 5, end_row, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {
        "A": 10, "B": 18, "C": 50, "D": 10, "E": 10,
        "F": 8, "G": 12, "H": 40, "I": 14,
    })


def _build_form_price(wb: Workbook, form_data: dict):
    ws = wb.create_sheet("Form × Price")
    ws.sheet_properties.tabColor = TAB_COLORS["Form × Price"]

    # Part 1: Form Summary
    form_summary = form_data.get("form_summary", [])
    col_count = 6
    _write_title(
        ws, "Product Form Analysis",
        "제형(Oil, Serum, Cream 등)별 평균 가격/평점/BSR 비교. 매트릭스에서 빈 칸 = 미개척 시장 기회.",
        col_count,
    )

    headers = ["Form", "Count", "Avg Price", "Avg Rating", "Avg Reviews", "Avg BSR"]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, f in enumerate(form_summary):
        row = 5 + i
        ws.cell(row=row, column=1, value=f["form"])
        ws.cell(row=row, column=2, value=f["count"])
        if f["avg_price"] is not None:
            ws.cell(row=row, column=3, value=f["avg_price"]).number_format = "$#,##0.00"
        ws.cell(row=row, column=4, value=f["avg_rating"])
        ws.cell(row=row, column=5, value=f["avg_reviews"]).number_format = "#,##0"
        if f["avg_bsr"] is not None:
            ws.cell(row=row, column=6, value=f["avg_bsr"]).number_format = "#,##0"

    end_row = 4 + len(form_summary)
    _style_data_rows(ws, 5, end_row, col_count)

    # Part 2: Price × Form Matrix
    matrix = form_data.get("matrix", {})
    matrix_start = end_row + 3
    ws.cell(row=matrix_start, column=1, value="Price Tier × Form Matrix").font = TITLE_FONT

    all_forms = sorted({
        form for tier_data in matrix.values() for form in tier_data
    })
    for c, form in enumerate(all_forms, 2):
        ws.cell(row=matrix_start + 1, column=c, value=form)
    ws.cell(row=matrix_start + 1, column=1, value="Price Tier")
    _style_header_row(ws, matrix_start + 1, len(all_forms) + 1)

    for i, tier in enumerate(["Budget (<$10)", "Mid ($10-25)", "Premium ($25-50)", "Luxury ($50+)"]):
        row = matrix_start + 2 + i
        ws.cell(row=row, column=1, value=tier)
        tier_data = matrix.get(tier, {})
        for c, form in enumerate(all_forms, 2):
            count = tier_data.get(form, 0)
            ws.cell(row=row, column=c, value=count if count else "")

    _style_data_rows(ws, matrix_start + 2, matrix_start + 5, len(all_forms) + 1)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {
        "A": 20, "B": 14, "C": 14, "D": 12, "E": 14, "F": 12,
    })


def _build_market_insight(wb: Workbook, keyword: str, report_md: str):
    """AI 시장 분석 리포트를 Market Insight 시트에 기록.

    A5 셀 하나에 전체 리포트를 넣어 Notion 복사-붙여넣기 지원.
    """
    ws = wb.create_sheet("Market Insight")
    ws.sheet_properties.tabColor = TAB_COLORS["Market Insight"]

    col_count = 1
    _write_title(
        ws,
        f"{keyword.title()} Market Insight — AI Analysis Report",
        "Powered by Gemini | Data-driven product planning insights",
        col_count,
    )

    note = (
        "Notion 붙여넣기: A5 셀 선택 후 상단 수식입력줄의 텍스트를 전체 선택(Ctrl+A) → 복사(Ctrl+C) → "
        "Notion에 붙여넣기하면 마크다운으로 자동 렌더링됩니다."
    )
    note_cell = ws.cell(row=3, column=1, value=note)
    note_cell.font = Font(name="Arial", size=9, italic=True, color="E91E63")

    cell = ws.cell(row=5, column=1, value=report_md)
    cell.font = Font(name="Arial", size=10)
    cell.alignment = Alignment(wrap_text=True, vertical="top")

    line_count = report_md.count("\n") + 1
    ws.row_dimensions[5].height = min(line_count * 15, 8000)
    ws.column_dimensions["A"].width = 120
    ws.freeze_panes = "A5"


def _build_analysis_data(wb: Workbook, analysis_data: dict):
    """Gemini에 전달한 시장 분석 원본 데이터를 시트로 출력."""
    ws = wb.create_sheet("Analysis Data")
    ws.sheet_properties.tabColor = TAB_COLORS["Analysis Data"]

    sections = [
        ("price_tier_analysis", "Price Tier Analysis"),
        ("bsr_analysis", "BSR Top vs Bottom"),
        ("brand_analysis", "Brand Profiles"),
        ("cooccurrence_analysis", "Ingredient Co-occurrence"),
        ("form_price_matrix", "Form x Price Matrix"),
        ("brand_positioning", "Brand Positioning"),
        ("rising_products", "Rising Products"),
        ("rating_ingredients", "Rating vs Ingredients"),
    ]

    _write_title(
        ws,
        "Analysis Data — Raw Input to AI Market Report",
        f"Gemini에 전달한 분석 원본 JSON. 8개 섹션의 데이터를 직접 확인 가능. "
        f"Keyword: {analysis_data.get('keyword', '')} | "
        f"{analysis_data.get('total_products', 0)} products",
        1,
    )

    row = 4
    for key, label in sections:
        data = analysis_data.get(key, {})
        if not data:
            continue
        ws.cell(row=row, column=1, value=label).font = Font(
            name="Arial", size=11, bold=True, color="1B2A4A",
        )
        _style_header_row(ws, row, 1)
        row += 1

        json_text = json.dumps(data, ensure_ascii=False, indent=2)
        cell = ws.cell(row=row, column=1, value=json_text)
        cell.font = DATA_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        line_count = json_text.count("\n") + 1
        ws.row_dimensions[row].height = min(line_count * 15, 4000)
        row += 2

    ws.column_dimensions["A"].width = 120


def build_excel(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    market_report: str = "",
    rising_products: list[dict] | None = None,
    form_price_data: dict | None = None,
    analysis_data: dict | None = None,
) -> bytes:
    wb = Workbook()

    _build_ingredient_ranking(wb, keyword, rankings, len(weighted_products))
    _build_category_summary(wb, categories)
    _build_product_detail(wb, weighted_products)
    if rising_products:
        _build_rising_products(wb, rising_products)
    if form_price_data:
        _build_form_price(wb, form_price_data)
    _build_raw_search(wb, keyword, search_products)
    _build_raw_detail(wb, details)
    if market_report:
        _build_market_insight(wb, keyword, market_report)
    if analysis_data:
        _build_analysis_data(wb, analysis_data)

    # Move Market Insight to front (first sheet)
    if market_report and "Market Insight" in wb.sheetnames:
        idx = wb.sheetnames.index("Market Insight")
        wb.move_sheet("Market Insight", offset=-idx)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
