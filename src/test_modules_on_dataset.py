"""
Integration test: run all 4 refactored code_parsing modules
on every record in applets_synt_new_final.jsonl.

Reports: parse successes/failures, getter/setter extraction,
path analysis, and catalog validation stats.
"""
import sys, os, json, time, traceback
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.code_parsing.expr import (
    _expr_to_str, Const, Field, BinOp,
    simplify_fix, eval_expr, substitute_aliases,
)
from src.code_parsing.js_validator import (
    safe_parse_with_tail_drop, SetterCall, SkipCall, ASTParser,
    detect_and_unwrap_wrapper, clean_filter_code,
)
from src.code_parsing.path_analyzer import (
    extract_used_filter_codes_semantic,
    build_outcomes_from_ast,
    simplify_condition_logic,
    extract_getters_from_outcomes,
    normalize_platform_getters,
)
from src.code_parsing.catalog_validator import (
    ValidationReport, load_catalog, get_allowed_api_surface,
    validate_against_catalog,
)

# ---- load dataset ----
DATASET = "data/dataset/applets/applets_synt_new_final.jsonl"
TRIGGERS_PATH = "data/ifttt_catalog/triggers.json"
ACTIONS_PATH  = "data/ifttt_catalog/actions.json"

with open(DATASET, "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f if line.strip()]

print(f"Loaded {len(records)} records from {DATASET}")

# ---- load catalog (if files exist) ----
catalog_available = os.path.exists(TRIGGERS_PATH) and os.path.exists(ACTIONS_PATH)
if catalog_available:
    trigger_index, action_index = load_catalog(TRIGGERS_PATH, ACTIONS_PATH)
    print(f"Catalog: {len(trigger_index)} triggers, {len(action_index)} actions")
else:
    trigger_index, action_index = {}, {}
    print("WARNING: catalog files not found, skipping catalog validation")

# ---- counters ----
total = len(records)
parse_ok = 0
parse_fail = 0
empty_code = 0
unwrap_count = 0

getter_total = 0
setter_total = 0
outcome_total = 0
skip_total = 0

catalog_tested = 0
catalog_valid = 0
catalog_invalid = 0

errors = []

t0 = time.time()

for i, rec in enumerate(records):
    code = rec.get("filter_code", "")
    if not code or not code.strip():
        empty_code += 1
        continue

    row_idx = rec.get("row_index", i)

    try:
        # ---- Step 1: js_validator — parse ----
        parsed, cleaned, err = safe_parse_with_tail_drop(code)

        if err or parsed is None:
            parse_fail += 1
            errors.append((row_idx, "parse_fail", err, code[:80]))
            continue

        parse_ok += 1

        # check wrapper detection
        if parsed.get("wrapper_detected"):
            unwrap_count += 1

        # ---- Step 2: path_analyzer — extract semantics ----
        true_getters, used_ns, used_setters, outcomes = extract_used_filter_codes_semantic(parsed)

        getter_total += len(true_getters)
        setter_total += len(used_setters)
        outcome_total += len(outcomes)

        for o in outcomes:
            if o.get("skip"):
                skip_total += 1

        # ---- Step 3: expr — verify condition serialization roundtrip ----
        for o in outcomes:
            cond = o["condition"]
            cond_str = _expr_to_str(cond)
            # just verify it doesn't crash
            simplified = simplify_condition_logic(cond)
            _ = _expr_to_str(simplified)

        # ---- Step 4: catalog_validator (if available) ----
        if catalog_available:
            trigger_apis = rec.get("trigger_apis", [])
            action_apis = rec.get("action_apis", [])

            # extract skip targets
            used_skips = []
            for o in outcomes:
                if o.get("skip"):
                    used_skips.extend(o.get("skip_targets", []))

            report = validate_against_catalog(
                used_getters=true_getters,
                used_setters=used_setters,
                used_skips=used_skips,
                trigger_slugs=trigger_apis,
                action_slugs=action_apis,
                trigger_index=trigger_index,
                action_index=action_index,
            )
            catalog_tested += 1
            if report.is_valid:
                catalog_valid += 1
            else:
                catalog_invalid += 1

    except Exception as e:
        parse_fail += 1
        tb = traceback.format_exc().splitlines()[-3:]
        errors.append((row_idx, "exception", str(e), "\n".join(tb)))

elapsed = time.time() - t0

# ---- report ----
print(f"\n{'='*60}")
print(f"  RESULTS  ({elapsed:.2f}s)")
print(f"{'='*60}")
print(f"  Total records:     {total}")
print(f"  Empty code:        {empty_code}")
print(f"  Parse OK:          {parse_ok}")
print(f"  Parse FAIL:        {parse_fail}")
print(f"  Wrapper unwrapped: {unwrap_count}")
print(f"  ---")
print(f"  Getters extracted: {getter_total}")
print(f"  Setters extracted: {setter_total}")
print(f"  Outcomes built:    {outcome_total}")
print(f"  Skip paths:        {skip_total}")
if catalog_available:
    print(f"  ---")
    print(f"  Catalog tested:    {catalog_tested}")
    print(f"  Catalog valid:     {catalog_valid}")
    print(f"  Catalog invalid:   {catalog_invalid}")
print(f"{'='*60}")

if errors:
    print(f"\nFirst {min(10, len(errors))} errors:")
    for row_idx, kind, detail, snippet in errors[:10]:
        print(f"  [{row_idx}] {kind}: {detail}")
        print(f"       code: {snippet}")
    if len(errors) > 10:
        print(f"  ... and {len(errors) - 10} more")

# exit code: 0 if parse rate > 90%
parse_rate = parse_ok / max(1, parse_ok + parse_fail) * 100
print(f"\nParse rate: {parse_rate:.1f}%")
sys.exit(0 if parse_rate > 90 else 1)
