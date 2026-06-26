#!/usr/bin/env python3
"""
Demonstrates the three bugs Devin fixed in superset/views/core.py.
Shows the exact crash that would occur BEFORE the fix, and the safe
behavior AFTER the fix.
"""

import json

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m💥 CRASH\033[0m"

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ---------------------------------------------------------------------------
# Bug 1 — PR #10: KeyError/ValueError in datasource_metadata
# Endpoint: GET /superset/fetch_datasource_metadata?datasourceKey=<bad>
# ---------------------------------------------------------------------------
section("Bug 1 · fetch_datasource_metadata (PR #10)")

def before_fix_1(datasource_key):
    # Original code — no error handling
    datasource_id, datasource_type = datasource_key.split("__")
    return f"200 OK — id={datasource_id} type={datasource_type}"

def after_fix_1(datasource_key):
    try:
        datasource_id, datasource_type = datasource_key.split("__")
        return f"200 OK — id={datasource_id} type={datasource_type}"
    except (KeyError, ValueError):
        return "400 Bad Request — Invalid datasourceKey format"

good_key = "42__table"
bad_key  = "malformed-no-separator"

print(f"\n  Input: '{good_key}' (valid)")
print(f"  Before: {before_fix_1(good_key)}")
print(f"  After:  {after_fix_1(good_key)}  {PASS}")

print(f"\n  Input: '{bad_key}' (malformed)")
try:
    before_fix_1(bad_key)
    print(f"  Before: (no crash — unexpected)")
except ValueError as e:
    print(f"  Before: {FAIL} — ValueError: {e}  → 500 Internal Server Error")
print(f"  After:  {after_fix_1(bad_key)}  {PASS}")

# ---------------------------------------------------------------------------
# Bug 2 — PR #11: ValueError in get_redirect_url
# Endpoint: GET /r/ with form_data containing a bad datasource string
# ---------------------------------------------------------------------------
section("Bug 2 · get_redirect_url (PR #11)")

def before_fix_2(datasource_string):
    # Original code — assumes exactly one "__" separator
    datasource_id, datasource_type = datasource_string.split("__")
    return f"Redirect built — id={datasource_id} type={datasource_type}"

def after_fix_2(datasource_string):
    parts = datasource_string.split("__")
    if len(parts) == 2:
        datasource_id, datasource_type = parts
        return f"Redirect built — id={datasource_id} type={datasource_type}"
    else:
        return "Redirect built (datasource skipped — malformed value logged)"

good_ds = "99__druid"
bad_ds  = "no-separator-here"

print(f"\n  Input: '{good_ds}' (valid)")
print(f"  Before: {before_fix_2(good_ds)}")
print(f"  After:  {after_fix_2(good_ds)}  {PASS}")

print(f"\n  Input: '{bad_ds}' (malformed)")
try:
    before_fix_2(bad_ds)
except ValueError as e:
    print(f"  Before: {FAIL} — ValueError: {e}  → 500 Internal Server Error")
print(f"  After:  {after_fix_2(bad_ds)}  {PASS}")

# ---------------------------------------------------------------------------
# Bug 3 — PR #12: JSONDecodeError in explore()
# Endpoint: GET /explore with a corrupted form_data_key in cache
# ---------------------------------------------------------------------------
section("Bug 3 · explore() cached form data (PR #12)")

def before_fix_3(cached_value):
    initial_form_data = json.loads(cached_value) if cached_value else {}
    return f"Chart loaded — form_data keys: {list(initial_form_data.keys())}"

def after_fix_3(cached_value):
    try:
        initial_form_data = json.loads(cached_value) if cached_value else {}
    except json.JSONDecodeError:
        initial_form_data = {}
        print("  [WARNING] Corrupt cache — falling back to empty form data")
    return f"Chart loaded — form_data keys: {list(initial_form_data.keys())}"

good_cache = '{"datasource": "42__table", "viz_type": "bar"}'
bad_cache  = "corrupted{not valid json%%"

print(f"\n  Input: valid JSON cache")
print(f"  Before: {before_fix_3(good_cache)}")
print(f"  After:  {after_fix_3(good_cache)}  {PASS}")

print(f"\n  Input: corrupted cache value")
try:
    before_fix_3(bad_cache)
except json.JSONDecodeError as e:
    print(f"  Before: {FAIL} — JSONDecodeError: {e}  → 500 Internal Server Error")
print(f"  After:  {after_fix_3(bad_cache)}  {PASS}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print("  SUMMARY")
print('='*60)
print("  All 3 crash paths now return safe responses instead of 500s.")
print("  PRs #10, #11, #12 merged to master by Devin autonomously.")
print(f"{'='*60}\n")
