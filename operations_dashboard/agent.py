"""基于 LangGraph 的运营日报智能体，封装工具调用链路并可通过 MCP 桥接远程服务。"""

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
# 标记是否通过 HTTP MCP 桥调用远端工具；默认仅使用本地实现。
logger = logging.getLogger(__name__)


def _call_mcp_bridge(tool_name: str, args: Dict[str, Any]) -> Optional[Any]:
    """
    功能说明:
        当环境变量开启桥接模式时，通过 HTTP 与 MCP 服务通信获取工具结果。
    参数:
        tool_name (str): 预期在 MCP 侧注册的工具名称。
        args (Dict[str, Any]): 发送给 MCP 工具的参数字典，需保证可序列化。
    返回:
        Optional[Any]: returns the remote result when bridging is enabled; returns `None` when bridging is disabled.
    """
    # 1. 若桥接未启用则直接跳过，保持调用方逻辑简洁。
    if not USE_MCP_BRIDGE:
        return None
    try:
        logger.debug("调用 MCP 工具 %s，参数：%s", tool_name, args)
        # 2. 实际触发 HTTP 请求并返回远端结果。
        return call_mcp_tool(tool_name, args)
    except Exception as exc:  # pragma: no cover
        logger.error("MCP 工具 %s 调用失败：%s", tool_name, exc)
        raise RuntimeError(f"MCP tool '{tool_name}' failed") from exc


def build_operations_agent(
    config: AppConfig,
    *,
    context: Optional[ServiceContext] = None,
    repository: Optional[SQLiteRepository] = None,
) -> tuple:
    """
    功能说明:
        构建具备运营分析能力的 LangGraph Agent，并注册所有领域工具。
    参数:
        config (AppConfig): 包含仪表盘刷新窗口、存储、凭证等全局配置。
        context (Optional[ServiceContext]): 预构建的服务上下文，可避免重复初始化。
        repository (Optional[SQLiteRepository]): 外部注入的存储仓库实例，便于复用连接。
    返回:
        tuple: `(graph, tools)`，其中 `graph` 为已组装好的智能体，`tools` 为工具列表。
    """
    # 1. 构建默认服务上下文，包含数据源、存储以及可选的 LLM。
    if context is None:
        llm_for_services = (
            ChatOpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                model="gpt-5-mini",
                temperature=0,
            )
            if os.getenv("OPENAI_API_KEY")
            else None
        )
        repository = repository or (
            SQLiteRepository(config.storage.db_path) if config.storage.enabled else None
        )
        context = create_service_context(config, repository=repository, llm=llm_for_services)
    # 2. 构建 Agent 主体使用的对话模型（与服务内部模型可不同）。
    llm = ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-5-mini",
        temperature=0,
    )

    @tool("fetch_dashboard_data")
    def fetch_dashboard_data_tool(
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        函数说明:
            调用服务层拉取指定时间窗口内的销售和流量原始数据。
        参数:
            start (Optional[str]): ISO 8601 起始时间，默认使用配置中的最近窗口。
            end (Optional[str]): ISO 8601 结束时间，缺省时根据 `start` 推导。
            window_days (Optional[int]): 当未提供时间范围时使用的天数跨度。
            top_n (Optional[int]): 仅返回排名前 N 的商品记录。
        返回:
            Dict[str, Any]: 包含销售、流量及衍生字段的原始数据载荷。
        """
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge(
                "fetch_dashboard_data",
                {
                    "start": start,
                    "end": end,
                    "window_days": window_days,
                    "top_n": top_n,
                },
            )
            if not isinstance(remote, dict):
                raise RuntimeError(
                    "fetch_dashboard_data via MCP returned an invalid payload"
                )
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
        sales: Optional[List[Dict[str, Any]]] = None,
        traffic: Optional[List[Dict[str, Any]]] = None,
        top_n: Optional[int] = None,
        window_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        函数说明:
            基于销售与流量数据计算 KPI，可复用 `fetch_dashboard_data` 的输出。
        参数:
            start (str): 统计区间起始时间（ISO 8601）。
            end (str): 统计区间结束时间（ISO 8601）。
            source (str): 数据来源标识，例如 `amazon_paapi`。
            sales (Optional[List[Dict[str, Any]]]): 可选的销售数据数组，缺省时由服务层补全。
            traffic (Optional[List[Dict[str, Any]]]): 可选的流量数据数组，缺省时由服务层补全。
            top_n (Optional[int]): 指定仅保留排名前 N 的指标。
            window_days (Optional[int]): 仅提供起止时间之一时使用的默认跨度。
        返回:
            Dict[str, Any]: 计算后的指标摘要与中间数据。
        """
        data: Dict[str, Any] | None = None
        if sales is None or traffic is None:
            fetch_args: Dict[str, Any] = {
                "start": start or None,
                "end": end or None,
                "window_days": window_days,
                "top_n": top_n,
            }
            fetch_args = {k: v for k, v in fetch_args.items() if v not in (None, "")}
            if USE_MCP_BRIDGE:
                remote_fetch = _call_mcp_bridge("fetch_dashboard_data", fetch_args)
                if not isinstance(remote_fetch, dict):
                    raise RuntimeError("fetch_dashboard_data via MCP returned an invalid payload")
                data = remote_fetch
            else:
                data = fetch_dashboard_data(
                    context,
                    start=start,
                    end=end,
                    window_days=window_days,
                    top_n=top_n,
                )
            sales = data.get("sales") if data else sales
            traffic = data.get("traffic") if data else traffic
            start = (data.get("start") if data else None) or start
            end = (data.get("end") if data else None) or end
            source = (data.get("source") if data else None) or source or context.config.dashboard.marketplace
            if sales is None or traffic is None:
                raise RuntimeError("compute_dashboard_metrics 需要销售或流量数据，无法继续计算")

        payload = {
            "start": start,
            "end": end,
            "source": source,
            "sales": sales,
            "traffic": traffic,
            "top_n": top_n,
        }
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge("compute_dashboard_metrics", payload)
            if not isinstance(remote, dict):
                raise RuntimeError("compute_dashboard_metrics via MCP returned an invalid payload")
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
        summary: Optional[Dict[str, Any]] = None,
        focus: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        window_days: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        函数说明:
            根据指标摘要生成洞见报告，可在缺省时自动拉取并计算指标。
        参数:
            summary (Optional[Dict[str, Any]]): 已计算好的指标摘要。
            focus (Optional[str]): 洞见关注的重点，例如 `sales`。
            start (Optional[str]): 指定自动取数的起始时间。
            end (Optional[str]): 指定自动取数的结束时间。
            window_days (Optional[int]): 自动取数时的窗口跨度。
            top_n (Optional[int]): 需要分析的排行榜 Top N。
        返回:
            Dict[str, Any]: 包含洞见文本及辅助数据的结果。
        """
        working_summary = summary
        if working_summary is None:
            fetch_args: Dict[str, Any] = {
                "start": start or None,
                "end": end or None,
                "window_days": window_days,
                "top_n": top_n,
            }
            fetch_args = {k: v for k, v in fetch_args.items() if v not in (None, "")}
            if USE_MCP_BRIDGE:
                data = _call_mcp_bridge("fetch_dashboard_data", fetch_args)
                if not isinstance(data, dict):
                    raise RuntimeError("fetch_dashboard_data via MCP returned an invalid payload")
            else:
                data = fetch_dashboard_data(
                    context,
                    start=start,
                    end=end,
                    window_days=window_days,
                    top_n=top_n,
                )
            data_start = data.get("start") or start
            data_end = data.get("end") or end
            data_source = data.get("source") or context.config.dashboard.marketplace
            compute_payload = {
                "start": data_start,
                "end": data_end,
                "source": data_source,
                "sales": data.get("sales", []),
                "traffic": data.get("traffic", []),
                "top_n": top_n,
            }
            if USE_MCP_BRIDGE:
                metrics_result = _call_mcp_bridge("compute_dashboard_metrics", compute_payload)
                if not isinstance(metrics_result, dict):
                    raise RuntimeError("compute_dashboard_metrics via MCP returned an invalid payload")
            else:
                metrics_result = compute_dashboard_metrics(
                    context,
                    start=data_start,
                    end=data_end,
                    source=data_source,
                    sales=compute_payload["sales"],
                    traffic=compute_payload["traffic"],
                    top_n=top_n,
                )
            working_summary = metrics_result.get("summary") if isinstance(metrics_result, dict) else None
            if working_summary is None:
                raise RuntimeError("无法从指标结果中提取 summary 字段")

        payload: Dict[str, Any] = {"summary": working_summary}
        if focus is not None:
            payload["focus"] = focus
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge("generate_dashboard_insights", payload)
            if not isinstance(remote, dict):
                raise RuntimeError("generate_dashboard_insights via MCP returned an invalid payload")
            return remote
        return generate_dashboard_insights(context, summary=working_summary, focus=focus)

    @tool("analyze_dashboard_history")
    def analyze_dashboard_history_tool(
        limit: int = 6,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        函数说明:
            汇总历史仪表盘数据，生成时间序列趋势或异常分析。
        参数:
            limit (int): 本次分析包含的历史期数。
            metrics (Optional[List[str]]): 需要重点关注的指标列表。
        返回:
            Dict[str, Any]: 历史趋势与分析结论。
        """
        payload: Dict[str, Any] = {"limit": limit, "metrics": metrics}
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge("analyze_dashboard_history", payload)
            if not isinstance(remote, dict):
                raise RuntimeError("analyze_dashboard_history via MCP returned an invalid payload")
            return remote
        return analyze_dashboard_history(context, limit=limit, metrics=metrics)

    @tool("export_dashboard_history")
    def export_dashboard_history_tool(
        limit: int,
        path: str,
    ) -> Dict[str, Any]:
        """
        函数说明:
            导出历史仪表盘数据并保存为 CSV 文件。
        参数:
            limit (int): 导出的历史期数上限。
            path (str): CSV 文件的输出路径。
        返回:
            Dict[str, Any]: 导出结果与文件信息。
        """
        payload = {"limit": limit, "path": path}
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge("export_dashboard_history", payload)
            if not isinstance(remote, dict):
                raise RuntimeError("export_dashboard_history via MCP returned an invalid payload")
            return remote
        return export_dashboard_history(context, limit=limit, path=path)


    @tool("amazon_bestseller_search")
    def amazon_bestseller_search_tool(
        category: str,
        search_index: str,
        browse_node_id: Optional[str] = None,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        函数说明:
            查询 Amazon PAAPI 热销榜单，获取指定分类的热门商品。
        参数:
            category (str): 自定义的业务分类名称。
            search_index (str): Amazon PAAPI 搜索索引，例如 `Toys` 或 `Books`。
            browse_node_id (Optional[str]): 对应的类目节点 ID。
            max_items (Optional[int]): 限制返回的商品数量。
        返回:
            Dict[str, Any]: 热销商品列表与相关元数据。
        """
        payload = {
            "category": category,
            "search_index": search_index,
            "browse_node_id": browse_node_id,
            "max_items": max_items,
        }
        if USE_MCP_BRIDGE:
            remote = _call_mcp_bridge("amazon_bestseller_search", payload)
            if not isinstance(remote, dict):
                raise RuntimeError("amazon_bestseller_search via MCP returned an invalid payload")
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
    """
    功能说明:
        供 CLI 或脚本快速体验完整 Agent 流程，执行一次问答请求。
    参数:
        config (AppConfig): 当前运行所需的配置集合。
        query (str): 用户侧提出的问题或分析意图描述。
    返回:
        Dict[str, Any]: LangGraph 执行后的完整消息与工具调用轨迹。
    """
    repository = None
    if config.storage.enabled:
        repository = SQLiteRepository(config.storage.db_path)
    graph, _ = build_operations_agent(config, repository=repository)
    result = graph.invoke(
        {
            "messages": [
                SystemMessage(
                    content=(
                        "请按照“数据获取→指标计算→洞察总结→历史分析（可选）→导出（可选）→畅销榜查询（可选)"
                        "的顺序调用工具，最终输出结构化运营日报。"
                    )
                ),
                HumanMessage(content=query),
            ]
        }
    )
    return result
