from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Param:
    name: str
    in_: str
    required: bool
    schema: Dict[str, Any]

@dataclass
class Endpoint:
    method: str
    path: str
    operation: Dict[str, Any]
    body_schema: Optional[Dict[str, Any]] = None
    query_params: List[Param] = field(default_factory=list)
    path_params: List[Param] = field(default_factory=list)
    requires_auth: bool = False
