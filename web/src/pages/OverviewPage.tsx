import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEvents, fetchStats, startSync } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ErrorState, Loading, MetricCard, PageHeader, SourcePill } from "../components/ui";
import { mockEvents, mockStats } from "../data/mock";
import { usePreviewData } from "../hooks/usePreviewData";
import { formatDateTime } from "../lib/format";
import type { EventItem, Stats } from "../types";

export function OverviewPage() {
  const { isAuthenticated, requireAuth } = useAuth();
  const navigate = useNavigate();
  const [syncMessage, setSyncMessage] = useState("");
  const [syncing, setSyncing] = useState(false);

  const { data: stats, loading, error, refresh } = usePreviewData<Stats>(
    fetchStats,
    mockStats,
    [],
  );

  const events = usePreviewData<EventItem[]>(
    () => fetchEvents({ limit: 20 }),
    mockEvents,
    [],
  ).data;

  const metrics = useMemo(
    () => [
      { label: "总事件数", value: stats.total, accent: "blue" },
      { label: "观看记录", value: stats.by_type?.view ?? 0, accent: "green" },
      { label: "阅读记录", value: stats.by_type?.read ?? 0, accent: "orange" },
      { label: "创作记录", value: stats.by_type?.create ?? 0, accent: "purple" },
    ],
    [stats],
  );

  async function handleSync() {
    setSyncing(true);
    setSyncMessage("");
    try {
      const task = await startSync();
      setSyncMessage(`同步任务已启动：${task.task_id.slice(0, 8)}…`);
      window.setTimeout(() => setSyncMessage(""), 8000);
    } catch (err) {
      setSyncMessage(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "同步失败",
      );
    } finally {
      setSyncing(false);
    }
  }

  function syncWithAuth() {
    requireAuth(() => void handleSync());
  }

  return (
    <div>
      <PageHeader
        title="个人认知画像"
        subtitle={
          isAuthenticated
            ? "基于行为数据生成的兴趣画像与数据看板"
            : "公开预览 · 登录后查看你自己的画像"
        }
        actions={
          !isAuthenticated ? (
            <button
              type="button"
              className="button primary"
              onClick={() => requireAuth()}
            >
              查看我的真实画像
            </button>
          ) : (
            <button type="button" className="button" onClick={refresh}>
              刷新数据
            </button>
          )
        }
      />

      {error && <ErrorState message={error} />}
      {loading && <Loading />}

      <div className="metric-grid">
        {metrics.map((m) => (
          <MetricCard key={m.label} label={m.label} value={m.value} accent={m.accent} />
        ))}
      </div>

      <section className="card">
        <div className="section-heading">
          <h2>最近事件</h2>
          <span className="muted">
            {isAuthenticated ? "你的真实数据" : "示例数据"}
          </span>
        </div>
        <div className="event-table">
          {events.length === 0 ? (
            <p className="empty">暂无数据，请先在设置页配置并同步数据源。</p>
          ) : (
            events.slice(0, 8).map((event) => (
              <div className="event-row" key={event.id}>
                <SourcePill source={event.source} />
                <div className="event-main">
                  <strong>{event.title}</strong>
                  <span className="muted">
                    {formatDateTime(event.timestamp)} · {event.event_type}
                  </span>
                </div>
                {event.url && (
                  <a
                    className="button ghost small"
                    href={event.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card quick-actions">
        <h2>快捷操作</h2>
        <div className="action-row">
          <button
            type="button"
            className="button"
            disabled={syncing}
            onClick={syncWithAuth}
          >
            {syncing ? "同步中…" : "同步数据"}
          </button>
          <button
            type="button"
            className="button"
            onClick={() => requireAuth(() => navigate("/report"))}
          >
            生成报告
          </button>
          <button
            type="button"
            className="button"
            onClick={() => requireAuth(() => navigate("/settings"))}
          >
            配置数据源
          </button>
        </div>
        {syncMessage && <p className="form-success">{syncMessage}</p>}
        {!isAuthenticated && (
          <p className="muted">
            以上操作需要登录后使用真实数据；当前预览中的示例数据仅供展示。
          </p>
        )}
      </section>
    </div>
  );
}
