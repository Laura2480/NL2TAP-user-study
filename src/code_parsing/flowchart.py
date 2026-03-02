"""
Flowchart renderer — custom HTML/CSS decision-flow from L1 outcomes.

Generates a self-contained HTML block (no external CDN) for
st.components.html(). Supports two display modes:
  - non_expert: human-readable names from IFTTT catalog
  - expert: code paths with namespace prefixes stripped
"""
import html as _html
import re
from typing import Any, Dict, List, Optional


# ============================================================
# I18N
# ============================================================

_KW = {
    "it": {
        "IF": "SE", "ALWAYS": "SEMPRE", "THEN": "ALLORA",
        "skip": "Salta", "AND": "E", "OR": "O",
        "decision_header": "Uno dei seguenti percorsi si attiva:",
        "path_label": "Percorso",
        "if_any": "SE (almeno una)",
        "guard_header": "Condizioni di blocco:",
        "default_header": "Configurazione azione:",
    },
    "en": {
        "IF": "IF", "ALWAYS": "ALWAYS", "THEN": "THEN",
        "skip": "Skip", "AND": "AND", "OR": "OR",
        "decision_header": "One of the following paths activates:",
        "path_label": "Path",
        "if_any": "IF (any of)",
        "guard_header": "Blocking conditions:",
        "default_header": "Action setup:",
    },
}

def _kw(lang: str, key: str) -> str:
    return _KW.get(lang, _KW["en"]).get(key, key)


# ============================================================
# SERVICE ICON HELPER
# ============================================================

def _ns_icon_html(ns_key: str, display_labels: Optional[dict], size: int = 18) -> str:
    """Return inline <img> for the namespace's service icon, or empty string."""
    if not display_labels:
        return ""
    icon_url = display_labels.get("namespace_icons", {}).get(ns_key, "")
    if not icon_url:
        return ""
    return (
        f'<img src="{_html.escape(icon_url)}" '
        f'style="height:{size}px;width:{size}px;vertical-align:middle;'
        f'margin-right:4px;filter:brightness(0)">'
    )


# ============================================================
# INGREDIENT STYLING — consistent colors for getter references
# ============================================================

_ING_COLORS = [
    '#1565c0',  # blue
    '#c62828',  # red
    '#2e7d32',  # green
    '#6a1b9a',  # purple
    '#e65100',  # orange
    '#00838f',  # teal
    '#4e342e',  # brown
    '#283593',  # indigo
]

def _ingredient_color(label: str) -> str:
    h = 0
    for c in label:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _ING_COLORS[h % len(_ING_COLORS)]

def _render_with_ingredients(text: str) -> str:
    """Convert text with \xab ingredient \xbb markers to HTML with styled spans."""
    parts = re.split(r'(\xab[^\xbb]+\xbb)', text)
    html_parts = []
    for part in parts:
        if part.startswith('\xab') and part.endswith('\xbb'):
            label = part[1:-1]
            color = _ingredient_color(label)
            html_parts.append(
                f'<span class="fc-ing" style="color:{color}">'
                f'{_html.escape(label)}</span>'
            )
        else:
            html_parts.append(_html.escape(part))
    return ''.join(html_parts)


# ============================================================
# JS UNWRAP / SEMANTIC PATTERNS (non-expert mode)
# ============================================================

# Captures an argument allowing 0-1 levels of paren nesting
_ARG = r'([^()]*(?:\([^()]*\))?[^()]*)'

# Transparent wrappers — unwrap to their argument
_UNWRAP_PATTERNS = [
    re.compile(r'\bNumber\('     + _ARG + r'\)'),
    re.compile(r'\bString\('     + _ARG + r'\)'),
    re.compile(r'\bBoolean\('    + _ARG + r'\)'),
    re.compile(r'\bparseFloat\(' + _ARG + r'\)'),
    re.compile(r'\bparseInt\('   + _ARG + r'(?:,[^)]*)?\)'),
    re.compile(r'\bMath\.floor\(' + _ARG + r'\)'),
    re.compile(r'\bMath\.round\(' + _ARG + r'\)'),
    re.compile(r'\bMath\.ceil\('  + _ARG + r'\)'),
    re.compile(r'\bMath\.abs\('   + _ARG + r'\)'),
    # JS string methods in function-call form (from Expr tree simplification)
    re.compile(r'\btoLowerCase\(' + _ARG + r'\)'),
    re.compile(r'\btoUpperCase\(' + _ARG + r'\)'),
    re.compile(r'\btrim\('        + _ARG + r'\)'),
    re.compile(r'\btoString\('    + _ARG + r'\)'),
]

# Semantic patterns — change meaning, must be applied with care
# !isNaN(x) → "x è valido"  (applied BEFORE generic ! → NOT)
_NEGATED_SEMANTIC = {
    "it": [(re.compile(r'!\s*isNaN\(' + _ARG + r'\)'), r'\1 è valido')],
    "en": [(re.compile(r'!\s*isNaN\(' + _ARG + r'\)'), r'\1 is valid')],
}
# isNaN(x) → "x non è valido"
_SEMANTIC_PATTERNS = {
    "it": [(re.compile(r'\bisNaN\(' + _ARG + r'\)'), r'\1 non è valido')],
    "en": [(re.compile(r'\bisNaN\(' + _ARG + r'\)'), r'\1 is not valid')],
}

# x.includes(y) → "x contiene y"  /  !x.includes(y) → "x non contiene y"
_INCLUDES_NEG = {
    "it": re.compile(r'!\s*(.+?)\.includes\(' + _ARG + r'\)'),
    "en": re.compile(r'!\s*(.+?)\.includes\(' + _ARG + r'\)'),
}
_INCLUDES_POS = {
    "it": re.compile(r'(.+?)\.includes\(' + _ARG + r'\)'),
    "en": re.compile(r'(.+?)\.includes\(' + _ARG + r'\)'),
}
_INCLUDES_REPL_NEG = {"it": r'\1 non contiene \2', "en": r'\1 does not contain \2'}
_INCLUDES_REPL_POS = {"it": r'\1 contiene \2', "en": r'\1 contains \2'}

# Function-call form: includes(x, y) — produced by Expr tree simplification
_INCLUDES_FN_NEG = {
    "it": re.compile(r'!\s*\bincludes\(([^,]+),\s*([^)]+)\)'),
    "en": re.compile(r'!\s*\bincludes\(([^,]+),\s*([^)]+)\)'),
}
_INCLUDES_FN_POS = {
    "it": re.compile(r'\bincludes\(([^,]+),\s*([^)]+)\)'),
    "en": re.compile(r'\bincludes\(([^,]+),\s*([^)]+)\)'),
}

# x.indexOf(y) === -1  → "x non contiene y"  (not found)
# x.indexOf(y) !== -1  → "x contiene y"      (found)
# Also handles < 0, >= 0, > -1 variants
_INDEXOF_PATTERNS = {
    "it": [
        # NOT FOUND: .indexOf(y) === -1  or  == -1  or  < 0
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*={2,3}\s*-1'), r'\1 non contiene \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*<\s*0'), r'\1 non contiene \2'),
        # FOUND: .indexOf(y) !== -1  or  != -1  or  >= 0  or  > -1
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*!={1,2}\s*-1'), r'\1 contiene \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*>=?\s*0'), r'\1 contiene \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*>\s*-1'), r'\1 contiene \2'),
    ],
    "en": [
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*={2,3}\s*-1'), r'\1 does not contain \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*<\s*0'), r'\1 does not contain \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*!={1,2}\s*-1'), r'\1 contains \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*>=?\s*0'), r'\1 contains \2'),
        (re.compile(r'(.+?)\.indexOf\(' + _ARG + r'\)\s*>\s*-1'), r'\1 contains \2'),
    ],
}

# Function-call form: indexOf(x, y) === -1 (from Expr simplification)
_INDEXOF_FN_PATTERNS = {
    "it": [
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*={2,3}\s*-1'), r'\1 non contiene \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*<\s*0'), r'\1 non contiene \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*!={1,2}\s*-1'), r'\1 contiene \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*>=?\s*0'), r'\1 contiene \2'),
    ],
    "en": [
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*={2,3}\s*-1'), r'\1 does not contain \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*<\s*0'), r'\1 does not contain \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*!={1,2}\s*-1'), r'\1 contains \2'),
        (re.compile(r'\bindexOf\(([^,]+),\s*([^)]+)\)\s*>=?\s*0'), r'\1 contains \2'),
    ],
}

# x.startsWith(y) → "x inizia con y" / "x starts with y"
# x.endsWith(y)   → "x finisce con y" / "x ends with y"
_STARTS_ENDS_PATTERNS = {
    "it": [
        # Negated forms first (before generic ! → NOT)
        (re.compile(r'!\s*(.+?)\.startsWith\(' + _ARG + r'\)'), r'\1 non inizia con \2'),
        (re.compile(r'!\s*(.+?)\.endsWith\(' + _ARG + r'\)'), r'\1 non finisce con \2'),
        # Positive forms
        (re.compile(r'(.+?)\.startsWith\(' + _ARG + r'\)'), r'\1 inizia con \2'),
        (re.compile(r'(.+?)\.endsWith\(' + _ARG + r'\)'), r'\1 finisce con \2'),
    ],
    "en": [
        (re.compile(r'!\s*(.+?)\.startsWith\(' + _ARG + r'\)'), r'\1 does not start with \2'),
        (re.compile(r'!\s*(.+?)\.endsWith\(' + _ARG + r'\)'), r'\1 does not end with \2'),
        (re.compile(r'(.+?)\.startsWith\(' + _ARG + r'\)'), r'\1 starts with \2'),
        (re.compile(r'(.+?)\.endsWith\(' + _ARG + r'\)'), r'\1 ends with \2'),
    ],
}

# .length === 0 → "è vuoto" / "is empty"
# .length > 0 / .length !== 0 → "non è vuoto" / "is not empty"
_LENGTH_PATTERNS = {
    "it": [
        (re.compile(r'(.+?)\.length\s*={2,3}\s*0'), r'\1 è vuoto'),
        (re.compile(r'(.+?)\.length\s*!={1,2}\s*0'), r'\1 non è vuoto'),
        (re.compile(r'(.+?)\.length\s*>\s*0'), r'\1 non è vuoto'),
        (re.compile(r'(.+?)\.length\s*<\s*1'), r'\1 è vuoto'),
    ],
    "en": [
        (re.compile(r'(.+?)\.length\s*={2,3}\s*0'), r'\1 is empty'),
        (re.compile(r'(.+?)\.length\s*!={1,2}\s*0'), r'\1 is not empty'),
        (re.compile(r'(.+?)\.length\s*>\s*0'), r'\1 is not empty'),
        (re.compile(r'(.+?)\.length\s*<\s*1'), r'\1 is empty'),
    ],
}

# Transparent JS string methods — strip from display (no semantic change)
_JS_STRIP_METHODS = re.compile(
    r'\.'
    r'(?:toLowerCase|toUpperCase|trim|trimStart|trimEnd'
    r'|toString|valueOf|normalize)'
    r'\(\)'
)


# ============================================================
# RANGE SIMPLIFICATION — remove redundant / impossible clauses
# ============================================================

# Match patterns like:  "Ora corrente" < 8  or  "Current Hour" ≥ 19
_RANGE_CMP = re.compile(
    r'("[^"]+?")\s*([<>≤≥=≠])\s*(\d+(?:\.\d+)?)'
)

def _simplify_range_conditions(text: str, lang: str) -> str:
    """Simplify AND-joined range conditions on the same variable.

    Detects patterns like:
      "Ora corrente" < 8 E "Ora corrente" ≥ 19  → impossible → "impossibile"
      "Ora corrente" ≥ 10 E "Ora corrente" < 17  → "Ora corrente" tra 10 e 17
      "Ora corrente" < 8 E "Ora corrente" < 17   → "Ora corrente" < 8  (redundant)
    """
    and_kw = _kw(lang, "AND")
    # Split on AND keyword (with surrounding spaces)
    parts = [p.strip() for p in text.split(f' {and_kw} ')]
    if len(parts) < 2:
        return text

    # Parse range constraints per variable
    constraints = {}  # var_name -> [(op, val, original_part_index)]
    for i, part in enumerate(parts):
        m = _RANGE_CMP.fullmatch(part.strip())
        if m:
            var, op, val = m.group(1), m.group(2), float(m.group(3))
            constraints.setdefault(var, []).append((op, val, i))

    new_parts = list(parts)
    remove_indices = set()

    for var, clist in constraints.items():
        if len(clist) < 2:
            continue

        # Extract lower and upper bounds
        lowers = [(op, val, idx) for op, val, idx in clist if op in ('≥', '>')]
        uppers = [(op, val, idx) for op, val, idx in clist if op in ('≤', '<')]

        if lowers and uppers:
            lo_op, lo_val, lo_idx = max(lowers, key=lambda x: x[1])
            up_op, up_val, up_idx = min(uppers, key=lambda x: x[1])

            # Check impossible: lower bound >= upper bound
            impossible = False
            if lo_op == '≥' and up_op == '<' and lo_val >= up_val:
                impossible = True
            elif lo_op == '≥' and up_op == '≤' and lo_val > up_val:
                impossible = True
            elif lo_op == '>' and up_op == '<' and lo_val >= up_val:
                impossible = True
            elif lo_op == '>' and up_op == '≤' and lo_val >= up_val:
                impossible = True

            if impossible:
                if lang == "it":
                    return "impossibile (condizione sempre falsa)"
                else:
                    return "impossible (always false)"

            # Valid range — simplify to "var tra X e Y"
            lo_int = int(lo_val) if lo_val == int(lo_val) else lo_val
            up_int = int(up_val) if up_val == int(up_val) else up_val
            if lang == "it":
                range_text = f'{var} tra {lo_int} e {up_int}'
            else:
                range_text = f'{var} between {lo_int} and {up_int}'
            # Replace the first constraint, remove the second
            new_parts[lo_idx] = range_text
            remove_indices.add(up_idx)

        elif len(lowers) >= 2:
            # Multiple lower bounds: keep only the strictest (highest)
            strictest = max(lowers, key=lambda x: x[1])
            for op, val, idx in lowers:
                if idx != strictest[2]:
                    remove_indices.add(idx)

        elif len(uppers) >= 2:
            # Multiple upper bounds: keep only the strictest (lowest)
            strictest = min(uppers, key=lambda x: x[1])
            for op, val, idx in uppers:
                if idx != strictest[2]:
                    remove_indices.add(idx)

    if not remove_indices:
        return text

    result = [p for i, p in enumerate(new_parts) if i not in remove_indices]
    return f' {and_kw} '.join(result)


# ============================================================
# UTILS
# ============================================================

def _strip_outer_parens(text: str) -> str:
    """Strip outer parens if they wrap the entire string."""
    while len(text) >= 2 and text[0] == "(" and text[-1] == ")":
        depth = 0
        ok = True
        for k, ch in enumerate(text):
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            if depth == 0 and k < len(text) - 1:
                ok = False
                break
        if ok:
            text = text[1:-1]
        else:
            break
    return text


# ============================================================
# GUARD MERGING — merge guards with same skip targets
# ============================================================

def _split_top_and(cond_str: str) -> List[str]:
    """Split condition string into top-level AND (&&) clauses."""
    cond_str = _strip_outer_parens(cond_str.strip())
    clauses: List[str] = []
    depth = 0
    current: List[str] = []
    i = 0
    while i < len(cond_str):
        ch = cond_str[i]
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif depth == 0 and cond_str[i:i+2] == '&&':
            clauses.append(''.join(current).strip())
            current = []
            i += 2
            continue
        else:
            current.append(ch)
        i += 1
    remaining = ''.join(current).strip()
    if remaining:
        clauses.append(remaining)
    return [_strip_outer_parens(c.strip()) for c in clauses if c.strip()]


def _is_negation(a: str, b: str) -> bool:
    """Check if a and b are boolean negations of each other."""
    a = _strip_outer_parens(a.strip())
    b = _strip_outer_parens(b.strip())
    if a.startswith('!'):
        if _strip_outer_parens(a[1:].strip()) == b:
            return True
    if b.startswith('!'):
        if _strip_outer_parens(b[1:].strip()) == a:
            return True
    return False


def _try_absorb_pair(cond_a: str, cond_b: str) -> Optional[str]:
    """Try to merge two AND-conditions via boolean absorption.

    Handles:
      (A && B) || (A && !B) = A             (complementary diff)
      (A) || (A && B)       = A             (subset absorption)
    Returns the simplified condition string, or None if no simplification.
    """
    clauses_a = set(_split_top_and(cond_a))
    clauses_b = set(_split_top_and(cond_b))

    common = clauses_a & clauses_b
    diff_a = clauses_a - common
    diff_b = clauses_b - common

    # Subset absorption: A || (A && B) = A
    if not diff_a and diff_b:
        return cond_a
    if not diff_b and diff_a:
        return cond_b

    # Complementary absorption: (A && B) || (A && !B) = A
    if common and len(diff_a) == 1 and len(diff_b) == 1:
        da = next(iter(diff_a))
        db = next(iter(diff_b))
        if _is_negation(da, db):
            if len(common) == 1:
                return next(iter(common))
            return ' && '.join(f'({c})' for c in common)

    return None


def _merge_guard_conditions(cond_strs: List[str]) -> str:
    """Merge multiple condition strings using iterative pairwise absorption.

    Repeatedly tries to absorb pairs until no more simplification is possible.
    Remaining un-merged conditions are joined with ||.
    """
    if len(cond_strs) <= 1:
        return cond_strs[0] if cond_strs else "True"

    conds = list(cond_strs)
    changed = True
    while changed:
        changed = False
        new_conds: List[str] = []
        used: set = set()
        for i in range(len(conds)):
            if i in used:
                continue
            merged = False
            for j in range(i + 1, len(conds)):
                if j in used:
                    continue
                result = _try_absorb_pair(conds[i], conds[j])
                if result is not None:
                    new_conds.append(result)
                    used.add(i)
                    used.add(j)
                    merged = True
                    changed = True
                    break
            if not merged:
                new_conds.append(conds[i])
        conds = new_conds

    if len(conds) == 1:
        return conds[0]
    return ' || '.join(f'({c})' for c in conds)


# ============================================================
# TEXT FORMATTING — condition / setter / skip
# ============================================================

def _split_top_level_or(text: str) -> List[str]:
    """Recursively split a condition on top-level ``||`` to flatten OR chains.

    Returns a list of leaf clauses. If the text contains no top-level ``||``,
    returns a single-element list with the (paren-stripped) text.
    """
    text = _strip_outer_parens(text.strip())
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif depth == 0 and text[i:i+2] == '||':
            parts.append(''.join(current).strip())
            current = []
            i += 2
            continue
        else:
            current.append(ch)
        i += 1
    remaining = ''.join(current).strip()
    if remaining:
        parts.append(remaining)

    if len(parts) <= 1:
        return [text]

    # Recursively split each part (handles left-associative nesting)
    result: List[str] = []
    for p in parts:
        result.extend(_split_top_level_or(p))
    return result


def _humanize_getter_refs(text: str, display_labels: Optional[dict]) -> str:
    """Replace getter paths (e.g. Feed.newFeedItem.EntryTitle) with human labels.

    Also strips transparent JS methods (.toLowerCase(), .trim(), etc.)
    and unwraps transparent wrapper functions (Number(), String(), etc.).
    """
    if not display_labels:
        return text
    # Strip transparent JS methods first so getter keys can match
    text = _JS_STRIP_METHODS.sub('', text)
    # Strip empty parens: e.g. Meta.currentUserTime.hour() → Meta.currentUserTime.hour
    text = re.sub(r'\(\)', '', text)
    # Unwrap transparent functions: Number(x) → x, parseInt(x) → x, etc.
    prev = None
    while prev != text:
        prev = text
        for pat in _UNWRAP_PATTERNS:
            text = pat.sub(r'\1', text)
    # Replace getter paths with human labels wrapped in markers (longest first)
    labels = display_labels.get("getter_labels", {})
    for key in sorted(labels, key=len, reverse=True):
        if key in text:
            text = text.replace(key, f'\xab{labels[key]}\xbb')
    return text


def _format_condition(
    condition_text: str,
    user_type: str,
    display_labels: Optional[dict],
    lang: str = "en",
    max_len: int = 120,
) -> str:
    """Format condition text based on user type."""
    text = _strip_outer_parens(condition_text)

    if display_labels is None:
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        return _html.escape(text)

    if user_type == "non_expert":
        # 0. Strip transparent JS string methods
        text = _JS_STRIP_METHODS.sub('', text)

        # 0b. Strip empty method-call parens so getter labels can match
        #    e.g. Meta.currentUserTime.hour() → Meta.currentUserTime.hour
        text = re.sub(r'\(\)', '', text)

        # 0c. Strip JS fallback idioms that are always-true/meaningless:
        #     x !== ''  /  x !== ""  (truthy guard, always true for real data)
        #     || ''     /  || ""     (default-value fallback)
        text = re.sub(r"""\s*&&\s*[\w.]+\s*!==?\s*(?:''|"")""", '', text)
        text = re.sub(r"""\s*\|\|\s*(?:''|"")""", '', text)
        # Standalone !== '' / !== "" at end of expression
        text = re.sub(r"""\s*!==?\s*(?:''|"")""", '', text)

        # 1. Replace getter paths with human names in «» markers (longest first)
        labels = display_labels.get("getter_labels", {})
        for key in sorted(labels, key=len, reverse=True):
            if key in text:
                text = text.replace(key, f'\xab{labels[key]}\xbb')

        # 2. Unwrap transparent JS functions (loop until convergence)
        prev = None
        while prev != text:
            prev = text
            for pat in _UNWRAP_PATTERNS:
                text = pat.sub(r'\1', text)

        # 3. !x.includes(y) → "x non contiene y" (BEFORE generic !)
        #    method-call form: x.includes(y)
        neg_pat = _INCLUDES_NEG.get(lang, _INCLUDES_NEG["en"])
        neg_repl = _INCLUDES_REPL_NEG.get(lang, _INCLUDES_REPL_NEG["en"])
        text = neg_pat.sub(neg_repl, text)

        # 3b. x.includes(y) → "x contiene y"
        pos_pat = _INCLUDES_POS.get(lang, _INCLUDES_POS["en"])
        pos_repl = _INCLUDES_REPL_POS.get(lang, _INCLUDES_REPL_POS["en"])
        text = pos_pat.sub(pos_repl, text)

        # 3c. function-call form: !includes(x, y) → "x non contiene y"
        fn_neg = _INCLUDES_FN_NEG.get(lang, _INCLUDES_FN_NEG["en"])
        text = fn_neg.sub(neg_repl, text)

        # 3d. function-call form: includes(x, y) → "x contiene y"
        fn_pos = _INCLUDES_FN_POS.get(lang, _INCLUDES_FN_POS["en"])
        text = fn_pos.sub(pos_repl, text)

        # 3e. indexOf(y) === -1 → "non contiene y" (BEFORE comparison humanization)
        for pat, repl in _INDEXOF_PATTERNS.get(lang, _INDEXOF_PATTERNS["en"]):
            text = pat.sub(repl, text)
        for pat, repl in _INDEXOF_FN_PATTERNS.get(lang, _INDEXOF_FN_PATTERNS["en"]):
            text = pat.sub(repl, text)

        # 3f. startsWith / endsWith (negated BEFORE generic ! → NOT)
        for pat, repl in _STARTS_ENDS_PATTERNS.get(lang, _STARTS_ENDS_PATTERNS["en"]):
            text = pat.sub(repl, text)

        # 3g. .length === 0 → "è vuoto" (BEFORE comparison humanization)
        for pat, repl in _LENGTH_PATTERNS.get(lang, _LENGTH_PATTERNS["en"]):
            text = pat.sub(repl, text)

        # 4. !isNaN → "è valido" (BEFORE generic ! → NOT)
        for pat, repl in _NEGATED_SEMANTIC.get(lang, _NEGATED_SEMANTIC["en"]):
            text = pat.sub(repl, text)

        # 4b. isNaN → "non è valido"
        for pat, repl in _SEMANTIC_PATTERNS.get(lang, _SEMANTIC_PATTERNS["en"]):
            text = pat.sub(repl, text)

        # 5. Humanize comparison operators
        text = text.replace("!==", " ≠ ")
        text = text.replace("!=",  " ≠ ")
        text = text.replace("===", " = ")
        text = text.replace("==",  " = ")
        text = text.replace(">=", " ≥ ")
        text = text.replace("<=", " ≤ ")

        # 6. Replace logical operators
        text = text.replace("&&", _kw(lang, "AND"))
        text = text.replace("||", _kw(lang, "OR"))
        text = text.replace("!", "NOT ")

        # 7. Clean up: strip redundant parens wrapping single tokens
        text = re.sub(r'\((\xab[^\xbb]*\xbb)\)', r'\1', text)  # («label»)
        text = re.sub(r'\(([^()]{1,60})\)', r'\1', text)      # (simple expr)
        text = _strip_outer_parens(text.strip())
        text = re.sub(r'  +', ' ', text)

        # 8. Simplify redundant/impossible range conditions
        text = _simplify_range_conditions(text, lang)

        # 9. Post-humanization cleanup: remove residual empty-string artifacts
        #    e.g. "E NOT ''" / "AND NOT ''" / "O ''" / "OR ''" / "≠ ''"
        #    ONLY match truly empty strings ('' or ""), never single quotes
        _and = _kw(lang, "AND")
        _or  = _kw(lang, "OR")
        text = re.sub(rf"""\s*{re.escape(_and)}\s*NOT\s*(?:''|"")""", '', text)
        text = re.sub(rf"""\s*{re.escape(_or)}\s*(?:''|"")""", '', text)
        text = re.sub(r"""\s*≠\s*(?:''|"")""", '', text)
        text = re.sub(r"""\s*NOT\s+(?:''|"")""", '', text)
        text = text.strip()

        # 10. Truthiness: NOT «variable» → «variable» è vuota / is empty
        if lang == "it":
            text = re.sub(r'NOT\s+\xab([^\xbb]+)\xbb', '«\\1» è vuota', text)
        else:
            text = re.sub(r'NOT\s+\xab([^\xbb]+)\xbb', '«\\1» is empty', text)

        # 11. Standalone bare "variable" → "variable" è presente / has a value
        #     Split by AND/OR, detect sub-clauses that are just a quoted string
        split_pat = rf'\s+({re.escape(_and)}|{re.escape(_or)})\s+'
        parts_split = re.split(split_pat, text)
        rebuilt = []
        for part in parts_split:
            stripped = part.strip()
            if stripped in (_and, _or):
                rebuilt.append(stripped)
            elif re.fullmatch(r'\xab[^\xbb]+\xbb', stripped):
                suffix = "è presente" if lang == "it" else "has a value"
                rebuilt.append(f'{stripped} {suffix}')
            else:
                rebuilt.append(part)
        text = ' '.join(rebuilt)

        # Truncation
        max_len = 140
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."

        # 12. Convert to HTML: AND → bullet list, OR → styled pill
        parts_split = re.split(split_pat, text)
        # Separate AND clauses from OR
        clauses = []
        for part in parts_split:
            stripped = part.strip()
            if stripped == _and:
                continue  # skip, we'll join with bullets
            elif stripped == _or:
                clauses.append(f' <span class="fc-or-kw">{_html.escape(_or)}</span> ')
            else:
                clauses.append(_render_with_ingredients(stripped))
        if len(clauses) > 1 and all(not c.startswith(' <span') for c in clauses):
            # Pure AND: render as numbered list, no indent
            items = ''.join(f'<li>{c}</li>' for c in clauses)
            return f'<ol class="fc-and-list">{items}</ol>'
        return ''.join(clauses)

    else:
        # Expert: strip trigger namespace prefix from getter paths
        for ns in display_labels.get("trigger_ns", set()):
            # Replace "Namespace.xxx" with ".xxx"
            if ns + "." in text:
                text = text.replace(ns + ".", ".")

    if len(text) > max_len:
        text = text[:max_len - 3] + "..."

    return _html.escape(text)


def _format_setter_field(
    setter: Dict[str, Any],
    display_labels: dict,
    lang: str = "en",
) -> str:
    """Format just the field assignment (no action name, no 'imposta' prefix)."""
    method = setter.get("method", "?")
    value = setter.get("value")

    label = display_labels.get("setter_labels", {}).get(method)
    if not label:
        label = method.split(".")[-1]
        label = re.sub(r'([a-z])([A-Z])', r'\1 \2', label)
        if label.startswith("set"):
            label = label[3:].strip()
        label = label.title() if label else method

    val_html = ""
    if value and value != "None":
        val = value.strip("'\"")
        val = _humanize_getter_refs(val, display_labels)
        # Simplify replace(expr, re.compile('...'), '...') → expr
        val = re.sub(r"replace\((.+?),\s*re\.compile\('[^']*'\),\s*'[^']*'\)", r'\1', val)
        val = _strip_outer_parens(val.strip())
        val = val.replace("\\n", " | ")
        if val.startswith("{") and val.endswith("}"):
            inner = val[1:-1].strip()
            inner = re.sub(r"'([^']+)':\s*'([^']*)'", r'\1: "\2"', inner)
            val_html = f'({_render_with_ingredients(inner)})'
        else:
            val_html = _render_with_ingredients(val)

    lbl_part = f'<u>{_html.escape(label)}</u>'
    if val_html:
        return f'{lbl_part} = {val_html}'
    return lbl_part


def _format_setter(
    setter: Dict[str, Any],
    user_type: str,
    display_labels: Optional[dict],
    lang: str = "en",
) -> str:
    """Format setter method + value for display."""
    method = setter.get("method", "?")
    value = setter.get("value")

    if display_labels is None:
        # Fallback: shorten to last 2 segments
        parts = method.split(".")
        short = ".".join(parts[-2:]) if len(parts) > 2 else method
        if value and value != "None":
            return _html.escape(f"{short}({value})")
        return _html.escape(short)

    # Resolve action name from namespace
    action_name = None
    ns_names = display_labels.get("namespace_names", {})
    for ns in display_labels.get("action_ns", set()):
        if method.startswith(ns + ".") or method == ns:
            action_name = ns_names.get(ns)
            break

    if user_type == "non_expert":
        label = display_labels.get("setter_labels", {}).get(method)
        if not label:
            # Try without last segment for derived setters
            label = method.split(".")[-1]
            # camelCase to words: setMessage -> Set Message
            label = re.sub(r'([a-z])([A-Z])', r'\1 \2', label)
            if label.startswith("set"):
                label = label[3:].strip()
            label = label.title() if label else method

        # Humanize value
        val_html = ""
        if value and value != "None":
            val = value.strip("'\"")
            val = _humanize_getter_refs(val, display_labels)
            # Simplify replace(expr, re.compile('...'), '...') → expr
            val = re.sub(r"replace\((.+?),\s*re\.compile\('[^']*'\),\s*'[^']*'\)", r'\1', val)
            val = _strip_outer_parens(val.strip())
            # Clean up \n for display
            val = val.replace("\\n", " | ")
            if val.startswith("{") and val.endswith("}"):
                inner = val[1:-1].strip()
                inner = re.sub(r"'([^']+)':\s*'([^']*)'", r'\1: "\2"', inner)
                val_html = f'({_render_with_ingredients(inner)})'
            else:
                val_html = _render_with_ingredients(val)

        # Build HTML with bold formatting
        act_part = f'<b>{_html.escape(action_name)}</b>' if action_name else ""
        lbl_part = f'<b>{_html.escape(label)}</b>'

        if lang == "it":
            if act_part and val_html:
                txt = f'{act_part}<br>imposta {lbl_part} = {val_html}'
            elif act_part:
                txt = f'{act_part}<br>imposta {lbl_part}'
            elif val_html:
                txt = f'imposta {lbl_part} = {val_html}'
            else:
                txt = lbl_part
        else:
            if act_part and val_html:
                txt = f'{act_part}<br>set {lbl_part} = {val_html}'
            elif act_part:
                txt = f'{act_part}<br>set {lbl_part}'
            elif val_html:
                txt = f'set {lbl_part} = {val_html}'
            else:
                txt = lbl_part

        return txt  # Already HTML-safe (parts escaped individually)
    else:
        # Expert: strip action namespace, add action name context
        short = method
        for ns in display_labels.get("action_ns", set()):
            if method.startswith(ns + "."):
                short = method[len(ns) + 1:]
                break
            elif method == ns:
                short = method.split(".")[-1]
                break

        if action_name:
            if lang == "it":
                prefix = f'[{action_name}] '
            else:
                prefix = f'[{action_name}] '
        else:
            prefix = ""

        if value and value != "None":
            return _html.escape(f"{prefix}{short}({value})")
        return _html.escape(f"{prefix}{short}")


def _format_skip(
    skip_targets: List[str],
    user_type: str,
    display_labels: Optional[dict],
    lang: str = "en",
) -> str:
    """Format skip targets for display (one per line if multiple)."""
    if not skip_targets:
        return _html.escape(_kw(lang, "skip"))

    skip_word = _kw(lang, "skip")

    if display_labels is None:
        if len(skip_targets) == 1:
            return _html.escape(f"{skip_word} {skip_targets[0]}")
        lines = [f"{skip_word} {t}" for t in skip_targets]
        return "<br>".join(_html.escape(l) for l in lines)

    if user_type == "non_expert":
        items_html = []
        for target in skip_targets:
            name = display_labels.get("skip_labels", {}).get(target)
            if not name:
                name = display_labels.get("namespace_names", {}).get(target, target)
            icon = _ns_icon_html(target, display_labels, size=16)
            items_html.append(f'<li>{icon}<b>{_html.escape(name)}</b></li>')
        # Header already says "SALTA" — numbered list of action names
        return f'<ol class="fc-and-list">{"".join(items_html)}</ol>'
    else:
        names = []
        for target in skip_targets:
            short = target
            for ns in display_labels.get("action_ns", set()):
                if target.startswith(ns):
                    short = target.split(".")[-1]
                    break
            names.append(short)
        if len(names) == 1:
            return _html.escape(f"skip {names[0]}")
        return "<br>".join(_html.escape(f"skip {n}") for n in names)


# ============================================================
# HTML/CSS TEMPLATE — self-contained, zero external deps
# ============================================================

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { margin: 0; background: transparent; }
.fc-container {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 4px 4px;
}
.fc-center { text-align: center; }
.fc-start {
  display: inline-block;
  background: linear-gradient(135deg, #e3f2fd, #bbdefb);
  border: 2px solid #42a5f5;
  color: #1565c0;
  font-weight: 700;
  padding: 10px 28px;
  border-radius: 24px;
  font-size: 14px;
  letter-spacing: 0.3px;
}
.fc-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 2px 0;
}
.fc-arrow-line { width: 2px; height: 18px; background: #bdbdbd; }
.fc-arrow-head {
  width: 0; height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 7px solid #bdbdbd;
}
.fc-path {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  width: fit-content;
  max-width: 100%;
}
.fc-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.fc-cond-label { color: #e65100; }
.fc-always-label { color: #1565c0; }
.fc-action-label { color: #2e7d32; }
.fc-skip-label { color: #c62828; }
.fc-condition {
  border-left: 4px solid #ff9800;
  background: #fffbf0;
  color: black;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.4;
  word-break: break-word;
  width: fit-content;
  max-width: 100%;
}
.fc-condition.always {
  border-left-color: #42a5f5;
  background: #f3f8ff;
}
.fc-condition.expert {
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
}
.fc-inner-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 6px 0;
}
.fc-inner-arrow-line { width: 2px; height: 12px; background: #e0e0e0; }
.fc-inner-arrow-head {
  width: 0; height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid #e0e0e0;
}
.fc-action {
  border-left: 4px solid #4caf50;
  background: #f1f8e9;
  color: black;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.4;
  word-break: break-word;
  width: fit-content;
  max-width: 100%;
}
.fc-action.expert {
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
}
.fc-skip {
  border-left: 4px solid #e53935;
  background: #fce4ec;
 color: black;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.4;
  word-break: break-word;
  width: fit-content;
  max-width: 100%;
}
.fc-l2-box {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}
.fc-l2-title { font-weight: 700; margin-bottom: 4px; }
.fc-l2-sug { margin-top: 8px; }
.fc-l2-sug ul { margin: 4px 0; padding-left: 20px; }
.fc-decision-group {
  border: 2px dashed #90a4ae;
  border-radius: 12px;
  padding: 10px 10px 8px;
  background: transparent;
}
.fc-decision-header {
  font-size: 12px; font-weight: 700; color: #546e7a;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 12px; text-align: center;
}
.fc-decision-group .fc-path { margin-bottom: 10px; position: relative; }
.fc-decision-group .fc-path:last-child { margin-bottom: 0; }
.fc-path-badge {
  position: absolute; top: -8px; left: 12px;
  background: #546e7a; color: #fff;
  font-size: 10px; font-weight: 700;
  width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.fc-ing {
  
  font-weight: 700;
}
.fc-and-list {
  list-style: decimal;
  margin: 2px 0 0 0;
  padding: 0 0 0 18px;
}
.fc-or-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fc-or-clause {
  flex: 1 1 180px;
  position: relative;
  font-size: 13px; line-height: 1.5;
  word-break: break-word;
  padding: 8px 10px 8px 30px;
  background: #fffbf0;
  color: black;
  border: 1px solid #ffe0b2;
  border-left: 3px solid #ff9800;
  border-radius: 6px;
}
.fc-or-badge {
  position: absolute; top: 6px; left: 7px;
  background: #e65100; color: #fff;
  font-size: 9px; font-weight: 700;
  width: 16px; height: 16px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.fc-and, .fc-or-kw {
  display: inline-block;
  background: #e3f2fd;
  color: #1565c0;
  font-weight: 700;
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
  margin: 1px 3px;
  vertical-align: middle;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.fc-or-kw {
  background: #fff3e0;
  color: #e65100;
}
.fc-guard-group {
  border: 2px dashed #e53935;
  border-radius: 12px;
  padding: 10px 10px 8px;
  background: transparent;
}
.fc-guard-header {
  font-size: 12px; font-weight: 700; color: #c62828;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 12px; text-align: center;
}
.fc-guard-group .fc-path { margin-bottom: 10px; position: relative; }
.fc-guard-group .fc-path:last-child { margin-bottom: 0; }
.fc-default-group {
  border: 2px solid #4caf50;
  border-radius: 12px;
  padding: 10px 10px 8px;
  background: transparent;
}
.fc-default-header {
  font-size: 12px; font-weight: 700; color: #2e7d32;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 12px; text-align: center;
}
.fc-default-group .fc-path { margin-bottom: 10px; position: relative; }
.fc-default-group .fc-path:last-child { margin-bottom: 0; }
.fc-split-row {
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: center;
}
.fc-split-row > .fc-guard-group { flex: 0 1 auto; }
.fc-split-row > .fc-default-group { flex: 0 1 auto; }
"""

_ARROW_HTML = """\
<div class="fc-arrow">
  <div class="fc-arrow-line"></div>
  <div class="fc-arrow-head"></div>
</div>"""

_INNER_ARROW_HTML = """\
<div class="fc-inner-arrow">
  <div class="fc-inner-arrow-line"></div>
  <div class="fc-inner-arrow-head"></div>
</div>"""


def _build_path_html(
    outcome: Dict[str, Any],
    user_type: str,
    display_labels: Optional[dict],
    lang: str,
    index: int = 0,
) -> str:
    """Build HTML for one outcome path card."""
    is_always = outcome.get("condition_is_always", False)
    is_skip = outcome.get("skip", False)
    cond_text = outcome.get("condition", "?")

    expert_cls = " expert" if user_type == "expert" else ""
    parts = []

    # Resolve trigger icon for condition labels
    trig_icon = ""
    if display_labels and user_type == "non_expert":
        for tns in display_labels.get("trigger_ns", set()):
            trig_icon = _ns_icon_html(tns, display_labels, size=16)
            if trig_icon:
                break

    # Condition block
    if is_always:
        parts.append(f'<div class="fc-label fc-always-label">{_kw(lang, "ALWAYS")}</div>')
        parts.append(f'<div class="fc-condition always{expert_cls}">{_kw(lang, "ALWAYS")}</div>')
    else:
        # Try splitting top-level OR clauses for readability
        clauses = _split_top_level_or(cond_text) if user_type == "non_expert" else []

        if len(clauses) > 1:
            # Multi-clause: horizontal flex grid with numbered badges
            parts.append(
                f'<div class="fc-label fc-cond-label">{_kw(lang, "if_any")}</div>'
            )
            parts.append('<div class="fc-or-container">')
            for ci, clause in enumerate(clauses, start=1):
                formatted = _format_condition(clause, user_type, display_labels, lang)
                parts.append(
                    f'<div class="fc-or-clause">'
                    f'<div class="fc-or-badge">{ci}</div>'
                    f'{trig_icon}{formatted}</div>'
                )
            parts.append('</div>')
        else:
            parts.append(f'<div class="fc-label fc-cond-label">{_kw(lang, "IF")}</div>')
            formatted = _format_condition(cond_text, user_type, display_labels, lang)
            parts.append(f'<div class="fc-condition{expert_cls}">{trig_icon}{formatted}</div>')

    parts.append(_INNER_ARROW_HTML)

    # Action block
    if is_skip:
        skip_text = _format_skip(
            outcome.get("skip_targets", []), user_type, display_labels, lang
        )
        parts.append(f'<div class="fc-label fc-skip-label">{_kw(lang, "skip").upper()}</div>')
        parts.append(f'<div class="fc-skip">{skip_text}</div>')
    else:
        setters = outcome.get("setters", [])
        if user_type == "non_expert" and display_labels and setters:
            # Group setters by action namespace for cleaner display
            from collections import OrderedDict
            groups: OrderedDict = OrderedDict()
            for s in setters:
                method = s.get("method", "")
                ns_key = None
                for ns in display_labels.get("action_ns", set()):
                    if method.startswith(ns + ".") or method == ns:
                        ns_key = ns
                        break
                ns_key = ns_key or method.rsplit(".", 1)[0]
                groups.setdefault(ns_key, []).append(s)

            # Single ALLORA label for all action groups
            action_label = _kw(lang, "THEN")
            parts.append(f'<div class="fc-label fc-action-label">{_html.escape(action_label)}</div>')

            first_group = True
            for ns_key, group_setters in groups.items():
                if not first_group:
                    parts.append(_INNER_ARROW_HTML)
                first_group = False

                # Action name + icon + "imposta" + numbered field list
                action_name = display_labels.get("namespace_names", {}).get(ns_key, ns_key)
                icon = _ns_icon_html(ns_key, display_labels)
                set_word = "imposta" if lang == "it" else "set"
                header = f'{icon}<b>{_html.escape(action_name)}</b><br>{set_word}'
                if len(group_setters) == 1:
                    field_text = _format_setter_field(group_setters[0], display_labels, lang)
                    block = f'{header} {field_text}'
                else:
                    items = ''.join(
                        f'<li>{_format_setter_field(s, display_labels, lang)}</li>'
                        for s in group_setters
                    )
                    block = f'{header}<ol class="fc-and-list">{items}</ol>'
                parts.append(f'<div class="fc-action">{block}</div>')
        else:
            # Expert or no labels: one block per setter
            for j, s in enumerate(setters):
                if j > 0:
                    parts.append(_INNER_ARROW_HTML)
                setter_text = _format_setter(s, user_type, display_labels, lang)
                action_label = _kw(lang, "THEN") if user_type == "non_expert" else "→"
                parts.append(f'<div class="fc-label fc-action-label">{_html.escape(action_label)}</div>')
                parts.append(f'<div class="fc-action{expert_cls}">{setter_text}</div>')

    badge = f'<div class="fc-path-badge">{index}</div>' if index > 0 else ''
    return f'<div class="fc-path">{badge}{"".join(parts)}</div>'


def _build_l2_box(l2_report, lang: str) -> str:
    """Build optional L2 explanation box."""
    if l2_report is None or getattr(l2_report, "error", None):
        return ""

    is_match = getattr(l2_report, "intent_match", False)
    if is_match:
        border = "#4caf50"
        bg = "#f1f8e9"
        title = "Il codice implementa correttamente l'intento" if lang == "it" else "Code correctly implements the intent"
    else:
        border = "#ff9800"
        bg = "#fffbf0"
        title = "Il codice potrebbe non corrispondere all'intento" if lang == "it" else "Code may not match the intent"

    explanation = _html.escape(getattr(l2_report, "explanation", ""))
    suggestions = getattr(l2_report, "suggestions", [])
    sug_html = ""
    if suggestions:
        items = "".join(f"<li>{_html.escape(s)}</li>" for s in suggestions)
        sug_title = "Suggerimenti:" if lang == "it" else "Suggestions:"
        sug_html = f'<div class="fc-l2-sug"><strong>{sug_title}</strong><ul>{items}</ul></div>'

    return (
        f'<div class="fc-l2-box" style="border-left:4px solid {border};background:{bg};">'
        f'<div class="fc-l2-title">{_html.escape(title)}</div>'
        f'<div>{explanation}</div>'
        f'{sug_html}'
        f'</div>'
    )


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def render_flowchart_html(
    outcomes_raw: List[Dict[str, Any]],
    l2_report=None,
    lang: str = "en",
    height: int = 0,
    user_type: str = "expert",
    display_labels: Optional[dict] = None,
) -> str:
    """
    Generate self-contained HTML flowchart for st.components.html().

    Args:
        outcomes_raw: L1Report.outcomes_raw
        l2_report: Optional L2Report
        lang: "it" or "en"
        height: if >0, set max-height with scroll
        user_type: "expert" or "non_expert"
        display_labels: from build_display_labels() — None = raw text fallback
    """
    if not outcomes_raw:
        return ""

    # Mixed paths contribute to BOTH sections:
    #   - skip part → guards (merged by skip targets)
    #   - setter part → defaults (merged by setter signature)
    from collections import OrderedDict

    # Collect all action namespaces (from setters + skip targets)
    all_action_ns = set()
    for o in outcomes_raw:
        for s in o.get("setters", []):
            ns = s.get("method", "").rsplit(".", 1)[0]
            if ns:
                all_action_ns.add(ns)
        for t in o.get("skip_targets", []):
            all_action_ns.add(t)

    raw_guards = []
    raw_defaults = []
    for o in outcomes_raw:
        has_skip = bool(o.get("skip_targets"))
        has_setters = bool(o.get("setters"))
        if has_skip:
            raw_guards.append({**o, "skip": True})
        # Exclude from defaults if skip covers ALL actions (setters are dead)
        skip_all = has_skip and set(o.get("skip_targets", [])) >= all_action_ns
        if not skip_all and (has_setters or not has_skip):
            raw_defaults.append(o)

    # --- Merge guards by skip targets with absorption ---
    skip_groups: OrderedDict = OrderedDict()
    for g in raw_guards:
        key = tuple(sorted(g.get("skip_targets", [])))
        skip_groups.setdefault(key, []).append(g)

    guards = []
    for skip_key, group in skip_groups.items():
        if len(group) == 1:
            guards.append(group[0])
        else:
            cond_strs = [g.get("condition", "True") for g in group]
            merged_cond = _merge_guard_conditions(cond_strs)
            guards.append({
                "condition": merged_cond,
                "condition_is_always": merged_cond in ("True", ""),
                "skip_targets": list(skip_key),
                "skip": True,
                "setters": [],
            })

    guards.sort(key=lambda g: len(g.get("skip_targets", [])), reverse=True)

    # --- Defaults: each path keeps its own condition (no absorption) ---
    defaults = []
    for d in raw_defaults:
        defaults.append({**d, "skip": False, "skip_targets": []})

    # Build flowchart body
    body_parts = []

    if guards and defaults:
        # Structural layout: action group first, then guard group below
        body_parts.append('<div class="fc-split-row">')

        body_parts.append('<div class="fc-default-group">')
        body_parts.append(
            f'<div class="fc-default-header">{_html.escape(_kw(lang, "default_header"))}</div>'
        )
        for i, outcome in enumerate(defaults, start=1):
            body_parts.append(
                _build_path_html(outcome, user_type, display_labels, lang, index=i)
            )
        body_parts.append('</div>')

        body_parts.append('<div class="fc-guard-group">')
        body_parts.append(
            f'<div class="fc-guard-header">{_html.escape(_kw(lang, "guard_header"))}</div>'
        )
        for i, outcome in enumerate(guards, start=1):
            body_parts.append(
                _build_path_html(outcome, user_type, display_labels, lang, index=i)
            )
        body_parts.append('</div>')

        body_parts.append('</div>')  # close fc-split-row

    elif guards:
        # Only guard (skip) paths — show as guard group
        body_parts.append(_ARROW_HTML)
        body_parts.append('<div class="fc-guard-group">')
        body_parts.append(
            f'<div class="fc-guard-header">{_html.escape(_kw(lang, "guard_header"))}</div>'
        )
        for i, outcome in enumerate(guards, start=1):
            body_parts.append(
                _build_path_html(outcome, user_type, display_labels, lang, index=i)
            )
        body_parts.append('</div>')

    elif defaults:
        # Only action paths — show as default group
        body_parts.append(_ARROW_HTML)
        body_parts.append('<div class="fc-default-group">')
        body_parts.append(
            f'<div class="fc-default-header">{_html.escape(_kw(lang, "default_header"))}</div>'
        )
        for i, outcome in enumerate(defaults, start=1):
            body_parts.append(
                _build_path_html(outcome, user_type, display_labels, lang, index=i)
            )
        body_parts.append('</div>')

    # L2 box
    l2_html = _build_l2_box(l2_report, lang)
    if l2_html:
        body_parts.append(l2_html)

    body = "\n".join(body_parts)

    # Assemble full HTML
    html_out = (
        f'<html><head><style>{_CSS}</style></head>'
        f'<body><div class="fc-container">{body}</div></body></html>'
    )

    return html_out


# ============================================================
# CODE FLOWCHART — Mermaid from JS AST
# ============================================================

def _html_to_plain(html_text: str) -> str:
    """Strip HTML tags and «» ingredient markers → plain text for Mermaid."""
    t = re.sub(r'<br\s*/?>', ' \u2014 ', html_text)
    t = re.sub(r'</li>\s*<li>', ' \u2014 ', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('\xab', '').replace('\xbb', '')
    t = _html.unescape(t)
    t = re.sub(r'\s*\u2014\s*\u2014\s*', ' \u2014 ', t)
    return t.strip(' \u2014')


def _mermaid_safe(text: str, max_len: int = 80) -> str:
    """Sanitize text for Mermaid node labels (inside double quotes)."""
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    text = text.replace('"', "'")
    text = text.replace('{', '(')
    text = text.replace('}', ')')
    # Fullwidth hash to avoid Mermaid entity syntax (#NN;)
    text = text.replace('#', '\uff03')
    return text


def render_code_flowchart_html(
    js_code: str,
    lang: str = "en",
    user_type: str = "expert",
    display_labels: Optional[dict] = None,
    invalid_setters: Optional[set] = None,
) -> tuple:
    """Render a classic Mermaid flowchart from JS code AST.

    Parses the JS code with esprima and generates a top-down flowchart
    showing the actual if/else control flow with colored nodes:
      - orange diamonds for conditions
      - green rectangles for setter/action calls
      - dark-red rectangles (thick border) for invalid setter calls
      - red parallelograms for skip() calls
      - blue stadium shapes for start/end

    When display_labels is provided, node text is translated to
    human-readable form (same as the semantic blocks).

    Returns (html_str, estimated_height) for st.components.html().
    """
    import esprima

    code = js_code.strip()
    if not code:
        return ("", 0)

    try:
        ast = esprima.parseScript(code, tolerant=True, range=True)
    except Exception:
        return ("", 0)

    body = list(ast.body)
    if (len(body) == 1
            and body[0].type == "FunctionDeclaration"
            and getattr(body[0].id, 'name', '') == "filter"):
        body = list(body[0].body.body)

    if not body:
        return ("", 0)

    # --- graph state ---
    _cnt = [0]
    mmd = ["flowchart TD"]
    edge_list = []       # (from_id, to_id)
    node_type = {}       # nid -> "cond"|"action"|"skip"|"terminal"

    def _nid():
        _cnt[0] += 1
        return f"N{_cnt[0]}"

    def _src(node):
        if hasattr(node, 'range') and node.range:
            return code[node.range[0]:node.range[1]]
        return "..."

    def _diamond(text):
        n = _nid()
        mmd.append(f'    {n}{{"{_mermaid_safe(text, 60)}"}}')
        node_type[n] = "cond"
        return n

    def _rect(text):
        n = _nid()
        mmd.append(f'    {n}["{_mermaid_safe(text, 80)}"]')
        node_type[n] = "action"
        return n

    def _skip_node(text):
        n = _nid()
        label = f"SKIP: {text}"
        mmd.append(f'    {n}[/"{_mermaid_safe(label, 70)}"/]')
        node_type[n] = "skip"
        return n

    def _invalid_node(text):
        n = _nid()
        mmd.append(f'    {n}["{_mermaid_safe(text, 80)}"]')
        node_type[n] = "invalid"
        return n

    def _stadium(text):
        n = _nid()
        mmd.append(f'    {n}(["{_mermaid_safe(text, 40)}"])')
        node_type[n] = "terminal"
        return n

    def _edge(f, t, label=None):
        if label:
            mmd.append(f'    {f} -->|"{label}"| {t}')
        else:
            mmd.append(f'    {f} --> {t}')
        edge_list.append((f, t))

    def _is_skip(expr):
        if not expr or expr.type != "CallExpression":
            return False
        c = expr.callee
        return (c.type == "MemberExpression"
                and hasattr(c.property, 'name')
                and c.property.name == "skip")

    def _walk(stmts, entries):
        """Walk AST statements.

        entries = [(node_id, edge_label|None), ...]
        Returns [(exit_node_id, edge_label|None), ...]
        """
        current = list(entries)

        for stmt in stmts:
            if stmt.type == "IfStatement":
                raw_cond = _src(stmt.test)
                if display_labels:
                    cond_txt = _html_to_plain(
                        _format_condition(raw_cond, user_type, display_labels, lang)
                    )
                else:
                    cond_txt = raw_cond
                cond = _diamond(cond_txt)
                for eid, lbl in current:
                    _edge(eid, cond, lbl)

                yes = "Si" if lang == "it" else "Yes"
                no = "No"

                # True branch
                cons = stmt.consequent
                if cons.type == "BlockStatement":
                    t_exits = _walk(list(cons.body), [(cond, yes)])
                else:
                    t_exits = _walk([cons], [(cond, yes)])

                # False branch
                alt = stmt.alternate
                if alt:
                    if alt.type == "BlockStatement":
                        f_exits = _walk(list(alt.body), [(cond, no)])
                    else:
                        f_exits = _walk([alt], [(cond, no)])
                else:
                    f_exits = [(cond, no)]

                current = t_exits + f_exits

            elif stmt.type == "ExpressionStatement":
                expr = stmt.expression
                if _is_skip(expr):
                    if display_labels:
                        targets = []
                        if (expr.callee.type == "MemberExpression"
                                and expr.callee.object):
                            targets = [_src(expr.callee.object)]
                        txt = _html_to_plain(
                            _format_skip(targets, user_type, display_labels, lang)
                        )
                    else:
                        if (expr.callee.type == "MemberExpression"
                                and expr.callee.object):
                            txt = _src(expr.callee.object) + ".skip()"
                        else:
                            txt = "skip()"
                    n = _skip_node(txt)
                else:
                    is_invalid = False
                    if (expr.type == "CallExpression"
                            and hasattr(expr, 'callee')
                            and expr.callee.type == "MemberExpression"):
                        method = _src(expr.callee)
                        value = _src(expr.arguments[0]) if expr.arguments else None
                        # Check if this setter is in the invalid set
                        if invalid_setters and method in invalid_setters:
                            is_invalid = True
                        if display_labels:
                            setter_dict = {"method": method, "value": value}
                            txt = _html_to_plain(
                                _format_setter(setter_dict, user_type, display_labels, lang)
                            )
                        else:
                            txt = _src(expr).rstrip(';').strip()
                    else:
                        txt = _src(expr).rstrip(';').strip()
                    n = _invalid_node(txt) if is_invalid else _rect(txt)
                for eid, lbl in current:
                    _edge(eid, n, lbl)
                current = [(n, None)]

            elif stmt.type == "VariableDeclaration":
                txt = _src(stmt).rstrip(';').strip()
                n = _rect(txt)
                for eid, lbl in current:
                    _edge(eid, n, lbl)
                current = [(n, None)]

            elif stmt.type in ("EmptyStatement",):
                continue

            else:
                # Fallback: show as generic action
                txt = _src(stmt).rstrip(';').strip()
                if txt:
                    n = _rect(txt)
                    for eid, lbl in current:
                        _edge(eid, n, lbl)
                    current = [(n, None)]

        return current

    # --- Build graph ---
    start = _stadium("Filter Code")
    exits = _walk(body, [(start, None)])

    end = _stadium("End")
    for eid, lbl in exits:
        _edge(eid, end, lbl)

    # --- Node styles ---
    for n, t in node_type.items():
        if t == "cond":
            mmd.append(f"    style {n} fill:#fff3e0,stroke:#ff9800,color:#e65100")
        elif t == "action":
            mmd.append(f"    style {n} fill:#e8f5e9,stroke:#4caf50,color:#2e7d32")
        elif t == "invalid":
            mmd.append(f"    style {n} fill:#ffcdd2,stroke:#b71c1c,color:#b71c1c,stroke-width:3px,stroke-dasharray:5 3")
        elif t == "skip":
            mmd.append(f"    style {n} fill:#ffebee,stroke:#e53935,color:#c62828")
        elif t == "terminal":
            mmd.append(f"    style {n} fill:#e3f2fd,stroke:#42a5f5,color:#1565c0")

    # --- Edge styles (colored by target node type) ---
    for i, (f, t) in enumerate(edge_list):
        tt = node_type.get(t, "")
        if tt == "skip":
            mmd.append(f"    linkStyle {i} stroke:#e53935,stroke-width:2px")
        elif tt == "invalid":
            mmd.append(f"    linkStyle {i} stroke:#b71c1c,stroke-width:2px")
        elif tt == "action":
            mmd.append(f"    linkStyle {i} stroke:#4caf50,stroke-width:2px")
        else:
            mmd.append(f"    linkStyle {i} stroke:#607d8b,stroke-width:1.5px")

    mermaid_src = "\n".join(mmd)

    # --- Estimate height from graph depth (longest path) ---
    from collections import deque
    adj = {}
    for f_node, t_node in edge_list:
        adj.setdefault(f_node, []).append(t_node)
    depth = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in adj.get(node, []):
            new_d = depth[node] + 1
            if nxt not in depth or new_d > depth[nxt]:
                depth[nxt] = new_d
                queue.append(nxt)
    max_depth = max(depth.values()) if depth else 1
    estimated_height = max(300, max_depth * 105 + 80)

    html = (
        '<html><head>'
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>'
        '<style>'
        'body{margin:0;padding:8px;background:transparent;}'
        '.mermaid{text-align:center;}'
        '</style>'
        '</head><body>'
        f'<div class="mermaid">\n{mermaid_src}\n</div>'
        '<script>'
        'mermaid.initialize({startOnLoad:false,theme:"base",securityLevel:"loose"});'
        'mermaid.run({querySelector:".mermaid"}).then(function(){'
        '  var svg=document.querySelector(".mermaid svg");'
        '  if(!svg)return;'
        '  var h=Math.ceil(svg.getBoundingClientRect().height)+20;'
        '  document.body.style.height=h+"px";'
        '  try{'
        '    var fr=window.frameElement;'
        '    if(fr){'
        '      fr.style.height=h+"px";'
        '      var p=fr.parentElement;'
        '      if(p)p.style.height=h+"px";'
        '    }'
        '  }catch(e){}'
        '});'
        '</script>'
        '</body></html>'
    )
    return (html, estimated_height)
