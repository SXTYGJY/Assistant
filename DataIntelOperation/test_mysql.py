#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试数据库连接问题
"""

import sys
import mysql.connector
from datetime import datetime
from config import DB_CONFIG_META

def test_direct_connection():
    """测试直接连接"""
    print("=== 直接连接测试 ===")
    try:
        conn = mysql.connector.connect(**DB_CONFIG_META)
        if conn.is_connected():
            print("✅ 直接连接成功")
            conn.close()
            return True
        else:
            print("❌ 直接连接失败")
            return False
    except Exception as e:
        print(f"❌ 直接连接异常: {e}")
        return False

def test_search_by_table():
    """测试 search_by_table 函数"""
    print("\\n=== search_by_table 测试 ===")
    try:
        import datasource
        result = datasource.search_by_table('dws_user_behavior_1d')
        if result is not None:
            print(f"✅ search_by_table 成功，找到 {len(result)} 条记录")
            return True
        else:
            print("❌ search_by_table 返回 None")
            return False
    except Exception as e:
        print(f"❌ search_by_table 异常: {e}")
        return False

def test_database_connector():
    """测试 DatabaseConnector 类"""
    print("\\n=== DatabaseConnector 测试 ===")
    try:
        import datasource
        db = datasource.DatabaseConnector()
        if db.connect():
            print("✅ DatabaseConnector 连接成功")
            tables = db.get_tables()
            print(f"  获取到 {len(tables)} 个表")
            db.close()
            return True
        else:
            print("❌ DatabaseConnector 连接失败")
            return False
    except Exception as e:
        print(f"❌ DatabaseConnector 异常: {e}")
        return False

if __name__ == "__main__":
    print(f"调试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]}")
    print(f"Python 版本: {sys.version}")

    success_count = 0
    total_tests = 3

    if test_direct_connection():
        success_count += 1

    if test_search_by_table():
        success_count += 1

    if test_database_connector():
        success_count += 1

    print(f"\\n=== 测试结果 {success_count}/{total_tests} 通过 ===")
    if success_count == total_tests:
        print("🎉 所有测试通过，数据库连接正常")
    else:
        print("⚠️ 部分测试失败，请检查配置")