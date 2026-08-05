export interface User {
  id: string;
  username: string;
  role: string;
  status: string;
  created_at?: string | null;
  last_login_at?: string | null;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface EventItem {
  id: string;
  timestamp: string;
  source: string;
  event_type: string;
  title: string;
  url?: string | null;
  description?: string | null;
  tags: string[];
  duration?: number | null;
  progress?: number | null;
  depth?: string;
  metadata?: Record<string, unknown>;
  processed?: boolean;
}

export interface Topic {
  id: string;
  name: string;
  category: string;
  frequency: number;
  weight: number;
  first_seen?: string | null;
  last_seen?: string | null;
  related_topics: string[];
}

export interface Stats {
  total: number;
  by_source: Record<string, number>;
  by_type: Record<string, number>;
}

export interface GraphNode {
  id: string;
  label: string;
  freq: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Profile {
  id: string;
  timestamp: string;
  period: string;
  top_topics: Topic[];
  topic_clusters: Record<string, { keywords: string[]; count: number }>;
  total_events: number;
  total_duration: number;
  active_days: number;
  source_distribution: Record<string, number>;
  emerging_topics: string[];
  declining_topics: string[];
  insights: string[];
  event_ids: string[];
}

export interface SourceConfig {
  source: string;
  enabled: boolean;
  config: Record<string, unknown>;
  has_secrets: Record<string, boolean>;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  profile_id?: string | null;
  error?: string | null;
  results?: Record<string, unknown>;
}

export interface YouTubeAuthUrl {
  url: string;
}

export interface YouTubeTokenResult {
  ok: boolean;
  message: string;
}

export interface YouTubeTakeoutResult {
  received: number;
  parsed: number;
  imported: number;
}
