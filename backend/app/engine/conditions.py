"""Edge conditions for conditional routing.

A DECLARATIVE, closed condition language — the same doctrine as the tool
parameter templates in handlers.py: a fixed vocabulary, no expressions, no
`eval`, nothing a workflow author can turn into code execution. A condition is
a small dict:

    {"field": "retrieved",              "op": "is_empty"}
    {"field": "citation_check.passed",  "op": "eq",       "value": false}
    {"field": "llm_output",             "op": "contains", "value": "escalate"}

Readable fields are exactly the EngineState keys, plus one level of dotted
access into the dict-valued ones. Nothing else is reachable, so a condition can
never read the database, the filesystem, or another run.

Evaluation NEVER raises. An unreadable field, a type mismatch, a malformed
condition — all evaluate to False, so the edge simply does not match and the
node's default edge takes over. Validation is where malformed conditions are
reported; runtime treats them as "no match" rather than failing a live run on a
routing technicality.
"""
from __future__ import annotations

from typing import Any

# Exactly the EngineState keys (handlers.EngineState). Kept explicit rather
# than derived so that adding state does not silently widen what a workflow
# author can branch on.
CONDITION_ROOTS = {
    "user_input", "prompt_parts", "retrieved", "context_block",
    "tool_results", "llm_output", "final_output", "citation_check",
    "hitl_decision",
}

# Roots that hold a dict, and so permit one level of `root.key` access.
DICT_ROOTS = {"citation_check", "hitl_decision"}

VALUE_OPS = {"eq", "ne", "contains", "not_contains", "gt", "gte", "lt", "lte"}
UNARY_OPS = {"is_empty", "is_not_empty"}
CONDITION_OPS = VALUE_OPS | UNARY_OPS

_MISSING = object()


def describe_ops() -> dict[str, list[str]]:
    """For the builder UI, so the palette cannot drift from the engine."""
    return {"value_ops": sorted(VALUE_OPS), "unary_ops": sorted(UNARY_OPS),
            "fields": sorted(CONDITION_ROOTS), "dict_fields": sorted(DICT_ROOTS)}


def condition_errors(condition: Any) -> list[str]:
    """Everything wrong with a condition, for validation. Empty list = valid."""
    errors: list[str] = []
    if not isinstance(condition, dict):
        return ["condition must be an object"]

    field = condition.get("field")
    if not isinstance(field, str) or not field:
        errors.append("condition.field is required")
    else:
        root, _, key = field.partition(".")
        if root not in CONDITION_ROOTS:
            errors.append(
                f"condition.field {field!r} is not readable — allowed fields: "
                f"{', '.join(sorted(CONDITION_ROOTS))}")
        elif key:
            if root not in DICT_ROOTS:
                errors.append(f"condition.field {field!r}: {root!r} is not an object, "
                              "so it has no sub-fields")
            elif "." in key:
                errors.append(f"condition.field {field!r}: only one level of nesting is readable")

    op = condition.get("op")
    if op not in CONDITION_OPS:
        errors.append(f"condition.op {op!r} is not one of: {', '.join(sorted(CONDITION_OPS))}")
    elif op in VALUE_OPS and "value" not in condition:
        errors.append(f"condition.op {op!r} requires a value")
    elif op in UNARY_OPS and "value" in condition:
        errors.append(f"condition.op {op!r} takes no value")

    if op in {"gt", "gte", "lt", "lte"} and isinstance(condition.get("value"), bool):
        # bool is an int in Python; comparing it numerically is never intended
        errors.append(f"condition.op {op!r} needs a number, not a boolean")

    return errors


def _resolve(field: str, state: dict) -> Any:
    root, _, key = field.partition(".")
    if root not in CONDITION_ROOTS:
        return _MISSING
    if root not in state:
        return _MISSING
    value = state.get(root)
    if not key:
        return value
    if not isinstance(value, dict) or key not in value:
        return _MISSING
    return value[key]


def _is_empty(value: Any) -> bool:
    if value is _MISSING or value is None:
        return True
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) == 0
    return False


def evaluate(condition: Any, state: dict) -> bool:
    """True iff the condition holds for this state. Never raises."""
    if not isinstance(condition, dict):
        return False
    field, op = condition.get("field"), condition.get("op")
    if not isinstance(field, str) or op not in CONDITION_OPS:
        return False

    actual = _resolve(field, state)

    if op == "is_empty":
        return _is_empty(actual)
    if op == "is_not_empty":
        return not _is_empty(actual)

    expected = condition.get("value")
    if actual is _MISSING:
        # An absent field matches nothing. Absent is absent — never coerced
        # into a passing comparison.
        return False

    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected

    if op in {"contains", "not_contains"}:
        if isinstance(actual, str) and isinstance(expected, str):
            # case-insensitive: these mostly match against model prose
            hit = expected.lower() in actual.lower()
        elif isinstance(actual, (list, tuple, set)):
            hit = expected in actual
        else:
            hit = False
        return hit if op == "contains" else not hit

    if op in {"gt", "gte", "lt", "lte"}:
        if isinstance(actual, bool) or isinstance(expected, bool):
            return False
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            return False
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        return actual <= expected

    return False


def summarize(condition: Any) -> str:
    """Human-readable form, for traces and validation messages."""
    if not isinstance(condition, dict):
        return "invalid condition"
    field, op = condition.get("field"), condition.get("op")
    if op in UNARY_OPS:
        return f"{field} {op}"
    return f"{field} {op} {condition.get('value')!r}"
