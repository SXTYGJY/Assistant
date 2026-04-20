#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简版意图识别系统
直接构造查询字符串，不使用PromptTemplate
"""

import os
from langchain_community.chat_models.tongyi import ChatTongyi
from rag import MetricRAGSystem
import dashscope
from dashscope import TextEmbedding

dashscope.api_key = os.getenv("OPENAI_API_KEY")

def build_query_prompt(query: str) -> str:
    return f"""
你是一个数据平台的「意图识别器」，只负责识别用户查询的意图类型，并提取一个关键词。
不要解释，不要输出多余内容。

【意图类型定义】
- 表信息查询：用户想查询某张表的基本信息
- 列信息查询：用户想查询某个字段/列的含义或信息
- 指标定义查询：用户想查询某个指标的定义或口径
- 其他：无法明确归类到以上类型

【识别规则】
1. 若用户输入中主要关注“表 xxx / xxx 表 / 表名是 xxx / xxx 这张表”等  
   → 意图类型 = 表信息查询，关键词 = 表名

2. 若用户输入中主要关注“字段 xxx / xxx 字段 / 列 xxx / 字段含义”等  
   → 意图类型 = 列信息查询，关键词 = 字段名

3. 若用户输入中主要关注“xxx 指标定义 / xxx 指标怎么算 / xxx 指标口径”等  
   → 意图类型 = 指标定义查询，关键词 = 指标名

4. 若无法明确判断  
   → 意图类型 = 其他，关键词 = default

【输出格式（严格遵守），仅包括以下两个字段的值，比如 指标定义查询:近7天用户总数】  
意图类型:关键词

【用户查询】
{query}
"""


model = ChatTongyi(
    model_name="qwen-flash",
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
)


def execute(query, user_id):
    prompt = build_query_prompt(query)
    response = model.invoke(prompt)
    print(response)
    # 更健壮的响应解析
    try:
        parts = response.content.split(":")
        print(parts)
        if len(parts) >= 2:
            intent = parts[0].strip()
            keyword = parts[1].strip()
            print(f"意图: {intent}, 关键词: {keyword}")
        else:
            intent = "其他"
            keyword = "default"

        # 确定类型
        if "表信息查询" in intent:
            types = "table"
        elif "列信息查询" in intent:
            types = "column"
        elif "指标定义查询" in intent:
            types = "document"
        else:
            types = "default"
            keyword = "default"

        rag_system = MetricRAGSystem(str(user_id), types, keyword)

        return rag_system.query_metric(query)
    except Exception as e:
        print(f"意图识别错误: {str(e)}")
        # 返回默认响应
        return "抱歉，我无法理解您的问题。请尝试更明确的提问方式。"


if __name__ == '__main__':
    response = execute("dwd_user_login_di表是什么含义", "001")
    # print(response)
