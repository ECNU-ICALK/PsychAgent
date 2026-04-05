export function StageBadge({ stage }) {
  return (
    <span
      className={`text-xs font-semibold px-2 py-1 rounded ${
        stage?.color || "bg-slate-100 text-slate-600"
      }`}
    >
      {stage?.label || "未知阶段"}
    </span>
  );
}
