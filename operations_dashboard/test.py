# operations_dashboard/test.py
import os

os.environ["USE_MCP_BRIDGE"] = "1"  # 必须在导入 agent 之前

from operations_dashboard.agent import run_agent_demo
from operations_dashboard.config import (
    AmazonCredentialConfig,
    AppConfig,
    DashboardConfig,
    StorageConfig,
)

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

    result = run_agent_demo(config, "请生成最近7天的运营日报，并给出重点洞察")
    print(result)

if __name__ == "__main__":
    main()
