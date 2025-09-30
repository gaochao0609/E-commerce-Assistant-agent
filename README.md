# Operations Dashboard MCP

Expose the e-commerce operations toolkit through the official Model Context Protocol (MCP) runtime.

## Prerequisites

- Python 3.10+
- Install dependencies with `pip install -r requirements.txt`
- Configure Amazon credentials through the existing `AMAZON_*` environment variables when calling PAAPI tools

## Running the MCP server

```bash
# stdio transport (default)
python -m operations_dashboard.mcp_server

# streamable HTTP transport for browser-based clients
python -m operations_dashboard.mcp_server streamable-http --host 0.0.0.0 --port 8000
```

The server registers all analytics functions as MCP tools and exposes read-only resources for configuration and stored dashboard history. Development tooling from the MCP SDK (`uv run mcp dev operations_dashboard/mcp_server.py`) also works with this module.

## Integrating with the LangGraph agent

Set `USE_MCP_BRIDGE=1` to force the agent to call tools through the MCP bridge. By default the bridge starts `python -m operations_dashboard.mcp_server` on demand. Override execution details if needed:

- `MCP_BRIDGE_COMMAND` - executable used to spawn the server (default `python`)
- `MCP_BRIDGE_ARGS` - JSON array of arguments (default `[-m, "operations_dashboard.mcp_server"]`)
- `MCP_BRIDGE_ENV` - optional JSON object of additional environment variables passed to the server process

When `USE_MCP_BRIDGE` is disabled, the agent calls the underlying services directly.

