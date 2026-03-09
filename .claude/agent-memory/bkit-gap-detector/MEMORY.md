# Gap Detector Memory

## Project: webhook-service

### Architecture
- Python FastAPI project with pydantic-settings for config (`app/config.py`)
- DB connector at `lib/mysql_connector.py` uses pymysql, context manager pattern
- 7 MySQL environments: CFO, BOOSTA, BOOSTAERP, BOOSTAADMIN, SCM, MART, BOOSTAAPI
- Config pattern: `{ENV}_HOST`, `{ENV}_PORT`, `{ENV}_USER`, `{ENV}_PASSWORD`, `{ENV}_DATABASE`
- Jobs in `jobs/` directory, shared libs in `lib/`

### Known Security Issues
- `lib/slack.py:103` has SQL injection via f-string email interpolation (HIGH)
- `jobs/meta_ads_manager.py:68-71` uses f-string for date in SQL (LOW)
- No `.env.example` file exists despite 35+ required env vars

### Completed Analyses
- `mysql-connector-refactor`: 97% match rate (2026-02-26). All R1-R6 requirements met.
  - Analysis at: `docs/03-analysis/mysql-connector-refactor.analysis.md`
- `amazon-researcher`: 98% match rate (2026-03-06). 0 Critical/Major gaps, 5 Minor.
  - Analysis at: `docs/03-analysis/amazon-researcher.analysis.md`
  - Key findings: impl improves on design (DI pattern, guard clauses, URL encoding)
  - Module at: `amz_researcher/` (Browse.ai + Gemini + Excel pipeline)
- `amazon-researcher-v2`: 99% match rate (2026-03-07). 0 Critical/Major gaps, 1 Minor.
  - Analysis at: `docs/03-analysis/amazon-researcher-v2.analysis.md`
  - V2 scope: ProductDetail v2 (dict fields), MySQL cache (AmzCacheService), BSR-based weights, HTML parser, checkpoint.py deletion
  - 190 comparison items across 12 design sections, all matched
  - 6 implementation improvements (error handling, guard clauses, dict filter, prompt refinement)
  - 1 minor: beautifulsoup4 missing version pin in pyproject.toml
- `amazon-researcher-v4`: 99% match rate (2026-03-09 v3). 0 Critical/Partial gaps.
  - Analysis at: `docs/03-analysis/amazon-researcher-v4.analysis.md`
  - V4 scope: Browse.ai -> Bright Data API, batch collection, category-based analysis, DB pipeline
  - 228 design items: 215 matched, 10 changed (compatible), 0 partial, 30 added
  - Key: adapter pattern instead of modifying analyzer.py, V3 backward compat added
  - New files: bright_data.py, data_collector.py, product_db.py, collect.py, v4_bright_data.py migration
  - v3 fix: retry 1x in trigger_collection, admin Slack DM on collection/DB failure
- `amazon-researcher-v5`: 98% match rate (2026-03-09). 0 Critical gaps, 2 Partial (Minor).
  - Analysis at: `docs/03-analysis/amazon-researcher-v5.analysis.md`
  - V5 scope: Dead code cleanup, 7 new analysis functions, statistical testing, Excel expansion
  - 25 comparison items: 23 MATCH, 2 PARTIAL, 0 MISSING
  - 2 impl improvements: stat_test early integration, run_research pipeline coverage
  - Partials: analyze_by_bsr() missing stat_test, Product Detail URL col 20 not written
- `excel-report-v6`: 100% match rate (2026-03-09). 0 gaps.
  - Analysis at: `docs/03-analysis/excel-report-v6.analysis.md`
  - V6 scope: TAB_COLORS consolidation, Product Detail URL fix, Consumer Voice BSR section, Badge Analysis stat test + threshold, 3 new sheets (Sales & Pricing, Brand Positioning, Marketing Keywords), build_excel() desired_order update
  - 146 comparison items across 10 design sections, all matched
  - 3 impl improvements: defensive .get() access, type guard in ingredient join, Item# comment annotations
  - Note: V5 partial (URL col 20 not written) resolved in V6
- `keyword-search-analysis`: 99% match rate (2026-03-09). 0 Critical/Major/Minor gaps.
  - Analysis at: `docs/03-analysis/keyword-search-analysis.analysis.md`
  - Scope: Keyword search via Bright Data discover_by=keyword, 9-sheet Excel, 2-layer ingredient enrichment
  - 132 comparison items: 127 MATCH, 4 CHANGED (compatible), 0 MISSING, 0 PARTIAL
  - 8 impl improvements: JSON parsing, Decimal->float, try/except guards, variations fallback, bought_past_month injection
  - New methods: trigger_keyword_search, process_search_snapshot, get_keyword_cache, get_keyword_products, save/update_keyword_search_log, build_keyword_market_analysis, build_keyword_excel, run_keyword_analysis, _prepare_for_gemini, _adapt_search_for_analyzer
- `html-insight-report`: 96% match rate (2026-03-09 v2). 0 Critical gaps, 0 Partial (Medium+).
  - Analysis at: `docs/03-analysis/html-insight-report.analysis.md`
  - Scope: Single-file HTML report with Chart.js, 12-section category / 9-section keyword
  - 90 comparison items: 80 MATCH, 9 CHANGED, 1 PARTIAL, 0 MISSING (Medium+)
  - Iteration 2 resolved: Chart.js CDN->inline bundle, hamburger button, Brand Positioning scatter chart
  - Remaining backlog (all Low/a11y): column toggle, focus states, th scope, reduced-motion, light mode, sticky pills
  - Implementation at: `amz_researcher/services/html_report_builder.py` (all-in-one)

### Key Callers of MysqlConnector
- `jobs/cash_mgmt.py` - upsert_data, get_column_max_length (CFO)
- `jobs/meta_ads_manager.py` - read_query_table (BOOSTA)
- `jobs/global_boosta.py` - read_query_table with dynamic host
- `jobs/upload_financial_db.py` - upsert_data (CFO)
- `lib/slack.py` - read_query_table (BOOSTA, lazy import)
