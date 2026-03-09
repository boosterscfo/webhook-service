# HTML Insight Report — UX Specification

> **Feature**: html-insight-report
> **Date**: 2026-03-09
> **Status**: Design Phase
> **Deliverable**: Single self-contained HTML file (Slack upload)

---

## 1. Information Architecture

### 1.1 Three-tier Navigation Model

The 12 sheets map to three conceptual tiers. Users follow a natural funnel: narrative insight → quantified analysis → raw evidence.

```
TIER 1 — STORY (What is happening)
├── Market Insight      AI narrative, executive summary
├── Consumer Voice      What customers actually say
├── Badge Analysis      Trust signal landscape

TIER 2 — ANALYSIS (Why it is happening)
├── Sales & Pricing     Revenue patterns, discount mechanics
├── Brand Positioning   Competitive map
├── Marketing Keywords  Title strategy that works
├── Ingredient Ranking  Core ranking — the hero data
├── Category Summary    Ingredient category rollup
└── Rising Products     Growth signals

TIER 3 — DATA (The evidence)
├── Product Detail      Full product table (20 columns)
├── Raw Search          Original search crawl
└── Raw Product Detail  Parsed product page data
```

### 1.2 Default View on Open

The report opens on **Market Insight** (Tier 1). This is the executive entry point — the AI narrative that synthesises all data. Users who only have 2 minutes should get full value from this single screen.

### 1.3 Navigation Pattern

**Fixed left sidebar** (desktop-first):
- Tier group labels act as visual dividers, not interactive
- Active section highlighted with left accent bar in section color
- Smooth scroll to section on click (single-page document)
- Sidebar collapses to icon-only on narrow viewports

Single-page scroll over tab switching rationale: this is a read-only report, not an application. Scrolling is natural for reading; tabs create hidden content that users may miss.

---

## 2. Design System Tokens

### 2.1 Color Palette

```css
/* === Section Identity Colors (from TAB_COLORS) === */
--color-market-insight:    #E91E63;  /* Pink — narrative */
--color-consumer-voice:    #FF9800;  /* Orange — voice */
--color-badge-analysis:    #673AB7;  /* Purple — trust */
--color-sales-pricing:     #009688;  /* Teal — revenue */
--color-brand-positioning: #3F51B5;  /* Indigo — competition */
--color-marketing-kw:      #795548;  /* Brown — keywords */
--color-ingredient-rank:   #1B2A4A;  /* Navy — ranking hero */
--color-category-summary:  #2E86AB;  /* Blue — categories */
--color-rising-products:   #00BCD4;  /* Cyan — growth */
--color-product-detail:    #4CAF50;  /* Green — products */
--color-raw-search:        #FF6B35;  /* Deep orange — raw */
--color-raw-detail:        #9B59B6;  /* Purple-grey — raw */

/* === Surface Colors === */
--color-bg-page:    #0F1117;  /* Near-black page background */
--color-bg-card:    #1A1D27;  /* Card surface */
--color-bg-sidebar: #13151F;  /* Sidebar background */
--color-bg-row-alt: #1E2130;  /* Alternating table row */

/* === Text Colors === */
--color-text-primary:   #F0F2F8;   /* Primary content */
--color-text-secondary: #8B92A5;   /* Captions, labels */
--color-text-muted:     #4D5468;   /* Disabled, placeholder */

/* === Semantic === */
--color-positive:  #22C55E;  /* Green — positive sentiment */
--color-negative:  #EF4444;  /* Red — negative sentiment */
--color-neutral:   #64748B;  /* Neutral */
--color-border:    #2A2D3E;  /* Subtle borders */
--color-separator: #1E2130;  /* Table row borders */
```

### 2.2 Typography

```css
/* System stack — no CDN, offline safe */
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
--font-mono: "SF Mono", "Fira Code", "Fira Mono", monospace;

/* Scale */
--text-xs:   11px;
--text-sm:   13px;
--text-base: 14px;
--text-md:   16px;
--text-lg:   20px;
--text-xl:   26px;
--text-2xl:  32px;

/* Weights */
--weight-normal: 400;
--weight-medium: 500;
--weight-bold:   700;
```

### 2.3 Spacing

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
```

### 2.4 Border Radius

```css
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-full: 9999px;
```

### 2.5 Shadows

```css
--shadow-card: 0 1px 3px 0 rgb(0 0 0 / 0.4), 0 1px 2px -1px rgb(0 0 0 / 0.4);
--shadow-elevated: 0 4px 16px 0 rgb(0 0 0 / 0.5);
```

---

## 3. Layout Blueprint

### 3.1 Overall Shell

```
┌──────────────────────────────────────────────────────────┐
│  HEADER (fixed top, 56px)                                │
│  [LOGO/REPORT TITLE]  [keyword badge]  [date]  [expand] │
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  SIDEBAR   │  CONTENT AREA (scrollable)                 │
│  (240px    │                                             │
│   fixed)   │  [Section content renders here]            │
│            │                                             │
│            │                                             │
└────────────┴─────────────────────────────────────────────┘
```

### 3.2 Header (56px fixed)

```
┌────────────────────────────────────────────────────────────┐
│  ◆ AMZ Insight  │  "rosehip oil"  2026-03-09  │  [≡] [▲] │
└────────────────────────────────────────────────────────────┘
```

- Left: Report logo + title
- Center: Keyword badge + date
- Right: Sidebar toggle (mobile) + "Back to top" button

### 3.3 Sidebar (240px fixed left)

```
┌───────────────────────┐
│  STORY                │  ← Group label (uppercase, muted)
│  ● Market Insight     │  ← Active: left accent bar + section color
│  ○ Consumer Voice     │
│  ○ Badge Analysis     │
│                       │
│  ANALYSIS             │
│  ○ Sales & Pricing    │
│  ○ Brand Positioning  │
│  ○ Marketing Keywords │
│  ○ Ingredient Ranking │
│  ○ Category Summary   │
│  ○ Rising Products    │
│                       │
│  DATA                 │
│  ○ Product Detail     │
│  ○ Raw - Search       │
│  ○ Raw - Detail       │
└───────────────────────┘
```

Each nav item has:
- Left 3px accent bar when active (section color)
- Hover: slight background lighten
- Icon: filled circle when active, outline when inactive

### 3.4 Content Area Width

Max-width 1200px, centered within available space. Left padding 240px (sidebar) + 24px gap.

---

## 4. Section-by-Section Layout

### 4.1 Market Insight (Pink — #E91E63)

**Purpose**: AI-generated markdown narrative. Users read this first.

```
┌─────────────────────────────────────────────────────────┐
│  ████ Market Insight                     AI Report      │
│  rosehip oil · 2026-03-09                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Rendered Markdown]                                    │
│                                                         │
│  # Market Overview                                      │
│  Lorem ipsum dolor sit amet...                         │
│                                                         │
│  ## Pricing & Ingredient Strategy                       │
│  ...                                                    │
│                                                         │
│  [Collapsible sections: expand/collapse each H2]        │
└─────────────────────────────────────────────────────────┘
```

**Component**: `MarkdownRenderer` — lightweight inline markdown parser (headings, bold, lists, paragraphs only). No CDN, inline implementation.

**Interaction**: Each H2 section is an `<details>` element, open by default. Users can collapse sections they have already read.

### 4.2 Consumer Voice (Orange — #FF9800)

**Purpose**: Keyword frequency + BSR correlation.

```
┌────────────────────────────────────────────────────────┐
│  ████ Consumer Voice                                    │
│  Keywords extracted from Amazon AI review summaries    │
├──────────────────────┬─────────────────────────────────┤
│  POSITIVE KEYWORDS   │  NEGATIVE KEYWORDS              │
│  ┌──────────────┐    │  ┌──────────────┐               │
│  │ moisturizing │ 34 │  │ sticky       │ 12            │
│  │ effective    │ 28 │  │ strong smell │ 8             │
│  │ hydrating    │ 22 │  │ greasy       │ 7             │
│  └──────────────┘    │  └──────────────┘               │
│  [horizontal bar chart for each keyword]               │
├──────────────────────┴─────────────────────────────────┤
│  BSR CORRELATION  Top Half vs Bottom Half              │
│  [grouped bar chart: keyword × top/bottom count]       │
└────────────────────────────────────────────────────────┘
```

**Charts**:
- Positive/Negative: horizontal bar chart, color-coded (green/red)
- BSR Correlation: grouped horizontal bars

**Table below chart**: Keyword | Count | Avg BSR | Avg Rating — sortable

### 4.3 Badge Analysis (Purple — #673AB7)

**Purpose**: Badge impact on market performance.

```
┌──────────────────────────────────────────────────────┐
│  ████ Badge Analysis                                  │
├──────────────────┬───────────────────────────────────┤
│  KPI CARDS (2)   │                                   │
│  ┌────────────┐  │  BADGE TYPE DISTRIBUTION          │
│  │ With Badge │  │  [donut chart]                    │
│  │    23      │  │  Amazon's Choice: 18              │
│  │ Avg BSR    │  │  #1 Best Seller: 5                │
│  │  3,421     │  │                                   │
│  └────────────┘  │                                   │
│  ┌────────────┐  │                                   │
│  │ No Badge   │  │                                   │
│  │    47      │  │                                   │
│  │ Avg BSR    │  │                                   │
│  │  12,890    │  │                                   │
│  └────────────┘  │                                   │
├──────────────────┴───────────────────────────────────┤
│  STATISTICAL TEST             ACQUISITION THRESHOLD  │
│  Mann-Whitney U: significant  Min Reviews:  342      │
│  p = 0.0023 ✓                 Med Reviews: 1,204     │
│                               Min Rating:  4.2       │
└──────────────────────────────────────────────────────┘
```

**KPI Cards**: 2 side-by-side cards — "With Badge" vs "Without Badge". Each shows Count, Avg BSR, Avg Price, Avg Rating. Badge card uses purple accent; No-badge card uses muted styling.

### 4.4 Sales & Pricing (Teal — #009688)

**Purpose**: Revenue, discounts, promotions analysis.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Sales & Pricing                                     │
├──────────────────────────────────────────────────────────┤
│  TOP SELLERS                                             │
│  [Table: ASIN | Brand | Title | Bought/Mo | Price | BSR]│
├──────────────────────────┬───────────────────────────────┤
│  SALES BY PRICE TIER     │  SUBSCRIBE & SAVE             │
│  [bar chart: 4 tiers]    │  Adoption Rate: 42%           │
│  Budget: 8 products      │  Avg Discount: 6.3%           │
│  Mid:    23 products     │  SNS Avg Sales: 1,240/mo      │
│  Premium: 31 products    │  No-SNS Avg:    890/mo        │
│  Luxury:  8 products     │                               │
├──────────────────────────┴───────────────────────────────┤
│  DISCOUNT IMPACT                                         │
│  [grouped bar: discount tier × avg BSR + avg bought]     │
├──────────────────────────────────────────────────────────┤
│  COUPON DISTRIBUTION                                     │
│  [small table: coupon type | count]                      │
└──────────────────────────────────────────────────────────┘
```

### 4.5 Brand Positioning (Indigo — #3F51B5)

**Purpose**: Brand vs BSR scatter view + manufacturer profile.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Brand Positioning                                   │
├───────────────────────────┬──────────────────────────────┤
│  BRAND PERFORMANCE TABLE  │  MARKET CONCENTRATION        │
│  [sortable table]         │  Top 10 Share: 68%           │
│  Brand | Prod | Avg Price │  Total Brands: 34            │
│        | Avg BSR | Seg   │                              │
│                           │  [donut: top10 vs rest]      │
├───────────────────────────┴──────────────────────────────┤
│  TOP MANUFACTURERS                                        │
│  [table: Manufacturer | Products | Avg BSR | K-Beauty]   │
└──────────────────────────────────────────────────────────┘
```

**Segment badges**: Budget / Mid / Premium / Luxury rendered as colored pill badges in the table.

### 4.6 Marketing Keywords (Brown — #795548)

**Purpose**: Title keywords that correlate with BSR performance.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Marketing Keywords                                  │
├──────────────────────────────────────────────────────────┤
│  KEYWORD PERFORMANCE                                      │
│  [horizontal bar chart sorted by Avg BSR ascending]      │
│  Korean      ████████████████  Avg BSR: 4,230   n=18    │
│  Organic     ██████████████    Avg BSR: 6,100   n=24    │
│  Hyaluronic  ████████████      Avg BSR: 8,400   n=11    │
├──────────────────────────────────────────────────────────┤
│  PRICE TIER TOP INGREDIENTS                              │
│  [4-row table: Tier | Products | Top 5 Ingredients]      │
└──────────────────────────────────────────────────────────┘
```

### 4.7 Ingredient Ranking (Navy — #1B2A4A)

**Purpose**: The core output. Top ingredients by weighted market score.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Ingredient Ranking                            HERO  │
│  Weighted Score = Bought/Mo(30%) + BSR(25%) + ...         │
├──────────────────────────────────────────────────────────┤
│  TOP 5 CARDS (horizontal row)                             │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐          │
│  │  #1  │ │  #2  │ │  #3  │ │  #4  │ │  #5  │          │
│  │Jojoba│ │HA    │ │Argan │ │Vit E │ │Shea  │          │
│  │ Oil  │ │Acid  │ │ Oil  │ │      │ │Butter│          │
│  │ 42.3 │ │ 38.1 │ │ 29.7 │ │ 24.2 │ │ 19.8 │          │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘          │
├──────────────────────────────────────────────────────────┤
│  FULL RANKING TABLE (sortable, searchable)               │
│  Rank | Ingredient | Score | # Products | Avg Weight     │
│       | Category   | Avg Price | Price Range | Insight   │
│                                                          │
│  [Search box]  [Filter by Category dropdown]            │
└──────────────────────────────────────────────────────────┘
```

**Top 5 Cards**: Large, prominent. Each card shows rank, name, category badge, weighted score (large number), product count, key insight snippet.

**Table**: Searchable by ingredient name. Filterable by category. Sortable by all numeric columns.

### 4.8 Category Summary (Blue — #2E86AB)

**Purpose**: Ingredient category rollup.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Category Summary                                    │
├──────────────────────────────────────────────────────────┤
│  [Treemap or horizontal bar chart by Total Weighted Score]│
│  Natural Oil: 156.4                                      │
│  Vitamin:      89.2                                      │
│  Botanical:    67.8                                      │
│  ...                                                     │
├──────────────────────────────────────────────────────────┤
│  [Table: Category | Score | Types | Mentions | Avg Price]│
└──────────────────────────────────────────────────────────┘
```

### 4.9 Rising Products (Cyan — #00BCD4)

**Purpose**: Low-review / high-BSR growth candidates.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Rising Products                                     │
│  Low reviews + BSR < 10,000 — new entrants to watch     │
├──────────────────────────────────────────────────────────┤
│  [Cards grid — 2 columns]                                │
│  ┌─────────────────────┐  ┌─────────────────────┐        │
│  │ BSR: 2,341          │  │ BSR: 3,890           │        │
│  │ [Brand]             │  │ [Brand]              │        │
│  │ [Title truncated]   │  │ [Title truncated]    │        │
│  │ $24.99 · ★4.5 · 89r │  │ $18.99 · ★4.3 · 124r │       │
│  │ Ingredients: HA, ... │  │ Ingredients: ...     │        │
│  └─────────────────────┘  └─────────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

### 4.10 Product Detail (Green — #4CAF50)

**Purpose**: Full product data table with all 20 columns.

```
┌──────────────────────────────────────────────────────────┐
│  ████ Product Detail                                      │
│  [Search by title/ASIN]  [Columns toggle]  [Export hint] │
├──────────────────────────────────────────────────────────┤
│  [Horizontally scrollable table]                         │
│  ASIN | Brand | Title | Price | SNS | Bought | Reviews  │
│       | Rating | BSR | Weight | Unit Price | ...         │
│                                                          │
│  Pagination: 25 rows per page                            │
└──────────────────────────────────────────────────────────┘
```

**Column groups** (togglable):
- Basic: ASIN, Brand, Title, Price
- Sales: Bought/Mo, Reviews, Rating, BSR, Weight
- Pricing: SNS Price, Unit Price, Discount%, Coupon
- Marketing: A+, Badge, Variations
- Detail: Customer Says, Ingredients, URL

### 4.11 Raw Sheets (Orange, Purple)

Minimal styling — clean table with search only. These are reference data. Presented with a disclaimer banner: "Raw data — unprocessed".

---

## 5. Chart Type Decisions

| Section | Data | Chart Type | Rationale |
|---------|------|-----------|-----------|
| Consumer Voice | Keyword counts | Horizontal bar | Easy rank comparison |
| Consumer Voice | BSR Top vs Bottom | Grouped horizontal bar | Comparison across 2 groups |
| Badge Analysis | Badge types | Donut | Composition at a glance |
| Sales & Pricing | Price tiers | Vertical bar | Category comparison |
| Sales & Pricing | Discount impact | Grouped bar (BSR + Bought) | Multi-metric comparison |
| Brand Positioning | Market concentration | Donut | Top10 vs rest |
| Marketing Keywords | Keyword × BSR | Horizontal bar sorted by BSR | Performance ranking |
| Ingredient Ranking | Top 5 | Large KPI cards | Hero emphasis |
| Ingredient Ranking | Full list | Searchable table | Detailed reference |
| Category Summary | Weighted score | Horizontal bar | Score ranking |
| Rising Products | Products | Card grid | Scannable at a glance |

**Chart library**: Chart.js (bundled inline, ~200KB minified). No CDN. License: MIT.

---

## 6. Interaction Patterns

### 6.1 Navigation

- Click sidebar item → smooth scroll to section anchor (`#section-slug`)
- Intersection Observer updates active sidebar item as user scrolls
- "Back to top" button (fixed bottom-right) appears after 300px scroll

### 6.2 Tables

- **Sort**: Click column header toggles asc/desc; arrow icon indicates state
- **Search**: Debounced input (300ms) filters visible rows
- **Pagination**: Product Detail table paginates at 25 rows; all others show up to 100 rows with a "show all" toggle
- **Column toggle**: Product Detail only — checkboxes to show/hide column groups

### 6.3 Expand/Collapse

- Market Insight H2 sections: `<details>/<summary>` — open by default, collapsible
- Each major section has a collapse toggle in the section header (useful for navigation-only use)

### 6.4 Hover States

- Table rows: background lighten on hover
- KPI cards: subtle scale(1.02) + shadow elevation on hover
- Chart tooltips: Chart.js built-in dark theme tooltip

### 6.5 Responsive

- Desktop (>= 1024px): Full sidebar + content layout
- Tablet (768–1023px): Sidebar collapses, accessible via hamburger icon
- Mobile (< 768px): No sidebar; sticky section pill navigation at top; tables horizontally scroll

---

## 7. Typography & Spacing

### 7.1 Hierarchy

```
Section header:    20px Bold     — section title
Subsection label:  12px Medium Uppercase tracking-wide  — "TOP SELLERS"
Card value:        28px Bold     — KPI numbers
Card label:        12px Regular  — "Avg BSR"
Table header:      12px Medium Uppercase — column names
Table cell:        13px Regular  — data values
Body text:         14px Regular  — descriptions
Caption/muted:     12px Regular  — secondary info
```

### 7.2 Section Layout Rhythm

```
Section padding:  top 40px, left/right 24px, bottom 48px
Section header:   margin-bottom 24px
Card row gap:     16px
Table margin-top: 24px
Subsection gap:   32px
```

### 7.3 Data Density Rule

Report is data-dense. Default line-height is 1.4 (not 1.6) to fit more information. Tables use compact padding: 8px vertical, 12px horizontal.

---

## 8. Section Color System

Every section has:
1. **Left border accent** (3px solid, section color) on the section header
2. **Section icon dot** (8px circle, section color) in the sidebar nav
3. **Chart palette** derived from section color (main color + lighter tints)
4. **Badge/pill** in section color for category labels

The section color never floods the background. It appears only as accent — borders, icons, selected states. Background remains dark (#1A1D27) throughout.

---

## 9. Technical Architecture (Single HTML File)

### 9.1 File Structure

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AMZ Insight Report — {keyword}</title>
  <style>
    /* All CSS inline — design tokens + component styles */
  </style>
</head>
<body>
  <!-- Header -->
  <!-- Sidebar nav -->
  <!-- Main content: sections as <section id="..."> -->

  <script>
    // 1. Report data as JSON
    const REPORT_DATA = { /* injected by Python */ };

    // 2. Chart.js bundled (minified inline)

    // 3. Application logic:
    //    - Markdown renderer (headings, bold, lists, inline code)
    //    - Table renderer (sort, search, paginate)
    //    - Chart initializer
    //    - Sidebar intersection observer
    //    - Responsive sidebar toggle
  </script>
</body>
</html>
```

### 9.2 Data Injection Pattern

Python `html_report_builder.py` generates HTML by:
1. Loading a template string (or inline template)
2. Serializing all report data to JSON
3. Injecting into `const REPORT_DATA = %s;` placeholder
4. Returning HTML bytes

No external requests. The file works fully offline.

### 9.3 Chart.js Integration

Chart.js UMD bundle (~210KB) inlined as a single `<script>` block. This is the largest dependency. All other JS is vanilla.

Alternative if file size is a concern: write a minimal canvas-based bar/donut renderer (~3KB) that covers only the chart types used.

### 9.4 Markdown Renderer

Lightweight inline parser supporting:
- `#` through `####` headings → `<h1>`–`<h4>`
- `**bold**` → `<strong>`
- `*italic*` → `<em>`
- `- item` unordered lists → `<ul><li>`
- `1. item` ordered lists → `<ol><li>`
- blank line → paragraph break
- `---` → `<hr>`

Does NOT support: tables (not in AI output), code blocks, images.

---

## 10. Deliverable Files

```
mockup/html-report/
├── report.html              # Full static mockup with hardcoded sample data
└── sample-data.json         # Sample REPORT_DATA structure

docs/02-design/html-report/
├── ux-spec.md               # This document
└── component-map.md         # HTML → Python builder mapping
```

Production output:
```
amz_researcher/services/
└── html_report_builder.py   # New service: build_html_report() -> bytes
```

---

## 11. Accessibility (WCAG 2.1 AA)

- Color alone never conveys information — text labels always accompany color indicators
- Focus states visible (outline: 2px, offset 2px, section color)
- Table headers use `<th scope="col">` and `<th scope="row">`
- Interactive elements minimum 44×44px touch target
- `prefers-color-scheme: light` media query provides a light mode variant
- `prefers-reduced-motion`: disables scroll animations

---

## 12. Estimated File Size

| Component | Size |
|-----------|------|
| HTML structure + CSS | ~15 KB |
| Chart.js (minified inline) | ~210 KB |
| Application JS | ~8 KB |
| Report data (JSON) | ~50–200 KB depending on product count |
| **Total** | **~290–430 KB** |

Acceptable for Slack file upload (Slack limit: 1GB). Opens instantly in browser.
