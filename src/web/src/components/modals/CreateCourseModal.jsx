import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

const INITIAL_FORM = {
  title: "",
};

export function CreateCourseModal({ open, currentSchool, onClose, onSubmit }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);

  const defaultTitle = useMemo(() => {
    if (!currentSchool?.name) return "";
    return `${currentSchool.name} 疗程`;
  }, [currentSchool?.name]);

  useEffect(() => {
    if (!open) return;
    setForm({ ...INITIAL_FORM, title: defaultTitle });
    setSubmitting(false);
  }, [open, defaultTitle]);

  if (!open) return null;

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);

    const payload = {
      title: form.title.trim(),
    };

    try {
      const ok = await onSubmit?.(payload);
      if (ok) {
        onClose?.();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
          onClick={onClose}
          disabled={submitting}
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mb-4">
          <h3 className="text-lg font-bold text-slate-800">新建疗程</h3>
          <p className="mt-1 text-sm text-slate-600">
            填写疗程标题后将自动创建第一次会谈。
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="course-title" className="mb-1 block text-sm font-medium text-slate-700">
              疗程标题
            </label>
            <input
              id="course-title"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-teal-400 focus:outline-none"
              value={form.title}
              onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              placeholder="例如：焦虑管理与认知重建"
              maxLength={80}
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              className="flex-1 rounded-lg bg-slate-100 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="flex-1 rounded-lg bg-teal-600 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={submitting}
            >
              {submitting ? "创建中..." : "创建疗程"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
