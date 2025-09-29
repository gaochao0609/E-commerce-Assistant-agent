"""基于 LangGraph 的运营日报工作流，支持 MCP 桥接与畅销榜查询。"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .config import AppConfig
from .mcp_bridge import call_mcp_tool
from .services import (
    ServiceContext,
    analyze_dashboard_history,
    amazon_bestseller_search,
    compute_dashboard_metrics,
    create_service_context,
    export_dashboard_history,
    fetch_dashboard_data,
    generate_dashboard_insights,
)
from .storage.repository import SQLiteRepository

USE_MCP_BRIDGE = os.getenv("USE_MCP_BRIDGE", "0").lower() in {"1", "true", "yes"}
logger = logging.getLogger(__name__)


def _call_mcp_bridge(tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
    if not USE_MCP_BRIDGE:
        return None
    try:
        logger.debug("调用 MCP 工具 %s，参数：%s", tool_name, args)
        return call_mcp_tool(tool_name, args)
    except Exception as exc:  # pragma: no cover
        logger.warning("MCP 工具 %s 调用失败：%s", tool_name, exc)
        return None


def build_operations_agent(
    config: AppConfig,
    *,
    context: Optional[ServiceContext] = None,
    repository: Optional[SQLiteRepository] = None,
) -> tuple:
    if context is None:
        llm_for_services = ChatOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model="gpt-3.5-turbo",
            temperature=0,
        ) if os.getenv("OPENAI_API_KEY") else None
        repository = repository or (SQLiteRepository(config.storage.db_path) if config.storage.enabled else None)
        context = create_service_context(config, repository=repository, llm=llm_for_services)
    llm = ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-3.5-turbo",
        temperature=0,
    )

    @tool("fetch_dashboard_data")
    def fetch_dashboard_data_tool(
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "fetch_dashboard_data",
            {
                "start": start,
                "end": end,
                "window_days": window_days,
                "top_n": top_n,
            },
        )
        if isinstance(remote, dict):
            return remote
        return fetch_dashboard_data(
            context,
            start=start,
            end=end,
            window_days=window_days,
            top_n=top_n,
        )

    @tool("compute_dashboard_metrics")
    def compute_dashboard_metrics_tool(
        start: str,
        end: str,
        source: str,
        sales: List[Dict[str, Any]],
        traffic: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "compute_dashboard_metrics",
            {
                "start": start,
                "end": end,
                "source": source,
                "sales": sales,
                "traffic": traffic,
                "top_n": top_n,
            },
        )
        if isinstance(remote, dict):
            return remote
        return compute_dashboard_metrics(
            context,
            start=start,
            end=end,
            source=source,
            sales=sales,
            traffic=traffic,
            top_n=top_n,
        )

    @tool("generate_dashboard_insights")
    def generate_dashboard_insights_tool(
        summary: Dict[str, Any],
        focus: Optional[str] = None,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "generate_dashboard_insights",
            {"summary": summary, "focus": focus},
        )
        if isinstance(remote, dict):
            return remote
        return generate_dashboard_insights(context, summary=summary, focus=focus)

    @tool("analyze_dashboard_history")
    def analyze_dashboard_history_tool(
        limit: int = 6,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "analyze_dashboard_history",
            {"limit": limit, "metrics": metrics},
        )
        if isinstance(remote, dict):
            return remote
        return analyze_dashboard_history(context, limit=limit, metrics=metrics)

    @tool("export_dashboard_history")
    def export_dashboard_history_tool(
        limit: int,
        path: str,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "export_dashboard_history",
            {"limit": limit, "path": path},
        )
        if isinstance(remote, dict):
            return remote
        return export_dashboard_history(context, limit=limit, path=path)

    @tool("amazon_bestseller_search")
    def amazon_bestseller_search_tool(
        category: str,
        search_index: str,
        browse_node_id: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        remote = _call_mcp_bridge(
            "amazon_bestseller_search",
            {
                "category": category,
                "search_index": search_index,
                "browse_node_id": browse_node_id,
                "max_items": max_items,
            },
        )
        if isinstance(remote, dict):
            return remote
        return amazon_bestseller_search(
            context,
            category=category,
            search_index=search_index,
            browse_node_id=browse_node_id,
            max_items=max_items,
        )

    tools = [
        fetch_dashboard_data_tool,
        compute_dashboard_metrics_tool,
        generate_dashboard_insights_tool,
        analyze_dashboard_history_tool,
        export_dashboard_history_tool,
        amazon_bestseller_search_tool,
    ]
    graph = create_react_agent(llm, tools=tools)
    return graph, tools


def run_agent_demo(config: AppConfig, query: str) -> Dict[str, Any]:
    repository = None
    if config.storage.enabled:
        repository = SQLiteRepository(config.storage.db_path)
    graph, _ = build_operations_agent(config, repository=repository)
    result = graph.invoke(
        {
            "messages": [
                SystemMessage(
                    content=(
                        "请按照“数据获取→指标计算→洞察总结→历史分析（可选）→导出（可选）→畅销榜查询（可选）"
                        "的顺序调用工具，最终输出结构化运营日报。"
                    )
                ),
                HumanMessage(content=query),
            ]
        }
    )
    return result
