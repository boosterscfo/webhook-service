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
- `amazon-researcher-v4`: 98% match rate (2026-03-08). 0 Critical gaps, 3 Partial (error handling).
  - Analysis at: `docs/03-analysis/amazon-researcher-v4.analysis.md`
  - V4 scope: Browse.ai -> Bright Data API, batch collection, category-based analysis, DB pipeline
  - 247 comparison items: 242 matched, 11 improvements, 3 partial, 3 added, 1 changed
  - Key: adapter pattern instead of modifying analyzer.py, V3 backward compat added
  - New files: bright_data.py, data_collector.py, product_db.py, collect.py, v4_bright_data.py migration

### Key Callers of MysqlConnector
- `jobs/cash_mgmt.py` - upsert_data, get_column_max_length (CFO)
- `jobs/meta_ads_manager.py` - read_query_table (BOOSTA)
- `jobs/global_boosta.py` - read_query_table with dynamic host
- `jobs/upload_financial_db.py` - upsert_data (CFO)
- `lib/slack.py` - read_query_table (BOOSTA, lazy import)
