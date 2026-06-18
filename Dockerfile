FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir .

# 复制源码
COPY . .

# 创建输出目录
RUN mkdir -p /app/output

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--config", "/app/config.yaml"]
