import json
from typing import Dict, Any

def parse_swagger(content: bytes, filename: str) -> Dict[str, Any]:
    """Parse JSON swagger/openapi file."""
    text = content.decode("utf-8")
    return json.loads(text)
