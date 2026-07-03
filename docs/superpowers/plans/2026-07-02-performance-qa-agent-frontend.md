# Performance QA Agent — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Performance QA Agent backend (8 tools, all reachable via chat, plus `GET /api/stories/{jira_id}/performance-findings`) visible and usable in the existing React dashboard — chat feedback for every performance action, plus a `PerformancePanel` findings table whose data shape matches the persisted `performance_findings` table. **Known limitation carried over from the Security phase:** the panel is populated only from live WebSocket events, not from a `getStoryPerformanceFindings` fetch, so findings do not survive a page refresh — the design spec (§7) explicitly accepts this gap for symmetry with `getStorySecurityFindings` (written-but-unwired, already logged as deferred work).

**Architecture:** Extend the existing `useAgentChat` hook and add a fourth tab to `Dashboard.tsx`'s existing tab-button row exactly as already done for `Scripts` and `OWASP` — no new state-management approach, no new component conventions, no icon-rail redesign. Add one new single-file panel (`PerformancePanel`, per the design spec §7: "no sub-components needed at this data shape") that renders a `<table>` of persisted-shape findings grouped by story, with a severity chip column reusing the existing semantic palette. The other 7 tool outputs (workload model, script, result analysis, bottleneck, SLA/SLO, defect, capacity plan) have no dedicated panel — they render inline in chat as formatted text, mirroring the existing `formatHealing`/`formatOwaspMapping`/etc. pattern. `write_perf_defect`'s Jira ticket reuses the `Message.link` field and `MessageBubble` anchor rendering already built for `security_defect` — no `MessageBubble` change is needed in this plan.

**Scope decision:** The design spec (§7) prescribes exactly: types + API client, chat feedback for all 8 actions via new `orchestrator_done` data-key branches, a `PerformancePanel` in the exact shape `performance_findings` stores, and a fourth tab button extending the `RightPanel` union. Persisting or paneling the other 7 conversational outputs is explicitly out of scope (§5, §9).

**Tech Stack:** React 19, TypeScript, Tailwind CSS (no UI kit), Vite

## Global Constraints

- NO new npm dependencies — the findings table uses raw Tailwind `<table>`/`<td>` markup, no charting library (design spec §2: "No new npm dependencies").
- NO `dangerouslySetInnerHTML` anywhere — all dynamic content (chat text, table cells) renders through JSX text interpolation only, matching the existing XSS-safe convention.
- Pure Tailwind utility classes with the existing slate/semantic palette — severity chips use the established `bg-*-100 text-*-700` lookup-object pattern (`FRAMEWORK_COLORS`/`HEALTH_COLORS` style), red/orange/yellow/slate per design spec §7.
- Thai empty-state copy matching house style — exact string: `ยังไม่มี performance findings — ลองสั่ง analyze performance risk จาก chat` (design spec §7, verbatim).
- Verification gate is `npm run build` (exit 0) from `qa-brain/frontend` — run it in every task; this project has no frontend test runner, so a clean TypeScript build is the hard gate (design spec §8).
- Commit after every task — one commit per task, exact commands given in each task's final step.
- The Chat panel must remain visible at all times — never replace it with a routed page; existing tabs (Test Cases / Scripts / OWASP) must remain byte-identical in behavior.
- Design spec (source of truth): `docs/superpowers/specs/2026-07-02-performance-qa-agent-design.md`. The orchestrator's `orchestrator_done` events for performance actions carry these `data` keys (spec §4): `workload_model`, `perf_risks`, `perf_script`, `perf_result_analysis`, `bottleneck`, `sla_slo`, `perf_defect`, `capacity_plan` — plus the existing `story_id` key where applicable. Payload shapes are spec §3 verbatim. `GET /api/stories/{jira_id}/performance-findings` (spec §5) returns a JSON array of objects with keys `id`, `story_id`, `risk_area`, `severity` (`"critical" | "high" | "medium" | "low"`), `description` (nullable TEXT), `created_at`.

---

## Task 1: Types & API Client for Performance Findings

**Files:**
- Modify: `qa-brain/frontend/src/lib/types.ts` (insert `PerformanceFinding` after the `OwaspTestCase` interface ending at line 40; add 8 keys to `AgentEvent["data"]` after the `owasp_dashboard` key at line 68)
- Modify: `qa-brain/frontend/src/lib/api.ts` (extend the type import on line 1; append `getStoryPerformanceFindings` after `getStorySecurityFindings` ending at line 49)

**Interfaces:**
- Consumes: existing `api` axios instance (`qa-brain/frontend/src/lib/api.ts`), existing `AgentEvent` interface
- Produces: `PerformanceFinding` interface, extended `AgentEvent["data"]` shape (8 new optional keys), `getStoryPerformanceFindings(jiraId: string): Promise<PerformanceFinding[]>`

- [ ] **Step 1: Add the `PerformanceFinding` interface to `qa-brain/frontend/src/lib/types.ts`**

Add this interface after the existing `OwaspTestCase` interface (line 40), before `AgentEvent`:

```typescript
export interface PerformanceFinding {
  id: string;
  story_id: string;
  risk_area: string;
  severity: "critical" | "high" | "medium" | "low";
  description: string | null;
  created_at: string;
}
```

`description` is `string | null` because the backing `performance_findings.description` column is nullable `TEXT` (design spec §5) — the REST endpoint can legitimately return `null`. The live `perf_risks` event payload always carries a `string` description (spec §3), which is assignable to `string | null`, so the same interface serves both the WebSocket-populated state and the REST endpoint's typed client.

- [ ] **Step 2: Extend the `AgentEvent["data"]` shape in `qa-brain/frontend/src/lib/types.ts`**

Inside the existing `AgentEvent` interface's `data?: { ... }` object, add these 8 optional keys immediately after the existing `owasp_dashboard` key (line 68), before the closing `};` of `data`:

```typescript
    workload_model?: { story_id: string; concurrent_users: number; ramp_up: string; duration: string; scenarios: { name: string; weight_percent: number; description: string }[] };
    perf_risks?: { risk_area: string; severity: "critical" | "high" | "medium" | "low"; description: string }[];
    perf_script?: { framework: "k6" | "jmeter"; content: string; notes: string };
    perf_result_analysis?: { verdict: "pass" | "fail" | "degraded"; root_cause: string; bottleneck_location: string; summary: string; recommendations: string[] };
    bottleneck?: { layer: "app" | "db" | "api" | "infra"; hypothesis: string; evidence: string[]; next_steps: string[] };
    sla_slo?: { slos: { metric: string; target: string; pass_criteria: string }[]; notes: string };
    perf_defect?: { report: string; impact: string; evidence: string; jira_id: string; url: string };
    capacity_plan?: { current_assessment: string; recommendations: { component: string; sizing: string; rationale: string }[]; estimated_headroom: string };
```

The full `AgentEvent` interface after this edit:

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
    workload_model?: { story_id: string; concurrent_users: number; ramp_up: string; duration: string; scenarios: { name: string; weight_percent: number; description: string }[] };
    perf_risks?: { risk_area: string; severity: "critical" | "high" | "medium" | "low"; description: string }[];
    perf_script?: { framework: "k6" | "jmeter"; content: string; notes: string };
    perf_result_analysis?: { verdict: "pass" | "fail" | "degraded"; root_cause: string; bottleneck_location: string; summary: string; recommendations: string[] };
    bottleneck?: { layer: "app" | "db" | "api" | "infra"; hypothesis: string; evidence: string[]; next_steps: string[] };
    sla_slo?: { slos: { metric: string; target: string; pass_criteria: string }[]; notes: string };
    perf_defect?: { report: string; impact: string; evidence: string; jira_id: string; url: string };
    capacity_plan?: { current_assessment: string; recommendations: { component: string; sizing: string; rationale: string }[]; estimated_headroom: string };
  };
}
```

Key/shape provenance, all spec §3 verbatim: `workload_model` ← `build_workload_model`, `perf_risks` ← `analyze_perf_risk`, `perf_script` ← `generate_perf_script`, `perf_result_analysis` ← `analyze_perf_result`, `bottleneck` ← `identify_bottleneck`, `sla_slo` ← `define_sla_slo`, `perf_defect` ← `write_perf_defect` (note: no `cvss_score` — that field is security-only), `capacity_plan` ← `recommend_capacity`. `concurrent_users` and `weight_percent` are `number` (counts/percentages); `ramp_up`, `duration`, `estimated_headroom` are free-text `string` (e.g. `"5 min to peak"`, `"~40%"`), since the spec does not constrain them to numerics.

- [ ] **Step 3: Add `getStoryPerformanceFindings` to `qa-brain/frontend/src/lib/api.ts`**

Replace the existing import line (line 1):

```typescript
import type { TestCase, AutomationScript, SecurityFinding } from "./types";
```

with:

```typescript
import type { TestCase, AutomationScript, SecurityFinding, PerformanceFinding } from "./types";
```

Add this function at the end of the file, after `getStorySecurityFindings`:

```typescript
export async function getStoryPerformanceFindings(jiraId: string): Promise<PerformanceFinding[]> {
  const { data } = await api.get<PerformanceFinding[]>(`/api/stories/${jiraId}/performance-findings`);
  return data;
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: exit 0, no type errors. `getStoryPerformanceFindings` isn't called from anywhere in this plan — it exists so the REST endpoint built in the backend plan has a typed client method available, exactly like `getStorySecurityFindings` before it (design spec §7 accepts this same page-refresh persistence gap for symmetry; already logged as deferred work). The `PerformancePanel` (Task 3) is populated optimistically from WebSocket `perf_risks` events (Task 2), so a page refresh loses findings even though the DB table and endpoint exist — called out explicitly here rather than left as an implicit shortcut.

- [ ] **Step 5: Commit**

```bash
cd qa-brain/frontend
git add src/lib/types.ts src/lib/api.ts
git commit -m "feat: add PerformanceFinding type, 8 performance event data keys, and API client for performance-findings endpoint"
```

---

## Task 2: Chat Feedback for Performance QA Actions

**Files:**
- Modify: `qa-brain/frontend/src/hooks/useAgentChat.ts` (type import line 2; new state after line 12; 8 handlers inside the `orchestrator_done` block after the `owasp_dashboard` handler ending at line 147; return statement line 187; 8 formatter functions appended after `formatOwaspDashboard` ending at line 267)

**Interfaces:**
- Consumes: the extended `AgentEvent["data"]` shape and `PerformanceFinding` from Task 1; the existing `appendAssistantMessage(content: string, link?: { label: string; url: string })` (already link-capable since the Security phase — no change needed)
- Produces: `useAgentChat` now also returns `perfFindings: PerformanceFinding[]` (optimistically populated from WebSocket `perf_risks` events, mirroring how `findings` is populated from `owasp_mapping` events); 8 new formatter functions

- [ ] **Step 1: Extend the type import in `qa-brain/frontend/src/hooks/useAgentChat.ts`**

Replace (line 2):

```typescript
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript, SecurityFinding } from "../lib/types";
```

with:

```typescript
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript, SecurityFinding, PerformanceFinding } from "../lib/types";
```

- [ ] **Step 2: Add the `perfFindings` state**

Add this state variable directly after the existing `const [findings, setFindings] = useState<SecurityFinding[]>([]);` (line 12):

```typescript
  const [perfFindings, setPerfFindings] = useState<PerformanceFinding[]>([]);
```

- [ ] **Step 3: Add the 8 performance event handlers inside the `orchestrator_done` block**

Inside the `if (event.type === "orchestrator_done")` block, after the existing `if (data.owasp_dashboard) { ... }` check (ends line 147), add:

```typescript
        if (data.workload_model) {
          appendAssistantMessage(formatWorkloadModel(data.workload_model));
        }
        if (data.perf_risks && data.story_id) {
          setPerfFindings((prev) => [
            ...prev,
            ...data.perf_risks!.map((risk) => ({
              id: crypto.randomUUID(),
              story_id: data.story_id as string,
              risk_area: risk.risk_area,
              severity: risk.severity,
              description: risk.description,
              created_at: new Date().toISOString(),
            })),
          ]);
          appendAssistantMessage(formatPerfRisks(data.story_id, data.perf_risks));
        }
        if (data.perf_script) {
          appendAssistantMessage(formatPerfScript(data.perf_script));
        }
        if (data.perf_result_analysis) {
          appendAssistantMessage(formatPerfResultAnalysis(data.perf_result_analysis));
        }
        if (data.bottleneck) {
          appendAssistantMessage(formatBottleneck(data.bottleneck));
        }
        if (data.sla_slo) {
          appendAssistantMessage(formatSlaSlo(data.sla_slo));
        }
        if (data.perf_defect) {
          const isMock = data.perf_defect.url === "[MOCK]";
          appendAssistantMessage(
            formatPerfDefect(data.perf_defect),
            isMock ? undefined : { label: data.perf_defect.jira_id, url: data.perf_defect.url }
          );
        }
        if (data.capacity_plan) {
          appendAssistantMessage(formatCapacityPlan(data.capacity_plan));
        }
```

The `perf_risks` branch mirrors the existing `owasp_mapping` branch structurally (same `data.<key> && data.story_id` guard, same `crypto.randomUUID()` id synthesis, same `data.story_id as string` narrowing, same `new Date().toISOString()` created_at) — the WebSocket payload carries only `risk_area`/`severity`/`description` (spec §3), so `id`, `story_id`, and `created_at` are synthesized client-side into the `PerformanceFinding` shape the panel and the `performance_findings` table share. The `perf_defect` branch mirrors `security_defect` exactly: mock-mode never creates a real Jira ticket (spec §6), so the `[MOCK]` URL suppresses the clickable link and the formatted text still renders. No `appendAssistantMessage` change is needed — it already accepts the optional `link` parameter since the Security phase.

- [ ] **Step 4: Update the hook's return statement**

Replace (line 187):

```typescript
  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings };
```

with:

```typescript
  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings, perfFindings };
```

- [ ] **Step 5: Add the 8 new formatter functions**

Add these at the bottom of the file, after the existing `formatOwaspDashboard` (ends line 267):

```typescript
function formatWorkloadModel(model: { story_id: string; concurrent_users: number; ramp_up: string; duration: string; scenarios: { name: string; weight_percent: number; description: string }[] }): string {
  const scenarios = model.scenarios.map((s) => `- **${s.name}** (${s.weight_percent}%) — ${s.description}`).join("\n");
  return `📈 Workload model for ${model.story_id}:\n\n**Concurrent users:** ${model.concurrent_users}\n**Ramp-up:** ${model.ramp_up}\n**Duration:** ${model.duration}\n\n**Scenarios:**\n${scenarios}`;
}

function formatPerfRisks(storyId: string, risks: { risk_area: string; severity: "critical" | "high" | "medium" | "low"; description: string }[]): string {
  const icons: Record<string, string> = { critical: "🔴", high: "🟠", medium: "🟡", low: "⚪" };
  const lines = risks.map((r) => `${icons[r.severity] || "•"} **${r.risk_area}** (${r.severity}) — ${r.description}`);
  return `⚡ Performance risks for ${storyId}:\n\n${lines.join("\n")}`;
}

function formatPerfScript(script: { framework: "k6" | "jmeter"; content: string; notes: string }): string {
  return `🏋️ ${script.framework} load-test script:\n\n\`\`\`\n${script.content}\n\`\`\`\n\n**Notes:** ${script.notes}`;
}

function formatPerfResultAnalysis(analysis: { verdict: "pass" | "fail" | "degraded"; root_cause: string; bottleneck_location: string; summary: string; recommendations: string[] }): string {
  const emoji = analysis.verdict === "pass" ? "✅" : analysis.verdict === "fail" ? "🚫" : "⚠️";
  const recommendations = analysis.recommendations.map((r) => `- ${r}`).join("\n");
  return `${emoji} Load-test verdict: **${analysis.verdict.toUpperCase()}**\n\n**Root cause:** ${analysis.root_cause}\n\n**Bottleneck location:** ${analysis.bottleneck_location}\n\n${analysis.summary}\n\n**Recommendations:**\n${recommendations}`;
}

function formatBottleneck(bottleneck: { layer: "app" | "db" | "api" | "infra"; hypothesis: string; evidence: string[]; next_steps: string[] }): string {
  const evidence = bottleneck.evidence.map((e) => `- ${e}`).join("\n");
  const nextSteps = bottleneck.next_steps.map((s) => `- ${s}`).join("\n");
  return `🔎 Bottleneck hypothesis — layer: **${bottleneck.layer.toUpperCase()}**\n\n${bottleneck.hypothesis}\n\n**Evidence:**\n${evidence}\n\n**Next steps:**\n${nextSteps}`;
}

function formatSlaSlo(slaSlo: { slos: { metric: string; target: string; pass_criteria: string }[]; notes: string }): string {
  const rows = slaSlo.slos.map((s) => `- **${s.metric}** — target: ${s.target}, pass: ${s.pass_criteria}`).join("\n");
  return `🎯 SLA/SLO definition:\n\n${rows}\n\n${slaSlo.notes}`;
}

function formatPerfDefect(defect: { report: string; impact: string; evidence: string; jira_id: string; url: string }): string {
  return `🐛 Performance defect created: ${defect.jira_id}\n\n**Report:** ${defect.report}\n\n**Impact:** ${defect.impact}\n\n**Evidence:** ${defect.evidence}`;
}

function formatCapacityPlan(plan: { current_assessment: string; recommendations: { component: string; sizing: string; rationale: string }[]; estimated_headroom: string }): string {
  const recommendations = plan.recommendations.map((r) => `- **${r.component}** — ${r.sizing} (${r.rationale})`).join("\n");
  return `🏗️ Capacity recommendation:\n\n**Current assessment:** ${plan.current_assessment}\n\n**Recommendations:**\n${recommendations}\n\n**Estimated headroom:** ${plan.estimated_headroom}`;
}
```

`formatPerfScript` embeds the script content in a fenced code block string (` ``` ` fences inside the message text), exactly the pattern the existing `formatted_script` and `fix` handlers use — `MessageBubble` renders it as preformatted-looking `whitespace-pre-wrap` text, the same way automation scripts display today (design spec §7). `formatPerfDefect` mirrors `formatSecurityDefect` minus the `cvss_score` line, because the `perf_defect` payload has no CVSS field (spec §3).

- [ ] **Step 6: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: exit 0, no type errors.

- [ ] **Step 7: Commit**

```bash
cd qa-brain/frontend
git add src/hooks/useAgentChat.ts
git commit -m "feat: chat feedback for all 8 Performance QA Agent actions"
```

---

## Task 3: PerformancePanel Component

**Files:**
- Create: `qa-brain/frontend/src/components/PerformancePanel/PerformancePanel.tsx`

**Interfaces:**
- Consumes: `PerformanceFinding` (Task 1's type)
- Produces: `PerformancePanel` component, named export, props `{ findings: PerformanceFinding[] }`

- [ ] **Step 1: Write `qa-brain/frontend/src/components/PerformancePanel/PerformancePanel.tsx`**

Single file, no sub-components (design spec §7: "single file; no sub-components needed at this data shape"). A real `<table>` grouped by story — findings render as flat rows sorted by story, with the story id shown only on the first row of each story's group (grouping without `rowSpan` complexity). Severity chips reuse the existing `bg-*-100 text-*-700` lookup-object convention from `ScriptsPanel`'s `FRAMEWORK_COLORS`, with the spec §7 palette: red/orange/yellow/slate. Header/empty-state/scroll structure mirrors `OwaspCoverage`:

```typescript
import type { PerformanceFinding } from "../../lib/types";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-slate-100 text-slate-600",
};

interface PerformancePanelProps {
  findings: PerformanceFinding[];
}

export function PerformancePanel({ findings }: PerformancePanelProps) {
  const storyIds = Array.from(new Set(findings.map((f) => f.story_id))).sort();

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <h2 className="font-semibold text-slate-800">Performance Findings</h2>
        <span className="text-xs text-slate-500">
          {findings.length} findings / {storyIds.length} stories
        </span>
      </div>

      <div className="flex-1 overflow-auto">
        {findings.length === 0 ? (
          <p className="text-center text-slate-400 text-sm py-8">
            ยังไม่มี performance findings — ลองสั่ง analyze performance risk จาก chat
          </p>
        ) : (
          <table className="border-collapse w-full">
            <thead>
              <tr>
                <th className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b whitespace-nowrap">
                  Story
                </th>
                <th className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b whitespace-nowrap">
                  Risk Area
                </th>
                <th className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b whitespace-nowrap">
                  Severity
                </th>
                <th className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b">
                  Description
                </th>
              </tr>
            </thead>
            <tbody>
              {storyIds.map((storyId) =>
                findings
                  .filter((f) => f.story_id === storyId)
                  .map((finding, index) => (
                    <tr key={finding.id} className="hover:bg-slate-50">
                      <td className="p-2 text-xs font-medium text-slate-700 border-b whitespace-nowrap align-top">
                        {index === 0 ? storyId : ""}
                      </td>
                      <td className="p-2 text-xs text-slate-700 border-b whitespace-nowrap align-top">
                        {finding.risk_area}
                      </td>
                      <td className="p-2 border-b align-top">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${
                            SEVERITY_COLORS[finding.severity] || "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {finding.severity}
                        </span>
                      </td>
                      <td className="p-2 text-xs text-slate-600 border-b align-top">
                        {finding.description ?? "—"}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

The `?? "—"` on `description` handles the nullable column (Task 1) without rendering an empty cell. The `|| "bg-slate-100 text-slate-600"` fallback on the chip guards against the trust-the-LLM enum caveat the spec carries over from security findings (§5) — an unexpected severity string degrades to a neutral chip instead of an unstyled one.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: exit 0, no type errors. Manual-verification note: the component isn't rendered anywhere until Task 4, so there is nothing to see in the browser yet — the build is the only gate for this task.

- [ ] **Step 3: Commit**

```bash
cd qa-brain/frontend
git add src/components/PerformancePanel/PerformancePanel.tsx
git commit -m "feat: PerformancePanel component — findings table grouped by story with severity chips"
```

---

## Task 4: Wire Performance Tab into Dashboard

**Files:**
- Modify: `qa-brain/frontend/src/pages/Dashboard.tsx` (full-file replacement below; changes touch the import block lines 1–6, the `RightPanel` union line 11, the destructure line 14, the tab-button row lines 31–56, and the conditional render lines 58–62)

**Interfaces:**
- Consumes: `PerformancePanel` (Task 3), `useAgentChat`'s new `perfFindings` return value (Task 2)

- [ ] **Step 1: Replace `qa-brain/frontend/src/pages/Dashboard.tsx` with the 4-tab version**

```typescript
import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel/ChatPanel";
import { TestCasePanel } from "../components/TestCasePanel/TestCasePanel";
import { ScriptsPanel } from "../components/ScriptsPanel/ScriptsPanel";
import { OwaspCoverage } from "../components/OwaspCoverage/OwaspCoverage";
import { PerformancePanel } from "../components/PerformancePanel/PerformancePanel";
import { useAgentChat } from "../hooks/useAgentChat";

const SESSION_ID = crypto.randomUUID();
const PROJECT_ID = "proj-001";

type RightPanel = "test-cases" | "scripts" | "owasp" | "performance";

export default function Dashboard() {
  const { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings, perfFindings } = useAgentChat(SESSION_ID, PROJECT_ID);
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
            <button
              onClick={() => setRightPanel("performance")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                rightPanel === "performance" ? "bg-slate-800 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
              }`}
            >
              Performance ({perfFindings.length})
            </button>
          </div>

          <div className="flex-1 min-h-0">
            {rightPanel === "test-cases" && <TestCasePanel testCases={testCases} releaseScore={releaseScore} />}
            {rightPanel === "scripts" && <ScriptsPanel scripts={scripts} />}
            {rightPanel === "owasp" && <OwaspCoverage findings={findings} />}
            {rightPanel === "performance" && <PerformancePanel findings={perfFindings} />}
          </div>
        </div>
      </main>
    </div>
  );
}
```

The only deltas from the current file are: the `PerformancePanel` import, `"performance"` in the `RightPanel` union, `perfFindings` in the destructure, the fourth button, and the fourth conditional render — the Test Cases / Scripts / OWASP tabs, their button markup, and their render lines are byte-identical to the current `Dashboard.tsx`, satisfying the "existing tabs must remain byte-identical in behavior" constraint.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: exit 0, no type errors.

- [ ] **Step 3: Manual smoke test with the dev server**

```bash
cd qa-brain/frontend
npm run dev -- --port 5175 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5175/
```

Expected: `200`. Then stop the dev server (`kill %1` or the equivalent background-job command).

If a real browser check is available in the environment, additionally: log in, switch to the "Performance" tab (should show the Thai empty state), send a chat message like "analyze performance risk for SCRUM-4" (backend must be running with `MOCK_MODE=true`), and confirm: (a) a formatted "⚡ Performance risks for SCRUM-4" message appears in chat, and (b) the Performance tab count increments and the table renders rows for SCRUM-4 with severity chips once you switch to it. Then try "generate k6 script for SCRUM-4" and confirm the script renders inline in chat inside a fenced code block (no panel change), and "write perf defect" with a pasted finding and confirm the defect message appears with NO clickable link (mock URL `[MOCK]` is suppressed). If no browser tool is available, skip this part and say so explicitly rather than fabricating a result — the TypeScript build and curl check are the objective gates for this task.

- [ ] **Step 4: Commit**

```bash
cd qa-brain/frontend
git add src/pages/Dashboard.tsx
git commit -m "feat: add Performance tab to Dashboard alongside Test Cases, Scripts, and OWASP"
```

---

## Explicitly Deferred

Per design spec §5, §7, and §9:

- Persistence/panels for the 7 non-persisted outputs — workload models, scripts, result analyses, bottleneck hypotheses, SLO drafts, and capacity plans remain one-shot chat outputs; no REST endpoint or DB table backs them, and refreshing the page loses them (same as the Automation Agent's `healing`/`classification`/`fix` and the Security Agent's `rbac_matrix`/`triage` outputs today).
- Wiring `getStoryPerformanceFindings` into an on-mount fetch — the panel is fed exclusively by transient WebSocket `perf_risks` state, so findings do not survive a page refresh even though the `performance_findings` table and `GET /api/stories/{jira_id}/performance-findings` endpoint exist. The spec (§7) explicitly accepts this gap for symmetry with the still-unwired `getStorySecurityFindings`; it is already logged as deferred work.
- Perf-script lifecycle (health tracking, self-healing runs, CI hooks) — spec §5/§9: that machinery is Automation-agent scope; perf scripts render in chat only and never enter the `scripts` state or `ScriptsPanel`.
- Gatling framework option, executing load tests, real APM integrations (Datadog/New Relic/Grafana) — spec §9; inputs are pasted text this phase.
- Analytics Agent, release-risk aggregation, `release_assessments.perf_score` wiring — separate Phase 3 work (spec §1, §9).
- Any new charting library, icon-rail sidebar redesign, LLM-based orchestrator routing — all previously rejected deferrals; nothing in this plan reopens them.
