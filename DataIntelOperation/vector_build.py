from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
from langchain_community.embeddings import DashScopeEmbeddings
import mysql.connector
from sympy.codegen.fnodes import dimension

from config import DORIS_CONFIG
from langchain_community.document_loaders import TextLoader
import dashscope
from dashscope import TextEmbedding

dashscope.api_key = os.getenv("OPENAI_API_KEY")

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    import numpy as np
    vec1_array = np.array(vec1) if isinstance(vec1, list) else np.array(eval(vec1))
    vec2_array = np.array(vec2) if isinstance(vec2, list) else np.array(eval(vec2))
    dot_product = np.dot(vec1_array, vec2_array)
    norm1 = np.linalg.norm(vec1_array)
    norm2 = np.linalg.norm(vec2_array)
    return dot_product / (norm1 * norm2) if norm1 != 0 and norm2 != 0 else 0


def build_vector(document_name):
    """必须保证document_name是唯一的"""
    documents = []
    knowledge_dir = "./data/knowledge/"

    # 手动加载Markdown文件
    for filename in os.listdir(knowledge_dir):
        if filename.endswith('.md') and not filename.startswith('.'):
            file_path = os.path.join(knowledge_dir, filename)
            loader = TextLoader(file_path=file_path)
            docs = loader.load()
            documents.extend(docs)

    # 初始化分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["# ", "\n\n", "\n", "。"],
        length_function=len
    )
    # 进行文档分割
    chunks = [doc.page_content for doc in text_splitter.split_documents(documents)]

    # 编码所有chunks
    embeddings_data = []
    for i, chunk in enumerate(chunks):
        vector = TextEmbedding.call(model=TextEmbedding.Models.text_embedding_v3, input=chunk, dimension=512)
        embeddings_data.append(
            (document_name, chunk, str(vector.output['embeddings'][0]['embedding']))
        )
    return embeddings_data


class MysqlConnector:
    def __init__(self):
        self.conn = mysql.connector.connect(**DORIS_CONFIG)
        self.cursor = self.conn.cursor()
        self.cursor.execute("USE doris_document_db")

    def data_opt_add(self, document_name):
        # 构建文档向量数据：读取、分割、嵌入
        embeddings_data = build_vector(document_name)
        for data in embeddings_data:
            print(data)

        # 查询数据库中现有的向量数据
        self.cursor.execute("SELECT document_name, content, embedding FROM doris_vector_table")
        existing_data = self.cursor.fetchall()
        print(f"数据库中已有 {len(existing_data)} 条记录")

        # 基于余弦相似度的重复检测
        unique_embeddings_data = []
        duplicate_count = 0

        # 遍历新生成的向量数据，进行去重检测
        for document_name, chunk, new_embedding in embeddings_data:
            is_duplicate = False

            # 与数据库中所有现有向量比较相似度
            for existing_document_name, existing_content, existing_embedding in existing_data:
                similarity = cosine_similarity(new_embedding, existing_embedding)
                if similarity > 0.9:  # 相似度超过90%判定为重复
                    is_duplicate = True
                    duplicate_count += 1
                    break

            # 如果不是重复数据，则添加到待插入列表
            if not is_duplicate:
                unique_embeddings_data.append((document_name, chunk, new_embedding))

        # 仅插入不重复的数据到数据库
        if unique_embeddings_data:
            insert_sql = """
            INSERT INTO doris_vector_table
            (document_name, content, embedding)
            VALUES (%s, %s, %s)
            """
            self.cursor.executemany(insert_sql, unique_embeddings_data)
            self.conn.commit()
            print(f"✅ 成功插入 {len(unique_embeddings_data)} 条不重复数据")
        else:
            print(f"ℹ️ 没有需要插入的新数据")

    def data_opt_delete(self, document_name):
        """根据document_name从数据库中删除相关数据"""
        try:
            # 构建删除SQL语句，根据document_name删除记录
            select_sql = """
            select *
            from doris_vector_table 
            WHERE document_name = %s
            """
            self.cursor.execute(select_sql, (document_name,))
            deleted_count = len(self.cursor.fetchall())

            if deleted_count > 0:

                delete_sql = """
                DELETE FROM doris_vector_table 
                WHERE document_name = %s
                """

                # 执行删除操作
                self.cursor.execute(delete_sql, (document_name,))

                # 提交事务
                self.conn.commit()

                print(f"✅ 成功删除文档 '{document_name}' 相关的 {deleted_count} 条记录")
            else:
                print(f"ℹ️  文档 '{document_name}' 未找到相关记录，无需删除")

            return deleted_count

        except mysql.connector.Error as e:
            # 发生错误时回滚事务
            self.conn.rollback()
            print(f"❌ 删除文档 '{document_name}' 时发生错误: {e}")
            return 0

    def data_opt_select(self):
        """查询向量库数据"""
        select_sql = """
        select document_name, content, embedding
        from doris_vector_table 
        """
        self.cursor.execute(select_sql)
        result = self.cursor.fetchall()
        return result


if __name__ == '__main__':
    mysql_connector = MysqlConnector()

    # 添加数据到数据库
    mysql_connector.data_opt_add("index")

    # 删除指定文档的数据
    # mysql_connector.data_opt_delete("index")
    # 查询文档数据
    # result = mysql_connector.data_opt_select()
    # for row in result:
    #     print(row)
