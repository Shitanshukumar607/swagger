from typing import Any, Callable, Dict, Optional, Tuple
from uuid import uuid4

from app.models import TestCase

from .schema_utils import generate_valid_payload, get_schema, sample_value

OperationMatcher = Callable[[str, str, Dict[str, Any]], bool]
FoundOperation = Tuple[str, str, Dict[str, Any], Dict[str, Any]]


def _infer_success_status(operation: Dict[str, Any], fallback: int) -> int:
    responses = operation.get("responses", {})
    success_codes = []

    for raw_status in responses.keys():
        status_code = None
        if isinstance(raw_status, int):
            status_code = raw_status
        elif isinstance(raw_status, str) and raw_status.isdigit():
            status_code = int(raw_status)

        if status_code is not None and 200 <= status_code < 300:
            success_codes.append(status_code)

    if success_codes:
        return min(success_codes)

    return fallback


def _extract_request_schema(operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    req_body = operation.get("requestBody", {})
    content = req_body.get("content", {})
    for content_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        if content_type in content:
            schema = content[content_type].get("schema")
            if schema:
                return schema
    return None


def _has_protected_operations(spec: Dict[str, Any]) -> bool:
    paths = spec.get("paths", {})
    for _, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            if bool(operation.get("security") or spec.get("security")):
                return True
    return False


def _is_signup_operation(path: str, method: str, operation: Dict[str, Any]) -> bool:
    if method != "post":
        return False
    if not _extract_request_schema(operation):
        return False

    path_lower = path.lower()
    op_text = f"{operation.get('summary', '')} {operation.get('description', '')}".lower()
    signup_keywords = ("signup", "sign-up", "register", "registration", "create account", "create-account")

    return any(k in path_lower for k in signup_keywords) or any(k in op_text for k in signup_keywords)


def _is_login_operation(path: str, method: str, operation: Dict[str, Any]) -> bool:
    if method != "post":
        return False
    if not _extract_request_schema(operation):
        return False

    path_lower = path.lower()
    op_text = f"{operation.get('summary', '')} {operation.get('description', '')}".lower()
    login_keywords = ("login", "sign in", "sign-in", "signin", "authenticate", "auth")
    exclusion_keywords = ("logout", "reset", "forgot", "register", "signup", "sign-up")

    if any(k in path_lower for k in exclusion_keywords) or any(k in op_text for k in exclusion_keywords):
        return False

    return any(k in path_lower for k in login_keywords) or any(k in op_text for k in login_keywords)


def is_auth_setup_operation(path: str, method: str, operation: Dict[str, Any]) -> bool:
    return _is_signup_operation(path, method, operation) or _is_login_operation(path, method, operation)


def _find_operation(spec: Dict[str, Any], matcher: OperationMatcher) -> Optional[FoundOperation]:
    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("post", "put", "patch", "get", "delete"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            if matcher(path, method, operation):
                schema = _extract_request_schema(operation)
                if schema:
                    return method, path, operation, schema
    return None


def _build_auth_payload(
    spec: Dict[str, Any],
    schema_or_ref: Dict[str, Any],
    email: str,
    password: str,
    username: str,
) -> Dict[str, Any]:
    payload = generate_valid_payload(spec, schema_or_ref)
    schema = get_schema(spec, schema_or_ref)
    props = schema.get("properties", {})
    required_fields = schema.get("required", [])

    for field_name in props.keys():
        field_lower = field_name.lower()

        if "email" in field_lower:
            payload[field_name] = email
            continue

        if "confirm" in field_lower and "password" in field_lower:
            payload[field_name] = password
            continue

        if "password" in field_lower or field_lower in ("pass", "pwd"):
            payload[field_name] = password
            continue

        if field_lower in (
            "name",
            "full_name",
            "fullname",
            "display_name",
            "displayname",
            "username",
        ) or "username" in field_lower:
            payload[field_name] = username
            continue

    for field_name in required_fields:
        if field_name not in payload:
            field_schema = get_schema(spec, props.get(field_name, {}))
            payload[field_name] = sample_value(field_schema)

    return payload


def build_auth_setup_tests(spec: Dict[str, Any], counter: list[int]) -> list[TestCase]:
    if not _has_protected_operations(spec):
        return []

    signup_op = _find_operation(spec, _is_signup_operation)
    login_op = _find_operation(spec, _is_login_operation)

    if not signup_op or not login_op:
        return []

    signup_method, signup_path, signup_operation, signup_schema = signup_op
    login_method, login_path, login_operation, login_schema = login_op

    suffix = uuid4().hex[:8]
    email = f"autotest_{suffix}@example.com"
    password = f"Passw0rd!{suffix}"
    username = f"autotest_{suffix}"

    signup_payload = _build_auth_payload(spec, signup_schema, email, password, username)
    login_payload = _build_auth_payload(spec, login_schema, email, password, username)

    counter[0] += 1
    signup_test = TestCase(
        id=f"tc_{counter[0]:03d}",
        name=f"Auth setup: create dummy user via {signup_method.upper()} {signup_path}",
        description="Create a unique dummy user used for authentication setup.",
        method=signup_method.upper(),
        path=signup_path,
        expected_status=_infer_success_status(signup_operation, 201),
        payload=signup_payload,
        category="auth_setup_signup",
        requires_auth=False,
    )

    counter[0] += 1
    login_test = TestCase(
        id=f"tc_{counter[0]:03d}",
        name=f"Auth setup: login via {login_method.upper()} {login_path} and capture token",
        description="Login with the dummy user and capture auth token for protected requests.",
        method=login_method.upper(),
        path=login_path,
        expected_status=_infer_success_status(login_operation, 200),
        payload=login_payload,
        category="auth_setup_login",
        requires_auth=False,
    )

    return [signup_test, login_test]