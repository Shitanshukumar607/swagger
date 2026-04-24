import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models import RunRequest, TestCase
from app.services.test_generator import (
    build_auth_setup_tests,
    generate_tests_for_operation,
    parse_swagger,
)
from app.services.runner import run_single_test

router = APIRouter()

@router.post("/generate-tests")
async def generate_tests(file: UploadFile = File(...)):
    content = await file.read()
    try:
        spec = parse_swagger(content, file.filename or "spec.json")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse spec: {e}")

    tests: list[TestCase] = []
    counter = [0]

    auth_setup_tests = build_auth_setup_tests(spec, counter)
    tests.extend(auth_setup_tests)
    skip_positive_for_auth_setup = bool(auth_setup_tests)

    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not operation:
                continue
            tests.extend(
                generate_tests_for_operation(
                    spec,
                    method,
                    path,
                    operation,
                    counter,
                    skip_positive_for_auth_setup=skip_positive_for_auth_setup,
                )
            )

    return {"tests": [t.model_dump() for t in tests], "count": len(tests)}


@router.post("/run-tests")
async def run_tests(req: RunRequest):
    results = []
    current_token = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        for test in req.tests:
            result = await run_single_test(client, test, req.base_url, current_token)
            if result.extracted_token:
                current_token = result.extracted_token
            results.append(result)

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    errored = sum(1 for r in results if r.status == "error")

    return {
        "results": [r.model_dump() for r in results],
        "summary": {
            "passed": passed, 
            "failed": failed, 
            "errored": errored, 
            "total": len(results)
        },
    }

@router.get("/health")
def health():
    return {"status": "ok"}
