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
  link?: { label: string; url: string };
}
