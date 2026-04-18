import asyncio
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models import RunRequest, RunResponse, TestCase
from app.services.generator import parse_swagger, generate_tests_for_operation
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


@router.post("/run-tests")
async def run_tests(req: RunRequest):
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [run_single_test(client, test, req.base_url) for test in req.tests]
        results = await asyncio.gather(*tasks)

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
