# HTML Report — Component Map

> Python `html_report_builder.py` implementation guide.
> Maps mockup HTML sections to data sources and builder functions.

---

## 1. Builder Function Signature

```python
def build_html_report(
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
    """Generate a self-contained HTML report. Returns UTF-8 encoded bytes."""
```

Same signature as `build_excel()` — drop-in parallel output.

---

## 2. Section → Data Source Mapping

| Section ID | Data Source | Key Fields |
|-----------|-------------|-----------|
| `#market-insight` | `market_report: str` | Markdown string — rendered inline |
| `#consumer-voice` | `analysis_data["customer_voice"]` | positive_keywords, negative_keywords, bsr_top_half_* |
| `#badge-analysis` | `analysis_data["badges"]` | with_badge, without_badge, badge_types, stat_test_bsr, acquisition_threshold |
| `#sales-pricing` | `analysis_data["sales_volume"]`, `["sns_pricing"]`, `["discount_impact"]`, `["promotions"]` | See excel_builder section mapping |
| `#brand-positioning` | `analysis_data["brand_positioning"]`, `["manufacturer"]` | positioning list, top_manufacturers, market_concentration |
| `#marketing-keywords` | `analysis_data["title_keywords"]`, `["price_tier_analysis"]` | keyword_analysis, price tier ingredients |
| `#ingredient-ranking` | `rankings: list[IngredientRanking]` | rank, ingredient, weighted_score, product_count, avg_weight, category, avg_price, key_insight |
| `#category-summary` | `categories: list[CategorySummary]` | category, total_weighted_score, type_count, mention_count, avg_price, top_ingredients |
| `#rising-products` | `rising_products: list[dict]` | bsr, brand, title, price, reviews, rating, top_ingredients, asin |
| `#product-detail` | `weighted_products: list[WeightedProduct]` | All 20 columns (see ProductDetail) |
| `#raw-search` | `search_products: list[SearchProduct]` | position, title, asin, price_raw, reviews_raw, rating, sponsored |
| `#raw-detail` | `details: list[ProductDetail]` | asin, brand, bsr_category, rating, review_count, ingredients_raw |

---

## 3. REPORT_DATA JSON Structure

The Python builder injects a single JSON blob into the HTML template:

```python
import json

report_data = {
    "keyword": keyword,
    "date": datetime.now().strftime("%Y-%m-%d"),
    "total_products": len(weighted_products),
    "market_report": market_report,
    "rankings": [r.model_dump() for r in rankings],
    "categories": [c.model_dump() for c in categories],
    "rising_products": rising_products or [],
    "products": [_product_to_dict(p) for p in weighted_products],
    "search_products": [_search_to_dict(p) for p in search_products],
    "details": [_detail_to_dict(d) for d in details],
    "analysis": analysis_data or {},
}

html = TEMPLATE.replace(
    "const REPORT_DATA = {};",
    f"const REPORT_DATA = {json.dumps(report_data, ensure_ascii=False, default=str)};"
)
```

---

## 4. Template Architecture

The HTML template is stored as a Python string constant (or read from a `.html` template file at build time). The Chart.js bundle is bundled inline.

```
amz_researcher/services/
├── html_report_builder.py        # Main builder
└── html_report_template.py       # Template constant (large string)
```

Or alternatively, store the template as a static asset:

```
amz_researcher/assets/
└── report_template.html          # Template with REPORT_DATA placeholder
```

---

## 5. Inline Chart.js Strategy

For production (offline requirement), download Chart.js UMD and embed inline:

```bash
curl -o chart.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
```

Embed in template:
```html
<script>
/* Chart.js 4.4.0 UMD — inlined for offline use */
/* CHARTJS_BUNDLE_PLACEHOLDER */
</script>
```

Python builder replaces `/* CHARTJS_BUNDLE_PLACEHOLDER */` with the file content. This runs once at template build time, not at report generation time.

Estimated Chart.js bundle size: ~210KB minified (not gzipped).

---

## 6. Conditional Sections

Sections are conditionally rendered based on data availability — same logic as `excel_builder.py`:

```python
# In builder:
sections = []
if market_report:
    sections.append(render_market_insight(market_report))
if analysis_data and analysis_data.get("customer_voice"):
    sections.append(render_consumer_voice(analysis_data["customer_voice"]))
# etc.
```

The sidebar nav items are dynamically generated to match only rendered sections.

---

## 7. Markdown Renderer (inline JS)

The inline JS markdown parser covers AI report output:

```javascript
function renderMarkdown(text) {
  return text
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/^---$/gm, '<hr>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(.+)$/gm, (line) =>
      line.match(/^<(h[1-4]|ul|ol|li|hr)/) ? line : `<p>${line}</p>`
    );
}
```

AI report is split on `## ` headings into `<details>` sections:

```javascript
function wrapInSections(markdownHtml) {
  // Split on <h2> tags and wrap each in <details><summary>
}
```

---

## 8. Table Sort / Search / Paginate (inline JS)

Reusable table controller:

```javascript
class TableController {
  constructor(tableId, { pageSize = 25, searchInputId, filterInputId } = {}) { ... }
  sort(colIndex, direction) { ... }
  search(query) { ... }
  paginate(page) { ... }
}
```

Initialized for:
- `#ingredient-table` — sort + search + category filter
- `#product-detail-table` — sort + search + pagination (25 rows)
- Raw tables — search only

---

## 9. File Size Budget

| Component | Target |
|-----------|--------|
| HTML + CSS | 15 KB |
| Chart.js inline | 210 KB |
| App JS | 10 KB |
| REPORT_DATA JSON | 50–200 KB |
| **Total** | **285–435 KB** |

Fits within Slack single-file upload. Opens in browser with no network requests.
