# Docker 发布

```bash
docker build -f docker/Dockerfile -t citeguard-cn:1.0.0 .
docker run --rm -p 8000:8000 citeguard-cn:1.0.0
# 或
docker compose -f docker/docker-compose.yml up --build
```

- 镜像内为 Apache-2.0 核心依赖；PyMuPDF 不在镜像内。
- 已验证：`citeguard-cn:0.9.85` 构建成功，`/api/health` 返回 0.9.85/offline=true。
- **1.0.0 构建未验证**：本机 Docker containerd 存储在一次系统盘写满后损坏
  （`blob ... input/output error`），需要重建 Docker 数据目录；这不是代码问题。
- 健康检查：`curl http://127.0.0.1:8000/api/health`。
