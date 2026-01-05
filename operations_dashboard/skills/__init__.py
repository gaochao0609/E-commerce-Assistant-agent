"""Skill 抽象与具体技能实现的统一入口。

当前项目将所有对外暴露的“能力”（如取数、算指标、生成洞察、历史分析、
导出 CSV、畅销榜查询等）抽象为 Skill，便于：

- 在 LangGraph / LangChain / MCP 等不同 Agent 容器之间复用；
- 为后续扩展新的编排方式（多 Agent 协作、技能路由等）提供统一接口。
"""

from .base import Skill
from .dashboard import (
    FetchDashboardDataSkill,
    ComputeDashboardMetricsSkill,
    GenerateDashboardInsightsSkill,
    AnalyzeDashboardHistorySkill,
    ExportDashboardHistorySkill,
    AmazonBestsellerSearchSkill,
    build_dashboard_skills,
)

__all__ = [
    "Skill",
    "FetchDashboardDataSkill",
    "ComputeDashboardMetricsSkill",
    "GenerateDashboardInsightsSkill",
    "AnalyzeDashboardHistorySkill",
    "ExportDashboardHistorySkill",
    "AmazonBestsellerSearchSkill",
    "build_dashboard_skills",
]

