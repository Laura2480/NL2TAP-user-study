"""
Enrich study_set.json with catalog data + i18n translations.

Reads:
  - src/evaluation/study_set.json
  - data/ifttt_catalog/services.json, triggers.json, actions.json
  - cache/i18n/v2_scenario_*_it.json (curated Italian translations)

Writes:
  - src/evaluation/study_set_enriched.json

Each scenario gets a "catalog" key with:
  - services: [{service_slug, name, brand_color, image_url, ...}]
  - triggers: [{api_endpoint_slug, namespace, name, description, ingredients, ...}]
  - actions:  [{api_endpoint_slug, namespace, name, description, fields, skip_method, ...}]

Both "en" (from raw catalog) and "it" (from i18n cache) versions are embedded.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

STUDY_PATH = BASE / "src" / "evaluation" / "study_set.json"
SERVICES_PATH = BASE / "data" / "ifttt_catalog" / "services.json"
TRIGGERS_PATH = BASE / "data" / "ifttt_catalog" / "triggers.json"
ACTIONS_PATH = BASE / "data" / "ifttt_catalog" / "actions.json"
CACHE_DIR = BASE / "cache" / "i18n"
OUTPUT_PATH = BASE / "src" / "evaluation" / "study_set_enriched.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_service_index(services: list) -> dict:
    return {s["service_slug"]: s for s in services}


def build_trigger_index(triggers: list) -> dict:
    return {t["api_endpoint_slug"]: t for t in triggers}


def build_action_index(actions: list) -> dict:
    return {a["api_endpoint_slug"]: a for a in actions}


def get_cached_it(scenario_code: str) -> dict | None:
    """Load curated Italian translation from i18n cache."""
    cache_path = CACHE_DIR / f"v2_scenario_{scenario_code}_it.json"
    if cache_path.exists():
        return load_json(cache_path)
    return None


def enrich_scenario(
    scenario: dict,
    svc_index: dict,
    trig_index: dict,
    act_index: dict,
) -> dict:
    """Add catalog data to a scenario, with en + it versions."""
    sc = dict(scenario)  # shallow copy
    code = sc["code"]

    # --- English catalog entries ---
    en_services = []
    for slug in sc.get("services", []):
        svc = svc_index.get(slug)
        if svc:
            en_services.append(svc)

    en_triggers = []
    for slug in sc.get("trigger_apis", []):
        trig = trig_index.get(slug)
        if trig:
            en_triggers.append(trig)

    en_actions = []
    for slug in sc.get("action_apis", []):
        act = act_index.get(slug)
        if act:
            en_actions.append(act)

    # --- Italian catalog entries (from curated cache) ---
    it_cache = get_cached_it(code)

    if it_cache:
        it_services = it_cache.get("services", en_services)
        it_triggers = it_cache.get("triggers", en_triggers)
        it_actions = it_cache.get("actions", en_actions)
    else:
        # No cache — fall back to English
        it_services = en_services
        it_triggers = en_triggers
        it_actions = en_actions
        print(f"  WARNING: no Italian cache for {code}, using English")

    sc["catalog"] = {
        "en": {
            "services": en_services,
            "triggers": en_triggers,
            "actions": en_actions,
        },
        "it": {
            "services": it_services,
            "triggers": it_triggers,
            "actions": it_actions,
        },
    }

    return sc


def main():
    print("Loading data...")
    study = load_json(STUDY_PATH)
    services = load_json(SERVICES_PATH)
    triggers = load_json(TRIGGERS_PATH)
    actions = load_json(ACTIONS_PATH)

    svc_index = build_service_index(services)
    trig_index = build_trigger_index(triggers)
    act_index = build_action_index(actions)

    enriched = dict(study)

    # Enrich non_expert scenarios
    print("Enriching non_expert scenarios...")
    enriched["non_expert"] = []
    for sc in study.get("non_expert", []):
        print(f"  {sc['code']}")
        enriched["non_expert"].append(
            enrich_scenario(sc, svc_index, trig_index, act_index)
        )

    # Enrich expert scenarios
    print("Enriching expert scenarios...")
    enriched["expert"] = []
    for sc in study.get("expert", []):
        print(f"  {sc['code']}")
        enriched["expert"].append(
            enrich_scenario(sc, svc_index, trig_index, act_index)
        )

    # Write output
    OUTPUT_PATH.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nDone! Written to {OUTPUT_PATH}")

    # Stats
    n_scenarios = len(enriched["non_expert"]) + len(enriched["expert"])
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"  {n_scenarios} scenarios enriched, {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
