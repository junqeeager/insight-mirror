import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  const { isAuthenticated } = useAuth();
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      <div className="page-actions">
        {!isAuthenticated && <span className="preview-badge">预览 · 示例数据</span>}
        {actions}
      </div>
    </div>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="card metric-card">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${accent ? `accent-${accent}` : ""}`}>
        {value}
      </span>
      {hint && <span className="metric-hint">{hint}</span>}
    </div>
  );
}

export function SourcePill({ source, count }: { source: string; count?: number }) {
  const names: Record<string, string> = {
    bilibili: "B站",
    github: "GitHub",
    rss: "RSS",
    browser_history: "浏览器",
    youtube: "YouTube",
  };
  return (
    <span className="source-pill">
      <span className="source-dot" />
      {names[source] ?? source}
      {typeof count === "number" && <b>{count}</b>}
    </span>
  );
}

export function Loading({ label = "加载中…" }: { label?: string }) {
  return <div className="state-box">{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="state-box error">{message}</div>;
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-box">{message}</div>;
}

export function useRequireAuth() {
  const { requireAuth } = useAuth();
  return requireAuth;
}
