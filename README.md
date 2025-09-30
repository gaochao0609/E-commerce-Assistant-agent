# Operations Dashboard MCP

基于 Model Context Protocol (MCP) 的运营仪表盘服务层，统一向外暴露资源和工具。

## 环境准备

- Python 3.10 及以上版本
- 安装依赖：`pip install -r requirements.txt`
- 若需要访问 Amazon PAAPI，请配置 `AMAZON_*` 系列环境变量

## 启动服务器

```bash
# 以 stdio 传输启动（默认行为）
python -m operations_dashboard.mcp_server

# 启动 Streamable HTTP，便于浏览器或 Inspector 连接
python -m operations_dashboard.mcp_server streamable-http --host 127.0.0.1 --port 8000
```

## 验证运行状态

1. **stdio**：启动后终端保持静默等待连接，这是预期行为。
2. **Streamable HTTP**：看到 `Uvicorn running on http://127.0.0.1:8000` 即表示监听成功。
3. **MCP Inspector**（推荐用于调试）  
   ```bash
   uv run mcp dev operations_dashboard/mcp_server.py --with-editable .
   ```
   打开浏览器中的 MCP Inspector 页面，可查看资源/工具并直接调用。
4. **脚本校验**：
   ```bash
   set MCP_SERVER_URL=http://127.0.0.1:8000/mcp
   python operations_dashboard/test.py
   ```
   控制台会输出已注册的工具名称，证明链路正常。

## 与 LangGraph Agent 协同

- 设置 `USE_MCP_BRIDGE=1` 时，`agent.py` 会通过 `mcp_bridge.py` 访问 MCP 服务。
- 桥接器默认执行 `python -m operations_dashboard.mcp_server`，可通过以下变量覆盖：
  - `MCP_BRIDGE_COMMAND`
  - `MCP_BRIDGE_ARGS`（JSON 数组）
  - `MCP_BRIDGE_ENV`（JSON 对象）
- 未启用桥接时，Agent 直接调用本地服务函数。

## 目录结构

```
operations_dashboard/
├── agent.py                 # LangGraph Agent 封装
├── config.py                # 应用配置模型
├── mcp_server.py            # FastMCP 服务器入口
├── mcp_bridge.py            # MCP HTTP 桥接工具
├── services.py              # 业务服务层
├── data_sources/            # 数据源模拟与适配
├── metrics/                 # 指标计算逻辑
├── reporting/               # 报表格式化
├── storage/                 # SQLite 仓储实现
├── utils/                   # 工具函数（日期等）
└── test.py                  # 调试脚本
```

