-- ============================================
-- Supabase user_account 表 + RLS 策略
-- 在 Supabase SQL 编辑器中执行
-- ============================================

-- 1. 创建用户表
CREATE TABLE IF NOT EXISTS user_account (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  dept TEXT DEFAULT '',
  position TEXT DEFAULT '',
  duty TEXT DEFAULT '',
  join_date TEXT DEFAULT '',
  leave_date TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 启用行级安全 (RLS)
ALTER TABLE user_account ENABLE ROW LEVEL SECURITY;

-- 3. 禁止 anon 角色的一切访问（前端无法直连数据库）
CREATE POLICY "deny_all_anon" ON user_account
  FOR ALL TO anon
  USING (false)
  WITH CHECK (false);

-- 4. 禁止 authenticated 角色的一切访问（前端无法直连数据库）
CREATE POLICY "deny_all_authenticated" ON user_account
  FOR ALL TO authenticated
  USING (false)
  WITH CHECK (false);

-- 5. 创建索引加速查询
CREATE INDEX IF NOT EXISTS idx_user_account_username ON user_account(username);

-- 完成！所有读写只能通过 Vercel 服务端（service_role key）中转
