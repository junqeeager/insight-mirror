# 🧠 个人认知画像系统

通过长期行为数据（观看、阅读、搜索、收藏、创作、项目记录），构建一个动态变化的个人认知画像。

## ✨ 功能特性

- 📊 **多维度数据采集** - 支持 B站、浏览器历史、GitHub 等数据源
- 🔌 **插件化架构** - 轻松添加新的数据源
- 📈 **时间趋势分析** - 查看兴趣变化趋势
- 🕸️ **关系网络图** - 发现兴趣之间的关联
- 💡 **智能洞察** - 自动生成个人行为洞察
- 📋 **报告生成** - 周报/月报/年报

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据源

复制 `.env.example` 为 `.env` 并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 B站 Cookie 等信息。

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
│   └── pages/              # 页面
│
└── scripts/                 # 工具脚本
    ├── init_db.py          # 初始化数据库
    ├── sync.py             # 数据同步
    └── generate_report.py  # 生成报告
```

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

MIT
