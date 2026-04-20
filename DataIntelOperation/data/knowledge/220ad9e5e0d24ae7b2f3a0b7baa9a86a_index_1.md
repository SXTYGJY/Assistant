# 1.某App近30天活跃用户总数
## 业务定义
在最近30个自然日内（含当日），至少有一次登录或使用App行为的独立用户数量。用于衡量产品整体活跃度。
## SQL实现
```sql 
SELECT 
    COUNT(DISTINCT user_id) AS active_users_last_30_days
FROM 
    dws_user_login_1d
WHERE 
    dt >= '${bizdate-29}'
    AND dt <= '${bizdate}'
    AND user_id IS NOT NULL;
```
# 2.近7日订单支付成功率
## 业务定义
最近7天内，成功支付的订单数占总下单订单数的百分比，反映交易转化效率。
## SQL实现
```sql 
SELECT 
    ROUND(
        SUM(CASE WHEN order_status = 'paid' THEN 1 ELSE 0 END) * 100.0 
        / NULLIF(COUNT(*), 0), 
        2
    ) AS payment_success_rate_7d
FROM 
    dwd_order_info_di
WHERE 
    dt >= '${bizdate-6}'
    AND dt <= '${bizdate}'
    AND is_test_order = 0;
```
# 3.表平均生命周期存储成本（元/天）
## 业务定义
每张数据表在过去30天内，平均每张表每天产生的存储成本（基于逻辑存储量估算）
## SQL实现
```sql 
SELECT 
    AVG(storage_size_mb * 0.00012) AS avg_table_daily_storage_cost
FROM 
    ods_meta_table_info_dd
WHERE 
    dt = '${bizdate}'
    AND is_deleted = 0
    AND storage_size_mb > 0;
```