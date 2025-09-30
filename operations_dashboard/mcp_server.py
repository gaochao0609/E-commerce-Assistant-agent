"""Operations Dashboard MCP server implemented with FastMCP."""


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


class DashboardAppContext:
    """Objects shared for the lifetime of the MCP server."""

    def __init__(self, service_context: ServiceContext) -> None:
        self.service_context = service_context


def _load_config() -> AppConfig:
    """Load configuration from the environment with safe fallbacks."""

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
    """Create a shared `ServiceContext` for the lifetime of the FastMCP server."""

    config = _load_config()
    service_context = create_service_context(config)
    try:
        yield DashboardAppContext(service_context=service_context)
    finally:
        # Nothing to clean up yet – placeholder for future teardown.
        pass


mcp = FastMCP(
    name="Operations Dashboard",
    instructions=(
        "Expose Amazon operations analytics through MCP tools and resources. "
        "Use the registered tools to fetch raw data, compute KPIs, and analyze trends."
    ),
    lifespan=app_lifespan,
)
# Help the MCP Inspector install required third-party packages automatically.
mcp.dependencies = [
    "langchain",
    "langchain-openai",
    "langgraph",
    "python-amazon-paapi",
]


def _service(ctx: Context) -> ServiceContext:
    """Access the shared `ServiceContext` from the request context."""

    return ctx.app.service_context


def _summary_to_dict(summary: StoredSummary) -> Dict[str, Any]:
    """Convert a stored dashboard summary into JSON-ready data."""

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
    """Expose the active dashboard configuration."""

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
    """Return recent persisted dashboard summaries when storage is enabled."""

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
    """Fetch raw sales and traffic data for a given window."""

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
    """Generate natural-language insights for the requested timeframe."""

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
    """Compare recent dashboard summaries to highlight trends."""

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
    """Export stored dashboard history to a CSV file."""

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
    """Query Amazon PAAPI for best-selling products in the requested category."""

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
    """Compute KPIs from raw sales and traffic payloads and persist the summary."""

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
    """Command-line entry point that mirrors the FastMCP CLI."""

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

