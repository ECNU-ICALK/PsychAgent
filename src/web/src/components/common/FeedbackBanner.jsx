import { AlertCircle, CheckCircle2, Info } from "lucide-react";

const toneMap = {
  success: {
    icon: CheckCircle2,
    style: "border-emerald-200 bg-emerald-50 text-emerald-800",
  },
  error: {
    icon: AlertCircle,
    style: "border-rose-200 bg-rose-50 text-rose-800",
  },
  info: {
    icon: Info,
    style: "border-sky-200 bg-sky-50 text-sky-800",
  },
};

export function FeedbackBanner({ feedback, onClose }) {
  if (!feedback?.message) return null;

  const tone = toneMap[feedback.type] || toneMap.info;
  const Icon = tone.icon;

  return (
    <div className={`mx-4 mt-3 flex items-start justify-between rounded-xl border px-4 py-3 text-sm shadow-sm ${tone.style}`}>
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <p className="leading-6">{feedback.message}</p>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="ml-3 rounded px-2 py-0.5 text-xs font-medium text-current/80 hover:bg-white/70"
      >
        关闭
      </button>
    </div>
  );
}
