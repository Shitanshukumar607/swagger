from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import yaml
import httpx
import asyncio
import re
from typing import Any, Optional

app = FastAPI(title="Swagger Negative Test Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────

class TestCase(BaseModel):
    id: str
    name: str
    description: str
    method: str
    path: str
    expected_status: int
    payload: Optional[dict] = None
    headers: Optional[dict] = None
    params: Optional[dict] = None
    category: str  # e.g. "missing_required", "invalid_type", "auth", etc.

class RunResult(BaseModel):
    id: str
    name: str
    status: str   # "passed" | "failed" | "error"
    expected_status: int
    actual_status: Optional[int] = None
    message: str

class RunRequest(BaseModel):
    tests: list[TestCase]
    base_url: str

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_swagger(content: bytes, filename: str) -> dict:
    """Parse JSON or YAML swagger/openapi file."""
    text = content.decode("utf-8")
    if filename.endswith((".yaml", ".yml")):
        return yaml.safe_load(text)
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


def required_fields(spec: dict, schema: dict) -> list[str]:
    s = get_schema(spec, schema)
    return s.get("required", [])


def properties_of(spec: dict, schema: dict) -> dict:
    s = get_schema(spec, schema)
    return s.get("properties", {})


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


def generate_tests_for_operation(
    spec: dict,
    method: str,
    path: str,
    operation: dict,
    counter: list,
) -> list[TestCase]:
    tests: list[TestCase] = []
    op_id = operation.get("operationId", f"{method}_{path}")

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
    # also include path-level params
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
            headers={},  # no auth header
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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/generate-tests")
async def generate_tests(file: UploadFile = File(...)):
    content = await file.read()
    try:
        spec = parse_swagger(content, file.filename or "spec.json")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse spec: {e}")

    tests: list[TestCase] = []
    counter = [0]

    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not operation:
                continue
            tests.extend(generate_tests_for_operation(spec, method, path, operation, counter))

    return {"tests": [t.model_dump() for t in tests], "count": len(tests)}


@app.post("/run-tests")
async def run_tests(req: RunRequest):
    results: list[RunResult] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [_run_single(client, test, req.base_url) for test in req.tests]
        results = await asyncio.gather(*tasks)

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errored = sum(1 for r in results if r.status == "error")

    return {
        "results": [r.model_dump() for r in results],
        "summary": {"passed": passed, "failed": failed, "errored": errored, "total": len(results)},
    }


async def _run_single(client: httpx.AsyncClient, test: TestCase, base_url: str) -> RunResult:
    url = base_url.rstrip("/") + test.path
    headers = test.headers or {}
    params = test.params or {}

    try:
        resp = await client.request(
            method=test.method,
            url=url,
            json=test.payload,
            headers=headers,
            params=params,
        )
        actual = resp.status_code
        # For auth tests, also accept 403
        expected_set = {test.expected_status}
        if test.category == "auth":
            expected_set.add(403)
        # Accept any 4xx as passing for validation tests
        if test.category in ("missing_required", "invalid_type", "missing_required_param", "invalid_path_param"):
            passed = 400 <= actual < 500
        else:
            passed = actual in expected_set

        return RunResult(
            id=test.id,
            name=test.name,
            status="passed" if passed else "failed",
            expected_status=test.expected_status,
            actual_status=actual,
            message=f"Expected {test.expected_status}, got {actual}" if not passed else "Test passed",
        )
    except Exception as e:
        return RunResult(
            id=test.id,
            name=test.name,
            status="error",
            expected_status=test.expected_status,
            actual_status=None,
            message=str(e),
        )


@app.get("/health")
def health():
    return {"status": "ok"}
