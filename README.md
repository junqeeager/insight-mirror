# 🧠 个人认知画像系统 · Personal Cognitive Profile

> 基于长期行为数据（B站、浏览器历史、GitHub、RSS）构建动态个人认知画像，并提供可视化看板与定期报告。
> A personal cognitive-profile system that turns long-term behavioral data into an evolving interest profile with a Streamlit dashboard.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)

## ✨ 功能特性

- 📊 **多维度数据采集** - 支持 B站、浏览器历史、GitHub 等数据源
- 🔌 **插件化架构** - 轻松添加新的数据源
- 📈 **时间趋势分析** - 查看兴趣变化趋势
- 🕸️ **关系网络图** - 发现兴趣之间的关联
- 💡 **智能洞察** - 自动生成个人行为洞察
- 📋 **报告生成** - 周报/月报/年报

## 📸 Screenshots

截图待补充，目录与命名约定见 [docs/screenshots/README.md](docs/screenshots/README.md)。
正式部署后将补充首页、时间视图、关系视图、报告视图四张截图，避免 README 中出现失效图片链接。

## 🏗️ 架构

```
plugins/（B站 / 浏览器历史 / GitHub / RSS）
        │ scripts/sync.py 采集写入
        ▼
SQLite（data/profile.db）
        ▲                    ▲
        │ 直连回退             │ 查询
frontend/（Streamlit）  ──▶  api/（FastAPI，仅监听本机 :8502）
        │
        ▼
analysis/（关键词提取 / 主题聚类 / 趋势 / 洞察）
        │
        ▼
report/（HTML 周报 / 月报 / 年报）
```

Streamlit 前端优先调用 FastAPI（带 TTL 缓存），API 不可用时自动回退直连 SQLite，保证低流量个人项目的实时响应。

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据源与访问密码

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

- 填入你的 B站 Cookie、GitHub Token 等凭据；
- 设置 `APP_PASSWORD` 作为公开看板的访问密码（不设置时看板会拒绝访问并提示）。

### 3. 初始化数据库

```bash
python scripts/init_db.py
```

### 4. 同步数据

```bash
# 同步所有已启用的数据源
python scripts/sync.py

# 或同步单个数据源
python scripts/sync.py --source bilibili
```

### 5. 启动前端

```bash
streamlit run frontend/app.py
```

访问 http://localhost:8501 即可使用。

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
├── frontend/                # Streamlit 前端
│   ├── app.py              # 主入口
│   ├── auth.py             # 公开看板密码门
│   ├── theme.py            # Astryx 主题注入（纯 CSS）
│   ├── layout.py           # 共享侧边栏与页头
│   ├── assets/             # Astryx neutral 预编译 CSS（固定版本）
│   └── pages/              # 页面
│
├── scripts/                 # 工具脚本
│   ├── init_db.py          # 初始化数据库
│   ├── sync.py             # 数据同步
│   ├── generate_report.py  # 生成报告
│   └── migrate_db.py       # SQLite ↔ PostgreSQL 数据迁移
│
├── api/                     # FastAPI 服务层
│   ├── main.py             # 应用入口（含 jieba 预热与全局异常处理）
│   └── routers/            # /events /topics /profile /stats /graph
│
└── docs/                    # 设计文档（含 FastAPI 迁移规划）
```

## 🌐 API 服务

```bash
make run-api   # 等价于 uvicorn api.main:app --host 0.0.0.0 --port 8502
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
| `GET` | `/api/v1/graph` | 兴趣共现图（后端预计算，5 分钟缓存） |

Streamlit 通过 `frontend/data_access.py` 优先调用 API，API 不可用时自动回退直连 SQLite；数据结果带 TTL 缓存（30s/60s/300s）。

## 🧪 测试与开发命令

```bash
make test       # 数据库双后端 + 分析 + 插件 + 前端主题/密码门测试
make test-api   # API 测试（需在非沙箱环境运行）
make init-db    # 初始化数据库
make sync       # 同步所有数据源
make run-web    # 启动 Streamlit
```

## 🔒 隐私与安全

- 所有 Cookie / Token 仅保存在本地 `.env`（已被 `.gitignore` 排除），`config.yaml` 只通过 `${VAR}` 引用，仓库中不包含任何真实凭据。
- 公开 Streamlit 看板带简单密码门（`frontend/auth.py`）：密码来自 `.env` 的 `APP_PASSWORD`，使用 `secrets.compare_digest` 校验；未配置密码时页面会阻塞并提示，未登录前不会渲染任何个人数据。
- 设置页展示配置时自动脱敏 Cookie / Token / Secret。
- FastAPI 服务默认仅监听本机（:8502），Cloudflare 隧道只转发 Streamlit 端口（:8501），不会把 API 直接暴露到公网。

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

## 📝 获取 B站 Cookie

1. 浏览器登录 bilibili.com
2. F12 打开开发者工具
3. 切到 Network 标签
4. 刷新页面，找到 Request Headers 中的 Cookie
5. 复制 `SESSDATA=xxx` 和 `bili_jct=xxx`

## 📄 License

[MIT](LICENSE) © 2026 [junqeeager](https://github.com/junqeeager)
