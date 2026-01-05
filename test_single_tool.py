"""测试单个 MCP 工具调用"""

import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    print("🧪 测试 fetch_dashboard_data 工具...")
    print("=" * 60)
    
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "operations_dashboard.mcp_server", "stdio"],
        env={"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")},
    )
    
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 调用 fetch_dashboard_data 工具
            print("\n📞 调用工具: fetch_dashboard_data")
            print("参数: window_days=7")
            print("-" * 60)
            
            result = await session.call_tool(
                "fetch_dashboard_data",
                {"window_days": 7}
            )
            
            # 打印结构化结果
            if result.structuredContent:
                print("\n✅ 工具调用成功！")
                print("\n结构化结果:")
                print(json.dumps(result.structuredContent, indent=2, ensure_ascii=False))
            else:
                print("\n⚠️  工具返回了非结构化结果")
                print("内容:")
                for content in result.content:
                    print(f"  {content}")

if __name__ == "__main__":
    asyncio.run(main())
