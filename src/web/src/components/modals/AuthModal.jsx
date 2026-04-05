import { User, X } from "lucide-react";

export function AuthModal({
  open,
  user,
  authMode,
  authForm,
  onClose,
  onChangeMode,
  onChangeForm,
  onSubmit,
  onLogout,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[70] p-4">
      <div className="bg-white border border-slate-200 shadow-2xl rounded-2xl w-full max-w-md p-6 space-y-4 relative">
        <button className="absolute top-3 right-3 text-slate-400 hover:text-slate-600" onClick={onClose}>
          <X className="w-5 h-5" />
        </button>

        <div className="text-center space-y-1">
          <h2 className="text-xl font-bold text-slate-800">账户</h2>
          <p className="text-sm text-slate-500">
            {user ? `当前登录：${user.username}` : "请输入用户名和密码，或注册新账号。"}
          </p>
        </div>

        {!user && (
          <div className="space-y-3">
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              placeholder="用户名"
              value={authForm.username}
              onChange={(event) => onChangeForm({ ...authForm, username: event.target.value })}
            />

            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              placeholder="密码"
              type="password"
              value={authForm.password}
              onChange={(event) => onChangeForm({ ...authForm, password: event.target.value })}
            />

            <div className="flex items-center justify-between text-xs text-slate-500">
              <div>当前模式：{authMode === "login" ? "登录" : "注册"}</div>
              <button
                className="text-teal-600 hover:text-teal-700"
                onClick={() => onChangeMode(authMode === "login" ? "register" : "login")}
              >
                切换到{authMode === "login" ? "注册" : "登录"}
              </button>
            </div>

            <button
              className="w-full bg-teal-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-teal-700 transition"
              onClick={() => onSubmit(authMode)}
            >
              {authMode === "login" ? "登录" : "注册"}
            </button>
          </div>
        )}

        {user && (
          <div className="space-y-3 text-sm text-slate-600">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-slate-500" />
              <span>{user.username}</span>
            </div>

            <button
              className="w-full bg-slate-800 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-900 transition"
              onClick={onLogout}
            >
              退出登录
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
