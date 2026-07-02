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
