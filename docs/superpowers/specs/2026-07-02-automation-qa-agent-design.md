# Automation QA Agent — Phase 2 Design

**Status:** Approved for planning. Supersedes nothing — extends `docs/superpowers/specs/2026-07-01-qa-brain-design.md` §3.3 and §8 (Phase 2) with concrete implementation decisions.

**Goal:** Add an Automation QA Agent to QA Brain that generates, standardizes, and self-heals automation test scripts (Playwright and Robot Framework), and diagnoses CI test failures — following the same architectural patterns Phase 1's Manual QA Agent already proved out (plain async HTTP clients, regex-based orchestrator routing, `MOCK_MODE` for demoability).

**Why this scope:** The original design spec's Automation QA Agent table lists 8 tools including `explore_and_generate` (auto-crawl a live app with a headless browser and generate scripts with no human-provided spec). That one tool requires browser-automation infrastructure Phase 1 has none of, and is materially more complex than the other 7 combined. It's deferred to a later phase so Phase 2 stays consistent in complexity with Phase 1.

---

## 1. Scope — 7 tools

| Tool | Input | Output | Notes |
|---|---|---|---|
| `generate_script_from_spec` | OpenAPI/Jira spec + test case | Playwright (TypeScript) **or** Robot Framework skeleton, caller picks | Both frameworks supported per original spec — the tool takes a `framework` parameter |
| `apply_company_framework` | Raw script + house-style doc | Script reformatted to Extosoft convention | Needs a house-style reference doc (see §2) |
| `suggest_self_healing` | Broken locator + page URL | 3–5 alternative locators + strategy | Fetches the page HTML via a plain `httpx.get()` — no headless browser needed for a single-page locator suggestion (distinct from `explore_and_generate`, which needs interactive crawling) |
| `classify_failure` | CI run URL/ID | Root cause: Bug / Data / Env / Script | Log is fetched via `GitHubClient.get_test_results(run_id)` — no execution runner needed, the company's existing CI (GitHub Actions/GitLab CI) already runs the scripts |
| `auto_fix_script` | Script + error (from `classify_failure`) | Fixed script + explanation | |
| `generate_test_data` | Test case requirements | Test data sets + boundary variations | Pure LLM generation, no external I/O — same shape as Manual QA Agent's existing tools |
| `map_script_traceability` | Script + Story ID | Persists story↔script↔test-case links to DB | Feeds the Traceability Graph UI panel (§5) |

**Deferred to a later phase:** `explore_and_generate` (auto-crawl UI, no spec input) — requires headless-browser crawling infrastructure that doesn't exist yet.

**Model:** `claude-sonnet-4-6`, matching the existing convention in `ManualQAAgent`.

---

## 2. `apply_company_framework` — house-style reference

This tool needs something concrete to conform generated scripts to. Proposal: a single markdown file, `docs/automation-standards.md`, containing naming conventions, page-object-model structure, and folder layout — written once by the Extosoft QA team, loaded as extra system-prompt context whenever this tool runs.

This file does not exist yet and is **out of scope for this implementation plan** — the user owns writing its content. The mechanism (loading and injecting it) is in scope.

---

## 3. New integration: `GitHubClient`

`app/mcp_clients/github_client.py` — a plain `httpx.AsyncClient` wrapper, structurally identical to the existing `JiraClient` (no MCP protocol, per the pattern Phase 1 already established and this project explicitly chose to continue rather than adopt real MCP servers).

Methods:
- `get_pr_diff(pr_id)` — code changes for review
- `get_test_results(run_id)` — fetch a CI run's log/result for `classify_failure` and `auto_fix_script`
- `list_open_prs(repo)` — PRs pending test coverage

Auth via `GITHUB_TOKEN` (already present as an env var slot in `.env`/`.env.example`, currently a placeholder).

---

## 4. `AutomationQAAgent`

`app/agents/automation_qa.py`, structurally identical to `ManualQAAgent`:
- `__init__` builds `self._client` (`AsyncAnthropic`), `self._github` (`GitHubClient`), `self._mock = settings.mock_mode`.
- One async method per tool in §1, each either calling Claude directly (`generate_test_data`, `apply_company_framework`, `auto_fix_script`) or fetching real data first via `GitHubClient`/`httpx` then calling Claude (`classify_failure`, `suggest_self_healing`, `generate_script_from_spec` when spec comes from Jira).
- Every method checks `self._mock` first and returns a `[MOCK]`-labeled fixture, following the exact pattern already implemented in `ManualQAAgent` (`_mock_test_cases`, `_mock_analysis`, etc.) — real GitHub/Jira data is fetched best-effort even in mock mode where cheap to do so (mirrors `_fetch_story_title`).

---

## 5. Orchestrator routing — Approach A (extend the existing regex classifier)

`QAOrchestrator._classify_intent()` gains new keyword rules, checked **before** the existing generic ones to avoid collisions (e.g. bare "generate" already means `generate_test_cases` for Manual QA):

```python
if any(w in msg for w in ["fix script", "auto fix", "แก้ script"]):
    return {"action": "auto_fix_script", ...}
if any(w in msg for w in ["why fail", "failure", "root cause", "ทำไม fail"]):
    return {"action": "classify_failure", ...}
if any(w in msg for w in ["locator", "self-heal", "element not found"]):
    return {"action": "suggest_self_healing", ...}
if any(w in msg for w in ["test data", "boundary data"]):
    return {"action": "generate_test_data", ...}
if any(w in msg for w in ["generate script", "automation script", "playwright", "robot framework"]):
    framework = "robot" if "robot" in msg else "playwright"  # default: playwright
    return {"action": "generate_script_from_spec", "framework": framework, ...}
```

**Known limitation, accepted for now:** regex keyword matching doesn't scale indefinitely — as more agents/tools are added, natural-language phrasing will increasingly collide or get misclassified. Two alternatives were considered and explicitly deferred as tech debt rather than built now:

- **Approach B — LLM-based intent classification:** call Claude to classify intent as structured output instead of regex. More robust to phrasing variance; adds one LLM call (latency + cost) per message.
- **Approach C — native Claude tool-use:** replace the whole custom dispatch loop with the Anthropic SDK's tool-use loop, letting Claude pick the tool natively. Architecturally the "correct" long-term shape (and closer to the original spec's "Claude Agent SDK" framing), but requires rewriting the orchestrator and re-exposing every existing Manual QA Agent method as a tool definition — too large a change to bundle into this phase without risking Phase 1 regressions.

Revisit B or C when a third agent (Security QA) is added and keyword collisions become a real problem, not preemptively.

---

## 6. Database schema

Extends the `automation_scripts` table already sketched in the original design spec with one new column:

```sql
automation_scripts (
  id, story_id, test_case_id, framework ENUM(playwright, robot),
  content TEXT, health_status ENUM(healthy, flaky, broken),
  last_run_at, failure_root_cause VARCHAR,
  ci_run_url TEXT,        -- new: link to the GitHub Actions/GitLab CI run that was analyzed
  created_at
)
```

---

## 7. Mock mode

`MOCK_MODE` extends to cover every `AutomationQAAgent` tool, following the exact pattern already built for `ManualQAAgent` — real Jira/GitHub data is fetched best-effort and blended into `[MOCK]`-labeled fixture output, so demos work without a real `ANTHROPIC_API_KEY` (which is currently pending approval — see project memory).

---

## 8. UX/UI direction

Full report produced by a parallel research pass over the existing frontend codebase (verified against actual `package.json`, `Dashboard.tsx`, `TestCasePanel.tsx`, `tailwind.config.js` — not assumed):

### Current state (verified)
- **Stack reality check:** `package.json` has React 19, Tailwind, `class-variance-authority`, `clsx`, `lucide-react`, `axios`, `react-router-dom` — but no shadcn/ui components are actually wired up, and neither Recharts nor React Flow exist yet, despite both being named in the original spec. Phase 2 adds both as new dependencies.
- **Layout:** `Dashboard.tsx` is a single `grid grid-cols-2` with a static logo bar — no router-driven pages exist yet even though `react-router-dom` is installed.
- **Visual language:** white cards (`bg-white rounded-lg border`), `slate` neutrals for chrome/text, semantic Tailwind color-100/700 pairs for status badges (e.g. `bg-blue-100 text-blue-700`), tight `text-xs`/`text-sm` type scale, no shadows beyond `border`.
- **Color tokens:** shadcn CSS variables exist in `index.css` but components use raw Tailwind classes directly. Phase 2 follows this established raw-Tailwind pattern rather than switching to CSS-variable tokens mid-project.

### Navigation & layout (foundational change)
At 5 panels, the 2-column grid breaks. **Recommendation: left icon-rail sidebar + tab bar, not routes-per-page** — Chat is the product's spine (results should appear beside it, not on a page that navigates away), so a full-page-per-panel router would orphan the chat context that the WebSocket design assumes stays live.

```
┌────────────────────────────────────────────────────────┐
│ [QA] QA Brain                          AI-Powered QE    │
├───┬──────────────────────┬───────────────────────────────┤
│ 💬│                      │  [Test Cases] [Risk] [OWASP]  │
│ ✓ │     ChatPanel        │  [Traceability]                │
│ 📊│   (fixed, ~40%)      │  ┌───────────────────────────┐ │
│ 🛡│                      │  │  active panel (~60%)       │ │
│ 🔀│                      │  └───────────────────────────┘ │
└───┴──────────────────────┴───────────────────────────────┘
```
- Left rail: 4 icon buttons (lucide-react `MessageSquare`, `ListChecks`, `Gauge`, `ShieldAlert`, `Share2`), active state `bg-slate-800 text-white`.
- Right region keeps a tab bar (reusing the existing pill-button pattern from `TestCasePanel`'s type filters) to switch Test Cases / Release Risk / OWASP / Traceability without losing the Chat pane.
- Route-level: one `/dashboard` route, tab state in a query param (`?panel=risk`) via `react-router-dom` (already installed, unused) for deep-linkability.
- **Tradeoff:** this hybrid is more custom code than plain shadcn `Tabs`, but keeps chat permanently visible. A plain 5-tab layout (Chat as just another tab) is the simpler fallback if a reviewer prefers it, at the cost of the "chat drives everything" UX.

### Release Risk Dashboard
Recharts `RadialBarChart` (4 concentric rings: manual/automation/security + bold outer ring for overall), not a custom SVG gauge (no free tooltip/accessibility) or `PieChart` (implies part-of-whole; a score-vs-100 is a magnitude).
```
┌─────────────────────────────────────────┐
│  Release Risk                 [GO ●]     │
│      ╭───────────╮        Overall: 82    │
│      │  ◔ ◑ ◕     │        Manual:    88 │
│      │   82        │        Automation: 74│
│      ╰───────────╯        Security:   79 │
└─────────────────────────────────────────┘
```
Color system extends the existing raw-Tailwind convention (same three-tier semantics as `PRIORITY_COLORS`, applied to scores):

| Meaning | Class |
|---|---|
| Go | `bg-green-100 text-green-700 border-green-200` |
| Conditional | `bg-yellow-100 text-yellow-700` |
| No-Go | `bg-red-100 text-red-700` |
| Score ≥80 | `text-green-600` / stroke `#16a34a` |
| Score 50–79 | `text-yellow-600` / stroke `#ca8a04` |
| Score <50 | `text-red-600` / stroke `#dc2626` |

New files: `components/RiskDashboard/RiskDashboard.tsx`, `RiskGauge.tsx`, `GoNoGoBadge.tsx`.

### OWASP Coverage panel
A real grid heatmap built from Tailwind divs/table cells — not a chart-library heatmap (Recharts has no heatmap primitive; a third viz lib isn't justified for one panel) and not a plain uncolored table. A `<table>` with color-coded `<td>` cells gives real table semantics for screen readers, unlike a canvas-based heatmap.
```
                Auth   Payment  Profile  Search  Admin
A01 Broken Acc   ■       ■        ▢        ▢       ■
A02 Crypto Fail  ▢       ■        ■        ▢       ▢
A03 Injection    ■       ■        ▢        ■       ■
```
Each cell is a keyboard-focusable `button`, ~32×32px min, with a hover tooltip ("3/5 test cases · last updated..."). Row/column headers sticky for horizontal scroll on smaller screens.

Coverage-% color scale (kept distinct from risk-severity red/green to avoid overloading meaning):

| Coverage | Class |
|---|---|
| 0% (gap) | `bg-red-200` + small dot icon (not color alone) |
| 1–49% | `bg-orange-200` |
| 50–79% | `bg-yellow-200` |
| 80–100% | `bg-green-200` |
| N/A | `bg-slate-100` diagonal hatch |

New files: `components/OwaspCoverage/OwaspCoverage.tsx`, `CoverageCell.tsx`, `CoverageLegend.tsx`.

### Traceability Graph
React Flow, per the original spec — the one panel where a new dependency is genuinely unavoidable (Recharts cannot do node-link graphs). Layout via `dagre` (left-to-right layered: `Story → Test Case → Script → Defect`) rather than a force-directed layout, since traceability is an inherently staged DAG that force layout would make illegible.

Custom node types styled consistent with the existing card look:
- Story: rounded slate card, `FileText` icon
- Test Case: colored left-border matching the existing `TYPE_COLORS` from `TestCasePanel` (functional=blue, security=purple, etc.)
- Script: `Code` icon, `healthy/flaky/broken` badge using the same 3-tier green/yellow/red
- Defect: `Bug` icon, red-bordered if open, slate if fixed

Edges: solid for confirmed links, dashed for AI-inferred/unconfirmed links. Lives as a tab alongside Risk/OWASP (not a modal — graphs need real estate). Default zoom-to-fit; click-node-to-filter dims unrelated branches.

New files: `components/TraceabilityGraph/TraceabilityGraph.tsx`, `nodes/StoryNode.tsx`, `nodes/TestCaseNode.tsx`, `nodes/ScriptNode.tsx`, `nodes/DefectNode.tsx`, `layout.ts` (dagre wrapper).

### New frontend dependencies
`recharts`, `@xyflow/react` (React Flow's current package name), `@dagrejs/dagre`.

---

## 9. Testing approach

Mirror Phase 1's TDD pattern exactly (per `superpowers:test-driven-development` and the existing `test_manual_qa_agent.py`/`test_jira_client.py` structure):
- `tests/test_github_client.py` — mock `httpx`, verify normalized output shape, mirrors `test_jira_client.py`.
- `tests/test_automation_qa_agent.py` — mock `self._client.messages.create` and `self._github`/`httpx` calls, one test per tool, mirrors `test_manual_qa_agent.py`.
- Extend `tests/test_orchestrator.py` with new intent-classification cases for the 5 new keyword rules, including at least one collision-avoidance test (a message containing "generate" that should still route to `generate_test_cases`, not `generate_script_from_spec`).

---

## 10. Explicitly out of scope for this phase

- `explore_and_generate` (headless-browser UI crawling) — deferred, no infra for it exists.
- Real MCP protocol servers (per original spec §4) — Phase 1 established plain HTTP clients instead, and this phase continues that pattern.
- LLM-based or native-tool-use orchestrator routing (Approaches B/C in §5) — logged as tech debt, revisit when a third agent is added.
- Writing `docs/automation-standards.md` content — mechanism is built, content is the user's/team's to write.
- Security QA Agent — separate spec, not bundled here (see project memory: user chose to scope Automation QA Agent first).
