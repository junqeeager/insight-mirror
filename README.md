# 🧠 个人认知画像系统 · Personal Cognitive Profile

> 基于长期行为数据（B站、浏览器历史、GitHub、RSS）构建动态个人认知画像，并提供可视化看板与定期报告。
> A personal cognitive-profile system that turns long-term behavioral data into an evolving interest profile with a React SPA + FastAPI dashboard.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-blue.svg)
![React](https://img.shields.io/badge/React-18+-blue.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-blue.svg)
![SQLite/PostgreSQL](https://img.shields.io/badge/SQLite%2FPostgreSQL-database-green.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

## ✅ 环境要求

- Python 3.11+
- Node.js 20.19+（或 22.12+）与 npm 10+
- 可选：Docker / docker compose、systemd 用户服务（长期部署）

项目默认使用 SQLite，无需额外数据库；切换 PostgreSQL 的方式见下文「数据库配置」。

## ✨ 功能特性

- 📊 **多维度数据采集** - 支持 B站、浏览器历史、GitHub、RSS、YouTube（OAuth 喜欢/订阅 + Takeout 观看历史）等数据源
- 🔌 **插件化架构** - 轻松添加新的数据源
- 📈 **时间趋势分析** - 查看兴趣变化趋势
- 🕸️ **关系网络图** - 发现兴趣之间的关联
- 💡 **智能洞察** - 自动生成个人行为洞察
- 📋 **报告生成** - 周报/月报/年报

## 📸 Screenshots

线上预览：<https://t.506ikun.space>（公开预览，登录后可查看自己的真实画像）

截图待补充，目录与命名约定见 [docs/screenshots/README.md](docs/screenshots/README.md)。
正式部署后将补充首页、时间视图、关系视图、报告视图四张截图，避免 README 中出现失效图片链接。

## 🏗️ 架构

```
plugins/（B站 / 浏览器历史 / GitHub / RSS）
        │ scripts/sync.py 采集写入
        ▼
SQLite（data/profile.db）
        ▲
        │ 查询
web/（React SPA） ──▶ api/（FastAPI，生产同源 :8501，开发代理 :8502）
        │
        ▼
analysis/（关键词提取 / 主题聚类 / 趋势 / 洞察）
        │
        ▼
report/（HTML 周报 / 月报 / 年报）
```

React SPA 未登录时可浏览全站示例数据预览；登录后通过 FastAPI 读取当前用户的真实数据。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
npm --prefix web install
npm --prefix web run build   # 构建 React SPA，产出 web/dist
```

### 2. 配置数据源与账号

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

- 填入你的 B站 Cookie、GitHub Token 等凭据；
- 设置 `APP_SECRET_KEY`（随机长字符串，用于加密每个用户的数据源凭据，可用 `openssl rand -hex 32` 生成）。

### 3. 初始化数据库

```bash
python scripts/init_db.py

# 旧版（单用户）数据库升级为多用户结构，并把现有数据归入管理员
python scripts/migrate_multiuser.py --admin-username admin

# 创建管理员（新库或在迁移时跳过密码输入时使用）
python scripts/manage_users.py create-admin --username admin
```

### 4. 同步数据

```bash
# 同步所有 active 用户的数据源
python scripts/sync.py

# 或同步指定用户的单个数据源
python scripts/sync.py --user alice --source bilibili
```

### 5. 启动前端

```bash
# 生产/本机同源运行（同时提供页面与 /api）
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8501

# 开发模式：Vite 热更新（代理 /api 到 :8502）
cd web && npm install && npm run dev
```

访问 http://localhost:8501 即可使用。

## 💻 本地开发

```bash
# 终端 1：启动 API（:8502）
make run-api

# 终端 2：启动 Vite 开发服务器（:5173，/api 自动代理到 :8502）
make run-web-dev
```

开发模式下访问 http://localhost:5173；生产/本机预览使用 `make run-web`（:8501）。

常用前端命令：

```bash
npm --prefix web run dev     # Vite 开发服务器
npm --prefix web run test    # Vitest 测试
npm --prefix web run build   # 生产构建
```

## 🗄️ 数据库配置

默认使用本地 SQLite（`sqlite:///./data/profile.db`）。数据层基于 SQLAlchemy Core，也支持 PostgreSQL：

```yaml
database:
  url: postgresql+psycopg://user:pass@localhost:5432/profile
```

也可用 `DATABASE_URL` 环境变量覆盖 `config.yaml`。切换后端时用迁移脚本幂等拷贝数据：

```bash
python scripts/migrate_db.py \
  --from-url sqlite:///./data/profile.db \
  --to-url postgresql+psycopg://user:pass@localhost:5432/profile
```

## 📁 项目结构

```
personal-profile/
├── config.yaml              # 配置文件
├── requirements.txt         # Python 依赖
├── main.py                  # 主入口
│
├── core/                    # 核心模块
│   ├── models.py           # 数据模型
│   ├── database.py         # 数据库操作
│   └── plugin_loader.py    # 插件管理器
│
├── plugins/                 # 数据源插件
│   ├── bilibili/           # B站插件
│   ├── browser_history/    # 浏览器历史
│   ├── github/             # GitHub
│   └── rss/                # RSS 订阅
│
├── analysis/                # 画像分析
│   ├── keywords.py         # 关键词提取
│   ├── topics.py           # 主题聚类
│   ├── trends.py           # 趋势分析
│   └── insights.py         # 洞察生成
│
├── report/                  # 报告生成
│   ├── generator.py        # 报告生成器
│   └── templates/          # HTML 模板
│
├── web/                     # React SPA（Vite + TypeScript + React Router）
│   ├── src/                 # 页面、Auth、API 客户端、mock 预览数据
│   └── dist/                # 构建产物（生产由 FastAPI 托管）
│
├── scripts/                 # 工具脚本
│   ├── init_db.py          # 初始化数据库
│   ├── sync.py             # 数据同步
│   ├── generate_report.py  # 生成报告
│   ├── migrate.py          # schema 迁移
│   └── migrate_db.py       # SQLite ↔ PostgreSQL 数据迁移
│
├── api/                     # FastAPI 服务层
│   ├── main.py             # 应用入口（建表、安全头、jieba 预热、SPA 托管与全局异常处理）
│   ├── tasks.py            # DB 持久化的后台任务（画像/同步）
│   └── routers/            # /events /topics /profile /stats /graph /auth /sources /sync /admin /report /account
│
└── docs/                    # 设计文档（含 FastAPI 迁移规划）
```

## 🌐 API 服务

```bash
make run-api   # 等价于 uvicorn api.main:app --host 0.0.0.0 --port 8502
make run-web   # 生产同源：uvicorn api.main:app --host 0.0.0.0 --port 8501
```

| 方法 | 端点 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 存活检查 |
| `GET` | `/api/v1/events` | 事件查询（source/event_type/since/limit） |
| `GET` | `/api/v1/topics` | 主题查询 |
| `GET` | `/api/v1/stats` | 数据库统计 |
| `GET` | `/api/v1/profile/latest` | 最近画像快照 |
| `POST` | `/api/v1/profile/refresh` | 后台重建画像 |
| `GET` | `/api/v1/profile/refresh/{task_id}` | 查询画像重建任务状态 |
| `GET` | `/api/v1/report?period&format` | 下载最近画像报告（html/txt/json） |
| `GET` | `/api/v1/graph` | 兴趣共现图（后端预计算，5 分钟缓存） |
| `POST` | `/api/v1/auth/register` | 注册（默认待管理员审核） |
| `POST` | `/api/v1/auth/login` | 登录并签发会话 token |
| `POST` | `/api/v1/auth/logout` | 登出并使 token 失效 |
| `POST` | `/api/v1/account/password` | 修改自己的密码（所有会话失效） |
| `POST` | `/api/v1/account/export` | 服务端导出自己的全部事件（csv/json） |
| `DELETE` | `/api/v1/account` | 注销账号并永久删除数据 |
| `GET/PUT` | `/api/v1/sources` | 查看/保存自己的数据源配置 |
| `POST` | `/api/v1/sources/{source}/test` | 测试自己的数据源连接 |
| `GET` | `/api/v1/sources/youtube/auth-url` | 生成 YouTube OAuth 授权地址（PKCE） |
| `GET` | `/api/v1/sources/youtube/callback` | Google 授权回跳入口（服务端换 token 后跳回设置页） |
| `POST` | `/api/v1/sources/youtube/token` | 用授权码换取并加密保存 refresh_token |
| `POST` | `/api/v1/sources/youtube/takeout` | 上传 Takeout watch-history.json 导入观看历史 |
| `POST` | `/api/v1/sources/youtube/takeout/export` | 后台自动创建 Takeout 导出并导入观看历史 |
| `GET` | `/api/v1/sources/youtube/takeout/export/{task_id}` | 查询自动导出任务状态与实时消息 |
| `POST/GET` | `/api/v1/sync` | 触发/查询自己的数据同步任务 |
| `GET/PATCH` | `/api/v1/admin/users` | 管理员列出/审核/禁用/重置用户 |

除 `/health` 和注册/登录外，所有 API 都需要 `Authorization: Bearer <token>`，并按登录用户隔离数据。

React SPA 通过 `web/src/api/client.ts` 调用同源 `/api/v1/*`；未登录一律使用 `web/src/data/mock.ts` 示例数据，登录后按 token 读取当前用户真实数据。

## 🧪 测试与开发命令

```bash
make test       # 数据库双后端 + 分析 + 图谱 + 插件 + 账号体系 + 迁移测试
make test-api   # API 测试（需在非沙箱环境运行）
make test-web   # React SPA 测试（Vitest + Testing Library）
make build-web  # 构建 React SPA
make init-db    # 初始化数据库
make sync       # 同步所有数据源
make run-web    # 启动 React SPA + API（:8501）
make run-web-dev # Vite 开发服务器（:5173）
```

## 🔒 隐私与安全

- 账号体系：注册后需管理员批准；密码使用 scrypt 加盐哈希，会话 token 只存哈希、30 天有效；未登录不渲染任何个人数据。
- 所有页面未登录均可浏览完整界面（示例数据 + “预览”标识）；查看真实画像、同步数据、生成报告、导出与用户管理等功能需登录后使用，未登录点击会弹出登录引导。
- 每个用户的数据源凭据（B站 Cookie、GitHub Token 等）加密后存数据库，使用 `.env` 的 `APP_SECRET_KEY` 派生密钥，界面展示始终脱敏；`config.yaml` 只通过 `${VAR}` 引用，仓库中不包含任何真实凭据。
- 设置页展示配置时自动脱敏 Cookie / Token / Secret。
- 生产由同一个 uvicorn 监听 :8501 同时提供 SPA 与 `/api`；开发期 FastAPI 默认仅监听本机（:8502），Vite 代理不会把 API 直接暴露到公网。
- 仓库公开且每次 commit 会自动推送到 GitHub：`deploy/pre-push` 钩子（由 `setup.sh` 安装）会在推送前运行 `scripts/check_secrets.py`，检测到 B 站 Cookie、GitHub Token、私钥、带密码的数据库 URL 等真实凭据时阻止推送。

## 🔌 添加新数据源

1. 在 `plugins/` 下创建新目录
2. 实现 `DataSourcePlugin` 接口
3. 在 `config.yaml` 中添加配置

示例：

```python
# plugins/my_source/plugin.py

from core.models import Event, EventType
from core.plugin_loader import DataSourcePlugin

class Plugin(DataSourcePlugin):
    @property
    def name(self) -> str:
        return "my_source"

    @property
    def display_name(self) -> str:
        return "我的数据源"

    def setup(self, config: dict) -> None:
        pass

    def test_connection(self) -> bool:
        return True

    def fetch(self, since: datetime) -> List[Event]:
        return []
```

## 📊 使用 Docker

```bash
# 启动主应用
docker-compose up app

# 启动定时同步
docker-compose --profile scheduler up
```

## 🚀 长期在线部署（systemd 用户服务）

将 Web 与 Cloudflare 隧道注册为开机自启的用户级服务（无需 root）：

```bash
cp deploy/personal-profile-web.service deploy/personal-profile-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now personal-profile-web.service personal-profile-tunnel.service
loginctl enable-linger junqeeager   # 无登录会话时也保持运行
```

常用管理命令：

```bash
systemctl --user status personal-profile-web.service personal-profile-tunnel.service
systemctl --user restart personal-profile-web.service
journalctl --user -u personal-profile-web.service -f
```

## 📝 获取 B站 Cookie

1. 浏览器登录 bilibili.com
2. F12 打开开发者工具
3. 切到 Network 标签
4. 刷新页面，找到 Request Headers 中的 Cookie
5. 复制 `SESSDATA=xxx` 和 `bili_jct=xxx`

## ❓ 常见问题

**启动时提示 `address already in use`**

8501/8502 端口可能已被旧进程占用：

```bash
pgrep -af "uvicorn api.main"
# 确认后停止旧服务，或使用 systemctl --user restart personal-profile-web.service
```

**登录后接口返回 401**

会话 token 30 天有效；过期后页面会自动弹出登录弹窗，重新登录即可。浏览器中的本地登录状态可通过“退出登录”清除。

**修改前端代码后页面没有更新**

开发模式请使用 `make run-web-dev`（Vite 热更新）；生产模式需要重新执行 `npm --prefix web run build`，FastAPI 会直接托管新的 `web/dist`。

## 🤝 贡献

- 保持代码风格：Python 遵循 PEP 8，中文注释；前端 TypeScript 严格模式。
- 提交信息使用 Conventional Commits，如 `feat:`、`fix:`、`docs:`、`refactor:`。
- 新增功能请补充对应测试：Python 测试放在 `tests/`，前端测试放在 `web/src/test/`。
- 提交前会触发 `deploy/pre-push` 密钥扫描，禁止提交真实 Cookie / Token / `.env`。

## 📄 License

本项目使用 [MIT License](LICENSE)。© 2026 [junqeeager](https://github.com/junqeeager)。
