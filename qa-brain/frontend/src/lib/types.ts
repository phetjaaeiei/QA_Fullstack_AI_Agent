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

export interface AutomationScript {
  id: string;
  story_id: string;
  framework: "playwright" | "robot";
  content: string;
  health_status: "healthy" | "flaky" | "broken";
  ci_run_url: string | null;
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
    script?: { framework: "playwright" | "robot"; content: string };
    formatted_script?: { content: string };
    healing?: { alternatives: string[]; strategy: string };
    classification?: { root_cause: string; explanation: string; failed_step: string };
    fix?: { content: string; explanation: string };
    test_data?: { label: string; value: string }[];
    traceability_mapping?: { story_id: string; covers_acceptance_criteria: boolean; confidence: string; notes: string };
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
