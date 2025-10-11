# operations_dashboard/test.py
import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["MCP_BRIDGE_COMMAND"] = sys.executable
os.environ.setdefault("MCP_BRIDGE_ARGS", '["-m", "operations_dashboard.mcp_server"]')

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.stdio import stdio_client
except ImportError as exc:
    raise RuntimeError("未找到 mcp 客户端依赖，请执行 pip install -r requirements.txt") from exc

# 确保 Agent 调用通过 MCP 桥路径
os.environ["USE_MCP_BRIDGE"] = "1"

from operations_dashboard.agent import run_agent_demo
from operations_dashboard.config import (
    AmazonCredentialConfig,
    AppConfig,
    DashboardConfig,
    StorageConfig,
)
from operations_dashboard.mcp_bridge import _server_parameters, call_mcp_tool


def _assert_keys(payload: Dict[str, Any], expected: Iterable[str]) -> None:
    missing = [key for key in expected if key not in payload]
    if missing:
        raise AssertionError(f"缺失字段: {missing}, payload={payload}")


async def _probe_stdio_once() -> Tuple[int, int, int]:
    params = _server_parameters()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            if not tools.tools:
                raise AssertionError("MCP stdio 接口返回的工具列表为空")
            if not resources.resources:
                raise AssertionError("MCP stdio 接口返回的资源列表为空")
            uris = {resource.uri for resource in resources.resources}
            if "operations-dashboard://config" not in uris:
                raise AssertionError("缺少 operations-dashboard://config 资源")
            config_payload = await session.read_resource("operations-dashboard://config")
            if not config_payload.contents:
                raise AssertionError("配置资源内容为空")
            return len(tools.tools), len(resources.resources), len(prompts.prompts)


def _verify_stdio_server() -> None:
    tool_count, resource_count, prompt_count = asyncio.run(_probe_stdio_once())
    print(
        f"[stdio] 工具={tool_count}, 资源={resource_count}, 提示集={prompt_count}"
    )


def _exercise_tools_with_storage() -> None:
    print("[tools] 通过 MCP 桥执行工具并验证持久化")
    previous_enabled = os.environ.get("STORAGE_ENABLED")
    previous_db_path = os.environ.get("STORAGE_DB_PATH")
    try:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "operations.sqlite3"
            history_path = Path(tmpdir) / "history.csv"
            os.environ["STORAGE_ENABLED"] = "1"
            os.environ["STORAGE_DB_PATH"] = str(db_path)

            fetch_result = call_mcp_tool("fetch_dashboard_data", {"window_days": 7})
            _assert_keys(fetch_result, ("start", "end", "source", "sales", "traffic"))
            if not fetch_result["sales"]:
                raise AssertionError("fetch_dashboard_data 返回空的销售列表")

            summary_result = call_mcp_tool(
                "compute_dashboard_metrics",
                {
                    "start": fetch_result["start"],
                    "end": fetch_result["end"],
                    "source": fetch_result["source"],
                    "sales": fetch_result["sales"],
                    "traffic": fetch_result["traffic"],
                    "top_n": fetch_result.get("top_n"),
                },
            )
            _assert_keys(summary_result, ("summary",))
            if not db_path.exists():
                raise AssertionError("未生成预期的 SQLite 数据库文件")

            export_result = call_mcp_tool(
                "export_dashboard_history",
                {"limit": 5, "path": str(history_path)},
            )
            _assert_keys(export_result, ("message",))
            if not history_path.exists():
                raise AssertionError("未生成导出的历史 CSV 文件")
    finally:
        if previous_enabled is None:
            os.environ.pop("STORAGE_ENABLED", None)
        else:
            os.environ["STORAGE_ENABLED"] = previous_enabled
        if previous_db_path is None:
            os.environ.pop("STORAGE_DB_PATH", None)
        else:
            os.environ["STORAGE_DB_PATH"] = previous_db_path


async def _probe_http_once(server_url: str) -> Dict[str, Any]:
    async with streamablehttp_client(server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            if not tools.tools:
                raise AssertionError("HTTP 传输下工具列表为空")
            if not resources.resources:
                raise AssertionError("HTTP 传输下资源列表为空")
            return {
                "tools": [tool.name for tool in tools.tools],
                "resources": [resource.uri for resource in resources.resources],
            }


def _verify_streamable_http(server_url: str) -> None:
    info = asyncio.run(_probe_http_once(server_url))
    print(f"[http] 工具={info['tools']}, 资源={info['resources']}")


@contextmanager
def _run_http_server(host: str = "127.0.0.1", port: int = 8765):
    server_url = f"http://{host}:{port}/mcp"
    cmd = [
        sys.executable,
        "-m",
        "operations_dashboard.mcp_server",
        "streamable-http",
        "--host",
        host,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                _verify_streamable_http(server_url)
            except Exception:
                time.sleep(0.5)
                continue
            break
        else:
            raise RuntimeError("HTTP MCP 服务器启动超时")
        yield server_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _run_agent_roundtrip() -> None:
    config = AppConfig(
        amazon=AmazonCredentialConfig(
            access_key="mock",
            secret_key="mock",
            associate_tag=None,
            marketplace="US",
        ),
        dashboard=DashboardConfig(
            marketplace="US",
            refresh_window_days=7,
            top_n_products=5,
        ),
        storage=StorageConfig(enabled=False),
    )
    result = run_agent_demo(
        config, "Generate the latest daily operations report with key insights."
    )
    if not isinstance(result, dict):
        raise AssertionError("Agent 返回值应为字典")
    messages = result.get("messages")
    if not messages:
        raise AssertionError("Agent 未返回任何消息")
    last_message = messages[-1]
    content = getattr(last_message, "content", None)
    if not content:
        raise AssertionError("Agent 最后一条消息内容为空")
    print("[agent] 已完成演示交互，最后回复内容:", content)


def main() -> None:
    print("开始执行 MCP 集成测试流程")
    _verify_stdio_server()
    _exercise_tools_with_storage()
    _run_agent_roundtrip()
    with _run_http_server() as server_url:
        _verify_streamable_http(server_url)
    print("全部检测通过")


if __name__ == "__main__":
    main()
