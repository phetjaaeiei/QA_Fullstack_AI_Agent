import { useState } from "react";
import type { TestCase, ReleaseScore } from "../../lib/types";

const TYPE_COLORS: Record<string, string> = {
  functional: "bg-blue-100 text-blue-700",
  edge: "bg-yellow-100 text-yellow-700",
  negative: "bg-red-100 text-red-700",
  security: "bg-purple-100 text-purple-700",
  e2e: "bg-green-100 text-green-700",
  performance: "bg-orange-100 text-orange-700",
};

const PRIORITY_COLORS: Record<string, string> = {
  high: "text-red-600 font-semibold",
  medium: "text-yellow-600",
  low: "text-slate-400",
};

interface TestCasePanelProps {
  testCases: TestCase[];
  releaseScore: ReleaseScore | null;
}

export function TestCasePanel({ testCases, releaseScore }: TestCasePanelProps) {
  const [filter, setFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const types = ["all", "functional", "edge", "negative", "security", "e2e"];
  const filtered = filter === "all" ? testCases : testCases.filter((tc) => tc.type === filter);

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border">
      <div className="px-4 py-3 border-b">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-slate-800">Test Cases</h2>
          <span className="text-xs text-slate-500">{testCases.length} total</span>
        </div>

        {releaseScore && (
          <div className={`rounded px-3 py-2 text-sm mb-2 ${
            releaseScore.recommendation === "go" ? "bg-green-50 border border-green-200" :
            releaseScore.recommendation === "no_go" ? "bg-red-50 border border-red-200" :
            "bg-yellow-50 border border-yellow-200"
          }`}>
            <span className="font-bold">{releaseScore.score}/100</span>
            <span className="ml-2 capitalize">{releaseScore.recommendation.replaceAll("_", " ")}</span>
          </div>
        )}

        <div className="flex gap-1 flex-wrap">
          {types.map((type) => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                filter === type ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {type} {type !== "all" && `(${testCases.filter((tc) => tc.type === type).length})`}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto divide-y">
        {filtered.length === 0 && (
          <p className="text-center text-slate-400 text-sm py-8">
            ยังไม่มี test cases — ลอง generate จาก chat
          </p>
        )}
        {filtered.map((tc) => (
          <div key={tc.id} className="p-3 hover:bg-slate-50 cursor-pointer" onClick={() => setExpanded(expanded === tc.id ? null : tc.id)}>
            <div className="flex items-start gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${TYPE_COLORS[tc.type] || "bg-slate-100 text-slate-600"}`}>
                {tc.type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-800 truncate">{tc.title}</p>
                <p className={`text-xs ${PRIORITY_COLORS[tc.priority]}`}>{tc.priority} priority</p>
              </div>
            </div>
            {expanded === tc.id && (
              <div className="mt-2 ml-1 text-xs text-slate-600 space-y-1">
                <p className="font-medium text-slate-700">Steps:</p>
                <ol className="list-decimal list-inside space-y-0.5">
                  {tc.steps.map((step, i) => <li key={i}>{step}</li>)}
                </ol>
                <p className="font-medium text-slate-700 mt-1">Expected:</p>
                <p>{tc.expected_result}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
