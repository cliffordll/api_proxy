# CLAUDE.md

## 技术栈

- Python 3.10+ / FastAPI / openai SDK / anthropic SDK / httpx / pyyaml / rich
- 测试: pytest + pytest-asyncio

## 编码规范

- 所有 I/O 使用 async/await
- 转换器（converters/）必须是纯函数，无 I/O，无副作用，输入输出统一 dict/str
- Client 层统一 `chat()` 接口，输入 dict，输出 dict（非流式）/ AsyncIterator[str]（流式），SDK 细节封装在内部
- Proxy 封装 Client + Converter，路由层通过 `proxy.chat()` 一行调用
- 流式响应使用 SSE 格式
- 配置统一通过 config/settings.yaml 管理（server + routes）
- 路由配置通过 from 字段推导 converter，不配则自动透传
- 统一入口 main.py（server / chat / test 子命令）
- CLI 模块（cli/）独立于服务代码（app/），不 import app/
- 不硬编码 API 密钥
- 模型名全部透传，不在代理层改写
- 做好封装，保持模块间职责清晰、接口稳定，便于后续扩展和替换

## 开发流程规范

开发任务必须通过 `docs/process.md` 进行管理。每个 Phase 下依次包含：
- **任务表**：编号、任务、说明、产出文件、状态（待开始/进行中/完成/阻塞）
- **执行记录**：每完成一个任务步骤，在此记录实现说明、测试数据、测试结果、验收结论
- 每个 Phase 自成一节，任务表和执行记录紧挨着，便于对照查看

**流程**：先创建完整计划 → 用户审核确认 → 严格按计划执行 → 逐步更新执行记录和任务状态

**确认机制**：
- 每个 Phase 和每个任务步骤执行完毕后，都必须等待用户确认，确认通过后再继续下一步。不得跳过确认自行推进
- 用户提问（"能不能 X？"、"为什么 Y？"、"...是不是更好？"）**默认是讨论意图**，先给分析和建议，等用户明确指令再动手，**不要直接执行**
- 代码风格讨论、设计权衡问题属于探索性对话；方案未定之前不要写代码

**提交机制**：代码改动不自动提交，须等待用户验证通过并下达提交指令后再提交到 git 并推送。commit message 中不添加 Co-Authored-By 信息。

## 代码风格偏好

- **优先内敛而非抽象**：只有单处调用者时，倾向于内联或降级为内部函数 / 局部变量；不为"未来可能用到"预埋泛化接口
- **慎用薄抽象**：如果抽取的函数/类仅减少几行重复，考虑它是否真的提升可读性；抽象不应只为对称而存在
- **模块职责单一**：跨层复用的纯工具函数放在 `common/` 或 `cli/core/`；与某个业务场景强绑定的逻辑（如 chat 启动探测）就放在对应子模块
- **展示风格统一**：终端输出同一概念用同一格式（路由表 + 状态符号 + 缩进模型列表 + 黄 `*` 标记当前），不同场景（welcome / probe / picker）复用同一渲染
- **命令行文案**：路由相关命令在前（`/route` `/routes`），模型命令在后（`/model` `/models`）
- **透传为默认**：模型名、API key 等用户输入**直接透传上游**，代理层不做隐式改写
- **冗余提示及时清理**：welcome / 状态行已经表达的信息不要再用 footer 重复

## 封装取舍

- 新增类的门槛：有状态（init 持参数）+ 多个方法协作
- 纯函数保持独立，不为了和类对称而塞进 `@staticmethod`
- 类内部方法互相调用用 `self.xxx`，不用裸类名
- 外部只暴露入口方法（如 `Probe.run()`），helper 一律加 `_` 前缀

## Hotfix 规范

### 文档管理
每次创建 hotfix 时，在 `docs/hotfix/` 下新增文件夹，命名规则为 `fix1`、`fix2` 依次递增。每个文件夹内存放该 hotfix 的设计方案（`design.md`）和开发计划（`process.md`）。

如果存在 `docs/hotfix/` 目录，在读完整体架构文档（`docs/architecture.md`、`docs/feature.md`）之后，必须补充读取 `docs/hotfix/` 下的所有设计文档，作为对现有架构的补丁说明。

### 执行规则
- 每个 Phase 执行完毕后，等待用户确认再继续下一步
- 全部 Phase 完成后，整体等待用户下达提交指令再提交到 git，不逐步提交
- hotfix 的开发计划和执行记录在 `docs/hotfix/fixN/process.md` 中管理，不在主 `docs/process.md` 中记录

## 文档归档规范

docs/ 下的文档日常直接放在根目录使用。当用户发出归档指令（如"归档"、"存档"等）时：
1. 扫描 `docs/history/` 下已有的 v* 目录，确定下一个版本号（从 v0.1 开始，依次 v0.2, v0.3...）
2. 在 `docs/history/` 下创建对应版本目录（如 `docs/history/v0.2/`）
3. 将 docs/ 根目录下的文档文件移动到该版本目录中
4. 如果存在 `docs/hotfix/` 目录，一并移动到归档版本目录中（如 `docs/history/v0.2/hotfix/`）
5. 版本号自动管理，用户不需要指定
6. 归档后的文件只读不写，不得修改已归档版本目录中的任何文件

## 文档索引

- 项目说明: README.md
- 架构设计: docs/architecture.md
- 开发计划: docs/feature.md
- 开发过程记录: docs/process.md
- Hotfix 文档: docs/hotfix/
- 归档历史: docs/history/
