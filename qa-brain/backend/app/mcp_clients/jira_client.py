import httpx
from base64 import b64encode
from app.config import settings


class JiraClient:
    def __init__(self):
        credentials = b64encode(
            f"{settings.jira_email}:{settings.jira_api_token}".encode()
        ).decode()
        self._http = httpx.AsyncClient(
            base_url=settings.jira_base_url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _extract_text(self, description) -> str:
        if description is None:
            return ""
        if isinstance(description, str):
            return description
        texts = []
        for block in description.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    texts.append(inline.get("text", ""))
        return " ".join(texts)

    def _extract_sprint_id(self, fields: dict):
        sprints = fields.get("customfield_10020", [])
        if sprints:
            return str(sprints[-1].get("id", ""))
        return None

    def _normalize_story(self, raw: dict) -> dict:
        fields = raw.get("fields", {})
        return {
            "jira_id": raw.get("key"),
            "title": fields.get("summary", ""),
            "description": self._extract_text(fields.get("description")),
            "acceptance_criteria": fields.get("acceptance_criteria") or self._extract_text(
                fields.get("customfield_10016")
            ),
            "status": fields.get("status", {}).get("name", ""),
            "sprint_id": self._extract_sprint_id(fields),
        }

    async def get_story(self, story_id: str) -> dict:
        response = await self._http.get(f"/rest/api/3/issue/{story_id}")
        response.raise_for_status()
        return self._normalize_story(response.json())

    async def search_stories(self, jql: str, max_results: int = 50) -> list:
        response = await self._http.post(
            "/rest/api/3/search/jql",
            json={
                "jql": jql,
                "maxResults": max_results,
                "fields": [
                    "summary", "description", "status", "acceptance_criteria",
                    "customfield_10016", "customfield_10020"
                ],
            },
        )
        response.raise_for_status()
        issues = response.json().get("issues", [])
        return [self._normalize_story(issue) for issue in issues]

    async def get_sprint_stories(self, sprint_id: str) -> list:
        return await self.search_stories(f"sprint = {sprint_id} ORDER BY created ASC")

    async def close(self):
        await self._http.aclose()
