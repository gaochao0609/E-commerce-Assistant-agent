# call_insights_tool.py
import os
import sys
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters
import asyncio

async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "operations_dashboard.mcp_server", "stdio"],
        env={"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # 鍏堣窇涓€涓?fetch锛屽彇鍑?start/end
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
