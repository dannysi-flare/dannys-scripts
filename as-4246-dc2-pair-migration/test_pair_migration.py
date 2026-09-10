#!/usr/bin/env python3
"""Self-check for the closure port — the one piece of logic that is not a mongo call.

    ./test_pair_migration.py
"""
from pair_migration import latest_by, parse_field_path, resolve_field_dependencies


def test_flare_condition_is_transitive() -> None:
    """A gate on a gate is pulled in too — the screening datapoint nobody templates."""
    properties = {
        "templated": {"flare_condition": {"key": "gate", "value": True}},
        "gate": {"flare_condition": {"key": "screening", "value": True}},
        "screening": {"type": "boolean"},
        "unrelated": {"type": "string"},
    }
    assert resolve_field_dependencies({"templated"}, properties, []) == {"templated", "gate", "screening"}


def test_all_of_patterns() -> None:
    """`if.required` keys and `if.properties` names both gate their `then` properties."""
    all_of = [
        {"if": {"required": ["hasChildren"]}, "then": {"properties": {"childCount": {}}}},
        {"if": {"properties": {"state": {"const": "CA"}}}, "then": {"properties": {"caOnlyField": {}}}},
        {"if": {"required": ["irrelevant"]}, "then": {"properties": {"notAsked": {}}}},
    ]
    closure = resolve_field_dependencies({"childCount", "caOnlyField"}, {}, all_of)
    assert closure == {"childCount", "caOnlyField", "hasChildren", "state"}, closure


def test_array_sub_paths_collapse_to_top_level() -> None:
    assert parse_field_path("children[].name") == ("children", "name")
    assert parse_field_path("lastName") == ("lastName", None)
    assert resolve_field_dependencies({"children[].name"}, {}, []) == {"children"}


def test_latest_by_picks_highest_version() -> None:
    docs = [
        {"_id": "a", "draftTypeId": "lineage", "versionId": 1},
        {"_id": "b", "draftTypeId": "lineage", "versionId": 3},
        {"_id": "c", "draftTypeId": "lineage", "versionId": 2},
        {"_id": "d", "versionId": 1},
    ]
    picked = {str(doc["_id"]) for doc in latest_by(docs, "draftTypeId")}
    assert picked == {"b", "d"}, picked


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_"):
            case()
            print("ok", name)
