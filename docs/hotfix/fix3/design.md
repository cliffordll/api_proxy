# Hotfix fix3：去掉 settings.yaml 的 mappings 和 client 段

## 需求

1. **砍掉 `mappings` 段**：模型名统一透传上游，不再做隐式改写
2. **砍掉 `client` 段**：CLI 默认值只从 `server` 段推导 `base_url`，其他用内置默认值；命令行参数覆盖

## 动机

- `mappings` 带来"传 gpt-4o 实际打到 claude-sonnet"的隐式改名，排查难；默认映射强观点，不同用户偏好不同
- `client` 段功能重复：CLI 已有 `--base-url / --route / --model` 等参数 + 内置 defaults，多加一层 YAML 覆盖增加心智负担
- 移除后数据流更直：converter 只转协议结构，不碰模型名；CLI 配置只有"CLI 参数 > server 推导 > 内置"三层

## 改动

| # | 文件 | 说明 |
|---|------|------|
| 1 | `app/core/config.py` | 删 `DEFAULT_MAPPINGS / _mappings / map_model`，`load_settings` 只接 `server_conf` |
| 2 | `app/core/loader.py` | 不再 pop `mappings` / `client`，`load_settings` 调用去掉 mappings_conf |
| 3 | `app/converters/*.py` (5 个) | 去掉 `from app.core.config import map_model` 和 `map_model(...)` 调用，模型名直接透传 |
| 4 | `cli/core/config.py` | `load_client_config` 不再读 `client` 段 |
| 5 | `config/settings.example.yaml` | 删 mappings 段 + client 段 |
| 6 | `config/settings.mockup.yaml` | 删 mappings 注释行 |
| 7 | `app/tests/test_converters/test_completions_from_messages.py` / `test_messages_from_completions.py` | 更新期望：模型名透传而非映射 |
| 8 | `README.md` / `CLAUDE.md` / `docs/architecture.md` | 删除 mappings / client 段相关描述 |

## 迁移说明

**破坏性变更**：
- 原先依赖 `mappings` 的 OpenAI SDK + gpt-4o → claude 上游用法需要显式传上游模型名（如 `model="claude-sonnet-4-6-20250514"`）
- 原先在 YAML 设置 `client:` 默认值的用户需改用命令行参数或 shell alias

**配置迁移**：
```diff
 server:
   host: 0.0.0.0
   port: 8000

-mappings:
-  openai_to_claude:
-    gpt-4o: claude-sonnet-4-6-20250514

 routes:
   completions:
     ...

-client:
-  base_url: http://localhost:8000
-  route: completions
-  model: ...
```
