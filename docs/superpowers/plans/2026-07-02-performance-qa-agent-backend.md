# Performance QA Agent — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for the Performance QA Agent — 8 tools (workload modeling, performance risk analysis, k6/JMeter script generation, load-test result analysis, bottleneck identification, SLA/SLO definition, performance defect creation as real Jira tickets, and capacity recommendation), a new `performance_findings` table with persistence + REST read endpoint, and orchestrator routing — driven entirely through the existing chat interface.

**Architecture:** `PerformanceQAAgent` mirrors `SecurityQAAgent`'s anatomy exactly: a stateless class whose async methods check `self._mock` first (returning `[MOCK]`-labeled fixtures) or call Claude (`claude-sonnet-4-6`) with data fetched via the existing `JiraClient`/`OpenAPIClient`. The orchestrator's regex/keyword `_classify_intent()` gains 8 rules placed before ManualQA's generic `analyze`/`risk` rule; `process()` dispatches each action through the established 3-event stream (`agent_start` → `agent_complete` → `orchestrator_done`). Only `analyze_perf_risk` output is persisted (to `performance_findings` via a `chat.py` helper mirroring `_persist_owasp_mapping`); the other 7 outputs are one-shot chat artifacts per design spec §5.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, Alembic, anthropic SDK, pytest + pytest-asyncio

## Global Constraints
- Model id: `claude-sonnet-4-6`
- MOCK_MODE convention: every public agent method checks `self._mock` first; fixtures labeled `[MOCK]`; real story titles fetched best-effort in mock mode
- `write_perf_defect` must NEVER call `JiraClient.create_issue` when mock (test with assert_not_called)
- No new dependencies, no new env vars
- Run tests with `.venv/bin/python -m pytest` from `qa-brain/backend`
- Baseline: 70 tests pass before Task 1; every task ends with the full suite green
- Commit after every task
- Design spec (source of truth for tool names, return shapes, routing keywords, schema): `docs/superpowers/specs/2026-07-02-performance-qa-agent-design.md`
---

### Task 1: PerformanceFinding model & migration

**Files:**
- Create: `qa-brain/backend/app/models/performance_finding.py`
- Create: `qa-brain/backend/alembic/versions/f4a7c9d31b20_add_performance_findings_table.py`
- Modify: `qa-brain/backend/app/models/__init__.py` (add import + `__all__` entry)
- Modify: `qa-brain/backend/tests/conftest.py` (cleanup block, lines 40–47: add `DELETE FROM performance_findings` before the `stories` delete)
- Test: `qa-brain/backend/tests/test_performance_finding_model.py` (new)

**Interfaces:**
- Consumes: `Base` from `app.models.base`, existing `stories.id` FK target, `db_session`/`test_story` fixtures from `tests/conftest.py`
- Produces: `PerformanceFinding` model importable as `from app.models import PerformanceFinding` with columns `id` (uuid4 str PK), `story_id` (FK → `stories.id`, indexed, not null), `risk_area` (String, not null), `severity` (SAEnum `critical|high|medium|low`, name `perf_severity`, not null), `description` (Text, nullable), `created_at` (DateTime, default `datetime.utcnow`). Tasks 7 and 8 depend on this model.

- [ ] **Step 1: Write the failing test** — create `qa-brain/backend/tests/test_performance_finding_model.py` with exactly:

```python
import pytest
from sqlalchemy import select
from app.models import PerformanceFinding


@pytest.mark.asyncio
async def test_performance_finding_roundtrip(db_session, test_story):
    finding = PerformanceFinding(
        story_id=test_story.id,
        risk_area="database",
        severity="high",
        description="Unindexed hot query path degrades under concurrent load",
    )
    db_session.add(finding)
    await db_session.commit()

    result = await db_session.execute(
        select(PerformanceFinding).where(PerformanceFinding.story_id == test_story.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].id is not None
    assert rows[0].risk_area == "database"
    assert rows[0].severity == "high"
    assert rows[0].description == "Unindexed hot query path degrades under concurrent load"
    assert rows[0].created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_finding_model.py -q
```

Expected failure: collection error — `ImportError: cannot import name 'PerformanceFinding' from 'app.models'`.

- [ ] **Step 3: Write minimal implementation**

3a. Create `qa-brain/backend/app/models/performance_finding.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from app.models.base import Base


class PerformanceFinding(Base):
    __tablename__ = "performance_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"), nullable=False, index=True)
    risk_area = Column(String, nullable=False)
    severity = Column(SAEnum("critical", "high", "medium", "low", name="perf_severity"), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

3b. Replace the full contents of `qa-brain/backend/app/models/__init__.py` with:

```python
from app.models.base import Base
from app.models.user import User
from app.models.project import Project
from app.models.story import Story
from app.models.test_case import TestCase
from app.models.automation_script import AutomationScript
from app.models.security_finding import SecurityFinding
from app.models.performance_finding import PerformanceFinding
from app.models.agent_session import AgentSession

__all__ = ["Base", "User", "Project", "Story", "TestCase", "AutomationScript", "SecurityFinding", "PerformanceFinding", "AgentSession"]
```

3c. In `qa-brain/backend/tests/conftest.py`, the `db_session` fixture teardown (lines 40–47) currently deletes from `automation_scripts`, `security_findings`, `test_cases`, `stories`, `projects`, `users`. Add `performance_findings` right after the `security_findings` line (it FK-references `stories`, so it must be deleted before the `stories` delete). The block becomes:

```python
        from sqlalchemy import text
        async with session_factory() as cleanup:
            await cleanup.execute(text("DELETE FROM automation_scripts"))
            await cleanup.execute(text("DELETE FROM security_findings"))
            await cleanup.execute(text("DELETE FROM performance_findings"))
            await cleanup.execute(text("DELETE FROM test_cases"))
            await cleanup.execute(text("DELETE FROM stories"))
            await cleanup.execute(text("DELETE FROM projects"))
            await cleanup.execute(text("DELETE FROM users"))
            await cleanup.commit()
```

3d. Create `qa-brain/backend/alembic/versions/f4a7c9d31b20_add_performance_findings_table.py` (hand-written for a deterministic revision id; `down_revision` MUST be `'03fdf5c62169'`, the current head):

```python
"""add_performance_findings_table

Revision ID: f4a7c9d31b20
Revises: 03fdf5c62169
Create Date: 2026-07-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a7c9d31b20'
down_revision: Union[str, None] = '03fdf5c62169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('performance_findings',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('story_id', sa.String(), nullable=False),
    sa.Column('risk_area', sa.String(), nullable=False),
    sa.Column('severity', sa.Enum('critical', 'high', 'medium', 'low', name='perf_severity'), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_performance_findings_story_id'), 'performance_findings', ['story_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_performance_findings_story_id'), table_name='performance_findings')
    op.drop_table('performance_findings')
```

(Downgrade intentionally does not drop the `perf_severity` enum type — exact parity with the `security_findings` migration `03fdf5c62169`.)

3e. Apply the migration to the dev database (requires the repo's docker postgres running):

```bash
cd qa-brain/backend
.venv/bin/alembic upgrade head
```

Expected output: `Running upgrade 03fdf5c62169 -> f4a7c9d31b20, add_performance_findings_table`. Verify:

```bash
docker exec qa-brain-postgres-1 psql -U qa_brain -d qa_brain -c "\d performance_findings"
```

Expected: columns `id`, `story_id`, `risk_area`, `severity`, `description`, `created_at` and index `ix_performance_findings_story_id`. (The test suite itself uses `Base.metadata.create_all` against the test DB on port 5433, so tests pass independently of this step.)

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_finding_model.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `71 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/models/performance_finding.py app/models/__init__.py tests/conftest.py tests/test_performance_finding_model.py alembic/versions/f4a7c9d31b20_add_performance_findings_table.py
git commit -m "feat: add PerformanceFinding model and migration"
```

---

### Task 2: PerformanceQAAgent skeleton + build_workload_model + analyze_perf_risk

**Files:**
- Create: `qa-brain/backend/app/agents/performance_qa.py`
- Test: `qa-brain/backend/tests/test_performance_qa_agent.py` (new)

**Interfaces:**
- Consumes: `settings` from `app.config` (`anthropic_api_key`, `mock_mode`), `JiraClient` from `app.mcp_clients.jira_client` (`get_story(story_id) -> dict` with keys `jira_id`, `title`, `description`, `acceptance_criteria`, `status`), `OpenAPIClient` from `app.mcp_clients.openapi_client`
- Produces: `PerformanceQAAgent` class with `async def build_workload_model(self, story_id: str) -> dict` returning `{"story_id", "concurrent_users", "ramp_up", "duration", "scenarios": [{"name", "weight_percent", "description"}]}` and `async def analyze_perf_risk(self, story_id: str) -> list` returning `[{"risk_area", "severity": "critical|high|medium|low", "description"}]`. Also module-level `SYSTEM_PROMPT`, `_parse_json`, and `self._client` / `self._jira` / `self._openapi` / `self._model = "claude-sonnet-4-6"` / `self._mock` attributes that Tasks 3–5 extend and Task 6 consumes.

- [ ] **Step 1: Write the failing test** — create `qa-brain/backend/tests/test_performance_qa_agent.py` with exactly:

```python
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.performance_qa import PerformanceQAAgent

MOCK_STORY = {
    "jira_id": "SCRUM-400",
    "title": "Customer can search the product catalog",
    "description": "As a customer I want to search products by keyword so I can find items quickly",
    "acceptance_criteria": "Given a keyword, when I search, results return within 2 seconds",
    "status": "In Progress",
}

MOCK_WORKLOAD_MODEL = {
    "story_id": "SCRUM-400",
    "concurrent_users": 500,
    "ramp_up": "0 to 500 users over 10 minutes",
    "duration": "45m",
    "scenarios": [
        {"name": "Keyword search", "weight_percent": 70, "description": "Users search with common keywords"},
        {"name": "Filtered browse", "weight_percent": 30, "description": "Users refine results with filters"},
    ],
}

MOCK_PERF_RISKS = [
    {"risk_area": "database", "severity": "high", "description": "LIKE '%keyword%' scan on the products table under concurrency"},
    {"risk_area": "api", "severity": "medium", "description": "No pagination on the search results endpoint"},
]


@pytest.mark.asyncio
async def test_build_workload_model_returns_model():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_WORKLOAD_MODEL))]
            )
            result = await agent.build_workload_model("SCRUM-400")

    assert result["story_id"] == "SCRUM-400"
    assert result["concurrent_users"] == 500
    assert result["duration"] == "45m"
    assert len(result["scenarios"]) == 2
    assert result["scenarios"][0]["weight_percent"] == 70


@pytest.mark.asyncio
async def test_build_workload_model_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.build_workload_model("SCRUM-400")

    assert result["story_id"] == "SCRUM-400"
    assert result["ramp_up"].startswith("[MOCK]")
    assert len(result["scenarios"]) >= 1
    assert result["scenarios"][0]["name"].startswith("[MOCK]")
    assert "Customer can search the product catalog" in result["scenarios"][0]["name"]


@pytest.mark.asyncio
async def test_analyze_perf_risk_returns_list():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_PERF_RISKS))]
            )
            result = await agent.analyze_perf_risk("SCRUM-400")

    assert len(result) == 2
    assert result[0]["risk_area"] == "database"
    assert result[0]["severity"] == "high"
    assert "description" in result[0]


@pytest.mark.asyncio
async def test_analyze_perf_risk_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.analyze_perf_risk("SCRUM-400")

    assert len(result) >= 1
    assert result[0]["description"].startswith("[MOCK]")
    assert result[0]["severity"] in ("critical", "high", "medium", "low")
    assert "Customer can search the product catalog" in result[0]["description"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected failure: collection error — `ModuleNotFoundError: No module named 'app.agents.performance_qa'`.

- [ ] **Step 3: Write minimal implementation** — create `qa-brain/backend/app/agents/performance_qa.py` with exactly:

```python
import json
import re as _re
import anthropic
from app.config import settings
from app.mcp_clients.jira_client import JiraClient
from app.mcp_clients.openapi_client import OpenAPIClient


def _parse_json(text: str):
    text = text.strip()
    text = _re.sub(r"^```(?:json)?\s*", "", text)
    text = _re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


SYSTEM_PROMPT = """You are an expert Performance QA Engineer with deep expertise in performance engineering.

Your expertise:
- Load modeling: workload profiles, concurrency estimation, ramp-up design, scenario weighting
- APM analysis: latency percentiles, throughput, error rates, trace-span interpretation
- Bottleneck diagnosis: isolating issues to the app, database, API, or infrastructure layer
- Infrastructure sizing: capacity planning, headroom estimation, scaling recommendations
- Load-test tooling: k6 (JavaScript) and JMeter (JMX) script authoring

Rules:
- Always return valid JSON only — no markdown, no explanation outside JSON
- Be conservative and evidence-based: ground every conclusion in the provided data, never invent metrics
- Generated scripts must be syntactically valid for the requested framework
- Recommendations must be specific and actionable (not vague like "optimize the database")
"""


def _mock_workload_model(story_id: str, title: str = "") -> dict:
    label = f"{story_id} ({title})" if title else story_id
    return {
        "story_id": story_id,
        "concurrent_users": 200,
        "ramp_up": "[MOCK] Ramp from 0 to 200 users over 5 minutes, then hold at 200",
        "duration": "30m",
        "scenarios": [
            {"name": f"[MOCK] Browse flow for {label}", "weight_percent": 60, "description": "Users browse the feature's read-heavy pages"},
            {"name": f"[MOCK] Transaction flow for {label}", "weight_percent": 30, "description": "Users complete the primary write action"},
            {"name": f"[MOCK] Admin flow for {label}", "weight_percent": 10, "description": "Admin users run reports and exports"},
        ],
    }


def _mock_perf_risks(story_id: str, title: str = "") -> list:
    label = f"{story_id} ({title})" if title else story_id
    return [
        {"risk_area": "database", "severity": "high", "description": f"[MOCK] Hot query path for {label} has no index coverage and degrades under concurrent load"},
        {"risk_area": "api", "severity": "medium", "description": f"[MOCK] N+1 request pattern between the frontend and API for {label}"},
        {"risk_area": "infra", "severity": "low", "description": f"[MOCK] No autoscaling policy verified for the service behind {label}"},
    ]


class PerformanceQAAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._openapi = OpenAPIClient()
        self._model = "claude-sonnet-4-6"
        self._mock = settings.mock_mode

    async def _fetch_story_title(self, story_id: str) -> str:
        try:
            story = await self._jira.get_story(story_id)
            return story.get("title", "")
        except Exception:
            return ""

    async def build_workload_model(self, story_id: str) -> dict:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_workload_model(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Build a workload/load model for this story. Estimate realistic concurrency, ramp-up, duration, and weighted user scenarios for the described feature.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Return JSON only:
{{
  "story_id": "{story['jira_id']}",
  "concurrent_users": 0,
  "ramp_up": "how load ramps up over time",
  "duration": "total test duration, e.g. 30m",
  "scenarios": [
    {{"name": "scenario name", "weight_percent": 0, "description": "what these users do"}}
  ]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def analyze_perf_risk(self, story_id: str) -> list:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_perf_risks(story_id, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Identify performance risks in this story. Only flag genuine risks grounded in the described feature — do not manufacture risks that clearly do not apply.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Return a JSON array. Each risk must have all these fields:
[
  {{
    "risk_area": "freeform area, e.g. database|api|frontend|infra",
    "severity": "critical|high|medium|low",
    "description": "specific explanation of the risk and the load condition that triggers it"
  }}
]"""
            }]
        )

        return _parse_json(response.content[0].text)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `75 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/agents/performance_qa.py tests/test_performance_qa_agent.py
git commit -m "feat: add PerformanceQAAgent with build_workload_model and analyze_perf_risk"
```

---

### Task 3: generate_perf_script + analyze_perf_result

**Files:**
- Modify: `qa-brain/backend/app/agents/performance_qa.py` (append two mock-fixture constants + two fixture functions after `_mock_perf_risks`, and two methods inside `PerformanceQAAgent` after `analyze_perf_risk`)
- Test: `qa-brain/backend/tests/test_performance_qa_agent.py` (append)

**Interfaces:**
- Consumes: from the existing `qa-brain/backend/app/agents/performance_qa.py` — `self._mock`, `self._jira.get_story(story_id) -> dict` (keys `jira_id`, `title`, `description`, `acceptance_criteria`), `self._client.messages.create(...)`, `self._model`, `SYSTEM_PROMPT`, `_parse_json(text) -> dict|list`, and `self._fetch_story_title(story_id) -> str`
- Produces: `async def generate_perf_script(self, story_id: str, framework: str = "k6") -> dict` returning `{"framework": "k6|jmeter", "content", "notes"}` and `async def analyze_perf_result(self, result_text: str) -> dict` returning `{"verdict": "pass|fail|degraded", "root_cause", "bottleneck_location", "summary", "recommendations": [str]}`. Task 6 dispatches both.

- [ ] **Step 1: Write the failing test** — append to `qa-brain/backend/tests/test_performance_qa_agent.py`:

```python
MOCK_K6_SCRIPT_RESULT = {
    "framework": "k6",
    "content": "import http from 'k6/http';\nexport default function () {\n  http.get('https://example.com/api/search?q=shoes');\n}",
    "notes": "Replace the base URL and add auth headers before running",
}

MOCK_PERF_RESULT_ANALYSIS = {
    "verdict": "fail",
    "root_cause": "Database connection pool exhaustion at peak concurrency",
    "bottleneck_location": "db",
    "summary": "p95 latency breached 4s once concurrency passed 150 users while error rate stayed low",
    "recommendations": ["Increase the DB connection pool from 10 to match worker concurrency", "Re-run the test at 200 users after the change"],
}

SAMPLE_LOAD_TEST_RESULT = """
scenarios: 1, max VUs: 200
http_req_duration p(95)=4213ms p(99)=6890ms
http_req_failed rate=0.4%
db_conn_wait avg=3900ms
"""


@pytest.mark.asyncio
async def test_generate_perf_script_returns_k6_script():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY), \
             patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_K6_SCRIPT_RESULT))]
            )
            result = await agent.generate_perf_script("SCRUM-400")

    assert result["framework"] == "k6"
    assert "k6/http" in result["content"]
    assert "notes" in result


@pytest.mark.asyncio
async def test_generate_perf_script_mock_mode_returns_k6_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.generate_perf_script("SCRUM-400")

    assert result["framework"] == "k6"
    assert "// [MOCK]" in result["content"]
    assert "k6/http" in result["content"]
    assert result["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_generate_perf_script_mock_mode_returns_jmeter_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.generate_perf_script("SCRUM-400", framework="jmeter")

    assert result["framework"] == "jmeter"
    assert "[MOCK]" in result["content"]
    assert "jmeterTestPlan" in result["content"]
    assert result["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_analyze_perf_result_returns_analysis():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_PERF_RESULT_ANALYSIS))]
            )
            result = await agent.analyze_perf_result(SAMPLE_LOAD_TEST_RESULT)

    assert result["verdict"] == "fail"
    assert result["bottleneck_location"] == "db"
    assert "root_cause" in result
    assert "summary" in result
    assert len(result["recommendations"]) == 2


@pytest.mark.asyncio
async def test_analyze_perf_result_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        result = await agent.analyze_perf_result(SAMPLE_LOAD_TEST_RESULT)

    assert result["verdict"] in ("pass", "fail", "degraded")
    assert result["root_cause"].startswith("[MOCK]")
    assert result["summary"].startswith("[MOCK]")
    assert len(result["recommendations"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `5 failed, 4 passed` — the 5 new tests fail with `AttributeError: 'PerformanceQAAgent' object has no attribute 'generate_perf_script'` / `'analyze_perf_result'`.

- [ ] **Step 3: Write minimal implementation**

3a. In `qa-brain/backend/app/agents/performance_qa.py`, add these module-level fixtures immediately after the `_mock_perf_risks` function (before `class PerformanceQAAgent`):

```python
_MOCK_K6_SCRIPT = """// [MOCK] k6 load test script — replace BASE_URL before running
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '5m', target: 200 },
    { duration: '20m', target: 200 },
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = 'https://example.com';

export default function () {
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
"""

_MOCK_JMETER_SCRIPT = """<?xml version="1.0" encoding="UTF-8"?>
<!-- [MOCK] JMeter test plan - replace the target host before running -->
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="[MOCK] Load Test Plan"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Load Users">
        <intProp name="ThreadGroup.num_threads">200</intProp>
        <intProp name="ThreadGroup.ramp_time">300</intProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="GET /api/health">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api/health</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
        </HTTPSamplerProxy>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


def _mock_perf_script(story_id: str, framework: str, title: str = "") -> dict:
    label = f"{story_id} ({title})" if title else story_id
    content = _MOCK_JMETER_SCRIPT if framework == "jmeter" else _MOCK_K6_SCRIPT
    return {
        "framework": framework,
        "content": content,
        "notes": f"[MOCK] Baseline {framework} script for {label} — adjust the target URL, thresholds, and auth before running",
    }


def _mock_perf_result_analysis(result_text: str) -> dict:
    return {
        "verdict": "degraded",
        "root_cause": f"[MOCK] Latency degradation inferred from pasted results: {result_text.strip()[:60]}",
        "bottleneck_location": "db",
        "summary": "[MOCK] p95 latency exceeds the target under peak load while the error rate stays low",
        "recommendations": [
            "[MOCK] Add an index on the hot query path",
            "[MOCK] Re-run the test after enabling connection pooling",
        ],
    }
```

3b. Add these two methods inside `PerformanceQAAgent`, immediately after `analyze_perf_risk`:

```python
    async def generate_perf_script(self, story_id: str, framework: str = "k6") -> dict:
        if self._mock:
            title = await self._fetch_story_title(story_id)
            return _mock_perf_script(story_id, framework, title)

        story = await self._jira.get_story(story_id)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Generate a runnable {framework} load-test script for this story.

Story ID: {story['jira_id']}
Title: {story['title']}
Description: {story['description']}
Acceptance Criteria: {story.get('acceptance_criteria') or 'Not provided'}

Requirements:
- The script must be syntactically valid {framework} ({'JavaScript' if framework == 'k6' else 'JMX XML'})
- Include ramp-up stages, a hold period, and latency/error-rate thresholds
- Use a placeholder base URL (e.g. https://example.com) the user can replace

Return JSON only:
{{
  "framework": "{framework}",
  "content": "the full script source code, using \\n for newlines",
  "notes": "what to adjust before running (URLs, thresholds, test data)"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def analyze_perf_result(self, result_text: str) -> dict:
        if self._mock:
            return _mock_perf_result_analysis(result_text)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Analyze this load-test result / APM output. Determine the verdict, root cause, and bottleneck location. The format is tool-agnostic — infer field meaning from context.

Result data:
{result_text}

Return JSON only:
{{
  "verdict": "pass|fail|degraded",
  "root_cause": "the most likely root cause, grounded in the data",
  "bottleneck_location": "where the bottleneck sits, e.g. app|db|api|infra or a specific component",
  "summary": "short plain-language summary of what happened",
  "recommendations": ["specific next action"]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `80 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/agents/performance_qa.py tests/test_performance_qa_agent.py
git commit -m "feat: add generate_perf_script and analyze_perf_result to PerformanceQAAgent"
```

---

### Task 4: identify_bottleneck + define_sla_slo

**Files:**
- Modify: `qa-brain/backend/app/agents/performance_qa.py` (append two fixture functions after `_mock_perf_result_analysis`, and two methods + one private helper inside `PerformanceQAAgent` after `analyze_perf_result`)
- Test: `qa-brain/backend/tests/test_performance_qa_agent.py` (append)

**Interfaces:**
- Consumes: from the existing `qa-brain/backend/app/agents/performance_qa.py` — `self._mock`, `self._jira.get_story(story_id) -> dict` (keys `jira_id`, `title`, `description`), `self._client.messages.create(...)`, `self._model`, `SYSTEM_PROMPT`, `_parse_json(text)`
- Produces: `async def identify_bottleneck(self, trace_text: str) -> dict` returning `{"layer": "app|db|api|infra", "hypothesis", "evidence": [str], "next_steps": [str]}` and `async def define_sla_slo(self, requirements: str, story_id: str | None = None) -> dict` returning `{"slos": [{"metric", "target", "pass_criteria"}], "notes"}` (when `story_id` is given, the story title/description are fetched best-effort and appended to the requirements context). Task 6 dispatches both.

- [ ] **Step 1: Write the failing test** — append to `qa-brain/backend/tests/test_performance_qa_agent.py`:

```python
MOCK_BOTTLENECK = {
    "layer": "db",
    "hypothesis": "Connection pool exhaustion under peak concurrency",
    "evidence": ["db.acquire_conn spans grow from 2ms to 3900ms as VUs increase", "SQL execution time itself stays flat at ~180ms"],
    "next_steps": ["Increase the pool size to match worker concurrency", "Re-run the test at 300 users and re-capture traces"],
}

SAMPLE_APM_TRACE = """
span http.request /api/search 4200ms
  span db.acquire_conn 3900ms
  span db.query SELECT ... 180ms
  span serialize_response 45ms
"""

MOCK_SLA_SLO = {
    "slos": [
        {"metric": "p95 latency", "target": "< 400ms", "pass_criteria": "95% of search requests complete under 400ms at 500 concurrent users"},
        {"metric": "error rate", "target": "< 0.5%", "pass_criteria": "HTTP 5xx rate stays below 0.5% for the full test duration"},
    ],
    "notes": "Derived from the 2-second acceptance criterion with headroom for peak traffic",
}


@pytest.mark.asyncio
async def test_identify_bottleneck_returns_layer_hypothesis():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_BOTTLENECK))]
            )
            result = await agent.identify_bottleneck(SAMPLE_APM_TRACE)

    assert result["layer"] == "db"
    assert "hypothesis" in result
    assert len(result["evidence"]) == 2
    assert len(result["next_steps"]) == 2


@pytest.mark.asyncio
async def test_identify_bottleneck_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        result = await agent.identify_bottleneck(SAMPLE_APM_TRACE)

    assert result["layer"] in ("app", "db", "api", "infra")
    assert result["hypothesis"].startswith("[MOCK]")
    assert len(result["evidence"]) >= 1
    assert len(result["next_steps"]) >= 1


@pytest.mark.asyncio
async def test_define_sla_slo_returns_slos():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_SLA_SLO))]
            )
            result = await agent.define_sla_slo("Search must feel instant even during sale traffic")

    assert len(result["slos"]) == 2
    assert result["slos"][0]["metric"] == "p95 latency"
    assert result["slos"][0]["target"] == "< 400ms"
    assert "notes" in result


@pytest.mark.asyncio
async def test_define_sla_slo_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        result = await agent.define_sla_slo("Search must feel instant even during sale traffic")

    assert len(result["slos"]) >= 1
    assert "metric" in result["slos"][0]
    assert "target" in result["slos"][0]
    assert "pass_criteria" in result["slos"][0]
    assert result["notes"].startswith("[MOCK]")


@pytest.mark.asyncio
async def test_define_sla_slo_mock_mode_blends_story_context():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "get_story", new_callable=AsyncMock, return_value=MOCK_STORY):
            result = await agent.define_sla_slo("Search must feel fast", story_id="SCRUM-400")

    assert result["notes"].startswith("[MOCK]")
    assert "Customer can search the product catalog" in result["notes"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `5 failed, 9 passed` — the 5 new tests fail with `AttributeError: 'PerformanceQAAgent' object has no attribute 'identify_bottleneck'` / `'define_sla_slo'`.

- [ ] **Step 3: Write minimal implementation**

3a. In `qa-brain/backend/app/agents/performance_qa.py`, add these module-level fixtures immediately after `_mock_perf_result_analysis` (before `class PerformanceQAAgent`):

```python
def _mock_bottleneck(trace_text: str) -> dict:
    return {
        "layer": "db",
        "hypothesis": f"[MOCK] Database layer saturation inferred from trace: {trace_text.strip()[:60]}",
        "evidence": [
            "[MOCK] The longest spans concentrate in database access",
            "[MOCK] Connection acquisition time grows with load while query time stays flat",
        ],
        "next_steps": [
            "[MOCK] Capture a slow-query log during the next run",
            "[MOCK] Compare connection pool size against concurrent request count",
        ],
    }


def _mock_sla_slo(context: str) -> dict:
    return {
        "slos": [
            {"metric": "p95 latency", "target": "< 500ms", "pass_criteria": "95% of requests complete under 500ms during a 30m soak"},
            {"metric": "error rate", "target": "< 1%", "pass_criteria": "HTTP 5xx rate stays below 1% at peak load"},
            {"metric": "throughput", "target": ">= 100 req/s", "pass_criteria": "Sustained throughput of at least 100 req/s at target concurrency"},
        ],
        "notes": f"[MOCK] SLA/SLO draft derived from: {context[:120]}",
    }
```

3b. Add these methods inside `PerformanceQAAgent`, immediately after `analyze_perf_result`:

```python
    async def identify_bottleneck(self, trace_text: str) -> dict:
        if self._mock:
            return _mock_bottleneck(trace_text)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Identify the bottleneck layer from this APM trace data. Pick exactly one layer and justify it with evidence from the trace.

Trace data:
{trace_text}

Return JSON only:
{{
  "layer": "app|db|api|infra",
  "hypothesis": "what is most likely saturating and why",
  "evidence": ["specific observation from the trace supporting the hypothesis"],
  "next_steps": ["specific diagnostic or fix action to take next"]
}}"""
            }]
        )

        return _parse_json(response.content[0].text)

    async def _build_sla_context(self, requirements: str, story_id: str | None) -> str:
        if not story_id:
            return requirements
        try:
            story = await self._jira.get_story(story_id)
            return (
                f"{requirements}\n\n"
                f"Related story {story_id}: {story.get('title', '')}\n"
                f"{story.get('description', '')}"
            )
        except Exception:
            return requirements

    async def define_sla_slo(self, requirements: str, story_id: str | None = None) -> dict:
        context = await self._build_sla_context(requirements, story_id)

        if self._mock:
            return _mock_sla_slo(context)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Define SLA/SLO thresholds with measurable pass/fail criteria for these business requirements.

Requirements:
{context}

Return JSON only:
{{
  "slos": [
    {{"metric": "the metric name, e.g. p95 latency", "target": "the threshold, e.g. < 500ms", "pass_criteria": "measurable pass/fail statement for a load test"}}
  ],
  "notes": "assumptions made and what to confirm with stakeholders"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `14 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `85 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/agents/performance_qa.py tests/test_performance_qa_agent.py
git commit -m "feat: add identify_bottleneck and define_sla_slo to PerformanceQAAgent"
```

---

### Task 5: write_perf_defect + recommend_capacity

**Files:**
- Modify: `qa-brain/backend/app/agents/performance_qa.py` (append two fixture functions after `_mock_sla_slo`, and two methods inside `PerformanceQAAgent` after `define_sla_slo`)
- Test: `qa-brain/backend/tests/test_performance_qa_agent.py` (append)

**Interfaces:**
- Consumes: from the existing `qa-brain/backend/app/agents/performance_qa.py` — `self._mock`, `self._client.messages.create(...)`, `self._model`, `SYSTEM_PROMPT`, `_parse_json(text)`; and the EXACT existing Jira write method `JiraClient.create_issue(self, project_key: str, summary: str, description: str, issue_type: str = "Bug", labels: list = None) -> dict` returning `{"jira_id": str, "url": str}` (defined in `qa-brain/backend/app/mcp_clients/jira_client.py`, lines 76–97)
- Produces: `async def write_perf_defect(self, finding_text: str) -> dict` returning `{"report", "impact", "evidence", "jira_id", "url"}` (mock: `jira_id="[MOCK]"`, `url="[MOCK]"`, and `create_issue` is NEVER called) and `async def recommend_capacity(self, results_text: str) -> dict` returning `{"current_assessment", "recommendations": [{"component", "sizing", "rationale"}], "estimated_headroom"}`. Task 6 dispatches both.

- [ ] **Step 1: Write the failing test** — append to `qa-brain/backend/tests/test_performance_qa_agent.py`:

```python
MOCK_PERF_DEFECT_ANALYSIS = {
    "report": "Search API p95 latency exceeds 4s at 150 concurrent users",
    "impact": "Search becomes unusable during peak traffic, blocking product discovery",
    "evidence": "k6 run 2026-07-02: p95 4.2s vs 500ms target at 150 VUs; db.acquire_conn dominates traces",
}

MOCK_PERF_CREATE_ISSUE_RESULT = {"jira_id": "SCRUM-777", "url": "https://example.atlassian.net/browse/SCRUM-777"}

MOCK_CAPACITY_PLAN = {
    "current_assessment": "App tier saturates CPU at 150 users; database has headroom",
    "recommendations": [
        {"component": "app servers", "sizing": "Scale from 2 to 4 instances (2 vCPU / 4 GB each)", "rationale": "CPU-bound at 70% of target load"},
        {"component": "database", "sizing": "Keep current size, add one read replica", "rationale": "Read-heavy workload dominates the profile"},
    ],
    "estimated_headroom": "~35% at projected peak after scaling",
}

SAMPLE_CAPACITY_INPUT = "CPU 92% at 150 VUs, p95 1.8s, DB CPU 40%, memory stable at 60%"


@pytest.mark.asyncio
async def test_write_perf_defect_creates_real_jira_ticket_when_not_mock():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create, \
             patch.object(agent._jira, "create_issue", new_callable=AsyncMock, return_value=MOCK_PERF_CREATE_ISSUE_RESULT) as mock_create_issue:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_PERF_DEFECT_ANALYSIS))]
            )
            result = await agent.write_perf_defect(
                "p95 latency 4.2s at 150 VUs on /api/search, db connection pool wait dominates"
            )

    mock_create_issue.assert_called_once()
    _, kwargs = mock_create_issue.call_args
    assert kwargs["project_key"] == "SCRUM"
    assert kwargs["issue_type"] == "Bug"
    assert kwargs["summary"] == MOCK_PERF_DEFECT_ANALYSIS["report"]
    assert kwargs["labels"] == ["performance"]
    assert result["jira_id"] == "SCRUM-777"
    assert result["url"] == "https://example.atlassian.net/browse/SCRUM-777"
    assert "report" in result
    assert "impact" in result
    assert "evidence" in result


@pytest.mark.asyncio
async def test_write_perf_defect_mock_mode_does_not_call_create_issue():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        with patch.object(agent._jira, "create_issue", new_callable=AsyncMock) as mock_create_issue:
            result = await agent.write_perf_defect(
                "p95 latency 4.2s at 150 VUs on /api/search, db connection pool wait dominates"
            )

    mock_create_issue.assert_not_called()
    assert result["jira_id"] == "[MOCK]"
    assert result["url"] == "[MOCK]"
    assert result["report"].startswith("[MOCK]")
    assert "impact" in result
    assert "evidence" in result


@pytest.mark.asyncio
async def test_recommend_capacity_returns_plan():
    with patch("app.agents.performance_qa.settings.mock_mode", False):
        agent = PerformanceQAAgent()
        with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(
                content=[MagicMock(text=json.dumps(MOCK_CAPACITY_PLAN))]
            )
            result = await agent.recommend_capacity(SAMPLE_CAPACITY_INPUT)

    assert "current_assessment" in result
    assert len(result["recommendations"]) == 2
    assert result["recommendations"][0]["component"] == "app servers"
    assert "estimated_headroom" in result


@pytest.mark.asyncio
async def test_recommend_capacity_mock_mode_returns_mock_fixture():
    with patch("app.agents.performance_qa.settings.mock_mode", True):
        agent = PerformanceQAAgent()
        result = await agent.recommend_capacity(SAMPLE_CAPACITY_INPUT)

    assert result["current_assessment"].startswith("[MOCK]")
    assert len(result["recommendations"]) >= 1
    assert "component" in result["recommendations"][0]
    assert "sizing" in result["recommendations"][0]
    assert "rationale" in result["recommendations"][0]
    assert result["estimated_headroom"].startswith("[MOCK]")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `4 failed, 14 passed` — the 4 new tests fail with `AttributeError: 'PerformanceQAAgent' object has no attribute 'write_perf_defect'` / `'recommend_capacity'`.

- [ ] **Step 3: Write minimal implementation**

3a. In `qa-brain/backend/app/agents/performance_qa.py`, add these module-level fixtures immediately after `_mock_sla_slo` (before `class PerformanceQAAgent`):

```python
def _mock_perf_defect(finding_text: str) -> dict:
    return {
        "report": f"[MOCK] Performance defect report for: {finding_text.strip()[:80]}",
        "impact": "[MOCK] Degraded response times for end users under peak load",
        "evidence": f"[MOCK] Evidence extracted from: {finding_text.strip()[:80]}",
        "jira_id": "[MOCK]",
        "url": "[MOCK]",
    }


def _mock_capacity_plan(results_text: str) -> dict:
    return {
        "current_assessment": f"[MOCK] Current capacity assessment based on: {results_text.strip()[:60]}",
        "recommendations": [
            {"component": "app servers", "sizing": "[MOCK] Scale from 2 to 4 instances (2 vCPU / 4 GB each)", "rationale": "[MOCK] CPU saturates before the target load is reached"},
            {"component": "database", "sizing": "[MOCK] Add one read replica", "rationale": "[MOCK] Read-heavy workload dominates the profile"},
        ],
        "estimated_headroom": "[MOCK] ~30% headroom at projected peak after the changes",
    }
```

3b. Add these two methods inside `PerformanceQAAgent`, immediately after `define_sla_slo`:

```python
    async def write_perf_defect(self, finding_text: str) -> dict:
        if self._mock:
            return _mock_perf_defect(finding_text)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Turn this performance finding into a structured defect report.

Finding:
{finding_text}

Return JSON only:
{{
  "report": "concise defect title/summary",
  "impact": "user-facing and business impact of this performance issue",
  "evidence": "the specific metrics/trace evidence demonstrating the issue"
}}"""
            }]
        )

        analysis = _parse_json(response.content[0].text)

        description = (
            f"Impact: {analysis['impact']}\n\n"
            f"Evidence: {analysis['evidence']}"
        )
        issue = await self._jira.create_issue(
            project_key="SCRUM",
            summary=analysis["report"],
            description=description,
            issue_type="Bug",
            labels=["performance"],
        )

        return {
            "report": analysis["report"],
            "impact": analysis["impact"],
            "evidence": analysis["evidence"],
            "jira_id": issue["jira_id"],
            "url": issue["url"],
        }

    async def recommend_capacity(self, results_text: str) -> dict:
        if self._mock:
            return _mock_capacity_plan(results_text)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Recommend infrastructure sizing based on these load-test results / load model. Ground every recommendation in the provided numbers.

Results / load model:
{results_text}

Return JSON only:
{{
  "current_assessment": "assessment of current capacity based on the data",
  "recommendations": [
    {{"component": "which part of the stack", "sizing": "concrete sizing change", "rationale": "why, grounded in the data"}}
  ],
  "estimated_headroom": "estimated headroom at projected peak after the changes"
}}"""
            }]
        )

        return _parse_json(response.content[0].text)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_qa_agent.py -q
```

Expected: `18 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `89 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/agents/performance_qa.py tests/test_performance_qa_agent.py
git commit -m "feat: add write_perf_defect and recommend_capacity to PerformanceQAAgent"
```

---

### Task 6: Orchestrator routing

**Files:**
- Modify: `qa-brain/backend/app/agents/orchestrator.py` — import (after line 5), `__init__` (after line 18), classifier rules (inserted between the `build_owasp_dashboard` rule ending at line 41 and the ManualQA generic `analyze/ambigui/missing/risk` rule at line 42), dispatch blocks (inserted after the `build_owasp_dashboard` elif block ending at line 230, before the final `else:` at line 232)
- Test: `qa-brain/backend/tests/test_orchestrator.py` (append)

**Interfaces:**
- Consumes: `PerformanceQAAgent` from `app.agents.performance_qa` with exactly these method signatures — `build_workload_model(story_id: str) -> dict`, `analyze_perf_risk(story_id: str) -> list`, `generate_perf_script(story_id: str, framework: str = "k6") -> dict`, `analyze_perf_result(result_text: str) -> dict`, `identify_bottleneck(trace_text: str) -> dict`, `define_sla_slo(requirements: str, story_id: str | None = None) -> dict`, `write_perf_defect(finding_text: str) -> dict`, `recommend_capacity(results_text: str) -> dict`; existing module regexes `STORY_ID_PATTERN`, `CODE_BLOCK_PATTERN`, and `re` (already imported at line 1)
- Produces: 8 new intent actions and `orchestrator_done` events with data keys exactly `workload_model` (+`story_id`), `perf_risks` (+`story_id`), `perf_script` (+`story_id`), `perf_result_analysis`, `bottleneck`, `sla_slo`, `perf_defect`, `capacity_plan`. Task 7 consumes the `perf_risks` + `story_id` event.

- [ ] **Step 1: Write the failing test** — append to `qa-brain/backend/tests/test_orchestrator.py`:

```python
# ---------------------------------------------------------------------------
# Performance QA routing
# ---------------------------------------------------------------------------

MOCK_WORKLOAD_MODEL = {
    "story_id": "SCRUM-10",
    "concurrent_users": 200,
    "ramp_up": "0 to 200 users over 5 minutes",
    "duration": "30m",
    "scenarios": [{"name": "Browse", "weight_percent": 100, "description": "d"}],
}

MOCK_BOTTLENECK_RESULT = {
    "layer": "db",
    "hypothesis": "Connection pool exhaustion",
    "evidence": ["pool wait grows with load"],
    "next_steps": ["increase pool size"],
}


def test_classify_build_workload_model():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("build a workload model for SCRUM-10")
    assert intent["action"] == "build_workload_model"
    assert intent["story_ids"] == ["SCRUM-10"]


def test_classify_analyze_perf_risk():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("analyze performance risk for SCRUM-10")
    assert intent["action"] == "analyze_perf_risk"
    assert intent["story_ids"] == ["SCRUM-10"]


def test_classify_generate_perf_script_defaults_to_k6():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("generate a load test script for SCRUM-10")
    assert intent["action"] == "generate_perf_script"
    assert intent["framework"] == "k6"
    assert intent["story_ids"] == ["SCRUM-10"]


def test_classify_generate_perf_script_jmeter():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("generate a jmeter script for SCRUM-10")
    assert intent["action"] == "generate_perf_script"
    assert intent["framework"] == "jmeter"


def test_classify_analyze_perf_result_extracts_code_block():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent(
        "analyze this load test result:\n```\np95=4200ms rate=0.4%\n```"
    )
    assert intent["action"] == "analyze_perf_result"
    assert intent["result_text"] == "p95=4200ms rate=0.4%"


def test_classify_identify_bottleneck_falls_back_to_raw_message():
    orchestrator = QAOrchestrator()
    message = "where is the bottleneck? p95 went from 200ms to 4s at 150 users"
    intent = orchestrator._classify_intent(message)
    assert intent["action"] == "identify_bottleneck"
    assert intent["trace_text"] == message


def test_classify_define_sla_slo_word_boundary():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("define sla for the checkout api")
    assert intent["action"] == "define_sla_slo"
    assert intent["requirements"] == "define sla for the checkout api"


def test_classify_write_perf_defect():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent(
        "write a performance defect for this finding:\n```\np95 4s on /checkout at 150 VUs\n```"
    )
    assert intent["action"] == "write_perf_defect"
    assert intent["finding_text"] == "p95 4s on /checkout at 150 VUs"


def test_classify_recommend_capacity():
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent(
        "recommend capacity for this service based on:\n```\nCPU 85% at 150 users\n```"
    )
    assert intent["action"] == "recommend_capacity"
    assert intent["results_text"] == "CPU 85% at 150 users"


def test_classify_performance_risk_does_not_route_to_manual_analyze():
    """Collision guard: 'performance risk' contains the generic ManualQA keyword
    'risk' — it must route to analyze_perf_risk, not analyze_story."""
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("performance risk for SCRUM-1")
    assert intent["action"] == "analyze_perf_risk"
    assert intent["action"] != "analyze_story"


def test_classify_translate_does_not_route_to_sla():
    """Collision guard: 'translate' contains the substring 'sla' — the word-boundary
    regex must NOT match it."""
    orchestrator = QAOrchestrator()
    intent = orchestrator._classify_intent("translate this story to Thai")
    assert intent["action"] != "define_sla_slo"
    assert intent["action"] == "unknown"


def test_classify_existing_agent_routing_unchanged():
    """Regression guard: one ManualQA, one AutomationQA, and one SecurityQA
    routing case must still classify exactly as before."""
    orchestrator = QAOrchestrator()
    assert orchestrator._classify_intent("analyze story PROJ-1 for ambiguities")["action"] == "analyze_story"
    assert orchestrator._classify_intent("generate playwright script for PROJ-1")["action"] == "generate_script_from_spec"
    assert orchestrator._classify_intent("map story to owasp for PROJ-1")["action"] == "map_story_to_owasp"


@pytest.mark.asyncio
async def test_process_builds_workload_model():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._performance_qa, "build_workload_model", new_callable=AsyncMock,
                       return_value=MOCK_WORKLOAD_MODEL):
        async for event in orchestrator.process(
            message="build a workload model for SCRUM-10",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    start_event = next(e for e in events if e["type"] == "agent_start")
    assert start_event["agent"] == "performance_qa"
    assert any(e["type"] == "agent_complete" for e in events)
    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["workload_model"]["concurrent_users"] == 200
    assert done_event["data"]["story_id"] == "SCRUM-10"


@pytest.mark.asyncio
async def test_process_identifies_bottleneck_from_pasted_trace():
    orchestrator = QAOrchestrator()
    events = []

    with patch.object(orchestrator._performance_qa, "identify_bottleneck", new_callable=AsyncMock,
                       return_value=MOCK_BOTTLENECK_RESULT) as mock_bottleneck:
        async for event in orchestrator.process(
            message="identify the bottleneck in this data:\n```\nspan db.acquire_conn 3900ms\n```",
            session_id="test-session",
            project_id="proj-001",
        ):
            events.append(event)

    mock_bottleneck.assert_called_once_with("span db.acquire_conn 3900ms")
    start_event = next(e for e in events if e["type"] == "agent_start")
    assert start_event["agent"] == "performance_qa"
    done_event = next(e for e in events if e["type"] == "orchestrator_done")
    assert done_event["data"]["bottleneck"]["layer"] == "db"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_orchestrator.py -q
```

Expected: `12 failed, 21 passed` — classification tests fail on wrong actions (e.g. `"analyze performance risk for SCRUM-10"` classifies as `analyze_story`, `"generate a load test script for SCRUM-10"` as `generate_test_cases`), and the two `process()` tests fail with `AttributeError: 'QAOrchestrator' object has no attribute '_performance_qa'`. Note: `test_classify_translate_does_not_route_to_sla` and `test_classify_existing_agent_routing_unchanged` already pass before implementation (they guard that the new rules do not break existing behavior) — that is expected.

- [ ] **Step 3: Write minimal implementation** — four edits to `qa-brain/backend/app/agents/orchestrator.py`:

3a. Add the import after line 5 (`from app.agents.security_qa import SecurityQAAgent`):

```python
from app.agents.performance_qa import PerformanceQAAgent
```

3b. Add the agent instance in `__init__`, after `self._security_qa = SecurityQAAgent()` (line 18):

```python
        self._performance_qa = PerformanceQAAgent()
```

3c. In `_classify_intent()`, insert the 8 performance rules immediately after the `build_owasp_dashboard` rule (line 41) and immediately BEFORE the ManualQA generic rule `if any(w in msg for w in ["analyze", "ambigui", "missing", "risk"]):` (line 42) — the generic `analyze`/`risk` keywords would otherwise swallow performance intents:

```python
        if any(w in msg for w in ["workload model", "load model", "load profile"]):
            return {"action": "build_workload_model", "story_ids": story_ids}
        if any(w in msg for w in ["performance risk", "perf risk"]):
            return {"action": "analyze_perf_risk", "story_ids": story_ids}
        if any(w in msg for w in ["load test script", "perf script", "performance script", "k6 script", "jmeter script"]):
            framework = "jmeter" if "jmeter" in msg else "k6"
            return {"action": "generate_perf_script", "story_ids": story_ids, "framework": framework}
        if any(w in msg for w in ["load test result", "perf result", "performance result"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            result_text = code_match.group(1).strip() if code_match else message
            return {"action": "analyze_perf_result", "result_text": result_text}
        if "bottleneck" in msg:
            code_match = CODE_BLOCK_PATTERN.search(message)
            trace_text = code_match.group(1).strip() if code_match else message
            return {"action": "identify_bottleneck", "trace_text": trace_text}
        if re.search(r"\bsla\b", msg) or re.search(r"\bslo\b", msg):
            return {"action": "define_sla_slo", "requirements": message, "story_ids": story_ids}
        if any(w in msg for w in ["perf defect", "performance defect"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            finding_text = code_match.group(1).strip() if code_match else message
            return {"action": "write_perf_defect", "finding_text": finding_text}
        if any(w in msg for w in ["capacity", "infra sizing", "sizing recommendation"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            results_text = code_match.group(1).strip() if code_match else message
            return {"action": "recommend_capacity", "results_text": results_text}
```

3d. In `process()`, insert the 8 dispatch blocks after the `build_owasp_dashboard` elif block (which ends at line 230 with the `owasp_dashboard` yield) and before the final `else:` (line 232):

```python
        elif action == "build_workload_model":
            story_ids = intent.get("story_ids", [])
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "performance_qa", "message": f"Building workload model for {story_id}..."}
                workload_model = await self._performance_qa.build_workload_model(story_id)
                yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Workload model ready for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"workload_model": workload_model, "story_id": story_id}}

        elif action == "analyze_perf_risk":
            story_ids = intent.get("story_ids", [])
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "performance_qa", "message": f"Analyzing performance risks for {story_id}..."}
                perf_risks = await self._performance_qa.analyze_perf_risk(story_id)
                yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Found {len(perf_risks)} performance risk(s) for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"perf_risks": perf_risks, "story_id": story_id}}

        elif action == "generate_perf_script":
            story_ids = intent.get("story_ids", [])
            framework = intent.get("framework", "k6")
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "performance_qa", "message": f"Generating {framework} load test script for {story_id}..."}
                perf_script = await self._performance_qa.generate_perf_script(story_id, framework=framework)
                yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Generated {framework} script for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"perf_script": perf_script, "story_id": story_id}}

        elif action == "analyze_perf_result":
            result_text = intent.get("result_text", "")
            yield {"type": "agent_start", "agent": "performance_qa", "message": "Analyzing load test results..."}
            perf_result_analysis = await self._performance_qa.analyze_perf_result(result_text)
            yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Result analysis complete: {perf_result_analysis.get('verdict', 'unknown')}"}
            yield {"type": "orchestrator_done", "data": {"perf_result_analysis": perf_result_analysis}}

        elif action == "identify_bottleneck":
            trace_text = intent.get("trace_text", "")
            yield {"type": "agent_start", "agent": "performance_qa", "message": "Identifying bottleneck from trace data..."}
            bottleneck = await self._performance_qa.identify_bottleneck(trace_text)
            yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Bottleneck hypothesis: {bottleneck.get('layer', 'unknown')} layer"}
            yield {"type": "orchestrator_done", "data": {"bottleneck": bottleneck}}

        elif action == "define_sla_slo":
            requirements = intent.get("requirements", "")
            story_ids = intent.get("story_ids", [])
            story_id = story_ids[0] if story_ids else None
            yield {"type": "agent_start", "agent": "performance_qa", "message": "Defining SLA/SLO thresholds..."}
            sla_slo = await self._performance_qa.define_sla_slo(requirements, story_id=story_id)
            yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Defined {len(sla_slo.get('slos', []))} SLO(s)"}
            yield {"type": "orchestrator_done", "data": {"sla_slo": sla_slo}}

        elif action == "write_perf_defect":
            finding_text = intent.get("finding_text", "")
            yield {"type": "agent_start", "agent": "performance_qa", "message": "Writing performance defect..."}
            perf_defect = await self._performance_qa.write_perf_defect(finding_text)
            yield {"type": "agent_complete", "agent": "performance_qa", "message": f"Performance defect created: {perf_defect.get('jira_id', 'unknown')}"}
            yield {"type": "orchestrator_done", "data": {"perf_defect": perf_defect}}

        elif action == "recommend_capacity":
            results_text = intent.get("results_text", "")
            yield {"type": "agent_start", "agent": "performance_qa", "message": "Building capacity recommendation..."}
            capacity_plan = await self._performance_qa.recommend_capacity(results_text)
            yield {"type": "agent_complete", "agent": "performance_qa", "message": "Capacity recommendation ready"}
            yield {"type": "orchestrator_done", "data": {"capacity_plan": capacity_plan}}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_orchestrator.py -q
```

Expected: `33 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `103 passed` (all pre-existing manual/automation/security routing tests must still pass).

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: route performance intents to PerformanceQAAgent in orchestrator"
```

---

### Task 7: Persistence — perf_risks → performance_findings

**Files:**
- Modify: `qa-brain/backend/app/api/chat.py` — import (after line 13, `from app.models.security_finding import SecurityFinding`), helper function (after `_persist_owasp_mapping`, which ends at line 128), websocket trigger (in the `orchestrator_done` block, after the `owasp_mapping` trigger at line 166)
- Test: `qa-brain/backend/tests/test_chat_api.py` (append)

**Interfaces:**
- Consumes: `PerformanceFinding` model from `app.models.performance_finding` (columns `story_id`, `risk_area`, `severity`, `description`); `orchestrator_done` events whose `data` contains `perf_risks` (list of `{"risk_area", "severity", "description"}`) and `story_id` (a Jira id like `"SCRUM-10"`), produced by Task 6's `analyze_perf_risk` dispatch; existing `Story` model and `select` already imported in `chat.py`
- Produces: `async def _persist_performance_findings(db: AsyncSession, jira_id: str, perf_risks: list) -> None` — get-or-creates the `Story` by `jira_id` (existing `_get_or_create_story` helper at `chat.py:27`), inserts one `PerformanceFinding` row per risk and commits. Task 8 reads these rows.

- [ ] **Step 1: Write the failing test** — append to `qa-brain/backend/tests/test_chat_api.py`:

```python
from sqlalchemy import select
from app.models.performance_finding import PerformanceFinding


@pytest.mark.asyncio
async def test_persist_performance_findings_writes_rows(db_session, test_story):
    from app.api.chat import _persist_performance_findings

    perf_risks = [
        {"risk_area": "database", "severity": "high", "description": "Unindexed hot query"},
        {"risk_area": "api", "severity": "medium", "description": "N+1 calls on the list endpoint"},
    ]
    await _persist_performance_findings(db_session, test_story.jira_id, perf_risks)

    result = await db_session.execute(
        select(PerformanceFinding).where(PerformanceFinding.story_id == test_story.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 2
    risk_areas = {r.risk_area for r in rows}
    assert risk_areas == {"database", "api"}
    severities = {r.severity for r in rows}
    assert severities == {"high", "medium"}


@pytest.mark.asyncio
async def test_persist_performance_findings_creates_missing_story(db_session):
    from app.api.chat import _persist_performance_findings
    from app.models.story import Story

    await _persist_performance_findings(
        db_session,
        "NOPE-999",
        [{"risk_area": "database", "severity": "low", "description": "x"}],
    )

    story_res = await db_session.execute(select(Story).where(Story.jira_id == "NOPE-999"))
    story = story_res.scalar_one_or_none()
    assert story is not None

    result = await db_session.execute(
        select(PerformanceFinding).where(PerformanceFinding.story_id == story.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].severity == "low"


@pytest.mark.asyncio
async def test_websocket_chat_persists_perf_risks(db_session, test_user, auth_token, test_story):
    mock_events = [
        {"type": "agent_start", "agent": "performance_qa", "message": "Analyzing performance risks..."},
        {
            "type": "orchestrator_done",
            "data": {
                "perf_risks": [
                    {"risk_area": "database", "severity": "high", "description": "Hot query has no index"},
                ],
                "story_id": test_story.jira_id,
            },
        },
    ]

    async def mock_process(*args, **kwargs):
        for event in mock_events:
            yield event

    with patch("app.api.chat.orchestrator.process", side_effect=mock_process):
        async with AsyncClient(transport=ASGIWebSocketTransport(app=app), base_url="ws://test") as client:
            async with aconnect_ws(
                f"ws://test/ws/chat/test-session?token={auth_token}",
                client
            ) as ws:
                await ws.send_json({"type": "user_message", "content": f"analyze performance risk for {test_story.jira_id}", "project_id": "proj-001"})
                events = []
                for _ in range(len(mock_events)):
                    msg = await ws.receive_json()
                    events.append(msg)

    assert any(e["type"] == "orchestrator_done" for e in events)

    result = await db_session.execute(
        select(PerformanceFinding).where(PerformanceFinding.story_id == test_story.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].risk_area == "database"
    assert rows[0].severity == "high"
    assert rows[0].description == "Hot query has no index"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_chat_api.py -q
```

Expected: `3 failed, 1 passed` — the two helper tests fail with `ImportError: cannot import name '_persist_performance_findings' from 'app.api.chat'`, and the websocket test fails at the final row-count assertion (`assert 0 == 1`) because no trigger exists yet.

- [ ] **Step 3: Write minimal implementation** — three edits to `qa-brain/backend/app/api/chat.py`:

3a. Add the import after line 13 (`from app.models.security_finding import SecurityFinding`):

```python
from app.models.performance_finding import PerformanceFinding
```

3b. Add the helper immediately after `_persist_owasp_mapping` (after line 128), mirroring its shape exactly — get-or-create the story anchor via the existing `_get_or_create_story` helper (`chat.py:27`), same as every other persistence helper in this file:

```python
async def _persist_performance_findings(
    db: AsyncSession,
    jira_id: str,
    perf_risks: list,
) -> None:
    story = await _get_or_create_story(db, jira_id)

    for risk_data in perf_risks:
        finding = PerformanceFinding(
            story_id=story.id,
            risk_area=risk_data.get("risk_area", ""),
            severity=risk_data.get("severity", "medium"),
            description=risk_data.get("description", ""),
        )
        db.add(finding)
    await db.commit()
```

3c. Add the trigger inside the websocket `orchestrator_done` block, immediately after the `owasp_mapping` trigger (line 166), keeping the exact `if ev_data.get(...) and ev_data.get("story_id")` pattern:

```python
                        if ev_data.get("perf_risks") and ev_data.get("story_id"):
                            await _persist_performance_findings(db, ev_data["story_id"], ev_data["perf_risks"])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_chat_api.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `106 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/api/chat.py tests/test_chat_api.py
git commit -m "feat: persist perf_risks to performance_findings via chat websocket"
```

---

### Task 8: REST API — GET /api/stories/{jira_id}/performance-findings

**Files:**
- Create: `qa-brain/backend/app/api/performance.py`
- Modify: `qa-brain/backend/app/main.py` — import (after line 8, `from app.api.security import router as security_router`) and router registration (after line 25, `app.include_router(security_router)`)
- Test: `qa-brain/backend/tests/test_performance_api.py` (new)

**Interfaces:**
- Consumes: `PerformanceFinding` from `app.models.performance_finding` (columns `id`, `story_id`, `risk_area`, `severity`, `description`, `created_at`), `Story` from `app.models.story`, `get_db` from `app.database`, `get_current_user` from `app.api.auth` (OAuth2 bearer — missing token returns 401)
- Produces: `GET /api/stories/{jira_id}/performance-findings` returning `[{"id", "story_id", "risk_area", "severity", "description", "created_at"}]` (404 if the story is unknown, 401 without auth). Consumed by the frontend Performance panel (separate plan).

- [ ] **Step 1: Write the failing test** — create `qa-brain/backend/tests/test_performance_api.py` with exactly:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models.performance_finding import PerformanceFinding


@pytest.mark.asyncio
async def test_get_story_performance_findings_requires_auth(test_story):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/stories/{test_story.jira_id}/performance-findings")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_story_performance_findings_returns_empty_list(db_session, auth_token, test_story):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/stories/{test_story.jira_id}/performance-findings",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_story_performance_findings_returns_list(db_session, auth_token, test_story):
    finding = PerformanceFinding(
        story_id=test_story.id,
        risk_area="database",
        severity="high",
        description="Unindexed hot query path degrades under load",
    )
    db_session.add(finding)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/stories/{test_story.jira_id}/performance-findings",
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["risk_area"] == "database"
    assert data[0]["severity"] == "high"
    assert data[0]["description"] == "Unindexed hot query path degrades under load"
    assert data[0]["story_id"] == test_story.id
    assert data[0]["id"] is not None
    assert data[0]["created_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_api.py -q
```

Expected: `3 failed` — all three receive `404 Not Found` (route not registered), so the status-code assertions fail (`assert 404 == 401`, `assert 404 == 200`).

- [ ] **Step 3: Write minimal implementation**

3a. Create `qa-brain/backend/app/api/performance.py` (mirrors `app/api/security.py` field-for-field with this table's columns):

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.story import Story
from app.models.performance_finding import PerformanceFinding

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/stories/{jira_id}/performance-findings")
async def get_story_performance_findings(
    jira_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    story_result = await db.execute(select(Story).where(Story.jira_id == jira_id))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {jira_id} not found")

    result = await db.execute(select(PerformanceFinding).where(PerformanceFinding.story_id == story.id))
    findings = result.scalars().all()
    return [
        {
            "id": f.id,
            "story_id": f.story_id,
            "risk_area": f.risk_area,
            "severity": f.severity,
            "description": f.description,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in findings
    ]
```

3b. In `qa-brain/backend/app/main.py`, add the import after line 8:

```python
from app.api.performance import router as performance_router
```

and register the router after line 25 (`app.include_router(security_router)`):

```python
app.include_router(performance_router)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest tests/test_performance_api.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run full suite**

```bash
cd qa-brain/backend
.venv/bin/python -m pytest -q
```

Expected: `109 passed`.

- [ ] **Step 6: Commit**

```bash
cd qa-brain/backend
git add app/api/performance.py app/main.py tests/test_performance_api.py
git commit -m "feat: add GET /api/stories/{jira_id}/performance-findings endpoint"
```

---

## Spec coverage map (self-review)

| Spec section | Covered by |
|---|---|
| §1 tools 1–2 (`build_workload_model`, `analyze_perf_risk`) | Task 2 |
| §1 tools 3–4 (`generate_perf_script` k6/jmeter, `analyze_perf_result`) | Task 3 |
| §1 tools 5–6 (`identify_bottleneck`, `define_sla_slo`) | Task 4 |
| §1 tools 7–8 (`write_perf_defect` real Jira ticket, `recommend_capacity`) | Task 5 |
| §1 model `claude-sonnet-4-6` + prompt focus | Task 2 (`self._model`, `SYSTEM_PROMPT`) |
| §2 integrations (reuse `JiraClient.create_issue`, no new deps/env vars) | Task 5; Global Constraints |
| §3 class anatomy + return shapes (all 8, keys verbatim) | Tasks 2–5 |
| §4 routing keywords, rule placement before ManualQA generics, `\bsla\b`/`\bslo\b` word-boundary regex, code-block extraction with raw-message fallback, jmeter detection, event data keys | Task 6 |
| §5 `performance_findings` schema, migration `down_revision='03fdf5c62169'`, `_persist_performance_findings`, read path | Tasks 1, 7, 8 |
| §6 mock mode (`[MOCK]` labels, real titles best-effort, `write_perf_defect` never POSTs) | Tasks 2–5 (fixtures + `assert_not_called` test in Task 5) |
| §7 UX/UI | Out of scope — frontend plan (`2026-07-02-performance-qa-agent-frontend.md`) |
| §8 testing approach (both modes per tool, orchestrator intent + collision regressions, API tests, persistence trigger test) | Tasks 2–8 |
| §9 out-of-scope items (no Gatling, no execution, no APM clients, no extra persistence, no script lifecycle, keyword routing retained) | Not implemented anywhere — verified |

Expected test totals per task: 70 → 71 → 75 → 80 → 85 → 89 → 103 → 106 → 109.
