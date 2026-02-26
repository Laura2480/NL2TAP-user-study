# run_responses_parallel.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

from llm_utility.prompts.prompt_d import make_body_D_single
from llm_utility.prompts.prompt_f import make_body_F_single
from llm_utility.prompts.utility import get_trigger_def_for_row, get_action_def_for_row

OPENAI_API_KEY = "REDACTED_OPENAI_KEY"

client = OpenAI(api_key=OPENAI_API_KEY)

MAX_WORKERS      = 4
RETRY_MAX        = 3
RETRY_SLEEP_BASE = 1

import json, time
from typing import Dict, Any

def call_responses_with_body(body: Dict[str, Any], row: Dict[str, Any], attempt: int = 1) -> Dict[str, Any]:
    row_index= row.get("row_index")
    t0 = time.time()

    def safe_json(s: str):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            a, b = s.find("{"), s.rfind("}")
            return json.loads(s[a:b+1]) if a != -1 and b > a else None

    try:
        resp = client.responses.create(**body)
        # se troncato per token, prova una volta a continuare
        if getattr(resp, "status", "") == "incomplete" and \
           getattr(resp, "incomplete_details", None) and \
           getattr(resp.incomplete_details, "reason", "") == "max_output_tokens":
            resp = client.responses.create(
                model=body["model"],
                previous_response_id=resp.id,
                input=body.get("input", []),
                max_output_tokens=body.get("max_output_tokens", 800),
            )

        # raccogli tutto il testo
        text = ""
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") == "message":
                for c in getattr(item, "content", []) or []:
                    t = getattr(c, "text", None)
                    if t: text += t + "\n"

        parsed = safe_json(text)
        latency = round(time.time() - t0, 2)

        if not parsed:
            return {
                "row_index": row_index,
                "rule_description": text.strip(),
                "app_summary": None,
                "user_intent_example": None
            }

        return {
            "row_index": parsed.get("row_index", row_index),
            "rule_description": parsed.get("rule_description"),
            "app_summary": parsed.get("app_summary"),
            "user_intent_example": parsed.get("user_intent_example")
        }

    except Exception as e:
        if attempt < RETRY_MAX:
            time.sleep(RETRY_SLEEP_BASE * attempt)
            return call_responses_with_body(body, row, attempt + 1)
        return {
            "row_index": row_index,
            "rule_description": None,
            "app_summary": None,
            "user_intent_example": None
        }

def call_responses_with_body_F(body: Dict[str, Any], row: Dict[str, Any], attempt: int = 1) -> Dict[str, Any]:
    row_index= row.get("row_index")
    t0 = time.time()

    def safe_json(s: str):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            a, b = s.find("{"), s.rfind("}")
            return json.loads(s[a:b+1]) if a != -1 and b > a else None

    try:
        resp = client.responses.create(**body)
        # se troncato per token, prova una volta a continuare
        if getattr(resp, "status", "") == "incomplete" and \
           getattr(resp, "incomplete_details", None) and \
           getattr(resp.incomplete_details, "reason", "") == "max_output_tokens":
            resp = client.responses.create(
                model=body["model"],
                previous_response_id=resp.id,
                input=body.get("input", []),
                max_output_tokens=body.get("max_output_tokens", 800),
            )

        # raccogli tutto il testo
        text = ""
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") == "message":
                for c in getattr(item, "content", []) or []:
                    t = getattr(c, "text", None)
                    if t: text += t + "\n"

        parsed = safe_json(text)
        latency = round(time.time() - t0, 2)

        if not parsed:
            return {
                "row_index": row_index,
                "require_filter_code": None,
                "filter_code_gpt": text.strip(),
            }

        return {
            "row_index": parsed.get("row_index", row_index),
            "require_filter_code": parsed.get("code_required"),
            "filter_code_gpt": parsed.get("filter_code"),
        }

    except Exception as e:
        if attempt < RETRY_MAX:
            time.sleep(RETRY_SLEEP_BASE * attempt)
            return call_responses_with_body(body, row, attempt + 1)
        return {
            "row_index": row_index,
            "require_filter_code": None,
            "filter_code_gpt": None,
        }



def process_rows_D(rows: List[Dict[str, Any]],ti:Dict[str, Any],ai:Dict[str, Any], max_workers: int = MAX_WORKERS) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for row in rows:
            body = make_body_D_single(row,ti,ai)
            fut = ex.submit(call_responses_with_body, body, row, RETRY_MAX)
            futures[fut] = row

        for (fut) in as_completed(futures):
            try:
                res = fut.result()
            except Exception as e:
                print("EXC in future:", repr(e))
                continue
            results.append(res)
            print(f"\r[D] {res['row_index']} error:{pd.isnull(res['user_intent_example'])}", end="", flush=True)
    return results


def process_rows_F(rows: List[Dict[str, Any]],trigger_index:Any,action_index:Any, max_workers: int = MAX_WORKERS) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for row in rows:
            body = make_body_F_single(row, trigger_index, action_index)
            fut = ex.submit(call_responses_with_body_F, body, row, RETRY_MAX)
            futures[fut] = row

        for (fut) in as_completed(futures):
            try:
                res = fut.result()
            except Exception as e:
                print("EXC in future:", repr(e))
                continue
            results.append(res)
            print(f"\r[F] {res['row_index']} error:{pd.isnull(res['require_filter_code'])}", end="", flush=True)

    return results

