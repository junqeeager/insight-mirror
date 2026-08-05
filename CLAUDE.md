# CLAUDE.md — Claude Code 项目交接文档

> 本文件是 Claude Code 在本仓库工作的主入口。`AGENTS.md` 保留给 Codex 等其他工具，两者内容以本文件为准。

## 项目定位与现状

个人认知画像系统：采集 B站、浏览器历史、GitHub、RSS、YouTube 等行为数据，构建兴趣画像，并提供 React SPA + FastAPI 看板与定期 HTML 报告。

当前状态（2026-08-05）：

- `main` 分支干净，最新提交 `7cd9a30`；Git 元数据在 `.git-data/`（见「Git 工作流」）。
- FastAPI 迁移已完成：API 层、多用户账号、SQLite/PostgreSQL 双后端、后台任务、报告与图谱均可用。
- 生产部署正常：systemd 用户服务 `personal-profile-web.service` 在 :8501 同时托管 SPA 与 API，经 Cloudflare Tunnel 对外（公网 `https://t.506ikun.space`）。
- YouTube 数据源（本交接的新功能）：OAuth2 自动同步喜欢/订阅 + Takeout 观看历史导入，插件、API、前端入口与离线测试已落地；首次使用前需配置 `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` 并在 Google 控制台登记回调地址。

## 目录地图

- `core/`：数据模型、SQLAlchemy Core 双后端、插件管理器、同步服务、账号安全。
- `plugins/<source>/plugin.py`：数据源插件（必须实现 `DataSourcePlugin` 接口）。
- `analysis/`：关键词提取、主题聚类、趋势、洞察；画像预计算后落库。
- `report/`：HTML 报告生成器与模板。
- `api/`：FastAPI 服务层；`api/routers/` 按资源拆分，`api/tasks.py` 为后台任务。
- `web/`：React SPA（Vite + TS + React Router）；API 客户端在 `web/src/api/client.ts`，页面在 `web/src/pages/`。
- `scripts/`：`init_db.py`、`sync.py`、`generate_report.py`、`migrate.py`、`migrate_db.py`、`manage_users.py`、`check_secrets.py`。
- `tests/`：纯脚本测试（可 `python tests/test_*.py` 直接运行，也兼容 pytest）。
- `data/`：运行时 SQLite 与报告产物（gitignored）。

## 常用命令

```bash
pip install -r requirements.txt        # Python 依赖
npm --prefix web install               # 前端依赖
python scripts/init_db.py              # 建表
python scripts/migrate.py              # 应用 schema 迁移
python scripts/sync.py --user alice --source youtube   # 按用户同步指定源
python scripts/generate_report.py --period weekly      # 生成周报
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8501  # 生产同源运行
make run-web-dev                       # Vite 开发模式（:5173，代理 :8502）
make test                              # 后端全量测试
make test-api                          # API 测试（需在非沙箱 shell 运行）
make test-web                          # 前端 Vitest
make build-web                         # 前端生产构建
```

## 架构与数据流

```
plugins/ ──scripts/sync.py──▶ SQLite/PostgreSQL ──▶ analysis/（预计算画像落库）
                                                          │
web/（React SPA）──同源 /api/v1──▶ FastAPI ──▶ report/（HTML 周/月/年报告）
```

- 同步流程：`sync_service.sync_user()` 读取用户加密的数据源配置 → `PluginManager` 加载插件 → `fetch(since)` → `db.insert_events()`（幂等去重）→ 更新 `sync_state`。
- 画像流程：同步完成后由后台任务预计算 `topics` / `event_topics` / `profiles`，API 只读最新快照。
- 前端未登录全部使用 `web/src/data/mock.ts` 示例数据；登录后走真实 API，按 token 隔离用户数据。

## 部署拓扑（不含任何密钥）

- systemd 用户服务（`~/.config/systemd/user/`，由 `deploy/*.service` 复制安装）：
  - `personal-profile-web.service`：uvicorn `api.main:app`，监听 `0.0.0.0:8501`，工作目录为仓库根目录。
  - `personal-profile-tunnel.service`：cloudflared 隧道，把 `t.506ikun.space` 转发到 `127.0.0.1:8501`。
  - `personal-profile-sync.service` + `.timer`：定时 `python scripts/sync.py`（全用户全源）。
  - `personal-profile-report.service` + `.timer`：定时生成周报。
- 开发端口：8501（生产同源）、8502（API 开发）、5173（Vite）。
- 日志：`journalctl --user -u personal-profile-web.service -n 50 --no-pager`。
- 开机自启：`loginctl enable-linger junqeeager` 已启用。
- 重启服务：`systemctl --user restart personal-profile-web.service`；改前端代码后需先 `make build-web`。
- 数据库默认 `data/profile.db`（SQLite WAL）；PostgreSQL 通过 `DATABASE_URL` 或 `database.url` 切换，用 `scripts/migrate_db.py` 拷贝数据。

## Git 工作流

- Git 元数据在 `.git-data/`（`.git` 是只读挂载），所有 Git 命令必须：
  ```bash
  git --git-dir=$PWD/.git-data add .
  git --git-dir=$PWD/.git-data commit -m "feat: ..."
  git --git-dir=$PWD/.git-data push origin main
  ```
- 提交信息使用 Conventional Commits：`feat:` / `fix:` / `refactor:` / `docs:` / `chore:`。
- 仓库公开，push 前由 `deploy/pre-push` 钩子运行 `scripts/check_secrets.py`，禁止提交 `.env`、Cookie、Token、私钥。

## 安全约定

- 密钥只放 `.env`（gitignored）；`config.yaml` 通过 `${VAR}` 引用，绝不写真实值。
- 每个用户的数据源凭据用 `APP_SECRET_KEY` 派生密钥加密后存 `source_configs.config`（敏感键：cookie/csrf/token/secret）；设置页展示时脱敏为 `***`。
- 账号密码 scrypt 加盐哈希，会话只存 token 哈希、30 天有效；未登录不渲染任何个人数据。
- 新增敏感配置字段时，确认 `core/auth.py` 的 `_SENSITIVE_KEYWORDS` 能覆盖，并补充 `tests/test_secret_guard.py` 场景。

## 编码与测试约定

- Python 3.11+、PEP 8、4 空格缩进；注释与文档字符串用中文。
- 插件实现 `name/display_name/version/icon/description/setup/test_connection/fetch`；事件 id 必须稳定（禁止 Python `hash()`，用 `sha256` 派生）。
- 新增功能必须补离线测试：Python 放 `tests/test_*.py`（内存库 + mock HTTP），前端放 `web/src/test/`；禁止真实 Cookie、Token 或线上 API。
- 改动涉及数据库时：先更新 `core/database.py` 的表定义，再新增 `scripts/migrations/NNN_*.py`（SQLite/PostgreSQL 通用、幂等），并补 `tests/test_migrations.py`。

## 交接路线图

1. **YouTube 源收尾**：配置真实 Google OAuth 凭据与回调（`app.public_url` + `/settings`），验证连接、同步、报告链路；可补充端到端冒烟。
2. **插件框架打磨**：沉淀 HTTP 超时/重试/分页工具，统一插件 `get_status()` 元数据；让设置页字段改为插件声明式（当前 `SettingsPage.tsx` 的 `FIELDS` 是硬编码）。
3. **可选 LLM 增强（默认关闭）**：`analysis.llm` 配置已就位；实现 OpenAI 兼容的洞察摘要，无 key/失败时回退本地分析，测试全部 mock。
4. **上线收尾**：README 截图、部署监控、数据量过万后的连接池/异步评估。
