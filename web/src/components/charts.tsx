import { useMemo } from "react";
import type { EventItem, GraphData } from "../types";
import { formatDateShort, weekdayCN } from "../lib/format";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

export function Heatmap({ events }: { events: EventItem[] }) {
  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const event of events) {
      const d = new Date(event.timestamp);
      if (Number.isNaN(d.getTime())) continue;
      const key = `${d.getDay()}:${d.getHours()}`;
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return map;
  }, [events]);

  const max = Math.max(1, ...counts.values());

  return (
    <div className="heatmap" role="img" aria-label="活跃时段热力图">
      <div className="heatmap-axis">小时</div>
      <div className="heatmap-hours">
        {HOURS.map((h) => (
          <span key={h}>{h}</span>
        ))}
      </div>
      {WEEKDAYS.map((day, dayIndex) => (
        <div className="heatmap-row" key={day}>
          <span className="heatmap-weekday">{day}</span>
          {HOURS.map((hour) => {
            const count = counts.get(`${dayIndex}:${hour}`) ?? 0;
            const alpha = count ? 0.2 + 0.8 * (count / max) : 0.05;
            return (
              <span
                key={hour}
                className="heatmap-cell"
                style={{ backgroundColor: `rgba(59, 130, 246, ${alpha})` }}
                title={`${day} ${hour}:00 - ${count} 条`}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function Timeline({ events }: { events: EventItem[] }) {
  const rows = useMemo(() => {
    const map = new Map<string, number>();
    for (const event of events) {
      const d = new Date(event.timestamp);
      if (Number.isNaN(d.getTime())) continue;
      const key = d.toDateString();
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return [...map.entries()]
      .map(([key, count]) => ({ date: new Date(key), count }))
      .sort((a, b) => a.date.getTime() - b.date.getTime());
  }, [events]);
  const max = Math.max(1, ...rows.map((r) => r.count));

  if (!rows.length) return <p className="empty">暂无时间数据</p>;

  return (
    <div className="timeline">
      {rows.map((row) => (
        <div className="timeline-row" key={row.date.toISOString()}>
          <span className="timeline-label">
            {formatDateShort(row.date)} {weekdayCN(row.date)}
          </span>
          <div className="timeline-track">
            <span
              className="timeline-bar"
              style={{ width: `${Math.max(6, (row.count / max) * 100)}%` }}
            />
          </div>
          <span className="timeline-count">{row.count}</span>
        </div>
      ))}
    </div>
  );
}

function donutGradient(
  entries: { label: string; value: number }[],
  colors: string[],
) {
  const total = entries.reduce((sum, item) => sum + item.value, 0);
  if (!total) return "conic-gradient(#e5e7eb 0 100%)";
  let cursor = 0;
  const stops = entries.map((item, index) => {
    const start = cursor;
    cursor += (item.value / total) * 100;
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

export function PieChart({
  data,
  title,
}: {
  data: Record<string, number>;
  title: string;
}) {
  const entries = Object.entries(data)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
  const colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4", "#ef4444"];
  const total = entries.reduce((sum, item) => sum + item.value, 0);

  if (!total) return <p className="empty">暂无数据</p>;

  return (
    <div className="pie-block">
      <div
        className="donut"
        style={{ background: donutGradient(entries, colors) }}
        role="img"
        aria-label={title}
      >
        <div className="donut-hole">
          <strong>{total}</strong>
          <span>总计</span>
        </div>
      </div>
      <ul className="legend">
        {entries.map((entry, index) => (
          <li key={entry.label}>
            <span
              className="legend-dot"
              style={{ backgroundColor: colors[index % colors.length] }}
            />
            {entry.label}
            <b>{entry.value}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BarChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, value]) => value));
  if (!entries.length) return <p className="empty">暂无数据</p>;

  return (
    <div className="bar-chart">
      {entries.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <span className="bar-label">{label}</span>
          <div className="bar-track">
            <span
              className="bar-fill"
              style={{ width: `${(value / max) * 100}%` }}
            />
          </div>
          <span className="bar-value">{value}</span>
        </div>
      ))}
    </div>
  );
}

export function RadarChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
  if (!entries.length) return <p className="empty">暂无平台数据</p>;

  const max = Math.max(1, ...entries.map((e) => e.value));
  const cx = 160;
  const cy = 140;
  const radius = 100;
  const points = entries.map((entry, index) => {
    const angle = (Math.PI * 2 * index) / entries.length - Math.PI / 2;
    const r = (entry.value / max) * radius;
    return {
      ...entry,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
      labelX: cx + (radius + 22) * Math.cos(angle),
      labelY: cy + (radius + 22) * Math.sin(angle),
    };
  });
  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg className="radar" viewBox="0 0 320 280" role="img" aria-label="平台分布雷达图">
      {[0.25, 0.5, 0.75, 1].map((ratio) => (
        <polygon
          key={ratio}
          points={entries
            .map((_, index) => {
              const angle =
                (Math.PI * 2 * index) / entries.length - Math.PI / 2;
              const r = radius * ratio;
              return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
            })
            .join(" ")}
          fill="none"
          stroke="#d1d5db"
          strokeWidth="1"
        />
      ))}
      {points.map((p, index) => {
        const angle = (Math.PI * 2 * index) / entries.length - Math.PI / 2;
        return (
          <line
            key={`line-${p.label}`}
            x1={cx}
            y1={cy}
            x2={cx + radius * Math.cos(angle)}
            y2={cy + radius * Math.sin(angle)}
            stroke="#d1d5db"
            strokeWidth="1"
          />
        );
      })}
      <polygon
        points={polygon}
        fill="rgba(59, 130, 246, 0.25)"
        stroke="#3b82f6"
        strokeWidth="2"
      />
      {points.map((p) => (
        <g key={p.label}>
          <circle cx={p.x} cy={p.y} r="4" fill="#3b82f6" />
          <text
            x={p.labelX}
            y={p.labelY}
            textAnchor={p.labelX > cx ? "start" : p.labelX < cx ? "end" : "middle"}
            fontSize="11"
          >
            {p.label} ({p.value})
          </text>
        </g>
      ))}
    </svg>
  );
}

export function NetworkGraph({ graph }: { graph: GraphData }) {
  const nodes = useMemo(() => {
    const sorted = [...graph.nodes].sort((a, b) => b.freq - a.freq);
    const cx = 210;
    const cy = 170;
    const radius = 135;
    return sorted.map((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, sorted.length) - Math.PI / 2;
      return {
        ...node,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
        size: Math.max(8, Math.sqrt(node.freq) * 5),
      };
    });
  }, [graph.nodes]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const visibleEdges = graph.edges.filter(
    (edge) => byId.has(edge.source) && byId.has(edge.target),
  );
  const maxWeight = Math.max(1, ...visibleEdges.map((e) => e.weight));

  if (!nodes.length) return <p className="empty">数据不足以生成关联网络</p>;

  return (
    <svg className="network" viewBox="0 0 420 340" role="img" aria-label="兴趣关联网络">
      {visibleEdges.map((edge) => {
        const from = byId.get(edge.source)!;
        const to = byId.get(edge.target)!;
        return (
          <line
            key={`${edge.source}-${edge.target}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke="#94a3b8"
            strokeWidth={0.8 + (edge.weight / maxWeight) * 2.4}
            opacity={0.55}
          />
        );
      })}
      {nodes.map((node) => (
        <g key={node.id} className="network-node">
          <circle
            cx={node.x}
            cy={node.y}
            r={node.size}
            fill="rgba(59, 130, 246, 0.85)"
            stroke="#fff"
            strokeWidth="2"
          >
            <title>{`${node.label} · ${node.freq} 次`}</title>
          </circle>
          <text
            x={node.x}
            y={node.y + 4}
            textAnchor="middle"
            fontSize={node.size > 14 ? 12 : 10}
            fill="#fff"
            fontWeight="600"
          >
            {node.label.length > 6 ? `${node.label.slice(0, 6)}…` : node.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
