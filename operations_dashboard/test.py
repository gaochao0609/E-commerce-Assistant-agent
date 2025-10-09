# operations_dashboard/test.py
import asyncio
import os

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as exc:
    raise RuntimeError("未找到 mcp 客户端，请先执行 pip install -r requirements.txt") from exc

# Ensure the agent routes tool calls through the MCP bridge before importing it.
os.environ["USE_MCP_BRIDGE"] = "1"

from operations_dashboard.agent import run_agent_demo
from operations_dashboard.config import (
    AmazonCredentialConfig,
    AppConfig,
    DashboardConfig,
    StorageConfig,
)


def _verify_streamable_http(server_url: str) -> None:
    """Connect via streamable HTTP and list available tools to confirm the MCP server."""

    async def _probe() -> None:
        async with streamablehttp_client(server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"Discovered tools: {[tool.name for tool in tools.tools]}")

    try:
        asyncio.run(_probe())
    except Exception as exc:  # pragma: no cover - manual diagnostics helper
        raise RuntimeError(f"Failed to reach MCP server at {server_url}: {exc}") from exc


def main() -> None:
    config = AppConfig(
        amazon=AmazonCredentialConfig(
            access_key="mock",
            secret_key="mock",
            associate_tag=None,
            marketplace="US",
        ),
        dashboard=DashboardConfig(
            marketplace="US",
            refresh_window_days=7,
            top_n_products=5,
        ),
        storage=StorageConfig(enabled=False),
    )

    result = run_agent_demo(config, "Generate the latest daily operations report with key insights.")
    print(result)

    server_url = os.getenv("MCP_SERVER_URL")
    if server_url:
        _verify_streamable_http(server_url)


if __name__ == "__main__":
    main()


