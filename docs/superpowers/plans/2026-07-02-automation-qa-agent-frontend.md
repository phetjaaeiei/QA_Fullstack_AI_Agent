# Automation QA Agent — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already-shipped Automation QA Agent backend (7 tools, all reachable via chat) visible and usable in the existing React dashboard — chat feedback for every automation action, plus a panel to browse generated scripts.

**Architecture:** Extend the existing `useAgentChat` hook and `TestCasePanel` pattern exactly as they already work for the Manual QA Agent — no new state-management approach, no new component conventions. Add one new panel (`ScriptsPanel`, a structural twin of `TestCasePanel`) and a small pill-style tab switcher (reusing the exact button styling `TestCasePanel` already uses for its type filters) so the user can flip between Test Cases and Scripts without losing the pinned Chat panel.

**Scope decision (why this and not the full dashboard redesign):** The original design spec (`docs/superpowers/specs/2026-07-02-automation-qa-agent-design.md` §8) sketched a larger dashboard overhaul — an icon-rail sidebar, a Recharts-based Release Risk gauge, an OWASP coverage heatmap, and a React-Flow traceability graph. Building that now would mean: (a) two new npm dependencies (`recharts`, `@xyflow/react` + `@dagrejs/dagre`) for visualizations that have no real backend data behind two of the three panels yet (OWASP coverage needs the not-yet-built Security QA Agent; the traceability graph's Defect node needs a not-yet-built defect-tracking table), and (b) a navigation restructure sized for 5 panels when only 2 exist today. That's speculative infrastructure ahead of validated need. This plan instead closes the actual gap — the 7 tools built in the backend plan are currently invisible in the UI — with the smallest change that follows established conventions. The sidebar-based nav and the two chart-heavy panels (Release Risk, Traceability Graph) remain the right design for when Security QA Agent and defect tracking exist; nothing in this plan forecloses building them then.

**Tech Stack:** React 19 + TypeScript + Vite, matching the existing frontend exactly. No new dependencies.

## Global Constraints

- No new npm dependencies — everything here is buildable with what's already installed.
- Match existing conventions exactly: raw Tailwind utility classes (not shadcn components, even though shadcn is nominally installed — the codebase doesn't use it yet), the `TYPE_COLORS`/`PRIORITY_COLORS`-style lookup-object pattern for badges, optimistic client-side state updates from WebSocket payloads (no REST refetch needed for data that already arrived over the socket).
- The Chat panel must remain visible at all times — never replace it with a routed page.
- Design spec: `docs/superpowers/specs/2026-07-02-automation-qa-agent-design.md` (§8 covers the longer-term full dashboard vision this plan intentionally scopes down from).
- Backend plan (already shipped, PR open): `docs/superpowers/plans/2026-07-02-automation-qa-agent-backend.md`. The orchestrator's `orchestrator_done` events for automation actions carry these `data` keys (verified against `qa-brain/backend/app/agents/orchestrator.py`): `script` + `story_id` (generate_script_from_spec), `formatted_script` (apply_company_framework), `healing` (suggest_self_healing), `classification` (classify_failure), `fix` (auto_fix_script), `test_data` (generate_test_data), `traceability_mapping` + `story_id` (map_script_traceability).

---

## Task 1: Types & API Client for Automation Scripts

**Files:**
- Modify: `qa-brain/frontend/src/lib/types.ts`
- Modify: `qa-brain/frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `AutomationScript` interface, extended `AgentEvent["data"]` shape, `getStoryScripts(jiraId): Promise<AutomationScript[]>`

- [ ] **Step 1: Add the `AutomationScript` interface and extend `AgentEvent` in `qa-brain/frontend/src/lib/types.ts`**

Add this interface (place it after the existing `TestCase` interface):

```typescript
export interface AutomationScript {
  id: string;
  story_id: string;
  framework: "playwright" | "robot";
  content: string;
  health_status: "healthy" | "flaky" | "broken";
  ci_run_url: string | null;
  created_at: string;
}
```

Extend the existing `AgentEvent` interface's `data` field — replace:

```typescript
  data?: {
    test_cases?: TestCase[];
    analysis?: Record<string, unknown>;
    traceability?: Record<string, string[]>;
    release_score?: ReleaseScore;
    gaps?: Record<string, unknown>;
    story_id?: string;
    message?: string;
  };
```

with:

```typescript
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
```

- [ ] **Step 2: Add `getStoryScripts` to `qa-brain/frontend/src/lib/api.ts`**

Add this import at the top (alongside the existing `TestCase` import):

```typescript
import type { TestCase, AutomationScript } from "./types";
```

Add this function after `getStoryTestCases`:

```typescript
export async function getStoryScripts(jiraId: string): Promise<AutomationScript[]> {
  const { data } = await api.get<AutomationScript[]>(`/api/stories/${jiraId}/scripts`);
  return data;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd qa-brain/frontend
npm run build
```

Expected: build succeeds with no type errors (this function isn't called from anywhere yet, so it just needs to type-check — it will be used starting Task 4).

- [ ] **Step 4: Commit**

```bash
git add src/lib/types.ts src/lib/api.ts
git commit -m "feat: add AutomationScript type and API client for scripts endpoint"
```

---

## Task 2: Chat Feedback for Automation Actions

**Files:**
- Modify: `qa-brain/frontend/src/hooks/useAgentChat.ts`

**Interfaces:**
- Consumes: the extended `AgentEvent["data"]` shape from Task 1
- Produces: `useAgentChat` now also returns `scripts: AutomationScript[]` (optimistically populated from WebSocket `script` events, mirroring how `testCases` is already populated from `test_cases` events)

- [ ] **Step 1: Add the `scripts` state and formatting functions to `qa-brain/frontend/src/hooks/useAgentChat.ts`**

Add the import (extend the existing type import line):

```typescript
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript } from "../lib/types";
```

Add a new state variable alongside the existing ones (after `const [releaseScore, setReleaseScore] = useState<ReleaseScore | null>(null);`):

```typescript
  const [scripts, setScripts] = useState<AutomationScript[]>([]);
```

Inside the `if (event.type === "orchestrator_done")` block, after the existing `if (data.message) { ... }` check, add:

```typescript
        if (data.script && data.story_id) {
          setScripts((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              story_id: data.story_id as string,
              framework: data.script!.framework,
              content: data.script!.content,
              health_status: "healthy" as const,
              ci_run_url: null,
              created_at: new Date().toISOString(),
            },
          ]);
          appendAssistantMessage(`สร้าง ${data.script.framework} script สำเร็จ ✓`);
        }
        if (data.formatted_script) {
          appendAssistantMessage(`ปรับ script ตาม company standard แล้ว:\n\n\`\`\`\n${data.formatted_script.content}\n\`\`\``);
        }
        if (data.healing) {
          appendAssistantMessage(formatHealing(data.healing));
        }
        if (data.classification) {
          appendAssistantMessage(formatClassification(data.classification));
        }
        if (data.fix) {
          appendAssistantMessage(`แก้ script แล้ว: ${data.fix.explanation}\n\n\`\`\`\n${data.fix.content}\n\`\`\``);
        }
        if (data.test_data) {
          appendAssistantMessage(formatTestData(data.test_data));
        }
        if (data.traceability_mapping) {
          appendAssistantMessage(formatTraceabilityMapping(data.traceability_mapping));
        }
```

Update the hook's return statement to also return `scripts`:

```typescript
  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts };
```

Add these formatting helper functions at the bottom of the file, alongside the existing `formatAnalysis`/`formatReleaseScore`:

```typescript
function formatHealing(healing: { alternatives: string[]; strategy: string }): string {
  return `🔧 Self-healing suggestions:\n${healing.alternatives.map((a) => `- ${a}`).join("\n")}\n\n**Strategy:** ${healing.strategy}`;
}

function formatClassification(classification: { root_cause: string; explanation: string; failed_step: string }): string {
  return `🔍 Root cause: **${classification.root_cause}**\n\nFailed step: ${classification.failed_step}\n\n${classification.explanation}`;
}

function formatTestData(testData: { label: string; value: string }[]): string {
  return `📋 Test data:\n${testData.map((d) => `- **${d.label}:** ${d.value}`).join("\n")}`;
}

function formatTraceabilityMapping(mapping: { story_id: string; covers_acceptance_criteria: boolean; confidence: string; notes: string }): string {
  const emoji = mapping.covers_acceptance_criteria ? "✅" : "⚠️";
  return `${emoji} ${mapping.story_id}: ${mapping.covers_acceptance_criteria ? "Covers" : "Does NOT cover"} acceptance criteria (confidence: ${mapping.confidence})\n\n${mapping.notes}`;
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
git add src/hooks/useAgentChat.ts
git commit -m "feat: chat feedback for all 7 Automation QA Agent actions"
```

---

## Task 3: ScriptsPanel Component

**Files:**
- Create: `qa-brain/frontend/src/components/ScriptsPanel/ScriptsPanel.tsx`

**Interfaces:**
- Consumes: `AutomationScript[]` (Task 1's type)
- Produces: `ScriptsPanel` component, default-exported... no — named-exported as `ScriptsPanel`, matching `TestCasePanel`'s export style, taking props `{ scripts: AutomationScript[] }`

- [ ] **Step 1: Write `qa-brain/frontend/src/components/ScriptsPanel/ScriptsPanel.tsx`**

This is a structural twin of `qa-brain/frontend/src/components/TestCasePanel/TestCasePanel.tsx` — same layout shell, filter-pill pattern, and expand-on-click behavior, adapted to scripts' fields (`framework` instead of `type`, `health_status` instead of `priority`, `content` shown as a code block instead of steps/expected-result):

```typescript
import { useState } from "react";
import type { AutomationScript } from "../../lib/types";

const FRAMEWORK_COLORS: Record<string, string> = {
  playwright: "bg-blue-100 text-blue-700",
  robot: "bg-purple-100 text-purple-700",
};

const HEALTH_COLORS: Record<string, string> = {
  healthy: "text-green-600 font-semibold",
  flaky: "text-yellow-600",
  broken: "text-red-600 font-semibold",
};

interface ScriptsPanelProps {
  scripts: AutomationScript[];
}

export function ScriptsPanel({ scripts }: ScriptsPanelProps) {
  const [filter, setFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const frameworks = ["all", "playwright", "robot"];
  const filtered = filter === "all" ? scripts : scripts.filter((s) => s.framework === filter);

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border">
      <div className="px-4 py-3 border-b">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-slate-800">Automation Scripts</h2>
          <span className="text-xs text-slate-500">{scripts.length} total</span>
        </div>

        <div className="flex gap-1 flex-wrap">
          {frameworks.map((fw) => (
            <button
              key={fw}
              onClick={() => setFilter(fw)}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                filter === fw ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {fw} {fw !== "all" && `(${scripts.filter((s) => s.framework === fw).length})`}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto divide-y">
        {filtered.length === 0 && (
          <p className="text-center text-slate-400 text-sm py-8">
            ยังไม่มี automation script — ลอง generate จาก chat
          </p>
        )}
        {filtered.map((script) => (
          <div key={script.id} className="p-3 hover:bg-slate-50 cursor-pointer" onClick={() => setExpanded(expanded === script.id ? null : script.id)}>
            <div className="flex items-start gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${FRAMEWORK_COLORS[script.framework] || "bg-slate-100 text-slate-600"}`}>
                {script.framework}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 truncate">{script.story_id}</p>
                <p className={`text-xs ${HEALTH_COLORS[script.health_status]}`}>{script.health_status}</p>
              </div>
            </div>
            {expanded === script.id && (
              <pre className="mt-2 ml-1 text-xs text-slate-600 bg-slate-50 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                {script.content}
              </pre>
            )}
          </div>
        ))}
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
git add src/components/ScriptsPanel/
git commit -m "feat: ScriptsPanel component for browsing generated automation scripts"
```

---

## Task 4: Wire ScriptsPanel into Dashboard

**Files:**
- Modify: `qa-brain/frontend/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: `ScriptsPanel` (Task 3), `useAgentChat`'s new `scripts` return value (Task 2)

- [ ] **Step 1: Replace `qa-brain/frontend/src/pages/Dashboard.tsx` with the tab-switching version**

```typescript
import { useState } from "react";
import { ChatPanel } from "../components/ChatPanel/ChatPanel";
import { TestCasePanel } from "../components/TestCasePanel/TestCasePanel";
import { ScriptsPanel } from "../components/ScriptsPanel/ScriptsPanel";
import { useAgentChat } from "../hooks/useAgentChat";

const SESSION_ID = crypto.randomUUID();
const PROJECT_ID = "proj-001";

type RightPanel = "test-cases" | "scripts";

export default function Dashboard() {
  const { messages, activeAgent, sendMessage, testCases, releaseScore, scripts } = useAgentChat(SESSION_ID, PROJECT_ID);
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
          </div>

          <div className="flex-1 min-h-0">
            {rightPanel === "test-cases" ? (
              <TestCasePanel testCases={testCases} releaseScore={releaseScore} />
            ) : (
              <ScriptsPanel scripts={scripts} />
            )}
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

If a real browser check is available in the environment, additionally: log in, switch to the "Scripts" tab (should show the empty state), send a chat message like "Generate playwright script for SCRUM-4" (backend must be running with `MOCK_MODE=true`), and confirm a script appears in the Scripts tab after the response streams in. If no browser tool is available, skip this part and say so explicitly rather than fabricating a result — the TypeScript build and curl check are the objective gates for this task.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Dashboard.tsx
git commit -m "feat: add Scripts tab to Dashboard alongside Test Cases"
```

---

## Explicitly out of scope for this plan

- Icon-rail sidebar navigation (only 2 panels exist; a tab switcher is proportionate — revisit when a 3rd/4th panel is real)
- Release Risk Dashboard (Recharts gauge) — needs a real automation-health scoring decision, not just UI; do this alongside whatever surfaces sprint-level automation quality first
- OWASP Coverage panel — zero backing data until Security QA Agent exists
- Traceability Graph (React Flow + dagre) — the Story→TestCase→Script edges are buildable today, but a Defect node has no backing data yet; better to build the whole graph once, not half now and half later
