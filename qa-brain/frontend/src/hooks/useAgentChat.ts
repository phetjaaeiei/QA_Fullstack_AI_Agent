import { useState, useEffect, useRef, useCallback } from "react";
import type { AgentEvent, Message, TestCase, ReleaseScore } from "../lib/types";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

export function useAgentChat(sessionId: string, projectId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [releaseScore, setReleaseScore] = useState<ReleaseScore | null>(null);
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
      }
    };

    ws.onerror = () => {
      setActiveAgent(null);
      appendAssistantMessage("เชื่อมต่อไม่สำเร็จ กรุณาลองใหม่อีกครั้ง");
    };

    ws.onclose = () => setActiveAgent(null);

    return () => ws.close();
  }, [sessionId]);

  const appendAssistantMessage = (content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content, timestamp: new Date() },
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

  return { messages, activeAgent, sendMessage, testCases, releaseScore };
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
