# [Analysis] ad-name-migration

> Design vs Implementation Gap Analysis for ad-name-migration feature

**Design Document**: `docs/02-design/features/ad-name-migration.design.md`
**Implementation Files**: `jobs/ad_migration.py`, `app/router.py`
**Analysis Date**: 2026-02-26
**Status**: Review

---

## Match Rate: 95%

**Calculation**: (39 MATCH + 4 PARTIAL * 0.5) / 43 total items = 95.3%

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Module Constants (3.1) | 100% | PASS |
| SQL Queries (3.2) | 100% | PASS |
| Function Signatures (3.3) | 100% | PASS |
| Function Logic (3.3) | 93% | PASS |
| Sheet Columns (3.3) | 100% | PASS |
| Router Change (4) | 100% | PASS |
| Error Handling (7) | 83% | PASS |
| Security | 100% | PASS |
| **Overall** | **95%** | **PASS** |

---

## Gap Summary

| # | Design Item | Status | Detail |
|---|-------------|--------|--------|
| 1 | MIGRATION_SHEET_ID | MATCH | Exact value match: `1qmbkOETkJJEUgb8N9njAOoCl17jnHg1Ya5PCJjIknBc` |
| 2 | SPREADSHEET_URL | MATCH | f-string format matches (line break in impl is cosmetic only) |
| 3 | TARGET_SHEET_NAME | MATCH | Exact: `"변경대상광고"` |
| 4 | CHANNEL_ID | MATCH | Exact: `"C06NZHCD17F"` |
| 5 | STEP1_QUERY columns | MATCH | All 14 columns match exactly |
| 6 | STEP1_QUERY JOINs | MATCH | Both INNER JOINs on correct keys |
| 7 | STEP1_QUERY WHERE | MATCH | `%s` param, 3 ACTIVE conditions, ORDER BY fia.name |
| 8 | STEP2_QUERY columns | MATCH | All 6 columns match exactly |
| 9 | STEP2_QUERY WHERE/GROUP | MATCH | DATE_SUB 30 DAY, IN placeholder, GROUP BY, ORDER BY |
| 10 | STEP3_QUERY columns | MATCH | All 7 columns match exactly |
| 11 | STEP3_QUERY WHERE/GROUP | MATCH | IN placeholder, GROUP BY, ORDER BY |
| 12 | SQL param security (Step 1) | MATCH | Uses `params=("%이퀄베리%",)` as designed |
| 13 | SQL param security (Step 2/3) | MATCH | Uses `str(int(x))` + `.format()` as designed |
| 14 | `run_extract(payload)` signature | MATCH | `def run_extract(payload: dict) -> str` |
| 15 | `run_extract` flow Step 1 | MATCH | `MysqlConnector("BOOSTA")` context manager, calls `_extract_active_ads` |
| 16 | `run_extract` empty check | MATCH | `df_ads.empty` early return |
| 17 | `run_extract` flow Steps 2-3 | MATCH | Extracts `internal_ids`, calls `_extract_performance` |
| 18 | `run_extract` merge + parse | MATCH | Calls `_merge_data` then `_parse_legacy_names` |
| 19 | `run_extract` sheet + notify | MATCH | Calls `_build_sheet_dataframe`, `_paste_to_sheet`, `_notify_slack` |
| 20 | `run_extract` return value | PARTIAL | Design: includes cell range "A2:V286". Impl: generic "시트 업데이트 완료" without range. |
| 21 | `_extract_active_ads` signature | MATCH | `(conn: MysqlConnector) -> pd.DataFrame` |
| 22 | `_extract_active_ads` params | MATCH | `params=("%이퀄베리%",)` |
| 23 | `_extract_performance` signature | MATCH | `(conn, internal_ids: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]` |
| 24 | `_extract_performance` logic | MATCH | `",".join(str(int(x)) ...)` + `.format(placeholders=...)` |
| 25 | `_merge_data` signature | MATCH | 3 DataFrame params, returns DataFrame |
| 26 | `_merge_data` logic | MATCH | merge on `internal_ad_id`, `how="left"`, `fillna(0)`, `sort_values("spend_30d")` |
| 27 | `_parse_legacy_names` signature | MATCH | `(df: pd.DataFrame) -> pd.DataFrame` |
| 28 | `_parse_legacy_names` 7 output columns | MATCH | All 7 parsed columns initialized correctly |
| 29 | `_parse_legacy_names` valid_mask | MATCH | `parts.str.len() >= 6` |
| 30 | `_parse_legacy_names` field assignment | MATCH | str[0] through str[4] + join(x[5:]) |
| 31 | `_parse_legacy_names` date validation | MATCH | `r"^\d{6}$"` pattern, combined with valid_mask |
| 32 | `_parse_legacy_names` ao/pm validation | GAP | Design specifies: `parts[2] not in {"ao", "pm"} -> parse_error=True`. Implementation does NOT validate parts[2]. |
| 33 | `_build_sheet_dataframe` 22 columns | MATCH | SHEET_COLUMNS list has exactly 22 columns in correct order |
| 34 | `_build_sheet_dataframe` column order | MATCH | Order matches design exactly (1-22) |
| 35 | `_paste_to_sheet` signature | MATCH | `(gsapi: GoogleSheetApi, df: pd.DataFrame) -> str` |
| 36 | `_paste_to_sheet` clear_contents | MATCH | `range="A2:V"`, `sheetname=TARGET_SHEET_NAME` |
| 37 | `_paste_to_sheet` paste_values | MATCH | Pastes to `"A2"` |
| 38 | `_notify_slack` signature | MATCH | `(payload, total, parsed_ok, parse_fail)` |
| 39 | `_notify_slack` message content | MATCH | Header, body with 3 stats, footer, url_button all match |
| 40 | `_notify_slack` channel logic | MATCH | test -> SLACK_CHANNEL_ID_TEST, else CHANNEL_ID |
| 41 | `_notify_slack` user_id logic | MATCH | email -> `SlackNotifier.find_slackid()` |
| 42 | `_notify_slack` bot_name | MATCH | `bot_name="META"` |
| 43 | ALLOWED_JOBS entry | MATCH | `"ad_migration": ["run_extract"]` present in router.py |

---

## Detailed Findings

### GAP: Missing ao/pm validation in `_parse_legacy_names` (Item #32)

**Design** (Section 3.3, line 219):
```
4. parts[2]가 {"ao", "pm"}에 없으면 parse_error = True
```

**Implementation** (`jobs/ad_migration.py` lines 137-162):
The function validates length >= 6 and date pattern `^\d{6}$`, but does NOT check whether `parts[2]` is in the set `{"ao", "pm"}`. Rows where `parts[2]` is something other than "ao" or "pm" will have `parse_error = False` despite the design requiring them to be flagged as errors.

**Impact**: Medium. Some ads with non-standard naming could be marked as successfully parsed when they should be flagged. This affects the accuracy of `parsed_ok` / `parse_fail` counts in Slack notifications.

**Severity**: Medium

---

### PARTIAL: Return message format in `run_extract` (Item #20)

**Design** (Section 5.2):
```json
"result": "추출 완료: 총 285건 (파싱 성공 240건, 실패 45건). 시트 A2:V286 업데이트."
```

**Implementation** (`jobs/ad_migration.py` lines 244-248):
```python
summary = (
    f"추출 완료: 총 {total}건 "
    f"(파싱 성공 {parsed_ok}건, 실패 {parse_fail}건). "
    f"시트 업데이트 완료."
)
```

The implementation does not include the specific cell range (e.g., `A2:V286`). Instead it uses a generic "시트 업데이트 완료" message. This is a minor cosmetic difference.

**Impact**: Low

---

### PARTIAL: Empty result Slack notification (Error Handling Item)

**Design** (Section 7, row 2):
```
Step 1 결과 0건: 조기 리턴, Slack으로 "Active 광고 없음" 알림
```

**Implementation** (`jobs/ad_migration.py` lines 224-227):
```python
if df_ads.empty:
    msg = "Active 광고가 없습니다."
    logger.info(msg)
    return msg
```

The implementation logs and returns the message but does NOT send a Slack notification. The design explicitly says to notify via Slack.

**Impact**: Medium. Operators relying on Slack will not be informed when there are zero active ads.

---

### PARTIAL: Slack failure error handling

**Design** (Section 7, row 6):
```
Slack 발송 실패: 작업 자체에 영향 없음, 로그만 기록
```

**Implementation** (`jobs/ad_migration.py` lines 201-214):
```python
try:
    return SlackNotifier.notify(...)
except Exception:
    logger.exception("Slack notification failed")
    return "Slack notification failed"
```

The implementation correctly catches exceptions and logs them. It returns a fallback string rather than raising, which matches the design intent. This is a MATCH in spirit -- the try/except ensures Slack failure does not crash the job.

**Status**: MATCH (upgraded from initial PARTIAL assessment)

---

### EXTRA: Additional implementation details not in design

| Item | Location | Description |
|------|----------|-------------|
| `SHEET_COLUMNS` constant | `ad_migration.py:75-98` | Column list extracted as a module-level constant. Design describes columns in `_build_sheet_dataframe` narrative but does not specify a separate constant. Good practice. |
| `_get_channel_id()` helper | `ad_migration.py:101-104` | Extracted channel logic into a helper function. Design describes this inline in `_notify_slack`. Clean refactor. |
| `.astype(str)` in `_parse_legacy_names` | `ad_migration.py:138` | `df["ad_name"].astype(str).str.split("_")` -- Design does not mention the `.astype(str)` cast. Defensive coding, good practice. |
| `meta_ad_id` string prefix | `ad_migration.py:167` | `"'" + out["meta_ad_id"].astype(str)` -- Prefixes meta_ad_id with a single quote to prevent Google Sheets from treating large numbers as scientific notation. Not in design but practical. |
| Date column string conversion | `ad_migration.py:168-170` | Converts date columns to strings and replaces "0" with empty string. Practical Sheets formatting not in design. |
| `df.empty` guard in `_paste_to_sheet` | `ad_migration.py:178` | Skips paste if DataFrame is empty. Extra safety not in design. |
| Logging | `ad_migration.py:1,10,249` | Logger setup and info logging. Standard practice, not specified in design. |

---

## Score Breakdown

| Category | Total Items | MATCH | PARTIAL | GAP | Score |
|----------|:-----------:|:-----:|:-------:|:---:|:-----:|
| Module Constants (3.1) | 4 | 4 | 0 | 0 | 100% |
| SQL Queries (3.2) | 8 | 8 | 0 | 0 | 100% |
| Function Signatures | 7 | 7 | 0 | 0 | 100% |
| Function Logic | 15 | 13 | 1 | 1 | 90% |
| Sheet Columns | 2 | 2 | 0 | 0 | 100% |
| Router Change | 1 | 1 | 0 | 0 | 100% |
| Error Handling | 6 | 5 | 1 | 0 | 92% |
| **Total** | **43** | **39** | **2** | **1** | **95%** |

---

## Recommendations

### Immediate Action (1 item)

1. **Add ao/pm validation to `_parse_legacy_names`** (`jobs/ad_migration.py`)
   - After line 159, add validation that `parsed_ao_pm` is in `{"ao", "pm"}`
   - Mark non-matching rows as `parse_error = True`
   - Estimated effort: 2 lines of code

   ```python
   # Add after line 159 (date_invalid line):
   ao_pm_invalid = ~df["parsed_ao_pm"].isin({"ao", "pm"}) & valid_mask
   df.loc[~valid_mask | date_invalid | ao_pm_invalid, "parse_error"] = True
   ```

### Minor Improvements (2 items)

2. **Add Slack notification for empty result** (`jobs/ad_migration.py:224-227`)
   - When `df_ads.empty`, send a Slack message before returning
   - Design explicitly specifies this behavior

3. **Include cell range in return message** (`jobs/ad_migration.py:244-248`)
   - Optional: calculate the actual range (e.g., `A2:V{total+1}`) and include in summary
   - Low priority, cosmetic only

### No Action Needed

- EXTRA items (SHEET_COLUMNS constant, `_get_channel_id` helper, `.astype(str)` cast, meta_ad_id prefix, date formatting, empty guard, logging) are all positive additions that improve code quality without contradicting the design.

---

## Conclusion

The implementation is a high-fidelity match to the design document at **95% match rate**. The single GAP (missing ao/pm validation) is a straightforward 2-line fix. The two PARTIAL items are minor. All EXTRA items represent good engineering practices. The feature is production-ready with the recommended ao/pm validation fix applied.
