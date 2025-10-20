# Operations Dashboard MCP

Operations Dashboard MCP 利用 Model Context Protocol (MCP) 和 LangGraph Agent，为亚马逊运营场景提供统一的数据资源、指标计算与洞察分析工具。项目既可以作为独立的 FastMCP 服务器运行，也可以与本地 LangGraph Agent 协同工作。

## 功能特性

- **FastMCP 服务器**：暴露配置、历史摘要等资源，并提供多种工具（数据拉取、指标计算、洞察生成、历史导出、亚马逊畅销榜查询等）。
- **LangGraph Agent 集成**：支持通过 `mcp_bridge` 在本地或远程环境中调用 MCP 工具，便于嵌入到现有工作流。
- **Mock 数据与持久化**：内置模拟数据源，并可选用 SQLite 存储指标摘要，方便快速演示和测试。
- **易于扩展**：模块化的 `services`、`metrics`、`reporting`、`storage` 设计，便于替换或新增业务逻辑。

## 环境准备

1. 安装 **Python 3.10** 或更高版本。
2. 创建虚拟环境（任选其一）：
   ```powershell
   # 基于 venv
   python -m venv .venv
   .\.venv\Scripts\activate

   # 或者使用 conda
   conda create -n BestSellers_env python=3.10
   conda activate BestSellers_env
   ```
3. 安装依赖：
   ```powershell
   pip install -r requirements.txt
   # 建议使用最新版 LangChain 组件
   python -m pip install --upgrade langchain langchain-openai
   ```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | `generate_dashboard_insights` 工具使用的 OpenAI 密钥。 |
| `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` / `AMAZON_ASSOCIATE_TAG` / `AMAZON_MARKETPLACE` | 使用 `amazon_bestseller_search` 时需要的 Amazon PAAPI 凭证。 |
| `USE_MCP_BRIDGE` | 设为 `1`/`true`/`yes` 时，LangGraph Agent 会通过 MCP 桥接远程服务器。 |
| `MCP_BRIDGE_COMMAND` / `MCP_BRIDGE_ARGS` / `MCP_BRIDGE_ENV` | 自定义 MCP 桥接子进程的命令、参数与环境变量。 |

> 若通过 MCP Inspector 等客户端连接，请确保所需变量在启动服务器的终端会话中已正确导出。

## 启动 MCP 服务器

```powershell
# stdio 传输（默认）
python -m operations_dashboard.mcp_server

# Streamable HTTP 传输（适配 MCP Inspector 等客户端）
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000
```

日志默认输出到控制台，可通过 `MCP_SERVER_LOG_LEVEL` 环境变量调整日志级别。

## 使用 MCP Inspector 进行调试

1. 在终端 A 中启动 Streamable HTTP 服务器（见上一节），确保监听地址与端口与 Inspector 设置一致。
2. 在终端 B 中启动 Inspector（任选其一）：
   ```powershell
   # 使用官方 Node 版本
   npx @modelcontextprotocol/inspector

   # 如果已安装 mcp CLI
   mcp inspector
   ```
3. 打开浏览器中的 Inspector 页面，填写连接信息：
   - **Server URL**：`http://127.0.0.1:8000/mcp`
   - **Proxy Token**：保持为空，除非你在部署时自定义了令牌。
4. 点击 **Connect**。若需要额外依赖，Inspector 会读取 `operations_dashboard/mcp_server.py` 中的 `mcp.dependencies` 列表并提示自动安装。
5. 连接成功后，可在左侧面板快速调用资源与工具，实时查看请求与响应。

> 若出现 405 或 CORS 相关报错，请确认服务器仍在运行，且浏览器访问的 URL 与 `--host`/`--port` 参数一致。项目已内置 CORS 支持，通常只需刷新页面重新连接即可。

## 常用脚本

- `python operations_dashboard/test.py`：快速验证 stdio 管道与 LangGraph Agent 的基础流程。
- `python operations_dashboard/call_insights_tool.py`：在命令行中依次调用 `fetch_dashboard_data` 与 `generate_dashboard_insights`，用于结构化联调。
- `python operations_dashboard/verify_amazon_keys.py`：检查 Amazon PAAPI 凭证是否配置正确。

## LangGraph Agent 协同

- `agent.py` 定义了 LangGraph 的运营分析 Agent，可作为脚本运行，也可以通过 MCP 桥接到远程。
- MCP 模式下默认执行 `python -m operations_dashboard.mcp_server`，可用 `MCP_BRIDGE_COMMAND`/`MCP_BRIDGE_ARGS`/`MCP_BRIDGE_ENV` 覆盖。
- 当 `USE_MCP_BRIDGE` 关闭时，Agent 将直接调用本地实现，无需 MCP。

## 目录结构

```
operations_dashboard/
├── agent.py                  # LangGraph Agent 入口
├── call_insights_tool.py     # MCP 工具调试脚本
├── config.py                 # 应用配置
├── mcp_bridge.py             # MCP stdio 客户端封装
├── mcp_server.py             # FastMCP 服务器
├── services.py               # 业务逻辑与工具实现
├── test.py                   # 集成测试脚本
├── verify_amazon_keys.py     # Amazon 凭证检测
├── data_sources/             # 数据源定义与 Mock 实现
├── metrics/                  # 指标计算逻辑
├── reporting/                # 报告格式化
├── storage/                  # SQLite 持久化实现
└── utils/                    # 通用工具函数
```

## 常见问题

1. **`generate_dashboard_insights` 报错缺少 `OPENAI_API_KEY`**  
   在服务器或桥接子进程的终端中执行 `python -c "import os; print(os.getenv('OPENAI_API_KEY'))"` 验证变量是否生效；若通过 MCP 桥接，请同步配置 `MCP_BRIDGE_ENV`。
2. **`generate_dashboard_insights` 报 `unhandled errors in a TaskGroup`**  
   升级 LangChain 相关组件：`python -m pip install --upgrade langchain langchain-openai`。
3. **`amazon_bestseller_search` 提示缺少凭证**  
   运行前填充 Amazon PAAPI 凭证或根据需求屏蔽该工具。
4. **Streamable HTTP 连接超时或 405**  
   检查 `uvicorn` 是否安装、端口是否占用，以及 Inspector 访问的 URL 是否正确。

## 版本兼容性

- 截至 2024 年 12 月测试通过的组合：`python>=3.10`、`langchain>=0.3.12`、`langchain-openai>=0.3.3`、`langgraph>=0.2.39`、`mcp>=1.15.0`。
- 近期 GPT-5 系列模型默认启用 TaskGroup 并行能力，如遇兼容性问题请关注上述版本更新。

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logoColor=ffffff)](https://zread.ai/gaochao0609/E-commerce-Assistant-agent)
