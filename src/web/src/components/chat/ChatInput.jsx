import { Send } from "lucide-react";

export function ChatInput({ currentCourse, currentVisit, input, isTyping, onInputChange, onSend }) {
  const nextVisitNo = (currentCourse?.latest_visit_no || 0) + 1;

  if (!currentVisit) {
    if (!currentCourse) return null;
    return (
      <div className="mb-20 border-t border-slate-200 bg-white p-4 text-center text-sm text-slate-600 lg:mb-0">
        当前疗程尚未开始会谈，请点击“开始第 {nextVisitNo} 次会谈”。
      </div>
    );
  }

  if (currentVisit.status !== "open") {
    return (
      <div className="mb-20 border-t border-slate-200 bg-white p-4 text-center text-sm text-slate-600 lg:mb-0">
        当前会谈已结束，可开始下一次会谈。
      </div>
    );
  }

  return (
    <div className="mb-20 border-t border-slate-200 bg-white p-4 lg:mb-0">
      <div className="relative mx-auto max-w-4xl">
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          placeholder="输入你的想法，按 Enter 发送，Shift + Enter 换行。"
          className="min-h-[56px] w-full max-h-32 resize-none rounded-xl border border-slate-200 bg-slate-50 py-3 pl-4 pr-12 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/20 md:text-base"
          rows={1}
        />

        <button
          type="button"
          onClick={onSend}
          disabled={!input.trim() || isTyping}
          className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center justify-center rounded-lg bg-teal-600 p-2 text-white transition-all hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>

      <p className="mt-2 text-center text-xs leading-5 text-slate-600">
        AI 回答仅供参考，不替代专业医疗建议。如有紧急情况，请立即联系当地急救资源。
      </p>
    </div>
  );
}
