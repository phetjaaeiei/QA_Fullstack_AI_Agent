# Security QA Agent — Phase 2 Design

**Status:** Approved for planning. Supersedes nothing — extends `docs/superpowers/specs/2026-07-01-qa-brain-design.md` §3.5 and §8 (Phase 2) with concrete implementation decisions, following the same pattern established by `docs/superpowers/specs/2026-07-02-automation-qa-agent-design.md` (Phase 2's first agent, now merged to `main`).

**Goal:** Add a Security QA Agent to QA Brain that generates OWASP-Top-10-aware test cases, maps stories to OWASP risk categories, builds RBAC test matrices, generates API security checklists from OpenAPI specs, triages vulnerability scanner output, and writes security defects as real Jira tickets — following the same architectural patterns Phase 1 and the Automation QA Agent already proved out (plain async HTTP clients, regex-based orchestrator routing, `MOCK_MODE` for demoability).

**Why this scope:** The original design spec's Security QA Agent table lists exactly 7 tools, none of which require infrastructure this project doesn't already have or can't add incrementally (unlike the Automation Agent's deferred `explore_and_generate`, which needed headless-browser crawling). All 7 are in scope.

---

## 1. Scope — 7 tools

| Tool | Input | Output | Notes |
|---|---|---|---|
| `generate_owasp_test_cases` | Story ID | Test cases covering relevant OWASP Top 10 categories | Persists as `TestCase` rows with `type="security"` — this enum value already exists in the Phase 1 schema, unused until now |
| `map_story_to_owasp` | Story ID(s) | Story → OWASP category risk/coverage mapping | Persists to the new `security_findings` table (§6) |
| `generate_rbac_matrix` | Roles (list) + feature description, both freeform from the chat message | Role × access-boundary test matrix | Pure LLM generation, no external I/O or persistence — same shape as `AutomationQAAgent.generate_test_data` |
| `generate_api_security_checklist` | OpenAPI spec (fetched via the existing `OpenAPIClient` from Phase 1) | Broken Access / Injection / Auth checklist | Reuses `app/mcp_clients/openapi_client.py` as-is — no new client |
| `triage_vulnerabilities` | Scanner results as raw JSON, pasted into chat as a code block | Priority ranking + false-positive filter | No scanner integration exists (confirmed) — input is scanner-agnostic JSON the user pastes/uploads, parsed with the same `CODE_BLOCK_PATTERN` regex the orchestrator already uses for `auto_fix_script` |
| `write_security_defect` | A vulnerability finding (chat message, typically `triage_vulnerabilities` output pasted back) | Report + Impact + CVSS score + Evidence, **and a real Jira ticket** | Requires a new `JiraClient.create_issue()` write method (§2) — the existing client is read-only |
| `build_owasp_dashboard` | Sprint ID | OWASP coverage % per category + traceability | Pure DB aggregation over `security_findings` + `test_cases` (`type="security"`), plus a Claude-generated gap/recommendation summary — mirrors `ManualQAAgent.score_release_readiness` |

**Model:** `claude-opus-4-8` for every tool — matches the original spec's explicit call for deeper reasoning on security analysis, unlike `claude-sonnet-4-6` used by `ManualQAAgent` and `AutomationQAAgent`.

**Key Prompt Focus:** OWASP Top 10 expertise, threat modeling, access control, injection patterns (per original spec §3.5).

---

## 2. New integration: `JiraClient.create_issue()`

`write_security_defect` is the only tool in this project so far that needs to *write* to an external system rather than only read from it. Add one method to the existing `app/mcp_clients/jira_client.py`:

```python
async def create_issue(
    self, project_key: str, summary: str, description: str,
    issue_type: str = "Bug", labels: list = None,
) -> dict:
    response = await self._http.post(
        "/rest/api/3/issue",
        json={
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {"type": "doc", "version": 1, "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ]},
                "issuetype": {"name": issue_type},
                "labels": labels or [],
            }
        },
    )
    response.raise_for_status()
    data = response.json()
    return {"jira_id": data["key"], "url": f"{self._http.base_url}/browse/{data['key']}"}
```

Jira Cloud's issue-create endpoint requires Atlassian Document Format for `description`, unlike the plain-text fields `_normalize_story` reads — the paragraph wrapper above is the minimum valid ADF body.

---

## 3. `SecurityQAAgent`

`app/agents/security_qa.py`, structurally identical to `ManualQAAgent`/`AutomationQAAgent`:
- `__init__` builds `self._client` (`AsyncAnthropic`), `self._jira` (`JiraClient`), `self._openapi` (`OpenAPIClient`), `self._mock = settings.mock_mode`, `self._model = "claude-opus-4-8"`.
- One async method per tool in §1.
- Every method checks `self._mock` first and returns a `[MOCK]`-labeled fixture, following the exact pattern already implemented in `ManualQAAgent`/`AutomationQAAgent`. `write_security_defect` in mock mode returns a fake ticket (e.g. `{"jira_id": "[MOCK] SCRUM-999", "url": "[MOCK]"}`) **without calling `JiraClient.create_issue()`** — this is the one tool where mock mode isn't just about avoiding LLM cost, it's about not polluting the real Jira project with fake tickets during demos.

---

## 4. Orchestrator routing — extends the existing regex classifier

`QAOrchestrator._classify_intent()` gains 7 new keyword rules for the third agent. Ordering matters more than it did for the Automation Agent, because generic words like "map" and "trace" already route to `ManualQAAgent`'s traceability action:

```python
if any(w in msg for w in ["owasp test", "owasp coverage test", "generate owasp"]):
    return {"action": "generate_owasp_test_cases", "story_ids": story_ids}
if any(w in msg for w in ["map story to owasp", "owasp map", "owasp mapping", "owasp risk"]):
    return {"action": "map_story_to_owasp", "story_ids": story_ids}
if any(w in msg for w in ["rbac", "role-based access", "role matrix", "access matrix"]):
    return {"action": "generate_rbac_matrix", "requirements": message}
if any(w in msg for w in ["api security checklist", "security checklist"]):
    return {"action": "generate_api_security_checklist", "requirements": message}
if any(w in msg for w in ["triage vulnerabilit", "scanner result", "zap result"]):
    code_match = CODE_BLOCK_PATTERN.search(message)
    scan_json = code_match.group(1).strip() if code_match else ""
    return {"action": "triage_vulnerabilities", "scan_json": scan_json}
if any(w in msg for w in ["security defect", "write defect", "cvss"]):
    return {"action": "write_security_defect", "finding": message}
if any(w in msg for w in ["owasp dashboard", "security dashboard", "owasp coverage"]):
    return {"action": "build_owasp_dashboard", "sprint_id": sprint_id}
```

**Placement:** all 7 checks are inserted *before* the existing generic `"traceability", "trace", "link", "map"` rule (which routes to `ManualQAAgent.build_traceability_map`), so an OWASP-qualified "map" phrase is caught first.

**Known limitation, accepted for now (carried forward from the Automation Agent design):** this is the third agent added to the same regex classifier, and the collision surface keeps growing — `"map"` alone is now shared across two agents' worth of qualified variants. Approaches B (LLM-based classification) and C (native Claude tool-use) remain logged as tech debt, not built now, per the same reasoning as before: no real misclassification has been observed in production use yet. Revisit if a 4th agent is added or real collisions surface.

---

## 5. Database schema — new `security_findings` table

```sql
security_findings (
  id, story_id FK -> stories.id,
  owasp_category VARCHAR,       -- e.g. "A01:2021-Broken Access Control"
  status ENUM(covered, gap, not_applicable),
  risk_level ENUM(critical, high, medium, low),
  notes TEXT,
  created_at
)
```

Written by `map_story_to_owasp` (one row per story × applicable OWASP category). Read by `build_owasp_dashboard` to compute coverage % per category across a sprint's stories, and by the future OWASP Coverage frontend panel (§7).

`triage_vulnerabilities` and `write_security_defect` do **not** write to this table in this phase — the Jira ticket created by `write_security_defect` is the system of record for actual vulnerability findings, matching how `map_script_traceability`'s design in the Automation Agent kept scope narrow. Revisit only if the dashboard later needs to show live vulnerability counts, not just category coverage.

---

## 6. Mock mode

`MOCK_MODE` extends to cover every `SecurityQAAgent` tool, following the exact established pattern — real Jira/OpenAPI data is fetched best-effort and blended into `[MOCK]`-labeled fixture output. The one deviation is `write_security_defect` (§3): mock mode skips the real Jira POST entirely, not just the Claude call.

---

## 7. UX/UI direction

### Current state (verified against actual code, not assumed)
`qa-brain/frontend/src/pages/Dashboard.tsx` is still the 2-column grid with a tab-button row (`Test Cases (n)` / `Scripts (n)`) added for the Automation Agent — the icon-rail sidebar + tab-bar redesign speculatively sketched in the Automation Agent design doc's §8 was never built. Extending the current tab-button pattern with a third button is more consistent with what's actually running than reviving that unbuilt redesign.

### OWASP Coverage panel
Reuses the heatmap design already fully specified in `2026-07-02-automation-qa-agent-design.md` §8 (grid of stories/features × OWASP category, color-coded cells, `components/OwaspCoverage/OwaspCoverage.tsx` + `CoverageCell.tsx` + `CoverageLegend.tsx`, coverage-% color scale). That spec was written ahead of the backend that would feed it; `build_owasp_dashboard` + `security_findings` (§5) now provide the real data source it was designed against. No redesign needed — just wire it up.

Added as a third tab button (`OWASP (n)`) next to `Test Cases` and `Scripts`, following the exact pattern used when the `Scripts` tab was added.

### RBAC matrix, vulnerability triage, and defect results
Render inline in chat as formatted text/tables, extending the existing "chat feedback per agent action" pattern (`useAgentChat.ts`, built for all 7 Automation Agent actions). No dedicated panel — these are one-off, read-once outputs rather than persisted/browsable collections (unlike test cases, scripts, and OWASP coverage). `write_security_defect`'s result additionally renders the created Jira ticket as a clickable link.

### New frontend dependencies
None — the heatmap reuses raw Tailwind divs/table cells as already speced, no new charting library needed for this panel.

---

## 8. Testing approach

Mirrors the existing TDD pattern exactly (per `superpowers:test-driven-development` and `test_automation_qa_agent.py`/`test_github_client.py`):
- `tests/test_jira_client.py` — extend with a `create_issue` test (mock `httpx`, verify request body shape and response normalization).
- `tests/test_security_qa_agent.py` — mock `self._client.messages.create` and `self._jira`/`self._openapi` calls, one test per tool, including a mock-mode test for `write_security_defect` that asserts `JiraClient.create_issue` is **not** called.
- `tests/test_security_api.py` — REST endpoint(s) exposing `security_findings` (mirrors `test_automation_api.py`'s `GET /api/stories/{id}/scripts`).
- Extend `tests/test_orchestrator.py` with 7 new intent-classification cases, including at least one collision-avoidance test (an OWASP-qualified "map" message that must route to `map_story_to_owasp`, not `build_traceability_map`).

---

## 9. Explicitly out of scope for this phase

- Real vulnerability scanner integration (OWASP ZAP or similar) — `triage_vulnerabilities` accepts scanner-agnostic pasted JSON instead; wiring a live scanner API is a separate, later decision once the team picks a specific tool.
- Persisting vulnerability/triage findings to `security_findings` — that table only tracks OWASP category coverage in this phase (§5); the Jira ticket from `write_security_defect` is the system of record for actual findings.
- The icon-rail sidebar navigation redesign — still unbuilt from the Automation Agent's speculative design, and 3 tabs doesn't yet justify it.
- LLM-based or native-tool-use orchestrator routing — logged as tech debt across both Phase 2 agents now, not built.
- RBAC matrix / triage output persistence — these remain one-shot chat outputs, not browsable collections, in this phase.
