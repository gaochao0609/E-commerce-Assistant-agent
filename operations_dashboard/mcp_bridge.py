"""MCP 桥接模块，使用官方 Python SDK 通过 stdio 方式与服务器交互。"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import EmbeddedResource, TextContent

# 默认用于启动 MCP 服务器的可执行命令，可通过环境变量覆盖。
DEFAULT_COMMAND = os.getenv("MCP_BRIDGE_COMMAND", "python")
# 以 JSON 数组形式存储的命令行参数，默认执行 `python -m operations_dashboard.mcp_server`。
DEFAULT_ARGS = os.getenv(
    "MCP_BRIDGE_ARGS",
    json.dumps(["-m", "operations_dashboard.mcp_server"]),
)
# 可选的环境变量补丁，允许调用方为子进程注入额外配置。
DEFAULT_ENV = os.getenv("MCP_BRIDGE_ENV")


def _parse_args(raw: str) -> list[str]:
    """将字符串形式的命令行参数解析为列表。

    参数:
        raw (str): 以 JSON 数组或空格分隔方式提供的参数字符串。

    返回:
        list[str]: 解析后的参数列表，保证所有元素均为字符串。
    """

    try:
        value = json.loads(raw)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
    except json.JSONDecodeError:
        pass
    return [item for item in raw.split(" ") if item]


def _parse_env(raw: Optional[str]) -> Optional[Dict[str, str]]:
    """解析子进程需要的环境变量补丁。

    参数:
        raw (Optional[str]): 使用 JSON 对象表示的环境变量字典，或为空。

    返回:
        Optional[Dict[str, str]]: 若输入合法返回键值均为字符串的字典，否则返回 ``None``。
    """

    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            return value
    except json.JSONDecodeError:
        pass
    return None


def _server_parameters() -> StdioServerParameters:
    """构建 stdio 传输所需的服务器启动参数对象。

    返回:
        StdioServerParameters: 描述可执行文件、参数、环境变量的配置实例。
    """

    command = DEFAULT_COMMAND
    args = _parse_args(DEFAULT_ARGS)
    env = _parse_env(DEFAULT_ENV)
    return StdioServerParameters(command=command, args=args, env=env)


async def _call_tool_async(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """异步调用 MCP 工具，优先返回结构化结果。

    参数:
        tool_name (str): 需要触发的工具名称，需与服务器注册项一致。
        arguments (Dict[str, Any]): 传递给工具的参数字典，必须可被 JSON 序列化。

    返回:
        Any: 结构化结果、文本结果或资源文本内容。

    异常:
        RuntimeError: 当工具调用失败或服务器返回错误状态时抛出。
    """

    params = _server_parameters()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

            if getattr(result, "isError", False):
                messages = []
                for block in result.content:
                    if isinstance(block, TextContent):
                        messages.append(block.text)
                raise RuntimeError(
                    f"MCP tool '{tool_name}' failed: {'; '.join(messages) if messages else 'unknown error'}"
                )

            if result.structuredContent is not None:
                return result.structuredContent

            normalized_blocks: list[dict[str, Any]] = []
            for block in result.content:
                if isinstance(block, TextContent):
                    normalized_blocks.append({"type": "text", "text": block.text})
                    continue
                if isinstance(block, EmbeddedResource):
                    resource = block.resource
                    resource_payload: dict[str, Any] = {"type": "embedded_resource"}
                    uri = getattr(resource, "uri", None)
                    if uri is not None:
                        resource_payload["uri"] = uri
                    text = getattr(resource, "text", None)
                    if text is not None:
                        resource_payload["text"] = text
                    data = getattr(resource, "data", None)
                    if data is not None:
                        resource_payload["data"] = data
                    normalized_blocks.append(resource_payload)
                    continue
                normalized_blocks.append(
                    {"type": type(block).__name__, "repr": repr(block)}
                )

            if not normalized_blocks:
                return None
            if len(normalized_blocks) == 1 and normalized_blocks[0]["type"] == "text":
                return normalized_blocks[0]["text"]
            return normalized_blocks


def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """同步接口，封装异步 MCP 工具调用流程。

    参数:
        tool_name (str): MCP 工具名称。
        args (Dict[str, Any]): 传入工具的参数字典。

    返回:
        Any: 工具返回的结构化或文本结果，若无内容则返回 ``None``。

    异常:
        RuntimeError: 无法启动服务器进程、工具执行失败或发生其他异常。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    else:
        loop = asyncio.new_event_loop()

    try:
        if loop is None:
            return asyncio.run(_call_tool_async(tool_name, args))
        return loop.run_until_complete(_call_tool_async(tool_name, args))
    except FileNotFoundError as exc:  # pragma: no cover - surface configuration issues clearly
        raise RuntimeError(f"Unable to start MCP server process: {exc}") from exc
    except RuntimeError as exc:
        raise
    except Exception as exc:  # pragma: no cover - generic guard for unexpected errors
        raise RuntimeError(f"MCP tool '{tool_name}' invocation failed: {exc}") from exc
    finally:
        if loop is not None:
            loop.close()
