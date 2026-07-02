# Security QA Agent — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already-shipped Security QA Agent backend (7 tools, all reachable via chat, plus `GET /api/stories/{id}/security-findings`) visible and usable in the existing React dashboard — chat feedback for every security action, plus an OWASP Coverage heatmap panel whose data shape matches the persisted `security_findings` table. **Known limitation:** in this plan the panel is populated only from live WebSocket events, not from a `GET /api/stories/{id}/security-findings` fetch, so coverage data does not survive a page refresh — see Task 1 Step 5.

**Architecture:** Extend the existing `useAgentChat` hook and add a third tab to `Dashboard.tsx`'s existing tab-button row exactly as already done for `Scripts` — no new state-management approach, no new component conventions, no icon-rail redesign. Add one new panel family (`OwaspCoverage`/`CoverageCell`/`CoverageLegend`, per the design spec's exact naming) that renders a `<table>`-based heatmap of stories × OWASP category from `security_findings`, colored by coverage status. RBAC matrix, API security checklist, vulnerability triage, and security defect results have no dedicated panel — they render inline in chat as formatted text, mirroring the existing `formatHealing`/`formatClassification`/etc. pattern already built for the Automation QA Agent's one-shot outputs. `write_security_defect`'s Jira ticket link is the one output that needs a real clickable `<a>` tag rather than plain text, so `Message` gains a small optional `link` field and `MessageBubble` gains matching render logic — done once, without a Markdown dependency.

**Scope decision:** The design spec (§7) explicitly confirms the icon-rail sidebar sketched in the original Automation Agent design doc was never built, and that extending the current tab-button pattern with a third button is the right move — reviving that unbuilt redesign now (with only 3 panels total) is out of scope. This plan does exactly what the design spec asks: types + API client, chat feedback for all 7 actions, the `OwaspCoverage` panel family in the exact shape `security_findings` stores, and a third tab button.

**Tech Stack:** React 19 + TypeScript + Vite, matching the existing frontend exactly. No new dependencies — the heatmap uses raw Tailwind `<table>`/`<td>` markup, not a charting library.

## Global Constraints

- No new npm dependencies — the heatmap uses raw Tailwind divs/table cells, not a charting library (design spec §7, "New frontend dependencies: None").
- XSS-safe rendering — no `dangerouslySetInnerHTML` anywhere, matching the existing convention confirmed by the Automation Agent's final review. All dynamic content (chat text, table cells) renders through JSX text interpolation only.
- Match existing conventions exactly: raw Tailwind utility classes (not shadcn components), the `TYPE_COLORS`/`PRIORITY_COLORS`-style lookup-object pattern for badges, optimistic client-side state updates from WebSocket payloads (no REST refetch needed for data that already arrived over the socket) — the same convention the Automation Agent frontend plan established for `scripts`.
- The Chat panel must remain visible at all times — never replace it with a routed page.
- No icon-rail sidebar redesign — extend the current tab-button pattern only (design spec §7, §9; explicitly rejected as out of scope for this phase).
- RBAC matrix, vulnerability triage, and security defect results render inline in chat only — no dedicated panel, no persistence beyond the chat transcript (design spec §7, §9).
- Design spec: `docs/superpowers/specs/2026-07-02-security-qa-agent-design.md`. Heatmap grid/color-scale spec inherited from `docs/superpowers/specs/2026-07-02-automation-qa-agent-design.md` §8 (component names `OwaspCoverage.tsx`, `CoverageCell.tsx`, `CoverageLegend.tsx` are carried over verbatim per the Security spec §7).
- Backend plan (already shipped): `docs/superpowers/plans/2026-07-02-security-qa-agent-backend.md`. The orchestrator's `orchestrator_done` events for security actions carry these `data` keys (verified against `qa-brain/backend/app/agents/orchestrator.py`): `owasp_test_cases` + `story_id` (generate_owasp_test_cases), `owasp_mapping` + `story_id` (map_story_to_owasp), `rbac_matrix` (generate_rbac_matrix), `api_security_checklist` (generate_api_security_checklist), `triage` (triage_vulnerabilities), `security_defect` (write_security_defect), `owasp_dashboard` (build_owasp_dashboard). The REST endpoint `GET /api/stories/{jira_id}/security-findings` (verified against `qa-brain/backend/app/api/security.py`) returns a JSON array of objects with keys `id`, `story_id`, `owasp_category`, `status` (`"covered" | "gap" | "not_applicable"`), `risk_level` (`"critical" | "high" | "medium" | "low"`), `notes`, `created_at`.
- This project has no frontend test framework. Each task's verification step is `npm run build` (TypeScript compilation) passing cleanly, plus manual/code-reading review — not automated test evidence.

---

## Task 1: Types & API Client for Security Findings

**Files:**
- Modify: `qa-brain/frontend/src/lib/types.ts`
- Modify: `qa-brain/frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `SecurityFinding` interface, `OwaspTestCase` interface (distinct from `TestCase` — see Step 1), extended `AgentEvent["data"]` shape (7 new optional keys), extended `Message` interface (new optional `link` field), `getStorySecurityFindings(jiraId): Promise<SecurityFinding[]>`

- [ ] **Step 1: Add the `SecurityFinding` interface to `qa-brain/frontend/src/lib/types.ts`**

Add this interface (place it after the existing `AutomationScript` interface, before `AgentEvent`):

```typescript
export interface SecurityFinding {
  id: string;
  story_id: string;
  owasp_category: string;
  status: "covered" | "gap" | "not_applicable";
  risk_level: "critical" | "high" | "medium" | "low";
  notes: string;
  created_at: string;
}

export interface OwaspTestCase {
  title: string;
  type: "security";
  owasp_category: string;
  steps: string[];
  expected_result: string;
  priority: "high" | "medium" | "low";
}
```

`OwaspTestCase` is intentionally **not** `TestCase` — the orchestrator's `generate_owasp_test_cases` action yields the raw dicts returned by `SecurityQAAgent.generate_owasp_test_cases` (verified against `qa-brain/backend/app/agents/security_qa.py`'s prompt schema and `orchestrator.py` line 183), which only ever have `title, type, owasp_category, steps, expected_result, priority`. They never carry `id`, `story_id`, `source`, or `created_at`, and `owasp_category` is not a field on `TestCase` at all. Declaring this payload as `TestCase[]` would silently accept a lie about its shape.

- [ ] **Step 2: Extend the `AgentEvent["data"]` shape in `qa-brain/frontend/src/lib/types.ts`**

Replace the existing `AgentEvent` interface:

```typescript
export interface AgentEvent {
  type: "agent_start" | "stream_delta" | "agent_complete" | "orchestrator_done";
  agent?: string;
  message?: string;
  delta?: string;
  data?: {
    test_cases?: TestCase[];
    analysis?: Record<string, unknown>;
    traceability?: Record<string, string[]>;
    release_score?: ReleaseScore;
    gaps?: Record<string, unknown>;
    story_id?: string;
    message?: string;
    script?: { framework: "playwright" | "robot"; content: string };
    formatted_script?: { content: string };
    healing?: { alternatives: string[]; strategy: string };
    classification?: { root_cause: string; explanation: string; failed_step: string };
    fix?: { content: string; explanation: string };
    test_data?: { label: string; value: string }[];
    traceability_mapping?: { story_id: string; covers_acceptance_criteria: boolean; confidence: string; notes: string };
  };
}
```

with:

```typescript
export interface AgentEvent {
  type: "agent_start" | "stream_delta" | "agent_complete" | "orchestrator_done";
  agent?: string;
  message?: string;
  delta?: string;
  data?: {
    test_cases?: TestCase[];
    analysis?: Record<string, unknown>;
    traceability?: Record<string, string[]>;
    release_score?: ReleaseScore;
    gaps?: Record<string, unknown>;
    story_id?: string;
    message?: string;
    script?: { framework: "playwright" | "robot"; content: string };
    formatted_script?: { content: string };
    healing?: { alternatives: string[]; strategy: string };
    classification?: { root_cause: string; explanation: string; failed_step: string };
    fix?: { content: string; explanation: string };
    test_data?: { label: string; value: string }[];
    traceability_mapping?: { story_id: string; covers_acceptance_criteria: boolean; confidence: string; notes: string };
    owasp_test_cases?: OwaspTestCase[];
    owasp_mapping?: { owasp_category: string; status: "covered" | "gap" | "not_applicable"; risk_level: "critical" | "high" | "medium" | "low"; notes: string }[];
    rbac_matrix?: { roles: string[]; matrix: { boundary: string; access: Record<string, string> }[] };
    api_security_checklist?: { broken_access: string[]; injection: string[]; auth: string[] };
    triage?: { prioritized: { finding: string; severity: string; cvss_estimate: number }[]; false_positives: string[] };
    security_defect?: { report: string; impact: string; cvss_score: number; evidence: string; jira_id: string; url: string };
    owasp_dashboard?: { sprint_id: string; coverage_by_category: Record<string, number>; summary: string };
  };
}
```

- [ ] **Step 3: Add a `link` field to the `Message` interface in `qa-brain/frontend/src/lib/types.ts`**

`write_security_defect`'s result must render the created Jira ticket as a clickable link (design spec §7). This codebase has no Markdown renderer and Global Constraints forbid `dangerouslySetInnerHTML`, so a real link needs a dedicated field on `Message` rather than being embedded as Markdown syntax inside the plain-text `content` string. Replace the existing `Message` interface:

```typescript
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agentEvents?: AgentEvent[];
}
```

with:

```typescript
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agentEvents?: AgentEvent[];
  link?: { label: string; url: string };
}
```

- [ ] **Step 4: Add `getStorySecurityFindings` to `qa-brain/frontend/src/lib/api.ts`**

Replace the existing import line:

```typescript
import type { TestCase, AutomationScript } from "./types";
```

with:

```typescript
import type { TestCase, AutomationScript, SecurityFinding } from "./types";
```

Add this function at the end of the file, after `getStoryScripts`:

```typescript
export async function getStorySecurityFindings(jiraId: string): Promise<SecurityFinding[]> {
  const { data } = await api.get<SecurityFinding[]>(`/api/stories/${jiraId}/security-findings`);
  return data;
}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors. `getStorySecurityFindings` isn't called from anywhere in this plan — the `OwaspCoverage` panel is populated optimistically from WebSocket `owasp_mapping` events (Task 2), mirroring how `getStoryScripts` in the Automation Agent plan also type-checks without being called; it exists so the REST endpoint built in the backend plan has a typed client method available for future use (e.g. loading a story's findings on page refresh). `Message.link` isn't produced anywhere yet either — it will be used starting Task 2.

**Known limitation:** because `getStorySecurityFindings` is never called, the `OwaspCoverage` panel this plan builds is fed exclusively by transient, in-memory WebSocket state (`findings` in `useAgentChat`, Task 2) — not by the persisted `security_findings` table this REST endpoint reads from. A page refresh loses all coverage data even though the DB table and endpoint exist specifically to survive one. This satisfies the design spec's "wired to real `security_findings` data" (§7) only in the sense that the *shape* of the data matches what the table stores — the panel does not yet read the table back, so coverage does not persist across reloads. Wiring an initial `getStorySecurityFindings` fetch on mount (e.g. once a story ID is known) would close this gap, but doing so is not required by this plan's stated scope and is called out here explicitly rather than left as an implicit shortcut.

- [ ] **Step 6: Commit**

```bash
git add src/lib/types.ts src/lib/api.ts
git commit -m "feat: add SecurityFinding type, Message.link field, and API client for security-findings endpoint"
```

---

## Task 2: Chat Feedback for Security QA Actions

**Files:**
- Modify: `qa-brain/frontend/src/hooks/useAgentChat.ts`

**Interfaces:**
- Consumes: the extended `AgentEvent["data"]` shape from Task 1
- Produces: `useAgentChat` now also returns `findings: SecurityFinding[]` (optimistically populated from WebSocket `owasp_mapping` events, mirroring how `scripts` is already populated from `script` events)

- [ ] **Step 1: Extend the type import in `qa-brain/frontend/src/hooks/useAgentChat.ts`**

Replace:

```typescript
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript } from "../lib/types";
```

with:

```typescript
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript, SecurityFinding } from "../lib/types";
```

`OwaspTestCase` (Task 1) does not need to be imported here — per Step 3 below, its `owasp_category` field is intentionally discarded when mapping into `TestCase`-shaped state, so the handler only needs the already-imported `TestCase`.

- [ ] **Step 2: Add the `findings` state**

Add this state variable alongside the existing ones (after `const [scripts, setScripts] = useState<AutomationScript[]>([]);`):

```typescript
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
```

- [ ] **Step 3: Add the 7 security event handlers inside the `orchestrator_done` block**

Inside the `if (event.type === "orchestrator_done")` block, after the existing `if (data.traceability_mapping) { ... }` check, add:

```typescript
        if (data.owasp_test_cases && data.owasp_test_cases.length > 0 && data.story_id) {
          const storyId = data.story_id;
          setTestCases((prev) => [
            ...prev,
            ...data.owasp_test_cases!.map(
              (tc): TestCase => ({
                id: crypto.randomUUID(),
                story_id: storyId,
                title: `${tc.title} [${tc.owasp_category}]`,
                type: tc.type,
                steps: tc.steps,
                expected_result: tc.expected_result,
                priority: tc.priority,
                source: "ai_generated",
                created_at: new Date().toISOString(),
              })
            ),
          ]);
          appendAssistantMessage(`สร้าง ${data.owasp_test_cases.length} OWASP test cases สำเร็จ ✓`);
        }
```

The payload is `OwaspTestCase[]` (Task 1), not `TestCase[]` — it never carries `id`/`story_id`/`source`/`created_at`, so this handler synthesizes them explicitly rather than falling back on fields that will never be present. `owasp_category` has no home on `TestCase`, so rather than silently dropping it, it's folded into the visible `title` (e.g. `"Reject unauthenticated access [A01:2021-Broken Access Control]"`) so the OWASP category stays visible in the existing `TestCasePanel` UI, which only renders `TestCase` fields.

```typescript
        if (data.owasp_mapping && data.story_id) {
          setFindings((prev) => [
            ...prev,
            ...data.owasp_mapping!.map((finding) => ({
              id: crypto.randomUUID(),
              story_id: data.story_id as string,
              owasp_category: finding.owasp_category,
              status: finding.status,
              risk_level: finding.risk_level,
              notes: finding.notes,
              created_at: new Date().toISOString(),
            })),
          ]);
          appendAssistantMessage(formatOwaspMapping(data.story_id, data.owasp_mapping));
        }
        if (data.rbac_matrix) {
          appendAssistantMessage(formatRbacMatrix(data.rbac_matrix));
        }
        if (data.api_security_checklist) {
          appendAssistantMessage(formatApiSecurityChecklist(data.api_security_checklist));
        }
        if (data.triage) {
          appendAssistantMessage(formatTriage(data.triage));
        }
        if (data.security_defect) {
          const isMock = data.security_defect.url === "[MOCK]";
          appendAssistantMessage(
            formatSecurityDefect(data.security_defect),
            isMock ? undefined : { label: data.security_defect.jira_id, url: data.security_defect.url }
          );
        }
        if (data.owasp_dashboard) {
          appendAssistantMessage(formatOwaspDashboard(data.owasp_dashboard));
        }
```

- [ ] **Step 4: Extend `appendAssistantMessage` to accept an optional clickable link**

`write_security_defect`'s result must render the created Jira ticket as a real clickable link (design spec §7), not as Markdown text (this codebase has no Markdown renderer). Find the existing `appendAssistantMessage` function:

```typescript
  const appendAssistantMessage = (content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content, timestamp: new Date() },
    ]);
  };
```

Replace it with:

```typescript
  const appendAssistantMessage = (content: string, link?: { label: string; url: string }) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content, timestamp: new Date(), link },
    ]);
  };
```

- [ ] **Step 5: Update the hook's return statement**

Replace:

```typescript
  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts };
```

with:

```typescript
  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings };
```

- [ ] **Step 6: Add the 6 new formatting helper functions**

Add these at the bottom of the file, alongside the existing `formatHealing`/`formatClassification`/etc.:

```typescript
function formatOwaspMapping(
  storyId: string,
  mapping: { owasp_category: string; status: "covered" | "gap" | "not_applicable"; risk_level: "critical" | "high" | "medium" | "low"; notes: string }[]
): string {
  const icons: Record<string, string> = { covered: "✅", gap: "⚠️", not_applicable: "➖" };
  const lines = mapping.map((m) => `${icons[m.status] || "•"} **${m.owasp_category}** (${m.status}, risk: ${m.risk_level}) — ${m.notes}`);
  return `🛡️ OWASP mapping for ${storyId}:\n\n${lines.join("\n")}`;
}

function formatRbacMatrix(rbac: { roles: string[]; matrix: { boundary: string; access: Record<string, string> }[] }): string {
  const header = `Roles: ${rbac.roles.length > 0 ? rbac.roles.join(", ") : "not specified"}`;
  const rows = rbac.matrix.map((row) => {
    // Fall back to the row's own access keys when `roles` is empty — the live
    // orchestrator always calls generate_rbac_matrix(roles=[], ...) (see note below),
    // so `rbac.roles` is empty in every real chat-triggered call today, and mapping
    // over it would silently drop every row's access data.
    const roleNames = rbac.roles.length > 0 ? rbac.roles : Object.keys(row.access);
    const access = roleNames.map((role) => `${role}: ${row.access[role] || "?"}`).join(", ");
    return `- **${row.boundary}** — ${access}`;
  });
  return `🔐 RBAC test matrix:\n\n${header}\n\n${rows.join("\n")}`;
}

function formatApiSecurityChecklist(checklist: { broken_access: string[]; injection: string[]; auth: string[] }): string {
  const section = (title: string, items: string[]) => `**${title}:**\n${items.map((i) => `- ${i}`).join("\n")}`;
  return `📋 API Security Checklist:\n\n${section("Broken Access Control", checklist.broken_access)}\n\n${section("Injection", checklist.injection)}\n\n${section("Authentication", checklist.auth)}`;
}

function formatTriage(triage: { prioritized: { finding: string; severity: string; cvss_estimate: number }[]; false_positives: string[] }): string {
  const prioritized = triage.prioritized.map((p) => `- [${p.severity.toUpperCase()}] ${p.finding} (CVSS est. ${p.cvss_estimate})`).join("\n");
  const falsePositives = triage.false_positives.length > 0 ? `\n\n**Likely false positives:**\n${triage.false_positives.map((f) => `- ${f}`).join("\n")}` : "";
  return `🚨 Vulnerability triage:\n\n${prioritized}${falsePositives}`;
}

function formatSecurityDefect(defect: { report: string; impact: string; cvss_score: number; evidence: string; jira_id: string; url: string }): string {
  return `🐛 Security defect created: ${defect.jira_id}\n\n**Report:** ${defect.report}\n\n**Impact:** ${defect.impact}\n\n**CVSS Score:** ${defect.cvss_score}\n\n**Evidence:** ${defect.evidence}`;
}

function formatOwaspDashboard(dashboard: { sprint_id: string; coverage_by_category: Record<string, number>; summary: string }): string {
  const rows = Object.entries(dashboard.coverage_by_category).map(([category, pct]) => `- ${category}: ${pct}%`).join("\n");
  return `📊 OWASP Dashboard — ${dashboard.sprint_id}:\n\n${rows}\n\n${dashboard.summary}`;
}
```

**Known behavior gap (`formatRbacMatrix`):** the live orchestrator calls `self._security_qa.generate_rbac_matrix(roles=[], feature_description=requirements)` unconditionally (verified against `qa-brain/backend/app/agents/orchestrator.py` line 198) — `roles` is never parsed from the user's chat message today, despite the design doc's routing table implying roles are user-specified. This means `rbac.roles` will be an empty array in every real, non-test invocation. `formatRbacMatrix` above degrades gracefully instead of silently rendering blank output: the header falls back to `"not specified"`, and each row falls back to its own `access` object's keys (rather than mapping over the empty `roles` array and losing every row's data). The underlying empty-`roles` behavior is a backend orchestrator limitation outside this frontend plan's scope to fix — noted here as a known display quirk rather than left implicit.

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 8: Commit**

```bash
git add src/hooks/useAgentChat.ts
git commit -m "feat: chat feedback for all 7 Security QA Agent actions"
```

---

## Task 3: Render Clickable Links in Chat Messages

**Files:**
- Modify: `qa-brain/frontend/src/components/ChatPanel/MessageBubble.tsx`

**Interfaces:**
- Consumes: `Message.link` (Task 1, `{ label: string; url: string } | undefined`)

- [ ] **Step 1: Render the optional link in `qa-brain/frontend/src/components/ChatPanel/MessageBubble.tsx`**

Replace the full file:

```typescript
import type { Message } from "../../lib/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-slate-800 text-white"
            : "bg-white border border-slate-200 text-slate-800"
        }`}
      >
        {message.content}
        {message.link && (
          <div className="mt-2">
            <a
              href={message.link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-xs font-medium text-blue-600 hover:text-blue-800 underline"
            >
              {message.link.label} ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
```

This renders a real anchor tag via JSX (no `dangerouslySetInnerHTML`, no Markdown parsing) — satisfying the design spec's "renders the created Jira ticket as a clickable link" (§7) while staying within the XSS-safe-rendering constraint.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/ChatPanel/MessageBubble.tsx
git commit -m "feat: render clickable links in chat messages (used by security defect Jira tickets)"
```

---

## Task 4: CoverageLegend Component

**Files:**
- Create: `qa-brain/frontend/src/components/OwaspCoverage/CoverageLegend.tsx`

**Interfaces:**
- Produces: `CoverageLegend` component, named export, no props

- [ ] **Step 1: Write `qa-brain/frontend/src/components/OwaspCoverage/CoverageLegend.tsx`**

This implements the coverage-% color scale from the Automation Agent design doc §8 (kept distinct from risk-severity red/green to avoid overloading meaning), adapted to the three finding statuses this backend actually produces (`covered`/`gap`/`not_applicable` — there is no live scanner-driven percentage in this phase's `security_findings` table, so the legend documents per-cell status rather than a 0–100% scale, which only exists in the separate chat-only `owasp_dashboard` summary):

```typescript
const LEGEND_ITEMS = [
  { label: "Covered", className: "bg-green-200" },
  { label: "Gap", className: "bg-red-200" },
  { label: "Not applicable", className: "bg-slate-100" },
  { label: "No data", className: "bg-white border border-dashed border-slate-300" },
];

export function CoverageLegend() {
  return (
    <div className="flex items-center gap-3 flex-wrap text-xs text-slate-600">
      {LEGEND_ITEMS.map((item) => (
        <div key={item.label} className="flex items-center gap-1">
          <span className={`inline-block h-3 w-3 rounded ${item.className}`} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/OwaspCoverage/CoverageLegend.tsx
git commit -m "feat: CoverageLegend component for OWASP coverage color scale"
```

---

## Task 5: CoverageCell Component

**Files:**
- Create: `qa-brain/frontend/src/components/OwaspCoverage/CoverageCell.tsx`

**Interfaces:**
- Consumes: `SecurityFinding` (Task 1's type)
- Produces: `CoverageCell` component, named export, props `{ finding: SecurityFinding | null }`

- [ ] **Step 1: Write `qa-brain/frontend/src/components/OwaspCoverage/CoverageCell.tsx`**

Each cell is a keyboard-focusable `button` per the design spec's heatmap spec, ~32×32px min, with a hover tooltip via the native `title` attribute (no new dependency needed for tooltips), colored by `status`:

```typescript
import type { SecurityFinding } from "../../lib/types";

const STATUS_COLORS: Record<string, string> = {
  covered: "bg-green-200 hover:bg-green-300",
  gap: "bg-red-200 hover:bg-red-300",
  not_applicable: "bg-slate-100 hover:bg-slate-200",
};

const STATUS_SYMBOLS: Record<string, string> = {
  covered: "■",
  gap: "□",
  not_applicable: "–",
};

interface CoverageCellProps {
  finding: SecurityFinding | null;
}

export function CoverageCell({ finding }: CoverageCellProps) {
  if (!finding) {
    return (
      <td className="p-0.5">
        <button
          type="button"
          disabled
          title="No data"
          className="h-8 w-8 min-h-8 min-w-8 rounded bg-white border border-dashed border-slate-300 text-slate-300 text-xs"
        >
          {"·"}
        </button>
      </td>
    );
  }

  const tooltip = `${finding.owasp_category} — ${finding.status} (risk: ${finding.risk_level})\n${finding.notes}`;

  return (
    <td className="p-0.5">
      <button
        type="button"
        title={tooltip}
        className={`h-8 w-8 min-h-8 min-w-8 rounded text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 ${
          STATUS_COLORS[finding.status] || "bg-slate-100"
        }`}
      >
        {STATUS_SYMBOLS[finding.status] || "?"}
      </button>
    </td>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/OwaspCoverage/CoverageCell.tsx
git commit -m "feat: CoverageCell component for OWASP coverage heatmap"
```

---

## Task 6: OwaspCoverage Panel Component

**Files:**
- Create: `qa-brain/frontend/src/components/OwaspCoverage/OwaspCoverage.tsx`

**Interfaces:**
- Consumes: `SecurityFinding` (Task 1's type), `CoverageCell` (Task 5), `CoverageLegend` (Task 4)
- Produces: `OwaspCoverage` component, named export, props `{ findings: SecurityFinding[] }`

- [ ] **Step 1: Write `qa-brain/frontend/src/components/OwaspCoverage/OwaspCoverage.tsx`**

This builds the grid of stories (rows) × OWASP category (columns) from the Automation Agent design doc §8's heatmap spec — a real `<table>` with color-coded `<td>` cells for screen-reader table semantics, sticky row/column headers for horizontal scroll on smaller screens:

```typescript
import type { SecurityFinding } from "../../lib/types";
import { CoverageCell } from "./CoverageCell";
import { CoverageLegend } from "./CoverageLegend";

interface OwaspCoverageProps {
  findings: SecurityFinding[];
}

export function OwaspCoverage({ findings }: OwaspCoverageProps) {
  const storyIds = Array.from(new Set(findings.map((f) => f.story_id))).sort();
  const categories = Array.from(new Set(findings.map((f) => f.owasp_category))).sort();

  const findingFor = (storyId: string, category: string): SecurityFinding | null =>
    findings.find((f) => f.story_id === storyId && f.owasp_category === category) || null;

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border">
      <div className="px-4 py-3 border-b space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-800">OWASP Coverage</h2>
          <span className="text-xs text-slate-500">{storyIds.length} stories mapped</span>
        </div>
        <CoverageLegend />
      </div>

      <div className="flex-1 overflow-auto">
        {storyIds.length === 0 ? (
          <p className="text-center text-slate-400 text-sm py-8">
            ยังไม่มี OWASP mapping — ลอง "map story to owasp for PROJ-123" จาก chat
          </p>
        ) : (
          <table className="border-collapse w-full">
            <thead>
              <tr>
                <th className="sticky top-0 left-0 z-20 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b border-r">
                  Story
                </th>
                {categories.map((category) => (
                  <th
                    key={category}
                    className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b whitespace-nowrap"
                  >
                    {category}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {storyIds.map((storyId) => (
                <tr key={storyId}>
                  <th className="sticky left-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-700 border-r whitespace-nowrap">
                    {storyId}
                  </th>
                  {categories.map((category) => (
                    <CoverageCell key={category} finding={findingFor(storyId, category)} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/OwaspCoverage/OwaspCoverage.tsx
git commit -m "feat: OwaspCoverage panel component — heatmap of stories x OWASP category"
```

---

## Task 7: Wire OWASP Tab into Dashboard

**Files:**
- Modify: `qa-brain/frontend/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: `OwaspCoverage` (Task 6), `useAgentChat`'s new `findings` return value (Task 2)

- [ ] **Step 1: Replace `qa-brain/frontend/src/pages/Dashboard.tsx` with the 3-tab version**

```typescript
import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel/ChatPanel";
import { TestCasePanel } from "../components/TestCasePanel/TestCasePanel";
import { ScriptsPanel } from "../components/ScriptsPanel/ScriptsPanel";
import { OwaspCoverage } from "../components/OwaspCoverage/OwaspCoverage";
import { useAgentChat } from "../hooks/useAgentChat";

const SESSION_ID = crypto.randomUUID();
const PROJECT_ID = "proj-001";

type RightPanel = "test-cases" | "scripts" | "owasp";

export default function Dashboard() {
  const { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings } = useAgentChat(SESSION_ID, PROJECT_ID);
  const [rightPanel, setRightPanel] = useState<RightPanel>("test-cases");

  return (
    <div className="h-screen flex flex-col bg-slate-100">
      <header className="px-6 py-3 bg-white border-b flex items-center gap-3">
        <div className="h-8 w-8 rounded bg-slate-800 flex items-center justify-center">
          <span className="text-white text-xs font-bold">QA</span>
        </div>
        <span className="font-semibold text-slate-800">QA Brain</span>
        <span className="text-xs text-slate-400 ml-auto">AI-Powered Quality Engineering</span>
      </header>

      <main className="flex-1 grid grid-cols-2 gap-4 p-4 overflow-hidden">
        <ChatPanel messages={messages} activeAgent={activeAgent} onSend={sendMessage} />

        <div className="flex flex-col h-full min-h-0 gap-2">
          <div className="flex gap-1">
            <button
              onClick={() => setRightPanel("test-cases")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "test-cases" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              Test Cases ({testCases.length})
            </button>
            <button
              onClick={() => setRightPanel("scripts")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "scripts" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              Scripts ({scripts.length})
            </button>
            <button
              onClick={() => setRightPanel("owasp")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "owasp" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              OWASP ({findings.length})
            </button>
          </div>

          <div className="flex-1 min-h-0">
            {rightPanel === "test-cases" && <TestCasePanel testCases={testCases} releaseScore={releaseScore} />}
            {rightPanel === "scripts" && <ScriptsPanel scripts={scripts} />}
            {rightPanel === "owasp" && <OwaspCoverage findings={findings} />}
          </div>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Manual smoke test with the dev server**

```bash
cd qa-brain/frontend
npm run dev -- --port 5175 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5175/
```

Expected: `200`. Then stop the dev server (`kill %1` or the equivalent background-job command).

If a real browser check is available in the environment, additionally: log in, switch to the "OWASP" tab (should show the empty state), send a chat message like "map story to owasp for SCRUM-4" (backend must be running with `MOCK_MODE=true`), and confirm: (a) a formatted OWASP mapping message appears in chat, and (b) the OWASP tab count increments and the heatmap renders a row for SCRUM-4 with colored cells once you switch to it. Then try "generate an rbac matrix for the billing page" and confirm the RBAC matrix renders as inline chat text (no panel change) — note that because the live orchestrator always calls `generate_rbac_matrix(roles=[], ...)` (see Task 2 Step 6's known behavior gap), the rendered matrix's "Roles:" line will read "not specified" and per-boundary access will be keyed off whatever role names the mock/LLM output uses internally, regardless of which roles you mention in the chat message — this is expected, not a bug in this task's code. If no browser tool is available, skip this part and say so explicitly rather than fabricating a result — the TypeScript build and curl check are the objective gates for this task.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Dashboard.tsx
git commit -m "feat: add OWASP tab to Dashboard alongside Test Cases and Scripts"
```

---

## Explicitly Deferred

Per design spec §9 and §7:

- RBAC matrix / vulnerability triage / security defect output persistence — these remain one-shot chat outputs, not browsable collections, in this phase. No REST endpoint or DB table backs them; refreshing the page loses them (same as the Automation Agent's `test_data`, `healing`, `classification`, and `fix` outputs today).
- Any new charting library — the OWASP Coverage heatmap uses raw Tailwind `<table>`/`<td>` markup exactly as speced, no Recharts/D3/etc.
- The icon-rail sidebar navigation redesign — still unbuilt from the Automation Agent's speculative design; 3 tabs doesn't yet justify it (design spec §7, §9).
- A live 0–100% coverage-percent scale on the heatmap itself — `build_owasp_dashboard`'s `coverage_by_category` percentages are sprint-level aggregates surfaced only in chat (via `formatOwaspDashboard`); the heatmap's per-cell granularity is story × category status (`covered`/`gap`/`not_applicable`), which is what `security_findings` actually stores per §5 of the design spec. Revisit only if a future backend change adds per-cell percentage data.
- Real vulnerability scanner integration, `security_findings` persistence for triage/defect data, LLM-based orchestrator routing — all backend-side deferrals already logged in the backend plan; nothing in this frontend plan reopens them.
- Traceability Graph (React Flow + dagre) and Release Risk Dashboard (Recharts gauge) — out of scope for this plan; unrelated to the Security QA Agent and already deferred by the Automation Agent frontend plan pending their own backing data.
- **Known limitation carried forward (not a scope deferral, flagging for visibility):** `OwaspCoverage` in this plan is populated only from live WebSocket `owasp_mapping` events (Task 2), not from a `getStorySecurityFindings` fetch against the already-built `GET /api/stories/{id}/security-findings` endpoint (Task 1). Coverage data is therefore lost on page refresh even though the REST endpoint and `security_findings` table exist specifically to survive one. Wiring an initial fetch on mount would close this gap but is not included in this plan's task list — see Task 1 Step 5 for detail.
