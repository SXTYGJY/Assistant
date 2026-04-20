# DataIntelOperation — 项目规格说明书 (SPEC)

> 版本：1.0 | 日期：2026-04-20

---

## 1. 项目概述

DataIntelOperation 是一个面向数据团队的**智能数据助手平台**，提供基于自然语言的数据元数据查询能力。用户通过对话界面提问，系统自动识别意图、检索相关元数据或知识文档，并借助大语言模型（LLM）生成结构化回答。

### 核心价值
- 降低数据查询门槛：非技术人员可用自然语言查询表结构、字段含义、指标定义
- 知识沉淀：支持上传文档并构建向量索引，形成企业知识库
- 对话历史：保存每次会话，支持多轮上下文理解

---

## 2. 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Flask 3.0.2 (Python) |
| 元数据存储 | MySQL 8.x |
| 向量存储 | Apache Doris（HNSW 索引） |
| LLM | 阿里云通义千问（DashScope API）— `qwen-plus` / `qwen-turbo` / `qwen-max` |
| 向量嵌入 | DashScope Embedding（`text-embedding-v3`） |
| 前端 | Bootstrap 5.3 + Marked.js（Markdown 渲染） |
| 会话管理 | Flask Session（服务端 session） |
| 文件处理 | UUID 命名 + 本地存储（`data/knowledge/`） |

**主要依赖：**
```
flask==3.0.2
mysql-connector-python==8.3.0
dashscope==1.20.3
langchain==0.1.16
langchain-community==0.0.36
chromadb==0.4.24
numpy==1.26.4
```

---

## 3. 系统架构

```
用户浏览器
    │
    ▼
Flask Web 应用 (app.py)
    │
    ├── 认证模块（登录/注册/登出）
    │
    ├── 聊天 API (/api/chat)
    │       │
    │       ▼
    │   意图识别 (intent_recognition.py)
    │       │
    │       ├── 表信息查询 ──► MySQL 元数据查询 (datasource.py)
    │       ├── 列信息查询 ──► MySQL 元数据查询 (datasource.py)
    │       ├── 指标定义查询 ──► 向量检索 (rag.py + Doris)
    │       └── 其他 ──────► 向量检索 (rag.py + Doris)
    │               │
    │               ▼
    │           LLM 生成回答 (DashScope Qwen)
    │
    ├── 文件管理 API（管理员）
    │       │
    │       ▼
    │   向量构建 (vector_build.py)
    │       │
    │       ▼
    │   Doris 向量数据库
    │
    └── 对话历史存储 (MySQL)
```

---

## 4. 模块说明

### 4.1 `app.py` — Flask 主应用

**职责：** HTTP 路由、用户认证、会话管理、文件上传/下载

**路由列表：**

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET/POST | `/register` | 公开 | 用户注册（密码最少6位） |
| GET/POST | `/login` | 公开 | 用户登录（密码哈希验证） |
| GET | `/logout` | 登录用户 | 清除 session |
| GET | `/chat` | 登录用户 | 聊天界面 |
| GET/POST | `/api/chat` | 登录用户 | 聊天 API，调用意图识别 |
| POST | `/api/rate` | 登录用户 | 对话评分（1-5分 + 点赞/踩） |
| GET | `/admin` | 管理员 | 文件管理面板 |
| POST | `/api/upload` | 管理员 | 上传文件并构建向量索引 |
| GET | `/api/files` | 管理员 | 列出已上传文件 |
| GET | `/api/download/<filename>` | 管理员 | 下载文件 |
| DELETE | `/api/delete/<filename>` | 管理员 | 删除文件及向量数据 |

**关键逻辑：**
- 首次进入聊天页面自动发送欢迎消息
- 对话历史存入 MySQL `conversations` 表
- 文件上传使用 UUID 前缀避免命名冲突
- 允许上传类型：`txt, md, pdf, doc, docx, json, csv, xlsx`

---

### 4.2 `intent_recognition.py` — 意图识别

**职责：** 将用户自然语言问题分类为具体意图，并提取关键词

**意图类型：**

| 意图 | 触发条件 | 后续动作 |
|------|----------|----------|
| 表信息查询 | 询问表的定义、用途、结构 | 查询 MySQL 元数据 |
| 列信息查询 | 询问字段/列的含义、类型 | 查询 MySQL 元数据 |
| 指标定义查询 | 询问业务指标的计算逻辑 | 向量检索知识库 |
| 其他 | 无法归类的问题 | 向量检索知识库 |

**处理流程：**
1. 构造包含意图规则的 Prompt
2. 调用 `qwen-turbo`（快速模型）进行分类
3. 解析响应格式：`意图类型:关键词`
4. 根据意图实例化 `MetricRAGSystem` 并执行查询
5. 返回 LLM 生成的最终回答

**入口函数：** `execute(query: str, user_id: int) -> str`

---

### 4.3 `rag.py` — RAG 检索增强生成

**职责：** 向量检索 + 多轮对话上下文管理 + LLM 回答生成

**核心类：** `MetricRAGSystem`

**初始化参数：**
- `query_type`: `"table"` | `"column"` | `"document"`
- `top_k`: 返回的相关文档数量（默认 3）
- `model_name`: LLM 模型名称（默认 `qwen-plus`）

**检索策略：**
- `table` 类型：从 MySQL 查询表元数据，格式化为文本块
- `column` 类型：从 MySQL 查询列元数据，格式化为文本块
- `document` 类型：从 Doris 向量数据库进行语义相似度检索

**对话管理：**
- 每个用户维护独立的对话历史（`user_id` 隔离）
- 历史记录存储在内存中（`conversation_histories` 字典）
- 构建包含历史上下文的 Prompt 传入 LLM

**LLM 调用：** DashScope `Generation.call()` 流式/非流式

---

### 4.4 `vector_build.py` — 向量数据库管理

**职责：** 文档解析、文本分块、向量嵌入、Doris 存储

**核心类：** `VectorDatabaseManager`

**支持的文档格式：**
- `.txt` / `.md` — 直接读取文本
- `.pdf` — PyPDF2 解析
- `.docx` — python-docx 解析
- `.json` — JSON 格式化为字符串
- `.csv` / `.xlsx` — pandas 读取，转为字符串

**处理流程：**
1. 解析文档内容
2. 按 `chunk_size`（默认 500 字符）分块，`overlap`（默认 50 字符）重叠
3. 调用 DashScope `text-embedding-v3` 生成 1024 维向量
4. 批量写入 Doris `knowledge_vectors` 表
5. 记录文件元数据到 MySQL `file_uploads` 表

**删除逻辑：** 按 `file_id` 删除 Doris 中对应的所有向量块

---

### 4.5 `datasource.py` — 元数据数据源

**职责：** MySQL 连接管理 + 元数据查询

**核心类：** `MySQLConnector`

**主要方法：**
- `get_table_info(keyword)` — 模糊匹配表名/表注释，返回表元数据
- `get_column_info(keyword)` — 模糊匹配列名/列注释，返回列元数据
- `get_all_tables()` — 获取所有表信息
- `get_table_columns(table_name)` — 获取指定表的所有列信息

**查询的元数据表：**
- `meta_tables` — 表级元数据（表名、中文名、描述、数据库、负责人等）
- `meta_columns` — 列级元数据（列名、中文名、数据类型、描述、所属表等）

---

### 4.6 `config.py` — 配置管理

**职责：** 集中管理所有外部服务连接配置

**配置项：**

```python
# MySQL（元数据 + 用户数据）
MYSQL_CONFIG = {
    "host": "...",
    "port": 3306,
    "user": "...",
    "password": "...",
    "database": "data_intel"
}

# Doris（向量存储）
DORIS_CONFIG = {
    "host": "...",
    "port": 9030,
    "user": "root",
    "password": "...",
    "database": "data_intel"
}

# DashScope（LLM + Embedding）
DASHSCOPE_API_KEY = "sk-..."

# 文件存储路径
KNOWLEDGE_DIR = "data/knowledge/"
```

---

### 4.7 `utils.py` — 工具函数

**职责：** 通用辅助功能

**主要函数：**
- `hash_password(password)` — SHA-256 密码哈希
- `verify_password(password, hashed)` — 密码验证
- `allowed_file(filename)` — 检查文件扩展名是否允许上传
- `format_file_size(size_bytes)` — 字节数格式化为可读字符串

---

## 5. 数据库设计

### 5.1 MySQL 数据库（`data_intel`）

#### `users` — 用户表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| username | VARCHAR(50) UNIQUE | 用户名 |
| password | VARCHAR(255) | SHA-256 哈希密码 |
| email | VARCHAR(100) | 邮箱（可选） |
| is_admin | TINYINT(1) | 是否管理员（0/1） |
| created_at | DATETIME | 注册时间 |

#### `conversations` — 对话历史表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| user_id | INT | 关联用户 |
| role | VARCHAR(20) | `user` 或 `assistant` |
| content | TEXT | 消息内容 |
| rating | INT | 评分（1-5，可为空） |
| liked | TINYINT(1) | 点赞标记 |
| created_at | DATETIME | 消息时间 |

#### `meta_tables` — 表元数据
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| table_name | VARCHAR(200) | 英文表名 |
| table_name_cn | VARCHAR(200) | 中文表名 |
| description | TEXT | 表描述 |
| database_name | VARCHAR(100) | 所属数据库 |
| owner | VARCHAR(100) | 负责人 |
| update_frequency | VARCHAR(50) | 更新频率 |
| created_at | DATETIME | 创建时间 |

#### `meta_columns` — 列元数据
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| table_name | VARCHAR(200) | 所属表名 |
| column_name | VARCHAR(200) | 英文列名 |
| column_name_cn | VARCHAR(200) | 中文列名 |
| data_type | VARCHAR(50) | 数据类型 |
| description | TEXT | 列描述 |
| is_primary_key | TINYINT(1) | 是否主键 |
| created_at | DATETIME | 创建时间 |

#### `file_uploads` — 文件上传记录
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT AUTO_INCREMENT | 主键 |
| original_filename | VARCHAR(255) | 原始文件名 |
| stored_filename | VARCHAR(255) | 存储文件名（UUID前缀） |
| file_size | BIGINT | 文件大小（字节） |
| upload_time | DATETIME | 上传时间 |
| uploaded_by | INT | 上传用户 ID |
| chunk_count | INT | 向量分块数量 |

### 5.2 Doris 数据库（`data_intel`）

#### `knowledge_vectors` — 向量存储表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT | 主键 |
| file_id | INT | 关联文件 ID |
| chunk_index | INT | 分块序号 |
| content | TEXT | 文本内容 |
| embedding | ARRAY\<FLOAT\>(1024) | 向量（HNSW 索引） |
| created_at | DATETIME | 创建时间 |

---

## 6. 前端页面

### 6.1 `login.html` — 登录页
- Bootstrap 5.3 卡片布局
- 表单：用户名 + 密码
- 链接到注册页

### 6.2 `register.html` — 注册页
- 表单：用户名 + 密码 + 确认密码 + 邮箱（可选）
- 前端密码一致性验证

### 6.3 `chat.html` — 聊天界面
- 左侧边栏：用户信息 + 导航（管理员可见"文件管理"入口）
- 右侧主区：消息列表 + 输入框
- 消息渲染：Marked.js 解析 Markdown
- 评分组件：每条 AI 回复可点赞/踩 + 1-5 星评分
- 支持 Enter 发送，Shift+Enter 换行
- 自动滚动到最新消息

### 6.4 `admin.html` — 管理员面板
- 文件上传区（拖拽或点击选择）
- 已上传文件列表（文件名、大小、上传时间、分块数）
- 每个文件支持下载和删除操作
- 上传进度提示

---

## 7. 关键业务流程

### 7.1 用户提问流程

```
用户输入问题
    │
    ▼
POST /api/chat
    │
    ▼
intent_recognition.execute(query, user_id)
    │
    ├── 调用 qwen-turbo 识别意图 + 提取关键词
    │
    ├── 意图 = "表信息查询" / "列信息查询"
    │       │
    │       ▼
    │   datasource.get_table_info(keyword) 或 get_column_info(keyword)
    │       │
    │       ▼
    │   格式化元数据为文本上下文
    │
    └── 意图 = "指标定义查询" / "其他"
            │
            ▼
        向量化 query → Doris 相似度检索 top-k 文档块
            │
            ▼
        组合上下文 + 对话历史 → 构建 Prompt
            │
            ▼
        调用 qwen-plus 生成回答
            │
            ▼
保存对话到 MySQL conversations 表
    │
    ▼
返回 JSON { "response": "..." }
```

### 7.2 文件上传与向量化流程

```
管理员上传文件
    │
    ▼
POST /api/upload
    │
    ▼
保存文件到 data/knowledge/<uuid>_<filename>
    │
    ▼
VectorDatabaseManager.process_file(file_path)
    │
    ├── 解析文档内容（按格式选择解析器）
    ├── 文本分块（chunk_size=500, overlap=50）
    ├── 批量调用 DashScope Embedding API
    └── 写入 Doris knowledge_vectors 表
    │
    ▼
记录文件元数据到 MySQL file_uploads 表
    │
    ▼
返回 { "success": true, "chunk_count": N }
```

---

## 8. 安全设计

| 方面 | 实现方式 |
|------|----------|
| 密码存储 | SHA-256 哈希（`utils.hash_password`） |
| 会话保护 | Flask session + 随机 secret key |
| 权限控制 | `login_required` 装饰器 + `is_admin` 字段检查 |
| 文件上传 | 扩展名白名单校验（`allowed_file`） |
| 文件命名 | UUID 前缀防止路径遍历和命名冲突 |

> **注意：** 当前密码哈希使用 SHA-256 而非 bcrypt/argon2，建议生产环境升级为更安全的哈希算法。

---

## 9. 部署说明

### 9.1 依赖服务
- MySQL 8.x（元数据 + 用户数据）
- Apache Doris（向量存储，可通过 `scripts/doris-docker-compose.yml` 启动）
- DashScope API Key（通义千问 LLM + Embedding）

### 9.2 初始化步骤
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化 MySQL 表结构
mysql -u root -p < sql/create_user_table.sql
mysql -u root -p < sql/create_meta_table.sql
mysql -u root -p < sql/create_file_upload_table.sql

# 3. 初始化 Doris 向量表
# 执行 sql/doris.sql

# 4. 创建管理员用户
mysql -u root -p < scripts/create_admin_user.sql

# 5. 配置 config.py（数据库连接 + API Key）

# 6. 启动应用
python app.py
```

### 9.3 Doris 启动
```bash
cd scripts
docker-compose -f doris-docker-compose.yml up -d
bash restart_doris.sh
```

---

## 10. 已知限制与改进建议

| 问题 | 建议 |
|------|------|
| 对话历史存储在内存中（`conversation_histories` 字典） | 迁移到 Redis 或数据库，支持服务重启后恢复 |
| 密码使用 SHA-256 哈希 | 升级为 bcrypt 或 argon2 |
| 无速率限制 | 添加 API 请求频率限制防止滥用 |
| 文件存储在本地磁盘 | 生产环境建议迁移到对象存储（OSS/S3） |
| 无异步处理 | 文件向量化为同步操作，大文件会阻塞请求，建议引入任务队列（Celery） |
| 缺少单元测试 | 补充核心模块的单元测试和集成测试 |
| config.py 硬编码敏感信息 | 改用环境变量或 `.env` 文件管理密钥 |
