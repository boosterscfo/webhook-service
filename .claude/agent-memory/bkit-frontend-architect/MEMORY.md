# Frontend Architect Memory

## Project: amz_researcher HTML Report

### Key File Locations
- Excel builder (reference for data structure): `amz_researcher/services/excel_builder.py`
- Data models: `amz_researcher/models.py`
- HTML report mockup: `mockup/html-report/report.html`
- UX spec: `docs/02-design/html-report/ux-spec.md`
- Component map (builder guide): `docs/02-design/html-report/component-map.md`

### Report Architecture Decisions
- Dark theme (#0F1117 bg) with section accent colors from TAB_COLORS
- Single-page scroll with fixed left sidebar (not tabbed) — better for reading
- Each section has a unique color identity used only for accents, never flood fills
- Chart.js 4.x inlined for offline use (Slack delivery requirement)
- REPORT_DATA injected as inline JSON constant — no external requests
- Section colors follow TAB_COLORS: Market Insight=#E91E63, Consumer Voice=#FF9800, etc.

### Data Flow: Excel → HTML
build_html_report() mirrors build_excel() signature exactly.
analysis_data dict keys → section mapping documented in component-map.md.

### Conditional Rendering
Same graceful degradation as excel_builder: sections omitted when data absent.
Sidebar nav dynamically reflects only rendered sections.

### Builder Implementation
- Output file: `amz_researcher/services/html_report_builder.py`
- `build_html()` → report_type="category" (12 sections)
- `build_keyword_html()` → report_type="keyword" (9 sections, hides badge/brand/rising)
- Chart.js loaded via CDN (`cdn.jsdelivr.net/npm/chart.js@4.4.7`) — NOT inlined
- All sections rendered by JS; sections with no data use `el.style.display = 'none'`
- TableController class handles sort + search + pagination for all data tables
- Intersection Observer updates active sidebar nav on scroll
- `esc()` helper for XSS safety on all user strings
