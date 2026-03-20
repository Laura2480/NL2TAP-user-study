# src/evaluation/study_utils.py

from __future__ import annotations
import os, json, datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json
from pathlib import Path
from typing import Any, Dict, List, Union, Iterable
import gzip
import torch
import numpy as np
from datasets import tqdm
from torch.utils.data import DataLoader
import sys
import os
BASE=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _iter_lines_text(path: Path) -> Iterable[str]:
    """
    Iteratore di righe in testo (supporta anche .gz).
    """
    if path.suffix == ".gz":
        # .jsonl.gz -> apriamo in gzip text mode
        with gzip.open(path, mode="rt", encoding="utf-8") as f:
            for line in f:
                yield line
    else:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                yield line


def load_json_or_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Carica un file JSON o JSONL e restituisce sempre una lista di dict.

    - Se il file è .json: ci aspettiamo o una lista di oggetti o un singolo oggetto.
      * Se è una lista -> la ritorniamo così.
      * Se è un dict    -> ritorniamo [dict].
    - Se il file è .jsonl (o .jsonl.gz): ogni riga non vuota viene parse-ata come JSON
      e aggiunta alla lista.

    Esempio d'uso:
        triggers = load_json_or_jsonl("data/ifttt_catalog/triggers.json")
        actions  = load_json_or_jsonl("data/ifttt_catalog/actions.jsonl")
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    name_lower = p.name.lower()

    # Caso 1: JSONL / JSONLINES (anche gz)
    if name_lower.endswith(".jsonl") or name_lower.endswith(".jsonl.gz"):
        items: List[Dict[str, Any]] = []
        for line in _iter_lines_text(p):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                items.append(obj)
            else:
                # se è qualcosa di strano (lista, stringa, ecc.), lo impacchettiamo
                items.append({"value": obj})
        return items

    # Caso 2: JSON "normale"
    if name_lower.endswith(".json") or name_lower.endswith(".json.gz"):
        if p.suffix == ".gz":
            with gzip.open(p, mode="rt", encoding="utf-8") as f:
                obj = json.load(f)
        else:
            with p.open("r", encoding="utf-8") as f:
                obj = json.load(f)

        if isinstance(obj, list):
            # assumiamo lista di dict
            return obj
        elif isinstance(obj, dict):
            # un singolo oggetto -> lo mettiamo in una lista
            return [obj]
        else:
            # fallback paranoico
            return [{"value": obj}]

    # Caso 3: estensione non riconosciuta -> proviamo a sniffare
    with p.open("r", encoding="utf-8") as f:
        first_chars = f.read(1024)
        f.seek(0)
        first_non_ws = next((c for c in first_chars if not c.isspace()), "")

        if first_non_ws in ("{", "["):
            # sembra JSON "normale"
            obj = json.load(f)
            if isinstance(obj, list):
                return obj
            elif isinstance(obj, dict):
                return [obj]
            return [{"value": obj}]
        else:
            # proviamo a trattarlo come JSONL
            items: List[Dict[str, Any]] = []
            f.seek(0)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
                else:
                    items.append({"value": obj})
            return items


def generate_outputs(model, dataset, batch_size=16, max_new_tokens=340):
    loader = DataLoader(dataset, batch_size=batch_size)
    all_preds = []
    all_labels = []

    model.eval()
    for batch in tqdm(loader):
        input_ids = batch["input_ids"].to(model.device)
        attention_mask = batch["attention_mask"].to(model.device)
        labels = batch["labels"].numpy()

        with torch.no_grad():
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=False
            )

        # mettiamo in shape compatibile con compute_metrics
        preds = outputs.cpu().numpy()[:, input_ids.shape[1]:]
        all_preds.append(preds)
        all_labels.append(labels)

    all_preds = np.concatenate(all_preds, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)
    return all_preds, all_labels


# Per traduzione live
try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None  # fallback


from llm_utility.prompts.prompt_in import make_prompt as build_catalog_prompt
from llm_utility.prompts.utility import (
    load_api_indexes,
    PROMPT_CONFIGS,
)

STUDY_PATH    = Path(os.path.join(BASE,"src/evaluation/study_set_enriched.json"))
SERVICES_PATH = Path(os.path.join(BASE,"data/ifttt_catalog/services.json"))
TRIGGERS_PATH = Path(os.path.join(BASE,"data/ifttt_catalog/triggers.json"))
ACTIONS_PATH  = Path(os.path.join(BASE,"data/ifttt_catalog/actions.json"))

RESULTS_ROOT  = Path("results")

# ------------------------- LOADERS -------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

STUDY = load_json(STUDY_PATH)
SERVICES = load_json(SERVICES_PATH)
TRIGGERS_LIST = load_json(TRIGGERS_PATH)
ACTIONS_LIST  = load_json(ACTIONS_PATH)

# trigger_index / action_index by api_endpoint_slug
TRIGGER_INDEX, ACTION_INDEX = load_api_indexes(
    str(TRIGGERS_PATH), str(ACTIONS_PATH)
)

SERVICE_INDEX = {s["service_slug"]: s for s in SERVICES}

# 6 scenarios per type (3 per block), ordered simple → medium → complex (C1 → C2 → C3).
#
# Complexity classification (aligned with paper's C1/C2/C3 framework):
#   C1 (simple):  1 action, 0-1 execution conditions (single threshold / boolean)
#   C2 (medium):  1 action with 2+ conditions OR conditional setter values (branching)
#   C3 (complex): 2+ actions with selective execution OR multi-branch condition logic
#
# Non-expert:
#   Block 1 = S1 (C1), S3 (C2), C1 (C3)
#   Block 2 = S2 (C1), C3 (C2), C2 (C3)
# Expert:
#   Block 1 = E2 (C1), E1 (C2), E3 (C3)
#   Block 2 = E5 (C1), E4 (C2), E6 (C3)

_COMPLEXITY_CLASS = {
    # Non-expert
    "S1": "C1",  # 1 threshold condition → notify
    "S2": "C1",  # 1 time-range condition → notify
    "M1": "C2",  # 2 conditions (person + time) → single action
    "M2": "C2",  # 2 conditions (route + advisory type) → single action
    "C1": "C3",  # multi-branch CO2 ranges → conditional color setters
    "C2": "C3",  # 2 actions + selective skip + 6 setters
    # Expert
    "E5": "C1",  # 1 route-keyword filter → SMS
    "E2": "C1",  # boolean image filter → Telegram
    "E1": "C2",  # multi-branch CO2 → conditional LIFX color
    "E4": "C2",  # date/month logic → conditional Facebook album
    "E3": "C3",  # 2 actions + selective skip + 6 setters
    "E6": "C3",  # 2 actions + quiet hours + content filtering
}

_BLOCK_ASSIGNMENTS = {
    "S1": 1, "M1": 1, "C1": 1,
    "S2": 2, "M2": 2, "C2": 2,
    "E2": 1, "E1": 1, "E3": 1,
    "E5": 2, "E4": 2, "E6": 2,
}
# Order within block: 0=C1(simple), 1=C2(medium), 2=C3(complex)
_BLOCK_ORDER = {
    "S1": 0, "M1": 1, "C1": 2,
    "S2": 0, "M2": 1, "C2": 2,
    "E2": 0, "E1": 1, "E3": 2,
    "E5": 0, "E4": 1, "E6": 2,
}
_KEEP_NON_EXPERT = {"S1", "S2", "M1", "C1", "C2", "M2"}
_KEEP_EXPERT = {"E1", "E2", "E3", "E4", "E5", "E6"}

def _annotate_block(sc: dict) -> dict:
    """Add pre-assigned block number, intra-block order, and complexity class."""
    sc = dict(sc)  # shallow copy
    sc["assigned_block"] = _BLOCK_ASSIGNMENTS.get(sc["code"], 1)
    sc["block_order"] = _BLOCK_ORDER.get(sc["code"], 0)
    sc["complexity_class"] = _COMPLEXITY_CLASS.get(sc["code"], sc.get("complexity_tag", "C1"))
    return sc

NON_EXP = [_annotate_block(s) for s in STUDY["non_expert"] if s["code"] in _KEEP_NON_EXPERT]
EXP     = [_annotate_block(s) for s in STUDY["expert"] if s["code"] in _KEEP_EXPERT]
QUESTIONNAIRES = STUDY["questionnaires"]

# ------------------ TRANSLATION HELPERS --------------------

def translate_it_to_en(text: str) -> str:
    if not text:
        return ""
    if GoogleTranslator is None:
        return text  # fallback: no translation
    try:
        return GoogleTranslator(source="it", target="en").translate(text)
    except Exception:
        return text

# ------------------ SCENARIO UTILS ------------------------

def get_scenario_list(user_type: str) -> List[Dict[str, Any]]:
    return NON_EXP if user_type == "non_expert" else EXP

def get_scenario_by_code(code: str, user_type: str) -> Optional[Dict[str, Any]]:
    for sc in get_scenario_list(user_type):
        if sc["code"] == code:
            return sc
    return None

def get_allowed_filters_for_scenario(
    scenario: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """
    Ritorna:
      - lista di filter_code_key consentiti (ingredient)
      - lista di filter_code_method consentiti (setter)
    per tutte le trigger_apis / action_apis dello scenario.
    """
    allowed_keys = set()
    allowed_methods = set()

    for trig_slug in scenario.get("trigger_apis", []):
        trig_def = TRIGGER_INDEX.get(trig_slug)
        if not trig_def:
            continue
        for ing in trig_def.get("ingredients", []):
            key = ing.get("filter_code_key")
            if key:
                allowed_keys.add(key)

    for act_slug in scenario.get("action_apis", []):
        act_def = ACTION_INDEX.get(act_slug)
        if not act_def:
            continue
        # setters
        for fld in act_def.get("fields", []):
            m = fld.get("filter_code_method")
            if m:
                allowed_methods.add(m)
        # skip
        sk = act_def.get("skip_method")
        if sk:
            allowed_methods.add(sk)

    return sorted(allowed_keys), sorted(allowed_methods)

# ------------------ PROMPT BUILDING ------------------------

CATALOG_CFG = PROMPT_CONFIGS["catalog_full"]

def build_llm_prompt_for_scenario(
    scenario: Dict[str, Any],
    user_intent_en: str,
    separator: str = ""
) -> str:
    """
    Usa make_prompt (catalog_full) e sostituisce l'user_intent_example
    con l'intento dell'utente.
    """
    # make_prompt si aspetta un "row" simile a riga dataset reale:
    row = {
        "trigger_apis": scenario["trigger_apis"],
        "action_apis":  scenario["action_apis"],
        "user_intent_example": user_intent_en,
        "rule_description": scenario.get("background_en", "")
    }
    prompt = build_catalog_prompt(
        row=row,
        trigger_index=TRIGGER_INDEX,
        action_index=ACTION_INDEX,
        PROMPT_CFG=CATALOG_CFG,
        SEPARATOR=separator
    )
    return prompt

# ------------------ FIXTURE LOADING -------------------------

def load_scenario_fixtures(
    scenario: Dict[str, Any],
    lang: str = "en",
) -> List[Any]:
    """Load test fixtures from study_set_enriched.json for a scenario.

    Converts the JSON fixture definitions into TestFixture objects
    from execution_sandbox. Falls back to build_default_fixtures
    if no fixtures are defined.

    Args:
        scenario: scenario dict from study set (with optional test_fixtures field)
        lang: language for fixture descriptions

    Returns:
        List of TestFixture objects ready for run_test_suite()
    """
    from code_parsing.execution_sandbox import TestFixture, build_default_fixtures

    raw_fixtures = scenario.get("test_fixtures", [])
    if not raw_fixtures:
        # Fallback to auto-generated default fixtures
        return build_default_fixtures(
            scenario.get("trigger_apis", []),
            scenario.get("action_apis", []),
            TRIGGER_INDEX,
            ACTION_INDEX,
        )

    fixtures = []
    desc_key = f"description_{lang}" if lang in ("en", "it") else "description_en"
    for fx in raw_fixtures:
        desc = fx.get(desc_key) or fx.get("description_en", fx.get("name", ""))
        fixtures.append(TestFixture(
            name=fx.get("name", "unnamed"),
            description=desc,
            getter_values=fx.get("getter_values", {}),
            expect_skip=fx.get("expect_skip", []),
            expect_fire=fx.get("expect_fire", []),
            expect_setters=fx.get("expect_setters", {}),
        ))

    return fixtures


# ------------------ PARSER / VALIDATION --------------------


# ------------------ LOGGING -------------------------------

def save_attempt(
    user_id: str,
    user_type: str,
    scenario_code: str,
    attempt_idx: int,
    lang_ui: str,
    user_intent_original: str,
    user_intent_en: str,
    prompt_sent: str,
    llm_raw: str,
    llm_code: str,
    parse_info: Dict[str, Any],
    evaluator_status: str | None = None,
    evaluator_errors: List[str] | None = None,
    evaluator_notes: str | None = None
) -> Path:
    """
    Salva ogni tentativo in:
      results/user_<id>/scenario_<code>_attempt_<n>.json
    """
    ts = datetime.datetime.now().isoformat()
    user_dir = RESULTS_ROOT / f"user_{user_id}"
    user_dir.mkdir(parents=True, exist_ok=True)

    out_path = user_dir / f"scenario_{scenario_code}_attempt_{attempt_idx}.json"

    record = {
      "timestamp": ts,
      "user_id": user_id,
      "user_type": user_type,
      "scenario_code": scenario_code,
      "attempt": attempt_idx,
      "lang_ui": lang_ui,
      "user_intent_original": user_intent_original,
      "user_intent_en": user_intent_en,
      "prompt": prompt_sent,
      "llm_raw": llm_raw,
      "llm_code": llm_code,
      "parse_info": parse_info,
      "evaluator_status": evaluator_status,
      "evaluator_errors": evaluator_errors,
      "evaluator_notes": evaluator_notes
    }

    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
