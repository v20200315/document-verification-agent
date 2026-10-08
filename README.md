# Document Verification Agent / 文档核验智能体

[English](#english) | [中文](#中文)

---

## English

A LangGraph-based agent that verifies uploaded documents (PDF / image) by extracting content, classifying the material type, and cross-checking fields against third-party CCC data.

### Features

- Accept PDF and image uploads, with OCR when the file is a scan or photo
- Extract both raw text and structured fields
- Classify the document type (for example certificate, report, or supporting material)
- Query CCC (China Compulsory Certification) third-party data and compare it with extracted fields
- Expose the workflow through a FastAPI API
- Provide a Streamlit page for local testing

### Architecture

Typical verification flow:

```text
Upload (PDF / Image)
        │
        ▼
  Document parsing / OCR     app/tools/document.py
        │
        ▼
  Material classification    app/tools/classification.py
        │
        ▼
  Raw + structured extract   app/tools/extraction.py
        │
        ▼
  CCC third-party lookup     app/tools/ccc.py
        │
        ▼
  LangGraph agent            app/agent/graph.py
        │
        ▼
  Verification result        FastAPI / Streamlit
```

The agent state lives in `app/agent/state.py`. Request and response models live in `app/models/schemas.py`.

### Project structure

```text
document-verification-agent/
├── pyproject.toml
├── uv.lock
├── .env
├── README.md
│
├── app/
│   ├── main.py                  # FastAPI entry
│   │
│   ├── api/
│   │   └── verification.py      # Verification API
│   │
│   ├── agent/
│   │   ├── graph.py             # LangGraph workflow
│   │   └── state.py             # Agent state
│   │
│   ├── tools/
│   │   ├── document.py          # PDF / image / OCR
│   │   ├── extraction.py        # Raw / structured extraction
│   │   ├── classification.py    # Material type classification
│   │   └── ccc.py               # CCC third-party lookup
│   │
│   └── models/
│       └── schemas.py           # Pydantic models
│
├── streamlit/
│   └── app.py                   # Local test UI
│
└── tests/
    └── test_agent.py
```

### Tech stack

| Layer | Stack |
| --- | --- |
| Language | Python 3.12+ |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Agent | LangChain, LangGraph |
| LLM | OpenAI-compatible API and/or local Ollama |
| API | FastAPI |
| UI | Streamlit |
| Config | python-dotenv |
| Lint / format | Ruff |

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An OpenAI (or compatible) API key, **or** a local [Ollama](https://ollama.com/) model
- Optional: LangSmith account if you want tracing

### Setup

```bash
git clone <repo-url>
cd document-verification-agent
uv sync
```

This creates `.venv` and installs dependencies from `uv.lock`.

Activate the environment if you prefer running commands without `uv run`:

```bash
source .venv/bin/activate
```

### Environment variables

Copy the keys you need into `.env` in the project root. Do not commit real secrets.

```bash
DASHSCOPE_API_KEY=sk-...

# Optional: in-process verification queue (defaults shown)
# CCC_CONCURRENCY=3
# CCC_QUEUE_WAIT_SECONDS=20
# CCC_TIMEOUT_SECONDS=60
# TEST_REPORT_CONCURRENCY=2
# TEST_REPORT_QUEUE_WAIT_SECONDS=40
# TEST_REPORT_TIMEOUT_SECONDS=180
```

### Run

**API**:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive docs: `http://localhost:8000/docs`. Health check: `GET /health`.

Both verification endpoints accept a **multipart file upload** (`file`). Success and errors both return JSON with `status_code`. A successful body also includes `report` (Markdown). An error body includes `error` and `detail`. Set `DASHSCOPE_API_KEY` in the environment or project-root `.env`.

#### `POST /verify/ccc`

Verify a CCC certificate. Upload one PDF or image (`pdf`, `jpg`, `jpeg`, `png`). The service extracts certificate fields, reads the CQC QR URL, fetches the current website record, compares certificate number / models / standards, and checks expiration (from the upload) plus certificate status (from the website). Queue wait: **20 seconds**. Execution timeout: **60 seconds**. Concurrent jobs: **3**.

```bash
curl -X POST "http://localhost:8000/verify/ccc" \
  -F "file=@/path/to/certificate.jpg"
```

#### `POST /verify/test-report`

Verify a Chinese product test report. Upload one **PDF** (max 50 MB). The service classifies the product category and runs the category rules. Queue wait: **40 seconds**. Execution timeout: **180 seconds**. Concurrent jobs: **2**.

```bash
curl -X POST "http://localhost:8000/verify/test-report" \
  -F "file=@/path/to/report.pdf"
```

#### Status codes

| HTTP | `error` | Meaning |
| --- | --- | --- |
| 200 | — | Verification finished; JSON with `status_code` and Markdown `report` |
| 400 | `invalid_upload` | Empty file or unsupported type |
| 422 | `not_ccc_document` / `not_test_report` | File is not a CCC certificate, or the report category is Other |
| 429 | `queue_timeout` | Waited too long for a concurrency slot |
| 500 | `system_error` | Pipeline or unexpected system failure |
| 503 | `missing_api_key` | `DASHSCOPE_API_KEY` is not configured |
| 504 | `timeout` | Execution exceeded 1 minute (CCC) or 3 minutes (test report) |

Success body:

```json
{
  "status_code": 200,
  "report": "# CCC 证书核验最终报告\n\n..."
}
```

Error body:

```json
{
  "status_code": 422,
  "error": "not_ccc_document",
  "detail": "上传文件不是 CCC 证书，当前识别类型为：Other。"
}
```

#### Concurrency queue

Both endpoints are long-running (LLM + HTTP + parsing). FastAPI still waits for the result, but each endpoint has its **own in-process semaphore** so one type cannot starve the other.

```text
Request
  → read upload
  → wait for a slot (queue wait timeout)
  → run verification (execution timeout)
  → release the slot
```

| Setting | CCC default | Test report default |
| --- | --- | --- |
| Concurrent executions | `CCC_CONCURRENCY=3` | `TEST_REPORT_CONCURRENCY=2` |
| Queue wait timeout | `CCC_QUEUE_WAIT_SECONDS=20` | `TEST_REPORT_QUEUE_WAIT_SECONDS=40` |
| Execution timeout | `CCC_TIMEOUT_SECONDS=60` | `TEST_REPORT_TIMEOUT_SECONDS=180` |

Client time ≈ queue wait + execution. Queue timeout returns **429**; execution timeout returns **504**. A timed-out job may still run in a background thread, so the semaphore is what actually caps load.

Keep **one uvicorn worker** and **one `api` container**. Extra workers or replicas multiply the limits. For multiple machines, a shared Redis queue would be needed later.

**Sandbox Streamlit** (CCC, Simple RAG, Image PDF to Text, Verify Test Report):

```bash
uv run streamlit run sandbox/app/streamlit_app.py
```

**Docker**: put `DASHSCOPE_API_KEY` in the project-root `.env`. Compose injects it at runtime; the image does not copy `.env`.

Build and start FastAPI (port 8000) and Streamlit (port 8501):

```bash
docker compose up --build
```

API only:

```bash
docker compose up --build api
```

Then open `http://localhost:8000/docs` and `http://localhost:8501`.

Test the API from the host:

```bash
curl http://localhost:8000/health

curl -X POST "http://localhost:8000/verify/ccc" \
  -F "file=@/path/to/certificate.jpg"

curl -X POST "http://localhost:8000/verify/test-report" \
  -F "file=@/path/to/report.pdf"
```

Stop:

```bash
docker compose down
```

**Streamlit test page**:

```bash
uv run streamlit run streamlit/app.py
```

**Tests**:

```bash
uv run pytest tests/
```

### Rebuild after code changes

Code changes are not picked up by a container restart alone. Rebuild the image.

**On this machine**, from the project root:

```bash
docker compose up --build -d
```

API only:

```bash
docker compose up --build -d api
```

Follow logs:

```bash
docker compose logs -f api
```

Check:

```bash
curl http://localhost:8000/health
```

Docs: `http://localhost:8000/docs`.

**On the server:** push the latest code first, then SSH in:

```bash
cd document-verification-agent
git pull
docker compose up --build -d
```

Leave `.env` as-is (the key is injected at runtime, not baked into the image).

Confirm:

```bash
docker compose ps
curl http://localhost:8000/health
```

Notes:

- Omitting `--build` keeps the old image; report/API changes will not appear.
- If you did not `git push` locally, `git pull` on the server will not get the new code.
- To drop old containers first:

```bash
docker compose down
docker compose up --build -d
```

Usually `docker compose up --build -d` is enough.

### Deploy to a server

Typical flow: SSH into the server, install Docker, clone or pull the repo, write `.env`, then `docker compose up --build`. You do not need Python or `uv` on the host; dependencies are inside the image.

1. **SSH into the server.**

2. **Install Docker Engine** (includes `docker compose`). Confirm:

   ```bash
   docker --version
   docker compose version
   ```

3. **Get the code.** First time:

   ```bash
   git clone <repo-url>
   cd document-verification-agent
   ```

   Later updates:

   ```bash
   git pull
   ```

   To run a specific branch or tag: `git checkout <branch-or-tag>`.

4. **Create `.env` on the server** (do not commit secrets). The image does not copy `.env`; Compose injects it at runtime:

   ```bash
   DASHSCOPE_API_KEY=your-real-key
   ```

5. **Build and start** (background):

   ```bash
   docker compose up --build -d
   ```

   API only:

   ```bash
   docker compose up --build -d api
   ```

6. **Open ports** on the firewall / security group: **8000** (FastAPI), and **8501** if you need Streamlit. Then open `http://<server-ip>:8000/docs`.

7. **Smoke-test:**

   ```bash
   curl http://localhost:8000/health
   curl -X POST "http://localhost:8000/verify/ccc" \
     -F "file=@/path/to/certificate.jpg"
   ```

8. **Update later:**

   ```bash
   git pull
   docker compose up --build -d
   ```

9. **Stop:**

   ```bash
   docker compose down
   ```

For public internet access, put Nginx (or similar) in front and terminate HTTPS. Building on the server is fine for internal or test machines; a more production-like path is to build the image in CI, push it to a registry, and `docker compose pull` on the server.

### Development

```bash
uv run ruff check --fix
uv run ruff format .
```

Dev tools such as Ruff are installed via the `dev` dependency group in `pyproject.toml`.

### License

Private / unpublished unless a license file is added.

---

## 中文

基于 LangGraph 的文档核验智能体：接收 PDF / 图片，完成内容提取与材料分类，再对照 CCC 第三方数据核验字段是否一致。

### 功能

- 支持 PDF 与图片上传；扫描件 / 照片走 OCR
- 同时提取原文与结构化字段
- 判断材料类型（例如证书、报告、佐证材料）
- 查询 CCC（中国强制性产品认证）第三方数据，并与提取结果比对
- 通过 FastAPI 对外提供核验接口
- 提供 Streamlit 本地测试页面

### 架构

典型核验流程：

```text
上传（PDF / 图片）
        │
        ▼
  文档解析 / OCR              app/tools/document.py
        │
        ▼
  材料类型判断                app/tools/classification.py
        │
        ▼
  原文 + 结构化提取           app/tools/extraction.py
        │
        ▼
  CCC 第三方数据查询          app/tools/ccc.py
        │
        ▼
  LangGraph 智能体            app/agent/graph.py
        │
        ▼
  核验结果                    FastAPI / Streamlit
```

智能体状态定义在 `app/agent/state.py`，请求与响应模型定义在 `app/models/schemas.py`。

### 项目结构

```text
document-verification-agent/
├── pyproject.toml
├── uv.lock
├── .env
├── README.md
│
├── app/
│   ├── main.py                  # FastAPI 入口
│   │
│   ├── api/
│   │   └── verification.py      # API 接口
│   │
│   ├── agent/
│   │   ├── graph.py             # LangGraph 工作流
│   │   └── state.py             # Agent State
│   │
│   ├── tools/
│   │   ├── document.py          # PDF / 图片 / OCR
│   │   ├── extraction.py        # 原文 / 结构化数据提取
│   │   ├── classification.py    # 材料类型判断
│   │   └── ccc.py               # CCC 第三方数据查询
│   │
│   └── models/
│       └── schemas.py           # Pydantic 数据模型
│
├── streamlit/
│   └── app.py                   # 测试页面
│
└── tests/
    └── test_agent.py
```

### 技术栈

| 层级 | 技术 |
| --- | --- |
| 语言 | Python 3.12+ |
| 包管理 | [uv](https://docs.astral.sh/uv/) |
| 智能体 | LangChain、LangGraph |
| 大模型 | OpenAI 兼容接口，和/或本地 Ollama |
| API | FastAPI |
| 界面 | Streamlit |
| 配置 | python-dotenv |
| 代码检查 / 格式化 | Ruff |

### 环境要求

- Python 3.12 及以上
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- OpenAI（或兼容）API Key，**或**本地 [Ollama](https://ollama.com/) 模型
- 可选：LangSmith 账号（用于链路追踪）

### 安装

```bash
git clone <repo-url>
cd document-verification-agent
uv sync
```

会创建 `.venv`，并按 `uv.lock` 安装依赖。

如需直接使用虚拟环境中的命令：

```bash
source .venv/bin/activate
```

### 环境变量

在项目根目录的 `.env` 中填写所需密钥。请勿将真实密钥提交到仓库。

```bash
DASHSCOPE_API_KEY=sk-...

# 可选：进程内核验队列（下列为默认值）
# CCC_CONCURRENCY=3
# CCC_QUEUE_WAIT_SECONDS=20
# CCC_TIMEOUT_SECONDS=60
# TEST_REPORT_CONCURRENCY=2
# TEST_REPORT_QUEUE_WAIT_SECONDS=40
# TEST_REPORT_TIMEOUT_SECONDS=180
```

### 运行

**API**：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

交互文档：`http://localhost:8000/docs`。健康检查：`GET /health`。

两个核验接口都使用 **multipart 文件上传**（字段名 `file`）。成功和失败都返回带 `status_code` 的 JSON。成功时另有 Markdown 字段 `report`；失败时另有 `error`、`detail`。需在环境变量或项目根目录 `.env` 中配置 `DASHSCOPE_API_KEY`。

#### `POST /verify/ccc`

核验 CCC 证书。上传一份 PDF 或图片（`pdf` / `jpg` / `jpeg` / `png`）。服务会提取证书字段、识别 CQC 二维码链接、抓取官网当前记录，比对证书编号 / 型号规格 / 适用标准，并核验上传件有效期与官网证书状态。排队等待：**20 秒**。执行超时：**60 秒**。同时执行：**3** 份。

```bash
curl -X POST "http://localhost:8000/verify/ccc" \
  -F "file=@/path/to/certificate.jpg"
```

#### `POST /verify/test-report`

核验检测报告。上传一份 **PDF**（最大 50 MB）。服务会识别产品类别并按对应规则做合规核验。排队等待：**40 秒**。执行超时：**180 秒**。同时执行：**2** 份。

```bash
curl -X POST "http://localhost:8000/verify/test-report" \
  -F "file=@/path/to/report.pdf"
```

#### 状态码

| HTTP | `error` | 含义 |
| --- | --- | --- |
| 200 | — | 核验完成，JSON 含 `status_code` 与 Markdown `report` |
| 400 | `invalid_upload` | 空文件或格式不支持 |
| 422 | `not_ccc_document` / `not_test_report` | 不是 CCC 证书，或检测报告类别为 Other |
| 429 | `queue_timeout` | 等待并发槽位超时 |
| 500 | `system_error` | 解析失败或其他系统错误 |
| 503 | `missing_api_key` | 未配置 `DASHSCOPE_API_KEY` |
| 504 | `timeout` | 执行超时：3C 超过 1 分钟，或检测报告超过 3 分钟 |

成功体：

```json
{
  "status_code": 200,
  "report": "# CCC 证书核验最终报告\n\n..."
}
```

错误体：

```json
{
  "status_code": 422,
  "error": "not_ccc_document",
  "detail": "上传文件不是 CCC 证书，当前识别类型为：Other。"
}
```

#### 并发队列

两个接口都是长任务（大模型 + HTTP + 解析）。接口仍同步返回结果，但各自有一套 **进程内信号量**，避免检测报告把 3C 堵住。

```text
请求进来
  → 读上传文件
  → 排队等槽位（排队超时）
  → 执行核验（执行超时）
  → 释放槽位
```

| 配置 | 3C 默认 | 检测报告默认 |
| --- | --- | --- |
| 同时执行数 | `CCC_CONCURRENCY=3` | `TEST_REPORT_CONCURRENCY=2` |
| 排队等待超时 | `CCC_QUEUE_WAIT_SECONDS=20` | `TEST_REPORT_QUEUE_WAIT_SECONDS=40` |
| 执行超时 | `CCC_TIMEOUT_SECONDS=60` | `TEST_REPORT_TIMEOUT_SECONDS=180` |

客户端总耗时 ≈ 排队时间 + 执行时间。排队超时返回 **429**；执行超时返回 **504**。执行超时后线程里的任务可能仍在跑，真正控负载的是信号量。

请保持 **1 个 uvicorn worker**、**1 个 api 容器**。多 worker 或多副本会把限制翻倍。多机部署以后需要 Redis 一类共享队列。

**Sandbox Streamlit**（CCC、Simple RAG、图片 PDF 转文本、检测报告核验）：

```bash
uv run streamlit run sandbox/app/streamlit_app.py
```

**Docker**：在项目根目录 `.env` 中设置 `DASHSCOPE_API_KEY`。Compose 会在运行时注入该变量，镜像不会复制 `.env`。

同时启动 FastAPI（8000）和 Streamlit（8501）：

```bash
docker compose up --build
```

只启动 API：

```bash
docker compose up --build api
```

然后打开 `http://localhost:8000/docs` 和 `http://localhost:8501`。

在宿主机上测接口：

```bash
curl http://localhost:8000/health

curl -X POST "http://localhost:8000/verify/ccc" \
  -F "file=@/path/to/certificate.jpg"

curl -X POST "http://localhost:8000/verify/test-report" \
  -F "file=@/path/to/report.pdf"
```

停止：

```bash
docker compose down
```

**Streamlit 测试页**：

```bash
uv run streamlit run streamlit/app.py
```

**测试**：

```bash
uv run pytest tests/
```

### 代码更新后重新发布 Docker

改过代码后必须**重新构建镜像**，只重启容器不会带上新代码。

**本机**，在项目根目录：

```bash
docker compose up --build -d
```

只更新 API：

```bash
docker compose up --build -d api
```

看日志：

```bash
docker compose logs -f api
```

检查：

```bash
curl http://localhost:8000/health
```

文档：`http://localhost:8000/docs`。

**服务器：** 先把最新代码推到远程，再 SSH 登录：

```bash
cd document-verification-agent
git pull
docker compose up --build -d
```

`.env` 不用动（密钥本来就不在镜像里）。

确认新容器起来：

```bash
docker compose ps
curl http://localhost:8000/health
```

注意：

- 漏了 `--build` 会继续跑旧镜像，接口和报告改动不会生效。
- 本机改完但没 `git push`，服务器 `git pull` 也拉不到。
- 想先清掉旧容器再重建：

```bash
docker compose down
docker compose up --build -d
```

一般 `docker compose up --build -d` 就够。

### 发布到服务器

常见流程：SSH 登录服务器 → 安装 Docker → clone / pull 代码 → 写 `.env` → `docker compose up --build`。服务器上不必再装 Python 或 `uv`，依赖都在镜像里。

1. **SSH 登录服务器。**

2. **安装 Docker Engine**（自带 `docker compose`）。确认：

   ```bash
   docker --version
   docker compose version
   ```

3. **获取代码。** 第一次：

   ```bash
   git clone <repo-url>
   cd document-verification-agent
   ```

   之后更新：

   ```bash
   git pull
   ```

   发布指定分支或标签：`git checkout <branch-or-tag>`。

4. **在服务器上创建 `.env`**（不要把密钥提交进 git）。镜像不会复制 `.env`，Compose 在运行时注入：

   ```bash
   DASHSCOPE_API_KEY=真实密钥
   ```

5. **构建并后台启动：**

   ```bash
   docker compose up --build -d
   ```

   只启动 API：

   ```bash
   docker compose up --build -d api
   ```

6. **在防火墙 / 安全组放行端口**：**8000**（FastAPI），需要 UI 时再放 **8501**。然后打开 `http://<服务器IP>:8000/docs`。

7. **冒烟测试：**

   ```bash
   curl http://localhost:8000/health
   curl -X POST "http://localhost:8000/verify/ccc" \
     -F "file=@/path/to/certificate.jpg"
   ```

8. **之后更新：**

   ```bash
   git pull
   docker compose up --build -d
   ```

9. **停止：**

   ```bash
   docker compose down
   ```

公网访问建议在前面加 Nginx 并配置 HTTPS。在服务器上 `compose up --build` 适合内网或测试机；更稳妥的生产做法是在 CI 里构建镜像、推到仓库，服务器只 `docker compose pull` 后启动。

### 开发

```bash
uv run ruff check --fix
uv run ruff format .
```

Ruff 等开发依赖通过 `pyproject.toml` 中的 `dev` 依赖组安装。

### 许可证

未添加 LICENSE 文件前，默认视为未公开项目。
