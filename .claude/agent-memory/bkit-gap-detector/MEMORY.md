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

### Key Callers of MysqlConnector
- `jobs/cash_mgmt.py` - upsert_data, get_column_max_length (CFO)
- `jobs/meta_ads_manager.py` - read_query_table (BOOSTA)
- `jobs/global_boosta.py` - read_query_table with dynamic host
- `jobs/upload_financial_db.py` - upsert_data (CFO)
- `lib/slack.py` - read_query_table (BOOSTA, lazy import)
