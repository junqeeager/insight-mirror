import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  changePassword,
  deleteAccount,
  downloadYouTubeTakeoutHistory,
  exchangeYouTubeToken,
  exportAccountData,
  fetchAdminUsers,
  fetchSources,
  fetchYouTubeTakeoutHistory,
  fetchYouTubeTakeoutExportStatus,
  fetchYouTubeAuthUrl,
  fetchStats,
  fetchSyncStatus,
  patchAdminUser,
  reimportYouTubeTakeout,
  saveSource,
  startYouTubeTakeoutExport,
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
import {
  SourceCard,
  SourceEditModal,
  type SyncState,
} from "../components/SourceSettings";
import { mockSources, mockStats } from "../data/mock";
import { downloadBlob } from "../lib/format";
import { SOURCE_META, sourceToValues } from "../lib/sourceConfig";
import type { SourceConfig, Stats, User, YouTubeTakeoutFile } from "../types";

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
  const [syncStates, setSyncStates] = useState<Record<string, SyncState>>({});
  const syncTimers = useRef<Record<string, number>>({});
  const [takeoutState, setTakeoutState] = useState<SyncState | null>(null);
  const takeoutTimer = useRef<number | null>(null);
  const [takeoutFiles, setTakeoutFiles] = useState<YouTubeTakeoutFile[]>([]);
  const [takeoutFilesLoading, setTakeoutFilesLoading] = useState(false);
  const [editingSource, setEditingSource] = useState<string | null>(null);
  const [sourceQuery, setSourceQuery] = useState("");
  const [allSyncState, setAllSyncState] = useState<SyncState | null>(null);
  const allSyncTimer = useRef<number | null>(null);

  const loadTakeoutFiles = useCallback(async () => {
    if (!isAuthenticated) {
      setTakeoutFiles([]);
      setTakeoutFilesLoading(false);
      return;
    }
    setTakeoutFilesLoading(true);
    try {
      const files = await fetchYouTubeTakeoutHistory();
      setTakeoutFiles(files);
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status !== 401) {
        setTakeoutFiles([]);
      }
    } finally {
      setTakeoutFilesLoading(false);
    }
  }, [isAuthenticated]);

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
      setTakeoutFiles([]);
      setError("");
      return;
    }

    let active = true;
    setLoadingSources(true);
    setError("");
    loadTakeoutFiles();
    fetchSources()
      .then((result) => {
        if (!active) return;
        if (!Array.isArray(result) || result.length === 0) {
          setLoadingSources(false);
          setError("数据源列表为空，请检查服务端配置");
          return;
        }
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
  }, [isAuthenticated, loadTakeoutFiles]);

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

  const applySourceList = useCallback((result: SourceConfig[]) => {
    if (!Array.isArray(result) || result.length === 0) return;
    setSources(result);
    const nextValues: Record<string, Record<string, string>> = {};
    const nextEnabled: Record<string, boolean> = {};
    for (const item of result) {
      nextValues[item.source] = sourceToValues(item);
      nextEnabled[item.source] = item.enabled;
    }
    setValues(nextValues);
    setEnabled(nextEnabled);
  }, []);

  const refreshStatsAndSources = useCallback(() => {
    fetchSources().then(applySourceList).catch(() => undefined);
    fetchStats().then(setStats).catch(() => undefined);
  }, [applySourceList]);

  const clearSyncState = useCallback((source: string) => {
    if (syncTimers.current[source]) {
      window.clearTimeout(syncTimers.current[source]);
      delete syncTimers.current[source];
    }
    setSyncStates((prev) => {
      if (!prev[source]) return prev;
      const next = { ...prev };
      delete next[source];
      return next;
    });
  }, []);

  const pollSync = useCallback(
    (source: string, taskId: string) => {
      fetchSyncStatus(taskId)
        .then((task) => {
          if (task.status === "running") {
            setSyncStates((prev) => ({
              ...prev,
              [source]: { taskId, phase: "running", message: "正在同步…" },
            }));
            syncTimers.current[source] = window.setTimeout(
              () => pollSync(source, taskId),
              1500,
            );
            return;
          }
          const perSource = (task.results ?? {})[source] as
            | { count?: number; recognized?: number; error?: string }
            | undefined;
          const err = perSource?.error ?? task.error ?? "";
          if (task.status === "done" && perSource && !err) {
            const count = perSource?.count ?? 0;
            const recognized = perSource?.recognized ?? 0;
            const alreadyNote =
              count === 0 && recognized > 0
                ? `（识别 ${recognized} 条，均为已有记录）`
                : "";
            setSyncStates((prev) => ({
              ...prev,
              [source]: {
                taskId,
                phase: "done",
                message: `同步完成，新增 ${count} 条${alreadyNote}`,
              },
            }));
            refreshStatsAndSources();
          } else if (task.status === "done") {
            setSyncStates((prev) => ({
              ...prev,
              [source]: {
                taskId,
                phase: "error",
                message: `同步失败：${err || "未返回同步结果，请确认数据源已配置并启用"}`,
              },
            }));
          } else {
            setSyncStates((prev) => ({
              ...prev,
              [source]: {
                taskId,
                phase: "error",
                message: `同步失败：${err || "未知错误"}`,
              },
            }));
          }
          syncTimers.current[source] = window.setTimeout(
            () => clearSyncState(source),
            30000,
          );
        })
        .catch((err) => {
          const detail =
            (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? "";
          setSyncStates((prev) => ({
            ...prev,
            [source]: {
              taskId,
              phase: "error",
              message: `同步状态查询失败：${detail || "请稍后重试"}`,
            },
          }));
          syncTimers.current[source] = window.setTimeout(
            () => clearSyncState(source),
            30000,
          );
        });
    },
    [refreshStatsAndSources, clearSyncState],
  );

  const clearAllSyncState = useCallback(() => {
    if (allSyncTimer.current) {
      window.clearTimeout(allSyncTimer.current);
      allSyncTimer.current = null;
    }
    setAllSyncState(null);
  }, []);

  const pollAllSync = useCallback(
    (taskId: string) => {
      fetchSyncStatus(taskId)
        .then((task) => {
          if (task.status === "running") {
            setAllSyncState({
              taskId,
              phase: "running",
              message: "正在同步所有数据源…",
            });
            allSyncTimer.current = window.setTimeout(
              () => pollAllSync(taskId),
              1500,
            );
            return;
          }
          const results = (task.results ?? {}) as Record<
            string,
            { count?: number; recognized?: number; error?: string }
          >;
          const entries = Object.entries(results);
          if (task.status === "done") {
            const failed = entries
              .filter(([, result]) => result?.error)
              .map(([name]) => name);
            const total = entries.reduce(
              (sum, [, result]) => sum + (result?.count ?? 0),
              0,
            );
            const success = entries.length - failed.length;
            const message =
              entries.length === 0
                ? "同步完成：没有已启用的数据源"
                : failed.length === 0
                  ? `同步完成：${success} 个数据源全部成功，新增 ${total} 条`
                  : `同步完成：成功 ${success} 个，失败 ${failed.length} 个（${failed.join("、")}），新增 ${total} 条`;
            setAllSyncState({ taskId, phase: "done", message });
            refreshStatsAndSources();
          } else {
            setAllSyncState({
              taskId,
              phase: "error",
              message: `同步失败：${task.error || "未知错误"}`,
            });
          }
          allSyncTimer.current = window.setTimeout(clearAllSyncState, 30000);
        })
        .catch((err) => {
          const detail =
            (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? "";
          setAllSyncState({
            taskId,
            phase: "error",
            message: `同步状态查询失败：${detail || "请稍后重试"}`,
          });
          allSyncTimer.current = window.setTimeout(clearAllSyncState, 30000);
        });
    },
    [refreshStatsAndSources, clearAllSyncState],
  );

  async function handleSyncAll() {
    setNotice("");
    setError("");
    try {
      const task = await startSync();
      setAllSyncState({
        taskId: task.task_id,
        phase: "running",
        message: "正在同步所有数据源…",
      });
      pollAllSync(task.task_id);
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        status === 409
          ? "已有同步任务正在进行，请稍后再试"
          : detail ?? "同步启动失败",
      );
    }
  }

  async function handleModalSave(
    sourceName: string,
    config: Record<string, unknown>,
    sourceEnabled: boolean,
  ) {
    await saveSource(sourceName, { config, enabled: sourceEnabled });
    const refreshed = await fetchSources();
    applySourceList(refreshed);
    const result = await testSource(sourceName);
    setNotice(`${sourceName} 配置已保存`);
    return result;
  }

  async function handleModalSaveAndSync(
    sourceName: string,
    config: Record<string, unknown>,
    sourceEnabled: boolean,
  ) {
    await saveSource(sourceName, { config, enabled: sourceEnabled });
    const refreshed = await fetchSources();
    applySourceList(refreshed);
    const task = await startSync(sourceName);
    clearSyncState(sourceName);
    setSyncStates((prev) => ({
      ...prev,
      [sourceName]: {
        taskId: task.task_id,
        phase: "running",
        message: "正在同步…",
      },
    }));
    pollSync(sourceName, task.task_id);
    setNotice(`${sourceName} 配置已保存，正在同步…`);
  }

  const clearTakeoutState = useCallback(() => {
    if (takeoutTimer.current) {
      window.clearTimeout(takeoutTimer.current);
      takeoutTimer.current = null;
    }
    setTakeoutState(null);
  }, []);

  const pollTakeout = useCallback(
    (taskId: string) => {
      fetchYouTubeTakeoutExportStatus(taskId)
        .then((task) => {
          if (task.status === "running") {
            setTakeoutState({
              taskId,
              phase: "running",
              message: task.message || "等待 Google 打包导出…",
            });
            takeoutTimer.current = window.setTimeout(
              () => pollTakeout(taskId),
              2000,
            );
            return;
          }
          const err = task.error ?? "";
          if (task.status === "done" && !err) {
            setTakeoutState({
              taskId,
              phase: "done",
              message: task.message || `已导入 ${task.imported} 条观看记录`,
            });
            refreshStatsAndSources();
            loadTakeoutFiles();
          } else {
            setTakeoutState({
              taskId,
              phase: "error",
              message: `自动导出失败：${err || "未知错误"}`,
            });
          }
          takeoutTimer.current = window.setTimeout(
            () => clearTakeoutState(),
            30000,
          );
        })
        .catch((err) => {
          const detail =
            (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? "";
          setTakeoutState({
            taskId,
            phase: "error",
            message: `自动导出状态查询失败：${detail || "请稍后重试"}`,
          });
          takeoutTimer.current = window.setTimeout(
            () => clearTakeoutState(),
            30000,
          );
        });
    },
    [clearTakeoutState, refreshStatsAndSources, loadTakeoutFiles],
  );

  useEffect(() => {
    const status = searchParams.get("youtube");
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const clear = () => setSearchParams({}, { replace: true });

    if (status === "ok") {
      setNotice(searchParams.get("message") || "YouTube 已连接");
      fetchSources().then(applySourceList).catch(() => undefined);
      clear();
      startSync("youtube")
        .then((task) => {
          setSyncStates((prev) => ({
            ...prev,
            youtube: {
              taskId: task.task_id,
              phase: "running",
              message: "正在同步…",
            },
          }));
          pollSync("youtube", task.task_id);
        })
        .catch(() => undefined);
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
        applySourceList(refreshed);
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
  }, [searchParams, setSearchParams, applySourceList, pollSync]);

  useEffect(
    () => () => {
      Object.values(syncTimers.current).forEach((id) => window.clearTimeout(id));
      syncTimers.current = {};
      if (takeoutTimer.current) window.clearTimeout(takeoutTimer.current);
      if (allSyncTimer.current) window.clearTimeout(allSyncTimer.current);
    },
    [],
  );

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
      refreshStatsAndSources();
      loadTakeoutFiles();
      window.setTimeout(() => setNotice(""), 8000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Takeout 导入失败",
      );
    }
  }

  async function handleReimportTakeout(batchId: string) {
    setNotice("");
    setError("");
    try {
      const result = await reimportYouTubeTakeout(batchId);
      const analysisNote =
        result.imported > 0
          ? "，画像已重新生成"
          : "（记录已存在，无需重复导入）";
      setNotice(
        `已重新导入 ${result.imported} 条观看记录（识别 ${result.parsed} 条）${analysisNote}`,
      );
      refreshStatsAndSources();
      loadTakeoutFiles();
      window.setTimeout(() => setNotice(""), 8000);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "重新导入失败",
      );
    }
  }

  async function handleDownloadTakeout(batchId: string) {
    setNotice("");
    setError("");
    try {
      const blob = await downloadYouTubeTakeoutHistory(batchId);
      downloadBlob(blob, `watch-history-${batchId}.json`);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "下载失败",
      );
    }
  }

  async function handleTakeoutExport() {
    setNotice("");
    setError("");
    try {
      const task = await startYouTubeTakeoutExport();
      setTakeoutState({
        taskId: task.task_id,
        phase: "running",
        message: "已提交自动导出，正在等待 Google 打包…",
      });
      pollTakeout(task.task_id);
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        status === 409
          ? detail || "已有自动导出任务在进行，请稍后再试"
          : detail ?? "自动导出启动失败",
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

  const filteredSources = useMemo(() => {
    const query = sourceQuery.trim().toLowerCase();
    if (!query) return sources;
    return sources.filter((source) => {
      const meta = SOURCE_META[source.source] ?? { label: source.source };
      return [source.source, meta.label, meta.description ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [sources, sourceQuery]);

  const editingSourceConfig =
    sources.find((source) => source.source === editingSource) ?? null;

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
          <div className="source-section-actions">
            <span className="muted">
              {isAuthenticated
                ? "凭据加密保存在本地数据库，只对你自己可见"
                : "预览模式下仅展示示例配置"}
            </span>
            {isAuthenticated && (
              <button
                type="button"
                className="button primary"
                disabled={allSyncState?.phase === "running"}
                onClick={() => withAuth(() => void handleSyncAll())}
              >
                {allSyncState?.phase === "running" ? "同步中…" : "同步全部"}
              </button>
            )}
          </div>
        </div>

        {allSyncState && (
          <div
            className={`sync-status ${
              allSyncState.phase === "error"
                ? "sync-error"
                : allSyncState.phase === "done"
                  ? "sync-done"
                  : ""
            }`}
          >
            {allSyncState.phase === "running" && (
              <span className="spinner" aria-hidden="true" />
            )}
            <span>{allSyncState.message}</span>
          </div>
        )}

        <input
          type="search"
          className="source-search"
          aria-label="搜索数据源"
          placeholder="搜索数据源…"
          value={sourceQuery}
          onChange={(e) => setSourceQuery(e.target.value)}
        />

        <div className="source-list">
          {filteredSources.map((source) => (
            <SourceCard
              key={source.source}
              source={source}
              values={values[source.source] ?? {}}
              enabled={enabled[source.source] ?? source.enabled}
              syncState={syncStates[source.source]}
              onEdit={() => withAuth(() => setEditingSource(source.source))}
            />
          ))}
          {filteredSources.length === 0 && (
            <p className="empty">没有匹配的数据源。</p>
          )}
        </div>
        {!isAuthenticated && (
          <p className="muted">登录后即可保存并同步真实数据源。</p>
        )}
      </section>

      {editingSourceConfig && (
        <SourceEditModal
          key={editingSourceConfig.source}
          source={editingSourceConfig}
          values={values[editingSourceConfig.source] ?? {}}
          enabled={enabled[editingSourceConfig.source] ?? editingSourceConfig.enabled}
          isAuthenticated={isAuthenticated}
          takeoutFiles={takeoutFiles}
          takeoutFilesLoading={takeoutFilesLoading}
          takeoutState={takeoutState}
          onClose={() => setEditingSource(null)}
          onSave={(config, sourceEnabled) =>
            handleModalSave(editingSourceConfig.source, config, sourceEnabled)
          }
          onSaveAndSync={(config, sourceEnabled) =>
            handleModalSaveAndSync(editingSourceConfig.source, config, sourceEnabled)
          }
          onConnectYouTube={() => withAuth(handleConnectYouTube)}
          onTakeoutFile={handleTakeoutFile}
          onTakeoutExport={() => withAuth(handleTakeoutExport)}
          onReimport={(batchId) =>
            withAuth(() => void handleReimportTakeout(batchId))
          }
          onDownload={(batchId) =>
            withAuth(() => void handleDownloadTakeout(batchId))
          }
        />
      )}

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
