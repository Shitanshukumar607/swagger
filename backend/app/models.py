from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class TestCase(BaseModel):
    id: str
    name: str
    description: str
    method: str
    path: str
    expected_status: int
    payload: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    params: Optional[Dict[str, str]] = None
    category: str  # e.g. "missing_required", "invalid_type", "auth", etc.
    requires_auth: bool = False

class RunResult(BaseModel):
    id: str
    name: str
    status: str   # "passed" | "failed" | "error"
    expected_status: int
    actual_status: Optional[int] = None
    message: str
    response: Optional[Dict[str, Any]] = None
    response_body: Optional[Any] = None
    extracted_token: Optional[str] = None

class RunRequest(BaseModel):
    tests: List[TestCase]
    base_url: str

class Summary(BaseModel):
    passed: int
    failed: int
    errored: int
    total: int

class RunResponse(BaseModel):
    results: List[RunResult]
    summary: Summary
