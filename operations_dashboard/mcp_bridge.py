import requests
from typing import Dict, Any

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"


def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """调用 MCP 服务器上的工具并返回原始输出对象。"""

    payload = {"calls": [{"tool_name": tool_name, "args": args}]}
    response = requests.post(MCP_SERVER_URL, json=payload, timeout=10)
    response.raise_for_status()
    mcp_response = response.json()
    if not mcp_response.get("returns"):
        raise RuntimeError("MCP 响应中未包含任何工具结果。")
    tool_return = mcp_response["returns"][0]
    if tool_return.get("status") != "success":
        raise RuntimeError(
            f"工具 '{tool_name}' 调用失败：{tool_return.get('output')}"
        )
    return tool_return.get("output")
