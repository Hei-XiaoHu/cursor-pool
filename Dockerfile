FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY app/ ./app/
COPY data/ ./data/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建非root用户
RUN useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 3200

# 启动命令
CMD ["gunicorn", "--workers=4", "--worker-class=gevent", "--bind=0.0.0.0:3200", "app.app:app"]