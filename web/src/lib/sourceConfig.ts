import type { SourceConfig } from "../types";

export type SourceFieldKind =
  | "text"
  | "secret"
  | "select"
  | "textarea"
  | "tags"
  | "feeds";

export interface SourceField {
  key: string;
  label: string;
  kind?: SourceFieldKind;
  options?: string[];
  placeholder?: string;
  help?: string;
  required?: boolean;
}

export const SOURCE_META: Record<
  string,
  { label: string; description: string; icon: string }
> = {
  bilibili: {
    label: "哔哩哔哩",
    description: "同步 B 站视频观看历史",
    icon: "📺",
  },
  browser_history: {
    label: "浏览器历史",
    description: "同步 Chrome / Firefox 本地浏览记录",
    icon: "🌐",
  },
  github: {
    label: "GitHub",
    description: "同步代码提交与仓库活动",
    icon: "💻",
  },
  rss: {
    label: "RSS 订阅",
    description: "同步你订阅的 RSS 文章",
    icon: "📡",
  },
  youtube: {
    label: "YouTube",
    description: "同步喜欢、订阅与观看历史",
    icon: "▶️",
  },
};

export const SOURCE_FIELDS: Record<string, SourceField[]> = {
  bilibili: [
    {
      key: "cookie",
      label: "B 站 Cookie",
      kind: "secret",
      required: true,
      placeholder: "SESSDATA=...; bili_jct=...",
      help: "登录 bilibili.com 后，按 F12 打开开发者工具，在 Network 请求头中复制完整 Cookie。",
    },
    {
      key: "csrf",
      label: "B 站 CSRF（bili_jct）",
      kind: "secret",
      required: true,
      placeholder: "bili_jct=xxx",
      help: "通常就是 Cookie 中的 bili_jct 值；填写 Cookie 后会自动回填。",
    },
  ],
  github: [
    {
      key: "token",
      label: "GitHub Token",
      kind: "secret",
      required: true,
      placeholder: "ghp_xxx",
      help: "在 GitHub Settings → Developer settings → Personal access tokens 创建，至少勾选读取公开活动的权限。",
    },
    {
      key: "username",
      label: "GitHub 用户名",
      required: true,
      placeholder: "your-username",
    },
    {
      key: "include_repos",
      label: "只同步这些仓库（可选）",
      kind: "tags",
      placeholder: "输入仓库名后回车",
      help: "留空表示同步该用户所有仓库的公开活动。",
    },
  ],
  rss: [
    {
      key: "feeds",
      label: "RSS 订阅源",
      kind: "feeds",
      required: true,
      placeholder: "https://example.com/feed.xml",
      help: "每行一个订阅源；分类会作为文章标签，可留空。",
    },
  ],
  browser_history: [
    {
      key: "browser",
      label: "浏览器",
      kind: "select",
      options: ["chrome", "firefox", "edge"],
    },
    {
      key: "history_path",
      label: "历史记录路径",
      kind: "text",
      placeholder: "auto",
      help: "保持 auto 会自动检测；自动检测不到时填入浏览器历史数据库的绝对路径。",
    },
  ],
  youtube: [],
};

export function sourceToValues(
  source: SourceConfig,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of SOURCE_FIELDS[source.source] ?? []) {
    const raw = source.config?.[field.key];
    if (
      (field.kind === "textarea" || field.kind === "feeds") &&
      Array.isArray(raw)
    ) {
      values[field.key] = raw
        .map((item) =>
          typeof item === "string"
            ? item
            : `${String((item as { url?: string }).url ?? "")}|${String(
                (item as { category?: string }).category ?? "",
              )}`,
        )
        .join("\n");
    } else if (Array.isArray(raw)) {
      values[field.key] = raw.join(", ");
    } else {
      values[field.key] = raw === undefined || raw === null ? "" : String(raw);
    }
  }
  return values;
}

export function valuesToConfig(
  source: string,
  values: Record<string, string>,
): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  for (const field of SOURCE_FIELDS[source] ?? []) {
    const value = values[field.key] ?? "";
    if (field.kind === "textarea" || field.kind === "feeds") {
      config[field.key] = value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [url = "", category = "rss"] = line.split("|");
          return { url: url.trim(), category: category.trim() };
        });
    } else if (field.kind === "tags") {
      config[field.key] = value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    } else {
      config[field.key] = value;
    }
  }
  return config;
}

export function isSourceConfigured(
  source: SourceConfig,
  values: Record<string, string>,
): boolean {
  if (source.source === "youtube") {
    return Boolean(source.enabled);
  }
  if (Object.values(source.has_secrets ?? {}).some(Boolean)) {
    return true;
  }
  return (SOURCE_FIELDS[source.source] ?? []).some((field) =>
    Boolean((values[field.key] ?? "").trim()),
  );
}
