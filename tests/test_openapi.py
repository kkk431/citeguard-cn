"""The published OpenAPI schema is part of the integration surface.

If an endpoint disappears or the version drifts, external tools (the Python
client, the browser extension, Word task pane) silently break.  This test
keeps the contract honest without snapshotting the whole schema.
"""
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)

PUBLIC_PATHS = [
    "/api/health",
    "/api/analyze",
    "/api/jobs/{job_id}",
    "/api/jobs/{job_id}/events",
    "/api/report/{job_id}",
    "/api/report/{job_id}/export",
    "/api/report/{job_id}/page/{page}",
    "/api/report/{job_id}/replacement",
    "/api/report/{job_id}/triage",
    "/api/support/check",
    "/api/support/batch",
    "/api/library/suggest",
    "/api/aggregate",
]


def test_openapi_lists_public_endpoints():
    spec = app.openapi()
    paths = spec.get("paths", {})
    missing = [path for path in PUBLIC_PATHS if path not in paths]
    assert not missing, f"missing from OpenAPI: {missing}"


def test_openapi_version_matches_app():
    spec = app.openapi()
    assert spec["info"]["version"] == app.version


def test_openapi_documents_support_check_body():
    spec = app.openapi()
    body = spec["paths"]["/api/support/check"]["post"]
    assert "requestBody" in body
    content = body["requestBody"]["content"]
    assert "application/json" in content and "schema" in content["application/json"]
