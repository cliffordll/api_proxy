import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app.core.loader import load_providers


@pytest.fixture(scope="session", autouse=True)
def setup_mockup_providers():
    """测试全局使用 mockup 配置。"""
    load_providers("config/settings.mockup.yaml")
