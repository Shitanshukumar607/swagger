import random
import string
from typing import Any, Dict

def resolve_ref(spec: Dict[str, Any], ref: str) -> Dict[str, Any]:
    """Simple $ref resolver within the same document."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node

def get_schema(spec: Dict[str, Any], schema_or_ref: Dict[str, Any]) -> Dict[str, Any]:
    if "$ref" in schema_or_ref:
        return resolve_ref(spec, schema_or_ref["$ref"])
    return schema_or_ref

def wrong_type_value(prop_schema: Dict[str, Any]) -> Any:
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

def sample_value(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return "test"
    t = schema.get("type", "string")
    fmt = schema.get("format", "")
    example = schema.get("example")
    
    if example is not None:
        return example
        
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

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
        items = schema.get("items", {})
        return [sample_value(items)]
    if t == "object":
        # we can't fully resolve props without spec here, but mostly used for simple inner objects
        props = schema.get("properties", {})
        return {k: sample_value(v) for k, v in props.items()}
    return "test"

def generate_valid_payload(spec: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    resolved = get_schema(spec, schema)
    props = resolved.get("properties", {})
    return {k: sample_value(get_schema(spec, v)) for k, v in props.items()}
