# 阶段一：构建 Vue 应用
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

# 阶段二：使用 Nginx 部署静态文件
FROM nginx:alpine
# 将打包好的 dist 目录复制到 nginx 默认 HTML 路径
COPY --from=builder /app/dist /usr/share/nginx/html
# 暴露 80 端口
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]