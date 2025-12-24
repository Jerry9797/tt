from mcp.server.fastmcp import FastMCP
from mcp.server import Server
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Demo", json_response=True)


# Add an addition tool
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# mcp.run(transport="stdio")
mcp.run(transport="streamable-http")

# ----------------------------------------------
# ----------------------------------------------
# ----------------------------------------------

if __name__ == '__main__':
    """运行MCP服务器"""
    pass