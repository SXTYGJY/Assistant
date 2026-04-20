#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指标口径RAG系统
基于对话历史和index_define.md组装prompt，询问大模型输出结果
"""
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import message_to_dict, messages_from_dict
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
import os
import json
from datasource import search_by_table, search_by_table_lineage, search_by_column
from utils import safe_json_dumps, serialize_for_json
from doris_vector_search import DorisVectorClient, AuthOptions
from config import DORIS_CONFIG
from vector_build import MysqlConnector
import dashscope
from dashscope import TextEmbedding

dashscope.api_key = os.getenv("OPENAI_API_KEY")


class FileChatMessageHistory(BaseChatMessageHistory):
    """基于文件的聊天历史存储"""

    def __init__(self, session_id, storage_path):
        self.session_id = session_id
        self.storage_path = storage_path
        self.file_path = os.path.join(self.storage_path, f"{self.session_id}.json")
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def add_message(self, message) -> None:
        """
        Adds a message to the history.
        """
        all_messages = list(self.messages)

        if isinstance(message, (list, tuple)):
            all_messages.extend(message)
        else:
            all_messages.append(message)

        new_messages = [message_to_dict(msg) for msg in all_messages]

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(new_messages, f)

    @property
    def messages(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                messages = json.load(f)
            return messages_from_dict(messages)
        except FileNotFoundError:
            return []

    def clear(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)


class MetricRAGSystem:
    """指标口径RAG系统"""

    def __init__(self, session_id="default_user", types="document", kw="user"):

        self.session_id = session_id
        self.session_config = {"configurable": {"session_id": session_id}}
        self.vector_store = self.load_vector(types)

        self.types = types
        self.kw = kw
        # 初始化模型
        self.model = ChatTongyi(
            model_name="qwen-flash",
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        )

        # 设置记忆链
        self.conversation_chain = self.create_conversation_chain(types)

    def load_vector(self, types):
        if types == "document":
            mysql_connector = MysqlConnector()
            return mysql_connector.data_opt_select()
        else:
            return None

    def get_history(self, session_id):
        """获取历史会话（限制最多返回最近的5条记录以减少输入长度）"""

        class LimitedMessageHistory(FileChatMessageHistory):
            def __init__(self, session_id, storage_path, max_messages=5):
                super().__init__(session_id, storage_path)
                self.max_messages = max_messages

            @property
            def messages(self):
                try:
                    messages = super().messages
                    # 只返回最近的max_messages条消息
                    return messages[-self.max_messages:]
                except FileNotFoundError:
                    return []

        return LimitedMessageHistory(session_id, "./data/chat_history", max_messages=5)

    def create_conversation_chain(self, types):
        """创建带历史记忆的对话链"""
        # 基础提示模板
        if types == "table":

            prompt_template = PromptTemplate.from_template("""
                你是一个专业的数据分析师助手，负责回答【表信息查询】相关问题。
                你的回答将直接以 **Markdown** 形式展示在前端页面，请严格遵守 Markdown 语法与换行规则。

                基于以下相关信息来回答问题：

                【表的数据】
                {metric_context}

                【表的ddl】

CREATE TABLE `ods_meta_table_info_dd` (
  `id` bigint NOT NULL COMMENT '主键ID',
  `catalog_name` varchar(255) DEFAULT NULL COMMENT '数据源或集群名称',
  `database_name` varchar(255) DEFAULT NULL COMMENT '库名',
  `table_name` varchar(255) DEFAULT NULL COMMENT '表名',
  `layer` varchar(20) DEFAULT NULL COMMENT '分层（ODS/DWD/DWS/ADS）',
  `table_creator_id` varchar(100) DEFAULT NULL COMMENT '表创建人ID',
  `table_creator_name` varchar(100) DEFAULT NULL COMMENT '表创建人姓名',
  `comment` text COMMENT '表描述',
  `table_type` tinyint DEFAULT NULL COMMENT '1-内部表, 2-外部表, 3-视图',
  `storage_location` varchar(500) DEFAULT NULL COMMENT '表存储路径',
  `file_count` bigint DEFAULT NULL,
  `storage_size_mb` decimal(18,2) DEFAULT NULL COMMENT '逻辑存储量（MB，不含副本）',
  `daily_file_inc` bigint DEFAULT NULL COMMENT '日新增文件数',
  `daily_size_inc_mb` decimal(18,2) DEFAULT NULL COMMENT '日新增存储量（MB）',
  `last_access_time` datetime DEFAULT NULL COMMENT '最后访问时间',
  `create_time` datetime DEFAULT NULL COMMENT '表创建时间',
  `is_partitioned` tinyint DEFAULT NULL COMMENT '是否分区表：1-是，0-否',
  `visit_count` bigint DEFAULT NULL COMMENT '总访问次数',
  `is_deleted` tinyint DEFAULT NULL COMMENT '是否已下线：1-是，0-否',
  `is_cold` tinyint DEFAULT NULL COMMENT '是否30天无访问：1-是，0-否',
  `partition_count` bigint DEFAULT NULL COMMENT '分区数量',
  `small_file_count` bigint DEFAULT NULL COMMENT '小文件数量（<128MB）',
  `lifecycle_days` bigint DEFAULT NULL COMMENT '表生命周期（天）',
  `compress_format` varchar(50) DEFAULT NULL COMMENT '压缩格式',
  `storage_format` varchar(50) DEFAULT NULL COMMENT '存储格式（如 PARQUET/ORC）',
  `task_id` varchar(255) DEFAULT NULL COMMENT '关联的任务ID',
  `dt` varchar(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
  PRIMARY KEY (`id`,`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ODS层-元数据域-表信息-全量表'

CREATE TABLE `ods_meta_table_lineage_dd` (
  `id` bigint NOT NULL COMMENT '主键ID',
  `source_catalog_name` varchar(255) DEFAULT NULL COMMENT '上游数据源或集群名称',
  `source_database_name` varchar(255) DEFAULT NULL COMMENT '上游数据库名',
  `source_table_name` varchar(255) DEFAULT NULL COMMENT '上游表名',
  `source_table_layer` varchar(20) DEFAULT NULL COMMENT '上游表分层',
  `target_catalog_name` varchar(255) DEFAULT NULL COMMENT '下游数据源或集群名称',
  `target_database_name` varchar(255) DEFAULT NULL COMMENT '下游数据库名',
  `target_table_name` varchar(255) DEFAULT NULL COMMENT '下游表名',
  `target_table_layer` varchar(20) DEFAULT NULL COMMENT '下游表分层',
  `lineage_type` tinyint DEFAULT NULL COMMENT '血缘关系类型：-1=上游，1=下游',
  `create_by` varchar(100) DEFAULT NULL COMMENT '创建人',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(100) DEFAULT NULL COMMENT '最后更新人',
  `update_time` datetime DEFAULT NULL COMMENT '最后更新时间',
  `sync_timestamp` datetime DEFAULT NULL COMMENT '血缘同步时间',
  `dt` varchar(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
  PRIMARY KEY (`id`,`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ODS层-元数据域-表血缘信息-全量表'

                【对话历史】
                {chat_history}

                【用户问题】
                {input}

                请给出专业、准确的回答。如果信息不足，请说明需要补充的内容。

                回答要求（必须遵守）：
#### 1️⃣ 表是否存在
- 使用四级标题 `#### 表确认`
- 明确说明表是否存在
- 若不存在，请直接说明原因（如：未查询到对应表）

#### 2️⃣ 表的业务含义
- 使用四级标题 `#### 表说明`
- 说明该表的业务背景、用途和所在分层（ODS/DWD/DWS/ADS）

#### 3️⃣ 核心字段说明
- 使用四级标题 `#### 核心字段`
- 仅挑选 **最关键字段**（不超过 5 个）
- 每个字段一行，说明其业务含义

#### 4️⃣ 表特性补充（如有）
- 是否分区表
- 数据量 / 生命周期 / 是否冷表
- 是否有上下游血缘（如已知）
""")
        elif types == "column":
            prompt_template = PromptTemplate.from_template("""
            你是一个专业的数据分析师助手，负责回答【字段信息查询】相关问题。
            你的回答将直接以 **Markdown** 形式展示在前端页面，请严格遵守 Markdown 语法与换行规则。

                            基于以下相关信息来回答问题：

                            【字段的数据】
                            {metric_context}

                            【列的ddl】
                            CREATE TABLE `ods_meta_columns_info_dd` (
              `id` bigint NOT NULL COMMENT '主键ID',
              `catalog_name` varchar(255) DEFAULT NULL COMMENT '数据源或集群名称',
              `database_name` varchar(255) DEFAULT NULL COMMENT '数据库名',
              `table_name` varchar(255) DEFAULT NULL COMMENT '表名',
              `column_name` varchar(255) DEFAULT NULL COMMENT '字段名称',
              `data_type` varchar(100) DEFAULT NULL COMMENT '字段数据类型',
              `column_desc` text COMMENT '字段描述或业务含义',
              `ordinal_position` int DEFAULT NULL COMMENT '字段在表中的位置（从1开始）',
              `is_partition_key` tinyint DEFAULT NULL COMMENT '是否为分区字段：0-否，1-是',
              `create_by` varchar(100) DEFAULT NULL COMMENT '创建人',
              `create_time` datetime DEFAULT NULL COMMENT '创建时间',
              `update_by` varchar(100) DEFAULT NULL COMMENT '最后更新人',
              `update_time` datetime DEFAULT NULL COMMENT '最后更新时间',
              `dt` varchar(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
              PRIMARY KEY (`id`,`dt`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='ODS层-元数据域-字段信息-全量表'

                            【对话历史】
                            {chat_history}

                            【用户问题】
                            {input}

                            请给出专业、准确的回答。如果信息不足，请说明需要补充的内容。

                            回答要求（必须遵守）

#### 字段确认
- 使用四级标题 
- 明确说明字段是否存在，存在于哪个表中，若不存在，请直接说明原因（如：表中未找到该字段）

#### 字段业务含义
- 使用四级标题
- 说明字段的业务含义、数据类型

**明确禁止以下内容：**
- ❌ 不要添加"使用注意事项"章节
- ❌ 不要添加"字段属性补充"章节  
- ❌ 不要添加任何额外的说明、建议或扩展内容
- ❌ 仅限上述两个章节，保持回答高度简洁

仅需说明以上两块内容，其他无需展示
""")
        elif types == "document":
            prompt_template = PromptTemplate.from_template("""
            你是一个专业的数据分析师与指标口径专家，负责回答【指标定义 / 指标口径】相关问题。
                你的回答将 **直接以 Markdown 渲染在前端页面**，因此必须严格遵守 Markdown 语法和换行规则。

            ---

            ## 一、已知指标定义信息
            {metric_context}

            ---

            ## 二、历史对话（用于理解上下文）
            {chat_history}

            ---

            ## 三、用户问题
            {input}

            ---

            ## 四、回答要求（必须遵守）

            #### 1️⃣ 指标存在性确认
            - 明确说明该指标是否存在
            - 若不存在，请说明原因（如：未收录 / 定义不完整 / 需要补充业务背景）

            #### 2️⃣ 指标业务定义
            - 使用清晰的 Markdown 四级标题
            - 说明指标的业务含义、统计对象、统计范围、时间口径等关键信息
            - 表述准确、专业、避免歧义

            #### 3️⃣ 计算逻辑 / SQL 示例
            - 若可以给出计算逻辑，请使用 **Markdown 代码块**
            - SQL 示例需包含合理的换行与缩进，具备可读性
            - 若无法给出完整 SQL，请明确指出缺失的信息

            #### 4️⃣ 补充说明（可选）
            - 指标的典型使用场景
            - 常见口径差异或注意事项

            ---

            ## 五、输出格式规范（非常重要）

            - **必须使用 Markdown**
            - 推荐输出结构如下（结构可复用，但内容需结合实际）：
            
            #### 指标确认
            ...

            #### 指标定义
            ...

            #### 计算逻辑 / SQL 示例
            ```sql
            SELECT ...
            ```

            #### 补充说明
            - **禁止输出与问题无关的内容**
            - **禁止输出纯文本、JSON 或解释性说明**
            - 语气保持：专业、清晰、克制、友好
            """)

        else:
            prompt_template = PromptTemplate.from_template("""
请不要进行任何推测或扩展，直接返回以下内容（原样返回）：

🙂 抱歉，这个问题我暂时无法直接回答。 \n

目前我主要支持以下几类问题：\n
- 📊 表信息查询（如：某张表是做什么的）\n
- 🧩 字段信息查询（如：某个字段的业务含义）\n
- 📐 指标定义查询（如：指标的口径与计算方式）\n

👉 请明确提到 **表名 / 字段名 / 指标名** 后再试一次，我会很乐意帮你一起分析～

                """)
        # 基础链
        base_chain = prompt_template | self.model | StrOutputParser()

        # 带历史的链
        return RunnableWithMessageHistory(
            base_chain,
            self.get_history,
            input_messages_key="input",
            history_messages_key="chat_history"
        )

    def search_metric_definitions(self, query, types="document", kw="metric"):
        """搜索相关指标定义 / 表字段信息"""
        if types == "document":
            if not self.vector_store:
                return ["未找到相关指标定义"]

            query_vec = TextEmbedding.call(model=TextEmbedding.Models.text_embedding_v3, input=query, dimension=512).output['embeddings'][0]['embedding']

            auth = AuthOptions(
                host=DORIS_CONFIG["host"],
                query_port=DORIS_CONFIG["port"],
                user=DORIS_CONFIG["user"],
                password=""
            )

            client = DorisVectorClient(database=DORIS_CONFIG["database"], auth_options=auth)

            table = client.open_table("doris_vector_table")

            results = table.search(query_vec, metric_type="l2_distance").limit(3).select(["content"]).to_list()

            return results

        elif types == "table":
            return search_by_table(kw.strip())

        elif types == "column":
            return search_by_column(kw.strip())
        else:
            return ["未找到相关指标定义"]

    def query_metric(self, user_query):
        """处理指标口径查询"""
        print(f"\n用户查询: {user_query}")
        print("=" * 40)
        # 1. 根据意图搜索相关内容
        metric_results = self.search_metric_definitions(user_query, self.types, self.kw)
        print("搜索内容: " + str(metric_results))
        print("=" * 40)

        # 确保metric_context是字符串类型
        if isinstance(metric_results, list):
            metric_context = "\n\n".join(
                str(result) if not isinstance(result, str) else result for result in metric_results)
        else:
            metric_context = str(metric_results)

        # 2. 调用LLM对话链
        try:
            response = self.conversation_chain.invoke(
                {
                    "input": user_query,
                    "metric_context": metric_context
                },
                config=self.session_config
            )

            return response

        except Exception as e:
            return f"系统错误: {str(e)}"


if __name__ == '__main__':
    rag = MetricRAGSystem()
    print(rag.query_metric("最近30天活跃用户总数的指标定义"))
