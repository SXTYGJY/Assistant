#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库连接工具类
支持MySQL数据库的连接、查询、插入等基本操作
"""

import mysql.connector
from mysql.connector import Error
import logging
from typing import List, Dict, Any, Optional
from config import DB_CONFIG_META

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseConnector:
    """数据库连接器类"""

    def __init__(self,
                 host: str = None,
                 user: str = None,
                 password: str = None,
                 database: str = None,
                 port: int = None):
        """
        初始化数据库连接

        Args:
            host: 数据库主机地址(可选，默认从config.py读取)
            user: 用户名(可选)
            password: 密码(可选)
            database: 数据库名称(可选)
            port: 端口号(可选)
        """
        self.host = DB_CONFIG_META['host'] or host
        self.user = DB_CONFIG_META['user'] or user
        self.password = DB_CONFIG_META['password'] or password
        self.database = DB_CONFIG_META['database'] or database
        self.port = DB_CONFIG_META['port'] or port
        self.connection = None
        self.cursor = None

    def connect(self) -> bool:
        """连接到数据库"""
        try:
            # 构建连接配置，包含认证插件
            connection_config = {
                'host': self.host,
                'user': self.user,
                'password': self.password,
                'database': self.database,
                'port': self.port,
                'auth_plugin': 'mysql_native_password'
            }

            self.connection = mysql.connector.connect(**connection_config)

            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
                # 兼容性处理：获取服务器信息
                try:
                    db_info = self.connection.get_server_info()
                    # db_info = self.connection.server_info
                except:
                    db_info = "unknown version"
                logger.info(f"成功连接到MySQL服务器，版本: {db_info}")
                return True

        except Error as e:
            logger.error(f"数据库连接失败: {e}")
            return False

    def execute_query(self, query: str, params: tuple = None) -> Optional[List[Dict]]:
        """
        执行查询语句

        Args:
            query: SQL查询语句
            params: 查询参数

        Returns:
            查询结果列表或None
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return None

            self.cursor.execute(query, params or ())
            results = self.cursor.fetchall()
            logger.info(f"查询执行成功，返回 {len(results)} 条记录")
            return results

        except Error as e:
            logger.error(f"查询执行失败: {e}")
            return None

    def execute_update(self, query: str, params: tuple = None) -> bool:
        """
        执行更新操作（INSERT, UPDATE, DELETE）

        Args:
            query: SQL语句
            params: 参数

        Returns:
            是否执行成功
        """
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return False

            self.cursor.execute(query, params or ())
            self.connection.commit()
            logger.info(f"更新操作执行成功，影响行数: {self.cursor.rowcount}")
            return True

        except Error as e:
            logger.error(f"更新操作失败: {e}")
            if self.connection:
                self.connection.rollback()
            return False

    def get_tables(self) -> Optional[List[str]]:
        """获取数据库中的所有表名"""
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return None

            self.cursor.execute("SHOW TABLES")
            tables = [table['Tables_in_' + self.database] for table in self.cursor.fetchall()]
            return tables

        except Error as e:
            logger.error(f"获取表列表失败: {e}")
            return None

    def get_table_info(self, table_name: str) -> Optional[List[Dict]]:
        """获取表结构信息"""
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect():
                    return None

            self.cursor.execute(f"DESCRIBE {table_name}")
            return self.cursor.fetchall()

        except Error as e:
            logger.error(f"获取表结构失败: {e}")
            return None

    def close(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("数据库连接已关闭")


def search_by_table(keyword: str):
    """根据表名关键字模糊查询指定的表"""
    db = DatabaseConnector(
        host=DB_CONFIG_META['host'],
        user=DB_CONFIG_META['user'],
        password=DB_CONFIG_META['password'],
        database=DB_CONFIG_META['database'],
        port=DB_CONFIG_META['port']
    )

    try:
        if db.connect():
            # 构造模糊查询SQL，使用 % 作为通配符
            query = f"""
                SELECT table_name, catalog_name, database_name, layer, 
                       table_creator_name, comment, table_type, storage_location,
                       storage_size_mb, visit_count, create_time, is_deleted
                FROM ods_meta_table_info_dd
                WHERE table_name LIKE %s
                OR comment LIKE %s
                ORDER BY table_name
            """
            # 添加 % 到关键字前后实现模糊匹配
            params = (f"%{keyword}%", f"%{keyword}%")

            results = db.execute_query(query, params)

            return results
    finally:
        db.close()


def search_by_table_lineage(keyword: str):
    """根据表名关键字模糊查询表血缘关系"""
    db = DatabaseConnector(
        host=DB_CONFIG_META['host'],
        user=DB_CONFIG_META['user'],
        password=DB_CONFIG_META['password'],
        database=DB_CONFIG_META['database'],
        port=DB_CONFIG_META['port']
    )
    try:
        if db.connect():
            # 构造模糊查询SQL，搜索源表名或目标表名包含关键字的血缘关系
            query = """
                SELECT * FROM ods_meta_table_lineage_dd
                WHERE source_table_name LIKE %s
                OR target_table_name LIKE %s
                ORDER BY source_table_name, target_table_name
            """
            # 添加 % 到关键字前后实现模糊匹配
            params = (f"%{keyword}%", f"%{keyword}%")

            results = db.execute_query(query, params)
            return results

    finally:
        db.close()


def search_by_column(keyword: str):
    """根据表名关键字模糊查询指定的表"""
    db = DatabaseConnector(
        host=DB_CONFIG_META['host'],
        user=DB_CONFIG_META['user'],
        password=DB_CONFIG_META['password'],
        database=DB_CONFIG_META['database'],
        port=DB_CONFIG_META['port']
    )

    try:
        if db.connect():
            # 构造模糊查询SQL，使用 % 作为通配符
            query = f"""
                SELECT * FROM ods_meta_columns_info_dd
                WHERE column_name LIKE %s
                or column_desc LIKE %s
                ORDER BY column_name
            """
            # 添加 % 到关键字前后实现模糊匹配
            params = (f"%{keyword}%", f"%{keyword}%")

            results = db.execute_query(query, params)
            return results
    finally:
        db.close()


if __name__ == "__main__":
    print("======")
    print(search_by_table("dws_user_behavior_1d"))
    print("======")
    # search_by_column("user")
