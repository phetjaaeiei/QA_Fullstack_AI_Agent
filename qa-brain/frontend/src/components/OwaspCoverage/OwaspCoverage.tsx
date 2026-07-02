import type { SecurityFinding } from "../../lib/types";
import { CoverageCell } from "./CoverageCell";
import { CoverageLegend } from "./CoverageLegend";

interface OwaspCoverageProps {
  findings: SecurityFinding[];
}

export function OwaspCoverage({ findings }: OwaspCoverageProps) {
  const storyIds = Array.from(new Set(findings.map((f) => f.story_id))).sort();
  const categories = Array.from(new Set(findings.map((f) => f.owasp_category))).sort();

  const findingFor = (storyId: string, category: string): SecurityFinding | null =>
    findings.find((f) => f.story_id === storyId && f.owasp_category === category) || null;

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border">
      <div className="px-4 py-3 border-b space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-800">OWASP Coverage</h2>
          <span className="text-xs text-slate-500">{storyIds.length} stories mapped</span>
        </div>
        <CoverageLegend />
      </div>

      <div className="flex-1 overflow-auto">
        {storyIds.length === 0 ? (
          <p className="text-center text-slate-400 text-sm py-8">
            ยังไม่มี OWASP mapping — ลอง "map story to owasp for PROJ-123" จาก chat
          </p>
        ) : (
          <table className="border-collapse w-full">
            <thead>
              <tr>
                <th className="sticky top-0 left-0 z-20 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b border-r">
                  Story
                </th>
                {categories.map((category) => (
                  <th
                    key={category}
                    className="sticky top-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-600 border-b whitespace-nowrap"
                  >
                    {category}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {storyIds.map((storyId) => (
                <tr key={storyId}>
                  <th className="sticky left-0 z-10 bg-white p-2 text-left text-xs font-medium text-slate-700 border-r whitespace-nowrap">
                    {storyId}
                  </th>
                  {categories.map((category) => (
                    <CoverageCell key={category} finding={findingFor(storyId, category)} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
