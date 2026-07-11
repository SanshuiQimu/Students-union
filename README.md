# 学生会人事管理系统

> 华东师范大学附属龙港科技中学学生会人事管理系统 — 基于 Flask 的轻量化校园人事台账平台。

[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE) [![Python](https://img.shields.io/badge/python-3.8%2B-blue)](#)

---

目录
- 一、项目概览
- 二、核心功能（快速导航）
- 三、目录结构
- 四、本地快速运行
- 五、环境变量（云部署）
- 六、部署建议
- 七、数据库设计
- 八、默认管理员
- 九、API 摘要
- 十、项目亮点
- 十一、常见问题（FAQ)
- 十二、贡献指南
- 十三、许可证

---

## 一、项目概览

简述：本项目面向中学学生会管理人员与辅导老师，提供成员档案、账号鉴权、公告管理与多端同步功能。后端以 single-file Flask（main.py）为主，前端采用静态 HTML + PWA 配置，部署门槛低，适合教学与小规模校内使用。

技术要点：Flask、gunicorn、SQLite（本地）/PostgreSQL（云）、Supabase（账号同步）、PBKDF2 密码哈希、线程锁并发保护。

---

## 二、核心功能（快速导航）

| 模块 | 接口示例 | 说明 |
|---|---:|---|
| 成员管理 | GET /api/members<br>POST /api/members<br>PUT /api/member/{id}<br>DELETE /api/member/{id} | 成员增删改查，批量导入，自动同步 Supabase |
| 账号鉴权 | POST /api/auth/login<br>POST /api/auth/register<br>GET /api/auth/users | Supabase 鉴权、账号管理、初始化管理员 |
| 公告管理 | GET /api/messages<br>POST /api/messages | 公告读取与批量覆盖 |
| 系统 | GET /api/diagnose<br>GET /api/auth/status | Supabase 连接与认证状态诊断 |

---

## 三、目录结构

```
student-union-admin/
├── main.py            # Flask 后端主程序（全部接口、同步逻辑）
├── index.html         # 管理界面与登录页面（静态渲染）
├── manifest.json      # PWA 配置
├── requirements.txt   # 依赖清单
├── vercel.json        # Vercel 部署路由配置
├── school-logo.png    # 校徽 / PWA 图标
└── data.db            # 本地 SQLite（运行时生成）
```

---

## 四、本地快速运行

前置：Python 3.8+

克隆并运行：

```bash
git clone https://github.com/<你的用户名>/student-union-admin.git
cd student-union-admin
pip install -r requirements.txt
python main.py
# 访问 http://127.0.0.1:5000
```

生产（gunicorn）：

```bash
gunicorn main:app --bind 0.0.0.0:5000
```

---

## 五、环境变量（云部署）

要启用云持久化与账号同步，请在部署平台中设置：

- PostgreSQL（Railway）
  - DATABASE_URL=postgresql://user:pass@host:port/dbname
- Supabase（账号与同步）
  - SUPABASE_URL=https://<project>.supabase.co
  - SUPABASE_SERVICE_KEY=<service_key>
- 持久化卷（Railway）
  - RAILWAY_VOLUME_MOUNT_PATH=/data

未设置时系统自动使用本地 SQLite（开箱即用）。

---

## 六、部署建议（按场景）

- Vercel（免费 serverless） — 适合演示与轻量部署。注意：/tmp 与临时文件会随实例重启而丢失，建议开启 Supabase 同步以保证数据持久化。
- Railway — 适合生产，推荐绑定 PostgreSQL 并启用 Volume 挂载。
- 私有服务器 — 直接运行 Python 或 gunicorn，开放 5000 端口并做进程管理（systemd / supervisor）。

---

## 七、数据库设计（简要）

- members
  - id INTEGER PRIMARY KEY
  - data TEXT — JSON 字符串（姓名、部门、职位、职责、入职日期、passwordHash 等）
- messages
  - id INTEGER PRIMARY KEY
  - data TEXT — JSON 数组保存公告列表
- meta
  - key TEXT PRIMARY KEY
  - value TEXT — 系统元数据（如已初始化标记）

Supabase 云端表：user_account（username, password_hash, name, dept, position, join_date, leave_date）

---

## 八、默认管理员

首次启动会自动创建默认管理员：

- 姓名 / 用户名：林可翔
- 部门：秘书处 — 处长
- 初始密码：123456（请首次登录后立即修改）

---

## 九、API 摘要（精选）

- 成员：GET /api/members | POST /api/members | PUT /api/member/{id} | DELETE /api/member/{id}
- 公告：GET /api/messages | POST /api/messages
- 认证：POST /api/auth/login | POST /api/auth/register | POST /api/auth/init | GET /api/auth/status
- 诊断：GET /api/diagnose

> 详尽接口与参数建议在 docs/API.md 中补充（可请求生成）。

---

## 十、项目亮点

- 多数据库自适应：SQLite（本地）→ PostgreSQL（云）→ Supabase（账号同步）
- 轻量依赖：仅 Flask + gunicorn
- 安全：PBKDF2 加盐密码哈希、线程锁防止并发写冲突
- 支持 PWA：移动端桌面安装体验
- 开箱即用：首次运行自动建表并插入默认管理员

---

## 十一、常见问题（FAQ）

Q: 启动后无法访问？
A: 检查端口 5000、防火墙设置并确认服务在运行。

Q: Vercel 部署后数据丢失？
A: Vercel 无持久化，启用 Supabase 同步或使用 PostgreSQL。

Q: 忘记管理员密码？
A: 可调用 POST /api/auth/init 重置默认管理员，或在 SQLite 中直接修改 passwordHash 字段。

---

## 十二、贡献指南

1. Fork → 新分支 feature/xxx
2. 本地开发并测试
3. 发起 PR，说明变更与测试步骤

规范：保持接口分层、数据库操作使用锁保护并兼容多数据库逻辑。

---

## 十三、许可证

MIT License — 可用于校内教学与二次开发，保留开源声明后可商用。

---

需要将 README 同步回 Git 仓库并尝试推送吗？或要我生成英文版/截图示例/API 文档（docs/API.md）？