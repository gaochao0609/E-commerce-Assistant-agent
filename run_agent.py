"""简单的 Agent 运行脚本示例"""

from operations_dashboard.agent import run_agent_demo
from operations_dashboard.config import (
    AppConfig,
    AmazonCredentialConfig,
    DashboardConfig,
    StorageConfig,
)

if __name__ == "__main__":
    # 创建配置（使用 Mock 数据，不需要真实凭证）
    config = AppConfig(
        amazon=AmazonCredentialConfig(access_key="mock", secret_key="mock"),
        dashboard=DashboardConfig(),
        storage=StorageConfig(),
    )

    # 运行 Agent
    print("🚀 启动 Agent，生成运营日报...")
    print("=" * 60)
    
    result = run_agent_demo(
        config,
        "生成最近7天的运营日报，包括关键指标和Top商品分析"
    )
    
    print("\n" + "=" * 60)
    print("✅ Agent 执行完成")
    print("=" * 60)
    
    # 打印最后一条消息（Agent 的回复）
    if result.get("messages"):
        last_message = result["messages"][-1]
        print("\n📊 Agent 回复：")
        print("-" * 60)
        print(last_message.content)
        print("-" * 60)
    
    # 打印工具调用历史（可选）
    print("\n🔧 工具调用历史：")
    for msg in result.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                print(f"  - {tool_call.get('name', 'unknown')}")
