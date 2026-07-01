export interface TestCase {
  id: string;
  story_id: string;
  title: string;
  type: "functional" | "edge" | "negative" | "security" | "e2e" | "performance";
  steps: string[];
  expected_result: string;
  priority: "high" | "medium" | "low";
  source: "manual" | "ai_generated";
  created_at: string;
}

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
  };
}

export interface ReleaseScore {
  score: number;
  recommendation: "go" | "no_go" | "conditional";
  findings: string[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agentEvents?: AgentEvent[];
}
