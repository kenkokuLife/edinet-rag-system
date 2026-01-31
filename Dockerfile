FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖 - 使用清华镜像源加速
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装日语分词器（mecab）的依赖
RUN apt-get update && apt-get install -y \
    mecab \
    libmecab-dev \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data/raw /app/data/processed /app/logs /app/models

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV TRANSFORMERS_CACHE=/app/models
ENV HF_HOME=/app/models
ENV HF_DATASETS_CACHE=/app/models
ENV TOKENIZERS_PARALLELISM=false
ENV PYTHONUNBUFFERED=1

# 启动应用 - 移除预下载模型步骤
CMD ["python", "-m", "app.main"]