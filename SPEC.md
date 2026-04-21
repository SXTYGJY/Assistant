# DataIntelOperation — 开发规格说明书 (DEV_SPEC)

> 版本：2.0 | 日期：2026-04-20

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 核心特点](#2-核心特点)
- [3. 技术选型](#3-技术选型)
- [4. 系统架构与模块设计](#4-系统架构与模块设计)
- [5. 数据库设计](#5-数据库设计)
- [6. 评估体系](#6-评估体系)
- [7. 项目排期与验收指标](#7-项目排期与验收指标)
- [8. 可扩展性与未来展望](#8-可扩展性与未来展望)

---

## 1. 项目概述

DataIntelOperation 是一个面向数据团队的**智能数据助手**，以 LangChain ReAct Agent 为核心驱动，通过自主工具调用完成元数据查询与知识检索任务。用户通过自然语言提问，Agent 自主规划推理路径、选择合适工具、校验回答质量，最终生成有依据的结构化回答。

### 设计理念

#### 1️⃣ Agent-First 架构
摒弃传统的 if/else 意图路由，改用 ReAct（Reasoning + Acting）Agent 自主决策调用哪些工具、以何种顺序调用。Agent 的每一步推理都可被追踪和审计，体现真实的 Agent 工程能力。

#### 2️⃣ 可插拔组件设计
LLM Provider、向量库后端、检索策略、记忆后端均通过统一抽象接口封装，配置文件驱动切换，零代码修改即可完成组件替换，便于 A/B 测试与迭代优化。

#### 3️⃣ 全链路可观测
每次 Agent 推理生成唯一 `trace_id`，记录工具调用序列、检索中间结果、记忆注入内容、自我反思过程，通过本地 Dashboard 可视化展示，系统行为透明可审计。

#### 4️⃣ 量化评估驱动
引入 Ragas 评估框架，对 RAG 检索质量（Context Relevance、Answer Faithfulness、Answer Relevance）和 Agent 行为（工具调用准确率、冗余调用率）进行量化评估，每个开发阶段有明确的验收指标。

---

## 2. 核心特点

### 2.1 ReAct Agent 与工具调用

Agent 基于 LangChain `AgentExecutor` 实现 ReAct 循环，具备以下工具集：

| 工具名称 | 功能描述 | 触发场景 | 引入 Phase |
|---------|---------|---------|-----------|
| `search_table_metadata` | 模糊匹配表名/表注释，返回表结构与描述 | 用户询问某张表的用途、结构 | Phase A |
| `search_column_metadata` | 模糊匹配列名/列注释，返回字段定义 | 用户询问某个字段的含义、类型 | Phase A |
| `hybrid_search_knowledge` | BM25 + Dense 混合检索知识库，RRF 融合排序 | 用户询问指标定义、业务规则等文档内容 | Phase B |
| `verify_answer` | 检查回答是否有检索依据支撑（自我反思） | Agent 生成回答后自动触发校验 | Phase E |
| `trace_lineage` | 正向追溯指标依赖的字段/表（Cypher 查询 Neo4j） | 用户询问某指标依赖哪些字段 | Phase G |
| `impact_analysis` | 反向分析字段/表变更影响的下游指标 | 用户询问某字段变更的影响范围 | Phase G |

### 2.2 混合检索（Hybrid Search）

替代现有的纯向量检索，采用两路并行召回 + RRF 融合：

- **稠密检索（Dense）**：DashScope `text-embedding-v3` 生成向量，ChromaDB 余弦相似度检索
- **稀疏检索（Sparse/BM25）**：`rank_bm25` 库维护倒排索引，关键词精确匹配
- **融合算法（RRF）**：`Score = 1/(k + Rank_Dense) + 1/(k + Rank_Sparse)`，k=60

### 2.3 父块子块切分（Parent-Child Chunking）

文档入库采用两级切分策略：

```
原始文档
    ↓
父块（~1000字，按段落/标题语义切分）  ← 存储于 ChromaDB parent collection，用于返回上下文
    ↓
子块（~200字，细粒度切分，含父块引用）  ← 用于向量检索，命中后扩展到父块
```

LangChain `ParentDocumentRetriever` 原生支持此模式，检索精准度与上下文完整性兼顾。

### 2.4 分层记忆管理（Hierarchical Memory）

```
短期记忆（Short-term）
    - 最近 5 轮对话原文
    - LangChain ConversationBufferWindowMemory
    - 存储于内存，会话结束后触发压缩

    ↓ 触发条件：超过 5 轮 或 会话结束

长期记忆（Long-term）
    - LLM 对历史对话做摘要压缩，提取关键信息
    - LangChain ConversationSummaryMemory
    - 持久化到 MySQL memory_summaries 表

每次 `complex` 路径 Agent 推理：短期记忆原文 + 长期摘要 一并注入 System Prompt；simple/out_of_scope 路径不注入记忆
```

### 2.5 轻量查询路由（QueryRouter）

所有问题直接走 ReAct 会造成不必要的延迟和 token 消耗。系统在 Agent 入口前设置一个轻量路由层，用 `qwen-turbo` 做单轮分类，将查询分流到最合适的处理路径。

**路由分类标签：**

| 标签 | 含义 | 处理路径 | 预期延迟 |
|------|------|---------|---------|
| `simple_table` | 明确询问某张表的定义/用途/结构 | 直接调用 `search_table_metadata`，跳过 AgentExecutor | ~500ms |
| `simple_column` | 明确询问某个字段/列的含义/类型 | 直接调用 `search_column_metadata`，跳过 AgentExecutor | ~500ms |
| `complex` | 混合意图、指标定义、需多步推理 | 走完整 ReAct Agent | ~2000ms |
| `out_of_scope` | 与数据元数据/业务知识库无关的问题 | 直接返回固定提示，不进入 Agent | <100ms |

**`out_of_scope` 判断标准：** 问题与以下三类均无关：数据表结构、字段定义、业务指标/规则知识库。例如"帮我写首诗"、"今天天气怎么样"直接拦截，返回："您好，我是数据助手，仅支持数据元数据和业务指标相关问题的查询。"

**路由流程：**
```
用户输入
    │
    ▼
QueryRouter（qwen-turbo 单轮分类，~200ms）
    │
    ├── simple_table  ──► search_table_metadata → 直接返回
    ├── simple_column ──► search_column_metadata → 直接返回
    ├── complex       ──► DataAgent（ReAct 完整推理）
    └── out_of_scope  ──► 固定拒绝提示 → 直接返回
```

**引入 Phase：** Phase A（与 Agent 骨架同步实现）

---

### 2.6 防幻觉三道防线

LLM 幻觉是 RAG 系统的核心风险。本项目采用"拦截 → 约束 → 校验"三层防御体系：

**第一道：生成前拦截（QueryRouter）**

`out_of_scope` 路由直接拦截超出知识范围的问题，不进入 Agent，从源头避免 LLM 在无依据情况下自由发挥。

**第二道：生成中约束（System Prompt）**

Agent 的 System Prompt 中注入强约束规则：
```
【重要约束】
1. 你只能基于工具返回的内容（Observation）回答问题
2. 若工具未返回相关信息，必须明确告知用户"未找到相关数据"，不得自行推断或编造
3. 引用数据时须标注来源（表名/文档名），不得模糊表述
4. 禁止对工具未覆盖的领域给出任何建议或推断
```

**第三道：生成后校验（verify_answer，Phase E）**

Agent 生成 Final Answer 后自动调用 `verify_answer` 工具，逐条检查关键论断是否有 Observation 支撑。发现无依据断言时触发二次检索并修正，校验结果写入 Trace。

**三道防线覆盖范围：**

| 防线 | 时机 | 解决的幻觉类型 | 引入 Phase |
|------|------|-------------|-----------|
| QueryRouter 拦截 | 生成前 | 超范围问题（无知识支撑的自由发挥） | Phase A |
| System Prompt 约束 | 生成中 | 工具有返回但 LLM 过度推断 | Phase A |
| verify_answer 校验 | 生成后 | 细粒度论断无依据（漏网之鱼） | Phase E |

---

### 2.7 自我反思（Self-Reflection）

Agent 生成回答后自动调用 `verify_answer` 工具：
- 检查回答中的每个关键论断是否有检索文档支撑
- 若发现"无依据断言"，触发二次检索并修正回答
- 反思结果记录到 Trace，可在 Dashboard 中查看

### 2.8 全链路可观测性

每次 Agent 推理生成结构化 Trace，写入 `logs/traces.jsonl`：

```json
{
  "trace_id": "uuid",
  "timestamp": "2026-04-20T10:00:00",
  "user_query": "...",
  "agent_steps": [
    {"step": 1, "tool": "hybrid_search_knowledge", "input": "...", "output": "...", "latency_ms": 320},
    {"step": 2, "tool": "verify_answer", "input": "...", "output": "verified", "latency_ms": 180}
  ],
  "memory_injected": {
    "short_term_turns": 3,
    "long_term_summary": "...",
    "memory_injected": true
  },
  "final_answer": "...",
  "total_latency_ms": 1240,
  "evaluation": {"context_relevance": 0.87, "answer_faithfulness": 0.92}
}
```

> `evaluation` 字段在 Phase E 引入 Ragas 后才填充，Phase A-D 该字段为 `null`。`memory_injected` 标志由代码层控制（complex 路径为 true，其余为 false），用于支撑 6.3 的 `memory_hit_rate` 统计（注入记忆的请求中，经手工标注有效利用记忆的比例）。

---

## 3. 技术选型

### 3.1 技术栈总览

| 层次 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangChain 0.2.x（AgentExecutor + LCEL） | ReAct Agent、工具调用、记忆管理 |
| LLM | 阿里云通义千问（DashScope）`qwen-plus` | 主推理模型，可配置切换 |
| Embedding | DashScope `text-embedding-v3`（1024维） | 向量化，可配置切换 |
| 向量库 | ChromaDB（本地持久化） | 替代 Doris，原生支持 LangChain |
| 稀疏检索 | rank_bm25 | BM25 倒排索引，轻量无依赖 |
| 关系数据库 | MySQL 8.x | 用户、对话历史、元数据、记忆摘要 |
| Web 框架 | Flask 3.0.2 | 保留现有前端与认证体系 |
| 评估框架 | Ragas + 自定义指标 | RAG 质量评估 |
| 可观测 Dashboard | Streamlit | 本地轻量 Web UI |
| 图数据库 | Neo4j（本地） | 数据血缘图存储与查询（Phase G） |
| 配置管理 | settings.yaml（PyYAML） | 替代硬编码 config.py |

### 3.2 移除的组件

| 组件 | 原因 |
|------|------|
| Apache Doris | 仅用于向量存储，ChromaDB 完全替代，本地开发更轻量 |
| `intent_recognition.py` | 被 ReAct Agent 自主决策替代 |
| `rag.py`（旧） | 被 `agent.py` + 工具模块替代 |

### 3.3 配置文件结构（settings.yaml）

```yaml
llm:
  provider: dashscope        # dashscope | openai | ollama
  model: qwen-plus
  api_key: ${DASHSCOPE_API_KEY}

embedding:
  provider: dashscope
  model: text-embedding-v3
  dimensions: 1024

vector_store:
  backend: chroma            # chroma | qdrant（未来扩展）
  persist_dir: ./data/chroma

retrieval:
  sparse_backend: bm25
  fusion_algorithm: rrf
  rrf_k: 60
  top_k_dense: 10
  top_k_sparse: 10
  top_k_final: 5
  rerank_backend: none       # none | cross_encoder（未来扩展）

memory:
  short_term_window: 5       # 保留最近 N 轮
  summary_model: qwen-turbo  # 摘要压缩使用的模型

chunking:
  parent_chunk_size: 1000
  parent_chunk_overlap: 0      # 父块按语义边界切分，不设重叠
  child_chunk_size: 200
  child_chunk_overlap: 20

evaluation:
  enabled: true
  backends: [ragas, custom_metrics]
  golden_set_path: ./data/eval/golden_set.json

observability:
  log_file: logs/traces.jsonl
  detail_level: standard     # minimal | standard | verbose

dashboard:
  enabled: true
  port: 8501

lineage:
  neo4j_uri: bolt://localhost:7687
  neo4j_user: neo4j
  neo4j_password: ${NEO4J_PASSWORD}
  enabled: false             # Phase G 启用
```

---

## 4. 系统架构与模块设计

### 4.1 整体架构

```
用户浏览器（Flask 前端，保留现有页面）
    │
    ▼
Flask Web 应用 (app.py)
    │
    ├── 认证模块（login / register / logout）—— 保留不变
    │
    ├── POST /api/chat
    │       │
    │       ▼
    │   QueryRouter (router.py)                              [Phase A]
    │   qwen-turbo 单轮分类
    │       │
    │       ├── simple_table  ──► search_table_metadata → 直接返回
    │       ├── simple_column ──► search_column_metadata → 直接返回
    │       ├── out_of_scope  ──► 固定拒绝提示 → 直接返回
    │       └── complex
    │               │
    │               ▼
    │           DataAgent (agent.py)
    │           LangChain AgentExecutor + ReAct
    │       │
    │       ├── Tool: search_table_metadata    ──► MySQL 元数据查询        [Phase A]
    │       ├── Tool: search_column_metadata   ──► MySQL 元数据查询        [Phase A]
    │       ├── Tool: hybrid_search_knowledge  ──► BM25 + ChromaDB + RRF  [Phase B]
    │       └── Tool: verify_answer            ──► LLM 自我反思校验        [Phase E]
    │       │
    │       ├── Memory: HierarchicalMemory                              [Phase C]
    │       │       ├── 短期：ConversationBufferWindowMemory
    │       │       └── 长期：ConversationSummaryMemory → MySQL
    │       │
    │       └── TraceContext → logs/traces.jsonl
    │
    ├── POST /api/upload（管理员）
    │       │
    │       ▼
    │   IngestionPipeline (ingestion/pipeline.py)
    │       ├── DocumentLoader（多格式解析）
    │       ├── ParentChildSplitter（父块子块切分）
    │       ├── EmbeddingEncoder（DashScope）
    │       └── ChromaStore + BM25Indexer
    │
    └── Streamlit Dashboard (dashboard/)
            ├── 系统总览                    [Phase D]
            ├── 数据浏览器                  [Phase D]
            ├── Ingestion 管理              [Phase D]
            ├── Agent 追踪                  [Phase D]
            ├── 评估面板                    [Phase E]
            └── 血缘图                      [Phase G]
```

### 4.2 模块详细设计

#### 4.2.1 `router.py` — 轻量查询路由

**职责：** Agent 入口前的分流层，用 `qwen-turbo` 单轮分类，将查询路由到最合适的处理路径

**核心类：** `QueryRouter`

```python
class QueryRouter:
    def __init__(self, settings: Settings): ...
    def route(self, query: str) -> RouteResult: ...
    # RouteResult: {label: str, confidence: float, keyword: str}
```

**分类 Prompt 设计：**
```
你是一个查询分类器，将用户问题分为以下四类之一，只输出标签和关键词，格式：标签:关键词

- simple_table：明确询问某张表的定义、用途、结构
- simple_column：明确询问某个字段/列的含义、类型
- complex：混合意图、指标定义、需多步推理、或无法归入前两类的数据问题
- out_of_scope：与数据表、字段、业务指标完全无关的问题

示例：
"订单表是干什么的" → simple_table:订单表
"amount字段什么含义" → simple_column:amount
"GMV怎么计算" → complex:GMV
"帮我写首诗" → out_of_scope:
```

**`out_of_scope` 固定回复：**
> "您好，我是数据助手，仅支持数据元数据查询和业务指标相关问题。如需其他帮助，请联系相关团队。"

#### 4.2.2 `agent.py` — ReAct Agent 核心

**职责：** 封装 LangChain AgentExecutor，管理工具注册、记忆注入、Trace 生成

**核心类：** `DataAgent`

```python
class DataAgent:
    def __init__(self, settings: Settings): ...
    def run(self, query: str, user_id: int) -> AgentResponse: ...
    def _build_tools(self) -> List[BaseTool]: ...
    def _build_memory(self, user_id: int) -> HierarchicalMemory: ...
```

**ReAct 循环流程：**
1. 注入系统 Prompt（角色定义 + 工具说明 + 记忆上下文）
2. LLM 输出 `Thought → Action → Action Input`
3. 执行对应工具，获取 `Observation`
4. 重复直到 LLM 输出 `Final Answer`
5. （Phase E 起）触发 `verify_answer` 自我反思，若无依据则重新检索
6. 写入 TraceContext，持久化对话历史

**多工具调用场景（混合意图）：**

当用户问题同时涉及多个信息域（如"订单表的 GMV 指标怎么计算？"同时涉及表结构和指标定义），Agent 需依次调用多个工具并合并结果。SPEC 对此明确两条约束：

**约束 1 — 工具调用软顺序（Prompt 层约束）：**

系统 Prompt 中注入以下优先级规则，引导 Agent 按信息依赖关系排序调用：
```
工具调用优先级：
1. 先调用结构性工具（search_table_metadata / search_column_metadata）获取数据定义
2. 再调用语义性工具（hybrid_search_knowledge）获取业务规则与指标逻辑
3. 最后综合所有 Observation 生成回答
```
这是软约束（Prompt 引导），不在代码层强制顺序，保留 Agent 在特殊情况下自主调整的灵活性。

**约束 2 — 多源结果合并规范（Prompt 层约束）：**

系统 Prompt 中明确告知 LLM 如何整合不同格式的工具返回：
```
当你收到多个工具的 Observation 时：
- 元数据工具返回结构化表格信息，用于描述"是什么"
- 知识检索工具返回文档片段，用于描述"怎么算/为什么"
- 最终回答须将两者有机整合，先说明数据结构，再解释业务逻辑，不得割裂呈现
```

**典型多意图推理链路示例：**
```
用户：订单表的 GMV 指标怎么计算？

Thought: 需要先了解订单表结构，再查 GMV 的计算逻辑
Action: search_table_metadata
Input: "订单表"
Observation: [表名: order, 字段: order_id, amount, status, ...]

Thought: 已有表结构，现在查 GMV 指标定义
Action: hybrid_search_knowledge
Input: "GMV 指标定义 计算逻辑"
Observation: [GMV = 成交总金额，包含已支付订单的 amount 求和...]

Thought: 两部分信息齐全，可以综合回答
Final Answer: 订单表（order）中，GMV 通过对 status='paid' 的记录求 amount 字段之和计算得出...
```

#### 4.2.3 `tools/` — 工具模块

每个工具独立文件，继承 `BaseTool`，接口统一：

```
tools/
├── base.py                  # BaseTool 抽象类 + MockTool 基类
├── metadata_tools.py        # search_table_metadata, search_column_metadata
├── retrieval_tool.py        # hybrid_search_knowledge
├── reflection_tool.py       # verify_answer
└── lineage_tools.py         # trace_lineage, impact_analysis（Phase G）
```

**MockTool 设计（Harness 可测试性）：**

`base.py` 中提供 `MockTool` 基类，允许在不调用真实 LLM/DB 的情况下测试 Agent 推理逻辑：

```python
class MockTool(BaseTool):
    def __init__(self, name: str, fixed_response: str): ...
    def _run(self, query: str) -> str:
        return self.fixed_response  # 返回预设结果，不调用外部服务
```

用途：验证 Agent 工具调用顺序是否符合软约束（结构性工具先于语义性工具），以及多工具结果合并逻辑，无需真实数据库或 API Key。

**`hybrid_search_knowledge` 内部流程：**
```
输入 Query
    ├── Dense 路：Embedding → ChromaDB 子块检索 → Top-10
    ├── Sparse 路：关键词提取 → BM25 检索 → Top-10
    └── RRF 融合 → Top-5 → 扩展到父块 → 返回
```

#### 4.2.4 `memory/` — 分层记忆模块

```
memory/
├── hierarchical_memory.py   # 组合短期+长期记忆，统一接口
├── short_term.py            # ConversationBufferWindowMemory（窗口=5）
└── long_term.py             # ConversationSummaryMemory + MySQL 持久化
```

**记忆写入规则：**
- 仅 `complex` 路径（DataAgent.run() 完成后）写入短期记忆
- `simple_table`、`simple_column` 路径跳过 AgentExecutor，不写记忆
- `out_of_scope` 路径在 QueryRouter 层拦截，不写记忆
- 长期摘要仅在 `complex` 路径注入 Agent System Prompt，simple/out_of_scope 路径不注入

**记忆压缩触发逻辑：**
- 条件：短期记忆超过 5 轮，或用户主动结束会话
- 动作：调用 `qwen-turbo` 对超出窗口的历史做摘要
- 摘要写入 MySQL `memory_summaries` 表，下次会话自动加载

#### 4.2.5 `ingestion/` — 文档入库流水线

```
ingestion/
├── pipeline.py              # IngestionPipeline 主流程
├── loaders.py               # 多格式文档解析（txt/md/pdf/docx/json/csv/xlsx）
├── splitter.py              # ParentChildSplitter
├── encoder.py               # EmbeddingEncoder（DashScope）
└── stores.py                # ChromaStore + BM25Indexer
```

**`IngestionPipeline.run()` 流程：**
```
load → split(parent+child) → embed(child chunks) → upsert(chroma+bm25) → record(mysql)
```

**分段契约（Harness 可测试性）：**

每步有独立的输入/输出类型，可单独测试，不依赖下游组件：

| 步骤 | 输入 | 输出 |
|------|------|------|
| `load` | 文件路径 | `List[Document]` |
| `split` | `List[Document]` | `List[ParentChildPair]` |
| `embed` | `List[str]`（子块文本） | `List[List[float]]`（向量） |
| `upsert` | `List[ParentChildPair]` + 向量 | 写入确认 |
| `record` | 文件元信息 | MySQL 记录 ID |

切分逻辑（`splitter.py`）可在无 ChromaDB 和 DashScope 的情况下独立单测。

#### 4.2.6 `observability/` — 可观测性模块

```
observability/
├── trace.py                 # TraceContext，记录 Agent 推理链路
├── logger.py                # JSON Lines 结构化日志写入
└── dashboard/
    ├── app.py               # Streamlit 入口
    └── pages/
        ├── overview.py      # 系统总览（组件配置 + 数据统计）         [Phase D]
        ├── data_browser.py  # 数据浏览器（文档 + Chunk 详情）         [Phase D]
        ├── ingestion.py     # Ingestion 管理（上传 + 进度 + 删除）    [Phase D]
        ├── agent_traces.py  # Agent 追踪（推理链路 + 工具调用详情）    [Phase D]
        ├── evaluation.py    # 评估面板（Ragas 指标 + 历史趋势）       [Phase E]
        └── lineage.py       # 血缘图可视化                           [Phase G]
```

#### 4.2.7 `evaluation/` — 评估模块

```
evaluation/
├── ragas_evaluator.py       # Ragas 指标评估（Context Relevance 等）
└── agent_evaluator.py       # Agent 行为指标（工具准确率等）

data/eval/
└── golden_set.json          # 标注测试集（问题 + 标准答案 + 参考文档）
```

#### 4.2.8 `datasource.py` — MySQL 元数据查询（保留升级）

保留现有 `MySQLConnector`，新增统一返回格式，供工具模块调用。

#### 4.2.9 `config.py` → `settings.py` — 配置管理升级

从硬编码 `config.py` 迁移到 `settings.yaml` + `settings.py`（PyYAML 加载，支持环境变量覆盖）。

---

## 5. 数据库设计

### 5.1 MySQL（保留 + 新增）

#### 保留表（结构不变）
- `users` — 用户表
- `conversations` — 对话历史表
- `meta_tables` — 表元数据
- `meta_columns` — 列元数据
- `file_uploads` — 文件上传记录

#### 新增表

**`memory_summaries` — 长期记忆摘要表**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| user_id | INT | 关联用户 |
| summary | TEXT | LLM 生成的对话摘要 |
| covered_turns | INT | 摘要覆盖的对话轮数 |
| created_at | DATETIME | 摘要生成时间 |
| updated_at | DATETIME | 最后更新时间 |

### 5.2 ChromaDB（替代 Doris）

**Collection：`knowledge_parent`** — 父块存储（仅用于返回上下文，不参与向量检索）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 父块唯一 ID |
| document | string | 父块原文（~1000字） |
| metadata.source | string | 来源文件名 |
| metadata.file_id | int | 关联 MySQL file_uploads.id |
| metadata.chunk_index | int | 父块序号 |

> 父块不存储 embedding，检索命中子块后通过 `metadata.parent_id` 反查父块原文返回给用户。

**Collection：`knowledge_child`** — 子块存储（用于向量检索）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 子块唯一 ID |
| document | string | 子块原文（~200字） |
| embedding | vector(1024) | DashScope 向量 |
| metadata.parent_id | string | 关联父块 ID |
| metadata.source | string | 来源文件名 |

**BM25 索引** — 内存 + 本地序列化（`data/bm25_index.pkl`）

---

## 6. 评估体系

### 6.1 RAG 检索质量评估（Ragas）

| 指标 | 含义 | 目标值 |
|------|------|--------|
| `context_relevance` | 检索文档与问题的相关性 | ≥ 0.80 |
| `answer_faithfulness` | 回答是否有检索依据支撑 | ≥ 0.85 |
| `answer_relevance` | 回答是否真正回答了问题 | ≥ 0.80 |

### 6.2 Agent 行为评估（自定义指标）

| 指标 | 含义 | 目标值 |
|------|------|--------|
| `tool_selection_accuracy` | Agent 选择正确工具的比例 | ≥ 0.90 |
| `redundant_tool_calls` | 冗余工具调用率 | ≤ 0.10 |
| `self_reflection_trigger_rate` | verify_answer 触发后修正回答的比例 | 记录即可 |
| `avg_latency_ms` | 端到端平均响应时间 | ≤ 3000ms |

### 6.3 记忆质量评估

| 指标 | 含义 | 目标值 |
|------|------|--------|
| `memory_hit_rate` | 注入记忆的 complex 请求中，经手工标注有效利用记忆的比例 | ≥ 0.70 |
| `multi_turn_accuracy` | 多轮对话中指代消解准确率 | ≥ 0.85 |

### 6.4 Golden Test Set

位于 `data/eval/golden_set.json`，包含三类问题各 20 条：
- 表信息查询类（对应 `search_table_metadata` 工具）
- 列信息查询类（对应 `search_column_metadata` 工具）
- 知识检索类（对应 `hybrid_search_knowledge` 工具）

每条记录格式：
```json
{
  "question": "订单表的主键是什么字段？",
  "expected_tool": "search_column_metadata",
  "reference_answer": "...",
  "reference_docs": ["..."]
}
```

---

## 7. 项目排期与验收指标

### Phase A：Agent 骨架搭建

**目标：** ReAct Agent 可运行，工具调用链路通畅

**交付物：**
- `router.py`：QueryRouter（qwen-turbo 分类 + out_of_scope 拦截）
- `agent.py`：DataAgent 基础实现
- `tools/metadata_tools.py`：`search_table_metadata`、`search_column_metadata` 两个工具
- `settings.py` + `settings.yaml`：配置管理
- 移除 `intent_recognition.py`，`app.py` 接入 QueryRouter → DataAgent
- `data/eval/golden_set.json` 初始版本（表/列查询类 40 条，知识检索类留空）

**验收指标：**
- [ ] QueryRouter 对 `simple_table`/`simple_column`/`out_of_scope` 分类准确率 ≥ 90%（手工标注 30 条测试）
- [ ] `simple_table`/`simple_column` 路径端到端响应时间 ≤ 1500ms
- [ ] `out_of_scope` 问题正确拦截，不进入 Agent
- [ ] Agent 工具调用成功率 ≥ 90%（基于 Golden Set 表/列查询类 40 条）

---

### Phase B：混合检索升级

**目标：** 用 Hybrid Search 替代现有 Doris 向量检索

**交付物：**
- `ingestion/` 完整流水线（含父块子块切分）
- `tools/retrieval_tool.py`：`hybrid_search_knowledge`
- ChromaDB 替代 Doris，BM25 索引建立
- 移除 Doris 相关代码和配置
- `data/eval/golden_set.json` 补充知识检索类 20 条（Golden Set 完整至 60 条）

**验收指标：**
- [ ] 文档入库流水线可处理全部 7 种文件格式
- [ ] Hybrid Search 在知识检索类 Golden Set（20条）上 `context_relevance` ≥ 0.80
- [ ] 与旧系统基线对比 `context_relevance` 提升 ≥ 10%（基线：Phase B 开始前用旧 Doris 检索在同一 20 条上跑一次，记录为 `baseline_context_relevance`）

---

### Phase C：分层记忆管理

**目标：** 短期 + 长期记忆机制完整运行

**交付物：**
- `memory/` 模块（短期窗口 + 长期摘要 + MySQL 持久化）
- MySQL `memory_summaries` 表
- Agent 集成记忆注入

**验收指标：**
- [ ] 5 轮对话后自动触发摘要压缩，摘要写入 MySQL
- [ ] 新会话启动时正确加载历史摘要
- [ ] 多轮对话指代消解准确率 ≥ 0.85（手动测试 10 组多轮问答）

---

### Phase D：全链路可观测性

**目标：** TraceContext + 结构化日志 + Streamlit Dashboard

**交付物：**
- `observability/trace.py`：TraceContext
- `logs/traces.jsonl`：结构化日志
- Streamlit Dashboard 4 个页面（总览、数据浏览、Ingestion 管理、Agent 追踪）

**验收指标：**
- [ ] 每次 Agent 推理生成完整 Trace（含工具调用序列、耗时、记忆注入内容）
- [ ] Dashboard 可正确展示最近 50 条 Trace 记录
- [ ] Agent 追踪页面可展示单次推理的完整工具调用链路

---

### Phase E：自我反思 + 评估体系

**目标：** verify_answer 工具 + Ragas 评估 + 评估面板

**交付物：**
- `tools/reflection_tool.py`：verify_answer
- `evaluation/` 模块（Ragas + 自定义指标）
- `data/eval/golden_set.json` 最终版本（补充 reference_answer 字段，完善评估所需标注）
- Dashboard 评估面板页面

**验收指标：**
- [ ] `answer_faithfulness` ≥ 0.85（Golden Set 全量评估）
- [ ] `tool_selection_accuracy` ≥ 0.90
- [ ] 评估面板可展示各指标得分与历史趋势

---

### Phase F：MCP 接口（可选）

**目标：** 将 Agent 暴露为 MCP Server，可被 Claude Desktop / Copilot 调用

**交付物：**
- `mcp_server.py`：基于 Python MCP SDK 实现
- 暴露工具：`query_data_assistant`（封装 DataAgent.run）
- 配置文档：如何在 Claude Desktop 中接入

**验收指标：**
- [ ] Claude Desktop 可通过 MCP 协议调用并获得正确回答
- [ ] Stdio Transport 通信正常，无日志污染

---

### Phase G：数据血缘图（可选，最低优先级）

**目标：** 构建指标/字段/表之间的血缘关系图，支持正向追溯与反向影响分析

**交付物：**
- `lineage/builder.py`：血缘构建流水线（SQL 解析 + 文档 LLM 抽取）
- `lineage/graph.py`：Neo4j 图读写封装
- `tools/lineage_tools.py`：`trace_lineage`、`impact_analysis` 两个 Agent 工具
- `observability/dashboard/pages/lineage.py`：血缘图可视化页面

**图模型：**
```
节点：Table {name, description} | Column {name, type, table_name} | Metric {name, definition, formula}
边：(Metric)-[:DERIVED_FROM]->(Column) | (Column)-[:BELONGS_TO]->(Table) | (Metric)-[:REFERENCES]->(Metric)
```

**血缘构建两路并行：**
- SQL 路：`sqlglot` 解析 CREATE TABLE / SELECT，抽取 Column→Table、字段级依赖
- 文档路：LLM（qwen-plus）从知识库文档抽取 Metric→Column/Metric 关系，结构化 JSON 写入 Neo4j

**新增 Agent 工具：**

| 工具 | 功能 | 示例输入 |
|------|------|---------|
| `trace_lineage` | 正向追溯：指标依赖哪些字段/表 | "GMV 依赖哪些字段" |
| `impact_analysis` | 反向影响：字段变更影响哪些指标 | "order.amount 变更影响什么" |

**验收指标：**
- [ ] SQL 字段依赖抽取正确率 ≥ 85%（覆盖项目内所有 .sql 文件）
- [ ] 文档 Metric→Column 抽取准确率 ≥ 80%（手工标注 20 条验证）
- [ ] `trace_lineage` 在 10 条测试问题上返回正确路径 ≥ 90%
- [ ] Dashboard 血缘图可正确渲染，节点可点击展开

---

## 8. 可扩展性与未来展望

| 方向 | 描述 | 优先级 |
|------|------|--------|
| Rerank 精排 | 引入 Cross-Encoder 或 LLM Rerank，在 Hybrid Search 后增加精排阶段 | 中 |
| 多 Agent 协作 | 拆分为 Orchestrator + 专职 Agent（检索 Agent、生成 Agent、评估 Agent） | 低 |
| 流式输出 | Agent 推理过程流式返回，提升前端响应体验 | 中 |
| 向量库迁移 | 从 ChromaDB 迁移到 Qdrant/Milvus，支持更大规模数据 | 低 |
| 多模态支持 | 文档中的图片通过 Vision LLM（Qwen-VL）生成描述后入库检索 | 低 |
| 在线学习 | 根据用户评分（点赞/踩）持续优化检索策略 | 低 |
