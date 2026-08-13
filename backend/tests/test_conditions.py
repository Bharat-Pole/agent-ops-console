"""The edge-condition language.

Closed vocabulary, no expressions, and — the property that matters most at
runtime — evaluation never raises. A malformed condition is caught at
validation time; if one somehow reaches a live run it must degrade to "no
match" and let the default edge take over, never take the run down.
"""
from __future__ import annotations

import pytest

from app.engine import conditions
from app.engine.conditions import condition_errors, evaluate, summarize


# ---- validation --------------------------------------------------------------

def test_a_well_formed_condition_has_no_errors():
    assert condition_errors({"field": "llm_output", "op": "contains", "value": "x"}) == []


def test_unknown_fields_are_refused_with_the_allowed_list():
    errors = condition_errors({"field": "os.environ", "op": "eq", "value": "x"})
    assert errors and "not readable" in errors[0]
    assert "llm_output" in errors[0], "the message should say what IS allowed"


def test_unknown_operators_are_refused():
    errors = condition_errors({"field": "llm_output", "op": "regex", "value": ".*"})
    assert any("not one of" in e for e in errors)


def test_value_operators_require_a_value():
    assert any("requires a value" in e for e in condition_errors(
        {"field": "llm_output", "op": "eq"}))


def test_unary_operators_reject_a_value():
    assert any("takes no value" in e for e in condition_errors(
        {"field": "retrieved", "op": "is_empty", "value": True}))


def test_numeric_operators_reject_booleans():
    assert any("not a boolean" in e for e in condition_errors(
        {"field": "llm_output", "op": "gt", "value": True}))


def test_nesting_is_limited_to_one_level():
    assert any("one level" in e for e in condition_errors(
        {"field": "hitl_decision.a.b", "op": "eq", "value": 1}))


def test_sub_fields_are_refused_on_non_object_roots():
    assert any("no sub-fields" in e for e in condition_errors(
        {"field": "llm_output.length", "op": "eq", "value": 1}))


def test_dotted_access_is_allowed_on_object_roots():
    assert condition_errors({"field": "hitl_decision.approved", "op": "eq", "value": True}) == []


@pytest.mark.parametrize("bad", [None, "llm_output", 42, [], {"op": "eq", "value": 1}])
def test_malformed_conditions_are_reported_not_crashed(bad):
    assert condition_errors(bad), f"{bad!r} should produce at least one error"


# ---- evaluation --------------------------------------------------------------

def test_equality_and_inequality():
    state = {"llm_output": "escalate"}
    assert evaluate({"field": "llm_output", "op": "eq", "value": "escalate"}, state)
    assert not evaluate({"field": "llm_output", "op": "ne", "value": "escalate"}, state)


def test_contains_is_case_insensitive_for_prose():
    state = {"llm_output": "I recommend we ESCALATE this"}
    assert evaluate({"field": "llm_output", "op": "contains", "value": "escalate"}, state)
    assert not evaluate({"field": "llm_output", "op": "not_contains", "value": "escalate"}, state)


def test_contains_on_a_list_is_membership():
    state = {"prompt_parts": ["a", "b"]}
    assert evaluate({"field": "prompt_parts", "op": "contains", "value": "a"}, state)
    assert not evaluate({"field": "prompt_parts", "op": "contains", "value": "z"}, state)


def test_is_empty_covers_the_no_context_case():
    """The motivating branch: RAG found nothing, so take the fallback path."""
    assert evaluate({"field": "retrieved", "op": "is_empty"}, {"retrieved": []})
    assert not evaluate({"field": "retrieved", "op": "is_empty"},
                        {"retrieved": [{"n": 1}]})
    assert evaluate({"field": "retrieved", "op": "is_not_empty"}, {"retrieved": [{"n": 1}]})


def test_a_missing_field_is_empty_but_never_equal():
    assert evaluate({"field": "retrieved", "op": "is_empty"}, {})
    assert not evaluate({"field": "retrieved", "op": "eq", "value": []}, {})
    assert not evaluate({"field": "retrieved", "op": "ne", "value": "anything"}, {}), \
        "absent must not satisfy a comparison by accident"


def test_dotted_access_into_a_dict_root():
    state = {"hitl_decision": {"approved": False, "note": "needs legal"}}
    assert evaluate({"field": "hitl_decision.approved", "op": "eq", "value": False}, state)
    assert evaluate({"field": "hitl_decision.note", "op": "contains", "value": "legal"}, state)


def test_numeric_comparisons():
    state = {"llm_output": 7}
    assert evaluate({"field": "llm_output", "op": "gt", "value": 5}, state)
    assert evaluate({"field": "llm_output", "op": "lte", "value": 7}, state)
    assert not evaluate({"field": "llm_output", "op": "lt", "value": 7}, state)


def test_numeric_comparison_against_a_string_is_false_not_an_error():
    assert not evaluate({"field": "llm_output", "op": "gt", "value": 5},
                        {"llm_output": "seven"})


def test_booleans_are_never_compared_numerically():
    assert not evaluate({"field": "llm_output", "op": "gt", "value": 0},
                        {"llm_output": True})


@pytest.mark.parametrize("bad", [None, "x", 42, [], {}, {"field": "nope", "op": "eq", "value": 1}])
def test_evaluation_never_raises(bad):
    assert evaluate(bad, {"llm_output": "x"}) is False


def test_unreachable_state_is_not_readable():
    """Only EngineState roots resolve — nothing else in the dict is visible."""
    assert not evaluate({"field": "user_input", "op": "eq", "value": "secret"},
                        {"api_key": "secret"})


def test_summarize_is_readable_for_traces():
    assert summarize({"field": "retrieved", "op": "is_empty"}) == "retrieved is_empty"
    assert "contains" in summarize({"field": "llm_output", "op": "contains", "value": "x"})


def test_describe_ops_matches_the_implementation():
    """The builder palette reads this; it must not drift from the engine."""
    described = conditions.describe_ops()
    assert set(described["value_ops"]) | set(described["unary_ops"]) == conditions.CONDITION_OPS
    assert set(described["fields"]) == conditions.CONDITION_ROOTS
