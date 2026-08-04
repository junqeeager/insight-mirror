"""插件管理器"""

import importlib
import sys
from pathlib import Path
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from core.models import Event


class DataSourcePlugin(ABC):
    """数据源插件基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    def icon(self) -> str:
        return "📦"

    @property
    def description(self) -> str:
        return ""

    @abstractmethod
    def setup(self, config: dict) -> None:
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        pass

    @abstractmethod
    def fetch(self, since: datetime) -> List[Event]:
        pass

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "available": True,
        }

    def cleanup(self) -> None:
        pass


class PluginManager:
    """插件管理器"""

    def __init__(self, plugins_dir: str, config: dict):
        self.plugins_dir = Path(plugins_dir)
        self.config = config
        self._plugins: dict[str, type] = {}
        self._instances: dict[str, DataSourcePlugin] = {}

    def discover(self) -> List[str]:
        """自动发现插件"""
        discovered = []
        for path in self.plugins_dir.iterdir():
            if not path.is_dir():
                continue
            plugin_file = path / "plugin.py"
            if not plugin_file.exists():
                continue

            # 将项目根目录加入 sys.path（如果还没有的话）
            project_root = str(self.plugins_dir.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            try:
                module = importlib.import_module(f"plugins.{path.name}.plugin")
                plugin_class = getattr(module, "Plugin")
                self._plugins[path.name] = plugin_class
                discovered.append(path.name)
            except (ImportError, AttributeError) as e:
                print(f"[PluginManager] 加载插件 {path.name} 失败: {e}")

        return discovered

    def load(self, name: str) -> DataSourcePlugin:
        """加载并初始化插件"""
        if name not in self._instances:
            if name not in self._plugins:
                raise KeyError(f"插件 {name} 未注册")
            plugin_class = self._plugins[name]
            instance = plugin_class()
            source_config = self.config.get("sources", {}).get(name, {})
            instance.setup(source_config.get("config", {}))
            self._instances[name] = instance
        return self._instances[name]

    def get_enabled_plugins(self) -> List[DataSourcePlugin]:
        """获取所有已启用的插件"""
        enabled = []
        for name, source_config in self.config.get("sources", {}).items():
            if source_config.get("enabled", False) and name in self._plugins:
                enabled.append(self.load(name))
        return enabled

    def get_all_plugins(self) -> dict:
        """获取所有已发现的插件信息"""
        result = {}
        for name in self._plugins:
            try:
                instance = self.load(name)
                result[name] = {
                    "name": instance.name,
                    "display_name": instance.display_name,
                    "version": instance.version,
                    "icon": instance.icon,
                    "description": instance.description,
                    "enabled": self.config.get("sources", {}).get(name, {}).get("enabled", False),
                }
            except Exception:
                result[name] = {"name": name, "available": False}
        return result

    def sync_all(self, since: datetime) -> dict:
        """同步所有已启用的数据源"""
        results = {}
        for plugin in self.get_enabled_plugins():
            try:
                events = plugin.fetch(since)
                results[plugin.name] = {
                    "success": True,
                    "count": len(events),
                    "events": events,
                }
            except Exception as e:
                results[plugin.name] = {
                    "success": False,
                    "error": str(e),
                    "events": [],
                }
        return results
