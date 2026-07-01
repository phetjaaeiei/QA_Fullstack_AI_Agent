import pytest
from app.mcp_clients.openapi_client import OpenAPIClient

SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Sample API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "summary": "List users",
                "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer"}}],
                "responses": {"200": {"description": "OK"}}
            },
            "post": {
                "summary": "Create user",
                "requestBody": {
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {"email": {"type": "string"}, "password": {"type": "string"}},
                        "required": ["email", "password"]
                    }}}
                },
                "responses": {"201": {"description": "Created"}}
            }
        }
    }
}


def test_list_endpoints_returns_all_methods():
    client = OpenAPIClient()
    endpoints = client.list_endpoints(SAMPLE_SPEC)
    assert len(endpoints) == 2
    methods = {e["method"] for e in endpoints}
    assert "GET" in methods
    assert "POST" in methods


def test_get_endpoint_schema_returns_request_body():
    client = OpenAPIClient()
    schema = client.get_endpoint_schema(SAMPLE_SPEC, "/users", "POST")
    assert schema["request_body"]["required"] == ["email", "password"]


def test_list_endpoints_includes_path_and_summary():
    client = OpenAPIClient()
    endpoints = client.list_endpoints(SAMPLE_SPEC)
    get_ep = next(e for e in endpoints if e["method"] == "GET")
    assert get_ep["path"] == "/users"
    assert get_ep["summary"] == "List users"
