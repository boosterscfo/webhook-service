# Amazon Researcher v3 Error Handling & Failure Risk Analysis

## Analysis Target
- Path: `amz_researcher/`
- Files analyzed: 10
- Analysis date: 2026-03-08

## Quality Score: 58/100

---

## Issues Found

### CRITICAL (Immediate Fix Required)

| # | File | Line | Risk | Category | Current Behavior | Recommended Fix |
|---|------|------|------|----------|------------------|-----------------|
| 1 | `orchestrator.py` | 282-284 | HIGH | Swallowed exceptions | Top-level `except Exception` catches everything including `KeyboardInterrupt`-adjacent errors. Sends error to Slack but **the caller never knows the pipeline failed**. If `_msg()` itself fails inside the except block (e.g., Slack is down), the error is silently lost. | Re-raise after notification, or return a result object with success/failure status. Catch `Exception` not `BaseException`. Add try/except around the `_msg` call inside the except block. |
| 2 | `gemini.py` | 289-291 | HIGH | Swallowed exceptions + No retry | `generate_market_report()` catches all exceptions and returns empty string `""`. No retry at all. The orchestrator then **caches this empty string** at line 252 if `report_md` is truthy -- but empty string is falsy so it skips caching. However, if Gemini returns a partial/garbage response that doesn't raise, that gets cached for 30 days. | Add at least 1 retry (like `_extract_batch`). Validate response is non-trivial before returning. |
| 3 | `gemini.py` | 246 | HIGH | Swallowed exceptions | `_extract_batch()` returns empty list `[]` on all failures after retries. The caller (`extract_ingredients`) silently continues, meaning **products lose their ingredient data permanently** -- and the orchestrator caches these missing results. Next run with cache will treat them as "no ingredients found". | Return a failure indicator so the caller can distinguish "0 ingredients extracted" from "extraction failed". Don't cache failed extractions. |
| 4 | `cache.py` | 87-93, 179-185, 274-280, 337-345, 431-438 | HIGH | Data loss risk | All `save_*_cache()` methods catch exceptions and only log. If MySQL is temporarily down, **all computed results are lost** -- the pipeline continues but nothing is persisted. Next run will redo all expensive API calls. | Implement write-ahead: save intermediate results to local file (JSON) before attempting MySQL. Or propagate the error so the orchestrator can decide. |
| 5 | `orchestrator.py` | 170-177 | HIGH | Swallowed exceptions + Data loss | When `browse.run_details_batch()` fails entirely, the exception is caught, `new_details = []` is set, and the pipeline continues with only cached data. If `cached_details` is also empty, the pipeline proceeds with **zero details**, producing a meaningless analysis that gets cached. | Check `len(all_details)` after this block. If zero (or below a threshold), abort the pipeline with a clear message instead of producing garbage output. |

### WARNING (Improvement Recommended)

| # | File | Line | Risk | Category | Current Behavior | Recommended Fix |
|---|------|------|------|----------|------------------|-----------------|
| 6 | `gemini.py` | 166 | MEDIUM | Missing timeouts | `httpx.AsyncClient(timeout=120.0)` is a single global timeout. For `generate_market_report()` with large prompts, 120s may be insufficient. There is no **connect timeout** vs **read timeout** distinction. | Use `httpx.Timeout(connect=10.0, read=180.0, write=30.0)` for granular control. |
| 7 | `browse_ai.py` | 189-193 | MEDIUM | Missing timeouts | `httpx.AsyncClient(timeout=30.0)` -- the polling loop calls `_poll_task` with 20 attempts x 30s sleep = **600s max wall time**, but no overall deadline. If Browse.ai hangs returning 200 with "running" status forever, the pipeline blocks for 10+ minutes. | Add an overall wall-clock deadline (e.g., `asyncio.wait_for` wrapper). |
| 8 | `slack_sender.py` | 27-33, 40-52 | MEDIUM | Swallowed exceptions + No retry | All Slack API calls catch exceptions, log, and **return silently**. If Slack is rate-limited (429), the user gets no notification at all. No retry logic. | Add retry with exponential backoff for 429/5xx. For critical messages (final summary, error notification), propagate failure. |
| 9 | `slack_sender.py` | 80-83 | MEDIUM | Partial failure propagation | File upload Step 2 (`POST upload_url`) does not check response status. If the upload fails silently, Step 3 completes but the file is empty/corrupt in Slack. | Add `resp.raise_for_status()` after the upload POST. Check response before proceeding to Step 3. |
| 10 | `gemini.py` | 194, 200 | MEDIUM | No retry on external calls | `_extract_batch` has `max_retries=1` (so 2 total attempts), but only retries on **parse failure**. If the HTTP request itself gets a 429 (rate limit) or 503, it raises `httpx.HTTPStatusError` which is caught by the same generic `except Exception`, consuming a retry on a transient error without backoff. | Separate HTTP errors from parse errors. Add exponential backoff for 429/503. |
| 11 | `orchestrator.py` | 217 | MEDIUM | No retry on external calls | `gemini.extract_ingredients()` is called once. If it fails (network blip, rate limit), there is no retry at the orchestrator level. All Gemini work is lost. | Add orchestrator-level retry for the Gemini extraction step, or ensure the batch-level retry in `_extract_batch` is sufficient (currently only 1 retry). |
| 12 | `orchestrator.py` | 251 | MEDIUM | No retry on external calls | `gemini.generate_market_report()` is called once with no retry. If it returns `""` (failure), the pipeline continues with an empty market report, producing a degraded Excel file. | Retry at least once. If still empty, notify the user that the report is missing rather than silently omitting it. |
| 13 | `cache.py` | 131-134 | MEDIUM | Silent data corruption | `_json_or_empty(v)` calls `json.loads(v)` without try/except. If the stored JSON is corrupt, this will raise `json.JSONDecodeError`, which is caught by the outer `except Exception` at line 111, causing the **entire detail cache to return empty** even if only one record is corrupt. | Wrap `json.loads` in try/except per-record. Skip corrupt records instead of failing the entire batch. |
| 14 | `cache.py` | 383-394 | MEDIUM | Partial failure propagation | `harmonize_common_names()` iterates over all canonical names in a single transaction. If one UPDATE fails, the entire harmonization is rolled back (or partially applied depending on MySQL autocommit). | Use per-batch commits or handle individual failures gracefully. |
| 15 | `browse_ai.py` | 269-271 | MEDIUM | Swallowed exceptions | `run_detail()` catches all exceptions and returns `None`. The caller cannot distinguish between "product not found" (permanent) and "network timeout" (transient). | Return a typed result (success/failure with reason) instead of `None`, so the caller can decide whether to retry. |
| 16 | `orchestrator.py` | 287-290 | MEDIUM | Partial failure propagation | Admin DM notification in the except block -- if `slack.send_dm()` itself throws, it will be caught by its own internal try/except (line 125 in slack_sender.py), but the original error context is preserved. However, if `settings.AMZ_ADMIN_SLACK_ID` is misconfigured, the admin never gets notified. | Validate admin ID at startup. Add fallback notification (e.g., log to a monitoring channel). |
| 17 | `market_analyzer.py` | 278 | MEDIUM | Silent data corruption | `detect_rising_products()` computes `median_reviews` by indexing `sorted(p.reviews for p in products)[len(products) // 2]`. If `products` is empty, this raises `IndexError`. | Add guard: `if not products: return []`. |
| 18 | `analyzer.py` | 158-159 | LOW | Silent data corruption | `max_position` and `max_reviews` use `default=1`, which is correct for avoiding division by zero. However, if `search_products` is empty, the function continues and returns empty lists -- no error, but the caller doesn't know something is wrong. | Add early return or assertion for empty input. |
| 19 | `cache.py` | 44-46, 92-93, 111-113, 184-185, 236-238, 261-262, 279-280, 296-298, 365-366, 393-394, 416-417, 437-438 | LOW | Swallowed exceptions | Every single cache method catches `Exception` and returns a default (None, empty dict, empty set, 0). While this is intentional (cache is non-critical), the pattern means **MySQL connection failures are never surfaced**. If the DB is down for the entire run, all caching silently fails. | Add a health-check or connection test at startup. Log a single warning if multiple cache operations fail consecutively. |
| 20 | `html_parser.py` | 32-34, 63-65, 96-98 | LOW | Swallowed exceptions | All three parser functions catch all exceptions and return empty defaults. Malformed HTML silently produces empty results. | These are acceptable for HTML parsing, but consider logging the first N characters of the problematic HTML for debugging. |
| 21 | `browse_ai.py` | 85 | LOW | Silent data corruption | `rating=float(item.get("Rating", 0) or 0)` -- if Rating is a non-numeric string (e.g., "N/A"), this will raise ValueError, caught nowhere in `parse_search_results`. The entire product list parsing stops. | Wrap in try/except like `parse_reviews`. |
| 22 | `orchestrator.py` | 291-294 | LOW | Partial failure propagation | `finally` block calls `close()` on all three services. If `browse.close()` raises, `gemini.close()` and `slack.close()` are never called, leaking connections. | Use `contextlib.AsyncExitStack` or individual try/except for each close call. |
| 23 | `cache.py` | 116-134 | LOW | Silent data corruption | Helper functions `_int_or_none`, `_float_or_none`, `_str_or_empty`, `_json_or_empty` are redefined on every loop iteration inside `get_detail_cache`. Besides being a minor performance issue, if a column is missing from the DB result, it raises `KeyError`, not caught at the row level. | Define helpers outside the loop. Access columns with `.get()` or handle `KeyError` per-row. |

---

## Risk Summary by Category

| Category | Critical | Warning | Info | Total |
|----------|----------|---------|------|-------|
| Swallowed exceptions | 3 | 3 | 2 | 8 |
| Partial failure propagation | 1 | 2 | 1 | 4 |
| Missing timeouts | 0 | 2 | 0 | 2 |
| Data loss risk | 1 | 0 | 0 | 1 |
| No retry on external calls | 1 | 3 | 0 | 4 |
| Silent data corruption | 0 | 2 | 2 | 4 |

---

## Pipeline Failure Scenarios

### Scenario A: Gemini API returns garbage for ingredient extraction
1. `_extract_batch` fails to parse JSON
2. Tries `_try_repair_json` -- if it partially succeeds, returns **incomplete results**
3. Incomplete results are **cached permanently** in MySQL
4. Future runs use cached incomplete data, never re-extracting
5. **Impact**: Permanently degraded analysis quality

### Scenario B: MySQL goes down mid-pipeline
1. Search results fetched from Browse.ai successfully
2. `save_search_cache()` fails silently (logged only)
3. Detail crawling succeeds, `save_detail_cache()` fails silently
4. Gemini extraction succeeds, `save_ingredient_cache()` fails silently
5. Excel is generated and uploaded to Slack successfully
6. **Impact**: All expensive API work is lost. Next run repeats everything (cost: Browse.ai credits + Gemini tokens)

### Scenario C: Browse.ai batch fails, no cached details exist
1. `run_details_batch()` raises exception
2. Caught at orchestrator line 170, `new_details = []`
3. `cached_details` is empty (first run or expired cache)
4. `all_details = []` -- pipeline continues with zero product details
5. Gemini extraction runs on zero products, returns empty
6. Excel is generated with empty data and uploaded to Slack
7. **Impact**: User receives a meaningless empty Excel file

### Scenario D: Slack rate-limited during file upload
1. Summary message sent successfully
2. `upload_file()` Step 1 (getUploadURL) gets 429 rate limit
3. `raise_for_status()` throws, caught by outer except
4. Logged and returns -- user sees the summary but **never receives the Excel file**
5. No retry, no notification that upload failed
6. **Impact**: User thinks analysis is complete but lacks the Excel deliverable

---

## Top 5 Recommended Fixes (Priority Order)

### 1. Guard against empty pipeline progression
```python
# orchestrator.py, after Step 2
if not all_details:
    await _msg("No product details available. Aborting analysis.", ephemeral=True)
    return
```

### 2. Don't cache failed Gemini extractions
```python
# gemini.py _extract_batch: return a sentinel or raise instead of []
# orchestrator.py: only call save_ingredient_cache for successful results
```

### 3. Add retry with backoff for Gemini API calls
```python
# gemini.py: separate HTTP errors (retry with backoff) from parse errors (try repair)
for attempt in range(max_retries + 1):
    try:
        resp = await self.client.post(...)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (429, 503) and attempt < max_retries:
            await asyncio.sleep(2 ** attempt * 5)
            continue
        raise
```

### 4. Add local file fallback for intermediate results
```python
# orchestrator.py: after each expensive step, save to /tmp as fallback
import json, tempfile
with open(f"/tmp/amz_{keyword}_details.json", "w") as f:
    json.dump([d.model_dump() for d in all_details], f)
```

### 5. Fix `finally` block to close all services safely
```python
# orchestrator.py
finally:
    for svc in (browse, gemini, slack):
        try:
            await svc.close()
        except Exception:
            logger.warning("Failed to close %s", type(svc).__name__)
```

---

## Deployment Recommendation

**Fix critical issues #1 and #5 before next deployment.** Issues #2-#4 should be addressed in the next sprint. The current codebase can produce silently corrupt cached data that persists for 30 days, which is the highest-impact risk.
