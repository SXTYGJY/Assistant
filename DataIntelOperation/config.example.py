# 数据库配置示例文件 - 复制为 config.py 并填入真实配置
DB_CONFIG_BUSINESS = {
    'host': 'YOUR_HOST',
    'user': 'YOUR_USER',
    'password': 'YOUR_PASSWORD',
    'database': 'business_db',
    'port': 3306,
    'auth_plugin': 'mysql_native_password'
}

DB_CONFIG_META = {
    'host': 'YOUR_HOST',
    'user': 'YOUR_USER',
    'password': 'YOUR_PASSWORD',
    'database': 'data_metadata',
    'port': 3306,
    'auth_plugin': 'mysql_native_password'
}

DORIS_CONFIG = {
    'host': 'YOUR_HOST',
    'user': 'YOUR_USER',
    'password': 'YOUR_PASSWORD',
    'database': 'doris_document_db',
    'port': 9030
}
