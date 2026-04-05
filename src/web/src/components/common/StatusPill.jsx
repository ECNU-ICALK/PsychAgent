const toneMap = {
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  active: "bg-teal-50 text-teal-700 border-teal-200",
  neutral: "bg-slate-100 text-slate-600 border-slate-200",
  warning: "bg-amber-50 text-amber-700 border-amber-200",
  danger: "bg-rose-50 text-rose-700 border-rose-200",
};

export function StatusPill({ text, tone = "neutral", className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        toneMap[tone] || toneMap.neutral
      } ${className}`}
    >
      {text}
    </span>
  );
}
