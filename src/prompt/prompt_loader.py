"""
通用提示词加载器

从 YAML 配置文件中加载提示词，提供统一的访问接口。
"""
from typing import Optional
import yaml
from pathlib import Path


class PromptLoader:
    """通用提示词加载器"""
    
    def __init__(self, yaml_path: Optional[str] = None):
        """
        初始化提示词加载器
        
        Args:
            yaml_path: YAML 文件路径，默认为当前目录的 prompt.yaml
        """
        if yaml_path is None:
            # 默认路径: 当前文件所在目录的 prompt.yaml
            yaml_path = Path(__file__).parent / "prompt.yaml"
        self.yaml_path = Path(yaml_path)
        self._prompts = None
    
    @property
    def prompts(self) -> dict:
        """懒加载提示词字典"""
        if self._prompts is None:
            self._prompts = self._load_prompts()
        return self._prompts
    
    def _load_prompts(self) -> dict:
        """从 YAML 文件加载提示词"""
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Prompt YAML file not found: {self.yaml_path}")
        
        with open(self.yaml_path, 'r', encoding='utf-8') as f:
            prompts = yaml.safe_load(f)
        
        if not isinstance(prompts, dict):
            raise ValueError(f"Invalid prompt YAML format. Expected dict, got {type(prompts)}")
        
        return prompts
    
    def get(self, key: str, default: Optional[str] = None) -> str:
        """
        获取指定提示词
        
        Args:
            key: 提示词键名
            default: 默认值，如果键不存在则返回此值
            
        Returns:
            提示词内容
        """
        value = self.prompts.get(key, default)
        if value is None:
            raise KeyError(f"Prompt key '{key}' not found in {self.yaml_path}")
        return value
    
    def reload(self):
        """重新加载 YAML 文件"""
        self._prompts = self._load_prompts()


# 全局单例
_loader = PromptLoader()


def get_prompt(key: str, default: Optional[str] = None) -> str:
    """
    便捷函数: 获取提示词
    
    Args:
        key: 提示词键名
        default: 默认值
        
    Returns:
        提示词内容
        
    Example:
        >>> prompt = get_prompt("query_rewrite")
        >>> print(prompt[:20])
        你是一个由美团技术团队开发的...
    """
    return _loader.get(key, default)


def reload_prompts():
    """便捷函数: 重新加载提示词"""
    _loader.reload()
