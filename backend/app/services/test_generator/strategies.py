import re
import random
import string
from typing import List, Dict, Any
from app.models import TestCase
from .models_ir import Endpoint, Param
from .schema_utils import get_schema, sample_value, wrong_type_value, generate_valid_payload

def get_next_id(counter: List[int]) -> str:
    counter[0] += 1
    return f"tc_{counter[0]:03d}"

def positive_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    payload = None
    if endpoint.body_schema:
        payload = generate_valid_payload(spec, endpoint.body_schema)
        
    # generate valid path by replacing path parameters
    path = endpoint.path
    for param in endpoint.path_params:
        schema = get_schema(spec, param.schema)
        val = sample_value(schema)
        path = re.sub(rf"\{{{param.name}\}}", str(val), path)
        
    return [TestCase(
        id=get_next_id(counter),
        name=f"Valid positive request for {endpoint.method.upper()} {endpoint.path}",
        description="Send valid request with all expected fields.",
        method=endpoint.method.upper(),
        path=path,
        expected_status=200 if endpoint.method.lower() == "get" else 201, # approximate baseline
        payload=payload,
        category="positive"
    )]

def missing_required_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    required = schema.get("required", [])
    props = schema.get("properties", {})
    
    for field in required:
        payload = {k: sample_value(get_schema(spec, v)) for k, v in props.items() if k != field}
        tests.append(TestCase(
            id=get_next_id(counter),
            name=f"Missing required field '{field}' on {endpoint.method.upper()} {endpoint.path}",
            description=f"Send request without required field '{field}'. Expect 4xx.",
            method=endpoint.method.upper(),
            path=endpoint.path,
            expected_status=422,
            payload=payload,
            category="missing_required",
        ))
    return tests

def wrong_type_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    props = schema.get("properties", {})
    
    for field, prop_schema in props.items():
        prop_schema_resolved = get_schema(spec, prop_schema)
        wrong = wrong_type_value(prop_schema_resolved)
        if wrong is None:
            continue
            
        payload = generate_valid_payload(spec, endpoint.body_schema)
        payload[field] = wrong
        
        tests.append(TestCase(
            id=get_next_id(counter),
            name=f"Wrong type for '{field}' on {endpoint.method.upper()} {endpoint.path}",
            description=f"Send '{field}' as wrong type. Expect 4xx.",
            method=endpoint.method.upper(),
            path=endpoint.path,
            expected_status=422,
            payload=payload,
            category="invalid_type",
        ))
    return tests

def query_param_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    tests = []
    required_params = [p for p in endpoint.query_params if p.required]
    for param in required_params:
        tests.append(TestCase(
            id=get_next_id(counter),
            name=f"Missing required query param '{param.name}' on {endpoint.method.upper()} {endpoint.path}",
            description=f"Omit required query parameter '{param.name}'. Expect 4xx.",
            method=endpoint.method.upper(),
            path=endpoint.path,
            expected_status=422,
            params={},
            category="missing_required_param",
        ))
    return tests

def path_param_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    tests = []
    for param in endpoint.path_params:
        schema = get_schema(spec, param.schema)
        if schema.get("type") in ("integer", "number"):
            invalid_path = re.sub(rf"\{{{param.name}\}}", "INVALID_ID", endpoint.path)
            tests.append(TestCase(
                id=get_next_id(counter),
                name=f"Invalid path param '{param.name}' type on {endpoint.method.upper()} {endpoint.path}",
                description=f"Use non-numeric value for '{param.name}' path param. Expect 4xx.",
                method=endpoint.method.upper(),
                path=invalid_path,
                expected_status=422,
                category="invalid_path_param",
            ))
    return tests

def auth_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.requires_auth:
        return []
    return [TestCase(
        id=get_next_id(counter),
        name=f"Unauthenticated request to {endpoint.method.upper()} {endpoint.path}",
        description="Send request without auth token. Expect 401.",
        method=endpoint.method.upper(),
        path=endpoint.path,
        expected_status=401,
        headers={},
        category="auth",
    )]

def boundary_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    props = schema.get("properties", {})
    
    for field, prop_schema in props.items():
        prop_schema_resolved = get_schema(spec, prop_schema)
        t = prop_schema_resolved.get("type")
        
        # Numeric boundaries
        if t in ("integer", "number"):
            minimum = prop_schema_resolved.get("minimum")
            maximum = prop_schema_resolved.get("maximum")
            
            if minimum is not None:
                payload = generate_valid_payload(spec, endpoint.body_schema)
                payload[field] = minimum - 1
                tests.append(TestCase(
                    id=get_next_id(counter),
                    name=f"Below minimum boundary for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                    description=f"Send '{field}' below min limit. Expect 4xx.",
                    method=endpoint.method.upper(),
                    path=endpoint.path,
                    expected_status=422,
                    payload=payload,
                    category="boundary",
                ))
            if maximum is not None:
                payload = generate_valid_payload(spec, endpoint.body_schema)
                payload[field] = maximum + 1
                tests.append(TestCase(
                    id=get_next_id(counter),
                    name=f"Above maximum boundary for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                    description=f"Send '{field}' above max limit. Expect 4xx.",
                    method=endpoint.method.upper(),
                    path=endpoint.path,
                    expected_status=422,
                    payload=payload,
                    category="boundary",
                ))
                
        # String boundaries
        if t == "string":
            min_len = prop_schema_resolved.get("minLength")
            max_len = prop_schema_resolved.get("maxLength")
            
            if min_len is not None and min_len > 0:
                payload = generate_valid_payload(spec, endpoint.body_schema)
                payload[field] = "a" * (min_len - 1)
                tests.append(TestCase(
                    id=get_next_id(counter),
                    name=f"Below minLength for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                    description=f"Send '{field}' shorter than minLength. Expect 4xx.",
                    method=endpoint.method.upper(),
                    path=endpoint.path,
                    expected_status=422,
                    payload=payload,
                    category="boundary",
                ))
            if max_len is not None:
                payload = generate_valid_payload(spec, endpoint.body_schema)
                payload[field] = "a" * (max_len + 1)
                tests.append(TestCase(
                    id=get_next_id(counter),
                    name=f"Above maxLength for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                    description=f"Send '{field}' longer than maxLength. Expect 4xx.",
                    method=endpoint.method.upper(),
                    path=endpoint.path,
                    expected_status=422,
                    payload=payload,
                    category="boundary",
                ))
                
    return tests

def enum_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    props = schema.get("properties", {})
    
    for field, prop_schema in props.items():
        prop_schema_resolved = get_schema(spec, prop_schema)
        if "enum" in prop_schema_resolved:
            payload = generate_valid_payload(spec, endpoint.body_schema)
            payload[field] = "INVALID_ENUM_VALUE_123"
            tests.append(TestCase(
                id=get_next_id(counter),
                name=f"Invalid enum value for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                description=f"Send invalid enum value for '{field}'. Expect 4xx.",
                method=endpoint.method.upper(),
                path=endpoint.path,
                expected_status=422,
                payload=payload,
                category="enum",
            ))
            
    return tests

def format_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    props = schema.get("properties", {})
    
    invalid_formats = {
        "email": "not-an-email",
        "uuid": "123",
        "date": "invalid-date",
        "date-time": "invalid-date-time",
        "uri": "not-a-uri"
    }
    
    for field, prop_schema in props.items():
        prop_schema_resolved = get_schema(spec, prop_schema)
        fmt = prop_schema_resolved.get("format")
        if fmt in invalid_formats:
            payload = generate_valid_payload(spec, endpoint.body_schema)
            payload[field] = invalid_formats[fmt]
            tests.append(TestCase(
                id=get_next_id(counter),
                name=f"Invalid format '{fmt}' for '{field}' on {endpoint.method.upper()} {endpoint.path}",
                description=f"Send invalid {fmt} string for '{field}'. Expect 4xx.",
                method=endpoint.method.upper(),
                path=endpoint.path,
                expected_status=422,
                payload=payload,
                category="format",
            ))
            
    return tests

def fuzz_strategy(spec: Dict[str, Any], endpoint: Endpoint, counter: List[int]) -> List[TestCase]:
    if not endpoint.body_schema:
        return []
        
    tests = []
    schema = get_schema(spec, endpoint.body_schema)
    props = schema.get("properties", {})
    
    # Let's target the first string field for fuzzing to keep tests manageable
    string_fields = [k for k, v in props.items() if get_schema(spec, v).get("type") == "string"]
    
    if string_fields:
        field = string_fields[0]
        payload = generate_valid_payload(spec, endpoint.body_schema)
        
        # 1. Very large string
        payload[field] = "A" * 10000
        tests.append(TestCase(
            id=get_next_id(counter),
            name=f"Fuzz: Large payload for '{field}' on {endpoint.method.upper()} {endpoint.path}",
            description=f"Send 10k chars for '{field}'. Expect handled cleanly.",
            method=endpoint.method.upper(),
            path=endpoint.path,
            expected_status=422, # Or 413, we assume 422 standard validation fail
            payload=payload,
            category="fuzz",
        ))
        
        # 2. Special characters
        payload = generate_valid_payload(spec, endpoint.body_schema)
        payload[field] = "<script>alert(1)</script> '\\\" DROP TABLE users; \x00"
        tests.append(TestCase(
            id=get_next_id(counter),
            name=f"Fuzz: Special characters for '{field}' on {endpoint.method.upper()} {endpoint.path}",
            description=f"Send injection payloads for '{field}'. Expect handled cleanly.",
            method=endpoint.method.upper(),
            path=endpoint.path,
            expected_status=422,
            payload=payload,
            category="fuzz",
        ))
            
    return tests

STRATEGIES = [
    positive_strategy,
    missing_required_strategy,
    wrong_type_strategy,
    query_param_strategy,
    path_param_strategy,
    auth_strategy,
    boundary_strategy,
    enum_strategy,
    format_strategy,
    fuzz_strategy
]
