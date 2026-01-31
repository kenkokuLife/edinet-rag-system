# 使用Nginx直接提供静态文件
FROM nginx:alpine

# 复制HTML文件
COPY index.html /usr/share/nginx/html/

# 创建JavaScript文件
RUN echo 'console.log("EDINET RAG Frontend loaded");' > /usr/share/nginx/html/app.js

# 复制自定义配置（如果需要）
# COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]