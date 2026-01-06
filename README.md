# Operations Dashboard MCP & AI Dashboard

本仓库提供两部分能力：

- **MCP 服务端**（`operations_dashboard/`）：以 FastMCP 暴露运营数据与洞察工具。
- **AI Dashboard 前端**（`src/ai_dashboard/`）：基于 Next.js + Vercel AI SDK 的对话式运营看板。

当前运营数据 **默认来自 Mock 数据源**，仅用于演示与联调；如需真实数据，需要替换/实现真实数据源。

## 功能概览

- **MCP 服务端**：
  - 运营数据拉取、KPI 计算、洞察生成、历史分析与导出。
  - MCP 工具以 Streamable HTTP 方式暴露（默认 `/mcp`）。
- **AI Dashboard 前端**：
  - 对话查询（支持“今天/本周/上月/最近X天”等时间范围）。
  - 展示 KPI / 表格 / 图表。
  - 上传 Excel/CSV 并持久化解析结果，支持历史列表与删除。
- **一键启动**：`python run_app.py` 同时启动 MCP 与前端。

## 目录结构

```text
operations_dashboard/
|-- agent.py                  # LangGraph Agent (MCP client)
|-- call_insights_tool.py     # MCP 工具调试脚本
|-- config.py                 # 后端配置
|-- mcp_bridge.py             # MCP client bridge (stdio/streamable-http)
|-- mcp_server.py             # FastMCP server
|-- services.py               # 业务逻辑
|-- data_sources/             # 数据源（含 Mock）
|-- metrics/                  # KPI 计算
|-- reporting/                # 摘要格式化
|-- skills/                   # MCP 工具封装
|-- storage/                  # SQLite 持久化
`-- utils/                    # 工具函数

src/ai_dashboard/
|-- app/                      # Next.js app routes
|-- components/               # UI 组件
|-- lib/                      # 前端工具库
|-- package.json              # 前端依赖与脚本

run_app.py                    # 一键启动脚本
configs/ai_dashboard.json     # 前端配置
```

## 环境要求

- Python 3.10+
- Node.js 18+（Next.js 14 要求）

## 快速开始（推荐）

在仓库根目录运行：

```powershell
python run_app.py
```

它会：

- 启动 MCP 服务器（默认 `http://127.0.0.1:8000/mcp`）
- 启动前端（默认 `http://localhost:3001`）
- 端口占用时自动切换到下一个可用端口
- 自动给前端注入 `MCP_SERVER_URL` 与 `AI_DASHBOARD_CONFIG_PATH`

可选参数：

```powershell
python run_app.py --mcp-host 127.0.0.1 --mcp-port 8000 --frontend-port 3001
python run_app.py --frontend-cmd "npm run dev"
```

## 手动启动

### 1) 启动 MCP 服务端

```powershell
# stdio（默认）
python -m operations_dashboard.mcp_server

# Streamable HTTP（供前端或 Inspector 使用）
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000
```

### 2) 启动前端

```powershell
cd src/ai_dashboard
npm install
copy .env.example .env.local
npm run dev
```

默认端口为 3001，访问 `http://localhost:3001`。

## 环境变量

### MCP 服务端（Python）

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 生成洞察（LLM）所需 | 必填（否则 `generate_dashboard_insights` 会失败） |
| `OPENAI_MODEL` | LLM 模型 | `gpt-5-mini` |
| `OPENAI_TEMPERATURE` | LLM 温度 | `0` |
| `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` / `AMAZON_ASSOCIATE_TAG` / `AMAZON_MARKETPLACE` | Amazon PAAPI 凭证（用于畅销榜工具） | 空则使用 mock 凭证 |
| `STORAGE_ENABLED` | 是否持久化 KPI 摘要 | `0` |
| `STORAGE_DB_PATH` | SQLite 路径（摘要 + 上传数据） | `operations_dashboard.sqlite3` |
| `MCP_SERVER_LOG_LEVEL` | MCP 服务端日志级别 | `INFO` |

### 前端（Next.js）

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 前端直连 OpenAI（仅在前端使用时需要） | 空 |
| `MCP_SERVER_URL` | MCP 服务地址 | `http://127.0.0.1:8000/mcp` |
| `AI_DASHBOARD_CONFIG_PATH` | 前端配置文件路径 | `configs/ai_dashboard.json` |
| `AI_DASHBOARD_UPLOAD_TTL_HOURS` | 临时上传文件保留时长（小时） | `24` |
| `AI_DASHBOARD_REPORT_TTL_HOURS` | 临时报表保留时长（小时） | `168` |
| `MCP_CLIENT_TIMEOUT_MS` | MCP 普通工具超时（毫秒） | `30000` |
| `MCP_CLIENT_INSIGHTS_TIMEOUT_MS` | 洞察工具超时（毫秒） | `120000` |

### Agent / MCP Bridge（可选）

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `USE_MCP_BRIDGE` | 是否启用 MCP Bridge | `1` |
| `MCP_BRIDGE_COMMAND` / `MCP_BRIDGE_ARGS` / `MCP_BRIDGE_ENV` | MCP bridge 子进程命令、参数、环境变量 | - |
| `MCP_BRIDGE_TRANSPORT` | `stdio` / `streamable-http` | `stdio` |
| `MCP_BRIDGE_URL` | streamable-http MCP 地址 | - |
| `MCP_BRIDGE_TIMEOUT` | Bridge 请求超时 | `30` |

## MCP 工具列表

- `fetch_dashboard_data`
- `compute_dashboard_metrics`
- `generate_dashboard_insights`
- `analyze_dashboard_history`
- `export_dashboard_history`
- `amazon_bestseller_search`
- `save_upload_table`
- `get_upload_table`
- `list_upload_tables`
- `delete_upload_table`

## 数据与时间范围说明

- 默认使用 **Mock 数据源**（`operations_dashboard/data_sources/amazon_business_reports.py`）。
- 前端会根据用户输入自动决定时间窗口：
  - “今天/今日/当天” → 当日
  - “昨天/前天” → 对应单日
  - “本周/上周” → 自然周
  - “本月/上月” → 自然月
  - “最近 X 天” → 滚动窗口
- 如果没有明确时间表达，则使用 `configs/ai_dashboard.json` 里的 `mcpWindowDays` 作为默认窗口。

## 上传与持久化

- 前端上传 Excel/CSV 后：
  - **临时文件**保存在系统临时目录（有 TTL 自动清理）。
  - **解析后的表格数据**持久化到 SQLite（`STORAGE_DB_PATH`）。
- 上传历史列表与删除操作走 MCP 工具：`list_upload_tables` / `delete_upload_table`。
- 注意：上传持久化会创建 `operations_dashboard.sqlite3`（或你配置的 DB 路径）。

## 前端配置

前端配置文件：`configs/ai_dashboard.json`，包含模型、窗口天数、图表类型等。示例：

```json
{
  "model": "gpt-5-mini",
  "mcpWindowDays": 7,
  "chartType": "bar"
}
```

## MCP Inspector 调试（可选）

```powershell
# 启动 MCP 服务端（streamable-http）
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000

# 启动 Inspector
npx @modelcontextprotocol/inspector
```

连接地址：`http://127.0.0.1:8000/mcp`

## 常见问题

- **对话请求返回 502**：通常是 MCP 工具超时或 MCP 服务不可用。
  - 可调大 `MCP_CLIENT_TIMEOUT_MS` / `MCP_CLIENT_INSIGHTS_TIMEOUT_MS`。

## 测试

```powershell
# 前端单测
npm run test:unit

# 前端 E2E（需先启动 dev server）
$env:E2E_BASE_URL = "http://localhost:3001"
npm run test:e2e

# Smoke 测试
$env:SMOKE_BASE_URL = "http://localhost:3001"
npm run test:smoke
```
