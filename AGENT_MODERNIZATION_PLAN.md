# 电商内容 Agent 现代化改造方案

> **状态说明（2026-08-11）**：本文档为远期架构规划。当前实现已覆盖阶段一～四的大部分能力（异步任务+SQLite持久化、图片/视频生成、Pydantic Schema 校验、配置管理），尚未迁移至 LangGraph。详见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 1. 文档目标

本文档用于规划电商内容生产项目从“线性 Agent 编排器”升级为完整、可恢复、可观测的多智能体系统。

目标不是简单增加 Agent 数量，而是建立一套可控的 Agent 工作流：有明确状态、有动态路由、有知识依据、有失败恢复，也能在本地 Mock 模式和云端服务模式下运行。

## 2. 当前项目评估

当前项目已经实现了以下闭环：

```text
商品理解 -> 文案生成 -> SEO -> 合规检查 -> 质量评分 -> 自动重写 -> 输出
```

现有优势：

- 已有商品理解、文案、SEO、合规、评分、重写等清晰的领域 Agent。
- 具备 Mock、vLLM、Transformers 和外部 API 等模型后端抽象。
- 已有质量评分、确定性指标和三路模型对比评估。
- 已有 FastAPI 与 Docker 基础，可以继续演进为服务化系统。

主要不足：

- 当前 `ContentOrchestrator` 是线性同步流程，状态不能持久化和恢复。
- Agent 路由主要由代码顺序决定，缺少 Supervisor 动态决策。
- 合规知识、品牌规则、商品目录和竞品信息还没有形成可检索知识库。
- 失败重试、任务队列、人工审核、成本统计和链路追踪不完整。
- 文档中的训练、GRPO、云端大模型和实验结果，需要与实际可运行代码明确区分。

## 3. 目标架构

目标系统采用 LangGraph 作为图编排层，以 Supervisor 负责动态路由，以结构化状态作为 Agent 之间的唯一通信协议。

```text
                         +------------------+
                         |  API / SSE       |
                         +--------+---------+
                                  |
                         +--------v---------+
                         | Task Queue       |
                         | Redis            |
                         +--------+---------+
                                  |
                         +--------v---------+
                         | LangGraph Worker |
                         +--------+---------+
                                  |
              +-------------------v-------------------+
              | Typed AgentState + Checkpoint         |
              +-------------------+-------------------+
                                  |
                         +--------v---------+
                         | Supervisor       |
                         +--+-----+----+----+
                            |     |    |
             +--------------+     |    +----------------+
             |                    |                     |
      商品理解 Agent       文案/SEO Agent       合规/评审 Agent
             |                    |                     |
             +--------------------v---------------------+
                                  |
                         质量判断与路由
                          /      |       \
                    通过    重写回路    人工审核
                          \      |       /
                           +-----v------+
                             最终输出
                                  |
                         Postgres + pgvector
                         OpenTelemetry
```

## 4. 核心状态机设计

新增统一 `AgentState`，至少包含以下字段：

- `task_id`：任务唯一标识。
- `product`：标准化后的商品输入。
- `requirements`：平台、语气、长度和业务约束。
- `retrieved_knowledge`：规则、品牌、商品和竞品证据。
- `understanding`：商品理解结果。
- `content`：标题、卖点、详情和社媒文案。
- `seo_result`：关键词和 SEO 分析结果。
- `compliance_result`：违规项、风险等级和审核摘要。
- `quality_score`：四维评分及原因。
- `rewrite_history`：每轮重写前后结果、原因和评分。
- `current_node`、`status`、`retry_count`、`errors`：执行控制信息。
- `events`：面向 SSE 和审计的节点事件。

工作流节点：

1. `intake`：校验输入并建立任务。
2. `retrieve`：并行检索平台规则、品牌资料、商品目录和竞品信息。
3. `understand`：分析商品属性、卖点、目标人群和使用场景。
4. `supervisor`：根据当前状态选择下一步 Agent。
5. `copywriting`：生成多平台内容。
6. `seo`：生成关键词并检查覆盖度。
7. `compliance`：确定性规则与 LLM 双重审核。
8. `judge`：进行准确性、吸引力、合规性和 SEO 评分。
9. `rewrite`：根据低分维度和违规项定向重写。
10. `human_review`：高风险或多轮失败时暂停等待人工处理。
11. `finalize`：输出结果、引用证据和审计信息。

路由规则：

- 合规高风险：进入人工审核。
- 合规失败但风险可控：进入重写。
- 质量未达标且未超过重写上限：进入重写。
- 质量达标：进入最终输出。
- 超过重写上限：进入人工审核或失败状态。
- 节点异常：按节点策略重试，超过次数后进入错误状态。

通过 LangGraph checkpoint 保存状态，使任务支持暂停、恢复、重放和故障后的继续执行。Supervisor 只负责决策，不直接生成最终文案，避免职责混乱。

## 5. 多智能体分层

保留现有 Agent 的业务职责，统一输入输出格式：

- `ProductUnderstandingAgent`：解析商品属性，提炼卖点和目标人群。
- `CopywritingAgent`：生成标题、五点卖点、详情页文案和社媒文案。
- `SEOAgent`：生成核心词、长尾词和平台关键词建议。
- `ComplianceAgent`：执行违禁词、事实一致性和平台规则检查。
- `JudgeAgent`：输出四维质量评分和改进建议。
- `RewriteAgent`：根据具体失败维度定向重写。
- `SupervisorAgent`：决定下一步任务和是否结束工作流。
- `RetrievalAgent`：统一检索知识并整理证据。
- `ValidationAgent`：校验 JSON、字段完整性、长度、卖点数量和关键词格式。

每个 Agent 的结果都应包含：

```json
{
  "result": {},
  "confidence": 0.0,
  "evidence": [],
  "warnings": [],
  "token_usage": {},
  "latency_ms": 0,
  "model_version": ""
}
```

所有模型输出必须经过 Pydantic Schema 校验。解析失败时自动重试一次，并将错误写入状态和观测链路。

## 6. RAG 与知识库

第一阶段同时建设两类知识：

### 规则知识

- 广告法和绝对化用语规则。
- 淘宝、Amazon、抖音、小红书等平台审核规则。
- 类目限制、敏感词和禁限售规则。
- 品牌语气、品牌禁用表达和内容模板。

### 商品知识

- 商品目录和标准属性。
- 历史商品文案。
- 竞品摘要和关键词。
- 平台搜索词与类目关键词。

统一知识文档字段：

- 文档 ID、来源、版本、生效时间。
- 平台、类目、品牌等 metadata。
- 原文片段和检索分数。
- 被哪个 Agent 使用。

云端默认使用 Postgres + pgvector；本地模式使用 SQLite 和内存检索。所有合规相关引用必须能够追溯到具体规则版本。

## 7. API 与服务化

新接口采用异步任务 + SSE：

- `POST /v1/tasks`：创建生成任务并返回 `task_id`。
- `GET /v1/tasks/{task_id}`：查询任务状态和最终结果。
- `GET /v1/tasks/{task_id}/events`：SSE 推送节点事件。
- `POST /v1/tasks/{task_id}/resume`：从人工审核或失败节点恢复。
- `POST /v1/tasks/{task_id}/cancel`：取消任务。
- `GET /health/live`：进程存活检查。
- `GET /health/ready`：数据库、队列和模型服务就绪检查。

现有 `/generate` 保留为兼容层，内部转换为任务执行并等待最终状态。新接口使用版本化 Pydantic Schema，不再把任意 `dict` 作为主要公共协议。

服务拆分为：

- API 服务：接收请求、鉴权、返回任务状态和 SSE。
- Worker：执行 LangGraph 工作流。
- Redis：任务队列、事件流和短期缓存。
- Postgres：任务状态、checkpoint、结果和审核记录。
- pgvector：知识库向量检索。
- OpenTelemetry Collector：收集追踪和指标。

## 8. 可靠性、安全与观测

每个任务和 Agent 节点都记录：

- trace、span、节点名称和路由决策。
- 模型版本、耗时、token 和估算成本。
- 检索来源、命中证据和规则版本。
- 重试次数、重写轮次和失败原因。
- 最终质量分、人工审核结果和用户反馈。

系统需要具备：

- 节点超时和指数退避重试。
- task_id 幂等，避免重复生成和重复扣费。
- 最大总耗时、最大模型调用次数和最大重写轮次。
- 敏感字段脱敏和环境变量密钥管理。
- 基础鉴权、请求限流和审计日志。
- 高风险内容默认暂停，等待人工审核。

模型继续使用 OpenAI 兼容协议，兼容 vLLM、OpenAI、国产 API 和 Mock 后端。

## 9. 实施阶段

### 阶段一：状态和图编排

- 增加 LangGraph、Pydantic 及异步执行依赖。
- 将现有 Agent 包装为图节点。
- 实现 `AgentState`、Supervisor 和条件路由。
- 保留原有 `ContentOrchestrator` 作为兼容适配层。
- 完成 Mock 模式下的完整图流程。

### 阶段二：结构化输出和校验

- 为商品理解、文案、SEO、合规、评分和重写定义输出 Schema。
- 增加字段缺失、格式错误、长度和卖点数量校验。
- 增加模型 JSON 解析失败重试。
- 为每个节点保存输入、输出和错误信息。

### 阶段三：RAG 与合规增强

- 增加知识文档导入和切分脚本。
- 实现平台规则、品牌资料、商品目录和竞品检索。
- 引入规则版本、生效时间和证据引用。
- 将确定性合规规则与 RAG 证据传递给 ComplianceAgent。

### 阶段四：异步任务和持久化

- 增加 Redis、Postgres 和 pgvector 配置。
- 拆分 API 与 Worker。
- 增加任务创建、查询、取消、恢复和 SSE 接口。
- 增加 checkpoint、事件表和人工审核记录。

### 阶段五：观测和评估

- 接入 OpenTelemetry。
- 增加成本、延迟、重试、路由和节点成功率统计。
- 增加轨迹评估、合规误报/漏报和证据覆盖率指标。
- 固定回归样本，比较线性编排、固定图、Supervisor 和 RAG 版本。

### 阶段六：开源发布

- 更新 Docker Compose，提供 local 和 cloud profiles。
- 更新 README、API 示例、架构图和故障排查文档。
- 增加 `.env.example`、迁移脚本和知识库示例数据。
- 明确标注已实现能力与训练、GRPO、云端大模型等规划能力。

## 10. 测试与验收标准

- `quick_start.py` 在无 GPU、无外部服务环境下仍可运行。
- 一个任务能够经过完整状态图并保存节点结果。
- 任务暂停后可以从 checkpoint 恢复。
- 高风险内容不能直接返回合规通过。
- SSE 能实时返回节点开始、完成、重试、审核和结束事件。
- 同一 task 重复消费不会重复生成或重复扣费。
- 所有 LLM 输出均通过结构化校验。
- local 模式和 cloud 模式均有明确启动方式。
- 旧 `/generate` 调用保持可用，新 `/v1/tasks` 接口完成异步任务闭环。
- 回归评估中，改造后的准确性、合规性和结构化输出通过率不能出现未解释的下降。

## 11. 设计边界

- 第一阶段使用 LangGraph，不实现独立自研 Graph Engine；通过工作流接口保留替换空间。
- Supervisor 采用受限路由，不允许无限 Agent 循环。
- 默认最大重写轮次为 2，最大模型调用次数和总耗时可配置。
- 人工审核为可选能力，高风险任务默认暂停；本地演示环境可关闭。
- Postgres、Redis、pgvector 和 OpenTelemetry 属于 cloud profile，本地模式不强制安装。
- 本轮优先完善推理、编排、知识增强和评估链路，不把完整 GRPO 训练当作系统可用性的前置条件。
