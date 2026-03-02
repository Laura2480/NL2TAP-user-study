"""
parser.py — thin backward-compatibility wrapper.

All logic has been moved to:
  - expr.py            (Expr DSL)
  - js_validator.py    (cleaning, parsing, ASTParser)
  - path_analyzer.py   (conditional path analysis)
  - catalog_validator.py (catalog validation)

This file re-exports everything so that existing imports like
    from src.code_parsing.parser import safe_parse_with_tail_drop
continue to work.
"""
from .expr import *               # noqa: F401,F403
from .expr import _expr_to_str    # noqa: F401  — underscore, not in __all__
from .js_validator import *        # noqa: F401,F403
from .path_analyzer import *       # noqa: F401,F403
from .catalog_validator import *   # noqa: F401,F403
