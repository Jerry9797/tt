"""
MCP 工具管理器
负责管理 MCP 服务器连接、工具加载和调用
"""
import asyncio
import logging
from typing import Dict, List, Optional
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import BaseTool

from src.mcp.mcp_config import load_mcp_config, get_enabled_servers, MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolManager:
    """MCP 工具管理器 - 单例模式"""
    
    _instance: Optional['MCPToolManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化管理器"""
        if not self._initialized:
            self._sessions: Dict[str, ClientSession] = {}
            self._tools: Dict[str, List[BaseTool]] = {}  # server_name -> tools
            self._stream_contexts: Dict[str, tuple] = {}  # 保存流上下文
            self._initialized = True
    
    async def connect(self, server_config: MCPServerConfig) -> bool:
        """
        连接到 MCP 服务器
        
        Args:
            server_config: 服务器配置
        
        Returns:
            bool: 连接是否成功
        """
        server_name = server_config.name
        url = server_config.url
        
        stream_context = None
        session = None

        try:
            logger.info("正在连接到 %s (%s)...", server_name, url)
            
            # 使用 streamable_http_client 创建连接
            stream_context = streamable_http_client(url=url)
            read_stream, write_stream, _ = await stream_context.__aenter__()
            
            # 保存流上下文以便后续关闭
            self._stream_contexts[server_name] = stream_context
            
            # 创建会话
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            
            # 初始化会话
            await session.initialize()
            
            # 保存会话
            self._sessions[server_name] = session
            
            logger.info("成功连接到 %s", server_name)
            return True
        
        except BaseException as e:
            # 连接失败时显式退出已进入的上下文，避免取消作用域泄漏到后续 await。
            if session is not None:
                try:
                    await session.__aexit__(type(e), e, e.__traceback__)
                except Exception as cleanup_err:
                    logger.warning("Session cleanup failed for %s: %s", server_name, cleanup_err)

            if stream_context is not None:
                try:
                    await stream_context.__aexit__(type(e), e, e.__traceback__)
                except Exception as cleanup_err:
                    logger.warning("Stream context cleanup failed for %s: %s", server_name, cleanup_err)

            self._stream_contexts.pop(server_name, None)
            self._sessions.pop(server_name, None)

            # Handle BaseExceptionGroup from anyio/httpx
            error_msg = str(e)
            if "ConnectError" in error_msg or "connection attempts failed" in error_msg:
                logger.warning("连接 %s 失败: 无法连接到服务器 (Connection Refused)", server_name)
            else:
                logger.warning("连接 %s 失败: %s", server_name, e)
            return False
    
    async def load_tools(self, server_name: str) -> List[BaseTool]:
        """
        从 MCP 服务器加载工具
        
        Args:
            server_name: 服务器名称
        
        Returns:
            List[BaseTool]: 加载的工具列表
        """
        if server_name not in self._sessions:
            logger.warning("服务器 %s 未连接", server_name)
            return []
        
        try:
            session = self._sessions[server_name]
            
            # 使用 langchain_mcp_adapters 加载工具
            tools = await load_mcp_tools(session)
            
            # 保存工具
            self._tools[server_name] = tools

            logger.info("从 %s 加载了 %s 个工具", server_name, len(tools))
            for tool in tools:
                logger.debug("  • %s: %s", tool.name, tool.description)

            return tools

        except Exception as e:
            logger.error("从 %s 加载工具失败: %s", server_name, e)
            return []
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        获取所有已加载的工具
        
        Returns:
            List[BaseTool]: 所有工具列表
        """
        all_tools = []
        for server_name, tools in self._tools.items():
            all_tools.extend(tools)
        return all_tools
    
    def get_tools_by_server(self, server_name: str) -> List[BaseTool]:
        """
        获取指定服务器的工具
        
        Args:
            server_name: 服务器名称
        
        Returns:
            List[BaseTool]: 工具列表
        """
        return self._tools.get(server_name, [])
    
    async def disconnect(self, server_name: str):
        """
        断开与指定服务器的连接
        
        Args:
            server_name: 服务器名称
        """
        if server_name in self._sessions:
            try:
                session = self._sessions[server_name]
                await session.__aexit__(None, None, None)
                
                # 关闭流上下文
                if server_name in self._stream_contexts:
                    stream_context = self._stream_contexts[server_name]
                    await stream_context.__aexit__(None, None, None)
                    del self._stream_contexts[server_name]
                
                del self._sessions[server_name]
                if server_name in self._tools:
                    del self._tools[server_name]
                
                logger.info("已断开 %s", server_name)
            except Exception as e:
                logger.warning("断开 %s 时出错: %s", server_name, e)
    
    async def disconnect_all(self):
        """断开所有连接"""
        server_names = list(self._sessions.keys())
        for server_name in server_names:
            await self.disconnect(server_name)
    
    def get_connected_servers(self) -> List[str]:
        """获取已连接的服务器名称列表"""
        return list(self._sessions.keys())
    
    def get_tool_count(self) -> int:
        """获取工具总数"""
        return len(self.get_all_tools())


# 全局管理器实例
_manager: Optional[MCPToolManager] = None
_init_lock = asyncio.Lock()


async def init_mcp_manager(config_path: str = None) -> MCPToolManager:
    """
    初始化 MCP 工具管理器（异步）
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        MCPToolManager: 管理器实例
    """
    global _manager
    
    async with _init_lock:
        if _manager is None:
            _manager = MCPToolManager()
        
        # 加载配置
        config = load_mcp_config(config_path)
        enabled_servers = get_enabled_servers(config)
        
        if not enabled_servers:
            logger.info("没有启用的 MCP 服务器")
            return _manager

        logger.info("开始初始化，共 %s 个服务器", len(enabled_servers))
        
        # 连接所有启用的服务器
        for server_config in enabled_servers:
            success = await _manager.connect(server_config)
            if success:
                # 加载工具
                await _manager.load_tools(server_config.name)
        
        logger.info(
            "初始化完成，已连接 %s 个服务器，共 %s 个工具",
            len(_manager.get_connected_servers()),
            _manager.get_tool_count(),
        )
        
        return _manager


def get_mcp_manager() -> MCPToolManager:
    """
    获取 MCP 工具管理器实例（同步）
    
    注意：在使用前必须先调用 init_mcp_manager()
    
    Returns:
        MCPToolManager: 管理器实例
    """
    global _manager
    
    if _manager is None:
        logger.warning("管理器未初始化，返回空管理器")
        _manager = MCPToolManager()
    
    return _manager


async def cleanup_mcp_manager():
    """清理 MCP 管理器，断开所有连接"""
    global _manager
    
    if _manager is not None:
        await _manager.disconnect_all()
        logger.info("已清理所有连接")
        _manager = None


# 测试代码
if __name__ == "__main__":
    async def test():
        """测试 MCP 管理器"""
        print("=== 测试 MCP 工具管理器 ===\n")
        
        # 初始化
        manager = await init_mcp_manager()
        
        # 显示连接状态
        print(f"\n已连接服务器: {manager.get_connected_servers()}")
        
        # 显示所有工具
        all_tools = manager.get_all_tools()
        print(f"\n所有工具 ({len(all_tools)}):")
        for tool in all_tools:
            print(f"  - {tool.name}: {tool.description}")
        
        # 清理
        await cleanup_mcp_manager()
        print("\n测试完成")
    
    # 运行测试
    asyncio.run(test())
