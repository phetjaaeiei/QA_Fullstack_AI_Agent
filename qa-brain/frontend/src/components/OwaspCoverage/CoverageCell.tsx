import type { SecurityFinding } from "../../lib/types";

const STATUS_COLORS: Record<string, string> = {
  covered: "bg-green-200 hover:bg-green-300",
  gap: "bg-red-200 hover:bg-red-300",
  not_applicable: "bg-slate-100 hover:bg-slate-200",
};

const STATUS_SYMBOLS: Record<string, string> = {
  covered: "■",
  gap: "□",
  not_applicable: "–",
};

interface CoverageCellProps {
  finding: SecurityFinding | null;
}

export function CoverageCell({ finding }: CoverageCellProps) {
  if (!finding) {
    return (
      <td className="p-0.5">
        <button
          type="button"
          disabled
          title="No data"
          className="h-8 w-8 min-h-8 min-w-8 rounded bg-white border border-dashed border-slate-300 text-slate-300 text-xs"
        >
          {"·"}
        </button>
      </td>
    );
  }

  const tooltip = `${finding.owasp_category} — ${finding.status} (risk: ${finding.risk_level})\n${finding.notes}`;

  return (
    <td className="p-0.5">
      <button
        type="button"
        title={tooltip}
        className={`h-8 w-8 min-h-8 min-w-8 rounded text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 ${
          STATUS_COLORS[finding.status] || "bg-slate-100"
        }`}
      >
        {STATUS_SYMBOLS[finding.status] || "?"}
      </button>
    </td>
  );
}
