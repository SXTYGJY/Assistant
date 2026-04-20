-- 修改用户表，移除email字段的唯一约束，允许重复的NULL值
ALTER TABLE users MODIFY email VARCHAR(100) UNIQUE;

-- 或者如果上面语法报错，可以使用以下替代方案：
-- ALTER TABLE users DROP INDEX email;
-- ALTER TABLE users MODIFY email VARCHAR(100);

-- 然后设置email字段可以为NULL，并对NULL值去除唯一约束
ALTER TABLE users MODIFY email VARCHAR(100) NULL;

-- 清理可能存在的空字符串记录（如果有的话）
UPDATE users SET email = NULL WHERE email = '';