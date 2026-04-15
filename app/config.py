from pathlib import Path
from functools import lru_cache

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 上游 URL
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # 默认参数
    default_max_tokens: int = 4096

    # 模型映射配置文件路径
    model_mapping_file: str = "config/model_mapping.yaml"

    model_config = {"env_prefix": "", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_model_mapping(path: str) -> dict:
    """加载模型映射配置，返回 {"openai_to_claude": {...}, "claude_to_openai": {...}}"""
    default_mapping = {
        "openai_to_claude": {
            "gpt-4o": "claude-sonnet-4-6-20250514",
            "gpt-4-turbo": "claude-sonnet-4-6-20250514",
            "gpt-4": "claude-opus-4-6-20250514",
            "gpt-3.5-turbo": "claude-haiku-4-5-20251001",
        },
        "claude_to_openai": {
            "claude-opus-4-6-20250514": "gpt-4",
            "claude-sonnet-4-6-20250514": "gpt-4o",
            "claude-haiku-4-5-20251001": "gpt-3.5-turbo",
        },
    }

    config_path = Path(path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            yaml_mapping = yaml.safe_load(f)
        if yaml_mapping:
            for direction in ("openai_to_claude", "claude_to_openai"):
                if direction in yaml_mapping:
                    default_mapping[direction].update(yaml_mapping[direction])

    return default_mapping


def map_model(model: str, direction: str) -> str:
    """映射模型名，未命中则透传"""
    settings = get_settings()
    mapping = load_model_mapping(settings.model_mapping_file)
    return mapping.get(direction, {}).get(model, model)
