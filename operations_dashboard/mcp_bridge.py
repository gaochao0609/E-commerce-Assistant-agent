"""MCP 桥接模块，支持 stdio/streamable-http 长连接复用。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import Future, TimeoutError
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import EmbeddedResource, TextContent

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # pragma: no cover - optional transport
    streamablehttp_client = None


def _bridge_command() -> str:
    return os.getenv("MCP_BRIDGE_COMMAND", sys.executable)


def _bridge_args() -> str:
    return os.getenv(
        "MCP_BRIDGE_ARGS",
        json.dumps(["-m", "operations_dashboard.mcp_server"]),
    )


def _bridge_env() -> Optional[str]:
    return os.getenv("MCP_BRIDGE_ENV")


def _bridge_transport() -> str:
    return os.getenv("MCP_BRIDGE_TRANSPORT", "stdio").lower()


def _bridge_url() -> Optional[str]:
    return os.getenv("MCP_BRIDGE_URL")


def _parse_args(raw: str) -> list[str]:
    """将字符串形式的命令行参数解析为列表。"""
    try:
        value = json.loads(raw)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
    except json.JSONDecodeError:
        pass
    return [item for item in raw.split(" ") if item]


def _parse_env(raw: Optional[str]) -> Optional[Dict[str, str]]:
    """解析子进程需要的环境变量补丁。"""
    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            return value
    except json.JSONDecodeError:
        pass
    return None


def _server_parameters() -> StdioServerParameters:
    """构建 stdio 传输所需的服务器启动参数对象。"""
    command = _bridge_command()
    args = _parse_args(_bridge_args())
    base_env = dict(os.environ)
    overrides = _parse_env(_bridge_env())
    if overrides:
        base_env.update(overrides)
    env: Dict[str, str] = base_env
    return StdioServerParameters(command=command, args=args, env=env)


def _normalize_result(tool_name: str, result: Any) -> Any:
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


@dataclass
class _Request:
    kind: str
    payload: Dict[str, Any]
    future: Future


class _MCPBridge:
    def __init__(self, signature: Tuple[Any, ...]) -> None:
        self._signature = signature
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._session_ready = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._queue: Optional[asyncio.Queue[_Request]] = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()
        if not self._session_ready.wait(timeout=30):
            raise RuntimeError("MCP bridge startup timed out.")
        if self._startup_error:
            raise RuntimeError(
                f"MCP bridge startup failed: {self._startup_error}"
            ) from self._startup_error

    @property
    def signature(self) -> Tuple[Any, ...]:
        return self._signature

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()
        self._loop.create_task(self._runner())
        self._ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        self._loop.run_until_complete(
            asyncio.gather(*pending, return_exceptions=True)
        )
        self._loop.close()

    async def _runner(self) -> None:
        try:
            transport = _bridge_transport()
            if transport in {"streamable-http", "http"}:
                server_url = _bridge_url()
                if not server_url:
                    raise RuntimeError(
                        "MCP_BRIDGE_URL is required for streamable-http transport."
                    )
                if streamablehttp_client is None:
                    raise RuntimeError(
                        "streamable-http client unavailable; install mcp[cli]."
                    )
                client_cm = streamablehttp_client(server_url)
            else:
                params = _server_parameters()
                client_cm = stdio_client(params)

            async with client_cm as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session_ready.set()
                    while True:
                        if self._queue is None:
                            raise RuntimeError("MCP bridge queue is not initialized.")
                        request = await self._queue.get()
                        if request.kind == "close":
                            request.future.set_result(True)
                            break
                        try:
                            if request.kind == "call_tool":
                                tool_name = request.payload["name"]
                                args = request.payload["args"]
                                result = await session.call_tool(
                                    tool_name, arguments=args
                                )
                                output = _normalize_result(tool_name, result)
                            elif request.kind == "list_tools":
                                response = await session.list_tools()
                                tools = []
                                for tool in response.tools:
                                    input_schema = getattr(
                                        tool, "inputSchema", None
                                    )
                                    if input_schema is None:
                                        input_schema = getattr(
                                            tool, "input_schema", None
                                        )
                                    tools.append(
                                        {
                                            "name": tool.name,
                                            "description": tool.description,
                                            "input_schema": input_schema,
                                        }
                                    )
                                output = tools
                            else:
                                raise RuntimeError(
                                    f"Unknown MCP bridge request: {request.kind}"
                                )
                            request.future.set_result(output)
                        except Exception as exc:
                            request.future.set_exception(exc)
        except Exception as exc:
            self._startup_error = exc
            self._session_ready.set()

    def _submit(self, kind: str, payload: Dict[str, Any]) -> Any:
        if self._queue is None:
            raise RuntimeError("MCP bridge queue is not initialized.")
        future: Future = Future()
        request = _Request(kind=kind, payload=payload, future=future)
        asyncio.run_coroutine_threadsafe(self._queue.put(request), self._loop).result()
        return future.result()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        return self._submit("call_tool", {"name": tool_name, "args": arguments})

    def list_tools(self) -> list[dict[str, Any]]:
        return self._submit("list_tools", {})

    def close(self) -> None:
        if not self._loop.is_running():
            return
        if self._queue is not None:
            future: Future = Future()
            request = _Request(kind="close", payload={}, future=future)
            asyncio.run_coroutine_threadsafe(
                self._queue.put(request), self._loop
            ).result()
            try:
                future.result(timeout=5)
            except TimeoutError:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


_BRIDGE_LOCK = threading.Lock()
_BRIDGE: Optional[_MCPBridge] = None


def _bridge_signature() -> Tuple[Any, ...]:
    transport = _bridge_transport()
    if transport in {"streamable-http", "http"}:
        return ("streamable-http", _bridge_url())
    command = _bridge_command()
    args = tuple(_parse_args(_bridge_args()))
    env_patch = _parse_env(_bridge_env())
    env_items = tuple(sorted(env_patch.items())) if env_patch else None
    return ("stdio", command, args, env_items)


def _get_bridge() -> _MCPBridge:
    global _BRIDGE
    signature = _bridge_signature()
    with _BRIDGE_LOCK:
        if _BRIDGE is None or _BRIDGE.signature != signature:
            if _BRIDGE is not None:
                _BRIDGE.close()
            _BRIDGE = _MCPBridge(signature)
        return _BRIDGE


def list_mcp_tools() -> list[dict[str, Any]]:
    """返回 MCP 服务端注册的工具列表及其 schema。"""
    return _get_bridge().list_tools()


def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """同步接口，封装 MCP 工具调用流程。"""
    try:
        return _get_bridge().call_tool(tool_name, args)
    except FileNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(f"Unable to start MCP server process: {exc}") from exc
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"MCP tool '{tool_name}' invocation failed: {exc}") from exc


def close_mcp_session() -> None:
    """主动关闭复用的 MCP 会话（如需切换配置可调用）。"""
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is not None:
            _BRIDGE.close()
            _BRIDGE = None
