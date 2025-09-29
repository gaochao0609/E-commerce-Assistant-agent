"""轻量级 HTTP 桥梁，用于代理 MCP 工具调用。"""

from typing import Any, Dict

import requests

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"
# 默认 MCP FastAPI 服务端点地址，必要时可通过环境变量或配置重写。

def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """
    功能说明:
        通过 HTTP POST 调用 MCP 服务器上的指定工具，并将返回结果转换为原始数据。
    参数:
        tool_name (str): 需要调用的 MCP 工具名称。
        args (Dict[str, Any]): 传递给 MCP 工具的 JSON 参数集合。
    返回:
        Any: 工具返回的原始输出数据。
    异常:
        RuntimeError: 当 MCP 返回不包含成功结果或标识失败时抛出。
    """
    # 1. 构造 MCP 规范要求的一次 batch 调用负载。
    payload = {"calls": [{"tool_name": tool_name, "args": args}]}
    # 2. 将请求发送至 FastAPI 端点，并设置 10 秒超时避免长时间阻塞。
    response = requests.post(MCP_SERVER_URL, json=payload, timeout=10)
    response.raise_for_status()
    # 3. 解析返回体结构并校验基础结果是否存在。
    mcp_response = response.json()
    if not mcp_response.get("returns"):
        raise RuntimeError("MCP 响应中不包含任何工具返回内容")
    tool_return = mcp_response["returns"][0]
    if tool_return.get("status") != "success":
        raise RuntimeError(
            f"工具 '{tool_name}' 调用失败: {tool_return.get('output')}"
        )
    # 4. 返回正常工具响应中的主要数据字段。
    return tool_return.get("output")
