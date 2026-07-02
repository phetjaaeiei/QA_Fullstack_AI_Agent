# Performance QA Agent — Design Spec (Phase 3, part 1)

**Date:** 2026-07-02
**Status:** Approved for planning. Supersedes nothing — extends `docs/superpowers/specs/2026-07-01-qa-brain-design.md` §3.4 and §8 (Phase 3).

> **Decision provenance:** the user delegated design decisions for Phase 3 ("เลือกวิธีที่ดีที่สุดมาเลย"). Approaches considered are recorded in §10 so the choices can be revisited.

## 1. Scope — 8 tools

Implements the Performance QA Agent exactly as enumerated in the master design §3.4 ("Performance QA Agent ครบทุกtool" per the Phase 3 roadmap §8). Analytics Agent, release-risk aggregation, and domain-IP templates are separate Phase 3 work and explicitly **not** part of this agent.

| # | Tool | Input | Output | Notes |
|---|------|-------|--------|-------|
| 1 | `build_workload_model` | Story ID(s) (Jira) | Concurrent users, ramp-up pattern, named scenarios with weights | One-shot chat output |
| 2 | `analyze_perf_risk` | Story ID (Jira) | List of performance risks: risk area, severity, description | **Persisted** to `performance_findings` |
| 3 | `generate_perf_script` | Story ID + framework (`k6` default, `jmeter`) | Runnable load-test script | One-shot chat output (code block) |
| 4 | `analyze_perf_result` | Pasted load-test result / APM log (chat code block) | Root cause + bottleneck location + summary verdict | One-shot chat output |
| 5 | `identify_bottleneck` | Pasted APM trace data (chat code block) | Layer hypothesis: App / DB / API / Infra + evidence | One-shot chat output |
| 6 | `define_sla_slo` | Story ID or freeform business requirements | SLA thresholds + pass/fail criteria per metric | One-shot chat output |
| 7 | `write_perf_defect` | Bottleneck/finding text (chat code block or message) | Defect report + **real Jira ticket** (reuses `JiraClient.create_issue()`) | Mock mode never POSTs |
| 8 | `recommend_capacity` | Pasted test results / load model (chat code block) | Infra sizing recommendation | One-shot chat output |

**Model:** `claude-sonnet-4-6` (master spec §6/§13: Sonnet for generation-heavy agents; Opus reserved for Orchestrator + Security reasoning).

**Key prompt focus:** load modeling, APM analysis, bottleneck diagnosis, infrastructure sizing. System prompt follows the established convention: module-level `SYSTEM_PROMPT` constant, "Always return valid JSON only — no markdown," conservative/evidence-based analysis rules.

## 2. Integrations — nothing new required

- **Jira:** `write_perf_defect` reuses `JiraClient.create_issue()` added in the Security phase (`app/mcp_clients/jira_client.py`). Target project stays `"SCRUM"`, matching `write_security_defect` (single-project demo; known limitation carried over).
- **OpenAPI:** `generate_perf_script` and `build_workload_model` use the existing `OpenAPIClient` best-effort (same as ManualQA/SecurityQA) to ground endpoints; degrade gracefully when no spec is configured.
- **No new Python dependencies. No new npm dependencies. No new env vars.**

## 3. `PerformanceQAAgent` (`app/agents/performance_qa.py`)

Mirrors `SecurityQAAgent`'s anatomy exactly:

```python
class PerformanceQAAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._jira = JiraClient()
        self._openapi = OpenAPIClient()
        self._model = "claude-sonnet-4-6"
        self._mock = settings.mock_mode
```

- One async public method per tool (8 methods).
- First line of every method: `if self._mock:` → return module-level `_mock_*` fixture labeled `[MOCK]`; real story titles still fetched best-effort for realistic demos (established MOCK_MODE convention).
- Real branch: `self._client.messages.create(...)` → `_parse_json()` (same fence-stripping helper convention).
- Both branches return identical dict/list shapes.

Return shapes (consumed by orchestrator events, frontend types, and persistence):

- `build_workload_model` → `{"story_id", "concurrent_users", "ramp_up", "duration", "scenarios": [{"name", "weight_percent", "description"}]}`
- `analyze_perf_risk` → `[{"risk_area", "severity": "critical|high|medium|low", "description"}]`
- `generate_perf_script` → `{"framework": "k6|jmeter", "content", "notes"}`
- `analyze_perf_result` → `{"verdict": "pass|fail|degraded", "root_cause", "bottleneck_location", "summary", "recommendations": [str]}`
- `identify_bottleneck` → `{"layer": "app|db|api|infra", "hypothesis", "evidence": [str], "next_steps": [str]}`
- `define_sla_slo` → `{"slos": [{"metric", "target", "pass_criteria"}], "notes"}`
- `write_perf_defect` → `{"report", "impact", "evidence", "jira_id", "url"}` (mock: `jira_id="[MOCK]"`, `url="[MOCK]"`)
- `recommend_capacity` → `{"current_assessment", "recommendations": [{"component", "sizing", "rationale"}], "estimated_headroom"}`

## 4. Orchestrator routing — extends the existing keyword classifier

Add 8 rules to `_classify_intent()` in `app/agents/orchestrator.py`, **placed before ManualQA's generic rules** (the generic `"risk"` and `"analyze"` keywords would otherwise swallow performance intents):

| Keywords (substring of lowercased msg unless noted) | Action |
|---|---|
| `workload model`, `load model`, `load profile` | `build_workload_model` |
| `performance risk`, `perf risk` | `analyze_perf_risk` |
| `load test script`, `perf script`, `performance script`, `k6 script`, `jmeter script` | `generate_perf_script` |
| `load test result`, `perf result`, `performance result` | `analyze_perf_result` |
| `bottleneck` | `identify_bottleneck` |
| `\bsla\b`, `\bslo\b` (**word-boundary regex**, not substring — `"sla" in msg` false-positives on "translate") | `define_sla_slo` |
| `perf defect`, `performance defect` | `write_perf_defect` |
| `capacity`, `infra sizing`, `sizing recommendation` | `recommend_capacity` |

Dispatch in `process()` follows the exact 3-event convention per action: `agent_start` (agent=`performance_qa`) → `agent_complete` → `orchestrator_done` with a distinct data key per tool (`workload_model`, `perf_risks`, `perf_script`, `perf_result_analysis`, `bottleneck`, `sla_slo`, `perf_defect`, `capacity_plan`) plus `story_id` where applicable.

Inputs for tools 4, 5, 7, 8 come from the chat message's fenced code block via the existing `CODE_BLOCK_PATTERN`; fall back to the raw message text when no fence is present (same pattern AutomationQA uses for CI-failure JSON). Framework detection for tool 3: `jmeter` in message → `jmeter`, else default `k6`.

**Known collision surface (accepted):** a message like "generate script for load test" hits AutomationQA's `generate script` rule first — users must say "load test script" / "perf script". Same class of tech debt as the Security keywords; revisit when routing moves to LLM/tool-use classification (already out of scope there too).

## 5. Database schema — new `performance_findings` table

```sql
CREATE TABLE performance_findings (
    id          VARCHAR PRIMARY KEY,            -- uuid4 string, matching all other tables
    story_id    VARCHAR NOT NULL REFERENCES stories(id),
    risk_area   VARCHAR NOT NULL,               -- freeform: "database", "api", "frontend", "infra", ...
    severity    perf_severity NOT NULL,         -- ENUM('critical','high','medium','low')
    description TEXT,
    created_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX ix_performance_findings_story_id ON performance_findings (story_id);
```

- SQLAlchemy model `PerformanceFinding` in `app/models/performance_finding.py`, registered in `app/models/__init__.py`; `created_at` uses `datetime.utcnow` default matching every existing model (known pre-existing pattern, not a regression).
- Alembic migration `add_performance_findings_table`, `down_revision = '03fdf5c62169'` (current head).
- **What writes:** `_persist_performance_findings()` in `app/api/chat.py`, triggered when an `orchestrator_done` event carries `perf_risks` + `story_id` (mirrors `_persist_owasp_mapping`). `risk_area`/`severity` values are trusted from the LLM (same trust-the-LLM enum caveat already documented for security findings).
- **What reads:** `GET /api/stories/{jira_id}/performance-findings` + the frontend Performance panel.
- **Why the other 7 outputs aren't persisted:** workload models, scripts, result analyses, bottleneck hypotheses, SLO drafts, and capacity plans are conversational artifacts the user copies onward; none has a dashboard read-path this phase. Perf scripts deliberately do NOT get `automation_scripts`-style lifecycle (health, runs, self-healing) — that machinery exists for functional automation; duplicating it here is scope creep (§9).

## 6. Mock mode

All 8 tools honor `MOCK_MODE=true` with `[MOCK]`-labeled fixtures; real Jira story titles are still blended in when fetchable (cheap, keeps demos realistic). `write_perf_defect` in mock mode **never** calls `JiraClient.create_issue()` and returns `url="[MOCK]"` — the frontend already suppresses links for `[MOCK]` URLs (established by `security_defect` handling).

## 7. UX/UI direction

- **New "Performance" tab** in `Dashboard.tsx`, fourth alongside Test Cases / Scripts / OWASP: extend the `RightPanel` union with `"performance"`, add the count-badge button, conditional render.
- **New `PerformancePanel`** (`src/components/PerformancePanel/PerformancePanel.tsx`): table of persisted findings grouped by story — columns story / risk area / severity chip / description. Severity colors reuse the existing semantic palette (red/orange/yellow/slate). Thai empty state matching house style: "ยังไม่มี performance findings — ลองสั่ง analyze performance risk จาก chat". Pure Tailwind, no new components beyond the panel (single file; no sub-components needed at this data shape).
- **`useAgentChat.ts`:** new `perfFindings` state returned by the hook; 8 new `orchestrator_done` data-key branches, each appending a formatted assistant chat message (existing formatter-function convention, emoji-prefixed). `perf_defect` attaches a `Message.link` with the Jira URL exactly like `security_defect` (mock URLs suppressed). `perf_script` renders fenced code in the chat message body (MessageBubble already renders markdown-ish text; scripts display as preformatted content the same way automation scripts do).
- **`types.ts` / `api.ts`:** extend `AgentEvent["data"]` with the 8 shapes from §3; add `PerformanceFinding` domain type; add `getStoryPerformanceFindings(jiraId)` (note: `getStorySecurityFindings` is written-but-unwired — same page-refresh persistence gap is accepted here for symmetry, already logged as deferred work).

## 8. Testing approach (TDD, per-task)

- `tests/test_performance_qa_agent.py` — every tool tested in both forms: real mode (patched `AsyncAnthropic.messages.create` returning canned JSON) and mock mode (`settings.mock_mode=True`, assert `[MOCK]` markers). `write_perf_defect` mock-mode test asserts `create_issue` is **never called** (`assert_not_called`), mirroring the security test.
- `tests/test_orchestrator.py` — extend with 8 intent-classification cases + collision regressions: "performance risk for SCRUM-1" must NOT route to ManualQA's generic `risk` rule; "translate this story" must NOT route to `define_sla_slo`; existing 3 agents' routing must stay green.
- `tests/test_performance_api.py` — GET endpoint: empty list, populated list, auth required.
- `tests/test_chat_api.py` or orchestrator-level test — `perf_risks` persistence trigger writes `performance_findings` rows.
- Frontend: `npm run build` must pass (no test runner configured in this project — build is the established frontend gate).

## 9. Explicitly out of scope for this phase

- **Gatling** script generation (k6 + JMeter cover the demo need; enum extension is cheap later).
- **Executing** load tests (no runner infra; agent generates scripts and analyzes pasted results only).
- **Real APM integration** (Datadog/New Relic/Grafana clients) — inputs are pasted text this phase.
- **Persisting** workload models, scripts, SLOs, capacity plans (no read-path yet).
- **Perf-script lifecycle** (health tracking, self-healing, CI hooks) — that's Automation-agent machinery.
- **Analytics Agent / release-risk aggregation / `release_assessments.perf_score` wiring** — next Phase 3 item, needs this agent's outputs first.
- **LLM-based intent routing** — keyword classifier retained, consistent with all prior agents.

## 10. Approaches considered

1. **Full 8-tool agent, minimal persistence (chosen).** Matches master spec §3.4 verbatim and the roadmap's "ครบทุก tool"; smallest DB surface (1 table); reuses every existing integration; identical shape to the two shipped Phase 2 agents so implementation risk is low.
2. **4-tool MVP (risk, script, SLO, result-analysis), defer the rest.** Rejected: the roadmap explicitly says all tools; the marginal cost per extra tool is small under the established mock/real pattern; a second PR for 4 more tools costs more overhead than it saves.
3. **Deep integration: actually run k6 locally and ingest real results.** Rejected: no load-runner infrastructure exists, `ANTHROPIC_API_KEY` is still mock-blocked so end-to-end realism is capped anyway, and execution infra is a separate operational decision (YAGNI now, revisit post-Analytics).
