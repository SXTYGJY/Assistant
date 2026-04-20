#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from decimal import Decimal
from datetime import datetime, date

class DecimalEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理Decimal类型"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # 将Decimal转换为float
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            # 将日期时间转换为字符串
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # 处理自定义对象
            return obj.__dict__

        # 让基类处理其他类型
        return super().default(obj)

def serialize_for_json(data):
    """将数据序列化为JSON可序列化的格式"""
    if isinstance(data, (list, tuple)):
        return [serialize_for_json(item) for item in data]
    elif isinstance(data, dict):
        return {key: serialize_for_json(value) for key, value in data.items()}
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, (datetime, date)):
        return data.isoformat()
    else:
        return data

def safe_json_dumps(data, **kwargs):
    """安全的JSON序列化函数，自动处理Decimal等不可序列化类型"""
    return json.dumps(data, cls=DecimalEncoder, **kwargs)