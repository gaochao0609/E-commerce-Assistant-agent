"""Operations Dashboard MCP 服务器，基于 FastMCP SDK 暴露运营工具与资源。"""

from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from operations_dashboard.config import (
    AppConfig,
    AmazonCredentialConfig,
    DashboardConfig,
    StorageConfig,
)
from operations_dashboard.services import (
    ServiceContext,
    analyze_dashboard_history as _analyze_dashboard_history,
    amazon_bestseller_search as _amazon_bestseller_search,
    compute_dashboard_metrics as _compute_dashboard_metrics,
    create_service_context,
    export_dashboard_history as _export_dashboard_history,
    fetch_dashboard_data as _fetch_dashboard_data,
    generate_dashboard_insights as _generate_dashboard_insights,
)
from operations_dashboard.storage.repository import StoredSummary


@dataclass
class DashboardAppContext:
    """封装 MCP 生命周期中共享的服务上下文。

    属性:
        service_context (ServiceContext): 预先构建好的服务上下文，包含数据源、存储与 LLM。
    """

    service_context: ServiceContext


def _load_config() -> AppConfig:
    """加载应用配置，缺省时退回到安全的 Mock 配置。

    返回:
        AppConfig: 含 Amazon 凭证、仪表盘默认参数及存储配置的完整对象。
    """

    try:
        return AppConfig.from_env()
    except RuntimeError:
        return AppConfig(
            amazon=AmazonCredentialConfig(
                access_key="mock",
                secret_key="mock",
                associate_tag=None,
                marketplace="US",
            ),
            dashboard=DashboardConfig(),
            storage=StorageConfig(),
        )


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[DashboardAppContext]:
    """在服务器生命周期内创建并共享 ServiceContext。

    参数:
        server (FastMCP): FastMCP 服务器实例（未直接使用，兼容接口签名）。

    生成:
        DashboardAppContext: 提供给工具与资源访问的共享上下文对象。
    """

    config = _load_config()
    service_context = create_service_context(config)
    try:
        yield DashboardAppContext(service_context=service_context)
    finally:
        pass


mcp = FastMCP(
    name="Operations Dashboard",
    instructions=(
        "Expose Amazon operations analytics through MCP tools and resources. "
        "Use the registered tools to fetch raw data, compute KPIs, and analyze trends."
    ),
    lifespan=app_lifespan,
)


def _service(ctx: Context[ServerSession, DashboardAppContext]) -> ServiceContext:
    """从上下文中提取共享的 ServiceContext。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): FastMCP 注入的请求上下文。

    返回:
        ServiceContext: 当前会话可复用的业务服务上下文。
    """

    return ctx.app.service_context


def _summary_to_dict(summary: StoredSummary) -> Dict[str, Any]:
    """将 SQLite 中的存储摘要转换为 JSON 友好的结构。

    参数:
        summary (StoredSummary): 存储层返回的仪表盘摘要对象。

    返回:
        Dict[str, Any]: 包含基础统计与产品列表的字典结构。
    """

    return {
        "id": summary.id,
        "start": summary.start,
        "end": summary.end,
        "source": summary.source,
        "total_revenue": summary.total_revenue,
        "total_units": summary.total_units,
        "total_sessions": summary.total_sessions,
        "conversion_rate": summary.conversion_rate,
        "refund_rate": summary.refund_rate,
        "created_at": summary.created_at,
        "products": [
            {
                "asin": product.asin,
                "title": product.title,
                "revenue": product.revenue,
                "units": product.units,
                "sessions": product.sessions,
                "conversion_rate": product.conversion_rate,
                "refunds": product.refunds,
                "buy_box_percentage": product.buy_box_percentage,
            }
            for product in summary.products
        ],
    }


@mcp.resource("operations-dashboard://config")
def read_configuration(ctx: Context[ServerSession, DashboardAppContext]) -> Dict[str, Any]:
    """暴露运行时使用的仪表盘配置。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): FastMCP 自动注入的上下文对象。

    返回:
        Dict[str, Any]: 包含市场、窗口长度、TopN 与存储配置的字典。
    """

    service_context = _service(ctx)
    config = service_context.config
    return {
        "marketplace": config.dashboard.marketplace,
        "default_window_days": config.dashboard.refresh_window_days,
        "top_n_products": config.dashboard.top_n_products,
        "storage_enabled": config.storage.enabled,
        "database_path": config.storage.db_path,
    }


@mcp.resource("operations-dashboard://history/{limit:int}")
def read_recent_history(
    ctx: Context[ServerSession, DashboardAppContext],
    limit: int = 5,
) -> Dict[str, Any]:
    """读取最近的仪表盘摘要历史。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 请求上下文。
        limit (int): 需要返回的历史记录条数，默认 5。

    返回:
        Dict[str, Any]: 若启用存储返回摘要列表，否则返回提示信息。
    """

    service_context = _service(ctx)
    repository = service_context.repository
    if not repository:
        return {"message": "Storage is disabled for this deployment."}
    repository.initialize()
    summaries = repository.fetch_recent_summaries(limit=limit)
    return {"summaries": [_summary_to_dict(summary) for summary in summaries]}


@mcp.tool(name="fetch_dashboard_data")
def tool_fetch_dashboard_data(
    ctx: Context[ServerSession, DashboardAppContext],
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    """获取指定时间窗口的原始销售与流量数据。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 当前工具调用的上下文。
        start (Optional[str]): ISO 日期字符串，表示起始日期。
        end (Optional[str]): ISO 日期字符串，表示结束日期。
        window_days (Optional[int]): 未提供 start/end 时的回溯天数。
        top_n (Optional[int]): 希望包含的重点商品数量。

    返回:
        Dict[str, Any]: 包含销售、流量与商品清单的原始数据。
    """

    return _fetch_dashboard_data(
        _service(ctx),
        start=start,
        end=end,
        window_days=window_days,
        top_n=top_n,
    )


@mcp.tool(name="generate_dashboard_insights")
def tool_generate_dashboard_insights(
    ctx: Context[ServerSession, DashboardAppContext],
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
) -> Dict[str, Any]:
    """生成面向运营团队的洞察总结。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 当前调用上下文。
        start (Optional[str]): 起始日期。
        end (Optional[str]): 结束日期。
        window_days (Optional[int]): 回溯天数。

    返回:
        Dict[str, Any]: 包含洞察文本与汇总数据的字典。
    """

    return _generate_dashboard_insights(
        _service(ctx),
        start=start,
        end=end,
        window_days=window_days,
    )


@mcp.tool(name="analyze_dashboard_history")
def tool_analyze_dashboard_history(
    ctx: Context[ServerSession, DashboardAppContext],
    limit: int = 6,
    metrics: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """对近期仪表盘摘要进行指标对比分析。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 上下文对象。
        limit (int): 参与比较的历史摘要数量，默认 6。
        metrics (Optional[list[str]]): 需要重点比较的指标名称列表。

    返回:
        Dict[str, Any]: 包括差异分析与时间序列的结构化结果。
    """

    return _analyze_dashboard_history(
        _service(ctx),
        limit=limit,
        metrics=metrics,
    )


@mcp.tool(name="export_dashboard_history")
def tool_export_dashboard_history(
    ctx: Context[ServerSession, DashboardAppContext],
    limit: int,
    path: str,
) -> Dict[str, Any]:
    """将历史摘要导出为 CSV 文件。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 当前调用上下文。
        limit (int): 导出的历史记录数量。
        path (str): CSV 输出路径，可为相对路径。

    返回:
        Dict[str, Any]: 文件生成结果与提示信息。
    """

    return _export_dashboard_history(
        _service(ctx),
        limit=limit,
        path=path,
    )


@mcp.tool(name="amazon_bestseller_search")
def tool_amazon_bestseller_search(
    ctx: Context[ServerSession, DashboardAppContext],
    category: str,
    search_index: str,
    browse_node_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """调用 Amazon PAAPI 查询热销产品。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 调用上下文。
        category (str): 业务定义的类目名称。
        search_index (str): PAAPI 使用的搜索索引，如 `Books`。
        browse_node_id (Optional[str]): 可选的分类节点 ID。
        max_items (Optional[int]): 返回的最大商品数量。

    返回:
        Dict[str, Any]: 包含商品信息与分类的结果。
    """

    return _amazon_bestseller_search(
        _service(ctx),
        category=category,
        search_index=search_index,
        browse_node_id=browse_node_id,
        max_items=max_items,
    )


@mcp.tool(name="compute_dashboard_metrics")
def tool_compute_dashboard_metrics(
    ctx: Context[ServerSession, DashboardAppContext],
    start: str,
    end: str,
    source: str,
    sales: list[Dict[str, Any]],
    traffic: list[Dict[str, Any]],
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    """根据原始数据计算 KPI 并进行存储。

    参数:
        ctx (Context[ServerSession, DashboardAppContext]): 调用上下文。
        start (str): 起始日期。
        end (str): 结束日期。
        source (str): 数据来源标识。
        sales (list[Dict[str, Any]]): 销售数据列表。
        traffic (list[Dict[str, Any]]): 流量数据列表。
        top_n (Optional[int]): 需要保留的重点商品数量。

    返回:
        Dict[str, Any]: 计算后的 KPI 摘要与存储结果。
    """

    return _compute_dashboard_metrics(
        _service(ctx),
        start=start,
        end=end,
        source=source,
        sales=sales,
        traffic=traffic,
        top_n=top_n,
    )


def main(argv: Optional[list[str]] = None) -> None:
    """命令行入口，支持选择不同的 MCP 传输方式。

    参数:
        argv (Optional[list[str]]): 可选的命令行参数列表，通常由 `argparse` 自动填充。

    返回:
        None
    """

    parser = argparse.ArgumentParser(
        description="Run the Operations Dashboard MCP server."
    )
    parser.add_argument(
        "transport",
        nargs="?",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="Transport mechanism to expose (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Optional host binding for HTTP-based transports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Optional port binding for HTTP-based transports.",
    )
    args = parser.parse_args(argv)

    run_kwargs: Dict[str, Any] = {"transport": args.transport}
    if args.host:
        run_kwargs["host"] = args.host
    if args.port is not None:
        run_kwargs["port"] = args.port

    mcp.run(**run_kwargs)


if __name__ == "__main__":
    main()
