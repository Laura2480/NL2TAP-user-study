"""
Execution sandbox for IFTTT filter code.

Executes generated filter code against mock API surfaces using PyMiniRacer (V8).
Records which setters were called and with what values, and which actions were skipped.

Used for:
- Execution-based validation (does the code do what the user intended?)
- Test fixture evaluation (pass/fail against expected behavior)
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from py_mini_racer import MiniRacer


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SetterRecord:
    """A setter call recorded during execution."""
    method: str       # e.g. "Twitter.postNewTweet.setTweet"
    value: Any        # the value passed to the setter


@dataclass
class SkipRecord:
    """A skip call recorded during execution."""
    target: str       # e.g. "Domovea.runScene"
    reason: str       # skip reason (or "")


@dataclass
class ExecutionResult:
    """Result of executing filter code against a test fixture."""
    success: bool = True
    error: Optional[str] = None
    setters_called: List[SetterRecord] = field(default_factory=list)
    skips_called: List[SkipRecord] = field(default_factory=list)
    actions_skipped: List[str] = field(default_factory=list)
    actions_fired: List[str] = field(default_factory=list)


@dataclass
class TestFixture:
    """A test case for a scenario: getter values + expected behavior."""
    name: str
    description: str
    getter_values: Dict[str, Any]  # {"Ns.trigger.Field": value, ...}
    expect_skip: List[str] = field(default_factory=list)    # action targets that should be skipped
    expect_fire: List[str] = field(default_factory=list)    # action targets that should fire
    expect_setters: Dict[str, Any] = field(default_factory=dict)  # {"method": expected_value}


@dataclass
class TestResult:
    """Result of one test fixture evaluation."""
    fixture_name: str
    passed: bool
    execution: ExecutionResult
    failures: List[str] = field(default_factory=list)  # what went wrong


# ============================================================
# MOCK BUILDER — builds JS mock objects from catalog data
# ============================================================

def _build_mock_js(
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
    getter_values: Dict[str, Any],
) -> str:
    """Build JS code for all mock objects (getters + setters + skip), merged by root namespace.

    Handles the case where trigger and action share the same root namespace
    (e.g. Domovea.deviceSwitchedOn + Domovea.runScene → single `var Domovea = {...}`).
    """
    js_lines = [
        "var __setters = [];",
        "var __skips = [];",
    ]

    # Merged namespace: root → sub → JS body string
    merged: Dict[str, Dict[str, str]] = {}

    # --- Getters (trigger ingredients as plain object properties) ---
    for slug in trigger_slugs:
        trig = trigger_index.get(slug)
        if not trig:
            continue
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key", "")
            if not fck:
                continue
            parts = fck.split(".")
            if len(parts) < 3:
                continue
            root, sub = parts[0], parts[1]
            field_name = ".".join(parts[2:])
            value = getter_values.get(fck, ing.get("example", ""))

            # Accumulate fields for this sub-namespace
            existing = merged.setdefault(root, {}).get(sub, "")
            sep = ",\n" if existing else ""
            merged[root][sub] = existing + sep + f"      {field_name}: {json.dumps(value)}"

    # --- Setters + skip (action methods as functions) ---
    for slug in action_slugs:
        act = action_index.get(slug)
        if not act:
            continue
        ns = act.get("namespace", "")
        if not ns:
            continue
        parts = ns.split(".")
        if len(parts) < 2:
            continue
        root, action_name = parts[0], parts[1]

        method_lines = []
        for fld in act.get("fields", []):
            fcm = fld.get("filter_code_method")
            if not fcm:
                continue
            m = re.match(r"[\w.]+\.(set\w+)\(", fcm)
            if m:
                setter_name = m.group(1)
                full_method = f"{ns}.{setter_name}"
                method_lines.append(
                    f'      {setter_name}: function(v) {{ '
                    f'__setters.push({{method: "{full_method}", value: v}}); }}'
                )

        method_lines.append(
            f'      skip: function(r) {{ '
            f'__skips.push({{target: "{ns}", reason: r || ""}}); }}'
        )

        existing = merged.setdefault(root, {}).get(action_name, "")
        sep = ",\n" if existing else ""
        merged[root][action_name] = existing + sep + ",\n".join(method_lines)

    # --- Emit merged var declarations ---
    for root, subs in merged.items():
        sub_parts = []
        for sub_name, body in subs.items():
            sub_parts.append(f"    {sub_name}: {{\n{body}\n    }}")
        js_lines.append(
            f"var {root} = {{\n" + ",\n".join(sub_parts) + "\n};"
        )

    return "\n".join(js_lines)


def _build_meta_js() -> str:
    """Build JS code for Meta.currentUserTime mock (simplified Moment.js)."""
    return """\
var Meta = {
  currentUserTime: {
    hour: function() { return __meta_hour; },
    minute: function() { return __meta_minute; },
    second: function() { return 0; },
    day: function() { return __meta_day; },
    weekday: function() { return __meta_weekday; },
    isoWeekday: function() { return __meta_weekday === 0 ? 7 : __meta_weekday; },
    month: function() { return __meta_month; },
    year: function() { return __meta_year; },
    format: function(fmt) { return __meta_hour + ":" + __meta_minute; },
    toISOString: function() { return "2026-03-09T" + __meta_hour + ":00:00Z"; },
    isBefore: function(other) { return __meta_hour < other.hour(); },
    isAfter: function(other) { return __meta_hour > other.hour(); }
  }
};
var __meta_hour = 12;
var __meta_minute = 0;
var __meta_day = 1;
var __meta_weekday = 1;
var __meta_month = 2;
var __meta_year = 2026;
"""


# ============================================================
# EXECUTOR
# ============================================================

def execute_filter_code(
    code: str,
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
    getter_values: Dict[str, Any] = None,
    meta_time: Dict[str, int] = None,
) -> ExecutionResult:
    """Execute IFTTT filter code in a V8 sandbox with mocked APIs.

    Args:
        code: JavaScript filter code to execute
        trigger_slugs: trigger API slugs for this scenario
        action_slugs: action API slugs for this scenario
        trigger_index: {slug: trigger_dict} from catalog
        action_index: {slug: action_dict} from catalog
        getter_values: override getter values {"Ns.trigger.Field": value}
        meta_time: override time values {"hour": 14, "minute": 30, ...}

    Returns:
        ExecutionResult with recorded setter/skip calls
    """
    if not code or not code.strip():
        return ExecutionResult(success=False, error="Empty code")

    getter_values = getter_values or {}
    meta_time = meta_time or {}

    # Build the sandbox JS
    mock_js = _build_mock_js(
        trigger_slugs, action_slugs, trigger_index, action_index, getter_values,
    )
    meta_js = _build_meta_js()

    # Override meta time values if provided
    time_overrides = ""
    for key in ("hour", "minute", "day", "weekday", "month", "year"):
        if key in meta_time:
            time_overrides += f"__meta_{key} = {json.dumps(meta_time[key])};\n"

    # Combine: mocks → time overrides → user code
    full_js = "\n".join([
        mock_js,
        meta_js,
        time_overrides,
        "// --- User filter code ---",
        code,
        "// --- Collect results ---",
        "JSON.stringify({setters: __setters, skips: __skips});",
    ])

    # Execute in isolated V8 context
    ctx = MiniRacer()
    try:
        raw = ctx.eval(full_js)
    except Exception as e:
        return ExecutionResult(success=False, error=str(e))

    # Parse results
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ExecutionResult(success=False, error=f"Invalid result: {raw}")

    setters = [
        SetterRecord(method=s["method"], value=s["value"])
        for s in data.get("setters", [])
    ]
    skips = [
        SkipRecord(target=s["target"], reason=s.get("reason", ""))
        for s in data.get("skips", [])
    ]

    # Determine which actions were skipped vs fired
    all_action_targets = set()
    for slug in action_slugs:
        act = action_index.get(slug)
        if act and act.get("namespace"):
            all_action_targets.add(act["namespace"])

    skipped_targets = {s.target for s in skips}
    # Per IFTTT semantics: skip is sticky — if skip() called, action doesn't fire
    actions_skipped = sorted(skipped_targets & all_action_targets)
    actions_fired = sorted(all_action_targets - skipped_targets)

    return ExecutionResult(
        success=True,
        setters_called=setters,
        skips_called=skips,
        actions_skipped=actions_skipped,
        actions_fired=actions_fired,
    )


# ============================================================
# TEST FIXTURE EVALUATION
# ============================================================

def evaluate_fixture(
    code: str,
    fixture: TestFixture,
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
) -> TestResult:
    """Run code against a test fixture and check expectations."""
    result = execute_filter_code(
        code=code,
        trigger_slugs=trigger_slugs,
        action_slugs=action_slugs,
        trigger_index=trigger_index,
        action_index=action_index,
        getter_values=fixture.getter_values,
        meta_time=fixture.getter_values,  # meta values can be in getter_values too
    )

    failures = []

    if not result.success:
        return TestResult(
            fixture_name=fixture.name,
            passed=False,
            execution=result,
            failures=[f"Execution error: {result.error}"],
        )

    # Check expected skips
    for target in fixture.expect_skip:
        if target not in result.actions_skipped:
            failures.append(f"Expected skip({target}) but it was not skipped")

    # Check expected fires
    for target in fixture.expect_fire:
        if target not in result.actions_fired:
            failures.append(f"Expected {target} to fire but it was skipped")

    # Check expected setter values
    setter_map = {s.method: s.value for s in result.setters_called}
    for method, expected_val in fixture.expect_setters.items():
        actual = setter_map.get(method)
        if actual is None:
            failures.append(f"Expected {method} to be called but it wasn't")
        elif expected_val is not None and actual != expected_val:
            failures.append(
                f"Expected {method}({expected_val!r}) but got {method}({actual!r})"
            )

    return TestResult(
        fixture_name=fixture.name,
        passed=len(failures) == 0,
        execution=result,
        failures=failures,
    )


def run_test_suite(
    code: str,
    fixtures: List[TestFixture],
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
) -> List[TestResult]:
    """Run code against all test fixtures, return results."""
    return [
        evaluate_fixture(code, f, trigger_slugs, action_slugs,
                         trigger_index, action_index)
        for f in fixtures
    ]


# ============================================================
# FIXTURE BUILDER — auto-generate from catalog examples
# ============================================================

def build_default_fixtures(
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
) -> List[TestFixture]:
    """Build basic test fixtures from catalog example values.

    Creates two fixtures:
    1. "default" — all getters use catalog example values (code runs with typical data)
    2. "empty" — all string getters are "" (edge case: empty inputs)
    """
    # Collect all getter paths + example values
    example_values = {}
    empty_values = {}
    for slug in trigger_slugs:
        trig = trigger_index.get(slug)
        if not trig:
            continue
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key", "")
            if fck:
                example_values[fck] = ing.get("example", "")
                dtype = ing.get("dtype", "String")
                empty_values[fck] = "" if dtype == "String" else 0

    # All action targets
    action_targets = []
    for slug in action_slugs:
        act = action_index.get(slug)
        if act and act.get("namespace"):
            action_targets.append(act["namespace"])

    fixtures = [
        TestFixture(
            name="default_values",
            description="All getters use catalog example values",
            getter_values=example_values,
            # No expectations — just check execution doesn't crash
        ),
        TestFixture(
            name="empty_strings",
            description="All string getters are empty",
            getter_values=empty_values,
        ),
    ]

    return fixtures
