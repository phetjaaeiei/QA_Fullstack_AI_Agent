const LEGEND_ITEMS = [
  { label: "Covered", className: "bg-green-200" },
  { label: "Gap", className: "bg-red-200" },
  { label: "Not applicable", className: "bg-slate-100" },
  { label: "No data", className: "bg-white border border-dashed border-slate-300" },
];

export function CoverageLegend() {
  return (
    <div className="flex items-center gap-3 flex-wrap text-xs text-slate-600">
      {LEGEND_ITEMS.map((item) => (
        <div key={item.label} className="flex items-center gap-1">
          <span className={`inline-block h-3 w-3 rounded ${item.className}`} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}
