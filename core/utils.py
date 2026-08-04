"""工具函数"""

import os
import yaml
from pathlib import Path

try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件，支持环境变量替换"""
    # 加载 .env 文件
    env_path = Path(".env")
    if env_path.exists() and HAS_DOTENV:
        load_dotenv(env_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 替换 ${ENV_VAR} 格式的环境变量
    config = _resolve_env_vars(config)
    return config


def _resolve_env_vars(obj):
    """递归替换配置中的环境变量"""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            env_name = obj[2:-1]
            return os.environ.get(env_name, obj)
        return obj
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def format_duration(seconds: int) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        return f"{seconds // 60}分钟"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}小时{minutes}分钟"


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
