# DataIntelOperation 函数接口规格

> 对应 SPEC.md v2.0，覆盖 A-F 阶段。
> 本文档描述"怎么做"（函数签名、职责、约定），SPEC.md 描述"做什么"（需求与架构）。

---

## Phase A — 核心 Agent 骨架

### settings.py

```python
from dataclasses import dataclass

@dataclass
class LLMSettings:
    provider: str
    reasoning_model: str
    routing_model: str
    api_key: str
    temperature: float
    max_tokens: int

@dataclass
class EmbeddingSettings:
    provider: str
    model: str
    dimension: int
    batch_size: int

@dataclass
class VectorStoreSettings:
    provider: str
    persist_dir: str
    parent_collection: str
    child_collection: str

@dataclass
class RetrievalSettings:
    dense_top_k: int
    sparse_top_k: int
    rrf_k: int
    final_top_n: int

@dataclass
class MemorySettings:
    short_term_window: int
    long_term_enabled: bool

@dataclass
class ChunkingSettings:
    parent_chunk_size: int
    parent_chunk_overlap: int
    child_chunk_size: int
    child_chunk_overlap: int

@dataclass
class DatabaseConfig:
    host: str
    user: str
    password: str
    database: str
    port: int

@dataclass
class DatabaseSettings:
    business: DatabaseConfig
    meta: DatabaseConfig

@dataclass
class ObservabilitySettings:
    log_level: str
    trace_enabled: bool

@dataclass
class EvaluationSettings:
    enabled: bool
    latency_warn_ms: int
    ragas_weights: dict

@dataclass
class Settings:
    llm: LLMSettings
    embedding: EmbeddingSettings
    vector_store: VectorStoreSettings
    retrieval: RetrievalSettings
    memory: MemorySettings
    chunking: ChunkingSettings
    database: DatabaseSettings
    observability: ObservabilitySettings
    evaluation: EvaluationSettings

def load_settings(config_path: str = "config/settings.yaml") -> Settings:
    """读取 YAML，展开 ${ENV_VAR} 占位符，构造 Settings。缺少必填环境变量时抛出 EnvironmentError。"""

def _expand_env(value: str) -> str:
    # 匹配 ${VAR_NAME}，替换为 os.environ[VAR_NAME]
    # 未找到时抛出 EnvironmentError
```

---

### router.py

```python
from dataclasses import dataclass
from settings import Settings

@dataclass
class RouteResult:
    label: str      # "simple_table" | "simple_column" | "complex" | "out_of_scope"
    keyword: str    # 提取的搜索关键词，out_of_scope 时为空字符串
    raw_response: str

OUT_OF_SCOPE_REPLY: str = "抱歉，我只能回答数据表、字段和指标相关的问题。"

class QueryRouter:
    def __init__(self, settings: Settings) -> None:
        # 使用 settings.llm.routing_model (qwen-turbo)
        ...

    def route(self, query: str) -> RouteResult:
        # 调用 LLM，返回 JSON：{"label": "...", "keyword": "..."}
        # 解析失败时 label = "complex"，keyword = query
        ...

    def _parse_response(self, raw: str) -> RouteResult:
        # 尝试 json.loads，失败则 fallback
        ...
```

### tools/base.py

```python
from langchain.tools import BaseTool

class DataBaseTool(BaseTool):
    def _run(self, query: str) -> str: ...
    def _arun(self, query: str) -> str: ...

class MockTool(DataBaseTool):
    def __init__(self, name: str, description: str, fixed_response: str) -> None: ...
    def _run(self, query: str) -> str:
        # 返回 fixed_response，用于单元测试
        ...
```

---

### tools/metadata_tools.py

```python
from settings import Settings
from tools.base import DataBaseTool

def _format_table_result(rows: list[dict]) -> str: ...
def _format_column_result(rows: list[dict]) -> str: ...

class SearchTableMetadataTool(DataBaseTool):
    name: str = "search_table_metadata"
    description: str = "根据关键词搜索数据表元数据，返回表名、注释、层级等信息"

    def __init__(self, settings: Settings) -> None: ...

    def _run(self, query: str) -> str:
        # 调用 datasource.search_by_table(query)
        # 结果为空返回 "未找到相关表"；异常返回 "查询失败: {e}"
        ...

class SearchColumnMetadataTool(DataBaseTool):
    name: str = "search_column_metadata"
    description: str = "根据关键词搜索字段元数据，返回字段名、所属表、字段描述等信息"

    def __init__(self, settings: Settings) -> None: ...

    def _run(self, query: str) -> str:
        # 调用 datasource.search_by_column(query)
        # 结果为空返回 "未找到相关字段"；异常返回 "查询失败: {e}"
        ...
```

---

### agent.py

```python
from dataclasses import dataclass, field
from langchain.tools import BaseTool
from settings import Settings

SYSTEM_PROMPT_TEMPLATE: str  # 含 {memory_context} 占位符

@dataclass
class AgentResponse:
    answer: str
    trace_id: str
    steps: list[dict]
    total_latency_ms: int

class DataAgent:
    def __init__(self, settings: Settings, db_conn) -> None: ...

    def run(self, query: str, user_id: int) -> AgentResponse:
        # 1. collector = TraceCollector(user_id, query)
        # 2. logger.trace_id_filter.set(collector.trace_id)
        # 3. memory = _build_memory(user_id); memory.load()
        # 4. route = router.route(query)
        # 5. if out_of_scope: 直接返回，不写记忆
        # 6. memory_context = memory.build_context()
        # 7. system_prompt = _build_system_prompt(memory_context)
        # 8. 执行 AgentExecutor，每个 tool 调用后 collector.record_tool_call(...)
        # 9. memory.add_turn(query, answer); memory.flush()
        # 10. trace = collector.finish(db_conn)
        # 11. _evaluate_async(trace, answer, contexts)
        # 12. logger.trace_id_filter.clear()
        ...

    def _build_tools(self) -> list[BaseTool]: ...
    def _build_system_prompt(self, memory_context: str = "") -> str: ...
    def _build_memory(self, user_id: int) -> "HierarchicalMemory": ...

    def _evaluate_async(self, trace, answer: str, contexts: list[str]) -> None:
        # ThreadPoolExecutor 后台执行，异常只 log 不上抛
        ...
```

---

## Phase B — 知识摄入管道

### ingestion/loaders.py

```python
from dataclasses import dataclass

@dataclass
class Document:
    text: str
    metadata: dict   # {"source": filename, "file_id": int, "page": int}

SUPPORTED_EXTENSIONS = {"txt", "md", "pdf", "docx", "json", "csv", "xlsx"}

def load_document(file_path: str, file_id: int = 0) -> list[Document]:
    # 按扩展名分发到对应 _load_* 函数
    # 不支持的扩展名抛出 ValueError
    ...

def _load_txt(file_path: str, file_id: int) -> list[Document]: ...
def _load_pdf(file_path: str, file_id: int) -> list[Document]: ...   # pypdf，按页分 Document
def _load_docx(file_path: str, file_id: int) -> list[Document]: ...  # python-docx，按段落合并
def _load_json(file_path: str, file_id: int) -> list[Document]: ...  # 整文件一个 Document
def _load_csv(file_path: str, file_id: int) -> list[Document]: ...   # 每行一个 Document
def _load_xlsx(file_path: str, file_id: int) -> list[Document]: ...  # 每 sheet 一个 Document
```

---

### ingestion/splitter.py

```python
from dataclasses import dataclass, field

@dataclass
class ChildChunk:
    child_id: str       # f"{parent_id}_c{index}"
    text: str
    metadata: dict

@dataclass
class ParentChildPair:
    parent_id: str      # f"{source}_p{index}"
    parent_text: str
    parent_metadata: dict
    children: list[ChildChunk]

class ParentChildSplitter:
    def __init__(
        self,
        parent_chunk_size: int = 1000,
        parent_chunk_overlap: int = 0,
        child_chunk_size: int = 200,
        child_chunk_overlap: int = 20,
    ) -> None: ...

    def split(self, documents: list[Document]) -> list[ParentChildPair]:
        # 对每个 Document 先切 parent，再对每个 parent 切 children
        ...

    def _split_parent(self, text: str) -> list[str]: ...
    def _split_children(self, parent_text: str, parent_id: str, source: str) -> list[ChildChunk]: ...
```

---

### ingestion/encoder.py

```python
from settings import Settings

class EmbeddingEncoder:
    def __init__(self, settings: Settings) -> None:
        # settings.embedding.batch_size 控制每批大小（<=25）
        ...

    def encode(self, texts: list[str]) -> list[list[float]]:
        # 自动分批，合并结果，保持顺序
        ...

    def _call_api(self, batch: list[str]) -> list[list[float]]:
        # 调用 DashScope text-embedding-v3
        # 失败时抛出 RuntimeError
        ...
```

---

### ingestion/stores.py

```python
from settings import Settings
from ingestion.splitter import ParentChildPair

class ChromaStore:
    def __init__(self, settings: Settings) -> None:
        # 初始化两个 collection：
        #   knowledge_parent（无 embedding function）
        #   knowledge_child（带 1024-dim embedding）
        ...

    def upsert(self, pairs: list[ParentChildPair], child_embeddings: list[list[float]]) -> None:
        # parent collection：存 parent_id + parent_text + parent_metadata
        # child collection：存 child_id + child_text + embedding + {parent_id} metadata
        ...

    def search_children(self, query_embedding: list[float], top_k: int) -> list[dict]:
        # 返回 [{"child_id": ..., "parent_id": ..., "distance": ...}]
        ...

    def get_parent(self, parent_id: str) -> dict | None:
        # 从 knowledge_parent collection 按 id 查询
        # 不存在返回 None
        ...

    def delete_by_file(self, source: str) -> int:
        # 删除 metadata.source == source 的所有 child 和 parent
        # 返回删除的 child 数量
        ...

class BM25Indexer:
    INDEX_PATH: str = "data/bm25_index.pkl"

    def __init__(self) -> None:
        # 启动时尝试 _load()，文件不存在则初始化空索引
        ...

    def add(self, pairs: list[ParentChildPair]) -> None:
        # 将所有 child text 加入索引，_save()
        ...

    def search(self, query: str, top_k: int) -> list[dict]:
        # 返回 [{"child_id": ..., "parent_id": ..., "score": ...}]
        ...

    def delete_by_ids(self, child_ids: list[str]) -> None:
        # 重建索引（排除指定 ids），_save()
        ...

    def _save(self) -> None: ...
    def _load(self) -> None: ...
```

---

### ingestion/pipeline.py

```python
from dataclasses import dataclass
from settings import Settings

@dataclass
class IngestionResult:
    file_id: int
    parent_count: int
    child_count: int
    elapsed_ms: int

class IngestionPipeline:
    def __init__(self, settings: Settings, db_conn) -> None: ...

    def run(self, file_path: str, original_name: str, uploaded_by: str) -> IngestionResult:
        # 1. _record_upload() 写 file_uploads 表，获取 file_id
        # 2. load_document(file_path, file_id)
        # 3. splitter.split(documents)
        # 4. encoder.encode(all child texts)
        # 5. chroma_store.upsert(pairs, embeddings)
        # 6. bm25_indexer.add(pairs)
        # 失败时回滚 file_uploads 记录并上抛异常
        ...

    def _record_upload(self, file_path: str, original_name: str, uploaded_by: str) -> int:
        # INSERT INTO file_uploads，返回 lastrowid
        ...

    def delete(self, source: str) -> None:
        # 1. chroma_store.delete_by_file(source) 获取 child_ids
        # 2. bm25_indexer.delete_by_ids(child_ids)
        # 3. DELETE FROM file_uploads WHERE filename = source
        ...
```

---

### tools/retrieval_tool.py

```python
from settings import Settings
from tools.base import DataBaseTool
from ingestion.stores import ChromaStore, BM25Indexer
from ingestion.encoder import EmbeddingEncoder

def _rrf_fuse(
    dense_results: list[dict],
    sparse_results: list[dict],
    k: int = 60,
    top_n: int = 5,
) -> list[str]:
    # Reciprocal Rank Fusion，返回 top_n 个 parent_id 列表
    ...

class HybridSearchKnowledgeTool(DataBaseTool):
    name: str = "hybrid_search_knowledge"
    description: str = "在知识库中混合检索相关文档，返回原文片段"

    def __init__(
        self,
        settings: Settings,
        chroma_store: ChromaStore,
        bm25_indexer: BM25Indexer,
        encoder: EmbeddingEncoder,
    ) -> None: ...

    def _run(self, query: str) -> str:
        # 1. encoder.encode([query]) 得到 query_embedding
        # 2. chroma_store.search_children(query_embedding, dense_top_k)
        # 3. bm25_indexer.search(query, sparse_top_k)
        # 4. _rrf_fuse(dense, sparse, top_n=final_top_n) 得到 parent_ids
        # 5. chroma_store.get_parent(pid) for pid in parent_ids
        # 6. _format_results(parents)
        ...

    def _format_results(self, parents: list[dict]) -> str:
        # 返回 Markdown 格式，每段用 --- 分隔
        ...
```

---

## Phase C — 分层记忆

### memory/short_term.py

```python
from dataclasses import dataclass

@dataclass
class Turn:
    role: str        # "human" | "ai"
    content: str

class ShortTermMemory:
    """滑动窗口对话缓冲，保留最近 window 轮"""

    def __init__(self, window: int = 5) -> None:
        # self._turns: list[Turn] = []
        ...

    def add_turn(self, human: str, ai: str) -> None:
        # 追加一轮，超出 window 时丢弃最旧一轮
        ...

    def get_turns(self) -> list[Turn]: ...

    def format_context(self) -> str:
        # 返回可注入 prompt 的字符串
        # 格式："Human: ...
AI: ...
"（每轮一对）
        ...

    def clear(self) -> None: ...
```

---

### memory/long_term.py

```python
from dataclasses import dataclass
from settings import Settings

@dataclass
class MemorySummary:
    user_id: int
    summary: str
    updated_at: str   # ISO-8601

class LongTermMemory:
    """
    用 qwen-turbo 对历史对话做摘要，持久化到 MySQL memory_summaries 表。
    表结构：id, user_id, summary, created_at, updated_at
    """

    def __init__(self, settings: Settings, db_conn) -> None: ...

    def load(self, user_id: int) -> MemorySummary | None:
        # SELECT summary FROM memory_summaries
        # WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1
        # 返回 None 表示该用户无历史摘要
        ...

    def update(self, user_id: int, new_turns: list[str], existing_summary: str = "") -> MemorySummary:
        # 调用 _summarize() 压缩为新摘要
        # UPSERT 到 memory_summaries（ON DUPLICATE KEY UPDATE）
        ...

    def _summarize(self, existing_summary: str, new_turns: list[str]) -> str:
        # 调用 DashScope qwen-turbo
        # prompt："已有摘要：{existing}
新对话：{turns}
请更新摘要，保留关键信息，控制在200字以内。"
        ...
```

---

### memory/hierarchical_memory.py

```python
from settings import Settings
from memory.short_term import ShortTermMemory, Turn
from memory.long_term import LongTermMemory, MemorySummary

class HierarchicalMemory:
    """统一接口：短期（窗口缓冲）+ 长期（摘要持久化）。Agent 只与此类交互。"""

    def __init__(self, settings: Settings, db_conn, user_id: int) -> None:
        # self._short = ShortTermMemory(window=settings.memory.short_term_window)
        # self._long  = LongTermMemory(settings, db_conn)
        # self._user_id = user_id
        # self._long_summary: MemorySummary | None = None
        ...

    def load(self) -> None:
        # 从 MySQL 加载该用户的长期摘要到 self._long_summary
        # 在 agent.run() 开始时调用一次
        ...

    def add_turn(self, human: str, ai: str) -> None:
        # 写入短期记忆；不立即更新长期摘要（由 flush 触发）
        ...

    def flush(self) -> None:
        # 将当前短期窗口内容合并进长期摘要并持久化
        # 调用时机：每次 agent.run() 结束后
        ...

    def build_context(self) -> str:
        # 返回注入 system prompt 的记忆字符串
        # 格式："[长期摘要]
{summary}

[近期对话]
{short_term_context}"
        # 若无长期摘要则省略该段
        ...

    def get_short_turns(self) -> list[Turn]: ...
```

---

## Phase D — 可观测性

### observability/trace.py

```python
import uuid
from dataclasses import dataclass, field

@dataclass
class ToolCall:
    tool_name: str
    input: str
    output: str
    latency_ms: int

@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: int = 0
    query: str = ""
    route_label: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    answer: str = ""
    total_latency_ms: int = 0
    memory_injected: bool = False
    error: str = ""

class TraceCollector:
    """per-request 生命周期对象，收集完毕后调用 finish() 持久化到 agent_traces 表。"""

    def __init__(self, user_id: int, query: str) -> None:
        # self._trace = TraceContext(user_id=user_id, query=query)
        # self._start_ts: float = time.time()
        ...

    def set_route(self, label: str) -> None: ...
    def record_tool_call(self, tool_name: str, input: str, output: str, latency_ms: int) -> None: ...
    def set_answer(self, answer: str) -> None: ...
    def set_memory_injected(self, injected: bool) -> None: ...
    def set_error(self, error: str) -> None: ...

    def finish(self, db_conn) -> TraceContext:
        # 计算 total_latency_ms
        # INSERT INTO agent_traces，tool_calls_json = json.dumps([asdict(tc) for tc in tool_calls])
        # 返回最终 TraceContext
        ...

    @property
    def trace_id(self) -> str: ...
```

---

### observability/logger.py

```python
import logging
from settings import Settings

def setup_logging(settings: Settings) -> None:
    """
    按 settings.observability.log_level 配置根 logger。
    格式：%(asctime)s [%(levelname)s] %(name)s trace_id=%(trace_id)s - %(message)s
    应在 app.py 启动时调用一次。
    """

class TraceIdFilter(logging.Filter):
    """将当前请求 trace_id 注入 LogRecord"""

    def __init__(self) -> None:
        # self._trace_id: str = "-"
        ...

    def set(self, trace_id: str) -> None: ...
    def clear(self) -> None: ...

    def filter(self, record: logging.LogRecord) -> bool:
        # record.trace_id = self._trace_id; return True
        ...

# 模块级单例，agent.run() 通过它注入/清除 trace_id
trace_id_filter: TraceIdFilter
```

---

### observability/dashboard.py（Streamlit 入口）

```python
"""运行方式：streamlit run observability/dashboard.py"""

def main() -> None:
    # st.set_page_config(title="DataIntel 监控面板", layout="wide")
    # 侧边栏页面选择：概览 / 对话详情 / 评估报告
    ...

def render_overview(db_conn) -> None:
    """
    指标卡片：今日请求数、平均延迟、成功率、路由分布饼图。
    数据来源：agent_traces，按 created_at 过滤当天。
    """

def render_conversation_detail(db_conn) -> None:
    """
    输入 trace_id 或 user_id 查询单条 trace。
    展示：query -> route -> tool_calls 时间线 -> answer。
    tool_calls 时间线用 st.expander 逐条展开。
    """

def render_evaluation_report(db_conn) -> None:
    """
    读取 evaluation_results 表，展示：
    - Ragas 指标折线图（按日期聚合均值）
    - 低分对话列表（score < 阈值，可点击跳转详情）
    """

def _get_db_conn():
    # 读取 settings，返回 mysql.connector 连接
    # 用 @st.cache_resource 缓存连接
    ...
```

---

## Phase E — 评估

### evaluation/ragas_evaluator.py

```python
from dataclasses import dataclass
from settings import Settings

@dataclass
class RagasResult:
    trace_id: str
    faithfulness: float        # 答案与检索内容的一致性 [0,1]
    answer_relevancy: float    # 答案与问题的相关性 [0,1]
    context_recall: float      # 检索内容覆盖率 [0,1]
    composite_score: float     # 加权均值，权重来自 settings.evaluation.ragas_weights
    raw: dict                  # ragas 原始输出

class RagasEvaluator:
    """封装 ragas 库，对单条 agent 响应打分。LLM 评判使用 qwen-turbo。"""

    def __init__(self, settings: Settings) -> None: ...

    def evaluate(
        self,
        trace_id: str,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> RagasResult:
        # 构造 ragas Dataset，调用 ragas.evaluate()
        # 计算 composite_score
        ...

    def _build_ragas_llm(self, settings: Settings):
        # 返回 ragas 兼容的 LLM 对象（基于 DashScope qwen-turbo）
        ...

    def _composite(self, f: float, ar: float, cr: float) -> float:
        # weights from settings.evaluation.ragas_weights
        # 默认 faithfulness:0.4, answer_relevancy:0.4, context_recall:0.2
        ...
```

---

### evaluation/agent_evaluator.py

```python
from dataclasses import dataclass
from observability.trace import TraceContext
from settings import Settings

@dataclass
class AgentBehaviorResult:
    trace_id: str
    tool_call_count: int
    redundant_tool_calls: int   # 同一 tool 连续调用 >=2 次视为冗余
    answered_without_tool: bool # complex 路由但未调用任何 tool
    latency_ms: int
    behavior_score: float       # 规则打分 [0,1]

class AgentBehaviorEvaluator:
    """基于 TraceContext 做规则评估，不调用 LLM，零成本。"""

    def __init__(self, settings: Settings) -> None: ...

    def evaluate(self, trace: TraceContext) -> AgentBehaviorResult:
        # 解析 trace.tool_calls，计算各维度指标
        ...

    def _score(self, result: AgentBehaviorResult) -> float:
        # base = 1.0
        # - 0.2 per redundant_tool_call（最多扣 0.4）
        # - 0.3 if answered_without_tool and route == "complex"
        # - 0.1 if latency_ms > settings.evaluation.latency_warn_ms
        # 返回 max(0.0, base - penalties)
        ...
```

---

### evaluation/reflection_tool.py

```python
from langchain.tools import BaseTool
from settings import Settings

class ReflectionTool(BaseTool):
    """
    Agent 可主动调用的自我反思工具。
    输入：当前 answer 草稿。输出：改进建议字符串。
    每次 run() 最多调用一次，不写 DB。
    """
    name: str = "reflection"
    description: str = "当你对当前答案不确定时调用。输入你的答案草稿，返回改进建议。每次 run() 最多调用一次。"

    def __init__(self, settings: Settings) -> None: ...

    def _run(self, draft_answer: str) -> str:
        # prompt："你是一个数据助手，请评估以下答案是否准确、完整：
{draft}
"
        #         "如有不足，给出具体改进方向（不超过100字）；若答案已足够好，回复无需修改。"
        # 调用 qwen-turbo
        ...

    def _arun(self, draft_answer: str) -> str:
        raise NotImplementedError
```

---

### evaluation/persistence.py

```python
from dataclasses import dataclass
from evaluation.ragas_evaluator import RagasResult
from evaluation.agent_evaluator import AgentBehaviorResult

@dataclass
class EvaluationRecord:
    trace_id: str
    composite_score: float
    behavior_score: float
    faithfulness: float
    answer_relevancy: float
    context_recall: float
    tool_call_count: int
    latency_ms: int

def save_evaluation(db_conn, ragas: RagasResult, behavior: AgentBehaviorResult) -> None:
    # INSERT INTO evaluation_results，另加 created_at = NOW()
    ...

def load_recent(db_conn, limit: int = 100) -> list[EvaluationRecord]:
    # SELECT ... FROM evaluation_results ORDER BY created_at DESC LIMIT %s
    # 供 dashboard.render_evaluation_report() 使用
    ...
```

---

## Phase F — 配置统一 & app.py 集成

### config/settings.yaml

```yaml
llm:
  provider: dashscope
  reasoning_model: qwen-plus
  routing_model: qwen-turbo
  api_key: "${DASHSCOPE_API_KEY}"
  temperature: 0.1
  max_tokens: 2048

embedding:
  provider: dashscope
  model: text-embedding-v3
  dimension: 1024
  batch_size: 25

vector_store:
  provider: chromadb
  persist_dir: data/chroma
  parent_collection: knowledge_parent
  child_collection: knowledge_child

retrieval:
  dense_top_k: 10
  sparse_top_k: 10
  rrf_k: 60
  final_top_n: 5

memory:
  short_term_window: 5
  long_term_enabled: true

chunking:
  parent_chunk_size: 1000
  parent_chunk_overlap: 0
  child_chunk_size: 200
  child_chunk_overlap: 20

database:
  business:
    host: "192.168.88.102"
    user: root
    password: "${DB_PASSWORD}"
    database: business_db
    port: 3306
  meta:
    host: "192.168.88.102"
    user: root
    password: "${DB_PASSWORD}"
    database: data_metadata
    port: 3306

observability:
  log_level: INFO
  trace_enabled: true

evaluation:
  enabled: true
  latency_warn_ms: 5000
  ragas_weights:
    faithfulness: 0.4
    answer_relevancy: 0.4
    context_recall: 0.2
```

---

### app.py 修改接口

```python
from settings import load_settings, Settings
from observability.logger import setup_logging
from agent import DataAgent
from ingestion.pipeline import IngestionPipeline

# 启动时初始化（模块级，替换原 config.py 导入）
_settings: Settings = load_settings()
setup_logging(_settings)

def _get_business_conn():
    # 返回 mysql.connector.connect(**_settings.database.business.__dict__)
    ...

def _get_meta_conn():
    # 返回 mysql.connector.connect(**_settings.database.meta.__dict__)
    ...

# 模块级单例（无状态，可复用）
_agent = DataAgent(_settings, _get_business_conn())
_pipeline = IngestionPipeline(_settings, _get_business_conn())

# /api/chat 修改：
#   替换 intent_execute(user_query, user_id) 为：
#     response_obj = _agent.run(user_query, user_id)
#     response = response_obj.answer
#   返回 jsonify 追加 trace_id 字段：
#     {"conversation_id": ..., "content": ..., "trace_id": response_obj.trace_id}

# upload_file() 修改：
#   替换 vector_build.MysqlConnector().data_opt_add() 为：
#     result = _pipeline.run(upload_path, filename, session["username"])
#   返回 jsonify 追加摄入统计：
#     {"success": True, ..., "parent_count": result.parent_count}

# delete_file() 修改：
#   替换 vector_build.MysqlConnector().data_opt_delete() 为：
#     _pipeline.delete(filename)
```

---

### 废弃清单

| 文件 | 处理方式 |
|------|---------|
| config.py | 删除，所有引用替换为 `_settings.database.*` |
| intent_recognition.py | 废弃入口，保留文件但不再被 app.py 调用 |
| vector_build.py | 废弃，被 `ingestion/` 模块替代 |
