"""
Robust IFTTT Filter Code Parser (ESPrima-based) WITH:
 - soft cleaning
 - wrapper detection (function/arrow filter)
 - Expr AST (Const, Field, Var, UnOp, BinOp, CallExpr, NativeMethod)
 - per-path aliases (var -> Expr)
 - constant folding (Number(1) -> 1, 60*1 -> 60, 60 == 1 -> False, etc.)
 - folding dei principali metodi JS (String, Number, Array, globali)
 - extraction of getters, setter methods, skip()
 - outcomes: list of { condition: Expr, skip: bool, setters: [ {method, value} ] }
 - trivial path + impossible path removal
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import esprima
import math
import urllib.parse
from src.utils.study_utils import load_json_or_jsonl, TRIGGERS_PATH

logger = logging.getLogger(__name__)

# ============================================================
# NATIVE METHODS
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
# CONSTANT EXPRESSION EVALUATION (grezzo)
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
# WRAPPER + CLEANING
# ============================================================

def build_platform_getter_index(triggers_path) -> dict[str, set[str]]:
    triggers = load_json_or_jsonl(triggers_path)

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
# WRAPPER DETECTION / UNWRAP (ROBUST, LLM-SAFE)
# ============================================================

def detect_and_unwrap_wrapper(code: str) -> Tuple[str, bool]:
    """
    Rimuove wrapper tipo:
      - function filter(...) { ... }
      - const filter = (...) => { ... }

    Versione robusta:
      - tollera whitespace, newline, codice LLM sporco
      - NON usa regex fragili
    """
    if not code:
        return code, False

    stripped = code.strip()

    # euristica: se contiene "filter" e una coppia di {}
    if "filter" in stripped and "{" in stripped and "}" in stripped:
        first = stripped.find("{")
        last = stripped.rfind("}")
        if 0 <= first < last:
            return stripped[first + 1:last].strip(), True

    return code, False
# ============================================================
# MARKDOWN STRIP (NON DISTRUTTIVO)
# ============================================================

def strip_markdown(code: str) -> str:
    """
    Rimuove SOLO un wrapper markdown esterno ```...```
    NON tocca backtick interni o template literal JS.
    """
    if not code:
        return code

    code = code.strip()

    if code.startswith("```"):
        # rimuove ```lang\n
        code = re.sub(r"^```[a-zA-Z]*\n?", "", code)
        # rimuove \n```
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
# CLEAN FILTER CODE (MINIMAL, SAFE)
# ============================================================

def clean_filter_code(code: str) -> str:
    """
    Pre-processing MINIMO e sicuro:
      - rimuove wrapper markdown esterno
      - rimuove wrapper function/arrow filter
      - NON rimuove commenti (lo fa Esprima)
      - NON usa regex distruttive
    """
    if not code:
        return ""

    code = strip_markdown(code)
    code, _ = detect_and_unwrap_wrapper(code)
    return code.strip()


# ============================================================
# Entities
# ============================================================

@dataclass
class SetterCall:
    target: str
    field: str
    expr: Optional[Expr]
    line: Optional[int] = None

@dataclass
class SkipCall:
    target: str
    reason: Optional[str] = None
    line: Optional[int] = None

# ============================================================
# AST Parser
# ============================================================

def is_platform_field(field: str) -> bool:
    return (
        isinstance(field, str)
        and "." in field
        and not field.startswith("None")
        and "<" not in field
        and not field.endswith("toString")
    )


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

        # --------------------------------------------
        # SKIP()
        # --------------------------------------------
        if path.endswith(".skip"):
            self.skips.append(
                SkipCall(path[:-5], None, getattr(node.loc.start, "line", None))
            )
            return

        # --------------------------------------------
        # SETTER (es. X.Y.setFoo(value))
        # --------------------------------------------
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
                    )
                )
                self.setters[-1].method = full_method
            return

        # --------------------------------------------
        # GETTER NORMALIZZATO
        # --------------------------------------------
        root = self._getter_root(path)
        last = path.split(".")[-1]

        # CASO 1 — Platform APIs (validi sempre)
        ns = self._extract_namespace(path)

        # if ns and ns in self.platform_getter_index:
        #     # verifichiamo che il campo esista davvero
        #     if path in self.platform_getter_index[ns]:
        #         self.getters.append(ns)
        #         return

        # CASO 2 — FUNZIONI GLOBALI / METODI NATIVI
        if last in self.NATIVE_METHODS or path in self.NATIVE_GLOBALS:
            # NON aggiungere come getter
            return

        # # CASO 3 — variabile simbolica letta da code path
        # self.getters.append(root)

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
        """
        Ritorna True se path non deve essere considerato un getter.
        Casi da escludere:
          - global JS functions (Number, String, ...)
          - native string/number methods (toString, trim, format, etc.)
          - chiamate dirette a metodi nativi su variabili
        """
        # se è un nome semplice tipo "Number"
        if path in self.NATIVE_GLOBALS:
            return True

        parts = path.split(".")
        last = parts[-1]

        # metodo nativo → NON getter
        if last in self.NATIVE_METHODS:
            return True

        # se tipo myVar.toString → NO getter
        if len(parts) == 2 and parts[1] in self.NATIVE_METHODS:
            return True

        return False

    def _is_meta_currentusertime_root(self, parts):
        """Verifica se il path punta a Meta.currentUserTime."""
        return len(parts) >= 2 and parts[0] == "Meta" and parts[1] == "currentUserTime"

    def _getter_root(self, path: str) -> str:
        """
        Normalizza un getter complesso in una root semantica:
        - Meta.currentUserTime.* → Meta.currentUserTime
        - DoNote.doNoteNewCommandCommon.* → DoNote.doNoteNewCommandCommon
        - Generico: primi due segmenti
        """
        parts = path.split(".")

        # Caso moment: qualsiasi metodo sopra currentUserTime
        if self._is_meta_currentusertime_root(parts):
            return "Meta.currentUserTime"

        # Caso DoNote (es. DoNote.doNoteNewCommandCommon.NoteText.trim)
        if len(parts) >= 3 and parts[0] == "DoNote":
            return ".".join(parts[:2])

        # Fallback generico (es. Weather.currentTemperature)
        if len(parts) >= 2:
            return ".".join(parts[:2])

        return path

    def _collect_var_reads(self, expr, aliases):
        """
        Identifica variabili lette e NON costanti (post-alias & folding).
        Aggiunge il nome ai getter simbolici.
        """
        if isinstance(expr, Var):
            # non registriamo Number, String, ecc.
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
            self._collect_var_reads(expr.obj, aliases)  # ma analizziamo l’oggetto
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
            # quasis: pezzi di stringa
            for i, q in enumerate(node.quasis):
                txt = q.value.cooked if hasattr(q, "value") else ""
                if txt:
                    items.append(Const(txt))
                # expressions intercalate
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

        # 🔥 CONDITIONAL (TERNARY)
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

# ============================================================
# SIMPLIFY
# ============================================================

def simplify(e: Expr) -> Expr:
    # Costanti, variabili, campi → invariati
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

        # NOT di comparazioni → umanizzazione
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
            # False && X → False
            if isinstance(L, Const) and L.value is False:
                return Const(False)
            if isinstance(R, Const) and R.value is False:
                return Const(False)

            # True && X → X
            if isinstance(L, Const) and L.value is True:
                return simplify(R)
            if isinstance(R, Const) and R.value is True:
                return simplify(L)

            return BinOp("&&", L, R)

        # ---------- OR ----------
        if e.op == "||":
            # True || X → True
            if isinstance(L, Const) and L.value is True:
                return Const(True)
            if isinstance(R, Const) and R.value is True:
                return Const(True)

            # False || X → X
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

    # confrontiamo le stringhe perché Expr può essere strutturale
    while _expr_to_str(prev) != _expr_to_str(curr):
        prev = curr
        curr = simplify(curr)

    return curr

def soft_normalize_numeric(expr: Expr) -> Expr:
    """
    Applica equivalenze numeriche leggere:
      x > n   ≈ x >= n
      x < n   ≈ x <= n
    Senza toccare l'espressione di valore, solo la forma.
    """
    if isinstance(expr, BinOp):
        L = soft_normalize_numeric(expr.left)
        R = soft_normalize_numeric(expr.right)
        op = expr.op

        # soft equivalence
        if op == ">":
            op = ">="
        elif op == "<":
            op = "<="
        elif op == ">=":
            op = ">="
        elif op == "<=":
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
# EVAL EXPR — FOLDING NATIVE JS
# ============================================================

def eval_expr(e: Expr) -> Expr:
    # ---------------------------
    # BASE CASES
    # ---------------------------
    if isinstance(e, Const):
        return e
    if isinstance(e, Var):
        return e
    if isinstance(e, Field):
        return e

    # ---------------------------
    # UNARY
    # ---------------------------
    if isinstance(e, UnOp):
        inner = eval_expr(e.expr)
        if isinstance(inner, Const) and e.op == "!":
            return Const(not inner.value)
        return UnOp(e.op, inner)

    # ---------------------------
    # BINARY
    # ---------------------------
    if isinstance(e, BinOp):
        L = eval_expr(e.left)
        R = eval_expr(e.right)

        # se entrambi Const → prova a foldare
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

    # ---------------------------
    # CONCAT (flatten + merge costanti)
    # ---------------------------
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

    # ---------------------------
    # CALL EXPRESSION
    # ---------------------------
    if isinstance(e, CallExpr):
        fn = eval_expr(e.func)
        args = [eval_expr(a) for a in e.args]

        # se non è un Field → non possiamo riconoscere nativo
        if not isinstance(fn, Field):
            return CallExpr(fn, args)

        name = fn.path

        # ===============================
        # GLOBAL FUNCTIONS
        # ===============================

        # Number(x)
        if name == "Number" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                try:
                    return Const(float(x.value))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, args)

        # String(x)
        if name == "String" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                return Const(str(x.value))
            return CallExpr(fn, args)

        # Boolean(x)
        if name == "Boolean" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                return Const(bool(x.value))
            return CallExpr(fn, args)

        # parseInt(x, base?)
        if name == "parseInt" and len(args) >= 1:
            s = args[0]
            base = args[1] if len(args) > 1 else Const(10)
            if isinstance(s, Const) and isinstance(base, Const):
                try:
                    return Const(int(str(s.value), int(base.value)))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, args)

        # parseFloat(x)
        if name == "parseFloat" and len(args) == 1:
            s = args[0]
            if isinstance(s, Const):
                try:
                    return Const(float(str(s.value)))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, args)

        # isNaN(x)
        if name == "isNaN" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                try:
                    val = float(x.value)
                    return Const(math.isnan(val))
                except Exception:
                    return Const(True)
            return CallExpr(fn, args)

        # isFinite(x)
        if name == "isFinite" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                try:
                    val = float(x.value)
                    return Const(math.isfinite(val))
                except Exception:
                    return Const(False)
            return CallExpr(fn, args)

        # encode/decode URI
        if name == "encodeURI" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const) and isinstance(x.value, str):
                return Const(urllib.parse.quote(x.value, safe=":/?#[]@!$&'()*+,;="))
            return CallExpr(fn, args)

        if name == "encodeURIComponent" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const) and isinstance(x.value, str):
                return Const(urllib.parse.quote(x.value, safe=""))
            return CallExpr(fn, args)

        if name == "decodeURI" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const) and isinstance(x.value, str):
                try:
                    return Const(urllib.parse.unquote(x.value))
                except Exception:
                    return Const(x.value)
            return CallExpr(fn, args)

        if name == "decodeURIComponent" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const) and isinstance(x.value, str):
                try:
                    return Const(urllib.parse.unquote(x.value))
                except Exception:
                    return Const(x.value)
            return CallExpr(fn, args)

        # ===============================
        # STRING METHODS
        # ===============================

        if name == "trim" and len(args) == 1:
            s = args[0]
            if isinstance(s, Const) and isinstance(s.value, str):
                return Const(s.value.strip())
            return CallExpr(fn, args)

        if name == "toLowerCase" and len(args) == 1:
            s = args[0]
            if isinstance(s, Const) and isinstance(s.value, str):
                return Const(s.value.lower())
            return CallExpr(fn, args)

        if name == "toUpperCase" and len(args) == 1:
            s = args[0]
            if isinstance(s, Const) and isinstance(s.value, str):
                return Const(s.value.upper())
            return CallExpr(fn, args)

        if name == "toString" and len(args) == 1:
            x = args[0]
            if isinstance(x, Const):
                return Const(str(x.value))
            return CallExpr(fn, args)

        if name == "repeat" and len(args) == 2:
            s, n = args
            if isinstance(s, Const) and isinstance(n, Const):
                try:
                    return Const(s.value * int(n.value))
                except Exception:
                    return CallExpr(fn, args)
            return CallExpr(fn, args)

        if name == "slice" and len(args) in (2, 3):
            obj = args[0]
            if isinstance(obj, Const) and isinstance(obj.value, str):
                try:
                    start = int(args[1].value)
                    end = int(args[2].value) if len(args) == 3 else None
                    return Const(obj.value[start:end])
                except Exception:
                    return CallExpr(fn, args)
            return CallExpr(fn, args)

        if name == "substring" and len(args) >= 2:
            obj = args[0]
            if isinstance(obj, Const) and isinstance(obj.value, str):
                try:
                    start = int(args[1].value)
                    end = int(args[2].value) if len(args) >= 3 else None
                    return Const(obj.value[start:end])
                except Exception:
                    return CallExpr(fn, args)
            return CallExpr(fn, args)

        if name == "substr" and len(args) == 3:
            obj, start, lng = args
            if isinstance(obj, Const) and isinstance(obj.value, str):
                try:
                    s0 = int(start.value)
                    l = int(lng.value)
                    return Const(obj.value[s0 : s0 + l])
                except Exception:
                    return CallExpr(fn, args)
            return CallExpr(fn, args)

        if name == "includes" and len(args) == 2:
            obj, sub = args
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(sub, Const):
                return Const(sub.value in obj.value)
            return CallExpr(fn, args)

        if name == "startsWith" and len(args) == 2:
            obj, pref = args
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(pref, Const):
                return Const(obj.value.startswith(pref.value))
            return CallExpr(fn, args)

        if name == "endsWith" and len(args) == 2:
            obj, suf = args
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(suf, Const):
                return Const(obj.value.endswith(suf.value))
            return CallExpr(fn, args)

        if name == "replace" and len(args) == 3:
            obj, pattern, repl = args
            if isinstance(obj, Const) and isinstance(pattern, Const) and isinstance(repl, Const):
                if isinstance(obj.value, str):
                    try:
                        return Const(obj.value.replace(pattern.value, repl.value, 1))
                    except Exception:
                        pass
            return CallExpr(fn, args)

        if name == "replaceAll" and len(args) == 3:
            obj, pattern, repl = args
            if isinstance(obj, Const) and isinstance(pattern, Const) and isinstance(repl, Const):
                if isinstance(obj.value, str):
                    try:
                        return Const(obj.value.replace(pattern.value, repl.value))
                    except Exception:
                        pass
            return CallExpr(fn, args)

        if name == "split" and len(args) >= 2:
            obj, sep = args[0], args[1]
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(sep, Const):
                return Const(obj.value.split(sep.value))
            return CallExpr(fn, args)

        if name == "charAt" and len(args) == 2:
            obj, idx = args
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(idx, Const):
                try:
                    return Const(obj.value[int(idx.value)])
                except Exception:
                    return Const("")
            return CallExpr(fn, args)

        if name == "charCodeAt" and len(args) == 2:
            obj, idx = args
            if isinstance(obj, Const) and isinstance(obj.value, str) and isinstance(idx, Const):
                try:
                    ch = obj.value[int(idx.value)]
                    return Const(ord(ch))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, args)

        # ===============================
        # NUMBER METHODS
        # ===============================

        if name == "toFixed" and len(args) >= 1:
            obj = args[0]
            digits = args[1] if len(args) > 1 else Const(0)
            if isinstance(obj, Const) and isinstance(obj.value, (int, float)) and isinstance(digits, Const):
                try:
                    d = int(digits.value)
                    return Const(f"{obj.value:.{d}f}")
                except Exception:
                    return Const("NaN")
            return CallExpr(fn, args)

        if name == "toPrecision" and len(args) >= 1:
            obj = args[0]
            digits = args[1] if len(args) > 1 else Const(1)
            if isinstance(obj, Const) and isinstance(obj.value, (int, float)) and isinstance(digits, Const):
                try:
                    d = int(digits.value)
                    return Const(format(obj.value, f".{d}g"))
                except Exception:
                    return Const("NaN")
            return CallExpr(fn, args)

        if name == "toExponential" and len(args) >= 1:
            obj = args[0]
            digits = args[1] if len(args) > 1 else Const(0)
            if isinstance(obj, Const) and isinstance(obj.value, (int, float)) and isinstance(digits, Const):
                try:
                    d = int(digits.value)
                    return Const(f"{obj.value:.{d}e}")
                except Exception:
                    return Const("NaN")
            return CallExpr(fn, args)

        # ===============================
        # PATTERN COMPOSITI (lusso)
        # ===============================

        # Number(toFixed(...))
        if name == "Number" and len(args) == 1 and isinstance(args[0], CallExpr):
            inner = eval_expr(args[0])
            if isinstance(inner, Const):
                try:
                    return Const(float(inner.value))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, [inner])

        # isNaN(Number(...))
        if name == "isNaN" and len(args) == 1 and isinstance(args[0], CallExpr):
            num_expr = eval_expr(args[0])
            if isinstance(num_expr, Const):
                try:
                    val = float(num_expr.value)
                    return Const(math.isnan(val))
                except Exception:
                    return Const(True)
            return CallExpr(fn, [num_expr])

        # toString(Number(Const))
        if name == "toString" and len(args) == 1 and isinstance(args[0], CallExpr):
            inner = eval_expr(args[0])
            if isinstance(inner, Const):
                return Const(str(inner.value))
            return CallExpr(fn, [inner])

        # parseInt(String(Const))
        if name == "parseInt" and len(args) >= 1 and isinstance(args[0], CallExpr):
            inner = eval_expr(args[0])
            base = args[1] if len(args) > 1 else Const(10)
            if isinstance(inner, Const) and isinstance(base, Const):
                try:
                    return Const(int(str(inner.value), int(base.value)))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, [inner, base] if len(args) > 1 else [inner])

        # parseFloat(String(Const))
        if name == "parseFloat" and len(args) == 1 and isinstance(args[0], CallExpr):
            inner = eval_expr(args[0])
            if isinstance(inner, Const):
                try:
                    return Const(float(str(inner.value)))
                except Exception:
                    return Const(float("nan"))
            return CallExpr(fn, [inner])

        # ===============================
        # ARRAY METHODS
        # ===============================

        if name == "join" and len(args) == 2:
            arr, sep = args
            if isinstance(arr, Const) and isinstance(arr.value, list) and isinstance(sep, Const):
                try:
                    return Const(sep.value.join(str(x) for x in arr.value))
                except Exception:
                    pass
            return CallExpr(fn, args)

        if name == "indexOf" and len(args) == 2:
            arr, val = args
            if isinstance(arr, Const) and isinstance(arr.value, list) and isinstance(val, Const):
                try:
                    return Const(arr.value.index(val.value))
                except ValueError:
                    return Const(-1)
            return CallExpr(fn, args)

        if name == "lastIndexOf" and len(args) == 2:
            arr, val = args
            if isinstance(arr, Const) and isinstance(arr.value, list) and isinstance(val, Const):
                try:
                    idx = len(arr.value) - 1 - arr.value[::-1].index(val.value)
                    return Const(idx)
                except ValueError:
                    return Const(-1)
            return CallExpr(fn, args)

        if name == "slice" and len(args) in (2, 3):
            arr = args[0]
            if isinstance(arr, Const) and isinstance(arr.value, list):
                try:
                    start = int(args[1].value)
                    end = int(args[2].value) if len(args) == 3 else None
                    return Const(arr.value[start:end])
                except Exception:
                    pass
            return CallExpr(fn, args)

        # ===============================
        # OBJECT
        # ===============================

        if name == "hasOwnProperty" and len(args) == 2:
            obj, key = args
            if isinstance(obj, Const) and isinstance(obj.value, dict) and isinstance(key, Const):
                return Const(key.value in obj.value)
            return CallExpr(fn, args)

        # ---------------------------
        # DEFAULT: non foldabile
        # ---------------------------
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
        # nessuna AST valida → filtro sicuramente NON valido
        return []

    parser: ASTParser = parsed["parser"]
    outcomes: List[Dict[str, Any]] = []

    # Stato = (cond: Expr, setters: List[Dict], alive: bool, aliases: Dict[str, Expr])

    def walk_block(stmts, states):
        current = states
        for stmt in stmts:
            new_states = []
            for cond, setters, alive, aliases in current:
                if not alive:
                    new_states.append((cond, setters, False, aliases))
                else:
                    new_states.extend(walk_stmt(stmt, cond, setters, aliases))
            current = new_states
        return current

    def walk_stmt(node, cond: Expr, setters: List[Dict[str, Any]], aliases: Dict[str, Expr]):
        if not hasattr(node, "type"):
            return [(cond, setters, True, aliases)]

        t = node.type

        # -----------------------
        # VAR DECLARATION
        # -----------------------
        if t == "VariableDeclaration":
            out = []
            for decl in node.declarations:
                if hasattr(decl, "id") and hasattr(decl, "init"):
                    name = decl.id.name
                    value_expr = parser.build_expr(decl.init, aliases)

                    # 🔥 esplodi ternari nell'inizializzatore
                    parts = explode_ternary(value_expr)

                    for local_cond, local_val in parts:
                        nc = And(cond, local_cond)
                        val = substitute_aliases(local_val, aliases)
                        val = simplify_fix(val)
                        val = eval_expr(val)

                        new_alias = aliases.copy()
                        new_alias[name] = val

                        out.append((nc, setters, True, new_alias))

            return out or [(cond, setters, True, aliases)]

        # -----------------------
        # IF STATEMENT
        # -----------------------
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
                [(then_cond, list(setters), True, aliases)]
            )

            if alt:
                else_states = walk_block(
                    alt.body if alt.type == "BlockStatement" else [alt],
                    [(else_cond, list(setters), True, aliases)]
                )
            else:
                else_states = [(else_cond, list(setters), True, aliases)]

            return then_states + else_states

        # -----------------------
        # BLOCK
        # -----------------------
        if t == "BlockStatement":
            return walk_block(node.body, [(cond, setters, True, aliases)])

        # -----------------------
        # EXPRESSION STATEMENT
        # -----------------------

        if t == "ExpressionStatement":
            expr = node.expression

            # 🔥 TERNARIO COME STATEMENT
            if isinstance(expr, TernaryExpr):
                parts = explode_ternary(expr)
                out = []
                for local_cond, local_expr in parts:
                    nc = And(cond, local_cond)

                    fake = type("ES", (), {})()
                    fake.type = "ExpressionStatement"
                    fake.expression = local_expr

                    out.extend(walk_stmt(fake, nc, list(setters), aliases))
                return out

            # -----------------------
            # ASSIGNMENT
            # -----------------------
            if expr.type == "AssignmentExpression":
                if expr.left.type == "Identifier":
                    name = expr.left.name
                    value_expr = parser.build_expr(expr.right, aliases)

                    # 🔥 ternari nella right-value
                    parts = explode_ternary(value_expr)
                    out = []
                    for local_cond, local_val in parts:
                        nc = And(cond, local_cond)

                        val = substitute_aliases(local_val, aliases)
                        val = simplify_fix(val)
                        val = eval_expr(val)

                        new_alias = aliases.copy()
                        new_alias[name] = val

                        out.append((nc, setters, True, new_alias))

                    return out

            # -----------------------
            # CALL → SKIP / SETTER
            # -----------------------
            if expr.type == "CallExpression":
                path = parser._extract_path(expr.callee)


                # SKIP — registra anche il target
                if path and path.endswith(".skip"):
                    target = path[:-5]  # "Slack.postToChannel"

                    cond_res = substitute_aliases(cond, aliases)
                    cond_res = simplify_fix(cond_res)
                    cond_res = eval_expr(cond_res)

                    outcomes.append({
                        "condition": cond_res,
                        "skip": True,
                        "skip_targets": [target],  # NEW
                        "setters": [],
                    })

                    # ramo chiuso
                    return [(cond, setters, False, aliases)]

                # SETTER
                if path and ".set" in path:
                    raw = path.split(".")[-1]
                    if raw.startswith("set"):

                        # 🔥 SAFE: gestisci setter senza argomenti
                        if expr.arguments and len(expr.arguments) > 0:
                            value_expr = parser.build_expr(expr.arguments[0], aliases)
                        else:
                            value_expr = Const(None)  # <-- FIX decisivo

                        # 🔥 esplodi ternari
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
                            out.append((nc, new_setters, True, aliases))

                        return out

        # default: nessuna semantica
        return [(cond, setters, True, aliases)]

    # =========================================
    # Avvio sul body della AST
    # =========================================
    root = ast.body if hasattr(ast, "body") else []
    initial_states = [(TRUE(), [], True, {})]
    final_states = walk_block(root, initial_states)

    # =========================================
    # Costruzione outcomes non-skip (rami vivi)
    # =========================================
    for cond, setters, alive, aliases in final_states:
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

        outcomes.append({
            "condition": cond_res,
            "skip": False,
            "skip_targets": [],  # NEW
            "setters": setters_res,
        })

    # =========================================
    # Filtraggio path triviali / impossibili
    # =========================================
    def is_impossible(o: Dict[str, Any]) -> bool:
        # condizione costante False
        return isinstance(o["condition"], Const) and o["condition"].value is False

    def is_trivial(o: Dict[str, Any]) -> bool:
        # path che non fanno skip e non hanno setter → nessun effetto
        return (not o["skip"]) and (not o["setters"])

    filtered = [o for o in outcomes if not is_impossible(o) and not is_trivial(o)]

    # =========================================
    # Deduplicazione dei path
    # =========================================
    seen = set()
    unique_outcomes: List[Dict[str, Any]] = []

    for o in filtered:
        cond_str = _expr_to_str(o["condition"])
        skip_flag = o["skip"]
        setter_methods = tuple(sorted(s["method"] for s in o["setters"]))

        sig = (cond_str, skip_flag, setter_methods)
        if sig in seen:
            continue
        seen.add(sig)
        unique_outcomes.append(o)

    # Se non rimane nulla → filtro non IFTTT
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

# def extract_used_filter_codes(parsed: Dict[str, Any]):
#     keys = set(parsed.get("getters", []))
#     methods = set(f"{s.target}.{s.field}" for s in parsed.get("setters", []))
#     return keys, methods

def extract_used_filter_codes_semantic(parsed: Dict[str, Any]):
    """
    Estrae:
      - true_getters: getter realmente letti nel codice
      - used_namespaces: namespace validi per scenario/validazione
      - used_setters: setter effettivamente chiamati
      - outcomes: path semantici
    """

    outcomes = build_outcomes_from_ast(parsed)

    # Getter reali (usati nel codice)
    true_getters = sorted({
        g for g in extract_getters_from_outcomes(outcomes)
        if isinstance(g, str) and "." in g
    })

    # Namespace (per validazione scenario)
    used_namespaces = normalize_platform_getters(
        true_getters,
        parsed["parser"].platform_getter_index
    )

    # Setter realmente chiamati
    used_setters = sorted({
        s["method"]
        for o in outcomes
        for s in o.get("setters", [])
        if "method" in s
    })

    return true_getters, used_namespaces, used_setters, outcomes


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
    return str(e)


def is_path_merge_safe(p1, p2):
    """
    Determina se due path possono essere fusi senza perdita di semantica.
    Condizioni:
      1) skip flag uguale
      2) stessi setter (insieme dei metodi identico)
      3) differenze nelle condizioni riguardano SOLO variabili irrilevanti per i setter
    """
    # 1 — skip flag
    if p1["skip"] != p2["skip"]:
        return False

    # 2 — confrontiamo l'insieme dei setter (solo i metodi)
    set1 = {s["method"] for s in p1["setters"]}
    set2 = {s["method"] for s in p2["setters"]}

    if set1 != set2:
        return False

    # 3 — le variabili che influenzano i setter
    # (cioè quelle che compaiono nei valori dei setter)
    relevant_vars = set()
    for s in p1["setters"]:
        if s["value"] is not None:
            relevant_vars |= extract_field_refs(s["value"])

    # tutte le variabili coinvolte nei due path
    refs1 = extract_field_refs(p1["condition"])
    refs2 = extract_field_refs(p2["condition"])

    # differenze simmetriche
    diff = (refs1 - refs2) | (refs2 - refs1)

    # se non ci sono differenze → merge sicuro
    if not diff:
        return True

    # tutte le differenze devono essere su variabili IRRILEVANTI
    for d in diff:
        root = d.split(".")[0]  # esempio: "Cta" da "Cta.status"
        if d in relevant_vars or root in relevant_vars:
            return False

    return True

def merge_group(group):
    """
    Fonde un gruppo di path semanticamente compatibili (merge-safe).
    La condizione risultante è OR di tutte, poi semplificata.
    I setter sono presi dall’inizio (identici per definizione).
    """
    assert len(group) >= 1

    skip_flag = group[0]["skip"]
    setters = group[0]["setters"]

    # NEW — aggrega skip_targets in modo sicuro

    if skip_flag:
        skip_targets = sorted({
            t for p in group for t in p.get("skip_targets", [])
        })
    else:
        skip_targets = []

    # OR di tutte le condizioni
    merged_cond = group[0]["condition"]
    for p in group[1:]:
        merged_cond = BinOp("||", merged_cond, p["condition"])

    merged_cond = simplify_condition_logic(merged_cond)

    return {
        "condition": merged_cond,
        "skip": skip_flag,
        "skip_targets": skip_targets,  # FIX
        "setters": setters,
    }


def extract_field_refs(expr: Expr) -> set:
    """
    Estrae TUTTI i riferimenti a campi o variabili dentro un'espressione.
    Serve per capire quali parti della condizione influiscono sui path.
    """
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

def explode_ternary(expr: Expr):
    """
    Esplode ricorsivamente TernaryExpr in una lista di:
        (condizione_locale, expr_senza_ternari)
    condizione_locale = TRUE() se non ci sono ternari.
    """
    # Caso base: niente ternario
    if not isinstance(expr, TernaryExpr):
        return [(TRUE(), expr)]

    # Altrimenti: ternario → esplodi i due rami
    test   = expr.test
    cons   = expr.then_expr
    alt    = expr.else_expr

    cons_parts = explode_ternary(cons)
    alt_parts  = explode_ternary(alt)

    results = []

    # ramo THEN
    for ccond, cexpr in cons_parts:
        results.append((And(test, ccond), cexpr))

    # ramo ELSE
    for acond, aexpr in alt_parts:
        results.append((And(Not(test), acond), aexpr))

    return results


def differing_parts_only_use(c1: Expr, c2: Expr, irrelevant_vars: set) -> bool:
    """
    Verifica se TUTTE le differenze tra c1 e c2 riguardano SOLO variabili irrilevanti.
    Le variabili irrilevanti sono quelle che NON influenzano i setter.
    """
    # campi presenti in ciascuna condizione
    r1 = extract_field_refs(c1)
    r2 = extract_field_refs(c2)

    # differenza simmetrica: ciò che compare in uno ma non nell'altro
    diff = (r1 - r2) | (r2 - r1)

    if not diff:
        # nessuna differenza → condizioni equivalenti → merge sicuro
        return True

    # se TUTTE le differenze sono irrilevanti → merge sicuro
    for d in diff:
        # matching tra "Campo" e "Campo.sottocampo"
        root = d.split(".")[0]
        if d not in irrelevant_vars and root not in irrelevant_vars:
            return False

    return True


def simplify_condition_logic(expr: Expr) -> Expr:
    """
    LIVELLO 2 — Semplificazione logica:
    - AND/OR flatten
    - rimozione duplicati
    - eliminazione contraddizioni
    - ordinamento dei termini
    - doppia negazione
    - applica soft-normalizzazione numerica
    """
    expr = soft_normalize_numeric(expr)
    expr = simplify_fix(expr)

    # flatten children for AND/OR
    def flatten_AND(e):
        if isinstance(e, BinOp) and e.op == "&&":
            return flatten_AND(e.left) + flatten_AND(e.right)
        return [e]

    def flatten_OR(e):
        if isinstance(e, BinOp) and e.op == "||":
            return flatten_OR(e.left) + flatten_OR(e.right)
        return [e]

    def rebuild(op, items):
        if not items:
            return Const(True if op == "&&" else False)
        # remove duplicates
        uniq = []
        seen = set()
        for item in items:
            s = _expr_to_str(item)
            if s not in seen:
                uniq.append(item)
                seen.add(s)

        # detect A && !A
        if op == "&&":
            positives = { _expr_to_str(x) for x in uniq }
            for x in uniq:
                s = _expr_to_str(x)
                if s.startswith("(!"):
                    if s[2:-1] in positives:
                        return Const(False)

        # reorder for canonical form
        uniq.sort(key=_expr_to_str)

        # rebuild binary tree left-assoc
        acc = uniq[0]
        for x in uniq[1:]:
            acc = BinOp(op, acc, x)
        return acc

    if isinstance(expr, BinOp):
        if expr.op == "&&":
            return rebuild("&&", flatten_AND(expr))

        if expr.op == "||":
            return rebuild("||", flatten_OR(expr))

    return expr


def merge_equivalent_paths(outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge dei path non-skip che hanno:
    - stessi setter
    - condizioni che differiscono solo per la parte 'ramificata'
    producendo un unico macro-path per gruppo.
    """
    merged = {}

    for o in outcomes:
        skip = o["skip"]
        key_setters = tuple(sorted(s["method"] for s in o["setters"]))

        # normalizza la condizione
        cond_norm = simplify_condition_logic(o["condition"])

        if skip:
            # non facciamo merge aggressivo per skip
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
                        "skip_targets": list(p.get("skip_targets", [])),  # FIX
                        "setters": [],
                    })

        else:
            # merge all non-skip paths into ONE macro-path
            if len(cond_list) == 1:
                merged_cond = cond_list[0]
            else:
                # OR of all conditions
                acc = cond_list[0]
                for c in cond_list[1:]:
                    acc = BinOp("||", acc, c)
                    acc = simplify_condition_logic(acc)
                merged_cond = acc

            # build final
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

        # merge del gruppo
        merged.append(merge_group(group))

    return merged


def normalize_paths(outcomes: List[Dict[str, Any]]):
    cleaned = []

    for o in outcomes:
        cond = simplify_condition_logic(o["condition"])
        skip = o["skip"]

        # normalizza setter: rimuovi duplicati
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
            "skip_targets": list(o.get("skip_targets", [])),  # FIX HERE
            "setters": setters,
        })

    # merge path duplicati
    merged = []
    seen = set()

    for o in cleaned:
        sig = (
            _expr_to_str(o["condition"]),
            o["skip"],
            tuple(sorted(o.get("skip_targets", []))),  # FIX HERE
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
            # NON raccogliere la funzione se è globale JS
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

