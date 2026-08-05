import axios from "axios";
import type {
  EventItem,
  GraphData,
  Profile,
  SourceConfig,
  Stats,
  TaskStatus,
  Topic,
  User,
} from "../types";

export const api = axios.create({
  baseURL: "/api/v1",
  timeout: 15000,
});

export const authApi = axios.create({
  baseURL: "/api/v1/auth",
  timeout: 15000,
});

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;
let unauthorizedOccurred = false;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      unauthorizedOccurred = true;
      unauthorizedHandler?.();
    }
    return Promise.reject(error);
  },
);

export function resetUnauthorizedFlag() {
  unauthorizedOccurred = false;
}

export function consumeUnauthorizedFlag(): boolean {
  const occurred = unauthorizedOccurred;
  unauthorizedOccurred = false;
  return occurred;
}

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

export async function fetchStats(): Promise<Stats> {
  const { data } = await api.get<Stats>("/stats");
  return data;
}

export async function fetchEvents(params?: {
  source?: string;
  event_type?: string;
  since?: string;
  limit?: number;
}): Promise<EventItem[]> {
  const { data } = await api.get<EventItem[]>("/events", { params });
  return data;
}

export async function fetchTopics(params?: {
  category?: string;
  limit?: number;
}): Promise<Topic[]> {
  const { data } = await api.get<Topic[]>("/topics", { params });
  return data;
}

export async function fetchGraph(windowDays = 90): Promise<GraphData> {
  const { data } = await api.get<GraphData>("/graph", {
    params: { window_days: windowDays },
  });
  return data;
}

export async function fetchLatestProfile(
  period = "weekly",
): Promise<Profile> {
  const { data } = await api.get<Profile>("/profile/latest", {
    params: { period },
  });
  return data;
}

export async function refreshProfile(period = "weekly"): Promise<{
  task_id: string;
  status: string;
  message: string;
}> {
  const { data } = await api.post("/profile/refresh", null, {
    params: { period },
  });
  return data;
}

export async function fetchTaskStatus(taskId: string): Promise<TaskStatus> {
  const { data } = await api.get<TaskStatus>(`/profile/refresh/${taskId}`);
  return data;
}

export async function fetchSources(): Promise<SourceConfig[]> {
  const { data } = await api.get<SourceConfig[]>("/sources");
  return data;
}

export async function saveSource(
  source: string,
  body: { config: Record<string, unknown>; enabled: boolean },
): Promise<SourceConfig> {
  const { data } = await api.put<SourceConfig>(`/sources/${source}`, body);
  return data;
}

export async function testSource(source: string): Promise<{
  ok: boolean;
  message: string;
}> {
  const { data } = await api.post(`/sources/${source}/test`);
  return data;
}

export async function startSync(source?: string): Promise<{
  task_id: string;
  status: string;
}> {
  const { data } = await api.post("/sync", source ? { source } : undefined);
  return data;
}

export async function fetchSyncStatus(taskId: string): Promise<TaskStatus> {
  const { data } = await api.get<TaskStatus>(`/sync/${taskId}`);
  return data;
}

export async function fetchAdminUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>("/admin/users");
  return data;
}

export async function patchAdminUser(
  userId: string,
  body: { status?: string; password?: string },
): Promise<User> {
  const { data } = await api.patch<User>(`/admin/users/${userId}`, body);
  return data;
}

export async function login(username: string, password: string) {
  const { data } = await authApi.post("/login", { username, password });
  return data;
}

export async function register(username: string, password: string) {
  const { data } = await authApi.post("/register", { username, password });
  return data;
}

export async function logout(token: string) {
  await authApi.post(
    "/logout",
    {},
    { headers: { Authorization: `Bearer ${token}` } },
  );
}
