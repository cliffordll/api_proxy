# Hotfix fix3 开发过程记录

---

| # | 任务 | 说明 | 产出文件 | 状态 |
|---|------|------|---------|------|
| 1 | app/core 侧清理 | 删 map_model / mappings 状态，load_settings 简化 | `app/core/config.py`、`app/core/loader.py` | 完成 |
| 2 | converters 清理 | 5 个 converter 去掉 map_model 调用 | `app/converters/*.py` | 完成 |
| 3 | cli 侧清理 | load_client_config 不再读 client 段 | `cli/core/config.py` | 完成 |
| 4 | YAML 模板清理 | 删 mappings + client 段 | `config/settings.example.yaml`、`config/settings.mockup.yaml` | 完成 |
| 5 | 测试修正 | 2 个 converter 测试改为期望透传 | `app/tests/test_converters/*.py` | 完成 |
| 6 | 文档清理 | README / CLAUDE / architecture 同步 | `README.md`、`CLAUDE.md`、`docs/architecture.md` | 完成 |
| 7 | 验证 | 85 passed | — | 完成 |

**执行记录**：

- **Phase 1 — app/core**：`DEFAULT_MAPPINGS / _mappings / map_model` 全部删除；`load_settings(server_conf)` 去掉 `mappings_conf` 参数；`loader.py` 不再 pop `mappings` / `client`
- **Phase 2 — converters**：4 个 converter 去掉 `map_model(request["model"], ...)` 调用，改为直接 `request["model"]`；1 个（responses_from_completions）原本就只 import 没调，一并清理
- **Phase 3 — cli**：`load_client_config` 不再读 `client` 段，只保留从 `server` 段推导 `base_url`；`DEFAULT_CLIENT_CONFIG` 保留（route/model/api_key/stream 内置默认值）
- **Phase 4 — YAML**：`settings.example.yaml` 删 mappings + client 段；`settings.mockup.yaml` 删 mappings 注释行
- **Phase 5 — 测试**：`test_completions_from_messages::test_basic` 和 `test_messages_from_completions::test_basic` 的 `req["model"]` 期望改为透传（gpt-4o→gpt-4o、claude-sonnet-4-6→claude-sonnet-4-6）
- **Phase 6 — 文档**：README 配置示例移除 mappings / client 段，特性列表"模型名自动映射"改为"模型名透传"；CLAUDE.md 同步；architecture.md 移除相关片段
- **Phase 7 — 验证**：`pytest` 全量 85 passed
