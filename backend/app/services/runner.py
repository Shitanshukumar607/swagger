import httpx
from app.models import TestCase, RunResult


def _extract_token_value(data):
    if isinstance(data, dict):
        for key in ("token", "access_token", "accessToken", "id_token", "idToken", "jwt"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value

        for value in data.values():
            token = _extract_token_value(value)
            if token:
                return token

    if isinstance(data, list):
        for item in data:
            token = _extract_token_value(item)
            if token:
                return token

    return None

async def run_single_test(client: httpx.AsyncClient, test: TestCase, base_url: str, auth_token: str = None) -> RunResult:
    url = base_url.rstrip("/") + test.path
    headers = test.headers or {}
    params = test.params or {}

    if test.requires_auth and auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        resp = await client.request(
            method=test.method,
            url=url,
            json=test.payload,
            headers=headers,
            params=params,
        )
        actual = resp.status_code
        response_body = None
        if resp.content:
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    response_body = resp.json()
                except Exception:
                    response_body = resp.text
            else:
                response_body = resp.text

        response = {
            "status_code": resp.status_code,
            "reason_phrase": resp.reason_phrase,
            "http_version": resp.http_version,
            "url": str(resp.request.url),
            "headers": dict(resp.headers),
            "body": response_body,
        }

        # For auth tests, also accept 403
        expected_set = {test.expected_status}
        if test.category == "auth":
            expected_set.add(403)
            
        passed = actual in expected_set

        extracted_token = None
        if passed and 200 <= actual < 300:
            try:
                data = resp.json()
                extracted_token = _extract_token_value(data)
            except:
                pass

        return RunResult(
            id=test.id,
            name=test.name,
            status="passed" if passed else "failed",
            expected_status=test.expected_status,
            actual_status=actual,
            message=f"Expected {test.expected_status}, got {actual}" if not passed else "Test passed",
            response=response,
            response_body=response_body,
            extracted_token=extracted_token,
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
