"""Deploy artifacts are present and consistent."""

from pathlib import Path


def _read(rel: str) -> str:
    return Path(rel).read_text()


def test_dockerfile_serves_the_app_on_8080() -> None:
    dockerfile = _read("Dockerfile")
    assert "python:3.12" in dockerfile
    assert "dietrace.web.app:app" in dockerfile
    assert "8080" in dockerfile


def test_frontend_dockerfile_builds_and_serves_on_port_env() -> None:
    dockerfile = _read("frontend/Dockerfile")
    # Node base image to build the Next app.
    assert "node:" in dockerfile
    # Build then start the Next app (the npm build + start scripts).
    assert "npm run build" in dockerfile
    assert '"start"' in dockerfile or "npm run start" in dockerfile
    # Cloud Run injects PORT; the container must honour it.
    assert "PORT" in dockerfile


def test_ci_runs_ruff_and_pytest_on_prs() -> None:
    ci = _read(".github/workflows/ci.yml")
    assert "pull_request" in ci
    assert "uv sync" in ci
    assert "ruff check" in ci
    assert "pytest" in ci


def test_terraform_defines_cloud_run_registry_and_gemini3() -> None:
    tf = _read("terraform/main.tf")
    assert "google_cloud_run_v2_service" in tf
    assert "google_artifact_registry_repository" in tf
    # Gemini 3 model + the global serving location must be the defaults.
    assert "gemini-3.1-pro-preview" in tf
    assert 'default     = "global"' in tf
    # Scale-to-zero to conserve the GCP credit budget.
    assert "min_instance_count = 0" in tf
