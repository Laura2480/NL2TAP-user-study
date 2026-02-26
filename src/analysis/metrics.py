"""
Semantic Metrics 3.1 for IFTTT Filter Code

FORMAL FILTER VALIDITY
- no 'return'
- no arrow functions ('=>')
- no JSON-like blocks
- at least one execution path OR at least one setter call

SEMANTIC SIMILARITY
- skip_similarity            (soft condition similarity)
- skip_target_similarity     (Jaccard on skip targets)
- effect_similarity          (Jaccard on setter methods)
- path_similarity            (Jaccard on normalized paths)
- api_usage_score            (coverage + precision over API surface)
- semantic_similarity        (weighted combination)

REDUNDANCY (diagnostic)
- code_redundancy_pred

Speed notes:
- Caches parsing + extraction for gold code (and also pred) to avoid recomputation
- Caches condition signatures and structural atoms
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Set, Tuple, Optional, Iterable

# ---- project imports ----
from src.code_parsing.parser import (
    safe_parse_with_tail_drop,
    extract_used_filter_codes_semantic,
    Expr, BinOp, UnOp, CallExpr, Field, Const,
    _expr_to_str,
)

# ============================================================
# ALWAYS-VALID META API
# ============================================================

GLOBAL_META_API: Set[str] = {
    "Meta.currentUserTime",
    "Meta.currentUserTime.year",
    "Meta.currentUserTime.month",
    "Meta.currentUserTime.day",
    "Meta.currentUserTime.dayOfWeek",
    "Meta.currentUserTime.weekOfYear",
    "Meta.currentUserTime.hour",
    "Meta.currentUserTime.minute",
}

# ============================================================
# BASIC UTILITIES
# ============================================================

def _to_set(x: Any) -> Set[Any]:
    if x is None:
        return set()
    if isinstance(x, set):
        return x
    if isinstance(x, (list, tuple)):
        return set(x)
    return {x}

def jaccard(A: Set[Any], B: Set[Any]) -> float:
    if not A and not B:
        return 1.0
    union = A | B
    return (len(A & B) / len(union)) if union else 0.0

def _looks_like_json_block(code: str) -> bool:
    stripped = code.lstrip()
    # crude but effective heuristic: JSON-like object/array literal at top-level
    return (stripped.startswith("{") or stripped.startswith("[")) and (":" in stripped)

# ============================================================
# CONDITION NORMALIZATION
# ============================================================

def rewrite_equivalent_patterns(expr: Expr) -> Expr:
    """
    Canonicalize semantically equivalent patterns:
      includes(S, T)    -> indexOf(S, T) >= 0
      !includes(S, T)   -> indexOf(S, T) == -1
    """
    # includes(x, y)
    if isinstance(expr, CallExpr) and isinstance(expr.func, Field):
        if expr.func.path == "includes" and len(expr.args) == 2:
            S, term = expr.args
            return BinOp(">=", CallExpr(Field("indexOf"), [S, term]), Const(0))

    # !includes(x, y)
    if isinstance(expr, UnOp) and expr.op == "!" and isinstance(expr.expr, CallExpr):
        inner = expr.expr
        if isinstance(inner.func, Field) and inner.func.path == "includes" and len(inner.args) == 2:
            S, term = inner.args
            return BinOp("==", CallExpr(Field("indexOf"), [S, term]), Const(-1))

    # recurse
    if isinstance(expr, BinOp):
        return BinOp(
            expr.op,
            rewrite_equivalent_patterns(expr.left),
            rewrite_equivalent_patterns(expr.right),
        )
    if isinstance(expr, UnOp):
        return UnOp(expr.op, rewrite_equivalent_patterns(expr.expr))
    if isinstance(expr, CallExpr):
        return CallExpr(
            rewrite_equivalent_patterns(expr.func),
            [rewrite_equivalent_patterns(a) for a in expr.args],
        )
    return expr

def _flatten_binop(e: Expr, op: str) -> List[Expr]:
    if isinstance(e, BinOp) and e.op == op:
        return _flatten_binop(e.left, op) + _flatten_binop(e.right, op)
    return [e]

def normalize_condition_expr(e: Expr) -> Expr:
    """Normalize AND/OR structure and ordering (canonical form)."""
    e = rewrite_equivalent_patterns(e)

    if isinstance(e, BinOp):
        L = normalize_condition_expr(e.left)
        R = normalize_condition_expr(e.right)

        if e.op in {"&&", "||"}:
            items: List[Expr] = []
            for c in (L, R):
                items.extend(_flatten_binop(c, e.op))
            items = [normalize_condition_expr(i) for i in items]
            items.sort(key=_expr_to_str)

            acc = items[0]
            for x in items[1:]:
                acc = BinOp(e.op, acc, x)
            return acc

        return BinOp(e.op, L, R)

    if isinstance(e, UnOp):
        return UnOp(e.op, normalize_condition_expr(e.expr))

    if isinstance(e, CallExpr):
        return CallExpr(normalize_condition_expr(e.func), [normalize_condition_expr(a) for a in e.args])

    return e

@lru_cache(maxsize=200_000)
def _condition_signature_from_str(expr_str: str) -> str:
    """
    Cache signatures keyed by the string form of the expression.
    Assumes _expr_to_str(expr) is stable for identical trees.
    """
    # NOTE: we cannot reconstruct Expr from string safely here;
    # cache is instead used through wrapper below that passes expr_str.
    return expr_str

def condition_signature(expr: Expr) -> str:
    sig = _expr_to_str(normalize_condition_expr(expr))
    # store in cache (cheap) so repeated occurrences reuse interned strings
    return _condition_signature_from_str(sig)

# ============================================================
# STRUCTURAL ATOMS + CACHES
# ============================================================

def extract_structural_atoms(expr: Expr) -> Set[str]:
    atoms: Set[str] = set()

    def walk(e: Expr):
        if isinstance(e, Field):
            atoms.add(f"Field:{e.path}")
        elif isinstance(e, UnOp):
            atoms.add(f"UnOp:{e.op}")
            walk(e.expr)
        elif isinstance(e, BinOp):
            atoms.add(f"BinOp:{e.op}")
            walk(e.left)
            walk(e.right)
        elif isinstance(e, CallExpr):
            atoms.add(f"Call:{_expr_to_str(e.func)}")
            for a in e.args:
                walk(a)
        elif isinstance(e, Const):
            atoms.add(f"Const:{repr(e.value)}")

    walk(expr)
    return atoms

@lru_cache(maxsize=200_000)
def _atoms_from_signature(sig: str) -> Tuple[str, ...]:
    """
    Atom cache keyed by normalized signature string.
    We store atoms as a tuple for caching.
    """
    # We cannot rebuild Expr from sig; this cache is filled through wrapper below
    # by passing already-extracted atoms. This is a placeholder to keep interface symmetric.
    return tuple()

def _atoms_for_expr(expr: Expr) -> Tuple[str, ...]:
    # compute from normalized expr and cache by signature
    sig = condition_signature(expr)
    cached = _atoms_from_signature(sig)
    if cached:
        return cached
    atoms = tuple(sorted(extract_structural_atoms(normalize_condition_expr(expr))))
    # write-through cache (hack: lru_cache doesn't allow set; so we return atoms directly)
    # We rely on signature caching + downstream caching of soft similarity instead.
    return atoms

# ============================================================
# ATOM & CONDITION SIMILARITY
# ============================================================

def atom_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a.split(":")[0] == b.split(":")[0]:
        return 0.5
    return 0.0

@lru_cache(maxsize=200_000)
def _soft_similarity_from_signatures(sig_a: str, sig_b: str) -> float:
    # signature-only cache; actual atoms must be reconstructed from strings (not possible)
    # so we only use this cache when sig strings repeat exactly (fast path)
    return 1.0 if sig_a == sig_b else -1.0  # -1 sentinel for "not cached"

def condition_soft_similarity(pred: Expr, gold: Expr) -> float:
    # fast path on identical normalized signature
    sig_p = condition_signature(pred)
    sig_g = condition_signature(gold)
    cached = _soft_similarity_from_signatures(sig_p, sig_g)
    if cached >= 0.0:
        return round(cached, 3)

    A = list(_atoms_for_expr(pred))
    B = list(_atoms_for_expr(gold))

    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0

    used = set()
    scores = []

    for a in A:
        best = 0.0
        best_j = None
        for j, b in enumerate(B):
            if j in used:
                continue
            s = atom_similarity(a, b)
            if s > best:
                best, best_j = s, j
        scores.append(best)
        if best_j is not None:
            used.add(best_j)

    val = round(sum(scores) / len(scores), 3)
    return val

# ============================================================
# SKIP SIMILARITY
# ============================================================

def skip_soft_similarity(pred_out: List[Dict[str, Any]], gold_out: List[Dict[str, Any]]) -> float:
    P = [o["condition"] for o in pred_out if o.get("skip")]
    G = [o["condition"] for o in gold_out if o.get("skip")]

    if not P and not G:
        return 1.0
    if not P or not G:
        return 0.0

    s1 = [max(condition_soft_similarity(p, g) for g in G) for p in P]
    s2 = [max(condition_soft_similarity(g, p) for p in P) for g in G]
    return round((sum(s1) / len(s1) + sum(s2) / len(s2)) / 2.0, 3)

def skip_target_similarity(pred_out: List[Dict[str, Any]], gold_out: List[Dict[str, Any]]) -> float:
    def targets(outcomes: List[Dict[str, Any]]) -> Set[str]:
        return {t for o in outcomes if o.get("skip") for t in o.get("skip_targets", [])}

    return round(jaccard(targets(pred_out), targets(gold_out)), 3)

# ============================================================
# PATH REPRESENTATION
# ============================================================

@dataclass(frozen=True)
class PathSig:
    cond_sig: str
    skip: bool
    skip_targets: Tuple[str, ...]
    setters: Tuple[str, ...]

def path_signature(o: Dict[str, Any]) -> PathSig:
    return PathSig(
        cond_sig=condition_signature(o["condition"]),
        skip=bool(o.get("skip")),
        skip_targets=tuple(sorted(o.get("skip_targets", []))),
        setters=tuple(sorted(s["method"] for s in o.get("setters", []))),
    )

# ============================================================
# REDUNDANCY (DIAGNOSTIC)
# ============================================================

def compute_code_redundancy(pred_out: List[Dict[str, Any]]) -> float:
    non_skip = [o for o in pred_out if not o.get("skip")]
    if not non_skip:
        return 0.0

    # condition atoms redundancy
    atoms: List[str] = []
    for o in non_skip:
        atoms.extend(_atoms_for_expr(o["condition"]))
    red_atoms = len(atoms) / len(set(atoms)) if atoms else 1.0

    # setters redundancy
    setters = [s["method"] for o in non_skip for s in o.get("setters", [])]
    red_setters = len(setters) / len(set(setters)) if setters else 1.0

    score = 0.5 * len(non_skip) + 0.3 * red_atoms + 0.2 * red_setters
    return round(score, 3)

# ============================================================
# PARSE + EXTRACT CACHES (BIG SPEEDUP)
# ============================================================

@lru_cache(maxsize=50_000)
def _parse_cached(code: str, clean: bool) -> Tuple[Optional[Any], Optional[str]]:
    ast, _, err = safe_parse_with_tail_drop(code, clean=clean)
    return ast, err

@lru_cache(maxsize=50_000)
def _extract_cached(code: str, clean: bool) -> Tuple[str, Tuple[str, ...], Tuple[str, ...], List[Dict[str, Any]]]:
    """
    Returns:
      status, namespaces(tuple), methods(tuple), outcomes(list)
    Note: outcomes are returned as-is (list of dict) and assumed deterministic.
    """
    ast, err = _parse_cached(code, clean=clean)
    if err or ast is None:
        return "parse_error", tuple(), tuple(), []
    _, namespaces, methods, outcomes = extract_used_filter_codes_semantic(ast)
    return "ok", tuple(namespaces), tuple(methods), outcomes

# ============================================================
# CORE EVALUATION
# ============================================================

def evaluate_filter_pair(
    pred_code: str,
    gold_code: str,
    allowed_filter_keys: List[str],
    allowed_filter_methods_raw: List[str],
) -> Dict[str, Any]:
    """
    Compute semantic metrics for one predicted vs gold filter code pair.
    """
    result: Dict[str, Any] = {
        "status": "ok",
        "skip_similarity": 0.0,
        "skip_target_similarity": 0.0,
        "effect_similarity": 0.0,
        "path_similarity": 0.0,
        "semantic_similarity": 0.0,
        "api_coverage_score": 0.0,
        "api_precision_score": 0.0,
        "api_usage_score": 0.0,
        "invalid_filter_keys": [],
        "invalid_filter_methods": [],
        "code_redundancy_pred": 0.0,
        "is_valid": False,
    }

    pred_clean = (pred_code or "").strip()
    gold_clean = (gold_code or "").strip()

    # ---------- Quick formal validity checks (cheap)
    if "return" in pred_clean:
        result["status"] = "invalid_filter"
        return result
    if "=>" in pred_clean:
        result["status"] = "invalid_filter"
        return result
    if _looks_like_json_block(pred_clean):
        result["status"] = "invalid_filter"
        return result

    # ---------- Parse + extract (cached)
    pred_status, pred_ns_t, pred_m_t, pred_out = _extract_cached(pred_clean, clean=True)
    gold_status, gold_ns_t, gold_m_t, gold_out = _extract_cached(gold_clean, clean=False)

    if pred_status != "ok" or gold_status != "ok":
        result["status"] = "parse_error"
        return result

    pred_ns = set(pred_ns_t)
    pred_methods = set(pred_m_t)
    gold_ns = set(gold_ns_t)
    gold_methods = set(gold_m_t)

    # if absolutely nothing happens, invalid
    if not pred_out and not pred_methods:
        result["status"] = "invalid_filter"
        return result

    # ---------- Platform alignment sets
    allowed_keys = set(allowed_filter_keys or [])
    allowed_methods = set(m for m in (allowed_filter_methods_raw or []) if isinstance(m, str))
    allowed_methods |= GLOBAL_META_API

    # ---------- API usage (coverage/precision relative to gold API footprint)
    required = gold_ns | gold_methods
    present = pred_ns | pred_methods

    hits = required & present
    api_cov = len(hits) / len(required) if required else 1.0
    api_prec = len(hits) / len(present) if present else 1.0  # no-API doesn't mean wrong-API

    result["api_coverage_score"] = round(api_cov, 3)
    result["api_precision_score"] = round(api_prec, 3)
    result["api_usage_score"] = round(0.5 * (api_cov + api_prec), 3)

    # invalid keys/methods wrt platform catalog
    result["invalid_filter_keys"] = sorted(pred_ns - allowed_keys)
    result["invalid_filter_methods"] = sorted(pred_methods - allowed_methods)

    # ---------- Similarity metrics
    skip_sim = skip_soft_similarity(pred_out, gold_out)
    result["skip_similarity"] = skip_sim

    skip_t_sim = skip_target_similarity(pred_out, gold_out)
    result["skip_target_similarity"] = skip_t_sim

    pred_setters = {s["method"] for o in pred_out for s in o.get("setters", [])}
    gold_setters = {s["method"] for o in gold_out for s in o.get("setters", [])}
    eff_sim = jaccard(pred_setters, gold_setters)
    result["effect_similarity"] = round(eff_sim, 3)

    path_sim = jaccard(
        {path_signature(o) for o in pred_out},
        {path_signature(o) for o in gold_out},
    )
    result["path_similarity"] = round(path_sim, 3)

    semantic = (
        0.25 * skip_sim +
        0.25 * eff_sim +
        0.20 * path_sim +
        0.20 * result["api_usage_score"] +
        0.10 * skip_t_sim
    )
    result["semantic_similarity"] = round(semantic, 3)

    # ---------- Redundancy (diagnostic)
    result["code_redundancy_pred"] = compute_code_redundancy(pred_out)

    result["is_valid"] = True
    return result
