"""
src.code_parsing — re-export all public symbols for backward compatibility.
"""
# Expr DSL
from .expr import (
    Expr, Const, Field, Var, UnOp, BinOp, CallExpr, NativeMethod,
    TernaryExpr, Concat,
    TRUE, FALSE, And, Or, Not,
    JS_NATIVE_METHODS, JS_GLOBAL_FUNCTIONS,
    is_const_expr, eval_const_expr,
    simplify, simplify_fix, soft_normalize_numeric,
    eval_expr, substitute_aliases,
    _expr_to_str, extract_field_refs, explode_ternary,
)

# JS Validator
from .js_validator import (
    SetterCall, SkipCall, ASTParser,
    strip_markdown, detect_and_unwrap_wrapper, unwrap_filter_wrapper,
    remove_comments, clean_filter_code,
    safe_parse_with_tail_drop,
    build_platform_getter_index, is_platform_field,
    TRIGGERS_PATH,
)

# Path Analyzer
from .path_analyzer import (
    build_outcomes_from_ast,
    extract_used_filter_codes_semantic,
    extract_getters_from_outcomes,
    normalize_platform_getters,
    simplify_condition_logic,
    merge_equivalent_paths, merge_equivalent_paths_safe,
    normalize_paths, is_path_merge_safe, merge_group,
    differing_parts_only_use,
    MOMENT_METHODS,
)

# Catalog Validator
from .catalog_validator import (
    ValidationReport,
    load_catalog, get_allowed_api_surface, validate_against_catalog,
    build_display_labels,
)

# Feedback (L1 + L2 validation)
from .feedback import (
    L1Report, L2Report,
    run_l1_validation, run_l2_validation, validate_filter_code,
)

# Agent Support (diagnosis + suggestions + orchestrator)
from .agent_support import (
    AgentDiagnosis,
    suggest_api_fixes, build_diagnosis_prompt, run_agent_diagnosis,
    run_agent_followup, render_intent_diff_html,
    OrchestratorResult, run_orchestrator_turn, build_api_surface_text,
    ORCHESTRATOR_TOOLS,
)
