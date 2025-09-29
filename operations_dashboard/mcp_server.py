"""Minimal MCP-like server exposing dashboard tools."""

from typing import Any, Callable, Dict, List, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from operations_dashboard.config import AppConfig, AmazonCredentialConfig, DashboardConfig, StorageConfig
from operations_dashboard.services import (
    ServiceContext,
    analyze_dashboard_history,
    amazon_bestseller_search,
    compute_dashboard_metrics,
    create_service_context,
    export_dashboard_history,
    fetch_dashboard_data,
    generate_dashboard_insights,
)


class ToolCall(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    calls: List[ToolCall]


class ToolReturn(BaseModel):
    tool_name: str
    status: Literal["success", "failed"]
    output: Any


class MCPResponse(BaseModel):
    returns: List[ToolReturn]


def _load_config() -> AppConfig:
    try:
        return AppConfig.from_env()
    except RuntimeError:
        return AppConfig(
            amazon=AmazonCredentialConfig(access_key="mock", secret_key="mock", associate_tag=None, marketplace="US"),
            dashboard=DashboardConfig(),
            storage=StorageConfig(),
        )


CONFIG = _load_config()
CONTEXT: ServiceContext = create_service_context(CONFIG)


def _fetch_dashboard_data_proxy(**kwargs):
    return fetch_dashboard_data(CONTEXT, **kwargs)


def _compute_dashboard_metrics_proxy(**kwargs):
    return compute_dashboard_metrics(CONTEXT, **kwargs)


def _generate_dashboard_insights_proxy(**kwargs):
    return generate_dashboard_insights(CONTEXT, **kwargs)


def _analyze_dashboard_history_proxy(**kwargs):
    return analyze_dashboard_history(CONTEXT, **kwargs)


def _export_dashboard_history_proxy(**kwargs):
    return export_dashboard_history(CONTEXT, **kwargs)


def _amazon_bestseller_search_proxy(**kwargs):
    return amazon_bestseller_search(CONTEXT, **kwargs)


TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    "fetch_dashboard_data": _fetch_dashboard_data_proxy,
    "compute_dashboard_metrics": _compute_dashboard_metrics_proxy,
    "generate_dashboard_insights": _generate_dashboard_insights_proxy,
    "analyze_dashboard_history": _analyze_dashboard_history_proxy,
    "export_dashboard_history": _export_dashboard_history_proxy,
    "amazon_bestseller_search": _amazon_bestseller_search_proxy,
}

app = FastAPI(title="Operations Dashboard MCP", description="Expose dashboard tools via MCP-style API")


@app.post("/mcp", response_model=MCPResponse)
def handle_mcp_request(request: MCPRequest) -> MCPResponse:
    results: List[ToolReturn] = []
    for call in request.calls:
        tool = TOOL_REGISTRY.get(call.tool_name)
        if not tool:
            results.append(
                ToolReturn(
                    tool_name=call.tool_name,
                    status="failed",
                    output=f"工具 '{call.tool_name}' 未注册",
                )
            )
            continue
        try:
            output = tool(**call.args)
            results.append(ToolReturn(tool_name=call.tool_name, status="success", output=output))
        except Exception as exc:  # pragma: no cover
            results.append(
                ToolReturn(
                    tool_name=call.tool_name,
                    status="failed",
                    output=str(exc),
                )
            )
    return MCPResponse(returns=results)


@app.get("/")
def read_root():
    return {"message": "MCP Server 正在运行，请向 /mcp 端点发送请求"}
