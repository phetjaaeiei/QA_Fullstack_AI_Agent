import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.mcp_clients.github_client import GitHubClient


MOCK_RUN_RESPONSE = {
    "id": 123456,
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/acme/repo/actions/runs/123456",
}

MOCK_JOBS_RESPONSE = {
    "jobs": [
        {
            "name": "e2e-tests",
            "conclusion": "failure",
            "steps": [
                {"name": "Run Playwright tests", "conclusion": "failure"},
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_get_test_results_returns_normalized_dict():
    client = GitHubClient()
    run_response = MagicMock()
    run_response.json.return_value = MOCK_RUN_RESPONSE
    run_response.raise_for_status = lambda: None

    jobs_response = MagicMock()
    jobs_response.json.return_value = MOCK_JOBS_RESPONSE
    jobs_response.raise_for_status = lambda: None

    with patch.object(client._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [run_response, jobs_response]

        result = await client.get_test_results("acme/repo", "123456")

    assert result["run_id"] == "123456"
    assert result["conclusion"] == "failure"
    assert result["jobs"][0]["name"] == "e2e-tests"
    assert result["jobs"][0]["steps"][0]["conclusion"] == "failure"


@pytest.mark.asyncio
async def test_list_open_prs_returns_list():
    client = GitHubClient()
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"number": 42, "title": "Add login flow", "html_url": "https://github.com/acme/repo/pull/42"}
    ]
    mock_response.raise_for_status = lambda: None

    with patch.object(client._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        prs = await client.list_open_prs("acme/repo")

    assert len(prs) == 1
    assert prs[0]["number"] == 42


@pytest.mark.asyncio
async def test_get_pr_diff_returns_raw_diff_text():
    client = GitHubClient()
    mock_response = MagicMock()
    mock_response.text = "diff --git a/file.py b/file.py\n+added line"
    mock_response.raise_for_status = lambda: None

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
        diff = await client.get_pr_diff("acme/repo", 42)

    assert "added line" in diff
