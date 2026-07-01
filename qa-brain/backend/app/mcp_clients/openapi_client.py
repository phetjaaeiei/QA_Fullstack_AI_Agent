import httpx
import yaml
import json
from pathlib import Path


class OpenAPIClient:
    async def parse_spec(self, url_or_path: str) -> dict:
        if url_or_path.startswith("http"):
            async with httpx.AsyncClient() as client:
                response = await client.get(url_or_path)
                response.raise_for_status()
                content = response.text
        else:
            content = Path(url_or_path).read_text()

        if url_or_path.endswith(".yaml") or url_or_path.endswith(".yml"):
            return yaml.safe_load(content)
        return json.loads(content)

    def list_endpoints(self, spec: dict) -> list[dict]:
        endpoints = []
        for path, path_item in spec.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    endpoints.append({
                        "path": path,
                        "method": method.upper(),
                        "summary": operation.get("summary", ""),
                        "description": operation.get("description", ""),
                        "parameters": operation.get("parameters", []),
                        "responses": list(operation.get("responses", {}).keys()),
                    })
        return endpoints

    def get_endpoint_schema(self, spec: dict, path: str, method: str) -> dict:
        operation = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
        schema = {
            "path": path,
            "method": method.upper(),
            "summary": operation.get("summary", ""),
            "parameters": operation.get("parameters", []),
            "responses": operation.get("responses", {}),
            "request_body": None,
        }
        request_body = operation.get("requestBody", {})
        content = request_body.get("content", {})
        if "application/json" in content:
            schema["request_body"] = content["application/json"].get("schema", {})
        return schema
