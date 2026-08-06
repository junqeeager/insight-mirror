import {
  useEffect,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type { SourceConfig, YouTubeTakeoutFile } from "../types";
import {
  SOURCE_FIELDS,
  SOURCE_META,
  sourceToValues,
  valuesToConfig,
} from "../lib/sourceConfig";

export interface SyncState {
  taskId: string;
  phase: "running" | "done" | "error";
  message: string;
}

function errorText(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? (err instanceof Error ? err.message : "操作失败，请稍后重试")
  );
}

function StatusLine({
  state,
  prefix = "",
}: {
  state?: SyncState | null;
  prefix?: string;
}) {
  if (!state) return null;
  return (
    <div
      className={`sync-status ${
        state.phase === "error"
          ? "sync-error"
          : state.phase === "done"
            ? "sync-done"
            : ""
      }`}
    >
      {state.phase === "running" && <span className="spinner" aria-hidden />}
      <span>
        {prefix}
        {state.message}
      </span>
    </div>
  );
}

export function SourceCard({
  source,
  values,
  enabled,
  syncState,
  onEdit,
}: {
  source: SourceConfig;
  values: Record<string, string>;
  enabled: boolean;
  syncState?: SyncState | null;
  onEdit: () => void;
}) {
  const meta = SOURCE_META[source.source] ?? {
    label: source.source,
    description: "",
    icon: "📦",
  };
  const configured = (SOURCE_FIELDS[source.source] ?? []).some(
    (field) => Boolean((values[field.key] ?? "").trim()),
  );
  const ready = configured || source.source === "youtube";
  const status = enabled
    ? ready
      ? "已启用"
      : "已启用 · 未配置"
    : ready
      ? "已配置 · 未启用"
      : "未配置";

  return (
    <div className={`source-card glass-card ${enabled ? "enabled" : ""}`}>
      <div className="source-card-main">
        <span className="source-icon" aria-hidden>
          {meta.icon}
        </span>
        <div className="source-card-info">
          <h3>
            {meta.label}
            <span className="muted">{source.source}</span>
          </h3>
          <p className="muted">{meta.description}</p>
          <span className="source-status">{status}</span>
        </div>
      </div>
      <div className="source-card-side">
        <StatusLine state={syncState} />
        <button type="button" className="button primary" onClick={onEdit}>
          配置
        </button>
      </div>
    </div>
  );
}

function SecretInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="secret-input">
      <input
        type={visible ? "text" : "password"}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="icon-button"
        aria-label={visible ? "隐藏凭据" : "显示凭据"}
        onClick={() => setVisible((prev) => !prev)}
      >
        {visible ? "🙈" : "👁"}
      </button>
    </span>
  );
}

function TagInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  function add() {
    const next = draft.trim();
    if (!next) return;
    if (!items.includes(next)) {
      onChange([...items, next].join(", "));
    }
    setDraft("");
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    }
  }

  return (
    <div className="tag-input">
      {items.map((item) => (
        <span className="tag-chip" key={item}>
          {item}
          <button
            type="button"
            aria-label={`移除 ${item}`}
            disabled={disabled}
            onClick={() =>
              onChange(items.filter((entry) => entry !== item).join(", "))
            }
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
      <button type="button" className="button small" disabled={disabled} onClick={add}>
        添加
      </button>
    </div>
  );
}

function FeedListInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const rows = value
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      const [url = "", category = "rss"] = line.split("|");
      return { url: url.trim(), category: category.trim() };
    });

  function updateRow(index: number, next: { url: string; category: string }) {
    const nextRows = rows.map((row, i) => (i === index ? next : row));
    onChange(nextRows.map((row) => `${row.url}|${row.category}`).join("\n"));
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index).map((row) => `${row.url}|${row.category}`).join("\n"));
  }

  return (
    <div className="feed-list">
      {rows.map((row, index) => (
        <div className="feed-row" key={`${index}-${row.url}`}>
          <input
            type="url"
            value={row.url}
            disabled={disabled}
            placeholder={placeholder}
            aria-label={`订阅源 URL ${index + 1}`}
            onChange={(e) =>
              updateRow(index, { ...row, url: e.target.value })
            }
          />
          <input
            value={row.category}
            disabled={disabled}
            placeholder="分类（可选）"
            aria-label={`订阅源分类 ${index + 1}`}
            onChange={(e) =>
              updateRow(index, { ...row, category: e.target.value })
            }
          />
          <button
            type="button"
            className="icon-button"
            disabled={disabled}
            aria-label={`移除订阅源 ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button small"
        disabled={disabled}
        onClick={() =>
          onChange(
            [...rows, { url: "", category: "rss" }]
              .map((row) => `${row.url}|${row.category}`)
              .join("\n"),
          )
        }
      >
        + 添加订阅源
      </button>
    </div>
  );
}

function GuidedFields({
  source,
  values,
  onChange,
  disabled,
}: {
  source: SourceConfig;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  disabled?: boolean;
}) {
  const fields = SOURCE_FIELDS[source.source] ?? [];
  if (fields.length === 0) {
    return (
      <p className="modal-hint">
        该数据源不需要手动填写配置，连接授权后即可同步。
      </p>
    );
  }

  return (
    <div className="source-fields">
      {fields.map((field) => (
        <label className="field" key={field.key}>
          <span>
            {field.label}
            {field.required && <em className="required-mark"> *</em>}
          </span>
          {field.kind === "secret" ? (
            <SecretInput
              value={values[field.key] ?? ""}
              disabled={disabled}
              placeholder={field.placeholder}
              onChange={(value) => onChange(field.key, value)}
            />
          ) : field.kind === "select" ? (
            <select
              disabled={disabled}
              value={values[field.key] ?? ""}
              onChange={(e) => onChange(field.key, e.target.value)}
            >
              {field.options?.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : field.kind === "tags" ? (
            <TagInput
              value={values[field.key] ?? ""}
              disabled={disabled}
              placeholder={field.placeholder}
              onChange={(value) => onChange(field.key, value)}
            />
          ) : field.kind === "feeds" ? (
            <FeedListInput
              value={values[field.key] ?? ""}
              disabled={disabled}
              placeholder={field.placeholder}
              onChange={(value) => onChange(field.key, value)}
            />
          ) : source.source === "browser_history" &&
            field.key === "history_path" ? (
            <div className="path-field">
              <label className="switch">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={
                    !(values[field.key] ?? "").trim() ||
                    values[field.key] === "auto"
                  }
                  onChange={(e) =>
                    onChange(field.key, e.target.checked ? "auto" : "")
                  }
                />
                <span>自动检测</span>
              </label>
              <input
                type="text"
                value={
                  !(values[field.key] ?? "").trim() ||
                  values[field.key] === "auto"
                    ? "auto"
                    : values[field.key] ?? ""
                }
                disabled={disabled}
                placeholder={field.placeholder}
                onChange={(e) => onChange(field.key, e.target.value)}
              />
            </div>
          ) : (
            <input
              type="text"
              value={values[field.key] ?? ""}
              disabled={disabled}
              placeholder={field.placeholder}
              onChange={(e) => onChange(field.key, e.target.value)}
            />
          )}
          {field.help && <small className="field-help">{field.help}</small>}
          {source.source === "bilibili" && field.key === "cookie" && (
            <details className="field-help">
              <summary>如何获取 B 站 Cookie？</summary>
              <ol>
                <li>浏览器登录 bilibili.com</li>
                <li>按 F12 打开开发者工具</li>
                <li>切到 Network 标签并刷新页面</li>
                <li>复制请求头中的完整 Cookie，至少包含 SESSDATA 与 bili_jct</li>
              </ol>
            </details>
          )}
        </label>
      ))}
    </div>
  );
}

function YouTubeSection({
  source,
  isAuthenticated,
  enabled,
  takeoutFiles,
  takeoutFilesLoading,
  takeoutState,
  onConnect,
  onTakeoutFile,
  onTakeoutExport,
  onReimport,
  onDownload,
}: {
  source: SourceConfig;
  isAuthenticated: boolean;
  enabled: boolean;
  takeoutFiles: YouTubeTakeoutFile[];
  takeoutFilesLoading: boolean;
  takeoutState: SyncState | null;
  onConnect: () => void;
  onTakeoutFile: (event: ChangeEvent<HTMLInputElement>) => void;
  onTakeoutExport: () => void;
  onReimport: (batchId: string) => void;
  onDownload: (batchId: string) => void;
}) {
  if (source.source !== "youtube" || !isAuthenticated) return null;
  return (
    <div className="youtube-actions">
      {!enabled && (
        <button type="button" className="button primary" onClick={onConnect}>
          连接 YouTube
        </button>
      )}
      <label className="button file-button">
        导入观看历史（Takeout JSON）
        <input
          type="file"
          accept=".json,application/json"
          hidden
          onChange={onTakeoutFile}
        />
      </label>
      <button
        type="button"
        className="button"
        disabled={takeoutState?.phase === "running"}
        onClick={onTakeoutExport}
      >
        自动获取观看历史
      </button>
      <StatusLine state={takeoutState} />
      <div className="takeout-history">
        <h4>自动获取的观看历史</h4>
        <p className="muted takeout-history-hint">
          自动下载的文件会保存到服务端并出现在这里；浏览器无法直接打开本地文件夹，
          可下载文件或直接重新导入。
        </p>
        {takeoutFilesLoading ? (
          <span className="muted">正在加载…</span>
        ) : takeoutFiles.length === 0 ? (
          <p className="muted">
            还没有自动获取的记录。点击“自动获取观看历史”后，文件会自动保存到这里。
          </p>
        ) : (
          <ul className="plain-list">
            {takeoutFiles.map((file) => (
              <li key={file.batch_id}>
                <div className="takeout-history-info">
                  <strong>{file.file_name}</strong>
                  <span className="muted">
                    {file.created_at} · {file.record_count} 条记录
                    {typeof file.imported === "number" &&
                      ` · 已导入 ${file.imported} 条`}
                  </span>
                  {file.path && (
                    <span className="muted takeout-history-path">
                      {file.path}
                    </span>
                  )}
                </div>
                <div className="takeout-history-actions">
                  <button
                    type="button"
                    className="button"
                    onClick={() => onReimport(file.batch_id)}
                  >
                    重新导入
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() => onDownload(file.batch_id)}
                  >
                    下载
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="muted">
        喜欢/订阅在连接后自动同步；点击“自动获取观看历史”由后台直接向 Google 创建
        Takeout 导出并导入完整观看历史（打包通常需要几分钟）。也可打开{" "}
        <a href="https://takeout.google.com" target="_blank" rel="noreferrer">
          Google Takeout 导出页
        </a>{" "}
        下载 watch-history.json 后手动上传。
      </p>
    </div>
  );
}

export function SourceEditModal({
  source,
  values,
  enabled,
  isAuthenticated,
  takeoutFiles,
  takeoutFilesLoading,
  takeoutState,
  onClose,
  onSave,
  onSaveAndSync,
  onConnectYouTube,
  onTakeoutFile,
  onTakeoutExport,
  onReimport,
  onDownload,
}: {
  source: SourceConfig;
  values: Record<string, string>;
  enabled: boolean;
  isAuthenticated: boolean;
  takeoutFiles: YouTubeTakeoutFile[];
  takeoutFilesLoading: boolean;
  takeoutState: SyncState | null;
  onClose: () => void;
  onSave: (
    config: Record<string, unknown>,
    enabled: boolean,
  ) => Promise<{ ok: boolean; message: string }>;
  onSaveAndSync: (
    config: Record<string, unknown>,
    enabled: boolean,
  ) => Promise<void>;
  onConnectYouTube: () => void;
  onTakeoutFile: (event: ChangeEvent<HTMLInputElement>) => void;
  onTakeoutExport: () => void;
  onReimport: (batchId: string) => void;
  onDownload: (batchId: string) => void;
}) {
  const [draftValues, setDraftValues] = useState<Record<string, string>>(() => ({
    ...values,
  }));
  const [configDraft, setConfigDraft] = useState<Record<string, unknown>>(() =>
    valuesToConfig(source.source, values),
  );
  const [draftEnabled, setDraftEnabled] = useState(enabled);
  const [mode, setMode] = useState<"form" | "json">("form");
  const [jsonText, setJsonText] = useState(() =>
    JSON.stringify(valuesToConfig(source.source, values), null, 2),
  );
  const [jsonError, setJsonError] = useState("");
  const [formError, setFormError] = useState("");
  const [testMessage, setTestMessage] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    setConfigDraft((prev) => ({
      ...prev,
      ...valuesToConfig(source.source, draftValues),
    }));
  }, [draftValues, source.source]);

  function updateValue(key: string, value: string) {
    setDraftValues((prev) => {
      const next = { ...prev, [key]: value };
      if (
        source.source === "bilibili" &&
        key === "cookie" &&
        !(prev.csrf ?? "").trim()
      ) {
        const match = value.match(/(?:^|;\s*)bili_jct=([^;\s]+)/i);
        if (match) next.csrf = match[1];
      }
      return next;
    });
    setTestMessage(null);
  }

  function switchToJson() {
    setJsonText(JSON.stringify(configDraft, null, 2));
    setJsonError("");
    setMode("json");
  }

  function switchToForm() {
    try {
      const parsed = JSON.parse(jsonText) as Record<string, unknown>;
      setConfigDraft(parsed);
      setDraftValues(sourceToValues({ ...source, config: parsed }));
      setJsonError("");
      setMode("form");
    } catch {
      setJsonError("JSON 格式错误，请修正后再切换回表单。");
    }
  }

  function currentConfig(): Record<string, unknown> {
    if (mode === "json") {
      const parsed = JSON.parse(jsonText) as Record<string, unknown>;
      setConfigDraft(parsed);
      return parsed;
    }
    return { ...configDraft, ...valuesToConfig(source.source, draftValues) };
  }

  async function handleSave(syncAfter: boolean) {
    if (!isAuthenticated) return;
    setSaving(true);
    setFormError("");
    try {
      const config = currentConfig();
      if (syncAfter) {
        await onSaveAndSync(config, draftEnabled);
        onClose();
      } else {
        const result = await onSave(config, draftEnabled);
        setTestMessage(result);
      }
    } catch (err) {
      setFormError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  const meta = SOURCE_META[source.source] ?? {
    label: source.source,
    description: "",
    icon: "📦",
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="modal source-modal glass-card"
        role="dialog"
        aria-modal="true"
        aria-label={`配置 ${meta.label}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>
            <span className="source-icon" aria-hidden>
              {meta.icon}
            </span>
            {meta.label}
            <span className="muted">{source.source}</span>
          </h2>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <label className="switch">
          <input
            type="checkbox"
            disabled={!isAuthenticated}
            checked={draftEnabled}
            onChange={(e) => setDraftEnabled(e.target.checked)}
          />
          <span>启用此数据源</span>
        </label>

        <div className="tabs source-editor-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "form"}
            className={mode === "form" ? "tab active" : "tab"}
            onClick={mode === "json" ? switchToForm : undefined}
          >
            表单
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "json"}
            className={mode === "json" ? "tab active" : "tab"}
            onClick={mode === "form" ? switchToJson : undefined}
          >
            高级 JSON
          </button>
        </div>

        {mode === "form" ? (
          <div className="source-editor-form">
            <GuidedFields
              source={source}
              values={draftValues}
              disabled={!isAuthenticated}
              onChange={updateValue}
            />
            <YouTubeSection
              source={source}
              isAuthenticated={isAuthenticated}
              enabled={draftEnabled}
              takeoutFiles={takeoutFiles}
              takeoutFilesLoading={takeoutFilesLoading}
              takeoutState={takeoutState}
              onConnect={onConnectYouTube}
              onTakeoutFile={onTakeoutFile}
              onTakeoutExport={onTakeoutExport}
              onReimport={onReimport}
              onDownload={onDownload}
            />
          </div>
        ) : (
          <div className="json-editor">
            <textarea
              className="json-textarea"
              rows={14}
              spellCheck={false}
              disabled={!isAuthenticated}
              value={jsonText}
              aria-label="高级 JSON 配置"
              onChange={(e) => {
                setJsonText(e.target.value);
                setJsonError("");
                setTestMessage(null);
              }}
            />
            {jsonError && <p className="form-error">{jsonError}</p>}
            <p className="modal-hint">
              敏感字段显示为 ***；未修改时保存会保留原值。
            </p>
          </div>
        )}

        {formError && <p className="form-error">{formError}</p>}
        {testMessage && (
          <p className={testMessage.ok ? "form-success" : "form-error"}>
            {testMessage.ok ? "连接成功" : "连接失败"}
            {testMessage.message &&
              testMessage.message !== "连接成功" &&
              `：${testMessage.message}`}
          </p>
        )}

        <div className="source-modal-actions">
          <button type="button" className="button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="button"
            disabled={saving || !isAuthenticated}
            onClick={() => void handleSave(false)}
          >
            {saving ? "保存中…" : "保存"}
          </button>
          <button
            type="button"
            className="button primary"
            disabled={saving || !isAuthenticated}
            onClick={() => void handleSave(true)}
          >
            保存并同步此源
          </button>
        </div>
      </div>
    </div>
  );
}
