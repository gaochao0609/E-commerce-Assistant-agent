from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal

# 从我们的工具文件中导入注册表
from tools import TOOL_REGISTRY

# --- 1. 定义数据模型 (使用Pydantic) ---
# 定义一个工具调用的结构
class ToolCall(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)

# 定义客户端发来的MCP请求体
class MCPRequest(BaseModel):
    calls: List[ToolCall]

# 定义服务器返回的工具执行结果的结构
class ToolReturn(BaseModel):
    tool_name: str
    status: Literal["success", "failed"]
    output: Any

# 定义服务器对MCP请求的最终响应体
class MCPResponse(BaseModel):
    returns: List[ToolReturn]

# --- 2. 创建FastAPI应用实例 ---
app = FastAPI(
    title="amazon bestseller search",
    description="使用 PAAPI 查询指定类目的畅销商品榜单。"
)

# --- 3. 创建核心API端点 ---
@app.post("/mcp", response_model=MCPResponse)
def handle_mcp_request(request: MCPRequest) -> MCPResponse:
    """
    处理来自AI Agent的MCP请求，执行工具调用并返回结果。
    """
    print(f"\n收到MCP请求，包含 {len(request.calls)} 个工具调用。")
    
    results = []
    
    # 遍历请求中的每一个工具调用
    for call in request.calls:
        tool_name = call.tool_name
        args = call.args
        
        print(f"正在处理工具调用: {tool_name}，参数: {args}")
        
        # 检查工具是否存在于我们的注册表中
        if tool_name in TOOL_REGISTRY:
            tool_function = TOOL_REGISTRY[tool_name]
            try:
                # 执行工具函数，并将参数解包传入
                output = tool_function(**args)
                results.append(ToolReturn(tool_name=tool_name, status="success", output=output))
            except Exception as e:
                # 如果工具执行出错
                results.append(ToolReturn(tool_name=tool_name, status="failed", output=str(e)))
        else:
            # 如果请求的工具不存在
            results.append(ToolReturn(tool_name=tool_name, status="failed", output=f"工具 '{tool_name}' 未找到。"))
            
    return MCPResponse(returns=results)

@app.get("/")
def read_root():
    return {"message": "MCP Server 正在运行！请向 /mcp 端点发送POST请求。"}