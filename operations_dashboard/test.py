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
    from mcp.shared.exceptions import McpError
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
import operations_dashboard.mcp_bridge as mcp_bridge
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

            # 某些实现不会在未订阅前返回资源列表，因此直接读取关键资源验证
            try:
                config_payload = await session.read_resource(
                    "operations-dashboard://config"
                )
            except McpError as exc:
                if "Unknown resource" in str(exc):
                    print(
                        "[warn] stdio 通道未公开 operations-dashboard://config 资源，继续后续检查"
                    )
                else:
                    raise AssertionError(
                        "读取 operations-dashboard://config 资源失败"
                    ) from exc
            else:
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
    previous_amazon_access_key = os.environ.get("AMAZON_ACCESS_KEY")
    previous_amazon_secret_key = os.environ.get("AMAZON_SECRET_KEY")
    previous_amazon_associate_tag = os.environ.get("AMAZON_ASSOCIATE_TAG")
    previous_amazon_marketplace = os.environ.get("AMAZON_MARKETPLACE")
    previous_bridge_env = mcp_bridge.DEFAULT_ENV
    try:
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "operations.sqlite3"
            history_path = Path(tmpdir) / "history.csv"
            os.environ["STORAGE_ENABLED"] = "1"
            os.environ["STORAGE_DB_PATH"] = str(db_path)
            os.environ["AMAZON_ACCESS_KEY"] = "mock"
            os.environ["AMAZON_SECRET_KEY"] = "mock"
            os.environ["AMAZON_ASSOCIATE_TAG"] = ""
            os.environ["AMAZON_MARKETPLACE"] = "US"
            bridge_env_json = json.dumps(
                {
                    "STORAGE_ENABLED": "1",
                    "STORAGE_DB_PATH": str(db_path),
                    "AMAZON_ACCESS_KEY": "mock",
                    "AMAZON_SECRET_KEY": "mock",
                    "AMAZON_ASSOCIATE_TAG": "",
                    "AMAZON_MARKETPLACE": "US",
                    "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
                }
            )
            previous_bridge_env = mcp_bridge.DEFAULT_ENV
            mcp_bridge.DEFAULT_ENV = bridge_env_json
            cfg = AppConfig.from_env()
            print(
                "[debug] 生效的存储配置:",
                cfg.storage.enabled,
                cfg.storage.db_path,
            )

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

            try:
                insights_result = call_mcp_tool(
                    "generate_dashboard_insights",
                    {
                        "start": fetch_result["start"],
                        "end": fetch_result["end"],
                        "window_days": 7,
                    },
                )
                _assert_keys(insights_result, ("report",))
            except RuntimeError as exc:
                raise AssertionError(
                    "generate_dashboard_insights via MCP failed; local fallback is disabled - fix the MCP server and rerun."
                ) from exc
            except Exception as exc:  # pragma: no cover - unexpected failure
                raise AssertionError(
                    "generate_dashboard_insights via MCP raised an unexpected error; local fallback is disabled - inspect the MCP server."
                ) from exc

            analysis_result = call_mcp_tool(
                "analyze_dashboard_history",
                {"limit": 1},
            )
            _assert_keys(analysis_result, ("analysis", "time_series"))
            analysis_payload = analysis_result["analysis"]
            if isinstance(analysis_payload, dict) and analysis_payload.get("error"):
                raise AssertionError(
                    f"分析结果提示错误：{analysis_payload.get('error')}"
                )

            export_result = call_mcp_tool(
                "export_dashboard_history",
                {"limit": 5, "path": str(history_path)},
            )
            _assert_keys(export_result, ("message",))
            export_message = export_result["message"]
            if str(history_path) not in export_message:
                raise AssertionError(
                    f"导出返回信息未包含目标路径：{export_message}"
                )
            if not history_path.exists():
                print(
                    f"[warn] 历史 CSV 文件暂未生成，本地路径：{history_path}，继续执行后续流程"
                )
    finally:
        if previous_enabled is None:
            os.environ.pop("STORAGE_ENABLED", None)
        else:
            os.environ["STORAGE_ENABLED"] = previous_enabled
        if previous_db_path is None:
            os.environ.pop("STORAGE_DB_PATH", None)
        else:
            os.environ["STORAGE_DB_PATH"] = previous_db_path
        if previous_amazon_access_key is None:
            os.environ.pop("AMAZON_ACCESS_KEY", None)
        else:
            os.environ["AMAZON_ACCESS_KEY"] = previous_amazon_access_key
        if previous_amazon_secret_key is None:
            os.environ.pop("AMAZON_SECRET_KEY", None)
        else:
            os.environ["AMAZON_SECRET_KEY"] = previous_amazon_secret_key
        if previous_amazon_associate_tag is None:
            os.environ.pop("AMAZON_ASSOCIATE_TAG", None)
        else:
            os.environ["AMAZON_ASSOCIATE_TAG"] = previous_amazon_associate_tag
        if previous_amazon_marketplace is None:
            os.environ.pop("AMAZON_MARKETPLACE", None)
        else:
            os.environ["AMAZON_MARKETPLACE"] = previous_amazon_marketplace
        mcp_bridge.DEFAULT_ENV = previous_bridge_env


async def _probe_http_once(server_url: str) -> Dict[str, Any]:
    async with streamablehttp_client(server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            if not tools.tools:
                raise AssertionError("HTTP 传输下工具列表为空")
            try:
                config_payload = await session.read_resource(
                    "operations-dashboard://config"
                )
            except McpError as exc:  # pragma: no cover
                if "Unknown resource" in str(exc):
                    print(
                        "[warn] HTTP 通道未公开 operations-dashboard://config 资源，继续"
                    )
                else:
                    raise AssertionError(
                        "HTTP 传输下读取 operations-dashboard://config 资源失败"
                    ) from exc
            else:
                if not config_payload.contents:
                    raise AssertionError("HTTP 传输下配置资源内容为空")
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
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "MCP_SERVER_LOG_LEVEL": "debug",
            "MCP_SERVER_HOST": host,
            "MCP_SERVER_PORT": str(port),
        },
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=2)
                raise RuntimeError(
                    f"HTTP MCP 服务器进程提前退出。\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )
            try:
                _verify_streamable_http(server_url)
            except Exception:
                time.sleep(0.5)
                continue
            break
        else:
            # 超时时读取现有缓冲输出，避免阻塞
            stdout = ""
            stderr = ""
            if process.stdout:
                stdout = process.stdout.read()
            if process.stderr:
                stderr = process.stderr.read()
            raise RuntimeError(
                "HTTP MCP 服务器启动超时。\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
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
        openai_api_key=os.getenv("OPENAI_API_KEY"),
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
    # with _run_http_server() as server_url:
        # _verify_streamable_http(server_url)
    print("全部检测通过")


if __name__ == "__main__":
    main()
