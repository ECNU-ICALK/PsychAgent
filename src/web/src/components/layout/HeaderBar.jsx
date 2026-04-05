import { CalendarPlus2, CheckCircle2, PlayCircle, PlusCircle, XCircle } from "lucide-react";
import { getCourseStatusText, getVisitStatusText } from "../common/statusText";
import { getSchoolDisplayName } from "../common/schoolText";

export function HeaderBar({
  currentSchool,
  currentCourse,
  currentVisit,
  selectedSchoolId,
  token,
  canCreateCourse,
  canStartNextVisit,
  canCompleteCourse,
  onOpenCreateCourseModal,
  onStartNextVisit,
  onContinueVisit,
  onCloseVisit,
  onOpenCompleteCourseModal,
}) {
  const hasOpenVisit = currentVisit?.status === "open" || Boolean(currentCourse?.active_visit_id);
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;

  const primaryAction = !currentCourse || currentCourse.status !== "active"
    ? {
        label: "新建疗程",
        icon: PlusCircle,
        onClick: onOpenCreateCourseModal,
        disabled: !canCreateCourse || !selectedSchoolId || !token,
      }
    : hasOpenVisit
    ? {
        label: "继续当前会谈",
        icon: PlayCircle,
        onClick: onContinueVisit,
        disabled: false,
      }
    : {
        label: `开始第 ${nextVisitNo} 次会谈`,
        icon: CalendarPlus2,
        onClick: onStartNextVisit,
        disabled: !canStartNextVisit,
      };

  const PrimaryIcon = primaryAction.icon;

  return (
    <header className="border-b border-slate-200 bg-white/90 px-5 py-3 backdrop-blur-sm sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <div className="ml-10 md:ml-0">
          <h1 className="text-base font-semibold text-slate-900">
            {currentSchool ? `${getSchoolDisplayName(currentSchool)} 咨询工作台` : "心理咨询工作台"}
          </h1>
          <p className="mt-1 text-xs text-slate-600">
            {!currentCourse
              ? "先创建疗程，再进入会谈流程。"
              : `疗程状态：${getCourseStatusText(currentCourse.status)}${
                  currentVisit ? ` · 会谈状态：${getVisitStatusText(currentVisit.status)}` : ""
                }`}
          </p>
        </div>

        <div className="hidden items-center gap-2 lg:flex">
          <button
            type="button"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
            className="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <PrimaryIcon className="h-3.5 w-3.5" />
            {primaryAction.label}
          </button>

          {hasOpenVisit ? (
            <button
              type="button"
              onClick={onCloseVisit}
              className="inline-flex items-center gap-1 rounded-lg bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100"
            >
              <XCircle className="h-3.5 w-3.5" />
              结束本次会谈
            </button>
          ) : null}

          {canCompleteCourse ? (
            <button
              type="button"
              onClick={onOpenCompleteCourseModal}
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              完成疗程
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
