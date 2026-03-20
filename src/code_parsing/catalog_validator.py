"""
Catalog Validator — validation of getters/setters/skip against IFTTT catalog.

Standalone module, no internal project dependencies.

Catalog structure:
  triggers.json: each entry has
    - api_endpoint_slug: "domovea.device_switched_on"
    - namespace: "Domovea.deviceSwitchedOn"
    - ingredients[*].filter_code_key: "Domovea.deviceSwitchedOn.DeviceName"

  actions.json: each entry has
    - api_endpoint_slug: "domovea.run_scene"
    - namespace: "Domovea.runScene"
    - fields[*].filter_code_method: "Twitter.postNewTweet.setTweet(string: tweet)"
    - skip_method: "Domovea.runScene.skip(string?: reason)"
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ============================================================
# ALWAYS-VALID & NON-GETTER CONSTANTS
# ============================================================

# Meta.currentUserTime is a global API available to every filter code,
# not bound to any specific trigger.  Any sub-path (hour, minute, …) is valid.
META_ALWAYS_VALID_PREFIX = "Meta.currentUserTime"

# JS built-in objects / globals that the expression evaluator may leave
# in the getter list but are NOT platform getters.
JS_NON_GETTER_ROOTS = {
    "Math", "JSON", "Date", "Object", "Array", "RegExp",
    "Number", "String", "Boolean", "moment",
    "parseInt", "parseFloat", "isNaN", "isFinite",
    "encodeURI", "encodeURIComponent", "decodeURI", "decodeURIComponent",
    "console", "undefined", "null", "NaN", "Infinity",
}

# Tokens that signal a parse artifact, not a real getter.
_ARTIFACT_MARKERS = {"<unknown>", "<mem:"}


@dataclass
class ValidationReport:
    valid_getters: List[str] = field(default_factory=list)
    invalid_getters: List[str] = field(default_factory=list)
    missing_getters: List[str] = field(default_factory=list)

    valid_setters: List[str] = field(default_factory=list)
    invalid_setters: List[str] = field(default_factory=list)
    missing_setters: List[str] = field(default_factory=list)

    skip_used: List[str] = field(default_factory=list)
    skip_available: List[str] = field(default_factory=list)

    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _load_json(path) -> list:
    """Minimal JSON/JSONL loader."""
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix == ".jsonl":
        items = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items
    else:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]


def _parse_setter_method(signature: str) -> str:
    """
    Extract method path from filter_code_method signature.
    E.g. "Twitter.postNewTweet.setTweet(string: tweet)" -> "Twitter.postNewTweet.setTweet"
    """
    if not signature:
        return ""
    # strip everything from '(' onwards
    return signature.split("(")[0].strip()


def _parse_skip_target(skip_method: str) -> str:
    """
    Extract skip target from skip_method signature.
    E.g. "Domovea.runScene.skip(string?: reason)" -> "Domovea.runScene"
    """
    if not skip_method:
        return ""
    path = skip_method.split("(")[0].strip()
    # remove trailing ".skip"
    if path.endswith(".skip"):
        return path[:-5]
    return path


def load_catalog(
    triggers_path: str,
    actions_path: str,
) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    Load trigger and action catalogs, returning indexed dicts.

    Both indexes are keyed by api_endpoint_slug (matching dataset format).

    Returns:
        trigger_index: { api_endpoint_slug: { "namespace", "ingredients": set[str] } }
        action_index:  { api_endpoint_slug: { "namespace", "setters": set[str], "skip_target": str } }
    """
    triggers = _load_json(triggers_path)
    actions = _load_json(actions_path)

    trigger_index: Dict[str, dict] = {}
    for trig in triggers:
        slug = trig.get("api_endpoint_slug")
        ns = trig.get("namespace")
        if not slug or not ns:
            continue
        ingredients = {
            ing["filter_code_key"]
            for ing in trig.get("ingredients", [])
            if isinstance(ing, dict) and ing.get("filter_code_key")
        }
        trigger_index[slug] = {
            "namespace": ns,
            "ingredients": ingredients,
        }

    action_index: Dict[str, dict] = {}
    for act in actions:
        slug = act.get("api_endpoint_slug")
        ns = act.get("namespace")
        if not slug or not ns:
            continue

        setter_methods = set()
        for f in act.get("fields", []):
            if not isinstance(f, dict):
                continue
            if f.get("filter_code_method"):
                method = _parse_setter_method(f["filter_code_method"])
                if method:
                    setter_methods.add(method)
            elif f.get("slug"):
                # derive setter from namespace + slug convention:
                # slug "amount" -> Qapital.saveTowardGoal.setAmount
                s = f["slug"]
                setter_methods.add(f"{ns}.set{s[0].upper()}{s[1:]}")

        # The namespace itself may be callable as a setter
        # (e.g. Yeelight.setScene, Hue.setScene)
        if ns.split(".")[-1].startswith("set"):
            setter_methods.add(ns)

        skip_target = _parse_skip_target(act.get("skip_method", ""))

        action_index[slug] = {
            "namespace": ns,
            "setters": setter_methods,
            "skip_target": skip_target,
        }

    return trigger_index, action_index


def get_allowed_api_surface(
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Given the trigger/action api_endpoint_slugs for a scenario,
    return the allowed API surface.

    Returns:
        allowed_getters: set of getter filter_code_keys
        allowed_setters: set of setter method paths
        allowed_skips:   set of skip targets (namespace without .skip)
    """
    allowed_getters: Set[str] = set()
    allowed_setters: Set[str] = set()
    allowed_skips: Set[str] = set()

    for slug in trigger_slugs:
        info = trigger_index.get(slug)
        if info:
            allowed_getters |= info["ingredients"]

    for slug in action_slugs:
        info = action_index.get(slug)
        if info:
            allowed_setters |= info["setters"]
            if info["skip_target"]:
                allowed_skips.add(info["skip_target"])

    return allowed_getters, allowed_setters, allowed_skips


def _is_ignorable_getter(g: str) -> bool:
    """
    Return True if *g* is NOT a platform getter and should be silently
    ignored during validation (JS global, parse artifact, local var, etc.).
    """
    if not g or not isinstance(g, str):
        return True
    # parse artifacts
    if any(m in g for m in _ARTIFACT_MARKERS):
        return True
    root = g.split(".")[0]
    if root in JS_NON_GETTER_ROOTS:
        return True
    # local variables start with lowercase (e.g. sunsetMoment, eventStart)
    # platform namespaces start with uppercase (e.g. Domovea, Twitter)
    if root and root[0].islower():
        return True
    return False


def _getter_matches_allowed(g: str, allowed: Set[str]) -> bool:
    """
    A getter is valid when:
      1. it is in the allowed set exactly, OR
      2. it is a method-chain extension of an allowed getter
         (e.g. "Feedly.newEntry.Categories.split.map" matches
          allowed "Feedly.newEntry.Categories").
    """
    if g in allowed:
        return True
    # check if any allowed getter is a prefix of g
    for a in allowed:
        if g.startswith(a + "."):
            return True
    return False


def validate_against_catalog(
    used_getters: List[str],
    used_setters: List[str],
    used_skips: List[str],
    trigger_slugs: List[str],
    action_slugs: List[str],
    trigger_index: Dict[str, dict],
    action_index: Dict[str, dict],
) -> ValidationReport:
    """
    Validate extracted getters/setters/skips against the IFTTT catalog
    for the given trigger/action api_endpoint_slugs.
    """
    allowed_getters, allowed_setters, allowed_skips = get_allowed_api_surface(
        trigger_slugs, action_slugs, trigger_index, action_index
    )

    # Collect action namespace prefixes — getters referencing action
    # APIs (e.g. Buffer.addToBuffer.isFull) are valid reads.
    action_ns_prefixes = set()
    for slug in action_slugs:
        info = action_index.get(slug)
        if info:
            action_ns_prefixes.add(info["namespace"])

    report = ValidationReport()

    # --- Getters ---
    for g in used_getters:
        # Meta.currentUserTime.* is always valid (global API)
        if g == META_ALWAYS_VALID_PREFIX or g.startswith(META_ALWAYS_VALID_PREFIX + "."):
            report.valid_getters.append(g)
        # JS globals / artifacts — silently skip
        elif _is_ignorable_getter(g):
            continue
        elif _getter_matches_allowed(g, allowed_getters):
            report.valid_getters.append(g)
        # getter reads from an action namespace (e.g. Buffer.addToBuffer.isFull)
        elif any(g == ns or g.startswith(ns + ".") for ns in action_ns_prefixes):
            report.valid_getters.append(g)
        else:
            report.invalid_getters.append(g)

    report.missing_getters = sorted(allowed_getters - set(used_getters))

    # --- Setters ---
    for s in used_setters:
        if s in allowed_setters:
            report.valid_setters.append(s)
        else:
            report.invalid_setters.append(s)

    report.missing_setters = sorted(allowed_setters - set(used_setters))

    # --- Skips ---
    report.skip_used = list(used_skips)
    report.skip_available = sorted(allowed_skips)

    # --- Validity ---
    if report.invalid_getters:
        report.is_valid = False
        report.errors.append(
            f"Invalid getters: {report.invalid_getters}"
        )
    if report.invalid_setters:
        report.is_valid = False
        report.errors.append(
            f"Invalid setters: {report.invalid_setters}"
        )

    if report.missing_getters:
        report.warnings.append(
            f"Unused available getters: {report.missing_getters}"
        )
    if report.missing_setters:
        report.warnings.append(
            f"Unused available setters: {report.missing_setters}"
        )

    return report


# ============================================================
# DISPLAY LABELS — human-readable names for flowchart rendering
# ============================================================

_META_TIME_LABELS = {
    "en": {
        "Meta.currentUserTime.hour": "Current Hour",
        "Meta.currentUserTime.minute": "Current Minute",
        "Meta.currentUserTime.second": "Current Second",
        "Meta.currentUserTime.day": "Day of Week",
        "Meta.currentUserTime.month": "Current Month",
        "Meta.currentUserTime.year": "Current Year",
        "Meta.currentUserTime.date": "Current Date",
        "Meta.currentUserTime": "Current User Time",
    },
    "it": {
        "Meta.currentUserTime.hour": "Ora corrente",
        "Meta.currentUserTime.minute": "Minuto corrente",
        "Meta.currentUserTime.second": "Secondo corrente",
        "Meta.currentUserTime.day": "Giorno della settimana",
        "Meta.currentUserTime.month": "Mese corrente",
        "Meta.currentUserTime.year": "Anno corrente",
        "Meta.currentUserTime.date": "Data corrente",
        "Meta.currentUserTime": "Ora locale utente",
    },
}


def build_display_labels(
    triggers: List[dict],
    actions: List[dict],
    trigger_slugs: List[str],
    action_slugs: List[str],
    lang: str = "en",
    services: List[dict] = None,
) -> dict:
    """
    Build human-readable label lookup tables for a scenario.

    Takes full catalog entries (already translated if i18n was applied)
    and returns lookup dicts for flowchart rendering.

    Returns dict with keys:
        getter_labels:    { filter_code_key -> ingredient name }
        setter_labels:    { method_path -> field label }
        trigger_ns:       set of trigger namespace prefixes
        action_ns:        set of action namespace prefixes
        namespace_names:  { namespace -> human-readable trigger/action name }
        skip_labels:      { skip_target -> action name }
        namespace_icons:  { namespace -> icon_url }
    """
    getter_labels = dict(_META_TIME_LABELS.get(lang, _META_TIME_LABELS["en"]))
    setter_labels = {}
    trigger_ns = set()
    action_ns = set()
    namespace_names = {}
    skip_labels = {}
    namespace_icons = {}
    namespace_colors = {}

    # Build service_slug -> icon_url / brand_color mapping
    svc_icons = {}
    svc_colors = {}
    if services:
        for svc in services:
            slug = svc.get("service_slug", "")
            icon = svc.get("image_url", "")
            color = svc.get("brand_color", "")
            if slug and icon:
                svc_icons[slug] = icon
            if slug and color:
                svc_colors[slug] = color

    slug_set_t = set(trigger_slugs)
    slug_set_a = set(action_slugs)

    for trig in triggers:
        slug = trig.get("api_endpoint_slug")
        if slug not in slug_set_t:
            continue
        ns = trig.get("namespace", "")
        name = trig.get("name", slug)
        if ns:
            trigger_ns.add(ns)
            namespace_names[ns] = name
            svc_slug = trig.get("service_slug", "")
            if svc_slug in svc_icons:
                namespace_icons[ns] = svc_icons[svc_slug]
            if svc_slug in svc_colors:
                namespace_colors[ns] = svc_colors[svc_slug]
        for ing in trig.get("ingredients", []):
            if not isinstance(ing, dict):
                continue
            fck = ing.get("filter_code_key")
            ing_name = ing.get("name")
            if fck and ing_name:
                getter_labels[fck] = ing_name

    for act in actions:
        slug = act.get("api_endpoint_slug")
        if slug not in slug_set_a:
            continue
        ns = act.get("namespace", "")
        name = act.get("name", slug)
        if ns:
            action_ns.add(ns)
            namespace_names[ns] = name
            svc_slug = act.get("service_slug", "")
            if svc_slug in svc_icons:
                namespace_icons[ns] = svc_icons[svc_slug]
            if svc_slug in svc_colors:
                namespace_colors[ns] = svc_colors[svc_slug]

        # Namespace-level setter (e.g. Yeelight.setScene)
        if ns and ns.split(".")[-1].startswith("set"):
            setter_labels[ns] = name

        # Skip target
        skip_method = act.get("skip_method", "")
        if skip_method:
            target = _parse_skip_target(skip_method)
            if target:
                skip_labels[target] = name

        for fld in act.get("fields", []):
            if not isinstance(fld, dict):
                continue
            label = fld.get("label", "")
            if fld.get("filter_code_method"):
                method = _parse_setter_method(fld["filter_code_method"])
                if method and label:
                    setter_labels[method] = label
            elif fld.get("slug") and ns:
                s = fld["slug"]
                derived = f"{ns}.set{s[0].upper()}{s[1:]}"
                if label:
                    setter_labels[derived] = label

    return {
        "getter_labels": getter_labels,
        "setter_labels": setter_labels,
        "trigger_ns": trigger_ns,
        "action_ns": action_ns,
        "namespace_names": namespace_names,
        "skip_labels": skip_labels,
        "namespace_icons": namespace_icons,
        "namespace_colors": namespace_colors,
    }
