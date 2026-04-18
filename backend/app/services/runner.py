import httpx
from app.models import TestCase, RunResult

async def run_single_test(client: httpx.AsyncClient, test: TestCase, base_url: str) -> RunResult:
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
