"""
JS Validator — code cleaning, esprima parsing, ASTParser.

Depends on: expr.py, esprima
Bug fixes applied:
  1. detect_and_unwrap_wrapper uses regex ^function\s+filter\s*\( instead of "filter" in stripped
  2. SetterCall dataclass has method: Optional[str] = None field
  3. Decoupled from torch: inline JSON loader replaces study_utils import
"""
import json
import re
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import esprima

from .expr import (
    Expr, Const, Field, Var, UnOp, BinOp, CallExpr, NativeMethod,
    TernaryExpr, Concat,
    JS_NATIVE_METHODS, JS_GLOBAL_FUNCTIONS,
    is_const_expr, eval_const_expr, simplify_fix, eval_expr,
)

logger = logging.getLogger(__name__)

# ============================================================
# INLINE JSON LOADER (replaces study_utils dependency)
# ============================================================

def _load_json_or_jsonl(path) -> list:
    """Minimal JSON/JSONL loader — no torch/numpy dependency."""
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


_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRIGGERS_PATH = Path(os.path.join(_BASE, "data/ifttt_catalog/triggers.json"))

# ============================================================
# PLATFORM GETTER INDEX
# ============================================================

def build_platform_getter_index(triggers_path=None) -> dict[str, set[str]]:
    if triggers_path is None:
        triggers_path = TRIGGERS_PATH
    triggers = _load_json_or_jsonl(triggers_path)

    index: dict[str, set[str]] = {}

    for trig in triggers:
        namespace = trig.get("namespace")
        if not namespace:
            continue

        ingredients = trig.get("ingredients", [])
        keys = {
            ing["filter_code_key"]
            for ing in ingredients
            if isinstance(ing, dict) and ing.get("filter_code_key")
        }

        if keys:
            index[namespace] = keys

    return index

# ============================================================
# WRAPPER DETECTION / UNWRAP  (BUG FIX: uses regex)
# ============================================================

def detect_and_unwrap_wrapper(code: str) -> Tuple[str, bool]:
    """
    Rimuove wrapper tipo:
      - function filter(...) { ... }
      - const filter = (...) => { ... }

    BUG FIX: uses regex ^function\s+filter\s*\( instead of the old
    heuristic '"filter" in stripped' which would incorrectly unwrap
    code like 'items.filter(x => x > 0)'.
    """
    if not code:
        return code, False

    stripped = code.strip()

    # Match function filter(...) or arrow: const filter = (...) =>
    is_function_filter = bool(re.match(r"^function\s+filter\s*\(", stripped))
    is_arrow_filter = bool(re.match(
        r"^(?:const|let|var)\s+filter\s*=\s*(?:\(.*?\)|[a-zA-Z_]\w*)\s*=>",
        stripped
    ))

    if (is_function_filter or is_arrow_filter) and "{" in stripped and "}" in stripped:
        first = stripped.find("{")
        last = stripped.rfind("}")
        if 0 <= first < last:
            return stripped[first + 1:last].strip(), True

    return code, False

# ============================================================
# MARKDOWN STRIP
# ============================================================

def strip_markdown(code: str) -> str:
    if not code:
        return code

    code = code.strip()

    if code.startswith("```"):
        code = re.sub(r"^```[a-zA-Z]*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)

    return code

def remove_comments(code: str) -> str:
    code = re.sub(r"//.*?$", "", code, flags=re.MULTILINE)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return code


def unwrap_filter_wrapper(code: str) -> str:
    stripped = code.lstrip()
    if not stripped.startswith("function"):
        return code
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return code
    return stripped[first + 1 : last].strip()


# ============================================================
# CLEAN FILTER CODE
# ============================================================

def clean_filter_code(code: str) -> str:
    if not code:
        return ""

    code = strip_markdown(code)
    code, _ = detect_and_unwrap_wrapper(code)
    return code.strip()


# ============================================================
# Entities (BUG FIX: SetterCall.method field added)
# ============================================================

@dataclass
class SetterCall:
    target: str
    field: str
    expr: Optional[Expr]
    line: Optional[int] = None
    method: Optional[str] = None   # BUG FIX: was set via monkey-patch before

@dataclass
class SkipCall:
    target: str
    reason: Optional[str] = None
    line: Optional[int] = None

# ============================================================
# HELPER
# ============================================================

def is_platform_field(field: str) -> bool:
    return (
        isinstance(field, str)
        and "." in field
        and not field.startswith("None")
        and "<" not in field
        and not field.endswith("toString")
    )


# ============================================================
# AST Parser
# ============================================================

class ASTParser:
    def __init__(self):
        self.platform_getter_index = build_platform_getter_index(TRIGGERS_PATH)
        self.getters: List[str] = []
        self.setters: List[SetterCall] = []
        self.skips: List[SkipCall] = []
        self.var_aliases: Dict[str, Expr] = {}
        self.wrapper_detected: bool = False
        self.unwrapped_code: str = ""

    def parse(self, code: str) -> Dict[str, Any]:
        code_unwrapped, wrapper_flag = detect_and_unwrap_wrapper(code)
        self.wrapper_detected = wrapper_flag
        self.unwrapped_code = code_unwrapped

        try:
            ast = esprima.parseScript(code_unwrapped, loc=True, tolerant=True)
        except Exception:
            return {
                "ast": None,
                "getters": [],
                "setters": [],
                "skips": [],
                "var_aliases": {},
                "parser": self,
                "wrapper_detected": wrapper_flag,
                "unwrapped_code": code_unwrapped,
                "fuzzy": True,
            }

        self._walk(ast)
        self._resolve_aliases_in_getters()
        self._resolve_aliases_in_setters()

        return {
            "ast": ast,
            "getters": list(set(self.getters)),
            "setters": self.setters,
            "skips": self.skips,
            "var_aliases": self.var_aliases,
            "parser": self,
            "wrapper_detected": wrapper_flag,
            "unwrapped_code": code_unwrapped,
            "fuzzy": False,
        }

    # -----------------------------
    def _walk(self, node):
        if not hasattr(node, "type"):
            return

        if node.type == "VariableDeclaration":
            self._handle_var_decl(node)

        if node.type == "CallExpression":
            self._handle_call(node)

        for _, v in vars(node).items():
            if isinstance(v, list):
                for el in v:
                    self._walk(el)
            elif hasattr(v, "type"):
                self._walk(v)

    # -----------------------------
    def _handle_var_decl(self, node):
        for d in node.declarations:
            if not hasattr(d, "id") or not hasattr(d, "init"):
                continue
            name = d.id.name
            init = d.init

            expr = None
            try:
                expr = self.build_expr(init)
            except Exception:
                expr = None

            if isinstance(expr, Field) and is_platform_field(expr.path):
                self.var_aliases[name] = expr
            else:
                self.var_aliases[name] = Field(name)

    # -----------------------------
    def _extract_path(self, node):
        if not hasattr(node, "type"):
            return None

        if node.type == "Identifier":
            return node.name

        if node.type == "MemberExpression":
            base = self._extract_path(node.object)
            if base is None:
                return None
            prop = node.property.name if hasattr(node.property, "name") else None
            return f"{base}.{prop}" if prop else base

        if node.type == "CallExpression":
            return self._extract_path(node.callee)

        return None

    # -----------------------------
    def _extract_namespace(self, path: str) -> str | None:
        parts = path.split(".")
        if len(parts) < 2:
            return None
        return ".".join(parts[:2])

    def _handle_call(self, node):
        path = self._extract_path(node.callee)
        if not path:
            return

        # SKIP()
        if path.endswith(".skip"):
            self.skips.append(
                SkipCall(path[:-5], None, getattr(node.loc.start, "line", None))
            )
            return

        # SETTER (es. X.Y.setFoo(value))
        if ".set" in path:
            parts = path.split(".")
            raw = parts[-1]
            if raw.startswith("set"):
                full_method = path
                arg = None
                if node.arguments:
                    try:
                        arg = self.build_expr(node.arguments[0])
                    except Exception:
                        arg = None

                self.setters.append(
                    SetterCall(
                        target=".".join(parts[:-1]),
                        field=raw[3:].lower(),
                        expr=arg,
                        line=getattr(node.loc.start, "line", None),
                        method=full_method,
                    )
                )
            return

        # GETTER NORMALIZZATO
        root = self._getter_root(path)
        last = path.split(".")[-1]

        ns = self._extract_namespace(path)

        # FUNZIONI GLOBALI / METODI NATIVI
        if last in self.NATIVE_METHODS or path in self.NATIVE_GLOBALS:
            return

    # -----------------------------

    NATIVE_GLOBALS = {"Number", "String", "Boolean", "parseInt", "parseFloat", "isNaN", "isFinite"}

    NATIVE_METHODS = {
        "trim", "toLowerCase", "toUpperCase", "toString",
        "slice", "substring", "substr",
        "includes", "startsWith", "endsWith",
        "repeat", "replace", "replaceAll", "split",
        "charAt", "charCodeAt",
        "toFixed", "toPrecision", "toExponential"
    }

    def _is_fake_getter(self, path: str) -> bool:
        if path in self.NATIVE_GLOBALS:
            return True

        parts = path.split(".")
        last = parts[-1]

        if last in self.NATIVE_METHODS:
            return True

        if len(parts) == 2 and parts[1] in self.NATIVE_METHODS:
            return True

        return False

    def _is_meta_currentusertime_root(self, parts):
        return len(parts) >= 2 and parts[0] == "Meta" and parts[1] == "currentUserTime"

    def _getter_root(self, path: str) -> str:
        parts = path.split(".")

        if self._is_meta_currentusertime_root(parts):
            return "Meta.currentUserTime"

        if len(parts) >= 3 and parts[0] == "DoNote":
            return ".".join(parts[:2])

        if len(parts) >= 2:
            return ".".join(parts[:2])

        return path

    def _collect_var_reads(self, expr, aliases):
        if isinstance(expr, Var):
            if expr.name not in self.NATIVE_GLOBALS:
                val = aliases.get(expr.name)
                if not isinstance(val, Const):
                    self.getters.append(expr.name)

        elif isinstance(expr, BinOp):
            self._collect_var_reads(expr.left, aliases)
            self._collect_var_reads(expr.right, aliases)

        elif isinstance(expr, UnOp):
            self._collect_var_reads(expr.expr, aliases)

        elif isinstance(expr, CallExpr):
            self._collect_var_reads(expr.func, aliases)
            for a in expr.args:
                self._collect_var_reads(a, aliases)

        elif isinstance(expr, NativeMethod):
            self._collect_var_reads(expr.obj, aliases)
            return

    def build_expr(self, node, aliases=None) -> Expr:
        if not hasattr(node, "type"):
            return Field("<unknown>")

        t = node.type

        # Literal
        if t == "Literal":
            return Const(node.value)

        # Identifier
        if t == "Identifier":
            if node.name in JS_GLOBAL_FUNCTIONS:
                return Field(node.name)
            if aliases and node.name in aliases:
                return aliases[node.name]
            if node.name in self.var_aliases:
                return self.var_aliases[node.name]
            return Var(node.name)

        # MemberExpression
        if t == "MemberExpression":
            prop = node.property.name if hasattr(node.property, "name") else None
            obj = self.build_expr(node.object, aliases)

            if prop in JS_NATIVE_METHODS:
                return NativeMethod(prop, obj)

            path = self._extract_path(node)
            if path:
                return Field(path)

            return CallExpr(Field(f"<mem:{prop}>"), [obj])

        # TemplateLiteral  -> Concat(quasis + expressions)
        if t == "TemplateLiteral":
            items = []
            for i, q in enumerate(node.quasis):
                txt = q.value.cooked if hasattr(q, "value") else ""
                if txt:
                    items.append(Const(txt))
                if i < len(node.expressions):
                    items.append(self.build_expr(node.expressions[i], aliases))
            return Concat(items)

        # Unary
        if t == "UnaryExpression":
            return UnOp(node.operator, self.build_expr(node.argument, aliases))

        # Binary / Logical
        if t in ("LogicalExpression", "BinaryExpression"):
            op = node.operator.replace("===", "==").replace("!==", "!=")
            return BinOp(
                op,
                self.build_expr(node.left, aliases),
                self.build_expr(node.right, aliases),
            )

        # CONDITIONAL (TERNARY)
        if t == "ConditionalExpression":
            test = self.build_expr(node.test, aliases)
            cons = self.build_expr(node.consequent, aliases)
            alt = self.build_expr(node.alternate, aliases)
            return TernaryExpr(test, cons, alt)

        # CallExpression
        if t == "CallExpression":
            callee = self.build_expr(node.callee, aliases)

            if isinstance(callee, NativeMethod):
                args = [self.build_expr(a, aliases) for a in node.arguments]
                return CallExpr(Field(callee.name), [callee.obj] + args)

            func = callee
            args = [self.build_expr(a, aliases) for a in node.arguments]
            return CallExpr(func, args)

        # ObjectExpression  {key: val, ...} → Const(dict) if all values resolve
        if t == "ObjectExpression":
            pairs = {}
            all_const = True
            for prop in node.properties:
                key = (
                    prop.key.name
                    if hasattr(prop.key, "name")
                    else str(getattr(prop.key, "value", "?"))
                )
                val_expr = self.build_expr(prop.value, aliases)
                if isinstance(val_expr, Const):
                    pairs[key] = val_expr.value
                else:
                    all_const = False
                    break
            if all_const:
                return Const(pairs)
            return Field("<unknown>")

        # ArrayExpression  [a, b, ...] → Const(list) if all elements resolve
        if t == "ArrayExpression":
            items = []
            all_const = True
            for elem in node.elements:
                val_expr = self.build_expr(elem, aliases)
                if isinstance(val_expr, Const):
                    items.append(val_expr.value)
                else:
                    all_const = False
                    break
            if all_const:
                return Const(items)
            return Field("<unknown>")

        return Field("<unknown>")

    # -----------------------------
    def _resolve_aliases_in_getters(self):
        resolved = []
        for g in self.getters:
            parts = g.split(".", 1)
            base = parts[0]
            if base in self.var_aliases and isinstance(self.var_aliases[base], Field):
                alias = self.var_aliases[base].path
                g = alias if len(parts) == 1 else f"{alias}.{parts[1]}"
            resolved.append(g)
        self.getters = list(set(resolved))

    def _resolve_aliases_in_setters(self):
        for s in self.setters:
            parts = s.target.split(".", 1)
            base = parts[0]
            if base in self.var_aliases and isinstance(self.var_aliases[base], Field):
                alias = self.var_aliases[base].path
                s.target = alias if len(parts) == 1 else f"{alias}.{parts[1]}"

# ============================================================
# SAFE PARSE
# ============================================================

def safe_parse_with_tail_drop(code: str, max_attempts: int = 6, clean: bool = True):
    original = code
    cleaned = clean_filter_code(code) if clean else code
    lines = cleaned.splitlines()

    for _ in range(max_attempts):
        parsed = ASTParser().parse("\n".join(lines))
        if parsed["ast"] is not None:
            return parsed, "\n".join(lines), None
        if len(lines) <= 1:
            break
        lines = lines[:-1]

    return None, original, "parse_error"
