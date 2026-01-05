"""围绕运营仪表盘场景的具体 Skill 实现。

这些 Skill 主要是对 ``services`` 层的业务逻辑进行二次封装，使其：
- 以统一的 Skill 接口暴露给 Agent / MCP；
- 更便于后续在不同 Agent 容器中复用和组合。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import Skill
from ..services import (
    ServiceContext,
    analyze_dashboard_history,
    amazon_bestseller_search,
    compute_dashboard_metrics,
    export_dashboard_history,
    fetch_dashboard_data,
    generate_dashboard_insights,
)


@dataclass
class _ContextBoundSkill(Skill):
    """带有 ServiceContext 依赖的技能基类。"""

    context: ServiceContext


@dataclass
class FetchDashboardDataSkill(_ContextBoundSkill):
    """拉取指定时间窗口内的销售与流量原始数据。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="fetch_dashboard_data",
            description="拉取指定时间窗口内的运营原始数据（销量与流量）。",
            context=context,
        )

    def invoke(
        self,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        return fetch_dashboard_data(
            self.context,
            start=start,
            end=end,
            window_days=window_days,
            top_n=top_n,
        )


@dataclass
class ComputeDashboardMetricsSkill(_ContextBoundSkill):
    """基于原始数据计算 KPI 与 Top 商品指标。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="compute_dashboard_metrics",
            description="基于销量与流量数据计算 KPI 指标与 Top 商品表现。",
            context=context,
        )

    def invoke(
        self,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
        source: Optional[str] = None,
        sales: Optional[List[Dict[str, Any]]] = None,
        traffic: Optional[List[Dict[str, Any]]] = None,
        top_n: Optional[int] = None,
        window_days: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        # 若未提供 sales / traffic，则自动调用取数技能补齐，再计算指标。
        working_sales = sales
        working_traffic = traffic
        effective_start = start
        effective_end = end
        effective_source = source or self.context.config.dashboard.marketplace

        if (effective_start is None or effective_end is None) and (
            sales is not None and traffic is not None
        ):
            raise RuntimeError("compute_dashboard_metrics 需要 start/end 或缺省以触发自动取数。")

        if working_sales is None or working_traffic is None:
            data = fetch_dashboard_data(
                self.context,
                start=start or None,
                end=end or None,
                window_days=window_days,
                top_n=top_n,
            )
            working_sales = data.get("sales", [])
            working_traffic = data.get("traffic", [])
            effective_start = data.get("start") or effective_start
            effective_end = data.get("end") or effective_end
            effective_source = data.get("source") or effective_source

        if working_sales is None or working_traffic is None:
            raise RuntimeError("compute_dashboard_metrics 需要销售和流量数据，当前参数不完整。")
        if effective_start is None or effective_end is None:
            raise RuntimeError("compute_dashboard_metrics 缺少 start/end，无法计算指标。")

        return compute_dashboard_metrics(
            self.context,
            start=effective_start,
            end=effective_end,
            source=effective_source,
            sales=working_sales,
            traffic=working_traffic,
            top_n=top_n,
        )


@dataclass
class GenerateDashboardInsightsSkill(_ContextBoundSkill):
    """基于 KPI 摘要调用 LLM 生成结构化洞察。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="generate_dashboard_insights",
            description="基于运营 KPI 摘要调用 LLM 生成运营洞察报告。",
            context=context,
        )

    def invoke(
        self,
        *,
        summary: Optional[Dict[str, Any]] = None,
        focus: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        return generate_dashboard_insights(
            self.context,
            summary=summary,
            focus=focus,
            start=start,
            end=end,
            window_days=window_days,
            top_n=top_n,
        )


@dataclass
class AnalyzeDashboardHistorySkill(_ContextBoundSkill):
    """分析历史汇总记录，计算趋势与环比同比。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="analyze_dashboard_history",
            description="基于历史汇总记录计算趋势、环比和同比指标。",
            context=context,
        )

    def invoke(
        self,
        *,
        limit: int = 6,
        metrics: Optional[List[str]] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        return analyze_dashboard_history(
            self.context,
            limit=limit,
            metrics=metrics,
        )


@dataclass
class ExportDashboardHistorySkill(_ContextBoundSkill):
    """将历史汇总数据导出为 CSV 文件。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="export_dashboard_history",
            description="导出最近 N 期运营摘要到受信任目录下的 CSV 文件。",
            context=context,
        )

    def invoke(
        self,
        *,
        limit: int,
        path: str,
        **_: Any,
    ) -> Dict[str, Any]:
        return export_dashboard_history(
            self.context,
            limit=limit,
            path=path,
        )


@dataclass
class AmazonBestsellerSearchSkill(_ContextBoundSkill):
    """查询 Amazon PAAPI 畅销榜单。"""

    def __init__(self, context: ServiceContext) -> None:
        super().__init__(
            name="amazon_bestseller_search",
            description="调用 Amazon PAAPI 查询指定类目的畅销商品榜单。",
            context=context,
        )

    def invoke(
        self,
        *,
        category: str,
        search_index: str,
        browse_node_id: Optional[str] = None,
        max_items: Optional[int] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        return amazon_bestseller_search(
            self.context,
            category=category,
            search_index=search_index,
            browse_node_id=browse_node_id,
            max_items=max_items,
        )


def build_dashboard_skills(context: ServiceContext) -> List[Skill]:
    """基于给定的 ``ServiceContext`` 构建本项目所有核心技能列表。"""
    return [
        FetchDashboardDataSkill(context),
        ComputeDashboardMetricsSkill(context),
        GenerateDashboardInsightsSkill(context),
        AnalyzeDashboardHistorySkill(context),
        ExportDashboardHistorySkill(context),
        AmazonBestsellerSearchSkill(context),
    ]

