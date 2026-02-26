# Changelog

All notable changes to the webhook-service project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2026-02-26] - MySQL Connector Refactor

### Added
- `DBConfig` dataclass for centralized environment-based database configuration
- Support for 7 database environments: CFO, BOOSTA, BOOSTAERP, BOOSTAADMIN, BOOSTAAPI, SCM, MART
- `delete_and_insert()` method for atomic delete + insert operations in single transaction
- Parameterized query support in `read_query_table()` via optional `params` argument
- Transaction control with `autocommit=False` and exception rollback in `__exit__`
- Backtick quoting for all table and column identifiers to prevent reserved word conflicts
- Full Unicode support via `charset="utf8mb4"` in connection initialization

### Changed
- Upsert syntax from `AS new` alias (MySQL 8.0.20+ only) to `VALUES()` syntax (universal MySQL 8.0+)
- `get_column_max_length()` from f-string SQL injection to parameterized query
- Connection initialization to use explicit transaction control (`autocommit=False`)

### Fixed
- SQL injection vulnerabilities via parameterized queries with `%s` placeholders
- Transaction atomicity for multi-statement operations
- Double-close safety in `close()` method via truthy guards

### Security
- All SQL methods now use parameterized queries
- Eliminated hardcoded SQL in connector (callers remain responsibility)
- Added transaction rollback on exception

### Maintained
- 100% backward compatibility with all 5 existing callers
- Public attributes (`connection`, `cursor`) unchanged
- Legacy `connectClose` alias preserved
- Context manager interface unchanged

---

## Unreleased

(Future changes will be documented here)
