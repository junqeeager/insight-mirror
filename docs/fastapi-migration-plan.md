# FastAPI 迁移实施规划（第二阶段）

> 前置条件：第一阶段已验证分析链路可用——`sync → generate_report` 会写入 `topics` / `event_topics` / `profiles` 三张表，报告与 Streamlit、公网隧道均正常。

## 目标

- 新增独立的 `api/` 服务层，Streamlit 与未来外部客户端统一走 HTTP API。
- 画像改为“同步完成后预计算并落库”，API 只读最新快照，不再每次请求现场计算。
- 补 SQLite 索引与批量写入；数据规模足够大时再评估异步 SQLite 或 PostgreSQL。
- API 层建立在已测试的分析链路上，避免在未验证代码上叠加新层。

## 现状调研要点（基于当前代码）

- `core/database.py` 是同步 `sqlite3`，已开启 WAL；连接非线程安全，API 需要每请求新连接或加锁复用。
- 画像持久化已就位：`ProfileGenerator.generate(..., persist=True)` 写入 `topics`/`event_topics`/`profiles`；`Database.get_profiles()` 可读取快照。
- 现有索引：`events(timestamp/source/event_type/processed)`、`topics(category)`。缺少：`event_topics(topic_id)`、`profiles(period)`。
- 已知待修问题（建议在 API 落地前或同期修复）：
  1. `analysis/topics.py` 的 LDA 分支调用不存在的 `LatentDirichletAllocation.fit_predict()`；
  2. 关系视图共现算法取全局 Top5 而非事件内 Top5；
  3. `browser_history` 事件 id 用 `hash(url)`，进程间不稳定导致重复入库；
  4. Streamlit 弃用告警：`use_container_width` → `width`、`st.components.v1.html` → `st.iframe`。

## 目标架构

```
api/
  main.py        # FastAPI app + lifespan（建表、加载配置）
  schemas.py     # Pydantic 模型：EventOut / TopicOut / ProfileOut / StatsOut
  routes/
    events.py    # GET /api/v1/events
    topics.py    # GET /api/v1/topics
    profile.py   # GET /api/v1/profile/latest, POST /api/v1/profile/refresh
  services/
    profile.py   # 读最新快照；可选内存 LRU（TTL 60s）
    sync.py      # 后台重建画像任务
```

### 端点设计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 存活检查 |
| GET | `/api/v1/events?source&event_type&since&limit` | 事件查询（复用现有 `Database.get_events`） |
| GET | `/api/v1/topics?category&limit` | 主题查询 |
| GET | `/api/v1/profile/latest?period=weekly` | 返回最近画像快照 |
| POST | `/api/v1/profile/refresh` | 触发后台重建画像，返回 `task_id`（202） |
| GET | `/api/v1/stats` | 数据库统计 |

### 预计算与缓存

- 调度器（systemd timer 或 `scripts/sync.py --daemon`）在同步后追加执行 `generate_report`，画像落库即为缓存。
- `ProfileService` 可加 TTL 缓存（如 60 秒）避免频繁读库；画像过期时返回 409 + 提示先 refresh。
- 重建任务用 `BackgroundTasks` 或线程池执行，避免请求阻塞；任务状态存内存或 `sync_state`。

### 性能

- 保持 SQLite（当前数据量小）：`insert_events` 改为 `executemany` 单事务批量写入；补上述两个索引。
- 当事件量达到数万条或并发升高时，再评估 `aiosqlite`（最小改动）或 PostgreSQL（需改 `Database` 实现与部署）。

### 前端迁移

- Streamlit 页面用 `httpx` 调 API，配合 `st.cache_data`；迁移顺序：时间视图 → 关系视图 → 报告 → 设置。
- 在 `config.yaml` 增加 `frontend.api_base`（如 `http://localhost:8502`）作为回退开关；API 不可用时给出明确错误提示。

### 部署

- `uvicorn api.main:app --port 8502`，与 Streamlit 同机运行。
- cloudflared `config.yml` 增加 `api.506ikun.space → http://localhost:8502` 的 ingress，并配置对应 DNS CNAME。
- `docker-compose.yml` 增加 `api` 服务；scheduler 定时跑 `sync.py` + `generate_report.py`。

## 测试与依赖

- 依赖：`fastapi`、`uvicorn[standard]`、`pydantic`；开发依赖 `pytest`（放 `requirements-dev.txt`，不污染运行时镜像）。
- 测试顺序：先 `tests/test_analysis.py`、`tests/test_plugins.py`（已补充并可直接运行），再写 API 层 `TestClient` 测试（临时 SQLite），最后用 `AppTest` 回归前端页面。

## 实施步骤（建议顺序）

1. `api/` 骨架 + `/health` + `/events`（只读，直接复用 `Database`）
2. `/topics` + `/profile/latest`（读快照，不现场计算）
3. `POST /profile/refresh` 后台重建 + 任务状态查询
4. 前端逐页切换到 API（保留直连开关）
5. 修复已知 bug（LDA、共现算法、browser id、Streamlit 弃用 API）
6. 批量写入 + 新索引；按数据规模评估 `aiosqlite` / PostgreSQL

每步保持可独立验证：跑通 `pytest`、`python main.py`、报告生成与四个页面后，再进入下一步。

## 实施状态（2026-08-04）

- [x] `api/` 服务层：`/health`、`/api/v1/events`、`/topics`、`/profile/latest`、`/profile/refresh`（后台任务）、`/stats`
- [x] 依赖管理：`fastapi`/`uvicorn` 加入 `requirements.txt`，新增 `requirements-dev.txt`（pytest）
- [x] SQLite 优化：新增 `event_topics(topic_id)`、`profiles(period, timestamp)` 索引；`insert_events` 改为单事务批量写入
- [x] 已知 bug 修复：LDA `fit_predict`、关系视图共现算法、`browser_history` 不稳定 `hash()`、Streamlit 弃用 API
- [x] 前端迁移：新增 `frontend/data_access.py`（API 优先 + 直连回退），五个页面已切换到数据访问层
- [x] API 测试：`tests/test_api.py`（TestClient + 临时数据库）
- [ ] 数据规模达到数万条后再评估 `aiosqlite` / PostgreSQL（暂不实施）
