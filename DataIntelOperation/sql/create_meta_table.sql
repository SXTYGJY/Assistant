-- 元数据表
CREATE TABLE IF NOT EXISTS `ods_meta_table_info_dd` (
  `id` BIGINT COMMENT '主键ID',
  `catalog_name` VARCHAR(255) COMMENT '数据源或集群名称',
  `database_name` VARCHAR(255) COMMENT '库名',
  `table_name` VARCHAR(255) COMMENT '表名',
  `layer` VARCHAR(20) COMMENT '分层（ODS/DWD/DWS/ADS）',
  `table_creator_id` VARCHAR(100) COMMENT '表创建人ID',
  `table_creator_name` VARCHAR(100) COMMENT '表创建人姓名',
  `comment` TEXT COMMENT '表描述',
  `table_type` TINYINT COMMENT '1-内部表, 2-外部表, 3-视图',
  `storage_location` VARCHAR(500) COMMENT '表存储路径',
  `file_count` BIGINT,
  `storage_size_mb` DECIMAL(18,2) COMMENT '逻辑存储量（MB，不含副本）',
  `daily_file_inc` BIGINT COMMENT '日新增文件数',
  `daily_size_inc_mb` DECIMAL(18,2) COMMENT '日新增存储量（MB）',
  `last_access_time` DATETIME COMMENT '最后访问时间',
  `create_time` DATETIME COMMENT '表创建时间',
  `is_partitioned` TINYINT COMMENT '是否分区表：1-是，0-否',
  `visit_count` BIGINT COMMENT '总访问次数',
  `is_deleted` TINYINT COMMENT '是否已下线：1-是，0-否',
  `is_cold` TINYINT COMMENT '是否30天无访问：1-是，0-否',
  `partition_count` BIGINT COMMENT '分区数量',
  `small_file_count` BIGINT COMMENT '小文件数量（<128MB）',
  `lifecycle_days` BIGINT COMMENT '表生命周期（天）',
  `compress_format` VARCHAR(50) COMMENT '压缩格式',
  `storage_format` VARCHAR(50) COMMENT '存储格式（如 PARQUET/ORC）',
  `task_id` VARCHAR(255) COMMENT '关联的任务ID',
  `dt` VARCHAR(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
  PRIMARY KEY (`id`, `dt`)  -- 若 id 非全局唯一，可仅设 dt 为普通索引；此处假设组合主键
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS层-元数据域-表信息-全量表';
INSERT INTO `ods_meta_table_info_dd` VALUES
(1, 'hive_prod', 'dwd', 'dwd_user_login_di', 'DWD', 'u1001', '张三', '用户每日登录事实表', 1, '/warehouse/dwd/user_login', 120, 2560.50, 4, 85.30, '2026-01-30 14:22:00', '2024-06-01 10:00:00', 1, 1500, 0, 0, 365, 12, 3650, 'snappy', 'PARQUET', 'task_001', '20260131'),
(2, 'hive_prod', 'ods', 'ods_log_raw_dd', 'ODS', 'u1002', '李四', '原始日志采集表', 2, '/warehouse/ods/log_raw', 890, 18432.75, 30, 614.42, '2026-01-31 09:15:00', '2023-11-10 08:30:00', 1, 9800, 0, 0, 730, 200, 1825, 'gzip', 'TEXTFILE', 'task_002', '20260131'),
(3, 'clickhouse_dev', 'ads', 'ads_user_summary_dm', 'ADS', 'u1003', '王五', '用户月度汇总指标', 3, NULL, 0, 120.80, 0, 5.20, '2026-01-25 16:40:00', '2025-01-05 11:20:00', 0, 320, 0, 1, 0, 0, 365, 'lz4', 'MergeTree', 'task_003', '20260131'),
(4, 'hive_prod', 'dws', 'dws_user_behavior_1d', 'DWS', 'u1001', '张三', '用户日行为宽表', 1, '/warehouse/dws/user_behavior', 60, 5120.00, 2, 170.67, '2026-01-31 18:00:00', '2024-08-12 14:00:00', 1, 2100, 0, 0, 180, 5, 730, 'snappy', 'PARQUET', 'task_004', '20260131'),
(5, 'hive_prod', 'ods', 'ods_order_detail_dd', 'ODS', 'u1004', '赵六', '订单明细原始表', 2, '/warehouse/ods/order_detail', 450, 9216.30, 15, 307.21, '2026-01-29 11:10:00', '2023-12-01 09:45:00', 1, 4500, 1, 1, 365, 80, 1095, 'none', 'ORC', 'task_005', '20260131'),
(6, 'hive_test', 'dwd', 'dwd_payment_fact_di', 'DWD', 'u1005', '钱七', '支付事实表', 1, '/test_warehouse/dwd/payment', 30, 640.25, 1, 21.34, '2026-01-30 20:05:00', '2025-03-15 16:30:00', 0, 890, 0, 0, 0, 0, 365, 'snappy', 'PARQUET', 'task_006', '20260131'),
(7, 'hive_prod', 'ads', 'ads_sales_report_dm', 'ADS', 'u1002', '李四', '销售月报', 3, NULL, 0, 80.50, 0, 2.70, '2026-01-20 10:00:00', '2024-05-20 13:15:00', 0, 120, 0, 1, 0, 0, 730, 'snappy', 'VIEW', 'task_007', '20260131'),
(8, 'hive_prod', 'dws', 'dws_product_click_1d', 'DWS', 'u1006', '孙八', '商品点击日汇总', 1, '/warehouse/dws/product_click', 25, 320.60, 1, 12.82, '2026-01-31 07:30:00', '2024-10-10 09:00:00', 1, 650, 0, 0, 90, 3, 365, 'snappy', 'PARQUET', 'task_008', '20260131'),
(9, 'hive_prod', 'ods', 'ods_user_profile_dd', 'ODS', 'u1001', '张三', '用户画像原始数据', 2, '/warehouse/ods/user_profile', 200, 4096.00, 7, 136.53, '2026-01-28 15:45:00', '2024-01-15 10:20:00', 1, 3000, 0, 1, 365, 50, 1825, 'gzip', 'JSON', 'task_009', '20260131'),
(10, 'hive_prod', 'dwd', 'dwd_page_view_di', 'DWD', 'u1003', '王五', '页面浏览事件表', 1, '/warehouse/dwd/page_view', 180, 3686.40, 6, 122.88, '2026-01-31 12:10:00', '2024-07-01 08:00:00', 1, 5400, 0, 0, 365, 18, 730, 'snappy', 'PARQUET', 'task_010', '20260131');


CREATE TABLE IF NOT EXISTS `ods_meta_columns_info_dd` (
  `id` BIGINT COMMENT '主键ID',
  `catalog_name` VARCHAR(255) COMMENT '数据源或集群名称',
  `database_name` VARCHAR(255) COMMENT '数据库名',
  `table_name` VARCHAR(255) COMMENT '表名',
  `column_name` VARCHAR(255) COMMENT '字段名称',
  `data_type` VARCHAR(100) COMMENT '字段数据类型',
  `column_desc` TEXT COMMENT '字段描述或业务含义',
  `ordinal_position` INT COMMENT '字段在表中的位置（从1开始）',
  `is_partition_key` TINYINT COMMENT '是否为分区字段：0-否，1-是',
  `create_by` VARCHAR(100) COMMENT '创建人',
  `create_time` DATETIME COMMENT '创建时间',
  `update_by` VARCHAR(100) COMMENT '最后更新人',
  `update_time` DATETIME COMMENT '最后更新时间',
  `dt` VARCHAR(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
  PRIMARY KEY (`id`, `dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS层-元数据域-字段信息-全量表';

INSERT INTO `ods_meta_columns_info_dd` VALUES
(1, 'hive_prod', 'dwd', 'dwd_user_login_di', 'user_id', 'bigint', '用户唯一ID', 1, 0, 'u1001', '2024-06-01 10:00:00', 'u1001', '2024-06-01 10:00:00', '20260131'),
(2, 'hive_prod', 'dwd', 'dwd_user_login_di', 'login_date', 'date', '登录日期', 2, 1, 'u1001', '2024-06-01 10:00:00', 'u1001', '2024-06-01 10:00:00', '20260131'),
(3, 'hive_prod', 'dwd', 'dwd_user_login_di', 'login_ts', 'timestamp', '登录时间戳', 3, 0, 'u1001', '2024-06-01 10:00:00', 'u1001', '2024-06-01 10:00:00', '20260131'),
(4, 'hive_prod', 'ods', 'ods_log_raw_dd', 'log_id', 'string', '日志唯一标识', 1, 0, 'u1002', '2023-11-10 08:30:00', 'u1002', '2023-11-10 08:30:00', '20260131'),
(5, 'hive_prod', 'ods', 'ods_log_raw_dd', 'event_time', 'bigint', '事件发生时间（Unix秒）', 2, 0, 'u1002', '2023-11-10 08:30:00', 'u1002', '2023-11-10 08:30:00', '20260131'),
(6, 'hive_prod', 'ods', 'ods_log_raw_dd', 'dt', 'string', '分区字段：业务日期', 3, 1, 'u1002', '2023-11-10 08:30:00', 'u1002', '2023-11-10 08:30:00', '20260131'),
(7, 'clickhouse_dev', 'ads', 'ads_user_summary_dm', 'user_cnt', 'UInt64', '活跃用户数', 1, 0, 'u1003', '2025-01-05 11:20:00', 'u1003', '2025-01-05 11:20:00', '20260131'),
(8, 'hive_prod', 'dws', 'dws_user_behavior_1d', 'user_id', 'bigint', '用户ID', 1, 0, 'u1001', '2024-08-12 14:00:00', 'u1001', '2024-08-12 14:00:00', '20260131'),
(9, 'hive_prod', 'dws', 'dws_user_behavior_1d', 'behavior_cnt', 'int', '行为次数', 2, 0, 'u1001', '2024-08-12 14:00:00', 'u1001', '2024-08-12 14:00:00', '20260131'),
(10, 'hive_prod', 'dws', 'dws_user_behavior_1d', 'stat_date', 'date', '统计日期', 3, 1, 'u1001', '2024-08-12 14:00:00', 'u1001', '2024-08-12 14:00:00', '20260131');


CREATE TABLE IF NOT EXISTS `ods_meta_table_lineage_dd` (
  `id` BIGINT COMMENT '主键ID',
  `source_catalog_name` VARCHAR(255) COMMENT '上游数据源或集群名称',
  `source_database_name` VARCHAR(255) COMMENT '上游数据库名',
  `source_table_name` VARCHAR(255) COMMENT '上游表名',
  `source_table_layer` VARCHAR(20) COMMENT '上游表分层',
  `target_catalog_name` VARCHAR(255) COMMENT '下游数据源或集群名称',
  `target_database_name` VARCHAR(255) COMMENT '下游数据库名',
  `target_table_name` VARCHAR(255) COMMENT '下游表名',
  `target_table_layer` VARCHAR(20) COMMENT '下游表分层',
  `lineage_type` TINYINT COMMENT '血缘关系类型：-1=上游，1=下游',
  `create_by` VARCHAR(100) COMMENT '创建人',
  `create_time` DATETIME COMMENT '创建时间',
  `update_by` VARCHAR(100) COMMENT '最后更新人',
  `update_time` DATETIME COMMENT '最后更新时间',
  `sync_timestamp` DATETIME COMMENT '血缘同步时间',
  `dt` VARCHAR(8) NOT NULL COMMENT '业务日期，格式：YYYYMMDD',
  PRIMARY KEY (`id`, `dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS层-元数据域-表血缘信息-全量表';

INSERT INTO `ods_meta_table_lineage_dd` VALUES
(1, 'hive_prod', 'ods', 'ods_log_raw_dd', 'ODS', 'hive_prod', 'dwd', 'dwd_user_login_di', 'DWD', 1, 'system', '2024-06-01 10:05:00', 'system', '2024-06-01 10:05:00', '2026-01-31 00:00:00', '20260131'),
(2, 'hive_prod', 'ods', 'ods_log_raw_dd', 'ODS', 'hive_prod', 'dwd', 'dwd_page_view_di', 'DWD', 1, 'system', '2024-07-01 08:05:00', 'system', '2024-07-01 08:05:00', '2026-01-31 00:00:00', '20260131'),
(3, 'hive_prod', 'dwd', 'dwd_user_login_di', 'DWD', 'hive_prod', 'dws', 'dws_user_behavior_1d', 'DWS', 1, 'system', '2024-08-12 14:05:00', 'system', '2024-08-12 14:05:00', '2026-01-31 00:00:00', '20260131'),
(4, 'hive_prod', 'dwd', 'dwd_page_view_di', 'DWD', 'hive_prod', 'dws', 'dws_user_behavior_1d', 'DWS', 1, 'system', '2024-08-12 14:06:00', 'system', '2024-08-12 14:06:00', '2026-01-31 00:00:00', '20260131'),
(5, 'hive_prod', 'dws', 'dws_user_behavior_1d', 'DWS', 'hive_prod', 'ads', 'ads_user_summary_dm', 'ADS', 1, 'system', '2025-01-05 11:25:00', 'system', '2025-01-05 11:25:00', '2026-01-31 00:00:00', '20260131'),
(6, 'hive_prod', 'ods', 'ods_order_detail_dd', 'ODS', 'hive_prod', 'dwd', 'dwd_payment_fact_di', 'DWD', 1, 'system', '2025-03-15 16:35:00', 'system', '2025-03-15 16:35:00', '2026-01-31 00:00:00', '20260131'),
(7, 'hive_prod', 'dwd', 'dwd_payment_fact_di', 'DWD', 'hive_prod', 'ads', 'ads_sales_report_dm', 'ADS', 1, 'system', '2024-05-20 13:20:00', 'system', '2024-05-20 13:20:00', '2026-01-31 00:00:00', '20260131'),
(8, 'hive_prod', 'ods', 'ods_user_profile_dd', 'ODS', 'hive_prod', 'dwd', 'dwd_user_profile_di', 'DWD', 1, 'system', '2024-01-15 10:25:00', 'system', '2024-01-15 10:25:00', '2026-01-31 00:00:00', '20260131'),
(9, 'hive_prod', 'dwd', 'dwd_user_profile_di', 'DWD', 'hive_prod', 'dws', 'dws_user_tag_1d', 'DWS', 1, 'system', '2024-02-01 09:00:00', 'system', '2024-02-01 09:00:00', '2026-01-31 00:00:00', '20260131'),
(10, 'hive_prod', 'dws', 'dws_product_click_1d', 'DWS', 'hive_prod', 'ads', 'ads_product_hot_rank_dm', 'ADS', 1, 'system', '2024-10-10 09:05:00', 'system', '2024-10-10 09:05:00', '2026-01-31 00:00:00', '20260131');