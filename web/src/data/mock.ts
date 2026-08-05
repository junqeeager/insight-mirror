import type {
  EventItem,
  GraphData,
  Profile,
  SourceConfig,
  Stats,
  Topic,
} from "../types";

const DAY = 24 * 60 * 60 * 1000;
const HOUR = 60 * 60 * 1000;

function iso(daysAgo: number, hour: number, minute = 0): string {
  const d = new Date(Date.now() - daysAgo * DAY);
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

export const mockStats: Stats = {
  total: 128,
  by_source: { bilibili: 88, github: 30, rss: 10 },
  by_type: { view: 88, read: 30, create: 10 },
};

export const mockEvents: EventItem[] = [
  {
    id: "ev-1",
    timestamp: iso(0, 22, 15),
    source: "bilibili",
    event_type: "view",
    title: "【示例】Python 异步编程入门",
    url: "https://www.bilibili.com/video/BV1demo1",
    tags: ["Python", "异步"],
    duration: 1840,
    depth: "deep",
  },
  {
    id: "ev-2",
    timestamp: iso(0, 20, 3),
    source: "github",
    event_type: "create",
    title: "【示例】提交 feat: add dashboard",
    url: "https://github.com/example/profile",
    tags: ["Git", "前端"],
    duration: 900,
    depth: "browse",
  },
  {
    id: "ev-3",
    timestamp: iso(1, 12, 40),
    source: "rss",
    event_type: "read",
    title: "【示例】大模型应用架构实践",
    url: "https://example.com/llm-architecture",
    tags: ["大模型", "架构"],
    duration: 720,
    depth: "deep",
  },
  {
    id: "ev-4",
    timestamp: iso(2, 9, 10),
    source: "bilibili",
    event_type: "view",
    title: "【示例】FastAPI 实战教程",
    url: "https://www.bilibili.com/video/BV1demo2",
    tags: ["FastAPI", "Python"],
    duration: 1320,
    depth: "deep",
  },
  {
    id: "ev-5",
    timestamp: iso(3, 23, 30),
    source: "rss",
    event_type: "read",
    title: "【示例】认知科学与学习效率",
    url: "https://example.com/cognitive-science",
    tags: ["认知科学", "学习"],
    duration: 480,
    depth: "browse",
  },
  {
    id: "ev-6",
    timestamp: iso(4, 14, 20),
    source: "github",
    event_type: "view",
    title: "【示例】review: 优化关键词提取模块",
    url: "https://github.com/example/profile/pull/12",
    tags: ["算法", "Python"],
    duration: 600,
    depth: "browse",
  },
  {
    id: "ev-7",
    timestamp: iso(5, 21, 5),
    source: "bilibili",
    event_type: "view",
    title: "【示例】React 状态管理深入浅出",
    url: "https://www.bilibili.com/video/BV1demo3",
    tags: ["React", "前端"],
    duration: 2100,
    depth: "deep",
  },
  {
    id: "ev-8",
    timestamp: iso(6, 8, 45),
    source: "rss",
    event_type: "read",
    title: "【示例】分布式系统设计模式",
    url: "https://example.com/distributed-patterns",
    tags: ["分布式", "架构"],
    duration: 960,
    depth: "browse",
  },
  {
    id: "ev-9",
    timestamp: iso(7, 19, 12),
    source: "bilibili",
    event_type: "view",
    title: "【示例】SQL 优化从入门到放弃",
    url: "https://www.bilibili.com/video/BV1demo4",
    tags: ["SQL", "数据库"],
    duration: 1500,
    depth: "deep",
  },
  {
    id: "ev-10",
    timestamp: iso(8, 11, 33),
    source: "github",
    event_type: "create",
    title: "【示例】docs: 更新 API 文档",
    url: "https://github.com/example/profile/commit/abc",
    tags: ["文档", "API"],
    duration: 300,
    depth: "browse",
  },
];

export const mockTopics: Topic[] = [
  {
    id: "t-python",
    name: "Python",
    category: "general",
    frequency: 18,
    weight: 0.21,
    related_topics: ["FastAPI", "异步"],
  },
  {
    id: "t-fastapi",
    name: "FastAPI",
    category: "general",
    frequency: 12,
    weight: 0.16,
    related_topics: ["Python", "API"],
  },
  {
    id: "t-frontend",
    name: "前端",
    category: "general",
    frequency: 10,
    weight: 0.14,
    related_topics: ["React", "TypeScript"],
  },
  {
    id: "t-llm",
    name: "大模型",
    category: "general",
    frequency: 9,
    weight: 0.12,
    related_topics: ["架构", "机器学习"],
  },
  {
    id: "t-architecture",
    name: "架构",
    category: "general",
    frequency: 8,
    weight: 0.11,
    related_topics: ["分布式", "大模型"],
  },
];

export const mockGraph: GraphData = {
  nodes: [
    { id: "python", label: "Python", freq: 18 },
    { id: "fastapi", label: "FastAPI", freq: 12 },
    { id: "frontend", label: "前端", freq: 10 },
    { id: "llm", label: "大模型", freq: 9 },
    { id: "architecture", label: "架构", freq: 8 },
    { id: "react", label: "React", freq: 7 },
    { id: "database", label: "数据库", freq: 6 },
    { id: "typescript", label: "TypeScript", freq: 5 },
    { id: "api", label: "API", freq: 4 },
  ],
  edges: [
    { source: "python", target: "fastapi", weight: 8 },
    { source: "python", target: "frontend", weight: 5 },
    { source: "fastapi", target: "api", weight: 4 },
    { source: "frontend", target: "react", weight: 6 },
    { source: "frontend", target: "typescript", weight: 4 },
    { source: "llm", target: "architecture", weight: 5 },
    { source: "architecture", target: "database", weight: 3 },
    { source: "react", target: "typescript", weight: 4 },
  ],
};

export const mockProfile: Profile = {
  id: "profile-demo",
  timestamp: new Date(Date.now() - 2 * HOUR).toISOString(),
  period: "weekly",
  top_topics: mockTopics,
  topic_clusters: {
    cluster_0: { keywords: ["Python", "FastAPI", "异步"], count: 18 },
    cluster_1: { keywords: ["React", "前端", "TypeScript"], count: 12 },
    cluster_2: { keywords: ["大模型", "架构", "机器学习"], count: 10 },
  },
  total_events: 128,
  total_duration: 86400,
  active_days: 21,
  source_distribution: { bilibili: 88, github: 30, rss: 10 },
  emerging_topics: ["大模型", "React", "分布式"],
  declining_topics: ["旧版框架", "Flash"],
  insights: [
    "【示例】晚间与周末是主要学习时段，深度学习集中在 Python 与前端方向。",
    "【示例】B 站视频是最主要信息来源，建议补充更多 RSS 阅读以拓宽视野。",
    "【示例】近期对架构与大模型话题关注上升，可尝试输出系统化笔记。",
  ],
  event_ids: mockEvents.map((e) => e.id),
};

export const mockSources: SourceConfig[] = [
  {
    source: "bilibili",
    enabled: true,
    config: { cookie: "***", csrf: "***" },
    has_secrets: { cookie: true, csrf: true },
  },
  {
    source: "browser_history",
    enabled: false,
    config: { browser: "chrome", history_path: "auto" },
    has_secrets: {},
  },
  {
    source: "github",
    enabled: false,
    config: {
      token: "***",
      username: "example",
      include_repos: "insight-mirror, personal-profile",
    },
    has_secrets: { token: true },
  },
  {
    source: "rss",
    enabled: false,
    config: {
      feeds: "https://example.com/rss.xml|科技\nhttps://example.com/blog.xml|编程",
    },
    has_secrets: {},
  },
];

export const mockUsers = [
  {
    id: "u-admin",
    username: "admin",
    role: "admin",
    status: "active",
  },
  {
    id: "u-alice",
    username: "alice",
    role: "user",
    status: "active",
  },
  {
    id: "u-pending",
    username: "bob",
    role: "user",
    status: "pending",
  },
];
