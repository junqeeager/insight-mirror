import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LoginModal } from "../auth/LoginModal";

const NAV_ITEMS = [
  { to: "/", label: "总览", icon: "🏠", end: true },
  { to: "/time", label: "时间视图", icon: "📈" },
  { to: "/graph", label: "关系视图", icon: "🕸️" },
  { to: "/report", label: "报告视图", icon: "📋" },
  { to: "/settings", label: "设置", icon: "⚙️" },
];

export function Layout() {
  const { user, isAuthenticated, isAdmin, openLogin, logout, requireAuth } =
    useAuth();

  function handleLogout() {
    requireAuth(() => void logout());
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-icon">🧠</span>
          <span>
            <strong>个人认知画像</strong>
            <small>Personal Cognitive Profile</small>
          </span>
        </NavLink>

        <nav className="nav-list" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? "nav-link active" : "nav-link"
              }
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {isAuthenticated ? (
            <>
              <div className="account-mini">
                <strong>{user?.username}</strong>
                <span>{isAdmin ? "管理员" : "用户"}</span>
              </div>
              <button type="button" className="button ghost" onClick={() => void logout()}>
                退出登录
              </button>
            </>
          ) : (
            <>
              <div className="account-mini">
                <strong>未登录</strong>
                <span>正在浏览示例预览</span>
              </div>
              <button type="button" className="button primary" onClick={openLogin}>
                登录 / 注册
              </button>
            </>
          )}
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-title">
            {!isAuthenticated && <span className="preview-badge">预览 · 示例数据</span>}
          </div>
          <div className="account-area">
            {isAuthenticated ? (
              <div className="account-pill">
                <span className="avatar" aria-hidden>
                  {user?.username.slice(0, 1).toUpperCase()}
                </span>
                <span className="account-name">{user?.username}</span>
                <span className={`role-tag ${isAdmin ? "admin" : ""}`}>
                  {isAdmin ? "管理员" : "用户"}
                </span>
                <button
                  type="button"
                  className="button ghost small"
                  onClick={handleLogout}
                >
                  退出
                </button>
              </div>
            ) : (
              <button type="button" className="button primary" onClick={openLogin}>
                登录 / 注册
              </button>
            )}
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
      <LoginModal />
    </div>
  );
}
