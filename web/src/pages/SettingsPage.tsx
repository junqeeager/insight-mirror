import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  changePassword,
  deleteAccount,
  exchangeYouTubeToken,
  exportAccountData,
  fetchAdminUsers,
  fetchSources,
  fetchYouTubeAuthUrl,
  fetchStats,
  patchAdminUser,
  saveSource,
  startSync,
  testSource,
  uploadYouTubeTakeout,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import {
  ErrorState,
  Loading,
  MetricCard,
  PageHeader,
  SourcePill,
} from "../components/ui";
import { mockSources, mockStats } from "../data/mock";
import { downloadBlob } from "../lib/format";
import type { SourceConfig, Stats, User } from "../types";

interface FieldDef {
  key: string;
  label: string;
  secret?: boolean;
  kind?: "textarea" | "select";
  options?: string[];
}

const FIELDS: Record<string, FieldDef[]> = {
  bilibili: [
    { key: "cookie", label: "B站 Cookie（SESSDATA=...; bili_jct=...）", secret: true },
    { key: "csrf", label: "B站 CSRF（bili_jct）", secret: true },
  ],
  github: [
    { key: "token", label: "GitHub Token", secret: true },
    { key: "username", label: "GitHub 用户名" },
    { key: "include_repos", label: "包含仓库（逗号分隔）" },
  ],
  rss: [
    {
      key: "feeds",
      label: "RSS 订阅源（每行：url|分类，如 https://x.com/rss|科技）",
      kind: "textarea",
    },
  ],
  browser_history: [
    {
      key: "browser",
      label: "浏览器",
      kind: "select",
      options: ["chrome", "firefox", "edge"],
    },
    { key: "history_path", label: "历史记录路径（auto 自动）" },
  ],
  youtube: [],
};

function sourceToValues(source: SourceConfig): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of FIELDS[source.source] ?? []) {
    const raw = source.config?.[field.key];
    if (field.kind === "textarea" && Array.isArray(raw)) {
      values[field.key] = raw
        .map((item) =>
          typeof item === "string"
            ? item
            : `${String((item as { url?: string }).url ?? "")}|${String(
                (item as { category?: string }).category ?? "",
              )}`,
        )
        .join("\n");
    } else if (Array.isArray(raw)) {
      values[field.key] = raw.join(", ");
    } else {
      values[field.key] = raw === undefined || raw === null ? "" : String(raw);
    }
  }
  return values;
}

function valuesToConfig(
  source: string,
  values: Record<string, string>,
): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  for (const field of FIELDS[source] ?? []) {
    const value = values[field.key] ?? "";
    if (field.kind === "textarea") {
      config[field.key] = value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [url = "", category = "rss"] = line.split("|");
          return { url: url.trim(), category: category.trim() };
        });
    } else if (source === "github" && field.key === "include_repos") {
      config[field.key] = value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    } else {
      config[field.key] = value;
    }
  }
  return config;
}

export function SettingsPage() {
  const { isAuthenticated, isAdmin, logout, requireAuth, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sources, setSources] = useState<SourceConfig[]>(mockSources);
  const [loadingSources, setLoadingSources] = useState(false);
  const [values, setValues] = useState<Record<string, Record<string, string>>>(() =>
    Object.fromEntries(
      mockSources.map((source) => [source.source, sourceToValues(source)]),
    ),
  );
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(mockSources.map((source) => [source.source, source.enabled])),
  );
  const [stats, setStats] = useState<Stats>(mockStats);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [users, setUsers] = useState<User[]>([]);
  const [resetPasswords, setResetPasswords] = useState<Record<string, string>>({});
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");

  useEffect(() => {
    setNotice("");
    if (!isAuthenticated) {
      setSources(mockSources);
      setStats(mockStats);
      const mockValues: Record<string, Record<string, string>> = {};
      const mockEnabled: Record<string, boolean> = {};
      for (const source of mockSources) {
        mockValues[source.source] = sourceToValues(source);
        mockEnabled[source.source] = source.enabled;
      }
      setValues(mockValues);
      setEnabled(mockEnabled);
      setError("");
      return;
    }

    let active = true;
    setLoadingSources(true);
    setError("");
    fetchSources()
      .then((result) => {
        if (!active) return;
        setSources(result);
        const nextValues: Record<string, Record<string, string>> = {};
        const nextEnabled: Record<string, boolean> = {};
        for (const source of result) {
          nextValues[source.source] = sourceToValues(source);
          nextEnabled[source.source] = source.enabled;
        }
        setValues(nextValues);
        setEnabled(nextEnabled);
        setLoadingSources(false);
      })
      .catch((err) => {
        if (!active) return;
        setLoadingSources(false);
        if (err?.response?.status !== 401) {
          setError(err?.response?.data?.detail ?? "数据源配置加载失败");
        }
      });

    fetchStats()
      .then((result) => active && setStats(result))
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated && isAdmin) {
      fetchAdminUsers()
        .then(setUsers)
        .catch((err) => {
          if (err?.response?.status !== 401) setError("用户列表加载失败");
        });
    } else {
      setUsers([]);
    }
  }, [isAuthenticated, isAdmin]);

  useEffect(() => {
    const status = searchParams.get("youtube");
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const clear = () => setSearchParams({}, { replace: true });
    const applySources = (result: SourceConfig[]) => {
      setSources(result);
      const nextValues: Record<string, Record<string, string>> = {};
      const nextEnabled: Record<string, boolean> = {};
      for (const item of result) {
        nextValues[item.source] = sourceToValues(item);
        nextEnabled[item.source] = item.enabled;
      }
      setValues(nextValues);
      setEnabled(nextEnabled);
    };

    if (status === "ok") {
      setNotice(searchParams.get("message") || "YouTube 已连接");
      fetchSources().then(applySources).catch(() => undefined);
      clear();
      return;
    }
    if (status === "error") {
      setError(searchParams.get("message") || "YouTube 连接失败");
      clear();
      return;
    }
    if (!code || !state) return;
    setNotice("");
    setError("");
    exchangeYouTubeToken(code, state)
      .then(async (result) => {
        setNotice(result.message);
        const refreshed = await fetchSources();
        applySources(refreshed);
      })
      .catch((err) => {
        setError(
          (err as { response?: { data?: { detail?: string } } })?.response?.data
            ?.detail ?? "YouTube 连接失败",
        );
      })
      .finally(() => {
        clear();
      });
  }, [searchParams, setSearchParams]);

  const updateValue = useCallback(
    (source: string, key: string, value: string) => {
      setValues((prev) => ({
        ...prev,
        [source]: { ...(prev[source] ?? {}), [key]: value },
      }));
    },
    [],
  );

  async function handleSave(source: string) {
    setNotice("");
    setError("");
    try {
      await saveSource(source, {
        config: valuesToConfig(source, values[source] ?? {}),
        enabled: enabled[source] ?? false,
      });
      setNotice(`${source} 配置已保存`);
      const refreshed = await fetchSources();
      setSources(refreshed);
      const nextValues: Record<string, Record<string, string>> = {};
      const nextEnabled: Record<string, boolean> = {};
      for (const item of refreshed) {
        nextValues[item.source] = sourceToValues(item);
        nextEnabled[item.source] = item.enabled;
      }
      setValues(nextValues);
      setEnabled(nextEnabled);
      window.setTimeout(() => setNotice(""), 5000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "保存失败",
      );
    }
  }

  async function handleTest(source: string) {
    setNotice("");
    setError("");
    try {
      const result = await testSource(source);
      setNotice(`${source}: ${result.message}`);
      window.setTimeout(() => setNotice(""), 6000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "连接测试失败",
      );
    }
  }

  async function handleSync(source: string) {
    setNotice("");
    setError("");
    try {
      const task = await startSync(source);
      setNotice(`${source} 同步任务已启动：${task.task_id.slice(0, 8)}…`);
      window.setTimeout(() => setNotice(""), 8000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "同步启动失败",
      );
    }
  }

  async function handleConnectYouTube() {
    setNotice("");
    setError("");
    try {
      const { url } = await fetchYouTubeAuthUrl();
      window.location.assign(url);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "无法生成 YouTube 授权地址",
      );
    }
  }

  async function handleTakeoutFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setNotice("");
    setError("");
    try {
      const result = await uploadYouTubeTakeout(file);
      setNotice(
        `已导入 ${result.imported} 条观看记录（识别 ${result.parsed} 条）`,
      );
      window.setTimeout(() => setNotice(""), 8000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Takeout 导入失败",
      );
    }
  }

  function withAuth(action: () => void | Promise<void>) {
    requireAuth(() => void Promise.resolve(action()));
  }

  async function handleServerExport(format: "csv" | "json") {
    setNotice("");
    setError("");
    try {
      const blob = await exportAccountData(format);
      downloadBlob(
        blob,
        `events_${user?.username ?? "user"}.${format}`,
      );
      setNotice(`数据已导出为 ${format.toUpperCase()}`);
      window.setTimeout(() => setNotice(""), 6000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "导出失败",
      );
    }
  }

  async function handleChangePassword() {
    setNotice("");
    setError("");
    try {
      await changePassword(oldPassword, newPassword);
      setOldPassword("");
      setNewPassword("");
      setNotice("密码已修改，请使用新密码重新登录");
      window.setTimeout(() => setNotice(""), 6000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "修改密码失败",
      );
    }
  }

  async function handleDeleteAccount() {
    if (
      !window.confirm(
        "此操作将永久删除你的账号与全部行为数据，且不可恢复。确定继续吗？",
      )
    ) {
      return;
    }
    setNotice("");
    setError("");
    try {
      await deleteAccount(deletePassword);
      setDeletePassword("");
      await logout();
      setNotice("账号已注销");
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "注销失败",
      );
    }
  }

  async function adminPatch(userId: string, body: { status?: string; password?: string }) {
    try {
      await patchAdminUser(userId, body);
      const next = await fetchAdminUsers();
      setUsers(next);
      setResetPasswords((prev) => ({ ...prev, [userId]: "" }));
      setNotice("用户状态已更新");
      window.setTimeout(() => setNotice(""), 4000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "操作失败",
      );
    }
  }

  return (
    <div>
      <PageHeader
        title="设置"
        subtitle="管理你的数据源、导出数据；管理员可管理用户"
        actions={
          !isAuthenticated && (
            <button
              type="button"
              className="button primary"
              onClick={() => requireAuth()}
            >
              登录后管理真实配置
            </button>
          )
        }
      />

      {error && <ErrorState message={error} />}
      {notice && <p className="form-success">{notice}</p>}
      {loadingSources && <Loading label="正在加载数据源配置…" />}

      <section className="card">
        <div className="section-heading">
          <h2>我的数据源</h2>
          <span className="muted">
            {isAuthenticated
              ? "凭据加密保存在本地数据库，只对你自己可见"
              : "预览模式下仅展示示例配置"}
          </span>
        </div>

        <div className="source-list">
          {sources.map((source) => {
            const sourceValues = values[source.source] ?? {};
            return (
              <div className="source-card" key={source.source}>
                <div className="source-card-header">
                  <h3>
                    <SourcePill source={source.source} />
                    <span className="muted">{source.source}</span>
                  </h3>
                  <label className="switch">
                    <input
                      type="checkbox"
                      disabled={!isAuthenticated}
                      checked={enabled[source.source] ?? source.enabled}
                      onChange={(e) =>
                        setEnabled((prev) => ({
                          ...prev,
                          [source.source]: e.target.checked,
                        }))
                      }
                    />
                    <span>启用此数据源</span>
                  </label>
                </div>

                <div className="source-fields">
                  {(FIELDS[source.source] ?? []).map((field) => (
                    <label className="field" key={field.key}>
                      <span>{field.label}</span>
                      {field.kind === "textarea" ? (
                        <textarea
                          rows={3}
                          disabled={!isAuthenticated}
                          value={sourceValues[field.key] ?? ""}
                          onChange={(e) =>
                            updateValue(source.source, field.key, e.target.value)
                          }
                        />
                      ) : field.kind === "select" ? (
                        <select
                          disabled={!isAuthenticated}
                          value={sourceValues[field.key] ?? ""}
                          onChange={(e) =>
                            updateValue(source.source, field.key, e.target.value)
                          }
                        >
                          {field.options?.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={field.secret ? "password" : "text"}
                          disabled={!isAuthenticated}
                          value={sourceValues[field.key] ?? ""}
                          placeholder={field.secret ? "已脱敏，留空保持不变" : ""}
                          onChange={(e) =>
                            updateValue(source.source, field.key, e.target.value)
                          }
                        />
                      )}
                    </label>
                  ))}
                </div>

                <div className="source-actions">
                  <button
                    type="button"
                    className="button primary"
                    onClick={() => withAuth(() => handleSave(source.source))}
                  >
                    保存
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() => withAuth(() => handleTest(source.source))}
                  >
                    测试连接
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() => withAuth(() => handleSync(source.source))}
                  >
                    同步此源
                  </button>
                </div>
                {source.source === "youtube" && isAuthenticated && (
                  <div className="youtube-actions">
                    {!enabled[source.source] && (
                      <button
                        type="button"
                        className="button primary"
                        onClick={() => withAuth(handleConnectYouTube)}
                      >
                        连接 YouTube
                      </button>
                    )}
                    <label className="button file-button">
                      导入观看历史（Takeout JSON）
                      <input
                        type="file"
                        accept=".json,application/json"
                        hidden
                        onChange={handleTakeoutFile}
                      />
                    </label>
                    <p className="muted">
                      喜欢/订阅在连接后自动同步；完整观看历史需在 Google
                      Takeout 导出 YouTube 数据并上传 watch-history.json。
                    </p>
                  </div>
                )}
                {!isAuthenticated && (
                  <p className="muted">登录后即可保存并同步真实数据源。</p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="card">
        <h2>我的数据统计</h2>
        <div className="metric-grid">
          <MetricCard label="总事件数" value={stats.total} accent="blue" />
          <MetricCard
            label="数据源数"
            value={Object.keys(stats.by_source ?? {}).length}
            accent="green"
          />
          <MetricCard
            label="事件类型数"
            value={Object.keys(stats.by_type ?? {}).length}
            accent="orange"
          />
        </div>
        {Object.keys(stats.by_source ?? {}).length > 0 && (
          <ul className="plain-list">
            {Object.entries(stats.by_source).map(([source, count]) => (
              <li key={source}>
                <SourcePill source={source} />
                <b>{count} 条</b>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>数据导出</h2>
        <p className="muted">从服务端导出你的全部事件，仅登录后可下载真实数据。</p>
        <button
          type="button"
          className="button primary"
          onClick={() => withAuth(() => handleServerExport("csv"))}
        >
          导出 CSV
        </button>
        <button
          type="button"
          className="button"
          onClick={() => withAuth(() => handleServerExport("json"))}
        >
          导出 JSON
        </button>
      </section>

      <section className="card">
        <h2>账号管理</h2>
        <p className="muted">修改密码后，所有已登录会话将立即失效。</p>
        <div className="account-password">
          <input
            type="password"
            placeholder="当前密码"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
          <input
            type="password"
            placeholder="新密码（至少 8 位）"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <button
            type="button"
            className="button primary"
            disabled={newPassword.length < 8 || !oldPassword}
            onClick={() => withAuth(() => handleChangePassword())}
          >
            修改密码
          </button>
        </div>
        <h3 className="section-heading">注销账号</h3>
        <p className="muted">
          永久删除你的账号与全部行为数据，不可恢复。请谨慎操作。
        </p>
        <div className="account-delete">
          <input
            type="password"
            placeholder="输入当前密码确认"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
          />
          <button
            type="button"
            className="button danger"
            disabled={!deletePassword}
            onClick={() => withAuth(() => handleDeleteAccount())}
          >
            注销账号
          </button>
        </div>
      </section>

      {isAuthenticated && isAdmin && (
        <section className="card">
          <h2>用户管理（管理员）</h2>
          <div className="user-table">
            {users.map((u) => (
              <div className="user-row" key={u.id}>
                <div className="user-info">
                  <strong>{u.username}</strong>
                  <span className="muted">
                    {u.role} · {u.status}
                  </span>
                </div>
                <div className="user-actions">
                  {u.status === "pending" && (
                    <button
                      type="button"
                      className="button small"
                      onClick={() => adminPatch(u.id, { status: "active" })}
                    >
                      批准
                    </button>
                  )}
                  {u.status === "active" && (
                    <button
                      type="button"
                      className="button small danger"
                      onClick={() => adminPatch(u.id, { status: "disabled" })}
                    >
                      禁用
                    </button>
                  )}
                  {u.status === "disabled" && (
                    <button
                      type="button"
                      className="button small"
                      onClick={() => adminPatch(u.id, { status: "active" })}
                    >
                      启用
                    </button>
                  )}
                  <input
                    type="password"
                    placeholder="重置密码（至少 8 位）"
                    value={resetPasswords[u.id] ?? ""}
                    onChange={(e) =>
                      setResetPasswords((prev) => ({
                        ...prev,
                        [u.id]: e.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    className="button small"
                    disabled={(resetPasswords[u.id] ?? "").length < 8}
                    onClick={() =>
                      adminPatch(u.id, { password: resetPasswords[u.id] })
                    }
                  >
                    重置
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {isAuthenticated && !isAdmin && (
        <p className="muted">用户管理区域仅对管理员开放。</p>
      )}
    </div>
  );
}
