"""面向 MCP 客户端的 FastAPI 服务，统一封装运营仪表盘工具。"""

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
    """
    表示一次由 MCP 客户端发起的工具调用。

    属性:
        tool_name (str): 目标工具名称，应当与注册表中的键一致。
        args (Dict[str, Any]): 发送给工具的参数字典，默认为空。
    """

    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    """
    MCP 端点接收的请求载荷结构，允许批量调用多个工具。

    属性:
        calls (List[ToolCall]): 请求队列，按顺序依次处理。
    """

    calls: List[ToolCall]


class ToolReturn(BaseModel):
    """
    MCP 服务器为每次工具调用返回的规范化结果。

    属性:
        tool_name (str): 对应的工具名称，便于客户端匹配。
        status (Literal["success", "failed"]): 标识调用是否成功。
        output (Any): 工具返回的原始结果或错误信息。
    """

    tool_name: str
    status: Literal["success", "failed"]
    output: Any


class MCPResponse(BaseModel):
    """
    MCP 端点最终返回的顶层包装结构。

    属性:
        returns (List[ToolReturn]): 每个工具调用的处理结果列表。
    """

    returns: List[ToolReturn]


def _load_config() -> AppConfig:
    """
    功能说明:
        优先尝试从环境变量加载应用配置；若缺失则使用默认的 Mock 凭证。
    返回:
        AppConfig: 供服务初始化使用的完整配置实例。
    """
    try:
        return AppConfig.from_env()
    except RuntimeError:
        # 回退到安全的默认值，便于本地演示与单元测试。
        return AppConfig(
            amazon=AmazonCredentialConfig(access_key="mock", secret_key="mock", associate_tag=None, marketplace="US"),
            dashboard=DashboardConfig(),
            storage=StorageConfig(),
        )


CONFIG = _load_config()
# 共享的服务上下文，避免每次请求重复构建依赖。
CONTEXT: ServiceContext = create_service_context(CONFIG)


def _fetch_dashboard_data_proxy(**kwargs):
    """代理函数：复用全局上下文调用 `fetch_dashboard_data`。"""

    return fetch_dashboard_data(CONTEXT, **kwargs)


def _compute_dashboard_metrics_proxy(**kwargs):
    """代理函数：调用 `compute_dashboard_metrics` 计算 KPI。"""

    return compute_dashboard_metrics(CONTEXT, **kwargs)


def _generate_dashboard_insights_proxy(**kwargs):
    """代理函数：生成结构化洞察描述。"""

    return generate_dashboard_insights(CONTEXT, **kwargs)


def _analyze_dashboard_history_proxy(**kwargs):
    """代理函数：执行历史趋势分析。"""

    return analyze_dashboard_history(CONTEXT, **kwargs)


def _export_dashboard_history_proxy(**kwargs):
    """代理函数：导出历史汇总数据。"""

    return export_dashboard_history(CONTEXT, **kwargs)


def _amazon_bestseller_search_proxy(**kwargs):
    """代理函数：查询亚马逊畅销榜。"""

    return amazon_bestseller_search(CONTEXT, **kwargs)


TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    "fetch_dashboard_data": _fetch_dashboard_data_proxy,
    "compute_dashboard_metrics": _compute_dashboard_metrics_proxy,
    "generate_dashboard_insights": _generate_dashboard_insights_proxy,
    "analyze_dashboard_history": _analyze_dashboard_history_proxy,
    "export_dashboard_history": _export_dashboard_history_proxy,
    "amazon_bestseller_search": _amazon_bestseller_search_proxy,
}
# 将所有可调用服务收敛到统一的注册表中，供路由调度使用。

app = FastAPI(title="Operations Dashboard MCP", description="Expose dashboard tools via MCP-style API")


@app.post("/mcp", response_model=MCPResponse)
def handle_mcp_request(request: MCPRequest) -> MCPResponse:
    """
    功能说明:
        逐个调度客户端请求的工具，实现 MCP 风格的批量调用。
    参数:
        request (MCPRequest): 包含所有工具调用定义的请求体。
    返回:
        MCPResponse: 按顺序排列的工具执行结果集合。
    """
    results: List[ToolReturn] = []
    for call in request.calls:
        tool = TOOL_REGISTRY.get(call.tool_name)
        if not tool:
            # 工具未注册时返回失败结果，帮助客户端排查配置问题。
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
            # 捕获内部错误，防止单个工具导致整个批次失败。
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
    """提供健康检查信息，提示客户端访问 /mcp 完成工具调用。"""

    return {"message": "MCP Server 正在运行，请向 /mcp 端点发送请求"}
