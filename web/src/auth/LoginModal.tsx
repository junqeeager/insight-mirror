import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "./AuthContext";

type Mode = "login" | "register";

export function LoginModal() {
  const { loginOpen, closeLogin, login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (loginOpen) {
      setError("");
      setNotice("");
      setSubmitting(false);
    }
  }, [loginOpen]);

  if (!loginOpen) return null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNotice("");

    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    if (mode === "register" && password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(username.trim(), password);
        setUsername("");
        setPassword("");
      } else {
        const message = await register(username.trim(), password);
        setNotice(message);
        setMode("login");
      }
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "操作失败，请稍后重试";
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
    setNotice("");
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={closeLogin}>
      <div
        className="modal login-modal"
        role="dialog"
        aria-modal="true"
        aria-label="登录 / 注册"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{mode === "login" ? "登录" : "注册"}</h2>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭"
            onClick={closeLogin}
          >
            ✕
          </button>
        </div>

        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => switchMode("login")}
          >
            登录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => switchMode("register")}
          >
            注册
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>用户名</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="3-32 位字母 / 数字 / 下划线 / 中文"
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "至少 8 位" : "输入密码"}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <label className="field">
              <span>确认密码</span>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="再次输入密码"
                autoComplete="new-password"
              />
            </label>
          )}

          {error && <p className="form-error">{error}</p>}
          {notice && <p className="form-success">{notice}</p>}

          <button
            type="submit"
            className="button primary"
            data-testid="auth-submit"
            disabled={submitting}
          >
            {submitting ? "提交中…" : mode === "login" ? "登录" : "注册"}
          </button>
          <p className="modal-hint">
            注册后需管理员审核启用；登录凭据仅保存在当前浏览器。
          </p>
        </form>
      </div>
    </div>
  );
}
