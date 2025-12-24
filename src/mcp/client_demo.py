import asyncio

from mcp import ClientSession, StdioServerParameters



from mcp.client.sse import sse_client
async def run_client():
    # ---------------------------------------------------------
    # 场景 1: 连接 API Server
    # 路径分析: http://localhost:8000 + /api (Mount路径) + /sse (FastMCP默认SSE路径)
    # ---------------------------------------------------------
    print("--- 正在连接 API Server ---")
    async with sse_client(url="http://localhost:8000/api/sse") as (read, write):
        async with ClientSession(read, write) as session:
            # 1. 初始化并获取工具列表
            await session.initialize()
            tools = await session.list_tools()
            print(f"发现工具: {[t.name for t in tools.tools]}")

            # 2. 调用工具 'api_status'
            result = await session.call_tool("api_status")
            print(f"工具调用结果: {result.content[0].text}")

    print("\n" + "="*30 + "\n")

    # ---------------------------------------------------------
    # 场景 2: 连接 Chat Server
    # 路径分析: http://localhost:8000 + /chat (Mount路径) + /sse
    # ---------------------------------------------------------
    print("--- 正在连接 Chat Server ---")
    async with sse_client(url="http://localhost:8000/chat/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"发现工具: {[t.name for t in tools.tools]}")

            # 调用工具 'send_message'
            result = await session.call_tool("send_message", arguments={"message": "你好，MCP！"})
            print(f"工具调用结果: {result.content[0].text}")

if __name__ == "__main__":
    asyncio.run(run_client())