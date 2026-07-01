import httpx
from app.config import settings


class GitHubClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        response = await self._http.get(
            f"/repos/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        response.raise_for_status()
        return response.text

    async def get_test_results(self, repo: str, run_id: str) -> dict:
        run_response = await self._http.get(f"/repos/{repo}/actions/runs/{run_id}")
        run_response.raise_for_status()
        run = run_response.json()

        jobs_response = await self._http.get(f"/repos/{repo}/actions/runs/{run_id}/jobs")
        jobs_response.raise_for_status()
        jobs = jobs_response.json().get("jobs", [])

        return {
            "run_id": str(run.get("id")),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
            "jobs": [
                {
                    "name": job.get("name"),
                    "conclusion": job.get("conclusion"),
                    "steps": [
                        {"name": s.get("name"), "conclusion": s.get("conclusion")}
                        for s in job.get("steps", [])
                    ],
                }
                for job in jobs
            ],
        }

    async def list_open_prs(self, repo: str) -> list:
        response = await self._http.get(f"/repos/{repo}/pulls", params={"state": "open"})
        response.raise_for_status()
        return [
            {"number": pr["number"], "title": pr["title"], "html_url": pr["html_url"]}
            for pr in response.json()
        ]

    async def close(self):
        await self._http.aclose()
