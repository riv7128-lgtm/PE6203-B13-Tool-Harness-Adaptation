"""Validation and preservation checks for normalized tool knowledge.

This is a deliberately small validator, not a replacement for a complete JSON
Schema implementation or the benchmark's task judge. It supports the schema
features used by the local contract fixtures and reports unsupported features.
"""

from __future__ import annotations

import json
import math
from typing import Any


class HarnessValidationError(ValueError):
    """A harness violates the normalized knowledge contract."""


def harness_errors(harness: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(harness, dict):
        return ["harness must be an object"]
    try:
        json.dumps(harness, allow_nan=False)
    except (TypeError, ValueError):
        errors.append("harness must contain only finite JSON values")
    tools = harness.get("tools")
    if not isinstance(tools, list):
        return errors + ["tools must be a list"]
    names: set[str] = set()
    for index, tool in enumerate(tools):
        prefix = f"tools[{index}]"
        if not isinstance(tool, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
        elif name in names:
            errors.append(f"duplicate tool name: {name}")
        else:
            names.add(name)
        if not isinstance(tool.get("description"), str):
            errors.append(f"{prefix}.description must be a string")
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            errors.append(f"{prefix}.inputSchema must be an object")
        else:
            if schema.get("type", "object") != "object":
                errors.append(f"{prefix}.inputSchema must describe an object")
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            if not isinstance(properties, dict):
                errors.append(f"{prefix}.inputSchema.properties must be an object")
            if not isinstance(required, list) or any(not isinstance(x, str) for x in required):
                errors.append(f"{prefix}.inputSchema.required must be a list of strings")
            # A required property need not appear in properties in general JSON
            # Schema, so we intentionally do not reject that legal pattern.
        if "outputSchema" in tool and not isinstance(tool["outputSchema"], dict):
            errors.append(f"{prefix}.outputSchema must be an object")
        if "server" in tool and not isinstance(tool["server"], str):
            errors.append(f"{prefix}.server must be a string")
    for field in ("usage_rules", "routing"):
        values = harness.get(field, {})
        if not isinstance(values, dict):
            errors.append(f"{field} must be an object")
            continue
        for name, value in values.items():
            if name not in names:
                errors.append(f"{field} references unknown tool: {name}")
            if field == "usage_rules":
                if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                    errors.append(f"usage_rules[{name}] must be a list of strings")
            elif not isinstance(value, str):
                errors.append(f"routing[{name}] must be a string")
    rules = harness.get("global_rules", [])
    if not isinstance(rules, list) or any(not isinstance(x, str) for x in rules):
        errors.append("global_rules must be a list of strings")
    return errors


def validate_harness(harness: Any) -> None:
    """Raise on malformed snapshots; never silently repair evaluation inputs."""
    errors = harness_errors(harness)
    if errors:
        raise HarnessValidationError("; ".join(errors))


_SUPPORTED_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "const", "description", "title", "default", "examples", "$schema", "$id",
    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
}


def _check_value(value: Any, schema: Any, path: str, errors: list[str]) -> None:
    if isinstance(schema, bool):
        if not schema:
            errors.append(f"{path}: schema forbids this value")
        return
    if not isinstance(schema, dict):
        errors.append(f"{path}: malformed schema")
        return
    unsupported = sorted(set(schema) - _SUPPORTED_SCHEMA_KEYS)
    if unsupported:
        errors.append(f"{path}: unsupported schema keywords: {', '.join(unsupported)}")
    expected = schema.get("type")
    valid_types = {
        "object": lambda x: isinstance(x, dict),
        "array": lambda x: isinstance(x, list),
        "string": lambda x: isinstance(x, str),
        "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
        "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x),
        "boolean": lambda x: isinstance(x, bool),
        "null": lambda x: x is None,
    }
    if expected is not None:
        alternatives = expected if isinstance(expected, list) else [expected]
        if any(t not in valid_types for t in alternatives):
            errors.append(f"{path}: unsupported schema type {expected}")
            return
        if not any(valid_types[t](value) for t in alternatives):
            errors.append(f"{path}: expected {expected}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not in enum")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value differs from const")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            errors.append(f"{path}: malformed object schema")
            return
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property missing")
        for key, item in value.items():
            if key in properties:
                _check_value(item, properties[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"{path}.{key}: additional property forbidden")
            elif isinstance(schema.get("additionalProperties"), dict):
                _check_value(item, schema["additionalProperties"], f"{path}.{key}", errors)
    elif isinstance(value, list):
        if "items" in schema:
            for index, item in enumerate(value):
                _check_value(item, schema["items"], f"{path}[{index}]", errors)
        for keyword, comparator in (("minItems", lambda n, b: n < b), ("maxItems", lambda n, b: n > b)):
            if keyword in schema and comparator(len(value), schema[keyword]):
                errors.append(f"{path}: violates {keyword}")
    elif isinstance(value, str):
        for keyword, comparator in (("minLength", lambda n, b: n < b), ("maxLength", lambda n, b: n > b)):
            if keyword in schema and comparator(len(value), schema[keyword]):
                errors.append(f"{path}: violates {keyword}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")


def validate_tool_call(harness: dict, tool_name: str, arguments: Any) -> list[str]:
    """Return local structural call errors; this does not score task success."""
    validate_harness(harness)
    tools = {tool["name"]: tool for tool in harness["tools"]}
    if tool_name not in tools:
        return [f"unknown tool: {tool_name}"]
    errors: list[str] = []
    _check_value(arguments, tools[tool_name]["inputSchema"], "$", errors)
    return errors


def preservation_report(old_harness: dict, new_harness: dict, patched: dict) -> dict:
    """Audit unaffected knowledge plus global and unrelated top-level fields."""
    from .changes import canonical_digest, detect_changes

    validate_harness(patched)
    changes = detect_changes(old_harness, new_harness)
    unchanged = changes["unchanged"]
    old_tools = {tool["name"]: tool for tool in old_harness["tools"]}
    patched_tools = {tool["name"]: tool for tool in patched["tools"]}
    violations: list[str] = []
    for name in unchanged:
        if canonical_digest(patched_tools.get(name)) != canonical_digest(old_tools[name]):
            violations.append(f"tools/{name}")
        for field in ("usage_rules", "routing"):
            before = old_harness.get(field, {})
            after = patched.get(field, {})
            if (name in before) != (name in after) or canonical_digest(before.get(name)) != canonical_digest(after.get(name)):
                violations.append(f"{field}/{name}")
    if ("global_rules" in old_harness) != ("global_rules" in patched) or canonical_digest(old_harness.get("global_rules")) != canonical_digest(patched.get("global_rules")):
        violations.append("global_rules")
    for field in set(old_harness) | set(patched):
        if field not in {"tools", "usage_rules", "routing", "global_rules"}:
            if (field in old_harness) != (field in patched) or canonical_digest(old_harness.get(field)) != canonical_digest(patched.get(field)):
                violations.append(field)
    return {
        "unchanged_tools_checked": len(unchanged),
        "unchanged_tool_names": unchanged,
        "preserved": not violations,
        "violations": violations,
        "global_rules_preserved": "global_rules" not in violations,
    }
