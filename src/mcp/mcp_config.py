"""
MCP 配置管理模块
负责读取和管理 MCP 服务器配置
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """MCP 服务器配置"""
    name: str = Field(description="服务器名称")
    url: str = Field(description="服务器 URL")
    enabled: bool = Field(default=True, description="是否启用")
    description: str = Field(default="", description="服务器描述")


class MCPConfig(BaseModel):
    """MCP 总配置"""
    mcp_servers: List[MCPServerConfig] = Field(default_factory=list)


def load_mcp_config(config_path: str = None) -> MCPConfig:
    """
    加载 MCP 配置文件
    
    Args:
        config_path: 配置文件路径，默认为项目根目录下的 config/mcp_servers.json
    
    Returns:
        MCPConfig: 配置对象
    """
    if config_path is None:
        # 默认配置文件路径
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "src" / "config" / "mcp_servers.json"
    else:
        config_path = Path(config_path)
    
    # 如果配置文件不存在，返回空配置
    if not config_path.exists():
        print(f"[MCP Config] 配置文件不存在: {config_path}")
        return MCPConfig(mcp_servers=[])
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        config = MCPConfig(**data)
        print(f"[MCP Config] 成功加载配置，共 {len(config.mcp_servers)} 个服务器")
        return config
    
    except json.JSONDecodeError as e:
        print(f"[MCP Config] JSON 解析错误: {e}")
        return MCPConfig(mcp_servers=[])
    
    except Exception as e:
        print(f"[MCP Config] 加载配置失败: {e}")
        return MCPConfig(mcp_servers=[])


def get_enabled_servers(config: MCPConfig) -> List[MCPServerConfig]:
    """
    获取所有启用的服务器配置
    
    Args:
        config: MCP 配置对象
    
    Returns:
        List[MCPServerConfig]: 启用的服务器列表
    """
    return [server for server in config.mcp_servers if server.enabled]


if __name__ == "__main__":
    # 测试配置加载
    config = load_mcp_config()
    enabled = get_enabled_servers(config)
    
    print(f"\n启用的服务器 ({len(enabled)}):")
    for server in enabled:
        print(f"  - {server.name}: {server.url}")
        if server.description:
            print(f"    描述: {server.description}")
