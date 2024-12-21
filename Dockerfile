FROM python:3.9-slim
WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY app/ .
COPY data/ ./data/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 3200

# 使用 Flask 的内置服务器
CMD ["python", "app.py"]