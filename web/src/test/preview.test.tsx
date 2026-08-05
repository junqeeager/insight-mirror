import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import * as client from "../api/client";
import {
  mockEvents,
  mockGraph,
  mockProfile,
  mockSources,
  mockStats,
  mockUsers,
} from "../data/mock";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    fetchStats: vi.fn(),
    fetchEvents: vi.fn(),
    fetchGraph: vi.fn(),
    fetchLatestProfile: vi.fn(),
    fetchSources: vi.fn(),
    fetchAdminUsers: vi.fn(),
    startSync: vi.fn(),
    saveSource: vi.fn(),
    testSource: vi.fn(),
    refreshProfile: vi.fn(),
    fetchTaskStatus: vi.fn(),
    patchAdminUser: vi.fn(),
  };
});

function renderRoute(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
}

function seedAuth(user: {
  id: string;
  username: string;
  role: string;
  status: string;
}) {
  localStorage.setItem(
    "personal_profile_auth",
    JSON.stringify({ token: "token-x", user }),
  );
}

async function loginViaModal(
  username = "alice",
  password = "alice-pass-123",
) {
  fireEvent.click(screen.getAllByRole("button", { name: "登录 / 注册" })[0]);
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(screen.getByLabelText("用户名"), {
    target: { value: username },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByTestId("auth-submit"));
  await waitFor(() => expect(client.login).toHaveBeenCalledWith(username, password));
  return dialog;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(client.fetchStats).mockResolvedValue(mockStats);
  vi.mocked(client.fetchEvents).mockResolvedValue(mockEvents);
  vi.mocked(client.fetchGraph).mockResolvedValue(mockGraph);
  vi.mocked(client.fetchLatestProfile).mockResolvedValue(mockProfile);
  vi.mocked(client.fetchSources).mockResolvedValue(mockSources);
  vi.mocked(client.fetchAdminUsers).mockResolvedValue(mockUsers);
  vi.mocked(client.startSync).mockResolvedValue({
    task_id: "task-abc",
    status: "started",
  });
  vi.mocked(client.login).mockResolvedValue({
    token: "token-x",
    user: { id: "u1", username: "alice", role: "user", status: "active" },
  });
  vi.mocked(client.register).mockResolvedValue({
    id: "u2",
    username: "bob",
    role: "user",
    status: "pending",
  });
  vi.mocked(client.logout).mockResolvedValue(undefined);
});

describe("未登录公开预览", () => {
  it.each([
    ["/", "最近事件"],
    ["/time", "活跃时段热力图"],
    ["/graph", "兴趣关联网络"],
    ["/report", "Top 兴趣领域"],
    ["/settings", "我的数据源"],
  ])("路由 %s 渲染示例数据且不调用真实接口", (path, heading) => {
    renderRoute(path);
    expect(screen.getByText(heading)).toBeInTheDocument();
    expect(screen.getAllByText("预览 · 示例数据").length).toBeGreaterThan(0);
    expect(client.fetchStats).not.toHaveBeenCalled();
    expect(client.fetchEvents).not.toHaveBeenCalled();
    expect(client.fetchGraph).not.toHaveBeenCalled();
    expect(client.fetchLatestProfile).not.toHaveBeenCalled();
    expect(client.fetchSources).not.toHaveBeenCalled();
  });

  it("设置页未登录只读展示示例配置", () => {
    renderRoute("/settings");
    expect(screen.getByDisplayValue("chrome")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("***").length).toBeGreaterThan(0);
    expect(
      screen.getByDisplayValue(/https:\/\/example\.com\/rss\.xml\|科技/),
    ).toBeInTheDocument();
  });
});

describe("登录 / 注册", () => {
  it("右上角打开登录弹窗，登录后进入真实数据态并显示账号", async () => {
    renderRoute("/");
    await loginViaModal();

    expect(await screen.findAllByText("alice")).not.toHaveLength(0);
    expect(screen.queryByText("预览 · 示例数据")).not.toBeInTheDocument();
    expect(client.fetchStats).toHaveBeenCalled();
  });

  it("注册 tab 提交后提示等待管理员审核", async () => {
    renderRoute("/");
    fireEvent.click(screen.getAllByRole("button", { name: "登录 / 注册" })[0]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));

    fireEvent.change(screen.getByLabelText("用户名"), {
      target: { value: "bob" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "bob-pass-123" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "bob-pass-123" },
    });
    fireEvent.click(screen.getByTestId("auth-submit"));

    await waitFor(() =>
      expect(client.register).toHaveBeenCalledWith("bob", "bob-pass-123"),
    );
    expect(
      await screen.findByText("注册成功，请等待管理员审核后登录"),
    ).toBeInTheDocument();
    expect(dialog).toBeInTheDocument();
  });

  it("退出登录后回到预览态", async () => {
    seedAuth({ id: "u1", username: "alice", role: "user", status: "active" });
    renderRoute("/");
    expect((await screen.findAllByText("alice")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(client.logout).toHaveBeenCalledWith("token-x"));
    expect(await screen.findAllByText("登录 / 注册")).not.toHaveLength(0);
  });
});

describe("requireAuth 登录后继续原操作", () => {
  it("未登录点击同步数据弹出登录，登录成功后自动执行同步", async () => {
    renderRoute("/");
    fireEvent.click(screen.getByRole("button", { name: "同步数据" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(client.startSync).not.toHaveBeenCalled();

    await loginViaModal();

    await waitFor(() => expect(client.startSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/同步任务已启动/)).toBeInTheDocument();
  });
});

describe("管理员区域", () => {
  it("普通用户看不到用户管理", async () => {
    seedAuth({ id: "u1", username: "alice", role: "user", status: "active" });
    renderRoute("/settings");
    await screen.findByText("我的数据源");
    expect(screen.queryByText("用户管理（管理员）")).not.toBeInTheDocument();
  });

  it("管理员可见用户列表", async () => {
    seedAuth({ id: "u0", username: "admin", role: "admin", status: "active" });
    renderRoute("/settings");
    expect(
      await screen.findByText("用户管理（管理员）"),
    ).toBeInTheDocument();
    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(client.fetchAdminUsers).toHaveBeenCalled();
  });
});
