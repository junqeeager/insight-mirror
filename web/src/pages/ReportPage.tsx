import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchLatestProfile,
  fetchReport,
  fetchTaskStatus,
  refreshProfile,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import {
  EmptyState,
  ErrorState,
  Loading,
  MetricCard,
  PageHeader,
  SourcePill,
} from "../components/ui";
import { mockProfile } from "../data/mock";
import {
  downloadBlob,
  formatDateTime,
  formatDuration,
} from "../lib/format";
import type { Profile } from "../types";

const PERIODS = ["weekly", "monthly", "yearly"];
const PERIOD_LABELS: Record<string, string> = {
  weekly: "周报",
  monthly: "月报",
  yearly: "年报",
};

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function ReportPage() {
  const { isAuthenticated, requireAuth } = useAuth();
  const [period, setPeriod] = useState("weekly");
  const [profile, setProfile] = useState<Profile | null>(mockProfile);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0);
  const stopPolling = useRef(false);

  useEffect(() => {
    stopPolling.current = true;
    if (!isAuthenticated) {
      setProfile(mockProfile);
      setLoading(false);
      setError("");
      return;
    }

    let active = true;
    stopPolling.current = false;
    setLoading(true);
    setError("");
    setProfile(null);
    fetchLatestProfile(period)
      .then((data) => {
        if (!active) return;
        setProfile(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setLoading(false);
        if (err?.response?.status === 404) {
          setProfile(null);
        } else if (err?.response?.status !== 401) {
          setError(err?.response?.data?.detail ?? "画像加载失败");
        }
      });
    return () => {
      active = false;
      stopPolling.current = true;
    };
  }, [isAuthenticated, period, tick]);

  const generate = useCallback(async () => {
    setGenerating(true);
    setError("");
    setNotice("画像正在后台生成中…");
    try {
      const task = await refreshProfile(period);
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await delay(1000);
        if (stopPolling.current) return;
        const status = await fetchTaskStatus(task.task_id);
        if (status.status === "done") {
          const latest = await fetchLatestProfile(period);
          setProfile(latest);
          setNotice("画像生成完成");
          setGenerating(false);
          return;
        }
        if (status.status === "error") {
          setError(status.error ?? "画像生成失败");
          setGenerating(false);
          return;
        }
      }
      setNotice("生成仍在后台执行，可稍后刷新页面查看");
      setGenerating(false);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "生成失败，请稍后重试",
      );
      setGenerating(false);
    }
  }, [period]);

  function generateWithAuth() {
    requireAuth(() => void generate());
  }

  async function downloadReport(format: "html" | "txt") {
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      const blob = await fetchReport(period, format);
      const ext = format === "html" ? "html" : "txt";
      downloadBlob(
        blob,
        `profile-${period}-${new Date().toISOString().slice(0, 10)}.${ext}`,
      );
      setNotice(`${format.toUpperCase()} 报告已下载`);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "报告下载失败",
      );
    } finally {
      setGenerating(false);
    }
  }

  function exportWithAuth(format: "html" | "txt") {
    requireAuth(() => void downloadReport(format));
  }

  const hasProfile = Boolean(profile);

  return (
    <div>
      <PageHeader
        title="报告视图"
        subtitle="查看最近画像快照并生成完整报告"
        actions={
          !isAuthenticated ? (
            <button
              type="button"
              className="button primary"
              onClick={() => requireAuth()}
            >
              登录查看真实报告
            </button>
          ) : (
            <button
              type="button"
              className="button"
              onClick={() => setTick((n) => n + 1)}
            >
              刷新
            </button>
          )
        }
      />

      <div className="filter-bar">
        <label className="filter">
          <span>报告周期</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {PERIOD_LABELS[p]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="button primary"
          disabled={generating || loading}
          onClick={generateWithAuth}
        >
          {generating ? "生成中…" : "生成报告"}
        </button>
        {hasProfile && (
          <>
            <button
              type="button"
              className="button"
              disabled={generating}
              onClick={() => exportWithAuth("html")}
            >
              导出 HTML
            </button>
            <button
              type="button"
              className="button"
              disabled={generating}
              onClick={() => exportWithAuth("txt")}
            >
              导出 TXT
            </button>
          </>
        )}
      </div>

      {error && <ErrorState message={error} />}
      {notice && <p className="form-success">{notice}</p>}
      {loading && <Loading label="正在加载画像…" />}

      {!hasProfile && !loading && !error && (
        <EmptyState
          message={`暂无 ${PERIOD_LABELS[period]} 画像快照，请先生成报告。`}
        />
      )}

      {hasProfile && profile && (
        <>
          <div className="metric-grid">
            <MetricCard label="总事件数" value={profile.total_events} accent="blue" />
            <MetricCard
              label="总投入时长"
              value={formatDuration(profile.total_duration)}
              accent="green"
            />
            <MetricCard label="活跃天数" value={profile.active_days} accent="orange" />
            <MetricCard
              label="生成时间"
              value={formatDateTime(profile.timestamp).slice(5)}
              accent="purple"
            />
          </div>

          {profile.top_topics.length > 0 && (
            <section className="card">
              <h2>Top 兴趣领域</h2>
              <ol className="topic-list">
                {profile.top_topics.slice(0, 10).map((topic, index) => (
                  <li key={topic.id}>
                    <span className="topic-rank">{index + 1}</span>
                    <div>
                      <strong>{topic.name}</strong>
                      <span className="muted">
                        权重 {topic.weight.toFixed(3)} · 出现 {topic.frequency} 次
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <div className="chart-grid two">
            <section className="card">
              <h2>来源分布</h2>
              <ul className="plain-list">
                {Object.entries(profile.source_distribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([source, count]) => (
                    <li key={source}>
                      <SourcePill source={source} />
                      <b>{count} 条</b>
                    </li>
                  ))}
              </ul>
            </section>
            <section className="card">
              <h2>兴趣聚类</h2>
              <ul className="plain-list">
                {Object.entries(profile.topic_clusters ?? {}).map(
                  ([cluster, info]) => (
                    <li key={cluster}>
                      <strong>{info.keywords.join(" / ")}</strong>
                      <span className="muted">{info.count} 条</span>
                    </li>
                  ),
                )}
              </ul>
            </section>
          </div>

          <div className="chart-grid two">
            <section className="card trend-section">
              <h2>新兴兴趣</h2>
              {profile.emerging_topics.length ? (
                <div className="tag-cloud">
                  {profile.emerging_topics.map((topic) => (
                    <span key={topic} className="tag-chip up">
                      🟢 {topic}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="muted">暂无</p>
              )}
            </section>
            <section className="card trend-section">
              <h2>衰退兴趣</h2>
              {profile.declining_topics.length ? (
                <div className="tag-cloud">
                  {profile.declining_topics.map((topic) => (
                    <span key={topic} className="tag-chip down">
                      🔴 {topic}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="muted">暂无</p>
              )}
            </section>
          </div>

          {profile.insights.length > 0 && (
            <section className="card">
              <h2>个人洞察</h2>
              <ul className="insight-list">
                {profile.insights.map((insight, index) => (
                  <li key={index}>{insight}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
