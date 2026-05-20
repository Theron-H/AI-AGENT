# AI-INF-AGENCY

## 1. 项目定位

本项目建设一个面向品牌方、MCN 和营销团队的企业级网红营销 AI Agent + 本地知识库系统。

系统不是普通聊天工具，而是一个本地优先、可沉淀资料、可检索知识、可调度营销 Skills、可审计执行过程、可扩展模型能力的营销智能工作台。它用于把品牌资料、达人信息、报价表、历史投放、合同条款、平台规则、复盘报告等资料沉淀为企业可控的本地营销知识资产。

当前版本不接入实际 AI 模型、不接入推理算力、不生成真实营销判断。所有依赖 AI 推理、RAG、机器学习、情绪识别、自动推荐、自动评分的能力，在当前阶段只保留功能模块、接口契约、数据结构和前端入口，并统一显示“能力暂不可用”。

长期目标是形成一套可本地运行、可局域网共享、可迁移远端服务器、可替换模型 Provider、可扩展业务模块、可沉淀企业知识资产的营销智能系统。

## 2. 当前版本边界

当前版本目标：

- 本地 FastAPI 服务。
- 内置 Web 控制台。
- 本地知识库录入、上传、列表、检索入口。
- 本地知识库 AI 搜索模块入口。
- 达人数据管理入口。
- Campaign 管理入口。
- Skill Registry。
- AgentRun、SkillRun、ToolCall、HumanApproval 数据结构预留。
- LLM Provider、Embedding Provider、Rerank Provider 接口预留。
- 所有 AI 能力返回统一不可用提示。

当前版本不实现：

- 真实 AI 答案生成。
- 真实语义向量检索。
- 真实达人推荐。
- 真实预算建议。
- 真实风险判断。
- 真实情绪识别。
- 真实机器学习评分。
- 自动发送邮件、自动修改预算、自动确认合作等外部动作。

## 3. 核心能力

### 3.1 本地知识库

本地知识库用于沉淀品牌资料、达人资料、报价表、合同、平台规则、历史投放、复盘报告、会议纪要等资料。

支持来源：

- 手动录入。
- CSV。
- Excel。
- Word。
- PDF。
- TXT。
- Markdown。

当前阶段能力：

- 保存原始文件。
- 保存文档元数据。
- 保存基础文本内容。
- 提供文档列表。
- 提供普通检索入口。
- 预留 chunk、embedding、citation、reindex 字段。
- AI 相关能力显示不可用。

### 3.2 本地知识库 AI 搜索

本地知识库 AI 搜索是本系统的核心功能模块之一。它区别于普通关键词检索，目标是让团队用自然语言查询本地资料，并得到带引用来源的结构化回答。

典型问题：

- 这个品牌有哪些禁用词？
- 小红书防晒品类投放有哪些注意事项？
- 去年类似预算的活动表现如何？
- 帮我找出报价高但历史转化一般的达人。
- 合同里关于内容修改次数和交付周期怎么规定？

目标能力：

- 自然语言提问。
- Query rewrite。
- 关键词检索。
- 语义检索。
- Hybrid search。
- Rerank。
- Citation 回显。
- 基于本地资料生成答案。
- 对无依据问题返回“知识库中未找到依据”。

当前阶段：

- 提供 `POST /kb/ai-search` 接口。
- 前端提供 AI 搜索入口。
- 返回统一不可用提示。
- 返回结构保持稳定，便于后续接入真实模型。

建议返回结构：

```json
{
  "query": "小红书防晒品类投放有哪些注意事项？",
  "status": "unavailable",
  "answer": null,
  "message": "本地知识库 AI 搜索能力暂不可用，当前版本未接入 AI 模型和推理算力。",
  "citations": [],
  "confidence": null,
  "not_found": false
}
```

### 3.3 AI Agent

AI Agent 是系统任务分析和编排核心。

当前阶段：

- 保留 Agent 接口。
- 保留 Skills 调度结构。
- 不执行真实 AI 推理。
- 所有依赖推理的 Skill 返回 `status: unavailable`。

后续职责：

- 理解用户 brief。
- 检索本地知识库。
- 选择 Skills。
- 汇总 Skill 输出。
- 发起人工确认。
- 写入 AgentRun、SkillRun、ToolCall 和 HumanApproval。

### 3.4 Skill Registry

Skill 是系统能力扩展单元。每个 Skill 代表一个稳定、可测试、可替换的业务动作。

基础 Skills：

- `brand_brief_analysis`：品牌 brief 分析。
- `influencer_discovery`：达人筛选。
- `campaign_strategy`：投放策略。
- `risk_analysis`：风险分析。
- `knowledge_ai_search`：本地知识库 AI 搜索。
- `local_file_ingestion`：本地文件入库。
- `contract_risk_scan`：合同与平台规则风险扫描。
- `campaign_review`：投放复盘。
- `influencer_scoring`：达人评分。

标准输出：

```json
{
  "skill": "knowledge_ai_search",
  "version": "0.1.0",
  "status": "unavailable",
  "output": {},
  "citations": [],
  "model_usage": {},
  "confidence": null,
  "next_skills": []
}
```

Skill 开发原则：

- 单一职责。
- 结构化输入输出。
- 可注册。
- 可替换。
- 可审计。
- 可被 Agent 编排。
- 可从规则版升级为 LLM、ML 或 DL 实现。

### 3.5 本地固有数据库

本地固有数据库用于保存结构化业务数据：

- 达人库。
- 品牌库。
- Campaign。
- 沟通记录。
- 投放指标。
- AgentRun。
- SkillRun。
- ToolCall。
- HumanApproval。
- SearchQueryLog。
- AISearchAnswer。
- UserFeedback。
- BackupRecord。

第一阶段可使用 JSON 或 SQLite，后续迁移 PostgreSQL。

### 3.6 个人文件库

个人文件库保存用户上传的原始文件，类似本地云盘。早期保存在本地目录，后续可迁移到 NAS、MinIO、S3 或 OSS。

建议目录：

```text
data/
  app.db
  knowledge.json
  uploads/
    workspace_default/
      original/
      extracted/
      thumbnails/
  chroma/
  models/
  exports/
  backups/
```

文件元数据字段：

```text
file_id
workspace_id
owner_id
visibility
source_type
file_name
file_ext
original_path
content_hash
size_bytes
created_at
indexed_at
```

## 4. 总体架构

```text
Presentation Layer
  Built-in Web Console
  Future React Workbench
  API Client

Application Layer
  FastAPI Routes
  Agent Use Cases
  Knowledge Use Cases
  Campaign Use Cases
  Influencer Use Cases

Agent Layer
  MarketingAgent
  TaskPlanner
  SkillRouter
  ToolExecutor
  ApprovalGate
  AuditLogger

Skill Layer
  brand_brief_analysis
  influencer_discovery
  campaign_strategy
  risk_analysis
  knowledge_ai_search
  local_file_ingestion
  contract_risk_scan
  campaign_review
  influencer_scoring

Knowledge Layer
  KnowledgeBaseService
  Local JSON Store
  Personal File Library
  KnowledgeDocument
  KnowledgeChunk
  Citation Builder
  Future Hybrid Search
  Future RAG

Business Data Layer
  LocalBusinessDatabase
  Influencer Repository
  Campaign Repository
  Communication Repository
  Metrics Repository

Provider Layer
  LLMProvider
  EmbeddingProvider
  RerankProvider
  ModelService
  StorageProvider

Infrastructure Layer
  Local Files
  SQLite
  Optional PostgreSQL
  Optional Qdrant / Chroma
  Optional MinIO
  Optional Ollama / Remote Model API
```

增强版架构：

```text
React Workbench
  Agent Drawer
  Knowledge Base Manager
  AI Search Panel
  Influencer Dashboard
  Campaign Manager
  Audit Center
  Settings

FastAPI API
  Agent Orchestrator
  Knowledge Service
  Business Data Service
  Provider Gateway

Storage
  SQLite / PostgreSQL
  Local Files / MinIO
  Chroma / Qdrant
```

## 5. 本地知识库 AI 搜索设计

### 5.1 入库流程

```text
upload file
  -> save original file
  -> detect file type
  -> extract text / table rows
  -> normalize metadata
  -> split chunks
  -> generate embeddings
  -> upsert vector index
  -> persist document and chunk records
```

当前版本只实现到可上传、可保存、可展示解析状态。`generate embeddings` 和 `upsert vector index` 作为接口和字段预留。

### 5.2 搜索流程

```text
user question
  -> intent detection
  -> query rewrite
  -> metadata filter
  -> keyword search
  -> vector search
  -> merge results
  -> rerank
  -> build cited context
  -> generate answer
  -> return answer + citations
```

当前版本保留流程结构和 API 返回结构。真实 query rewrite、vector search、rerank、generate answer 在未接入模型和算力前显示不可用。

### 5.3 Citation 字段

```text
document_id
chunk_id
title
source
file_name
page_number
row_number
created_at
score
excerpt
```

AI 搜索后续生成的每个答案都必须尽量带 citation。没有来源支撑时，不得输出确定性业务结论。

## 6. 接口设计

### 6.1 基础接口

```text
GET  /health
GET  /skills
POST /agent/analyze
```

### 6.2 知识库接口

```text
GET    /kb/documents
POST   /kb/documents
POST   /kb/upload
POST   /kb/search
POST   /kb/ai-search
POST   /kb/reindex
GET    /kb/chunks
GET    /kb/documents/{document_id}
DELETE /kb/documents/{document_id}
```

### 6.3 达人接口

```text
GET    /influencers
POST   /influencers
POST   /influencers/import
GET    /influencers/{influencer_id}
PATCH  /influencers/{influencer_id}
DELETE /influencers/{influencer_id}
```

### 6.4 Campaign 接口

```text
GET   /campaigns
POST  /campaigns
GET   /campaigns/{campaign_id}
PATCH /campaigns/{campaign_id}
GET   /campaigns/{campaign_id}/metrics
POST  /campaigns/{campaign_id}/review
```

### 6.5 Agent 审计接口

```text
GET  /agent/runs
GET  /agent/runs/{run_id}
GET  /agent/runs/{run_id}/skills
GET  /agent/runs/{run_id}/tools
POST /agent/approvals/{approval_id}
```

### 6.6 系统管理接口

```text
GET   /settings/providers
PATCH /settings/providers
GET   /system/status
POST  /system/backup
POST  /system/restore
GET   /system/audit-logs
```

## 7. 扩展性设计

### 7.1 Provider 抽象

业务层不得直接绑定某个模型厂商或 SDK。

建议接口：

```text
LLMProvider.generate(messages, tools, temperature)
EmbeddingProvider.embed(texts)
RerankProvider.rerank(query, documents)
StorageProvider.save(file)
StorageProvider.get(file_id)
ModelService.score_influencer(features)
ModelService.classify_sentiment(texts)
```

### 7.2 Repository 抽象

业务逻辑不直接绑定 JSON、SQLite、PostgreSQL、Qdrant 或 MinIO。

建议分层：

```text
KnowledgeDocumentRepository
KnowledgeChunkRepository
InfluencerRepository
CampaignRepository
AgentRunRepository
SkillRunRepository
FileRepository
```

### 7.3 Skill 插件化

新增能力优先新增 Skill，不把业务逻辑写进一个大 prompt。

```text
backend/app/skills/
  brand_brief_analysis.py
  influencer_discovery.py
  campaign_strategy.py
  risk_analysis.py
  knowledge_ai_search.py
  contract_risk_scan.py
  campaign_review.py
```

### 7.4 数据迁移

保存位置按阶段演进：

| 阶段 | 业务数据 | 文件库 | 检索索引 |
| --- | --- | --- | --- |
| 本地 MVP | JSON / SQLite | 本地目录 | JSON 检索索引 |
| 本地增强 | SQLite | 本地目录 | Chroma |
| 团队版 | PostgreSQL | MinIO / NAS | Qdrant |
| 生产版 | PostgreSQL / 云数据库 | MinIO / S3 / OSS | Qdrant / Milvus |

## 8. 前端页面设计

前端整体参考 Fima Copilot 的轻量对话式工作台风格。第一屏不做营销落地页，直接进入 AI 搜索和 Agent 工作区。

### 8.1 设计方向

- 左侧固定浅灰侧边栏。
- 中间大面积留白，突出 AI 输入框。
- 首页中央展示产品 Logo / 系统名。
- 主输入框作为核心入口，可同时用于本地知识库 AI 搜索、营销 Agent 提问、Campaign brief 输入。
- 底部展示精选示例、常用工作流、最近知识库或历史任务。
- 页面整体保持简洁、低噪音、企业级，不做复杂装饰和营销化大屏。

### 8.2 推荐页面结构

```text
左侧导航
  新对话
  本地知识库
  AI 搜索
  达人库
  Campaign
  工作流
  审计记录
  系统设置

主区域
  Logo / 系统名
  AI 输入框
  模式选择
  数据源选择
  上传附件
  发送按钮

下方区域
  精选示例
  最近搜索
  常用模板
  最近上传文件
```

### 8.3 首页交互

主输入框支持：

- 输入自然语言问题。
- 上传本地文件。
- 选择搜索模式。
- 选择知识库范围。
- 选择 Agent 任务类型。
- 发起普通搜索或 AI 搜索。

模式建议：

```text
对话模式
知识库 AI 搜索
Campaign Brief
达人筛选
风险扫描
投放复盘
```

数据源建议：

```text
全部资料
个人知识库
团队知识库
品牌资料
达人库
合同与规则
历史 Campaign
```

当前版本由于不接入真实 AI 模型和算力，选择 AI 搜索、达人筛选、风险扫描等模式时，页面应展示统一不可用提示：

```text
该能力模块已预留，当前版本暂未接入 AI 模型和推理算力。
```

### 8.4 视觉规范

- 背景：浅灰或近白色。
- 侧边栏：浅灰底，宽度约 280-320px。
- 主输入框：大圆角白色容器，带轻微阴影。
- 按钮：尽量使用图标按钮，配合 tooltip。
- 字体：清晰、克制，适合企业后台长期使用。
- 圆角：主输入框可较大，业务卡片控制在 6-8px。
- 色彩：黑白灰为主，状态色只用于成功、警告、风险。
- 避免复杂渐变、过多卡片嵌套、营销海报式布局。

### 8.5 推荐首页文案

系统名：

```text
YTH AI Agent
```

输入框 placeholder：

```text
有问题尽管问，或搜索本地知识库
```

模式按钮：

```text
对话模式
知识库 AI 搜索
营销 Agent
```

数据源按钮：

```text
全部资料
个人知识库
团队知识库
```

示例任务：

```text
查询某品牌禁用词和合同注意事项
分析小红书防晒品类投放规则
导入达人报价表并检查字段
生成夏季新品推广 Campaign 草稿
扫描合作方案中的潜在风险
```

## 9. 安全规范

- 不提交真实 API key、token、密码。
- 不提交未脱敏客户资料、合同、达人合作数据。
- `.env`、`.env.production`、`.env.test` 不提交。
- 数据库、向量库、对象存储不默认暴露到局域网或公网。
- 文件上传限制大小和类型。
- AI 搜索必须遵守 workspace、owner、visibility 权限。
- 无引用来源时不得生成确定性业务结论。
- 高风险动作必须进入 HumanApproval。

## 10. 开发排期 List

### Phase 0：项目骨架

- FastAPI 后端服务。
- 内置 Web Console。
- Skill Registry。
- 本地 JSON 知识库。
- 基础配置管理。
- `.env.example`。
- 健康检查接口。
- 不可用提示统一结构。

### Phase 1：知识库基础能力

- 手动录入知识文档。
- 文件上传。
- 文档列表。
- 普通关键词搜索。
- 原始文件保存。
- 文档元数据保存。
- 知识库详情页。
- 文档删除。
- 文档重新索引入口。
- 文件解析状态展示。

### Phase 2：本地知识库 AI 搜索模块

- `knowledge_ai_search` Skill。
- `POST /kb/ai-search`。
- AI 搜索页面。
- AI 搜索结果结构。
- Citation 字段结构。
- QueryLog 记录。
- 无模型状态下返回不可用提示。
- Provider 接口预留。
- Embedding / Rerank 接口预留。
- 后续 RAG 接入点预留。

### Phase 3：文件解析与资料入库

- CSV 解析。
- Excel 解析。
- Word 解析。
- PDF 文本抽取。
- TXT / Markdown 解析。
- chunk 元数据结构。
- 页码、行号、标题层级保留。
- 原始文件与知识切片关联。
- 文件 hash 去重。
- 解析失败记录。

### Phase 4：达人库与 Excel 导入

- 达人基础表。
- 达人平台账号。
- 粉丝数、互动率、报价字段。
- 达人标签。
- 达人 Excel 一键导入。
- 字段映射预览。
- 导入错误报告。
- 达人详情页。
- 达人筛选接口。

### Phase 5：Campaign 基础管理

- Campaign 列表。
- Campaign 创建。
- Campaign 预算字段。
- Campaign 平台字段。
- Campaign 达人组合。
- 投放节奏。
- 状态流转。
- 投放指标录入。
- Campaign 复盘入口，不可用提示。

### Phase 6：Agent 审计与运行记录

- AgentRun 数据结构。
- SkillRun 数据结构。
- ToolCall 数据结构。
- HumanApproval 数据结构。
- Agent 执行过程展示。
- Skill 调用结果展示。
- 原始 JSON 调试视图。
- 审计日志页面。

### Phase 7：知识库质量评分模块

- 文档元数据完整度检查。
- 缺失标题提示。
- 缺失来源提示。
- 缺失品牌归属提示。
- 过期资料提示。
- 重复文件检测。
- 低质量文档列表。
- 当前阶段显示规则检查结果，AI 质量判断不可用。

### Phase 8：搜索反馈机制

- 搜索结果“有用 / 无用”反馈。
- 引用错误反馈。
- 答案不准确反馈。
- 用户反馈记录。
- 反馈统计页。
- 后续 rerank 训练数据预留。

### Phase 9：AI 引用审查面板

- 答案引用来源展示。
- 每条 citation 原文片段展示。
- 文件名、页码、行号展示。
- 引用可信度字段预留。
- 引用不足提示。
- 无来源答案禁止标记为可信。

### Phase 10：合同与平台规则风险扫描

- 合同文件上传。
- 平台规则文件上传。
- 风险扫描入口。
- 风险类型结构。
- 禁用词命中结构。
- 条款风险结构。
- 当前阶段仅返回不可用提示和规则占位。
- 后续接入模型或规则引擎。

### Phase 11：Campaign 模板库

- 新品种草模板。
- 直播带货模板。
- 节日节点模板。
- KOC 铺量模板。
- 品牌声量模板。
- 模板复制为 Campaign。
- 模板版本管理。

### Phase 12：模型成本统计模块

- Provider 字段。
- Model 字段。
- Prompt tokens 字段。
- Completion tokens 字段。
- Estimated cost 字段。
- Skill name 字段。
- Campaign id 字段。
- 当前阶段无真实模型调用，字段保留为空。

### Phase 13：本地备份与恢复

- 知识库导出。
- 文件库导出。
- SQLite / JSON 导出。
- 配置导出。
- 备份记录。
- 恢复入口。
- 备份校验。
- 定期备份策略预留。

### Phase 14：权限分级

- 用户表。
- Workspace 表。
- 角色字段。
- visibility 字段。
- 个人资料。
- 团队资料。
- 管理层资料。
- API 权限检查。
- AI 搜索权限过滤。

### Phase 15：定时知识库巡检

- 未索引文件检查。
- 解析失败文件检查。
- 重复文件检查。
- 过期平台规则检查。
- 缺失来源文件检查。
- 巡检报告。
- 定时任务接口预留。

### Phase 16：向量检索与 RAG 接入

- Embedding Provider 实现。
- Chroma / Qdrant 接入。
- BM25 + Vector hybrid search。
- Rerank Provider 实现。
- Citation answer。
- AI 搜索真实答案生成。
- 搜索质量评估集。
- 检索效果调试页面。

### Phase 17：团队版与生产化

- 登录认证。
- RBAC。
- HTTPS 反向代理。
- PostgreSQL。
- MinIO。
- Qdrant。
- 审计日志。
- 数据库备份。
- 模型 token 管理。
- 远端服务器部署文档。

## 11. 验收标准

当前阶段验收：

- 系统可本地启动。
- Web Console 可访问。
- 知识库可录入。
- 文件可上传。
- 普通搜索可返回结果或空结果。
- AI 搜索入口存在，并明确显示不可用。
- Skills 可查看。
- Agent 分析接口返回结构稳定。
- 所有 AI 相关能力不输出伪结论。
- 主要接口具备清晰结构，便于后续前端和模型接入。
- 文档明确区分当前可用能力、模块入口和后续增强能力。

## 12. 后续技术原则

- 本地优先，云端可迁移。
- 接口优先，模块可替换。
- Skill 插件化，避免超级 prompt。
- Provider 抽象，避免绑定模型厂商。
- 数据可迁移，原始文件不可丢。
- AI 输出必须可追溯。
- 高风险动作必须人工确认。
- 当前阶段不伪造 AI 能力。
