import { Activity, ShieldAlert, Target } from "lucide-react";

const SESSION_FOCUS_DEFAULT = [
  "建立初始关系与咨询框架",
  "收集稳定背景信息",
  "了解当前主要困扰与近期变化",
  "澄清来访动机与期待",
  "进行基础身心与功能评估",
  "识别潜在风险与可用资源",
  "会谈总结与协作性反馈",
];

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-slate-800">
        <Icon className="h-4 w-4" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="text-xs leading-6 text-slate-600">{children}</div>
    </section>
  );
}

function buildPromptSessionFocus(currentVisit) {
  const focus = [];
  const appendUnique = (rawValue) => {
    const text = String(rawValue ?? "").trim();
    if (!text || focus.includes(text)) return;
    focus.push(text);
  };

  (currentVisit?.psych_context?.session_focus || []).forEach(appendUnique);
  if (focus.length === 0) {
    SESSION_FOCUS_DEFAULT.forEach(appendUnique);
  }
  return focus.slice(0, 8);
}

export function RightPanel({ currentCourse, currentVisit, embedded = false }) {
  const stage = currentVisit?.stage || currentCourse?.current_stage;
  const sessionFocus = buildPromptSessionFocus(currentVisit);

  const wrapperClassName = embedded
    ? "space-y-4"
    : "hidden shrink-0 xl:block xl:w-64 2xl:w-72 border-l border-slate-200 bg-slate-50/70 p-4 overflow-y-auto";

  return (
    <aside className={wrapperClassName}>
      <Section title="当前阶段" icon={Activity}>
        {currentCourse ? (
          <div className="space-y-1">
            <p className="font-semibold text-slate-800">{stage?.label || "未开始"}</p>
            <p>当前处于第 {currentVisit?.visit_no || currentCourse?.latest_visit_no || 0} 次会谈。</p>
          </div>
        ) : (
          <p>选择疗程后可查看当前阶段与进度。</p>
        )}
      </Section>

      <Section title="咨询目标" icon={Target}>
        {currentCourse ? (
          sessionFocus.length > 0 ? (
            <ul className="space-y-1">
              {sessionFocus.map((focusItem, index) => (
                <li key={`${index}-${focusItem}`} className="flex items-start gap-2">
                  <span className="mt-2 h-1.5 w-1.5 rounded-full bg-teal-500" />
                  <span>{focusItem}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>当前会谈暂无目标信息。</p>
          )
        ) : (
          <p>创建疗程后可在此查看和维护咨询目标。</p>
        )}
      </Section>

      <Section title="支持与提醒" icon={ShieldAlert}>
        <ul className="space-y-1">
          <li>AI 内容仅供参考，不替代专业医疗建议。</li>
          <li>如遇紧急心理危机，请尽快联系当地急救资源或专业机构。</li>
          <li>后续可扩展为会后任务与家庭练习模块，当前先提供提醒占位。</li>
        </ul>
      </Section>
    </aside>
  );
}
