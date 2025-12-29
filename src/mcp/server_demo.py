from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Demo", json_response=True, port=9901)


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# mcp.run(transport="stdio")


# ----------------------------------------------
# ----------------------------------------------
# ----------------------------------------------

if __name__ == '__main__':
    """运行MCP服务器"""
    mcp.run(transport="streamable-http")