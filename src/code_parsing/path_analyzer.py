"""
Path Analyzer — conditional path analysis, merge/normalize.

Depends on: expr.py, js_validator.py
Bug fix: simplify_condition_logic(expr, soft_numeric=False) — soft_normalize_numeric is opt-in
"""
from typing import Any, Dict, List

from .expr import (
    Expr, Const, Field, Var, UnOp, BinOp, CallExpr, NativeMethod,
    TernaryExpr,
    TRUE, Not, And,
    JS_GLOBAL_FUNCTIONS,
    is_const_expr, eval_const_expr,
    simplify_fix, eval_expr, substitute_aliases,
    soft_normalize_numeric,
    _expr_to_str, extract_field_refs, explode_ternary,
)

from .js_validator import ASTParser

# ===========================
#  MOMENT.JS METHOD SET
# ===========================
MOMENT_METHODS = {
    "year", "month", "date", "day", "weekday", "isoWeekday",
    "hour", "minute", "second", "millisecond",
    "week", "isoWeek",
    "add", "subtract", "set",
    "format", "calendar",
    "toISOString", "toJSON", "toString",
    "unix", "valueOf",
    "isBefore", "isAfter", "isSame", "isBetween"
}


# ============================================================
# OUTCOMES
# ============================================================

def build_outcomes_from_ast(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Costruisce i path semantici:
      - ogni path è { condition: Expr, skip: bool, setters: [ {method, value} ] }
      - skip() chiude SOLO il ramo corrente (non l'intero programma)
      - i setter vengono accumulati lungo il path
      - alla fine, per ogni path ancora "vivo", generiamo un outcome skip=False
      - poi filtriamo:
          * path triviali (skip=False, nessun setter)
          * path impossibili (condizione False)
          * path duplicati (stessa condizione, stesso skip, stessi setter)
    """
    ast = parsed.get("ast")
    if ast is None:
        return []

    parser: ASTParser = parsed["parser"]

    # State tuple: (cond, setters, alive, aliases, skip_targets)
    # skip_targets accumulates along the path — a single execution path
    # can have BOTH setters (for one action) AND skip targets (for another).

    def walk_block(stmts, states):
        current = states
        for stmt in stmts:
            new_states = []
            for cond, setters, alive, aliases, skips in current:
                if not alive:
                    new_states.append((cond, setters, False, aliases, skips))
                else:
                    new_states.extend(walk_stmt(stmt, cond, setters, aliases, skips))
            current = new_states
        return current

    def walk_stmt(node, cond: Expr, setters: List[Dict[str, Any]],
                  aliases: Dict[str, Expr], skips: List[str]):
        if not hasattr(node, "type"):
            return [(cond, setters, True, aliases, skips)]

        t = node.type

        # VAR DECLARATION
        if t == "VariableDeclaration":
            out = []
            for decl in node.declarations:
                if hasattr(decl, "id") and hasattr(decl, "init"):
                    name = decl.id.name
                    value_expr = parser.build_expr(decl.init, aliases)

                    parts = explode_ternary(value_expr)

                    for local_cond, local_val in parts:
                        nc = And(cond, local_cond)
                        val = substitute_aliases(local_val, aliases)
                        val = simplify_fix(val)
                        val = eval_expr(val)

                        new_alias = aliases.copy()
                        new_alias[name] = val

                        out.append((nc, setters, True, new_alias, skips))

            return out or [(cond, setters, True, aliases, skips)]

        # IF STATEMENT
        if t == "IfStatement":
            test = parser.build_expr(node.test, aliases)
            test = substitute_aliases(test, aliases)
            test = simplify_fix(test)
            test = eval_expr(test)

            then_cond = And(cond, test)
            else_cond = And(cond, Not(test))

            cons = node.consequent
            alt = node.alternate

            then_states = walk_block(
                cons.body if cons.type == "BlockStatement" else [cons],
                [(then_cond, list(setters), True, aliases, list(skips))]
            )

            if alt:
                else_states = walk_block(
                    alt.body if alt.type == "BlockStatement" else [alt],
                    [(else_cond, list(setters), True, aliases, list(skips))]
                )
            else:
                else_states = [(else_cond, list(setters), True, aliases, list(skips))]

            return then_states + else_states

        # BLOCK
        if t == "BlockStatement":
            return walk_block(node.body, [(cond, setters, True, aliases, skips)])

        # EXPRESSION STATEMENT
        if t == "ExpressionStatement":
            expr = node.expression

            # TERNARIO COME STATEMENT
            if isinstance(expr, TernaryExpr):
                parts = explode_ternary(expr)
                out = []
                for local_cond, local_expr in parts:
                    nc = And(cond, local_cond)

                    fake = type("ES", (), {})()
                    fake.type = "ExpressionStatement"
                    fake.expression = local_expr

                    out.extend(walk_stmt(fake, nc, list(setters), aliases, list(skips)))
                return out

            # ASSIGNMENT
            if expr.type == "AssignmentExpression":
                if expr.left.type == "Identifier":
                    name = expr.left.name
                    value_expr = parser.build_expr(expr.right, aliases)

                    parts = explode_ternary(value_expr)
                    out = []
                    for local_cond, local_val in parts:
                        nc = And(cond, local_cond)

                        val = substitute_aliases(local_val, aliases)
                        val = simplify_fix(val)
                        val = eval_expr(val)

                        new_alias = aliases.copy()
                        new_alias[name] = val

                        out.append((nc, setters, True, new_alias, skips))

                    return out

            # CALL -> SKIP / SETTER
            if expr.type == "CallExpression":
                path = parser._extract_path(expr.callee)

                # SKIP — accumulate target on state, don't create separate outcome
                if path and path.endswith(".skip"):
                    target = path[:-5]
                    new_skips = skips + [target]
                    return [(cond, setters, True, aliases, new_skips)]

                # SETTER
                if path and ".set" in path:
                    raw = path.split(".")[-1]
                    if raw.startswith("set"):

                        if expr.arguments and len(expr.arguments) > 0:
                            value_expr = parser.build_expr(expr.arguments[0], aliases)
                        else:
                            value_expr = Const(None)

                        parts = explode_ternary(value_expr)

                        out = []
                        for local_cond, local_val in parts:
                            nc = And(cond, local_cond)

                            val = substitute_aliases(local_val, aliases)
                            val = simplify_fix(val)
                            val = eval_expr(val)

                            new_setters = setters + [{
                                "method": path,
                                "value": val,
                            }]
                            out.append((nc, new_setters, True, aliases, skips))

                        return out

        # default: nessuna semantica
        return [(cond, setters, True, aliases, skips)]

    # Avvio sul body della AST
    root = ast.body if hasattr(ast, "body") else []
    initial_states = [(TRUE(), [], True, {}, [])]
    final_states = walk_block(root, initial_states)

    # Costruzione outcomes da tutti i rami vivi
    outcomes: List[Dict[str, Any]] = []

    for cond, setters, alive, aliases, skips in final_states:
        if not alive:
            continue

        cond_res = substitute_aliases(cond, aliases)
        cond_res = simplify_fix(cond_res)
        cond_res = eval_expr(cond_res)

        setters_res = []
        for s in setters:
            val = substitute_aliases(s["value"], aliases)
            val = simplify_fix(val)
            val = eval_expr(val)
            setters_res.append({
                "method": s["method"],
                "value": val,
            })

        skip_targets = sorted(set(skips))

        outcomes.append({
            "condition": cond_res,
            "skip": len(skip_targets) > 0,
            "skip_targets": skip_targets,
            "setters": setters_res,
        })

    # Filtraggio path triviali / impossibili
    def is_impossible(o: Dict[str, Any]) -> bool:
        return isinstance(o["condition"], Const) and o["condition"].value is False

    def is_trivial(o: Dict[str, Any]) -> bool:
        return (not o["skip"]) and (not o["setters"])

    filtered = [o for o in outcomes if not is_impossible(o) and not is_trivial(o)]

    # Deduplicazione dei path
    seen = set()
    unique_outcomes: List[Dict[str, Any]] = []

    for o in filtered:
        cond_str = _expr_to_str(o["condition"])
        setter_methods = tuple(sorted(s["method"] for s in o["setters"]))
        skip_tgts = tuple(sorted(o.get("skip_targets", [])))

        sig = (cond_str, setter_methods, skip_tgts)
        if sig in seen:
            continue
        seen.add(sig)
        unique_outcomes.append(o)

    if not unique_outcomes:
        return []

    # Normalizzazione livello 2
    normalized = normalize_paths(unique_outcomes)

    # Macro-merge dei path
    macro = merge_equivalent_paths_safe(normalized)

    # Remove trivial
    final = [o for o in macro if not (not o["skip"] and len(o["setters"]) == 0)]

    return final


# ============================================================
# Used APIs (getter/setter)
# ============================================================

def extract_used_filter_codes_semantic(parsed: Dict[str, Any]):
    """
    Estrae:
      - true_getters: getter realmente letti nel codice
      - used_namespaces: namespace validi per scenario/validazione
      - used_setters: setter effettivamente chiamati
      - outcomes: path semantici
    """

    outcomes = build_outcomes_from_ast(parsed)

    true_getters = sorted({
        g for g in extract_getters_from_outcomes(outcomes)
        if isinstance(g, str) and "." in g
    })

    used_namespaces = normalize_platform_getters(
        true_getters,
        parsed["parser"].platform_getter_index
    )

    used_setters = sorted({
        s["method"]
        for o in outcomes
        for s in o.get("setters", [])
        if "method" in s
    })

    return true_getters, used_namespaces, used_setters, outcomes


# ============================================================
# PATH MERGE SAFETY
# ============================================================

def is_path_merge_safe(p1, p2):
    if p1["skip"] != p2["skip"]:
        return False

    # Skip paths: allow merge if conditions are equivalent (same branch),
    # so merge_group can combine their targets.  Block if conditions differ
    # to avoid "skip both under either condition" (semantically wrong).
    if p1["skip"]:
        c1 = _expr_to_str(p1["condition"]) if p1["condition"] is not None else ""
        c2 = _expr_to_str(p2["condition"]) if p2["condition"] is not None else ""
        return c1 == c2

    set1 = {s["method"] for s in p1["setters"]}
    set2 = {s["method"] for s in p2["setters"]}

    if set1 != set2:
        return False

    # Do NOT merge if setter values differ (e.g. same method, different arguments)
    vals1 = {(s["method"], _expr_to_str(s["value"]) if s["value"] is not None else None) for s in p1["setters"]}
    vals2 = {(s["method"], _expr_to_str(s["value"]) if s["value"] is not None else None) for s in p2["setters"]}
    if vals1 != vals2:
        return False

    # Do NOT merge if any setter value is unresolved (<unknown>)
    for v in vals1 | vals2:
        if v[1] is not None and "<unknown>" in v[1]:
            return False

    relevant_vars = set()
    for s in p1["setters"]:
        if s["value"] is not None:
            relevant_vars |= extract_field_refs(s["value"])

    refs1 = extract_field_refs(p1["condition"])
    refs2 = extract_field_refs(p2["condition"])

    diff = (refs1 - refs2) | (refs2 - refs1)

    if not diff:
        return True

    for d in diff:
        root = d.split(".")[0]
        if d in relevant_vars or root in relevant_vars:
            return False

    return True

def merge_group(group):
    assert len(group) >= 1

    skip_flag = group[0]["skip"]
    setters = group[0]["setters"]

    if skip_flag:
        skip_targets = sorted({
            t for p in group for t in p.get("skip_targets", [])
        })
    else:
        skip_targets = []

    merged_cond = group[0]["condition"]
    for p in group[1:]:
        merged_cond = BinOp("||", merged_cond, p["condition"])

    merged_cond = simplify_condition_logic(merged_cond)

    return {
        "condition": merged_cond,
        "skip": skip_flag,
        "skip_targets": skip_targets,
        "setters": setters,
    }


def differing_parts_only_use(c1: Expr, c2: Expr, irrelevant_vars: set) -> bool:
    r1 = extract_field_refs(c1)
    r2 = extract_field_refs(c2)

    diff = (r1 - r2) | (r2 - r1)

    if not diff:
        return True

    for d in diff:
        root = d.split(".")[0]
        if d not in irrelevant_vars and root not in irrelevant_vars:
            return False

    return True


# ============================================================
# SIMPLIFY CONDITION LOGIC — sympy.logic + equality absorption
# ============================================================

import sympy.logic.boolalg as _sbl
from sympy import Symbol as _SympySymbol


def _expr_to_sympy(expr: Expr, atom_map: dict, reverse_map: dict):
    """Convert Expr tree to sympy boolean expression.
    Atomic comparisons (==, !=, <, >, <=, >=) become sympy Symbols.
    &&/|| become And/Or, ! becomes Not.
    """
    if isinstance(expr, Const):
        if expr.value is True:
            return _sbl.true
        if expr.value is False:
            return _sbl.false
        # Non-boolean constant treated as atom
        key = _expr_to_str(expr)
        if key not in atom_map:
            sym = _SympySymbol(f"_a{len(atom_map)}")
            atom_map[key] = sym
            reverse_map[sym] = expr
        return atom_map[key]

    if isinstance(expr, BinOp):
        if expr.op == "&&":
            return _sbl.And(
                _expr_to_sympy(expr.left, atom_map, reverse_map),
                _expr_to_sympy(expr.right, atom_map, reverse_map),
            )
        if expr.op == "||":
            return _sbl.Or(
                _expr_to_sympy(expr.left, atom_map, reverse_map),
                _expr_to_sympy(expr.right, atom_map, reverse_map),
            )
        # Comparison operators (==, !=, <, >, <=, >=) → atomic symbol
        key = _expr_to_str(expr)
        if key not in atom_map:
            sym = _SympySymbol(f"_a{len(atom_map)}")
            atom_map[key] = sym
            reverse_map[sym] = expr
        return atom_map[key]

    if isinstance(expr, UnOp) and expr.op == "!":
        return _sbl.Not(_expr_to_sympy(expr.expr, atom_map, reverse_map))

    # Any other Expr → atomic symbol
    key = _expr_to_str(expr)
    if key not in atom_map:
        sym = _SympySymbol(f"_a{len(atom_map)}")
        atom_map[key] = sym
        reverse_map[sym] = expr
    return atom_map[key]


def _sympy_to_expr(s_expr, reverse_map: dict) -> Expr:
    """Convert sympy boolean expression back to Expr tree."""
    if s_expr is _sbl.true or s_expr == True:
        return Const(True)
    if s_expr is _sbl.false or s_expr == False:
        return Const(False)

    if isinstance(s_expr, _SympySymbol):
        return reverse_map.get(s_expr, Const(True))

    if isinstance(s_expr, _sbl.And):
        items = sorted(s_expr.args, key=lambda a: str(a))
        acc = _sympy_to_expr(items[0], reverse_map)
        for item in items[1:]:
            acc = BinOp("&&", acc, _sympy_to_expr(item, reverse_map))
        return acc

    if isinstance(s_expr, _sbl.Or):
        items = sorted(s_expr.args, key=lambda a: str(a))
        acc = _sympy_to_expr(items[0], reverse_map)
        for item in items[1:]:
            acc = BinOp("||", acc, _sympy_to_expr(item, reverse_map))
        return acc

    if isinstance(s_expr, _sbl.Not):
        inner = _sympy_to_expr(s_expr.args[0], reverse_map)
        # If inner is a comparison, apply De Morgan directly
        if isinstance(inner, BinOp):
            neg = {"==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<"}
            if inner.op in neg:
                return BinOp(neg[inner.op], inner.left, inner.right)
        return UnOp("!", inner)

    return Const(True)


def _equality_absorption_pass(expr: Expr) -> Expr:
    """
    Post-pass: in AND conjunctions, if (X == A) is present,
    remove any (X != B) where A != B (since equality implies all inequalities).
    sympy doesn't know about this domain-specific rule.
    """
    if not isinstance(expr, BinOp) or expr.op != "&&":
        return expr

    # Flatten AND
    def flatten(e):
        if isinstance(e, BinOp) and e.op == "&&":
            return flatten(e.left) + flatten(e.right)
        return [e]

    items = flatten(expr)

    # Collect equalities: {lhs_str: const_repr}
    equalities = {}
    for item in items:
        if isinstance(item, BinOp) and item.op == "==":
            lhs = _expr_to_str(item.left)
            if isinstance(item.right, Const):
                equalities[lhs] = repr(item.right.value)
            elif isinstance(item.left, Const):
                equalities[_expr_to_str(item.right)] = repr(item.left.value)

    if not equalities:
        return expr

    filtered = []
    for item in items:
        if isinstance(item, BinOp) and item.op == "!=":
            lhs = _expr_to_str(item.left)
            rhs_val = repr(item.right.value) if isinstance(item.right, Const) else None
            if lhs in equalities and rhs_val is not None and equalities[lhs] != rhs_val:
                continue
            rhs = _expr_to_str(item.right)
            lhs_val = repr(item.left.value) if isinstance(item.left, Const) else None
            if rhs in equalities and lhs_val is not None and equalities[rhs] != lhs_val:
                continue
        filtered.append(item)

    if not filtered:
        return Const(True)

    acc = filtered[0]
    for item in filtered[1:]:
        acc = BinOp("&&", acc, item)
    return acc


def simplify_condition_logic(expr: Expr, soft_numeric: bool = False) -> Expr:
    """
    Boolean simplification using sympy.logic + equality absorption.

    Pipeline:
    1. Optional soft_normalize_numeric
    2. simplify_fix (constant folding, double negation)
    3. Convert to sympy → simplify_logic → convert back
    4. Equality absorption (domain-specific: X==A implies X!=B)
    """
    if soft_numeric:
        expr = soft_normalize_numeric(expr)
    expr = simplify_fix(expr)

    # Only apply sympy to boolean connectives (&&, ||, !)
    if not isinstance(expr, (BinOp, UnOp)):
        return expr
    if isinstance(expr, BinOp) and expr.op not in ("&&", "||"):
        return expr

    try:
        atom_map = {}
        reverse_map = {}
        s_expr = _expr_to_sympy(expr, atom_map, reverse_map)
        simplified = _sbl.simplify_logic(s_expr)
        result = _sympy_to_expr(simplified, reverse_map)
    except Exception:
        # Fallback: return as-is if sympy chokes
        result = expr

    # Post-pass: equality absorption
    result = _equality_absorption_pass(result)

    return result


# ============================================================
# MERGE EQUIVALENT PATHS
# ============================================================

def merge_equivalent_paths(outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = {}

    for o in outcomes:
        skip = o["skip"]
        key_setters = tuple(sorted(s["method"] for s in o["setters"]))

        cond_norm = simplify_condition_logic(o["condition"])

        if skip:
            merged.setdefault((key_setters, True), []).append(cond_norm)
        else:
            merged.setdefault((key_setters, False), []).append(cond_norm)

    final_paths = []

    for (setters_key, skip_flag), cond_list in merged.items():
        if skip_flag:
            for p in outcomes:
                if p["skip"]:
                    final_paths.append({
                        "condition": simplify_condition_logic(p["condition"]),
                        "skip": True,
                        "skip_targets": list(p.get("skip_targets", [])),
                        "setters": [],
                    })

        else:
            if len(cond_list) == 1:
                merged_cond = cond_list[0]
            else:
                acc = cond_list[0]
                for c in cond_list[1:]:
                    acc = BinOp("||", acc, c)
                    acc = simplify_condition_logic(acc)
                merged_cond = acc

            final_paths.append({
                "condition": merged_cond,
                "skip": False,
                "skip_targets": [],
                "setters": [
                    {"method": m, "value": None}
                    for m in setters_key
                ]
            })

    return final_paths


def merge_equivalent_paths_safe(outcomes):
    merged = []
    used = set()

    for i, p1 in enumerate(outcomes):
        if i in used: continue
        group = [p1]

        for j, p2 in enumerate(outcomes):
            if j <= i or j in used: continue
            if is_path_merge_safe(p1, p2):
                group.append(p2)
                used.add(j)

        merged.append(merge_group(group))

    return merged


def normalize_paths(outcomes: List[Dict[str, Any]]):
    cleaned = []

    for o in outcomes:
        cond = simplify_condition_logic(o["condition"])
        skip = o["skip"]

        setters = []
        seen_methods = set()
        for s in o["setters"]:
            method = s["method"]
            if method not in seen_methods:
                seen_methods.add(method)
                setters.append(s)

        cleaned.append({
            "condition": cond,
            "skip": skip,
            "skip_targets": list(o.get("skip_targets", [])),
            "setters": setters,
        })

    merged = []
    seen = set()

    for o in cleaned:
        sig = (
            _expr_to_str(o["condition"]),
            o["skip"],
            tuple(sorted(o.get("skip_targets", []))),
            tuple(sorted(s["method"] for s in o["setters"])),
        )
        if sig not in seen:
            seen.add(sig)
            merged.append(o)

    return merged

def extract_getters_from_outcomes(outcomes):
    getters = set()

    def collect(expr):
        if isinstance(expr, Field):
            getters.add(expr.path)
        elif isinstance(expr, Var):
            getters.add(expr.name)
        elif isinstance(expr, BinOp):
            collect(expr.left)
            collect(expr.right)
        elif isinstance(expr, UnOp):
            collect(expr.expr)
        elif isinstance(expr, CallExpr):
            if not (isinstance(expr.func, Field) and expr.func.path in JS_GLOBAL_FUNCTIONS):
                collect(expr.func)
            for a in expr.args:
                collect(a)
        elif isinstance(expr, NativeMethod):
            collect(expr.obj)

    for o in outcomes:
        collect(o["condition"])
        for s in o["setters"]:
            if s["value"] is not None:
                collect(s["value"])

    return sorted(getters)


def normalize_platform_getters(getters, platform_index):
    out = set()
    for g in getters:
        parts = g.split(".")
        if len(parts) >= 2:
            ns = ".".join(parts[:2])
            if ns in platform_index and g in platform_index[ns]:
                out.add(ns)
    return sorted(out)
