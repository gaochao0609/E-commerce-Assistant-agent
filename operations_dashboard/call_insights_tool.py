# call_insights_tool.py
import os
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters
import asyncio

async def main() -> None:
    params = StdioServerParameters(
        command="python",
        args=["-m", "operations_dashboard.mcp_server", "stdio"],
        env=None,  # 传递当前 shell 的环境变量
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # 先跑一下 fetch，取出 start/end
            data = await session.call_tool("fetch_dashboard_data", {"window_days": 7})
            print("fetch result structured:", data.structuredContent)
            payload = {
                "start": data.structuredContent["start"],
                "end": data.structuredContent["end"],
                "window_days": 7,
            }
            insights = await session.call_tool("generate_dashboard_insights", payload)
            print("insights structured:", insights.structuredContent)
            print("insights content:", [c.__dict__ for c in insights.content])

if __name__ == "__main__":
    asyncio.run(main())
