# Operations Dashboard MCP

面向 Amazon 运营分析场景的 Model Context Protocol (MCP) 服务端与 LangGraph Agent 示例。项目提供统一的资源、工具接口，可作为 MCP 服务对外暴露，也支持本地脚本联调与验证。

## 环境准备

- Python 3.10 及以上版本
- 推荐创建虚拟环境并激活：
  ```bash
  python -m venv .venv
  .\.venv\Scripts\activate               # Windows PowerShell
  pip install -r requirements.txt
  ```
- 可选外部凭证：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 用于生成运营洞察的 OpenAI 密钥。缺失时会返回占位文字。 |
| `AMAZON_ACCESS_KEY` / `AMAZON_SECRET_KEY` / `AMAZON_ASSOCIATE_TAG` / `AMAZON_MARKETPLACE` | Amazon PAAPI 凭证，`amazon_bestseller_search` 工具依赖。缺失时会提示未配置。 |

## 运行 MCP 服务器

```bash
# stdio 传输（默认模式）
python -m operations_dashboard.mcp_server

# Streamable HTTP 传输（便于 MCP Inspector 等客户端）
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000
```

可选环境变量：

- `USE_MCP_BRIDGE`：设为 `1/true/yes` 时，LangGraph Agent 会通过 MCP 桥访问远程工具。
- `MCP_BRIDGE_COMMAND` / `MCP_BRIDGE_ARGS` / `MCP_BRIDGE_ENV`：自定义 MCP 子进程的启动方式与环境变量，脚本默认已合并系统环境，避免覆盖 `OPENAI_API_KEY` 等配置。

## 自检与调试

| 脚本 | 说明 |
| --- | --- |
| `python operations_dashboard/test.py` | 串行验证 stdio 通路、工具调用、LangGraph Agent 回路以及 HTTP 监听（最后一步会尝试临时拉起 HTTP 服务器）。 |
| `python operations_dashboard/call_insights_tool.py` | 最小化脚本，直接通过 MCP 调用 `fetch_dashboard_data` → `generate_dashboard_insights`，便于查看结构化返回和错误信息。 |
| `python operations_dashboard/verify_openai_key.py` | 检查 `OPENAI_API_KEY` 是否可用。网络受限环境可能需要代理。 |

> 若仅关注 stdio/工具验证，可临时注释 `test.py` 末尾的 HTTP 检查段，以避免等待临时 HTTP 服务器启动。

## LangGraph Agent 协同

- `agent.py` 构建了一个基于 LangGraph 的运营顾问 Agent，可直接调用，也可通过 MCP 桥转发到远端工具。
- MCP 桥默认执行 `python -m operations_dashboard.mcp_server`。如需定制命令、参数或环境变量，可调整 `MCP_BRIDGE_COMMAND`、`MCP_BRIDGE_ARGS` 与 `MCP_BRIDGE_ENV`。
- 当 `USE_MCP_BRIDGE` 关闭时，Agent 会直接调用本地服务实现。

## 目录结构

```
operations_dashboard/
├── agent.py                 # LangGraph Agent 定义
├── call_insights_tool.py    # MCP 工具调试脚本
├── config.py                # 应用配置模型
├── mcp_bridge.py            # MCP 桥（stdio 客户端封装）
├── mcp_server.py            # FastMCP 服务端入口
├── services.py              # 业务服务与工具实现
├── test.py                  # 集成自检脚本
├── verify_openai_key.py     # OpenAI Key 快速验证
├── data_sources/            # 数据源接口及 Mock 实现
├── metrics/                 # 指标计算逻辑
├── reporting/               # 报表格式化工具
├── storage/                 # SQLite 仓储实现
└── utils/                   # 通用工具函数
```

## 常见问题

1. **`generate_dashboard_insights` 提示缺少 `OPENAI_API_KEY`**  
   在启动 MCP 服务器或执行脚本的终端中检查 `echo $env:OPENAI_API_KEY`（PowerShell）或 `python -c "import os; print(os.getenv('OPENAI_API_KEY'))"`。如使用 MCP 桥，请确认 `MCP_BRIDGE_ENV` 中也包含该变量。

2. **`amazon_bestseller_search` 提示未配置凭证**  
   填写 Amazon PAAPI 相关变量，或在未使用该工具时忽略告警。

3. **HTTP 联通性检查超时**  
   确认安装了 `uvicorn`，端口未被占用，必要时更换端口（例如 `--port 8765`）。

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/gaochao0609/E-commerce-Assistant-agent)
