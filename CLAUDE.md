# CLAUDE.md

## 技术栈

- Python 3.11+ / FastAPI / httpx / pydantic-settings / pyyaml
- 测试: pytest + pytest-asyncio

## 编码规范

- 所有 I/O 使用 async/await
- 转换器（converters/）必须是纯函数，无 I/O，无副作用
- 流式响应使用 SSE 格式
- 配置统一通过 pydantic-settings，不直接 os.environ
- 不硬编码 API 密钥
- content 块使用多态类型设计，预留多模态扩展
- 模型映射从 config/model_mapping.yaml 加载，未命中则透传

## 开发流程规范

每完成一个任务步骤，必须同步更新 `docs/process.md`，记录：
1. 当前完成的任务编号和内容
2. 关键实现说明（如有）
3. 测试数据和测试结果
4. 阶段验收结论（通过/失败及原因）

## 文档索引

- 项目说明: README.md
- 架构设计: docs/architecture.md
- 开发计划: docs/feature.md
- 开发过程记录: docs/process.md
