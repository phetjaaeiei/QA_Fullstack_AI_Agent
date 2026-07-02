import { useState, useEffect, useRef, useCallback } from "react";
import type { AgentEvent, Message, TestCase, ReleaseScore, AutomationScript, SecurityFinding } from "../lib/types";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

export function useAgentChat(sessionId: string, projectId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [releaseScore, setReleaseScore] = useState<ReleaseScore | null>(null);
  const [scripts, setScripts] = useState<AutomationScript[]>([]);
  const [findings, setFindings] = useState<SecurityFinding[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    const ws = new WebSocket(`${WS_URL}/ws/chat/${sessionId}?token=${token}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);

      if (event.type === "agent_start") {
        setActiveAgent(event.agent || null);
        appendAssistantMessage(`[${event.agent}] ${event.message || "กำลังทำงาน..."}`);
      }

      if (event.type === "stream_delta" && event.delta) {
        appendStreamDelta(event.delta);
      }

      if (event.type === "orchestrator_done") {
        setActiveAgent(null);
        const data = event.data || {};

        if (data.test_cases && data.test_cases.length > 0) {
          setTestCases((prev) => [
            ...prev,
            ...data.test_cases!.map((tc) => ({
              ...tc,
              id: tc.id || crypto.randomUUID(),
              story_id: tc.story_id || (data.story_id as string) || "",
              source: tc.source || ("ai_generated" as const),
              created_at: tc.created_at || new Date().toISOString(),
            })),
          ]);
          appendAssistantMessage(`สร้าง ${data.test_cases.length} test cases สำเร็จ ✓`);
        }
        if (data.analysis) {
          appendAssistantMessage(formatAnalysis(data.analysis));
        }
        if (data.release_score) {
          setReleaseScore(data.release_score);
          appendAssistantMessage(formatReleaseScore(data.release_score));
        }
        if (data.message) {
          appendAssistantMessage(data.message);
        }
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
      }
    };

    ws.onerror = () => {
      setActiveAgent(null);
      appendAssistantMessage("เชื่อมต่อไม่สำเร็จ กรุณาลองใหม่อีกครั้ง");
    };

    ws.onclose = () => setActiveAgent(null);

    return () => ws.close();
  }, [sessionId]);

  const appendAssistantMessage = (content: string, link?: { label: string; url: string }) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content, timestamp: new Date(), link },
    ]);
  };

  const appendStreamDelta = (delta: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === "assistant") {
        return [...prev.slice(0, -1), { ...last, content: last.content + delta }];
      }
      return [...prev, { id: crypto.randomUUID(), role: "assistant", content: delta, timestamp: new Date() }];
    });
  };

  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content, timestamp: new Date() },
    ]);
    wsRef.current.send(JSON.stringify({ type: "user_message", content, project_id: projectId }));
  }, [projectId]);

  return { messages, activeAgent, sendMessage, testCases, releaseScore, scripts, findings };
}

function formatAnalysis(analysis: Record<string, unknown>): string {
  const parts: string[] = [];
  if (Array.isArray(analysis.ambiguities) && analysis.ambiguities.length) {
    parts.push(`**Ambiguities:** ${(analysis.ambiguities as string[]).join(", ")}`);
  }
  if (Array.isArray(analysis.missing_requirements) && analysis.missing_requirements.length) {
    parts.push(`**Missing:** ${(analysis.missing_requirements as string[]).join(", ")}`);
  }
  if (Array.isArray(analysis.risk_areas) && analysis.risk_areas.length) {
    parts.push(`**Risk Areas:** ${(analysis.risk_areas as string[]).join(", ")}`);
  }
  return parts.join("\n");
}

function formatReleaseScore(score: { score: number; recommendation: string; findings: string[] }): string {
  const emoji = score.recommendation === "go" ? "✅" : score.recommendation === "no_go" ? "🚫" : "⚠️";
  return `${emoji} Release Score: **${score.score}/100** — ${score.recommendation.replace("_", " ").toUpperCase()}\n\n${score.findings.join("\n")}`;
}

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
