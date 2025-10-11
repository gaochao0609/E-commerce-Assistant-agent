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
        ����˵��:
            ��ȡָ��ʱ�䴰���ڵ�ԭʼ�������������ݡ�
        ����:
            start (Optional[str]): ISO ��ʽ�Ŀ�ʼ�����ַ�������Ϊ�ձ�ʾ�Զ����㡣
            end (Optional[str]): ISO ��ʽ�Ľ��������ַ������� `start` ����ʹ�á�
            window_days (Optional[int]): ��δ�ṩ `start`/`end` ʱ�Ĺ�������������
            top_n (Optional[int]): ��Ҫ�۽�����Ʒ�������������ƽ����ģ��
        ����:
            Dict[str, Any]: �����������������ֶεĽṹ�����ݡ�
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
        ����˵��:
            ����ָ��ʱ�䴰���ڵ� KPI����ȱ�����ۻ��������ݻ��Զ����� `fetch_dashboard_data` ���롣
        ����:
            start (str): ָ�����Ŀ�ʼ���ڣ�ISO ��ʽ��
            end (str): ָ�����Ľ������ڣ�ISO ��ʽ��
            source (str): ������Դ��ʶ������ժҪ˵����
            sales (Optional[List[Dict[str, Any]]]): ���������б������� None ʱ�Զ���ȡ��
            traffic (Optional[List[Dict[str, Any]]]): ���������б������� None ʱ�Զ���ȡ��
            top_n (Optional[int]): �ص���Ʒ������Ĭ��ʹ������ֵ��
            window_days (Optional[int]): �� start/end ȱʧʱʹ�õĹ�������������
        ����:
            Dict[str, Any]: ���� `summary` ���Ľṹ��ָ������
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
                raise RuntimeError("�޷���ȡ���ۻ��������ݣ��޷�����ָ�ꡣ")

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
        ����˵��:
            ������Ӫ���죻�� `summary` ȱʧʱ���Զ��ȼ��� KPI ժҪ��
        ����:
            summary (Optional[Dict[str, Any]]): ָ��ժҪ��ȱʧʱ�ɺ����ڲ����㡣
            focus (Optional[str]): �����ص㣬���� 'sales'��
            start (Optional[str]): ���¼���ָ��ʱʹ�õĿ�ʼ���ڡ�
            end (Optional[str]): ���¼���ָ��ʱʹ�õĽ������ڡ�
            window_days (Optional[int]): ���¼���ʱ�Ĺ�������������
            top_n (Optional[int]): ָ�����ʱ���ص���Ʒ������
        ����:
            Dict[str, Any]: ���������ı���ժҪ��Ϣ�Ľṹ�������
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
                raise RuntimeError("�޷���ȡָ��ժҪ���޷����ɶ��졣")

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
        ����˵��:
            �������ָ��ժҪ������ԱȲ�����������ʱ�����С�
        ����:
            limit (int): ����Ƚϵ���ʷժҪ������
            metrics (Optional[List[str]]): ��Ҫ��ע��ָ���б���Ϊ��ʱ����ȫ��ָ�ꡣ
        ����:
            Dict[str, Any]: �����Աȷ�����ʱ���������ݡ�
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
        ����˵��:
            �������ָ��ժҪ����Ϊ CSV �ļ���
        ����:
            limit (int): ��������ʷ��¼������
            path (str): CSV ���·�������������·����
        ����:
            Dict[str, Any]: ��������״̬���ļ�·���ķ�����Ϣ��
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
        ����˵��:
            ��ѯ����ѷָ����Ŀ�µĳ�������Ϣ��
        ����:
            category (str): �ڲ�ʹ�õķ������ƻ������
            search_index (str): Amazon PAAPI ������������ `Toys`��`Books` �ȡ�
            browse_node_id (Optional[str]): ָ���Ľڵ��ţ�ϸ��������Ŀ��
            max_items (Optional[int]): ��෵�ص���Ʒ������
        ����:
            Dict[str, Any]: ������Ʒ�б�����������������ժҪ��Ϣ��
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
