# utils/i18n_scenario.py

import json
from pathlib import Path
from deep_translator import GoogleTranslator

CACHE_DIR = Path("cache/i18n")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_VERSION = "v2"  # incrementa quando cambi logica di traduzione

# campi tradotti in base al tipo di oggetto
SERVICE_TEXT_FIELDS = {"title", "description", "category", "tags"}   # name di solito lo lascerei com'è
TRIGGER_TEXT_FIELDS = {"name", "description"}
ACTION_TEXT_FIELDS  = {"name", "description"}

INGREDIENT_TEXT_FIELDS = {"name", "description", "dtype", "example"}     # dtype/example volendo li puoi lasciare
FIELD_TEXT_FIELDS      = {"label", "helper_text", "input_type_family"}  # slug NO

def _cache_file(scenario_code: str, lang: str) -> Path:
    return CACHE_DIR / f"{CACHE_VERSION}_scenario_{scenario_code}_{lang}.json"

def _translate(text: str, lang: str) -> str:
    if not text or lang == "en":
        return text
    try:
        return GoogleTranslator(source="auto", target=lang).translate(text)
    except Exception:
        return text

def _tr_fields(obj: dict, fields: set[str], lang: str) -> dict:
    """
    Ritorna una copia dell'oggetto con SOLO i campi selezionati tradotti (se stringa).
    """
    out = dict(obj)
    for k in fields:
        v = out.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = _translate(v, lang)
    return out

def translate_scenario_bundle(
    scenario_code: str,
    services: list[dict],
    triggers: list[dict],
    actions: list[dict],
    lang: str,
) -> dict:
    """
    Traduce SOLO ciò che serve in UI per UNO scenario.
    Cache persistente su file.
    """
    cache_path = _cache_file(scenario_code, lang)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    # ---- services ----
    services_t = []
    for s in services:
        s2 = _tr_fields(s, SERVICE_TEXT_FIELDS, lang)
        # opzionale: tradurre anche name? di solito NO
        # if isinstance(s2.get("name"), str): s2["name"] = _translate(s2["name"], lang)
        services_t.append(s2)

    # ---- triggers ----
    triggers_t = []
    for t in triggers:
        t2 = _tr_fields(t, TRIGGER_TEXT_FIELDS, lang)

        # ingredients (se li usi in pagina 3)
        if isinstance(t2.get("ingredients"), list):
            new_ings = []
            for ing in t2["ingredients"]:
                if isinstance(ing, dict):
                    new_ings.append(_tr_fields(ing, INGREDIENT_TEXT_FIELDS, lang))
                else:
                    new_ings.append(ing)
            t2["ingredients"] = new_ings

        triggers_t.append(t2)

    # ---- actions ----
    actions_t = []
    for a in actions:
        a2 = _tr_fields(a, ACTION_TEXT_FIELDS, lang)

        # fields (se li usi in pagina 3)
        if isinstance(a2.get("fields"), list):
            new_fields = []
            for fld in a2["fields"]:
                if isinstance(fld, dict):
                    new_fields.append(_tr_fields(fld, FIELD_TEXT_FIELDS, lang))
                else:
                    new_fields.append(fld)
            a2["fields"] = new_fields

        actions_t.append(a2)

    bundle = {"services": services_t, "triggers": triggers_t, "actions": actions_t}

    cache_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle
