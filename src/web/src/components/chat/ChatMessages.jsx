import { Brain, FolderOpen, LogIn, MessageSquare, User } from "lucide-react";
import { EmptyState } from "../common/EmptyState";

function extractResponseText(rawText) {
  const text = String(rawText ?? "");
  const match = text.match(/<response>([\s\S]*?)<\/response>/i);
  if (match && typeof match[1] === "string") {
    return match[1].trim();
  }
  return text;
}

function ChatEmptyState({ hasToken, currentCourse }) {
  if (!hasToken) {
    return (
      <EmptyState
        icon={LogIn}
        title="登录后即可开始咨询"
        description="请先登录账号，再选择咨询流派并创建疗程。"
      />
    );
  }

  if (!currentCourse) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="先选择或创建疗程"
        description="建议先在左侧选择流派并新建疗程，系统会自动创建第一次会谈。"
      />
    );
  }

  return (
    <EmptyState
      icon={MessageSquare}
      title="当前疗程还没有会谈内容"
      description="点击“开始第 N 次会谈”后，即可在此查看完整对话记录。"
    />
  );
}

export function ChatMessages({ currentCourse, currentVisit, currentSchool, isTyping, chatEndRef, hasToken }) {
  const shouldShowEmpty = !currentVisit;

  return (
    <div className="flex-1 space-y-6 overflow-y-auto bg-slate-50/40 p-4 pb-28 sm:p-6 sm:pb-8">
      {shouldShowEmpty ? (
        <div className="mx-auto mt-6 max-w-2xl">
          <ChatEmptyState hasToken={hasToken} currentCourse={currentCourse} />
        </div>
      ) : null}

	      {currentVisit?.messages?.map((message) => (
        <div
          key={message.id}
          className={`flex w-full ${message.role === "user" ? "justify-end" : "justify-start"}`}
        >
          {message.role === "system" ? (
            <div className="my-4 flex w-full justify-center">
              <span className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                {message.text}
              </span>
            </div>
          ) : (
            <div
              className={`flex max-w-[85%] gap-3 md:max-w-[72%] ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}
            >
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm md:h-10 md:w-10 ${
                  message.role === "user"
                    ? "bg-slate-200 text-slate-600"
                    : `${currentSchool?.color || "bg-teal-500"} text-white`
                }`}
              >
                {message.role === "user" ? <User className="h-5 w-5" /> : <Brain className="h-5 w-5" />}
              </div>

              <div
                className={`whitespace-pre-wrap rounded-2xl p-3 text-sm leading-relaxed shadow-sm md:p-4 md:text-base ${
                  message.role === "user"
                    ? "rounded-tr-none bg-slate-800 text-white"
                    : "rounded-tl-none border border-slate-100 bg-white text-slate-700"
                }`}
              >
	                {message.role === "assistant" ? extractResponseText(message.text) : message.text}
              </div>
            </div>
          )}
        </div>
      ))}

      {isTyping ? (
        <div className="flex w-full justify-start">
          <div className="flex max-w-[80%] gap-3">
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white opacity-70 ${
                currentSchool?.color || "bg-teal-500"
              }`}
            >
              <Brain className="h-5 w-5" />
            </div>
            <div className="flex h-12 items-center gap-1 rounded-2xl rounded-tl-none border border-slate-100 bg-white p-4 shadow-sm">
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-75" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-150" />
            </div>
          </div>
        </div>
      ) : null}

      <div ref={chatEndRef} />
    </div>
  );
}
