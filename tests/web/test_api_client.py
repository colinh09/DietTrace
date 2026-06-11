"""Typed API client for the Next.js frontend.

Encodes the done-criterion as static checks on ``frontend/src/lib/api.ts``: the
client reads its base URL from ``NEXT_PUBLIC_API_BASE`` (default
http://localhost:8080), exposes a call per backend endpoint the frontend needs
(log/history/analysis/goals), and declares TypeScript types matching each
response shape from ``dietrace.web.app``. The Next build itself is verified
separately via ``cd frontend && npm run build``.
"""

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
API = FRONTEND / "src" / "lib" / "api.ts"


def test_api_client_file_exists():
    """The typed client lives at the conventional frontend lib path."""
    assert API.exists(), "frontend/src/lib/api.ts missing"


def test_base_url_from_env_with_localhost_default():
    """Base URL comes from NEXT_PUBLIC_API_BASE, defaulting to localhost:8080."""
    src = API.read_text()
    assert "NEXT_PUBLIC_API_BASE" in src, "base URL env var not referenced"
    assert "http://localhost:8080" in src, "default base URL (localhost:8080) missing"


def test_exposes_a_call_per_endpoint():
    """One exported async function per endpoint the frontend needs."""
    src = API.read_text()
    for fn in ("logMeal", "getHistory", "getAnalysis", "getGoals"):
        assert f"export async function {fn}" in src, f"client call {fn}() missing"


def test_calls_hit_the_expected_routes():
    """Each call targets its FastAPI route."""
    src = API.read_text()
    for route in ("/log", "/history", "/analysis", "/goals"):
        assert route in src, f"route {route} not called"


def test_response_types_declared():
    """TypeScript types matching each endpoint's response are exported."""
    src = API.read_text()
    for type_name in (
        "Nutrient",
        "LoggedItem",
        "TraceStep",
        "LogResponse",
        "Meal",
        "HistoryResponse",
        "Goal",
        "GoalProgress",
        "AnalysisResponse",
        "GoalsResponse",
    ):
        assert f"export interface {type_name}" in src or (
            f"export type {type_name}" in src
        ), f"response type {type_name} not declared"


def test_nutrient_type_matches_backend_fields():
    """The Nutrient type carries the backend's code/name/amount/unit fields."""
    src = API.read_text()
    start = src.index("interface Nutrient")
    nutrient = src[start : src.index("}", start)]
    for field in ("code", "name", "amount", "unit"):
        assert field in nutrient, f"Nutrient field {field} missing"
