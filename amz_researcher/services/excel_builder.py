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

    headers = [
        "Rank", "Ingredient", "Weighted Score", "# Products",
        "Avg Weight", "Category", "Avg Price", "Price Range", "Key Insight",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=4, column=c, value=h)
    _style_header_row(ws, 4, col_count)

    for i, r in enumerate(rankings):
        row = 5 + i
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

    end_row = 4 + len(rankings)
    _style_data_rows(ws, 5, end_row, col_count)
    ws.freeze_panes = "A5"
    _set_column_widths(ws, {
        "A": 7, "B": 28, "C": 15, "D": 12, "E": 13,
        "F": 20, "G": 12, "H": 18, "I": 42,
    })


def _build_category_summary(wb: Workbook, categories: list[CategorySummary]):
    ws = wb.create_sheet("Category Summary")
    ws.sheet_properties.tabColor = TAB_COLORS["Category Summary"]

    col_count = 7
    _write_title(ws, "Ingredient Category Summary", "", col_count)

    headers = [
        "Category", "Total Weighted Score", "# Types",
        "# Mentions", "Avg Price", "Price Range", "Top Ingredients",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=3, column=c, value=h)
    _style_header_row(ws, 3, col_count)

    for i, cat in enumerate(categories):
        row = 4 + i
        ws.cell(row=row, column=1, value=cat.category)
        ws.cell(row=row, column=2, value=cat.total_weighted_score).number_format = "0.000"
        ws.cell(row=row, column=3, value=cat.type_count)
        ws.cell(row=row, column=4, value=cat.mention_count)
        if cat.avg_price is not None:
            ws.cell(row=row, column=5, value=cat.avg_price).number_format = "$#,##0.00"
        ws.cell(row=row, column=6, value=cat.price_range)
        ws.cell(row=row, column=7, value=cat.top_ingredients)

    end_row = 3 + len(categories)
    _style_data_rows(ws, 4, end_row, col_count)
    ws.freeze_panes = "A4"
    _set_column_widths(ws, {
        "A": 22, "B": 20, "C": 10, "D": 12, "E": 12, "F": 18, "G": 45,
    })


def _build_product_detail(wb: Workbook, products: list[WeightedProduct]):
    ws = wb.create_sheet("Product Detail")
    ws.sheet_properties.tabColor = TAB_COLORS["Product Detail"]

    col_count = 10
    _write_title(ws, "Product-Level Data with Weight Breakdown", "", col_count)

    headers = [
        "ASIN", "Title", "Position", "Price", "Reviews",
        "Rating", "BSR (Category)", "BSR (Sub)", "Composite Weight", "Ingredients Found",
    ]
    for c, h in enumerate(headers, 1):
        ws.cell(row=3, column=c, value=h)
    _style_header_row(ws, 3, col_count)

    for i, p in enumerate(products):
        row = 4 + i
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

    end_row = 3 + len(products)
    _style_data_rows(ws, 4, end_row, col_count)
    ws.freeze_panes = "A4"
    _set_column_widths(ws, {
        "A": 14, "B": 50, "C": 10, "D": 10, "E": 10,
        "F": 8, "G": 14, "H": 10, "I": 16, "J": 50,
    })


def _build_raw_search(wb: Workbook, keyword: str, products: list[SearchProduct]):
    ws = wb.create_sheet("Raw - Search Results")
    ws.sheet_properties.tabColor = TAB_COLORS["Raw - Search Results"]

    col_count = 8
    title = f'Amazon Search Results — "{keyword}" (Raw Data, {len(products)} products)'
    _write_title(ws, title, "", col_count)

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
        "",
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


def build_excel(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
) -> bytes:
    wb = Workbook()

    _build_ingredient_ranking(wb, keyword, rankings, len(weighted_products))
    _build_category_summary(wb, categories)
    _build_product_detail(wb, weighted_products)
    _build_raw_search(wb, keyword, search_products)
    _build_raw_detail(wb, details)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
