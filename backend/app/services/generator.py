import json
import re
from typing import Any, List
from app.models import TestCase

def parse_swagger(content: bytes, filename: str) -> dict:
    """Parse JSON swagger/openapi file."""
    text = content.decode("utf-8")
    return json.loads(text)


def resolve_ref(spec: dict, ref: str) -> dict:
    """Simple $ref resolver within the same document."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def get_schema(spec: dict, schema_or_ref: dict) -> dict:
    if "$ref" in schema_or_ref:
        return resolve_ref(spec, schema_or_ref["$ref"])
    return schema_or_ref


def wrong_type_value(prop_schema: dict) -> Any:
    """Return a value of the wrong type for a property."""
    t = prop_schema.get("type", "string")
    if t == "string":
        return 99999
    if t in ("integer", "number"):
        return "not_a_number"
    if t == "boolean":
        return "yes_string"
    if t == "array":
        return "not_an_array"
    if t == "object":
        return "not_an_object"
    return None


def _sample_value(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return "test"
    t = schema.get("type", "string")
    fmt = schema.get("format", "")
    example = schema.get("example")
    if example is not None:
        return example
    if t == "string":
        if fmt == "email":
            return "test@example.com"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return "test_string"
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    if t == "array":
        return []
    if t == "object":
        return {}
    return "test"


def generate_tests_for_operation(
    spec: dict,
    method: str,
    path: str,
    operation: dict,
    counter: List[int],
) -> List[TestCase]:
    tests: List[TestCase] = []

    # ── 1. Missing required body fields ──────────────────────────────────────
    req_body = operation.get("requestBody", {})
    content = req_body.get("content", {})
    json_schema = None
    for ct in ("application/json", "application/x-www-form-urlencoded"):
        if ct in content:
            json_schema = content[ct].get("schema")
            break

    if json_schema:
        schema = get_schema(spec, json_schema)
        required = schema.get("required", [])
        props = schema.get("properties", {})

        for field in required:
            counter[0] += 1
            payload = {k: _sample_value(v) for k, v in props.items() if k != field}
            tests.append(TestCase(
                id=f"tc_{counter[0]:03d}",
                name=f"Missing required field '{field}' on {method.upper()} {path}",
                description=f"Send request without required field '{field}'. Expect 4xx.",
                method=method.upper(),
                path=path,
                expected_status=422,
                payload=payload,
                category="missing_required",
            ))

        # ── 2. Wrong type on each field ───────────────────────────────────────
        for field, prop_schema in props.items():
            prop_schema_resolved = get_schema(spec, prop_schema)
            wrong = wrong_type_value(prop_schema_resolved)
            if wrong is None:
                continue
            counter[0] += 1
            payload = {k: _sample_value(v) for k, v in props.items()}
            payload[field] = wrong
            tests.append(TestCase(
                id=f"tc_{counter[0]:03d}",
                name=f"Wrong type for '{field}' on {method.upper()} {path}",
                description=f"Send '{field}' as wrong type. Expect 4xx.",
                method=method.upper(),
                path=path,
                expected_status=422,
                payload=payload,
                category="invalid_type",
            ))

    # ── 3. Missing required query/path parameters ─────────────────────────────
    parameters = operation.get("parameters", [])
    path_item = spec.get("paths", {}).get(path, {})
    parameters = path_item.get("parameters", []) + parameters

    required_params = [p for p in parameters if p.get("required") and p.get("in") in ("query",)]
    for param in required_params:
        counter[0] += 1
        tests.append(TestCase(
            id=f"tc_{counter[0]:03d}",
            name=f"Missing required query param '{param['name']}' on {method.upper()} {path}",
            description=f"Omit required query parameter '{param['name']}'. Expect 4xx.",
            method=method.upper(),
            path=path,
            expected_status=422,
            params={},
            category="missing_required_param",
        ))

    # ── 4. Unauthenticated request (if security defined) ─────────────────────
    has_security = bool(operation.get("security") or spec.get("security"))
    if has_security:
        counter[0] += 1
        tests.append(TestCase(
            id=f"tc_{counter[0]:03d}",
            name=f"Unauthenticated request to {method.upper()} {path}",
            description="Send request without auth token. Expect 401.",
            method=method.upper(),
            path=path,
            expected_status=401,
            headers={},
            category="auth",
        ))

    # ── 5. Invalid path param (if exists) ─────────────────────────────────────
    path_params = [p for p in parameters if p.get("in") == "path"]
    for param in path_params:
        if param.get("schema", {}).get("type") in ("integer", "number"):
            counter[0] += 1
            invalid_path = re.sub(rf"\{{{param['name']}\}}", "INVALID_ID", path)
            tests.append(TestCase(
                id=f"tc_{counter[0]:03d}",
                name=f"Invalid path param '{param['name']}' type on {method.upper()} {path}",
                description=f"Use non-numeric value for '{param['name']}' path param. Expect 4xx.",
                method=method.upper(),
                path=invalid_path,
                expected_status=422,
                category="invalid_path_param",
            ))

    return tests
