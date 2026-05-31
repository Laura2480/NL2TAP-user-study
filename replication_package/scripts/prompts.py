"""
Prompt templates used in the paper — verbatim from the published manuscript.

1. REFINING PROMPT: Used with GPT-4 to refine noisy user-provided IFTTT rule
   descriptions based on their source code (Section 4.1).

2. GENERATION PROMPT: Used to generate filter code from a natural-language
   intent, grounded in the platform catalog (Appendix A).
   - ZS-NI+Catalog: zero-shot with catalog grounding
   - FT-NI+Catalog: fine-tuned with catalog grounding
"""

# =========================================================================
# 1. REFINING PROMPT (Dataset construction, Section 4.1)
# =========================================================================

REFINING_SYSTEM = (
    "You are an expert in refining and enhancing descriptions "
    "of trigger-action rules to ensure clarity."
)

REFINING_USER_TEMPLATE = """\
Context:
A trigger-action rule defines an automation in which one or more trigger \
conditions, possibly combined through logical operators (AND, OR), lead to \
the execution of one or more actions. The rule's behavior can be further \
customized through code, which specifies the conditions under which \
individual actions should be executed, suppressed, or have their parameters \
modified.

Given the following information regarding a trigger-action rule:
- The code representation of the rule:
  {rule_code}
- Natural language descriptions of the elements associated with the triggers in the code:
  {trigger_elements}
- Natural language descriptions of the elements associated with the actions in the code:
  {action_elements}
- A natural language description of the rule's behavior:
  {rule_description}

Instruction:
Rewrite the provided rule description to accurately and comprehensively \
reflect the logic defined in the code. The revised description must \
explicitly convey the values of relevant variables and the execution of \
pertinent methods, without including code snippets or variable names. \
If the original description already fully captures the rule logic, return \
it unchanged.\
"""


# =========================================================================
# 2. GENERATION PROMPT (Filter-code generation, Appendix A)
# =========================================================================

GENERATION_PROMPT_TEMPLATE = """\
Context.
A trigger-action rule defines an automation in which one or more trigger \
events, possibly combined through logical operators (AND, OR), lead to \
the execution of one or more actions.
Filter Code refines such rules by specifying when actions should be executed \
versus suppressed, and how action parameters should be computed.

Given the following information regarding a trigger-action rule:

- A natural language description of the rule's intended behavior:
  {intent}

- Natural language descriptions of the trigger elements available for the rule:
  {trigger_elements_nl}

- Natural Language descriptions of the action elements available for the rule:
  {action_elements_nl}

- The code trigger variables, action setter and skip methods:
  {code_level_elements}

Instruction.
Write the filter code that implements the intent using only the platform \
elements provided.

The generated code must:
- read trigger data exclusively from the provided trigger variables;
- modify action parameters exclusively via the provided action methods;
- suppress actions only through the provided skip operation(s);
- use Meta.currentUserTime for any time-based logic.\
"""


# =========================================================================
# Example: instantiate both prompts with a real dataset record
# =========================================================================

if __name__ == "__main__":
    import json
    import os

    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA = os.path.join(BASE, "data")

    with open(os.path.join(DATA, "dataset_train.json"), encoding="utf-8") as f:
        train = json.load(f)
    with open(os.path.join(DATA, "triggers.json"), encoding="utf-8") as f:
        triggers = {t["api_endpoint_slug"]: t for t in json.load(f) if "api_endpoint_slug" in t}
    with open(os.path.join(DATA, "actions.json"), encoding="utf-8") as f:
        actions = {a["api_endpoint_slug"]: a for a in json.load(f) if "api_endpoint_slug" in a}

    row = train[0]

    # ── Gather elements ──
    t_elems_ref, a_elems_ref = [], []
    trigger_nl, action_nl, code_elems = [], [], []

    for tkey in row.get("trigger_apis", []):
        tdef = triggers.get(tkey, {})
        for ing in tdef.get("ingredients", []):
            key = ing.get("filter_code_key", "")
            desc = ing.get("description", "")
            dtype = ing.get("dtype", "")
            if key:
                t_elems_ref.append(f"{key}: {desc}")
                trigger_nl.append(desc)
                code_elems.append(f"Trigger variable: {key}" + (f" (type: {dtype})" if dtype else ""))

    for akey in row.get("action_apis", []):
        adef = actions.get(akey, {})
        for fld in adef.get("fields", []):
            method = fld.get("filter_code_method", "")
            label = fld.get("label", "")
            if method:
                a_elems_ref.append(f"{method}: {label}")
                action_nl.append(label)
                code_elems.append(f"Action setter: {method}")
        sk = adef.get("skip_method", "")
        if sk:
            a_elems_ref.append(f"{sk}: skip action")
            code_elems.append(f"Skip method: {sk}")

    # ── Refining Prompt ──
    print("=" * 70)
    print("REFINING PROMPT (real instance from dataset_train[0])")
    print("=" * 70)
    print(f"[System]: {REFINING_SYSTEM}\n")
    print(REFINING_USER_TEMPLATE.format(
        rule_code=row["filter_code"],
        trigger_elements="\n  ".join(t_elems_ref) if t_elems_ref else "(none)",
        action_elements="\n  ".join(a_elems_ref) if a_elems_ref else "(none)",
        rule_description=row.get("description") or row.get("name", ""),
    ))

    # ── Generation Prompt ──
    print("\n" + "=" * 70)
    print("GENERATION PROMPT (real instance, FT-NI+Catalog)")
    print("=" * 70)
    print(GENERATION_PROMPT_TEMPLATE.format(
        intent=row.get("user_intent_example", ""),
        trigger_elements_nl="\n  ".join(trigger_nl) if trigger_nl else "(none)",
        action_elements_nl="\n  ".join(action_nl) if action_nl else "(none)",
        code_level_elements="\n  ".join(code_elems) if code_elems else "(none)",
    ))

    print("\n--- TARGET CODE ---")
    print(row["filter_code"])
