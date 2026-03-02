"""
Expr DSL — lightweight AST for representing JS expressions.

Classes: Expr, Const, Field, Var, UnOp, BinOp, CallExpr, NativeMethod,
         TernaryExpr, Concat
Constructors: TRUE, FALSE, And, Or, Not
Functions: is_const_expr, eval_const_expr, simplify, simplify_fix,
           soft_normalize_numeric, eval_expr, substitute_aliases,
           _expr_to_str, extract_field_refs, explode_ternary

Constant folding (eval_expr) uses PyMiniRacer (V8 engine) for JS evaluation.
"""
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from py_mini_racer import MiniRacer

# ============================================================
# NATIVE METHODS / GLOBAL FUNCTIONS (constants)
# ============================================================

JS_NATIVE_METHODS = {
    # String methods
    "trim", "toLowerCase", "toUpperCase",
    "slice", "substring", "substr",
    "replace", "replaceAll", "split",
    "charAt", "charCodeAt",
    "includes", "startsWith", "endsWith",
    "padStart", "padEnd", "repeat",
    "toString",

    # Number.prototype
    "toFixed", "toPrecision", "toExponential",

    # Array prototype (fold only on Const)
    "join", "concat", "indexOf", "lastIndexOf", "slice", "splice",

    # Object
    "hasOwnProperty",
}

JS_GLOBAL_FUNCTIONS = {
    "Number", "String", "Boolean",
    "parseInt", "parseFloat",
    "isNaN", "isFinite",
    "encodeURI", "encodeURIComponent",
    "decodeURI", "decodeURIComponent",
}

# ============================================================
# EXPR DSL
# ============================================================

class Expr:
    pass

@dataclass(frozen=True)
class TernaryExpr(Expr):
    test: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass(frozen=True)
class Concat(Expr):
    items: List[Expr]

@dataclass(frozen=True)
class Const(Expr):
    value: Any

@dataclass(frozen=True)
class Field(Expr):
    path: str

@dataclass(frozen=True)
class Var(Expr):
    name: str

@dataclass(frozen=True)
class UnOp(Expr):
    op: str
    expr: Expr

@dataclass(frozen=True)
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr

@dataclass(frozen=True)
class CallExpr(Expr):
    func: Expr
    args: List[Expr]

@dataclass(frozen=True)
class NativeMethod(Expr):
    name: str
    obj: Expr


def TRUE() -> Expr:  return Const(True)
def FALSE() -> Expr: return Const(False)
def And(a: Expr, b: Expr) -> Expr: return BinOp("&&", a, b)
def Or(a: Expr, b: Expr) -> Expr:  return BinOp("||", a, b)
def Not(e: Expr) -> Expr:          return UnOp("!", e)

# ============================================================
# CONSTANT EXPRESSION EVALUATION
# ============================================================

def is_const_expr(e: Expr) -> bool:
    if isinstance(e, Const):
        return True
    if isinstance(e, (Field, Var)):
        return False
    if isinstance(e, UnOp):
        return is_const_expr(e.expr)
    if isinstance(e, BinOp):
        return is_const_expr(e.left) and is_const_expr(e.right)
    if isinstance(e, CallExpr):
        f = getattr(e.func, "path", None)
        return (f in {"Number", "String"} and all(is_const_expr(a) for a in e.args))
    return False


def eval_const_expr(e: Expr):
    if isinstance(e, Const):
        return e.value

    if isinstance(e, UnOp):
        v = eval_const_expr(e.expr)
        if v is None:
            return None
        if e.op == "!":
            return not v
        return None

    if isinstance(e, BinOp):
        L = eval_const_expr(e.left)
        R = eval_const_expr(e.right)
        if L is None or R is None:
            return None
        try:
            if e.op == "==": return L == R
            if e.op == "!=": return L != R
            if e.op == "<":  return L < R
            if e.op == ">":  return L > R
            if e.op == "<=": return L <= R
            if e.op == ">=": return L >= R
            if e.op == "+":  return L + R
            if e.op == "-":  return L - R
            if e.op == "*":  return L * R
            if e.op == "/":  return L / R
            if e.op == "&&": return L and R
            if e.op == "||": return L or R
        except Exception:
            return None

    if isinstance(e, CallExpr):
        f = getattr(e.func, "path", None)
        if f == "Number":
            v = eval_const_expr(e.args[0])
            try:
                return float(v)
            except Exception:
                return None

    return None

# ============================================================
# SIMPLIFY
# ============================================================

def simplify(e: Expr) -> Expr:
    if isinstance(e, Const):
        return e
    if isinstance(e, Var):
        return e
    if isinstance(e, Field):
        return e

    # NOT / Unary
    if isinstance(e, UnOp):
        inner = simplify(e.expr)

        # !(Const)
        if isinstance(inner, Const) and isinstance(inner.value, bool):
            return Const(not inner.value)

        # NOT di comparazioni
        if isinstance(inner, BinOp):
            op = inner.op
            if op == "==":  return simplify(BinOp("!=", inner.left, inner.right))
            if op == "!=":  return simplify(BinOp("==", inner.left, inner.right))
            if op == "<":   return simplify(BinOp(">=", inner.left, inner.right))
            if op == ">":   return simplify(BinOp("<=", inner.left, inner.right))
            if op == "<=":  return simplify(BinOp(">",  inner.left, inner.right))
            if op == ">=":  return simplify(BinOp("<",  inner.left, inner.right))

        return UnOp(e.op, inner)

    # Binary
    if isinstance(e, BinOp):
        L = simplify(e.left)
        R = simplify(e.right)

        # ---------- AND ----------
        if e.op == "&&":
            if isinstance(L, Const) and L.value is False:
                return Const(False)
            if isinstance(R, Const) and R.value is False:
                return Const(False)
            if isinstance(L, Const) and L.value is True:
                return simplify(R)
            if isinstance(R, Const) and R.value is True:
                return simplify(L)
            return BinOp("&&", L, R)

        # ---------- OR ----------
        if e.op == "||":
            if isinstance(L, Const) and L.value is True:
                return Const(True)
            if isinstance(R, Const) and R.value is True:
                return Const(True)
            if isinstance(L, Const) and L.value is False:
                return simplify(R)
            if isinstance(R, Const) and R.value is False:
                return simplify(L)
            return BinOp("||", L, R)

        # ---------- OTHER OPS ----------
        return BinOp(e.op, L, R)

    # CallExpr
    if isinstance(e, CallExpr):
        return CallExpr(simplify(e.func), [simplify(a) for a in e.args])

    # NativeMethod
    if isinstance(e, NativeMethod):
        return NativeMethod(e.name, simplify(e.obj))

    return e

def simplify_fix(e: Expr) -> Expr:
    prev = None
    curr = e

    while _expr_to_str(prev) != _expr_to_str(curr):
        prev = curr
        curr = simplify(curr)

    return curr

def soft_normalize_numeric(expr: Expr) -> Expr:
    """
    Applica equivalenze numeriche leggere:
      x > n   -> x >= n
      x < n   -> x <= n
    """
    if isinstance(expr, BinOp):
        L = soft_normalize_numeric(expr.left)
        R = soft_normalize_numeric(expr.right)
        op = expr.op

        if op == ">":
            op = ">="
        elif op == "<":
            op = "<="

        return BinOp(op, L, R)

    if isinstance(expr, UnOp):
        return UnOp(expr.op, soft_normalize_numeric(expr.expr))

    if isinstance(expr, CallExpr):
        return CallExpr(
            soft_normalize_numeric(expr.func),
            [soft_normalize_numeric(a) for a in expr.args]
        )

    return expr

# ============================================================
# V8 ENGINE — constant folding via PyMiniRacer
# ============================================================

# Lazy singleton: initialized on first use
_v8_ctx: Optional[MiniRacer] = None

def _get_v8() -> MiniRacer:
    global _v8_ctx
    if _v8_ctx is None:
        _v8_ctx = MiniRacer()
    return _v8_ctx


def _const_to_js(value) -> Optional[str]:
    """Convert a Python constant to its JS literal representation."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)  # proper JS string escaping
    if isinstance(value, list):
        items = [_const_to_js(x) for x in value]
        if any(x is None for x in items):
            return None
        return "[" + ",".join(items) + "]"
    if isinstance(value, dict):
        pairs = []
        for k, v in value.items():
            kjs = json.dumps(str(k))
            vjs = _const_to_js(v)
            if vjs is None:
                return None
            pairs.append(f"{kjs}:{vjs}")
        return "{" + ",".join(pairs) + "}"
    return None


def _v8_result_to_const(result) -> Expr:
    """Convert V8 eval result to Const, normalizing types."""
    if result is None:
        return Const(None)
    if isinstance(result, bool):
        return Const(result)
    if isinstance(result, float):
        if result == int(result) and not math.isinf(result) and not math.isnan(result):
            return Const(int(result))
        return Const(result)
    if isinstance(result, int):
        return Const(result)
    if isinstance(result, str):
        return Const(result)
    # For complex return types (arrays), try JSON
    return Const(result)


# Method calls where first arg is the object: obj.method(arg1, arg2, ...)
_INSTANCE_METHODS = {
    # String.prototype
    "trim", "toLowerCase", "toUpperCase", "toString",
    "slice", "substring", "substr",
    "replace", "replaceAll", "split",
    "charAt", "charCodeAt",
    "includes", "startsWith", "endsWith",
    "padStart", "padEnd", "repeat",
    "indexOf", "lastIndexOf",
    # Number.prototype
    "toFixed", "toPrecision", "toExponential",
    # Array.prototype
    "join", "concat",
    # Object.prototype
    "hasOwnProperty",
}

# Global functions: name(arg1, arg2, ...)
_GLOBAL_FUNCTIONS = {
    "Number", "String", "Boolean",
    "parseInt", "parseFloat",
    "isNaN", "isFinite",
    "encodeURI", "encodeURIComponent",
    "decodeURI", "decodeURIComponent",
}


def _try_v8_fold(name: str, args: List[Expr]) -> Optional[Expr]:
    """Try to fold a function/method call with all-Const args using V8.
    Returns Const on success, None if not foldable.
    """
    # Check all args are Const
    if not all(isinstance(a, Const) for a in args):
        return None

    js_args = [_const_to_js(a.value) for a in args]
    if any(x is None for x in js_args):
        return None

    # Build JS expression
    if name in _GLOBAL_FUNCTIONS:
        js_expr = f"{name}({','.join(js_args)})"
    elif name in _INSTANCE_METHODS and len(js_args) >= 1:
        obj_js = js_args[0]
        rest = ",".join(js_args[1:])
        # Wrap numeric literals in parens for method calls: (3.14).toFixed(2)
        if isinstance(args[0].value, (int, float)):
            obj_js = f"({obj_js})"
        js_expr = f"{obj_js}.{name}({rest})"
    else:
        return None

    # For split/array methods, wrap in JSON.stringify to get proper array back
    needs_json = name in ("split",)

    try:
        v8 = _get_v8()
        if needs_json:
            result = v8.eval(f"JSON.stringify({js_expr})")
            result = json.loads(result)
        else:
            result = v8.eval(js_expr)
        return _v8_result_to_const(result)
    except Exception:
        return None


# ============================================================
# EVAL EXPR — FOLDING NATIVE JS (via V8)
# ============================================================

def eval_expr(e: Expr) -> Expr:
    """Constant-fold expressions. Uses V8 engine for JS method/function calls."""
    # BASE CASES
    if isinstance(e, Const):
        return e
    if isinstance(e, Var):
        return e
    if isinstance(e, Field):
        return e

    # UNARY
    if isinstance(e, UnOp):
        inner = eval_expr(e.expr)
        if isinstance(inner, Const) and e.op == "!":
            return Const(not inner.value)
        return UnOp(e.op, inner)

    # BINARY
    if isinstance(e, BinOp):
        L = eval_expr(e.left)
        R = eval_expr(e.right)

        if isinstance(L, Const) and isinstance(R, Const):
            try:
                op = e.op
                if op == "+":  return Const(L.value + R.value)
                if op == "-":  return Const(L.value - R.value)
                if op == "*":  return Const(L.value * R.value)
                if op == "/":  return Const(L.value / R.value)
                if op == "==": return Const(L.value == R.value)
                if op == "!=": return Const(L.value != R.value)
                if op == "<":  return Const(L.value < R.value)
                if op == "<=": return Const(L.value <= R.value)
                if op == ">":  return Const(L.value > R.value)
                if op == ">=": return Const(L.value >= R.value)
            except Exception:
                pass

        return BinOp(e.op, L, R)

    # CONCAT (flatten + merge adjacent string constants)
    if isinstance(e, Concat):
        new_items: List[Expr] = []
        buffer = ""

        for item in e.items:
            item_eval = eval_expr(item)
            if isinstance(item_eval, Const) and isinstance(item_eval.value, str):
                buffer += item_eval.value
            else:
                if buffer:
                    new_items.append(Const(buffer))
                    buffer = ""
                new_items.append(item_eval)

        if buffer:
            new_items.append(Const(buffer))

        if len(new_items) == 1:
            return new_items[0]

        return Concat(new_items)

    # CALL EXPRESSION — fold via V8 when all args are Const
    if isinstance(e, CallExpr):
        fn = eval_expr(e.func)
        args = [eval_expr(a) for a in e.args]

        if isinstance(fn, Field):
            result = _try_v8_fold(fn.path, args)
            if result is not None:
                return result

        return CallExpr(fn, args)

    # fallback
    return e

# ============================================================
# SUBSTITUTE ALIASES
# ============================================================

def substitute_aliases(expr: Expr, aliases: Dict[str, Expr]) -> Expr:
    def sub(e: Expr) -> Expr:
        if isinstance(e, Field):
            base = e.path.split(".", 1)[0]
            if base in aliases and isinstance(aliases[base], Field):
                alias = aliases[base].path
                suffix = e.path[len(base):]
                return Field(alias + suffix)
            return e

        if isinstance(e, Var):
            if e.name in aliases:
                return aliases[e.name]
            return e

        if isinstance(e, Const):
            return e

        if isinstance(e, UnOp):
            return UnOp(e.op, sub(e.expr))

        if isinstance(e, BinOp):
            return BinOp(e.op, sub(e.left), sub(e.right))

        if isinstance(e, CallExpr):
            return CallExpr(sub(e.func), [sub(a) for a in e.args])

        if isinstance(e, NativeMethod):
            return NativeMethod(e.name, sub(e.obj))

        return e

    new = sub(expr)

    if is_const_expr(new):
        val = eval_const_expr(new)
        if val is not None:
            return Const(val)

    return new

# ============================================================
# Pretty-print Expr
# ============================================================

def _expr_to_str(e: Expr) -> str:
    if isinstance(e, Const):
        return repr(e.value)
    if isinstance(e, Field):
        return e.path
    if isinstance(e, Var):
        return e.name
    if isinstance(e, UnOp):
        return f"({e.op}{_expr_to_str(e.expr)})"
    if isinstance(e, BinOp):
        return f"({_expr_to_str(e.left)} {e.op} {_expr_to_str(e.right)})"
    if isinstance(e, CallExpr):
        func = _expr_to_str(e.func)
        args = ", ".join(_expr_to_str(a) for a in e.args)
        return f"{func}({args})"
    if isinstance(e, NativeMethod):
        return f"{_expr_to_str(e.obj)}.{e.name}"
    if isinstance(e, Concat):
        parts = []
        for item in e.items:
            s = _expr_to_str(item)
            # Strip repr quotes from Const strings for cleaner concat
            if isinstance(item, Const) and isinstance(item.value, str):
                parts.append(item.value)
            else:
                parts.append(s)
        return " + ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")
    return str(e)

# ============================================================
# EXTRACT FIELD REFS
# ============================================================

def extract_field_refs(expr: Expr) -> set:
    refs = set()

    def walk(e):
        if isinstance(e, Field):
            refs.add(e.path)
        elif isinstance(e, Var):
            refs.add(e.name)
        elif isinstance(e, BinOp):
            walk(e.left)
            walk(e.right)
        elif isinstance(e, UnOp):
            walk(e.expr)
        elif isinstance(e, CallExpr):
            walk(e.func)
            for a in e.args:
                walk(a)
        elif isinstance(e, NativeMethod):
            walk(e.obj)

    walk(expr)
    return refs

# ============================================================
# EXPLODE TERNARY
# ============================================================

def explode_ternary(expr: Expr):
    if not isinstance(expr, TernaryExpr):
        return [(TRUE(), expr)]

    test   = expr.test
    cons   = expr.then_expr
    alt    = expr.else_expr

    cons_parts = explode_ternary(cons)
    alt_parts  = explode_ternary(alt)

    results = []

    for ccond, cexpr in cons_parts:
        results.append((And(test, ccond), cexpr))

    for acond, aexpr in alt_parts:
        results.append((And(Not(test), acond), aexpr))

    return results
