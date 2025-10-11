# Operations Dashboard MCP

面向 Amazon 运营分析场景的 Model Context Protocol (MCP) 服务端与 LangGraph Agent 示例。项目提供统一的数据资源和工具接口，既可作为 MCP 服务对外暴露，也便于本地联调和自动化测试。

## 环境准备

1. 安装 Python 3.10 及以上版本。
2. 建议创建并激活虚拟环境：
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
3. 若此前安装过旧版 LangChain 组件，请执行：
    python -m pip install --upgrade langchain langchain-openai
   以确保 GPT-5 接口兼容，避免 TaskGroup 聚合异常。
4. 可选环境变量：

| 变量 | 说明 |
| --- | --- |
| OPENAI_API_KEY | 用于生成运营洞察的 OpenAI 密钥；未配置时仅返回占位文字。 |
| AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY / AMAZON_ASSOCIATE_TAG / AMAZON_MARKETPLACE | Amazon PAAPI 凭证， amazon_bestseller_search 工具依赖。 |

## 运行 MCP 服务

    # stdio 传输（默认）
    python -m operations_dashboard.mcp_server

    # Streamable HTTP 传输（适配 MCP Inspector 等客户端）
    python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000

可选环境变量：
- USE_MCP_BRIDGE：设为 1/true/yes 时，LangGraph Agent 会通过 MCP 桥访问远端工具。
- MCP_BRIDGE_COMMAND / MCP_BRIDGE_ARGS / MCP_BRIDGE_ENV：自定义 MCP 子进程的启动命令、参数与环境变量。

## 自检与调试脚本

- python operations_dashboard/test.py：串行验证 stdio 通路、工具调用、LangGraph Agent 回路及临时 HTTP 监听。
- python operations_dashboard/call_insights_tool.py：通过 MCP 调用 fetch_dashboard_data 与 generate_dashboard_insights，并打印结构化返回以便排查。
- python operations_dashboard/verify_openai_key.py：快速校验 OPENAI_API_KEY 是否可用（受限网络可能需要代理）。

> 如果仅需验证 stdio/工具，可临时注释 	est.py 末尾的 HTTP 检查段。

## LangGraph Agent 协同

- agent.py 构建了 LangGraph 的运营顾问 Agent，可作为脚本调用，也可通过 MCP 桥转发到远端工具。
- MCP 桥默认执行 python -m operations_dashboard.mcp_server；如需自定义命令或环境，请调整 MCP_BRIDGE_COMMAND、MCP_BRIDGE_ARGS、MCP_BRIDGE_ENV。
- 当 USE_MCP_BRIDGE 关闭时，Agent 直接调用本地服务实现。

## 目录结构

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

## 常见问题

1. **generate_dashboard_insights 提示缺少 OPENAI_API_KEY**：在当前终端执行 echo （PowerShell）或 python -c "import os; print(os.getenv('OPENAI_API_KEY'))" 检查变量；若使用 MCP 桥，请确保 MCP_BRIDGE_ENV 也携带该变量。
2. **generate_dashboard_insights 抛出 “unhandled errors in a TaskGroup”**：升级 LangChain 组件，执行 python -m pip install --upgrade langchain langchain-openai。
3. **amazon_bestseller_search 提示缺少凭证**：补全 Amazon PAAPI 凭证；如暂不使用，可忽略告警。
4. **HTTP 联通性检查超时**：确认已安装 uvicorn、端口未被占用，必要时更换端口（如 --port 8765）。

## 版本提示

- 自 2024 年 12 月起，调用 GPT-5 模型需满足 langchain>=0.3.12 与 langchain-openai>=0.3.3，否则会出现 TaskGroup 聚合异常。

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logoColor=ffffff)](https://zread.ai/gaochao0609/E-commerce-Assistant-agent)
