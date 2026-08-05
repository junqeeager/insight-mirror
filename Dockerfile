FROM node:22-slim AS web-builder

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 复制 React 构建产物
COPY --from=web-builder /web/dist /app/web/dist

# 创建数据目录
RUN mkdir -p data/reports data/exports

# 暴露端口
EXPOSE 8501

# 启动 React SPA + FastAPI（同源 :8501）
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8501"]
