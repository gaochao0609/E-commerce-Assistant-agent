"""基于 LangGraph 的运营日报智能体，通过 MCP 桥接远程服务（纯远程模式）。"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from pydantic import Field, create_model

from .config import AppConfig
from .mcp_bridge import call_mcp_tool, list_mcp_tools

# 强制通过 MCP 桥调用远端工具；默认开启远程模式。
USE_MCP_BRIDGE = os.getenv("USE_MCP_BRIDGE", "1").lower() not in {"0", "false", "no"}
logger = logging.getLogger(__name__)


def _call_mcp_bridge(tool_name: str, args: Dict[str, Any]) -> Any:
    """
    功能说明:
        通过 MCP 桥接远程调用指定工具（纯远程模式，无本地 fallback）。
    参数:
        tool_name (str): 预期在 MCP 侧注册的工具名称。
        args (Dict[str, Any]): 发送给 MCP 工具的参数字典，需保证可序列化。
    返回:
        Any: 远端 MCP 工具返回的结构化结果。
    异常:
        RuntimeError: 当 MCP 工具调用失败时抛出。
    """
    if not USE_MCP_BRIDGE:
        raise RuntimeError(
            "MCP 桥接模式已禁用。请设置 USE_MCP_BRIDGE=1 启用，"
            "并确保远端 MCP 服务器可访问。"
        )
    try:
        logger.debug("调用 MCP 工具 %s，参数：%s", tool_name, args)
        # 实际触发 MCP 请求并返回远端结果。
        return call_mcp_tool(tool_name, args)
    except Exception as exc:  # pragma: no cover
        logger.error("MCP 工具 %s 调用失败：%s", tool_name, exc)
        raise RuntimeError(f"MCP tool '{tool_name}' failed") from exc


def _json_schema_to_type(schema: Dict[str, Any]) -> Any:
    if not schema:
        return Any
    if "anyOf" in schema or "oneOf" in schema:
        return Any
    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        item_schema = schema.get("items", {})
        item_type = _json_schema_to_type(item_schema) if isinstance(item_schema, dict) else Any
        return List[item_type]  # type: ignore[misc]
    if schema_type == "object":
        return Dict[str, Any]
    return Any


def _build_args_schema(tool_spec: Dict[str, Any]) -> Optional[type]:
    input_schema = tool_spec.get("input_schema") or {}
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    if not properties:
        return None
    required = set(input_schema.get("required", []))
    fields: Dict[str, Tuple[Any, Any]] = {}
    for name, prop_schema in properties.items():
        schema = prop_schema if isinstance(prop_schema, dict) else {}
        field_type = _json_schema_to_type(schema)
        if name not in required:
            field_type = Optional[field_type]
        default_value = schema.get("default", None) if name not in required else ...
        description = schema.get("description")
        if description:
            fields[name] = (field_type, Field(default_value, description=description))
        else:
            fields[name] = (field_type, default_value)
    return create_model(f"{tool_spec['name']}Input", **fields)


def _build_tool_from_mcp(tool_spec: Dict[str, Any]) -> StructuredTool:
    tool_name = tool_spec["name"]
    description = tool_spec.get("description") or ""
    args_schema = _build_args_schema(tool_spec)

    def _tool_func(**kwargs: Any) -> Any:
        return _call_mcp_bridge(tool_name, kwargs)

    return StructuredTool.from_function(
        func=_tool_func,
        name=tool_name,
        description=description,
        args_schema=args_schema,
    )


def _load_mcp_tools() -> List[StructuredTool]:
    tool_specs = list_mcp_tools()
    if not tool_specs:
        raise RuntimeError("No tools discovered from MCP server.")
    return [_build_tool_from_mcp(spec) for spec in tool_specs]


def build_operations_agent(
    config: AppConfig,
    *,
    context: Optional[object] = None,
    repository: Optional[object] = None,
) -> tuple:
    """
    功能说明:
        构建具备运营分析能力的 LangGraph Agent，并注册所有领域工具。
        所有工具调用均通过 MCP 桥接远端服务器，不再使用本地 Service/Skill 实现。
    参数:
        config (AppConfig): 包含仪表盘刷新窗口、存储、凭证等全局配置。
        context (Optional[object]): 为兼容旧接口保留，当前实现中未使用。
        repository (Optional[object]): 为兼容旧接口保留，当前实现中未使用。
    返回:
        tuple: `(graph, tools)`，其中 `graph` 为已组装好的智能体，`tools` 为工具列表。
    """
    if not USE_MCP_BRIDGE:
        raise RuntimeError(
            "本地模式已移除。请确保 MCP 服务器正在运行，并设置 USE_MCP_BRIDGE=1。"
        )

    # 仅构建 Agent 主体使用的对话模型，业务调用全部走远程 MCP。
    if not config.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in AppConfig.")
    llm = ChatOpenAI(
        api_key=config.openai_api_key,
        model=config.openai_model,
        temperature=config.openai_temperature,
    )
    tools = _load_mcp_tools()
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
    graph, _ = build_operations_agent(config)
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
