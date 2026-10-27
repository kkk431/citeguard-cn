# CiteGuard-CN 部署手册（v0.9.43）

本文覆盖四种落地方式：本地开发、服务器 `.pylibs` 部署、SSH 隧道访问、Docker。
所有方式都遵循同一条安全约束：**API Key 只从环境变量注入，绝不写进仓库或镜像**。

- 项目根目录：`citeguard/`
- Web 入口：`web.app:app`（FastAPI）
- 监听端口：`8000`
- 运行时依赖：`requirements.txt`
- 健康检查：`GET /api/health`（返回 `ok`、`version`、`supported` 后缀列表）
- 无 `DEEPSEEK_API_KEY` 时：支持度判定降级为 `not_checked`，其余功能（引文解析、多源核验、GB/T 7714-2025 字段检查、报告导出）正常。

---

## 1. 本地运行

### 1.1 安装依赖

```bash
cd citeguard
python3 -m pip install -r requirements.txt
```

Python 3.12 推荐；依赖包含 `fastapi`、`uvicorn`、`jinja2`、`python-multipart`、
`requests`、`rapidfuzz`、`pypdf`、`pdfplumber`、`python-docx`。

### 1.2 启动 Web 工作台

```bash
# 在 citeguard/ 目录下执行
PYTHONPATH=src python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
```

打开 <http://127.0.0.1:8000>。页面上传支持 `.pdf` / `.docx` / `.txt` / `.md`，
单文件默认上限 30 MB（`CITEGUARD_MAX_UPLOAD_MB` 可调）。

### 1.3 CLI 与测试

```bash
# CLI 分析一篇论文
PYTHONPATH=src python3 -m citeguard.cli --input web/static/samples/sample_paper.txt --out out/demo

# 单元 + 端到端测试（完全离线，不消耗 API 额度）
PYTHONPATH=src python3 -m pytest tests -q

# 交付物一致性检查（无需网络 / 无需 key）
PYTHONPATH=src python3 scripts/verify_artifacts.py

# 打干净 zip（输出到 dist/）
PYTHONPATH=src python3 scripts/package_deliverable.py
```

Windows PowerShell 下把 `PYTHONPATH=src` 换成 `$env:PYTHONPATH="src;.pylibs"` 即可。

### 1.4 可选：启用 LLM 支持度判定

判定后端是 OpenAI 兼容接口，默认用 DeepSeek；也可以指向**本地开源模型**完全离线跑（Ollama / vLLM / llama.cpp-server / LM Studio）：

```bash
# A. 用 API（默认）
export DEEPSEEK_API_KEY=sk-...          # 仅当前 shell 生效
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_MODEL=deepseek-chat

# B. 用本地开源模型（无需任何 API key）
export CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:11434/v1   # 例：Ollama
export CITEGUARD_JUDGE_MODEL=qwen2.5:7b-instruct
export CITEGUARD_JUDGE_API_KEY=        # 本地服务需要鉴权时才填

# C. 小模型建议换用精简 prompt（默认长 prompt 面向强模型调优）
export CITEGUARD_SUPPORT_PROMPT_FILE=scripts/support_prompt_simple.txt
export CITEGUARD_SUPPORT_AUDIT=0       # 精简 prompt 下关闭覆盖审计

# D. 覆盖审计版本：auto = 托管 API 用 v1、自托管端点自动用 v2（Qwen3 实测更好）
export CITEGUARD_SUPPORT_AUDIT_STYLE=auto   # v1 | v2 | auto
export CITEGUARD_SUPPORT_MAX_REFS=30    # 每个任务最多判定多少条（默认 30，上限 200）
```

> 优先级：`CITEGUARD_JUDGE_*` > `DEEPSEEK_*`。缓存按「模型 + prompt 版本 + 审计版本」分键，切换模型或自定义 prompt 都会自动重新判定。
> prompt 两端统一默认 v10 few-shot（`scripts/support_prompt_v10.txt`）；设置 `CITEGUARD_SUPPORT_PROMPT_FILE` 可显式覆盖（3B 及以下建议 `scripts/support_prompt_simple.txt`）。
> 本地 GPU 实测见 THIRD_PARTY_NOTICES.md §4.2：Qwen3-14B + v10 + 审计 v2 在留出 test 60 上 **0.9574**（同口径托管 0.9598，差 **0.24 分**；dev 40 为 1.0000；全 100 条 0.9744）；Qwen3-8B 0.8515；7B 0.7181。硬件为实验室已有 GPU，非购买。
> 「多篇文献对比」（`/compare`）复用这里的同一个判官接口，没有独立配置；未配置判官时页面只展示说明、不显示提交入口。

也可以复制 `.env.example` 为 `.env` 后由进程管理器 / Docker Compose 注入，
**不要**把 `.env` 提交到仓库，也不要 `COPY` 进 Docker 镜像。

### 1.4.1 公开演示的访问防护（可选）

demo 暴露到公网时建议至少加一道门，避免 API key 额度和上传目录被刷：

```bash
export CITEGUARD_ACCESS_TOKEN=<随机串>    # 空 = 不校验
export CITEGUARD_RATE_LIMIT_PER_MIN=120   # 每 IP 每分钟 POST /api/* 次数，0 = 关闭
export CITEGUARD_SUPPORT_WORKERS=4        # 支持度判定并发，1–8，默认 4
```

- 令牌：浏览器第一次用 `http://host/?token=<随机串>` 打开任意页面即可，服务端会种
  HttpOnly cookie；脚本调用可发 `X-Access-Token` 或 `Authorization: Bearer <token>`。
  未带或带错时页面与 API 返回 401。
- 限流：按客户端 IP 的滑动窗口，只限制 `POST /api/*`（GET 页面与导出不受影响），
  超限返回 429 + `Retry-After: 60`。`/api/health` 与静态资源始终放行。
- 并发：`CITEGUARD_SUPPORT_WORKERS` 只影响每条引文的判定并发，不改变「最多判定 N 条」
  的截断语义；进度条按完成条数递增。

### 1.5 可选：网页型引文链接检查

带 URL 的 `[EB/OL]` 引文会先检查链接可达性并读取页面标题（可达且标题一致 → 判「真实一致」）；
链接失效/需要登录只提示人工核对，不会判「疑似虚构」。默认开启、按 URL 缓存：

```bash
export CITEGUARD_URL_CHECK=1            # 0 = 完全离线，不做链接检查
export CITEGUARD_URL_CHECK_TIMEOUT=8    # 单条链接超时（秒，最大不超过 HTTP_TIMEOUT）
```

安全检查：只允许 http/https、80/443 端口，目标 IP 必须是公网地址（拒绝 localhost/内网/回环），
响应体截断 300 KB。若部署在完全隔离的内网，建议显式设为 `0`。

### 1.6 可选：图表结论核验（需要一台 GPU 主机）

产品本身不加载视觉模型。在 GPU 主机上：

```bash
pip install -U transformers accelerate qwen-vl-utils
python scripts/local_vl_server.py --model /path/Qwen2.5-VL-7B-Instruct \
    --host 0.0.0.0 --port 8099
```

在 Web 主机上配置：

```bash
export CITEGUARD_VL_ENDPOINT=http://<gpu-host>:8099/v1
export CITEGUARD_VL_MODEL=qwen3-vl-8b       # 与服务端 --model-name 一致
export CITEGUARD_VL_TIMEOUT=60                # 首次请求含加载模型的时间
export CITEGUARD_VL_MAX_FIGURE_MB=8
# 可选：export CITEGUARD_VL_API_KEY=...
```

未配置 `CITEGUARD_VL_ENDPOINT` 时，`/figure` 只显示说明与部署方法，不接收提交；首页也不会出现入口。
Qwen2.5-VL-7B 在单张 RTX 4090（24 GB）上 bf16 约占 16 GB，首次加载 ~8 秒，之后 1.8–2.6 秒/条。
图表页可选粘贴论文正文/图注（最多 4000 字，表单字段 `context`）：不填只核对图表，填写后同时判断正文是否支持该结论；
50 条评测上 v2+上下文 0.94、仅图 0.90，误报矛盾 0（`docs/figure_check.md`）。
评测与局限见 [figure_check.md](figure_check.md)。

---

## 2. 服务器部署（`/data/xyjiang/aic_mental/citeguard`，`.pylibs` 方案）

目标机器通常没有 root、也不方便建 venv，因此把依赖装进项目内的 `.pylibs/`。

### 2.1 同步代码与安装依赖

```bash
cd /data/xyjiang/aic_mental/citeguard

# 首次安装（清华源，适合国内服务器）
python3 -m pip install --target .pylibs -r requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple

# 升级依赖时同样执行上面的命令（--upgrade 可加可不加）
```

### 2.2 启动服务

```bash
cd /data/xyjiang/aic_mental/citeguard
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" \
PYTHONPATH=src:.pylibs \
python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
```

要点：

- `PYTHONPATH=src:.pylibs`：先源码、后本地依赖；不需要 `pip install -e .`。
- `data/`、`data/jobs/`、`data/cache/` 需要可写；上传文件在解析完成后立即删除。
- 用 `.env.remote` 保存密钥时，务必 `set -a; . ./.env.remote; set +a` 后再启动，否则这些变量只是 shell 变量、
  不会传给 uvicorn 子进程（实测踩过的坑；`CITEGUARD_VL_*` 就因此一度没生效）。
- 服务默认无守护。长期运行建议交给 `systemd`、`tmux` 或 `nohup`：

```bash
nohup env PYTHONPATH=src:.pylibs \
  python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000 \
  > citeguard.log 2>&1 &
```

### 2.3 反向代理 / 防火墙

若只允许本机或跳板机访问，推荐把监听地址改成 `--host 127.0.0.1`，再用第 3 节的 SSH 隧道；
若必须 `--host 0.0.0.0`，请用安全组 / `ufw` / `iptables` 限制来源 IP，不要直接暴露到公网。
Nginx 反向代理示例（片段）：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    client_max_body_size 32m;   # 与 CITEGUARD_MAX_UPLOAD_MB 对齐
    proxy_read_timeout 300s;
}
```

### 2.4 systemd 单元（可选）

```ini
# /etc/systemd/system/citeguard.service
[Unit]
Description=CiteGuard-CN web app
After=network.target

[Service]
User=xyjiang
WorkingDirectory=/data/xyjiang/aic_mental/citeguard
Environment=PYTHONPATH=src:.pylibs
Environment=DEEPSEEK_API_KEY=
ExecStart=/usr/bin/python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

> 生产环境请把 key 放在 root 可读的 `EnvironmentFile` 或用 `systemctl edit` 注入，
> 不要把真实 key 写进仓库里的 unit 文件。

### 2.5 增量更新（已部署实例）

服务器上的部署目录**不是 git 仓库**，更新时从本地打包改动的文件再解压：

```bash
# 本地打包（只打改过的文件，保持相对路径）
tar -cf out/deploy.tar src/citeguard/metadata_verify.py web/app.py \
  web/static/css/app.css web/templates/index.html

# 上传并解压
scp out/deploy.tar xyjiang@<host>:/tmp/citeguard_deploy.tar
ssh xyjiang@<host> 'cd /data/xyjiang/aic_mental/citeguard && tar -xf /tmp/citeguard_deploy.tar'

# 重启：pkill 旧 uvicorn → source .env.remote → nohup 启动 → 健康检查
bash /tmp/restart_remote.sh
```

验证（服务器本机）：

```bash
curl -s http://127.0.0.1:8000/api/health          # {"ok":true,...}
curl -s http://127.0.0.1:8000/static/js/index.js | grep -c "批量汇总"   # 前端是否为新版
```

> 演示实例的 `DEEPSEEK_API_KEY` 放在服务器 `citeguard/.env.remote`（`chmod 600`，不进仓库、
> 不进 zip）；重启脚本会 `source` 它。没有该文件时服务照常启动，只是支持度显示「未检测」。

如果题录库是在没有摘要的情况下导入的，可在服务器上补全（只取公开元数据）：

```bash
cd /data/xyjiang/aic_mental/citeguard
PYTHONPATH=src:.pylibs python3 scripts/enrich_library_abstracts.py --dry-run
PYTHONPATH=src:.pylibs python3 scripts/enrich_library_abstracts.py
```

---

## 3. 远程访问：SSH 隧道（演示默认方式）

> 本机实测：远端 `http://222.20.96.215:8000/` 与 `/api/health` 从当前网络均**超时**（服务端监听
> `0.0.0.0:8000` 正常，属校园网/防火墙限制）。**不要对外承诺公网地址**；答辩演示用本机 `127.0.0.1:8010`
> 或 SSH 隧道。若评审需要远程访问，请提前向网络管理员申请端口，或让评审连校园 VPN 后访问内网地址。

服务器上仅监听 `127.0.0.1:8000`（或防火墙只放行本机）时，用 SSH 本地端口转发：

```bash
ssh -L 8000:127.0.0.1:8000 jxy-2
```

保持该会话不退出，然后在本地浏览器打开 <http://127.0.0.1:8000>。
`8000` 被本地占用时换成任意空闲端口，例如：

```bash
ssh -L 18000:127.0.0.1:8000 jxy-2
# 浏览器访问 http://127.0.0.1:18000
```

排查：

- `channel 2: open failed: connect failed: Connection refused`：服务器上的 uvicorn 没启动，
  或监听地址与转发目标不一致。
- 本地端口已占用：`lsof -i :8000`（macOS/Linux）或 `netstat -ano | findstr :8000`（Windows）。
- 隧道建立后页面 404：确认命令在 `citeguard/` 目录执行，且 `PYTHONPATH=src`。

---

## 4. Docker 部署

镜像定义：`docker/Dockerfile`；编排：`docker/docker-compose.yml`。
构建上下文必须是 `citeguard/`（不是 `docker/`），`.dockerignore` 已排除
`.env`、`data/jobs`、`data/cache`、`data/uploads`、`.pylibs`、`dist`、`tests` 等。

### 4.1 直接构建 / 运行

```bash
cd citeguard
docker build -f docker/Dockerfile -t citeguard-cn:0.9.17 .

docker run --rm -p 127.0.0.1:8000:8000 \
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" \
  -v "$PWD/data/jobs:/app/data/jobs" \
  -v "$PWD/data/cache:/app/data/cache" \
  citeguard-cn:0.9.17
```

镜像内固定 `PYTHONPATH=/app/src`，启动命令：

```text
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

### 4.2 Docker Compose（推荐）

```bash
cd citeguard
export DEEPSEEK_API_KEY=sk-...        # 不设置也能跑，支持度会是 not_checked
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f citeguard
```

默认映射 `127.0.0.1:8000 -> 8000`，即只允许本机访问；需要局域网访问时把
`docker-compose.yml` 里的端口改成 `"8000:8000"` 并配合防火墙。

说明：

- **Key 只来自环境变量**：`${DEEPSEEK_API_KEY:-}`；compose 不使用 `env_file: .env`，
  Dockerfile 也不 `COPY .env`，因此镜像里没有密钥。
- `data/jobs` 与 `data/cache` 以 bind mount 持久化，重建容器不丢任务与缓存。
- 镜像内置 `HEALTHCHECK`，轮询 `/api/health`；`docker ps` 的 `STATUS` 会显示 `healthy`。
- 只把 `data/citebench_cn/results.json` 打进镜像（`/benchmark` 页面需要），
  不打包 15 MB 的离线缓存与 `data/jobs` 历史。
- 以非 root 用户 `citeguard`（UID 10001）运行。

### 4.3 无外网环境的镜像搬运

```bash
# 有网机器
docker save citeguard-cn:0.9.17 | gzip > citeguard-cn-0.9.17.tar.gz
# 目标机器
docker load < citeguard-cn-0.9.17.tar.gz
```

---

## 5. 无 API Key 的降级行为

`DEEPSEEK_API_KEY` 为空时：

- `support.judge_support()` 返回 `None`，`pipeline` 随即把该条记为 `not_checked`；
- 报告 `stats.support.not_checked` 等于未判定条数，`stats.support_meta.judge_available == false`；
- 报告页面显示「支持度：未检测」，不会报错、不会阻塞任务；
- 引文解析、OpenAlex/Crossref/arXiv 元数据核验、GB/T 7714-2025 字段检查、
  HTML/Markdown/JSON 导出全部可用。

完全断网时：

- `metadata_verify` 把每个请求的异常收敛为 `Unknown`（而不是崩溃），任务仍能完成；
- 报告里核验状态为「无法核验（网络/数据源问题）」，属于预期降级；
- 可用 `data/cache/` 预热过的缓存结果做离线演示（把缓存目录一起搬运即可）。

---

## 6. 验收清单

```bash
cd citeguard
PYTHONPATH=src:.pylibs python3 -m pytest tests -q          # 应全绿（含离线端到端）
PYTHONPATH=src python3 scripts/verify_artifacts.py         # 应输出 [OK] all checks passed
PYTHONPATH=src python3 scripts/package_deliverable.py      # 生成 dist/citeguard-cn-0.9.17.zip
curl -s http://127.0.0.1:8000/api/health                   # {"ok":true,...}
```

Docker 方式额外验证：

```bash
docker compose -f docker/docker-compose.yml up -d --build
docker inspect --format '{{.State.Health.Status}}' citeguard   # healthy
curl -s http://127.0.0.1:8000/api/health
```

---

## 7. FAQ

**Q1. 启动报 `ModuleNotFoundError: No module named 'citeguard'`？**
没有设置 `PYTHONPATH=src`。在 `citeguard/` 目录运行，或显式
`PYTHONPATH=src:.pylibs python3 -m uvicorn web.app:app ...`。

**Q2. 服务器上没有 venv/virtualenv，能装依赖吗？**
用 `.pylibs` 方案：`python3 -m pip install --target .pylibs -r requirements.txt`，
运行时把 `.pylibs` 放进 `PYTHONPATH`（放在 `src` 之后）。

**Q3. 上传 `.docx` 报 500 / `No module named 'docx'`？**
`python-docx` 未安装。`requirements.txt` 已包含 `python-docx>=1.1`，
重新执行 `pip install -r requirements.txt`（服务器上装到 `.pylibs`）。
旧版 `.doc` 不支持，会提示先另存为 `.docx`。

**Q4. 上传 PDF 后任务失败，提示“没有可提取的文字层”？**
扫描件 / 图片型 PDF 没有文本层。先用 OCR（PaddleOCR、Acrobat「识别文本」）处理，
或直接上传 Word 原稿。

**Q5. 上传大文件返回 413？**
默认上限 30 MB，由 `CITEGUARD_MAX_UPLOAD_MB` 控制；Nginx 侧还要放宽
`client_max_body_size`。

**Q6. 报告里全是“无法核验 / Unknown”？**
服务器无法访问 OpenAlex / Crossref / arXiv，或代理未配置。
检查 `curl -I https://api.crossref.org/works`；也可复制预热过的 `data/cache/` 到部署目录。

**Q7. 支持度全是“未检测（not_checked）”？**
没有配置 `DEEPSEEK_API_KEY`，或摘要缺失、正文未引用、超出本次判定上限
（`CITEGUARD_SUPPORT_MAX_REFS` / 页面上的上限参数）。看
`stats.support_meta` 中的 `skipped_no_abstract`、`skipped_no_claim`、`skipped_by_cap`。

**Q8. 端口 8000 被占用？**
`lsof -i :8000` / `netstat -ano | findstr :8000` 找到进程后停掉，
或换端口启动并用 SSH 隧道映射。

**Q9. Docker 构建很慢 / 拉不到基础镜像？**
配置镜像加速器或先在能联网的机器 `docker save` / `docker load`；
构建上下文已通过 `.dockerignore` 精简。

**Q10. 为什么镜像里没有 `data/jobs` 历史记录？**
交付镜像刻意只带只读的 benchmark 结果；任务与缓存通过 volume 持久化，
避免把用户上传内容和密钥带进镜像。

**Q11. 如何确认某次部署的版本？**
`curl -s http://127.0.0.1:8000/api/health`，`version` 字段即当前版本（本手册对应 `0.9.17`）。

- 图表核验 prompt 可选 `CITEGUARD_FIGURE_PROMPT=2|4`：2 为默认（中文论文图表），4 为分步读图（慢约 2 倍，ChartCheck 这类公开英文图表上收益明显）。
