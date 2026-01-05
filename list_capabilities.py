"""列出 MCP 服务器提供的所有能力（工具、资源、提示模板）"""

import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    print("🔍 连接 MCP 服务器，获取可用能力...")
    print("=" * 60)
    
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "operations_dashboard.mcp_server", "stdio"],
    )
    
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 列出所有工具
            tools = await session.list_tools()
            print(f"\n📦 可用工具 ({len(tools.tools)} 个):")
            print("-" * 60)
            for tool in tools.tools:
                print(f"  • {tool.name}")
                if tool.description:
                    print(f"    {tool.description}")
                print()
            
            # 列出所有资源
            resources = await session.list_resources()
            print(f"\n📚 可用资源 ({len(resources.resources)} 个):")
            print("-" * 60)
            for resource in resources.resources:
                print(f"  • {resource.uri}")
                if resource.name:
                    print(f"    名称: {resource.name}")
                if resource.description:
                    print(f"    说明: {resource.description}")
                print()
            
            # 列出所有提示模板
            prompts = await session.list_prompts()
            print(f"\n💡 可用提示模板 ({len(prompts.prompts)} 个):")
            print("-" * 60)
            for prompt in prompts.prompts:
                print(f"  • {prompt.name}")
                if prompt.description:
                    print(f"    {prompt.description}")
                if prompt.arguments:
                    print(f"    参数: {', '.join([arg.name for arg in prompt.arguments])}")
                print()

if __name__ == "__main__":
    asyncio.run(main())
