"""
SOP配置加载器
从YAML文件加载完整的场景配置（steps + tools + prompt）
"""

import yaml
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class SOPConfig:
    """SOP完整配置"""
    key: str
    name: str
    description: str
    category: str
    owner: str
    steps: List[str]
    tools: List[str]
    planning_prompt: str
    metrics: Dict[str, Any]
    
    def __repr__(self):
        return f"SOPConfig(key={self.key}, name={self.name}, steps={len(self.steps)}, tools={len(self.tools)})"


class SOPConfigLoader:
    """SOP配置加载器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), 
                "sop_config.yaml"
            )
        
        self.config_path = config_path
        self.sops: Dict[str, SOPConfig] = {}
        self._load()
    
    def _load(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f)
            
            if not raw_config:
                print(f"[SOPLoader] Warning: Empty config file")
                return
            
            for key, config in raw_config.items():
                if not isinstance(config, dict):
                    continue
                
                self.sops[key] = SOPConfig(
                    key=key,
                    name=config.get('name', key),
                    description=config.get('description', ''),
                    category=config.get('category', 'other'),
                    owner=config.get('owner', 'unknown'),
                    steps=config.get('steps', []),
                    tools=config.get('tools', []),
                    planning_prompt=config.get('planning_prompt', ''),
                    metrics=config.get('metrics', {})
                )
            
            print(f"[SOPLoader] Loaded {len(self.sops)} SOP configurations")
            
        except FileNotFoundError:
            print(f"[SOPLoader] Error: Config file not found: {self.config_path}")
        except Exception as e:
            print(f"[SOPLoader] Error loading config: {e}")
            import traceback
            traceback.print_exc()
    
    def get_sop(self, key: str) -> Optional[SOPConfig]:
        """获取指定SOP配置"""
        return self.sops.get(key)
    
    def get_steps(self, key: str) -> List[str]:
        """获取SOP步骤"""
        sop = self.get_sop(key)
        return sop.steps if sop else []
    
    def get_tools(self, key: str) -> List[str]:
        """获取SOP需要的工具列表（工具名称）"""
        sop = self.get_sop(key)
        return sop.tools if sop else []
    
    def get_planning_prompt(self, key: str) -> str:
        """获取Planning Prompt模板"""
        sop = self.get_sop(key)
        return sop.planning_prompt if sop else ""
    
    def get_intent_dict(self) -> Dict[str, str]:
        """获取intent字典（用于意图识别）
        
        Returns:
            {intent_key: name}
        """
        return {key: sop.name for key, sop in self.sops.items()}
    
    def get_all_sop_keys(self) -> List[str]:
        """获取所有SOP的key"""
        return list(self.sops.keys())
    
    def has_sop(self, key: str) -> bool:
        """检查是否存在指定的SOP"""
        return key in self.sops
    
    def reload(self):
        """重新加载配置"""
        self.sops.clear()
        self._load()


# ============================================================================
# 全局单例
# ============================================================================

_sop_loader: Optional[SOPConfigLoader] = None


def get_sop_loader() -> SOPConfigLoader:
    """获取SOP加载器单例"""
    global _sop_loader
    if _sop_loader is None:
        _sop_loader = SOPConfigLoader()
    return _sop_loader


def reload_sop_config():
    """重新加载SOP配置（用于热更新）"""
    global _sop_loader
    if _sop_loader:
        _sop_loader.reload()
    else:
        _sop_loader = SOPConfigLoader()


# ============================================================================
# 便捷函数
# ============================================================================

def get_sop_steps(intent: str) -> List[str]:
    """快捷方式：获取步骤"""
    return get_sop_loader().get_steps(intent)


def get_sop_tools(intent: str) -> List[str]:
    """快捷方式：获取工具列表"""
    return get_sop_loader().get_tools(intent)


def get_sop_prompt(intent: str) -> str:
    """快捷方式：获取prompt"""
    return get_sop_loader().get_planning_prompt(intent)


if __name__ == "__main__":
    # 测试
    loader = get_sop_loader()
    print(f"\n加载的SOP: {loader.get_all_sop_keys()}")
    
    for key in loader.get_all_sop_keys():
        sop = loader.get_sop(key)
        print(f"\n{sop}")
        print(f"  Steps: {len(sop.steps)}")
        print(f"  Tools: {sop.tools}")
        print(f"  Has prompt: {bool(sop.planning_prompt)}")
