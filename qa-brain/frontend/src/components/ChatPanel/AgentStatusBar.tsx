export function AgentStatusBar({ activeAgent }: { activeAgent: string | null }) {
  if (!activeAgent) return null;
  const labels: Record<string, string> = {
    manual_qa: "Manual QA Agent",
    automation_qa: "Automation QA Agent",
    security_qa: "Security QA Agent",
    orchestrator: "QA Orchestrator",
  };
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-slate-100 border-t text-sm text-slate-600">
      <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
      <span>{labels[activeAgent] || activeAgent} กำลังทำงาน...</span>
    </div>
  );
}
