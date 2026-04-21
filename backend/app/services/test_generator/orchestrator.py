from typing import List, Dict, Any
from app.models import TestCase
from .models_ir import Endpoint, Param
from .strategies import STRATEGIES
from .schema_utils import get_schema

def build_endpoint(spec: Dict[str, Any], method: str, path: str, operation: Dict[str, Any]) -> Endpoint:
    # Build params
    raw_params = operation.get("parameters", [])
    path_item = spec.get("paths", {}).get(path, {})
    raw_params = path_item.get("parameters", []) + raw_params

    query_params = []
    path_params = []
    
    for rp in raw_params:
        p = Param(
            name=rp.get("name", ""),
            in_=rp.get("in", ""),
            required=rp.get("required", False),
            schema=rp.get("schema", {})
        )
        if p.in_ == "query":
            query_params.append(p)
        elif p.in_ == "path":
            path_params.append(p)
            
    # Extract body schema
    body_schema = None
    req_body = operation.get("requestBody", {})
    content = req_body.get("content", {})
    for ct in ("application/json", "application/x-www-form-urlencoded"):
        if ct in content:
            body_schema = content[ct].get("schema")
            break
            
    # Check Auth
    requires_auth = bool(operation.get("security") or spec.get("security"))
    
    return Endpoint(
        method=method,
        path=path,
        operation=operation,
        body_schema=body_schema,
        query_params=query_params,
        path_params=path_params,
        requires_auth=requires_auth
    )

def generate_tests_for_operation(
    spec: Dict[str, Any],
    method: str,
    path: str,
    operation: Dict[str, Any],
    counter: List[int]
) -> List[TestCase]:
    endpoint = build_endpoint(spec, method, path, operation)
    tests = []
    
    for strategy in STRATEGIES:
        strategy_tests = strategy(spec, endpoint, counter)
        for t in strategy_tests:
            if t.category != "auth":
                t.requires_auth = endpoint.requires_auth
        tests.extend(strategy_tests)
        
    return tests
