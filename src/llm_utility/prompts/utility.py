from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, List

import json
from typing import Dict, Any, Tuple
@dataclass
class InstructPromptConfig:
    """
    Configurazione per costruire il prompt di fine-tuning/inference
    per modelli *instruct/chat*.

    Puoi usare direttamente questa dataclass oppure i profili predefiniti
    in PROMPT_CONFIGS / MODEL_PROMPT_PROFILE.
    """
    include_app_name: bool = True
    include_user_intent: bool = True
    include_rule_description: bool = False

    # Info di catalogo (trigger/action)
    include_ingredients: bool = False
    include_setters: bool = False
    include_skip_method: bool = True
    include_time_helpers: bool = False

    # Stile del system-like header
    strict_js_only: bool = True
    language: str = "en"  # per ora solo 'en', ma puoi estendere


# Profili predefiniti (chiavi logiche di configurazione)
PROMPT_CONFIGS: Dict[str, InstructPromptConfig] = {
    # Profilo minimale: solo intent + istruzioni generali
    "minimal": InstructPromptConfig(
        include_app_name=False,
        include_user_intent=True,
        include_rule_description=False,
        include_ingredients=False,
        include_setters=False,
        include_skip_method=False,
        include_time_helpers=False,
        strict_js_only=True,
    ),
    # Profilo che include anche ingredienti, setters e helper di tempo
    "catalog_full": InstructPromptConfig(
        include_app_name=False,
        include_user_intent=True,
        include_rule_description=True,
        include_ingredients=True,
        include_setters=True,
        include_skip_method=True,
        include_time_helpers=True,
        strict_js_only=True,
    ),
}


def get_prompt_config(profile_name: str) -> InstructPromptConfig:
    """
    Restituisce la InstructPromptConfig associata a un profilo.

    Profili predefiniti (PROMPT_CONFIGS):
      - 'minimal'
      - 'rich_no_catalog'
      - 'catalog_full'

    Se il nome non esiste, usa 'minimal' come fallback.
    """
    cfg = PROMPT_CONFIGS.get(profile_name)
    if cfg is None:
        return PROMPT_CONFIGS["minimal"]
    return cfg



def get_trigger_def_for_row(row: Dict[str, Any],trigger_index:Any) -> Dict[str, Any]:
    key: Tuple[str, str] = (
        row["trigger_service_slug"],
        row["trigger_module_slug"],
    )
    if key not in trigger_index:
        raise ValueError(
            f"Trigger non trovato per row_index={row.get('row_index')} "
            f"service_slug={key[0]!r} module_name={key[1]!r}"
        )
    return trigger_index[key]

def get_action_def_for_row(row: Dict[str, Any],action_index:Any) -> Dict[str, Any]:
    key: Tuple[str, str] = (
        row["action_service_slug"],
        row["action_module_slug"],
    )
    if key not in action_index:
        raise ValueError(
            f"Action non trovata per row_index={row.get('row_index')} "
            f"service_slug={key[0]!r} module_name={key[1]!r}"
        )
    return action_index[key]


from typing import Dict, Any, List, Tuple

from typing import Dict, Any, List, Tuple


def get_trigger_and_action_def_for_row(
        row: Dict[str, Any],
        trigger_index: Dict[str, Any],
        action_index: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    triggers: List[Dict[str, Any]] = []

    for t_key in row.get("trigger_apis", []):
        t = trigger_index.get(t_key)
        if t:
            trigger_obj = {
                "name": t.get("name") or "",
                "description": t.get("description") or "",
                "ingredients": []
            }

            for ing in t.get("ingredients", []):
                if ing.get("filter_code_key"):
                    trigger_obj["ingredients"].append({
                        "name": ing.get("name"),
                        "description": ing.get("description"),
                        "filter_code_key": ing.get("filter_code_key")
                    })

            triggers.append(trigger_obj)

    actions: List[Dict[str, Any]] = []

    for a_key in row.get("action_apis", []):
        a = action_index.get(a_key)
        if a:
            action_obj = {
                "name": a.get("name") or "",
                "description": a.get("description") or "",
                "fields": []
            }

            for field in a.get("fields", []):
                if field.get("filter_code_method"):
                    action_obj["fields"].append({
                        "label": field.get("label"),
                        "filter_code_method": field.get("filter_code_method")
                    })

            actions.append(action_obj)

    return triggers, actions


def extract_allowed_filters_unique(
        triggers: List[Dict[str, Any]],
        actions: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    keys = set()
    methods = set()

    for trig in triggers:
        for ing in trig.get("ingredients", []):
            fck = ing.get("filter_code_key")
            if fck:
                keys.add(fck)

    for act in actions:
        for fld in act.get("fields", []):
            fcm = fld.get("filter_code_method")
            if fcm:
                methods.add(fcm)

    return list(keys), list(methods)


def get_allowed_filters_for_row(
        row: Dict[str, Any],
        trigger_index: Dict[str, Any],
        action_index: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """
    Restituisce direttamente:
    - lista dei filter_code_key permessi
    - lista dei filter_code_method permessi
    per la riga specificata.
    """
    triggers, actions = get_trigger_and_action_def_for_row(row, trigger_index, action_index)
    allowed_keys, allowed_methods = extract_allowed_filters_unique(triggers, actions)
    return allowed_keys, allowed_methods



def load_api_indexes(
    triggers_path: str,
    actions_path: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    with open(triggers_path, "r", encoding="utf-8") as f:
        trigger_list = json.load(f)

    with open(actions_path, "r", encoding="utf-8") as f:
        action_list = json.load(f)

    # costruiamo indici basati su api_endpoint_slug
    trigger_index = {
        item["api_endpoint_slug"]: item
        for item in trigger_list
        if "api_endpoint_slug" in item
    }

    action_index = {
        item["api_endpoint_slug"]: item
        for item in action_list
        if "api_endpoint_slug" in item
    }

    return trigger_index, action_index

