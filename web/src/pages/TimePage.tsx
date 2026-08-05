import { useMemo, useState } from "react";
import { fetchEvents } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import {
  BarChart,
  Heatmap,
  PieChart,
  Timeline,
} from "../components/charts";
import {
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
} from "../components/ui";
import { mockEvents } from "../data/mock";
import { usePreviewData } from "../hooks/usePreviewData";
import type { EventItem } from "../types";

const PERIODS = [
  { label: "最近 7 天", days: 7 },
  { label: "最近 30 天", days: 30 },
  { label: "最近 90 天", days: 90 },
  { label: "全部", days: null },
];

export function TimePage() {
  const { isAuthenticated, requireAuth } = useAuth();
  const [period, setPeriod] = useState("最近 7 天");
  const [source, setSource] = useState("全部");
  const [eventType, setEventType] = useState("全部");

  const since = useMemo(() => {
    const days = PERIODS.find((p) => p.label === period)?.days;
    if (!days) return undefined;
    return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
  }, [period]);

  const { data, loading, error } = usePreviewData<EventItem[]>(
    () =>
      fetchEvents({
        source: source === "全部" ? undefined : source,
        event_type: eventType === "全部" ? undefined : eventType,
        since,
        limit: 5000,
      }),
    mockEvents,
    [source, eventType, since],
  );

  const visibleEvents = useMemo(() => {
    const base = isAuthenticated ? data : mockEvents;
    return base.filter((event) => {
      const time = new Date(event.timestamp).getTime();
      if (since && time < new Date(since).getTime()) return false;
      if (source !== "全部" && event.source !== source) return false;
      if (eventType !== "全部" && event.event_type !== eventType) return false;
      return true;
    });
  }, [data, isAuthenticated, source, eventType, since]);

  const sourceDistribution = useMemo(() => {
    const result: Record<string, number> = {};
    for (const event of visibleEvents) {
      result[event.source] = (result[event.source] ?? 0) + 1;
    }
    return result;
  }, [visibleEvents]);

  const typeDistribution = useMemo(() => {
    const result: Record<string, number> = {};
    for (const event of visibleEvents) {
      result[event.event_type] = (result[event.event_type] ?? 0) + 1;
    }
    return result;
  }, [visibleEvents]);

  return (
    <div>
      <PageHeader
        title="时间视图"
        subtitle="按时间范围观察事件分布与活跃时段"
        actions={
          !isAuthenticated && (
            <button
              type="button"
              className="button primary"
              onClick={() => requireAuth()}
            >
              登录查看真实时间线
            </button>
          )
        }
      />

      <div className="filter-bar">
        <label className="filter">
          <span>时间范围</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIODS.map((p) => (
              <option key={p.label} value={p.label}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span>数据来源</span>
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {["全部", "bilibili", "browser_history", "github", "rss"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span>事件类型</span>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
          >
            {["全部", "view", "read", "create", "search"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <ErrorState message={error} />}
      {loading && <Loading />}

      {visibleEvents.length === 0 ? (
        <EmptyState message="暂无数据，请先同步数据源。" />
      ) : (
        <>
          <section className="card">
            <h2>活跃时段热力图</h2>
            <Heatmap events={visibleEvents} />
          </section>
          <section className="card">
            <h2>事件时间线</h2>
            <Timeline events={visibleEvents} />
          </section>
          <div className="chart-grid two">
            <section className="card">
              <h2>数据来源分布</h2>
              <PieChart data={sourceDistribution} title="数据来源分布" />
            </section>
            <section className="card">
              <h2>事件类型统计</h2>
              <BarChart data={typeDistribution} />
            </section>
          </div>
        </>
      )}
    </div>
  );
}
