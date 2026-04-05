import { X } from "lucide-react";
import { getSchoolDisplayName } from "../common/schoolText";

export function SchoolModal({
  open,
  token,
  schools,
  selectedSchoolId,
  currentSchool,
  onClose,
  onSelectSchool,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
        <button type="button" className="absolute right-3 top-3 text-slate-400 hover:text-slate-600" onClick={onClose}>
          <X className="h-5 w-5" />
        </button>

        <div>
          <h3 className="text-lg font-bold text-slate-800">选择咨询流派</h3>
          <p className="mt-1 text-sm text-slate-600">
            选择后会自动切换疗程列表。当前：{getSchoolDisplayName(currentSchool)}
          </p>
        </div>

        <select
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          value={selectedSchoolId}
          onChange={(event) => onSelectSchool(event.target.value)}
          disabled={!token}
        >
          <option value="" disabled>
            请选择流派
          </option>
          {schools.map((school) => (
            <option key={school.id} value={school.id}>
              {getSchoolDisplayName(school)}
            </option>
          ))}
        </select>

        {!token ? <p className="text-xs text-amber-600">请先登录后再切换流派。</p> : null}

        <button
          type="button"
          className="w-full rounded-lg bg-slate-100 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200"
          onClick={onClose}
        >
          关闭
        </button>
      </div>
    </div>
  );
}
