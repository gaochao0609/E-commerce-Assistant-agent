"""Operations Dashboard MCP 服务模块，基于 FastMCP 暴露业务资源与工具。"""

import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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


class DashboardAppContext:
    """封装 MCP 生命周期中共享的业务依赖。

    Attributes:
        service_context (ServiceContext): 包含数据源、仓储、LLM 等资源的聚合上下文。
    """

    def __init__(self, service_context: ServiceContext) -> None:
        """初始化上下文容器。

        Args:
            service_context (ServiceContext): 通过 :func:`create_service_context` 构建的业务上下文。
        """

        self.service_context = service_context


def _load_config() -> AppConfig:
    """加载运行配置，未设置环境变量时使用示例值。

    Returns:
        AppConfig: 可用于初始化业务上下文的配置对象。
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
    """FastMCP 生命周期钩子，创建并共享业务上下文。

    Args:
        server (FastMCP): FastMCP 框架传入的服务器实例，本实现中仅为保持签名一致。

    Yields:
        DashboardAppContext: 包含业务依赖的上下文对象，供请求期间复用。
    """

    config = _load_config()
    service_context = create_service_context(config)
    try:
        yield DashboardAppContext(service_context=service_context)
    finally:
        # 当前业务无额外清理动作，保留扩展点。
        pass


mcp = FastMCP(
    name="Operations Dashboard",
    instructions=(
        "Expose Amazon operations analytics through MCP tools and resources. "
        "Use the registered tools to fetch raw data, compute KPIs, and analyze trends."
    ),
    lifespan=app_lifespan,
)
# Inspector 会读取该列表自动安装调试所需的三方依赖。
mcp.dependencies = [
    "langchain",
    "langchain-openai",
    "langgraph",
    "python-amazon-paapi",
]


def _service(ctx: Context) -> ServiceContext:
    """从请求上下文里提取共享业务依赖。

    Args:
        ctx (Context): FastMCP 提供的请求上下文，包含当前会话的 app 与 session 信息。

    Returns:
        ServiceContext: 预先构建的业务上下文实例。
    """

    return ctx.app.service_context


def _summary_to_dict(summary: StoredSummary) -> Dict[str, Any]:
    """将仓储层摘要对象转换为 JSON 友好格式。

    Args:
        summary (StoredSummary): 仓储返回的仪表盘摘要记录。

    Returns:
        Dict[str, Any]: 可直接返回给 MCP 客户端的字典结构。
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
def read_configuration(ctx: Context) -> Dict[str, Any]:
    """返回当前仪表盘配置，供客户端参考默认参数。

    Args:
        ctx (Context): FastMCP 请求上下文。

    Returns:
        Dict[str, Any]: 包含市场、时间窗口、TopN 等信息的配置字典。
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


@mcp.resource("operations-dashboard://history/{limit}")
def read_recent_history(
    ctx: Context,
    limit: int = 5,
) -> Dict[str, Any]:
    """读取最近的摘要历史，当未启用持久化时返回提示。

    Args:
        ctx (Context): FastMCP 请求上下文。
        limit (int): 需要拉取的摘要数量，默认值为 5。

    Returns:
        Dict[str, Any]: 包含摘要列表或提示信息的响应数据。
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
    ctx: Context,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    """获取指定时间窗口内的原始销售与流量数据。

    Args:
        ctx (Context): FastMCP 请求上下文。
        start (Optional[str]): 起始日期（ISO 字符串），未提供时会根据 window_days 计算。
        end (Optional[str]): 结束日期（ISO 字符串）。
        window_days (Optional[int]): 未提供 start/end 时使用的回溯天数。
        top_n (Optional[int]): 需要返回的重点商品数量。

    Returns:
        Dict[str, Any]: 含有销售、流量及商品列表的原始数据结构。
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
    ctx: Context,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: Optional[int] = None,
) -> Dict[str, Any]:
    """基于业务服务生成自然语言洞察。

    Args:
        ctx (Context): FastMCP 请求上下文。
        start (Optional[str]): 起始日期。
        end (Optional[str]): 结束日期。
        window_days (Optional[int]): 更新时间窗口天数。

    Returns:
        Dict[str, Any]: 结构化洞察结果，包含原始摘要与文本说明。
    """

    return _generate_dashboard_insights(
        _service(ctx),
        start=start,
        end=end,
        window_days=window_days,
    )


@mcp.tool(name="analyze_dashboard_history")
def tool_analyze_dashboard_history(
    ctx: Context,
    limit: int = 6,
    metrics: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """对比近几期摘要，分析关键指标趋势。

    Args:
        ctx (Context): FastMCP 请求上下文。
        limit (int): 参与对比的摘要数量，默认 6。
        metrics (Optional[list[str]]): 限定分析的指标名称列表。

    Returns:
        Dict[str, Any]: 含有趋势分析与时间序列数据的结果字典。
    """

    return _analyze_dashboard_history(
        _service(ctx),
        limit=limit,
        metrics=metrics,
    )


@mcp.tool(name="export_dashboard_history")
def tool_export_dashboard_history(
    ctx: Context,
    limit: int,
    path: str,
) -> Dict[str, Any]:
    """将摘要历史导出为 CSV 文件。

    Args:
        ctx (Context): FastMCP 请求上下文。
        limit (int): 需要导出的记录数量。
        path (str): 目标文件路径，可以是相对路径。

    Returns:
        Dict[str, Any]: 包含导出状态与文件路径的反馈信息。
    """

    return _export_dashboard_history(
        _service(ctx),
        limit=limit,
        path=path,
    )


@mcp.tool(name="amazon_bestseller_search")
def tool_amazon_bestseller_search(
    ctx: Context,
    category: str,
    search_index: str,
    browse_node_id: Optional[str] = None,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """调用 PAAPI，查询指定类目的热销商品。

    Args:
        ctx (Context): FastMCP 请求上下文。
        category (str): 业务自定义的商品类目描述。
        search_index (str): PAAPI 使用的索引，例如 "Books"。
        browse_node_id (Optional[str]): 可选的分类节点 ID。
        max_items (Optional[int]): 限制返回的商品数量。

    Returns:
        Dict[str, Any]: 包含热销商品列表及摘要信息的字典。
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
    ctx: Context,
    start: str,
    end: str,
    source: str,
    sales: list[Dict[str, Any]],
    traffic: list[Dict[str, Any]],
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    """根据原始数据计算 KPI 并持久化摘要结果。

    Args:
        ctx (Context): FastMCP 请求上下文。
        start (str): 起始日期（ISO 字符串）。
        end (str): 结束日期（ISO 字符串）。
        source (str): 数据来源标识。
        sales (list[Dict[str, Any]]): 销售数据列表。
        traffic (list[Dict[str, Any]]): 流量数据列表。
        top_n (Optional[int]): 重点商品数量。

    Returns:
        Dict[str, Any]: 计算后的 KPI 摘要信息。
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
    """命令行入口，支持选择传输方式与监听参数。

    Args:
        argv (Optional[list[str]]): 手动传入的参数列表，通常由命令行自动提供。
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

    if args.host:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
