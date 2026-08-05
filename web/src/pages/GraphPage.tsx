import { useMemo, useState } from "react";
import { fetchEvents, fetchGraph } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { NetworkGraph, PieChart, RadarChart } from "../components/charts";
import {
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
} from "../components/ui";
import { mockEvents, mockGraph } from "../data/mock";
import { usePreviewData } from "../hooks/usePreviewData";
import type { EventItem, GraphData } from "../types";

const PERIOD_WINDOWS = [
  { label: "最近 7 天", days: 7 },
  { label: "最近 30 天", days: 30 },
  { label: "最近 90 天", days: 90 },
];

export function GraphPage() {
  const { isAuthenticated, requireAuth } = useAuth();
  const [period, setPeriod] = useState("最近 90 天");
  const [minFreq, setMinFreq] = useState(3);
  const [minCo, setMinCo] = useState(2);
  const windowDays = useMemo(
    () => PERIOD_WINDOWS.find((p) => p.label === period)?.days ?? 90,
    [period],
  );

  const { data: graph, loading, error } = usePreviewData<GraphData>(
    () => fetchGraph(windowDays),
    mockGraph,
    [windowDays],
  );

  const { data: events } = usePreviewData<EventItem[]>(
    () =>
      fetchEvents({
        since: new Date(Date.now() - windowDays * 24 * 60 * 60 * 1000).toISOString(),
        limit: 5000,
      }),
    mockEvents,
    [windowDays],
  );

  const sourceDistribution = useMemo(() => {
    const result: Record<string, number> = {};
    const base = isAuthenticated ? events : mockEvents;
    for (const event of base) {
      result[event.source] = (result[event.source] ?? 0) + 1;
    }
    return result;
  }, [events, isAuthenticated]);

  const filteredGraph = useMemo(() => {
    const kept = new Set(
      graph.nodes.filter((node) => node.freq >= minFreq).map((node) => node.id),
    );
    return {
      nodes: graph.nodes.filter((node) => kept.has(node.id)),
      edges: graph.edges.filter(
        (edge) =>
          kept.has(edge.source) &&
          kept.has(edge.target) &&
          edge.weight >= minCo,
      ),
    };
  }, [graph, minFreq, minCo]);

  const tagCounts = useMemo(() => {
    const result: Record<string, number> = {};
    const base = isAuthenticated ? events : mockEvents;
    for (const event of base) {
      for (const tag of event.tags ?? []) {
        result[tag] = (result[tag] ?? 0) + 1;
      }
    }
    return Object.entries(result)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 30);
  }, [events, isAuthenticated]);

  return (
    <div>
      <PageHeader
        title="关系视图"
        subtitle="查看兴趣关键词之间的关联与平台分布"
        actions={
          !isAuthenticated && (
            <button
              type="button"
              className="button primary"
              onClick={() => requireAuth()}
            >
              登录查看真实关系图
            </button>
          )
        }
      />

      <div className="filter-bar">
        <label className="filter">
          <span>时间范围</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIOD_WINDOWS.map((p) => (
              <option key={p.label} value={p.label}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span>最小出现次数</span>
          <input
            type="range"
            min={1}
            max={20}
            value={minFreq}
            onChange={(e) => setMinFreq(Number(e.target.value))}
          />
          <b>{minFreq}</b>
        </label>
        <label className="filter">
          <span>最小共现次数</span>
          <input
            type="range"
            min={1}
            max={10}
            value={minCo}
            onChange={(e) => setMinCo(Number(e.target.value))}
          />
          <b>{minCo}</b>
        </label>
      </div>

      {error && <ErrorState message={error} />}
      {loading && <Loading />}

      <section className="card">
        <h2>兴趣关联网络</h2>
        {filteredGraph.nodes.length > 0 ? (
          <NetworkGraph graph={filteredGraph} />
        ) : (
          <EmptyState message="数据不足以生成关联网络，请增加数据量或调整筛选条件。" />
        )}
      </section>

      <div className="chart-grid two">
        <section className="card">
          <h2>平台分布雷达图</h2>
          <RadarChart data={sourceDistribution} />
        </section>
        <section className="card">
          <h2>标签云</h2>
          {tagCounts.length ? (
            <div className="tag-cloud">
              {tagCounts.map(([tag, count]) => (
                <span
                  key={tag}
                  className="tag-chip"
                  style={{ fontSize: `${11 + Math.min(14, count)}px` }}
                >
                  {tag} <b>{count}</b>
                </span>
              ))}
            </div>
          ) : (
            <EmptyState message="暂无标签数据" />
          )}
        </section>
      </div>

      <section className="card">
        <h2>来源占比</h2>
        <PieChart data={sourceDistribution} title="来源占比" />
      </section>
    </div>
  );
}
