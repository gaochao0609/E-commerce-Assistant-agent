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
        Optional[Any]: 若桥接成功返回远端输出，否则返回 `None` 以触发本地回退。
    """
    # 1. 若桥接未启用则直接跳过，保持调用方逻辑简洁。
    if not USE_MCP_BRIDGE:
        return None
    try:
        logger.debug("调用 MCP 工具 %s，参数：%s", tool_name, args)
        # 2. 实际触发 HTTP 请求并返回远端结果。
        return call_mcp_tool(tool_name, args)
    except Exception as exc:  # pragma: no cover
        # 3. 捕获网络/序列化异常并记录日志，最终回退至本地实现。
        logger.warning("MCP 工具 %s 调用失败：%s", tool_name, exc)
        return None


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
                model="gpt-3.5-turbo",
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
        """
        功能说明:
            获取指定时间窗口内的原始销量与流量数据。
        参数:
            start (Optional[str]): ISO 格式的开始日期字符串，可为空表示自动计算。
            end (Optional[str]): ISO 格式的结束日期字符串，与 `start` 搭配使用。
            window_days (Optional[int]): 当未提供 `start`/`end` 时的滚动窗口天数。
            top_n (Optional[int]): 需要聚焦的商品数量，用于限制结果规模。
        返回:
            Dict[str, Any]: 包含销量、流量等字段的结构化数据。
        """
        # 1. 优先尝试通过 MCP 远端调用，便于与其他进程共享能力。
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
            # 2. 远端返回有效结果时直接复用，保持一致的数据形态。
            return remote
        # 3. 否则退回到本地服务逻辑，使用当前上下文读取数据源。
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
        功能说明:
            计算指定时间窗口内的 KPI，若缺少销售或流量数据会自动调用 `fetch_dashboard_data` 补齐。
        参数:
            start (str): 指标计算的开始日期，ISO 格式。
            end (str): 指标计算的结束日期，ISO 格式。
            source (str): 数据来源标识，用于摘要说明。
            sales (Optional[List[Dict[str, Any]]]): 销售数据列表；传入 None 时自动拉取。
            traffic (Optional[List[Dict[str, Any]]]): 流量数据列表；传入 None 时自动拉取。
            top_n (Optional[int]): 重点商品数量；默认使用配置值。
            window_days (Optional[int]): 当 start/end 缺失时使用的滚动窗口天数。
        返回:
            Dict[str, Any]: 包含 `summary` 键的结构化指标结果。
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
            remote_fetch = _call_mcp_bridge("fetch_dashboard_data", fetch_args)
            if isinstance(remote_fetch, dict):
                data = remote_fetch
            if data is None:
                data = fetch_dashboard_data(
                    context,
                    start=start,
                    end=end,
                    window_days=window_days,
                    top_n=top_n,
                )
            sales = data.get("sales")
            traffic = data.get("traffic")
            start = data.get("start") or start
            end = data.get("end") or end
            source = data.get("source") or source or context.config.dashboard.marketplace
            if sales is None or traffic is None:
                raise RuntimeError("无法获取销售或流量数据，无法计算指标。")

        payload = {
            "start": start,
            "end": end,
            "source": source,
            "sales": sales,
            "traffic": traffic,
            "top_n": top_n,
        }
        remote = _call_mcp_bridge("compute_dashboard_metrics", payload)
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

    @tool("analyze_dashboard_history")
    def analyze_dashboard_history_tool(
        limit: int = 6,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        功能说明:
            对最近的指标摘要做横向对比并返回趋势与时间序列。
        参数:
            limit (int): 参与比较的历史摘要数量。
            metrics (Optional[List[str]]): 需要关注的指标列表；为空时返回全部指标。
        返回:
            Dict[str, Any]: 包含对比分析与时间序列数据。
        """
        payload: Dict[str, Any] = {"limit": limit, "metrics": metrics}
        remote = _call_mcp_bridge("analyze_dashboard_history", payload)
        if isinstance(remote, dict):
            return remote
        return analyze_dashboard_history(context, limit=limit, metrics=metrics)

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
        功能说明:
            生成运营洞察；当 `summary` 缺失时会自动先计算 KPI 摘要。
        参数:
            summary (Optional[Dict[str, Any]]): 指标摘要，缺失时由函数内部计算。
            focus (Optional[str]): 洞察重点，例如 'sales'。
            start (Optional[str]): 重新计算指标时使用的开始日期。
            end (Optional[str]): 重新计算指标时使用的结束日期。
            window_days (Optional[int]): 重新计算时的滚动窗口天数。
            top_n (Optional[int]): 指标计算时的重点商品数量。
        返回:
            Dict[str, Any]: 包含洞察文本及摘要信息的结构化结果。
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
            data = _call_mcp_bridge("fetch_dashboard_data", fetch_args)
            if not isinstance(data, dict):
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
            metrics_result = compute_dashboard_metrics(
                context,
                start=data_start,
                end=data_end,
                source=data_source,
                sales=data.get("sales", []),
                traffic=data.get("traffic", []),
                top_n=top_n,
            )
            working_summary = metrics_result.get("summary")
            if working_summary is None:
                raise RuntimeError("无法获取指标摘要，无法生成洞察。")

        payload: Dict[str, Any] = {"summary": working_summary}
        if focus is not None:
            payload["focus"] = focus
        remote = _call_mcp_bridge("generate_dashboard_insights", payload)
        if isinstance(remote, dict):
            return remote
        return generate_dashboard_insights(context, summary=working_summary, focus=focus)

    @tool("export_dashboard_history")
    def export_dashboard_history_tool(
        limit: int,
        path: str,
    ) -> Dict[str, Any]:
        """
        功能说明:
            将最近的指标摘要导出为 CSV 文件。
        参数:
            limit (int): 导出的历史记录数量。
            path (str): CSV 输出路径，可以是相对路径。
        返回:
            Dict[str, Any]: 包含导出状态与文件路径的反馈信息。
        """
        payload = {"limit": limit, "path": path}
        remote = _call_mcp_bridge("export_dashboard_history", payload)
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
        """
        功能说明:
            查询亚马逊指定类目下的畅销榜单信息。
        参数:
            category (str): 内部使用的分类名称或别名。
            search_index (str): Amazon PAAPI 搜索索引，如 `Toys`、`Books` 等。
            browse_node_id (Optional[str]): 指定的节点编号，细化至子类目。
            max_items (Optional[int]): 最多返回的商品数量。
        返回:
            Dict[str, Any]: 包含商品列表及其销量、排名等摘要信息。
        """
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

    # 3. 将所有工具注册至 LangGraph，构建可复用的 Agent 图。
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
