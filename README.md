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
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional tracing
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=document-verification-agent

# Optional local model
# OLLAMA_MODEL=gemma3:270m
```

### Run

**API** (after FastAPI is wired in `app/main.py`):

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open API docs at `http://localhost:8000/docs`.

**Streamlit test page**:

```bash
uv run streamlit run streamlit/app.py
```

**Tests**:

```bash
uv run pytest tests/
```

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
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# 可选：链路追踪
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=document-verification-agent

# 可选：本地模型
# OLLAMA_MODEL=gemma3:270m
```

### 运行

**API**（在 `app/main.py` 接入 FastAPI 之后）：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

接口文档：`http://localhost:8000/docs`。

**Streamlit 测试页**：

```bash
uv run streamlit run streamlit/app.py
```

**测试**：

```bash
uv run pytest tests/
```

### 开发

```bash
uv run ruff check --fix
uv run ruff format .
```

Ruff 等开发依赖通过 `pyproject.toml` 中的 `dev` 依赖组安装。

### 许可证

未添加 LICENSE 文件前，默认视为未公开项目。
