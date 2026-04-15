import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import register_providers

# 确保测试时 Provider 已注册
register_providers()
