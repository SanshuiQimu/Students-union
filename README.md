学生会人事管理系统
华东师范大学附属龙港科技中学学生会人事管理系统，基于 Flask 全栈一体开发，轻量化校园人事台账管理平台，支持本地 SQLite / 云 PostgreSQL/Supabase 三方数据同步存储，适配服务器、Vercel Serverless、Railway 云部署。
一、项目概览
1. 项目背景
面向中学学生会日常管理需求，解决学生会成员信息分散、人员增减无台账、登录权限缺失、消息公告无统一存储等痛点，打造轻量化校内人事管理网页系统，无需复杂前端分离工程，单文件后端承载全部接口，静态 HTML 直接渲染页面，部署门槛极低。
2. 核心定位
•使用对象：学校学生会管理人员、团委老师、学生会干事
•核心用途：学生会成员档案管理、账号登录鉴权、内部消息公告存储、人员增删改查
•部署场景：本地电脑调试、Vercel 免费 serverless、Railway 云服务器、私有 Linux 主机
3. 技术栈
后端（[main.py](main.py)）
•Web 框架：Flask
•Web 服务：gunicorn（生产部署）
•数据库兼容：
a.本地轻量：SQLite（默认，无需额外服务）
b.云持久化：PostgreSQL（Railway 数据库）
c.在线认证同步：Supabase（用户账号、密码鉴权、跨端同步）
•密码安全：PBKDF2 加盐哈希 + 兼容旧版 SHA256 加盐校验
•并发控制：线程锁防止多请求数据库冲突
•网络工具：urllib 实现 Supabase REST 接口调用，无额外第三方 SDK
前端静态资源
•index.html：系统主页面（管理界面、登录页面）
•manifest.json：PWA 应用配置，支持手机离线桌面安装
•school-logo.png：校徽图标（PWA 图标）
部署配置文件
•requirements.txt：Python 依赖清单
•vercel.json：Vercel 一键 Serverless 部署路由配置
二、核心功能清单
1. 成员人事管理（核心模块）
•成员列表全量查询：/api/members GET
•批量导入 / 覆盖全部成员：/api/members POST
•单成员信息修改：/api/member/<mid> PUT
•删除指定成员：/api/member/<mid> DELETE
•自动同步成员数据至 Supabase 云端用户表
2. 用户登录与账号体系（Supabase 鉴权）
•用户登录校验（密码哈希比对）：/api/auth/login
•新干事账号注册：/api/auth/register
•全员账号列表查询：/api/auth/users
•修改账号信息 / 重置密码：/api/auth/update
•删除账号：/api/auth/delete
•初始化默认管理员账号（林可翔，初始密码 123456）：/api/auth/init
•认证状态诊断接口：/api/auth/status
3. 内部消息公告管理
•获取全部存储消息：/api/messages GET
•批量更新 / 覆盖公告消息：/api/messages POST
4. 系统诊断与多数据库适配
•数据库自动降级策略：优先 PostgreSQL → SQLite
•SQLite 自动适配多平台可写目录：/data / /tmp / 项目本地
•Supabase 连接诊断接口 /api/diagnose
•启动自动初始化数据库表与默认管理员数据
•多端数据双向同步：本地库 ↔ Supabase 云端
5. 静态页面与 PWA 支持
•根路径访问自动渲染 index.html 管理页面
•全部静态资源（图片、页面）统一路由分发
•PWA 配置文件，手机添加到桌面独立运行
三、项目目录结构
Plain Text
student-union-admin/
├── main.py               # Flask后端主程序，全部接口、数据库逻辑、Supabase同步
├── index.html            # 前端管理页面、登录页面
├── manifest.json         # PWA桌面应用配置
├── requirements.txt     # Python运行依赖
├── vercel.json           # Vercel云部署配置
├── school-logo.png       # PWA图标、页面校徽资源
└── data.db（运行生成）   # SQLite本地数据库文件
四、本地快速运行指南
1. 环境前置
Python 3.8 及以上版本
2. 克隆仓库
bash
git clone https://github.com/你的用户名/student-union-admin.git
cd student-union-admin
3. 安装依赖
bash
pip install -r requirements.txt
4. 本地启动（开发模式）
bash
python main.py
访问地址：http://127.0.0.1:5000
5. 生产环境启动（gunicorn）
bash
gunicorn main:app --bind 0.0.0.0:5000
五、环境变量配置（云数据库 / Supabase）
如需开启云端持久化、跨设备账号同步，配置以下环境变量：
1.PostgreSQL 云数据库（Railway）
env
DATABASE_URL=postgresql://账号:密码@host:端口/数据库名
2.Supabase 账号同步（登录、跨端数据同步）
env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=你的supabase服务密钥
3.Railway 持久化卷（避免 SQLite 数据丢失）
env
RAILWAY_VOLUME_MOUNT_PATH=/data

不配置上述环境变量时，系统自动降级使用本地 SQLite，开箱即用无需额外数据库。
六、部署教程
方案 1：Vercel 免费 Serverless 部署
项目内置vercel.json，一键部署：
1.GitHub 仓库关联 Vercel
2.无需修改配置，自动识别 Python 构建
3.如需 Supabase/PostgreSQL，在 Vercel 后台添加对应环境变量
注意：Vercel 临时目录/tmp存储 SQLite，重新部署数据会清空，正式使用建议开启 Supabase 同步。
方案 2：Railway 云服务器部署
1.上传项目至 GitHub，Railway 关联仓库
2.可选绑定 PostgreSQL 数据库，自动注入DATABASE_URL环境变量
3.开启 Volume 持久化挂载，防止 SQLite 丢失数据
4.添加 Supabase 环境变量实现跨端数据同步
方案 3：本地 Windows/Linux 服务器
直接运行python main.py或 gunicorn，端口 5000，防火墙放行端口即可局域网访问。
七、数据库设计说明
1. SQLite/PostgreSQL 三张数据表
1.members：学生会成员表，JSON 格式存储人员完整信息
￮id：自增主键
￮data：JSON 字符串（姓名、部门、职位、职责、入职日期、密码哈希等）
2.messages：公告消息表
￮id：自增主键
￮data：JSON 数组存储全部公告内容
3.meta：系统元数据表
￮key：主键标识
￮value：标记数据库是否初始化，避免重复插入默认管理员
2. Supabase 云端表 user_account
用于账号登录、跨设备同步成员信息，字段映射本地成员数据：
username、password_hash、name、dept、position、duty、join_date、leave_date
八、默认管理员账号
系统首次启动自动创建初始管理员：
•姓名 / 用户名：林可翔
•部门：秘书处，职位：处长
•初始密码：123456
•入职日期：2026-04-01
登录后建议第一时间修改密码，密码采用 PBKDF2 加盐哈希加密存储，无明文留存。
九、API 接口简要说明
成员管理接口
•GET /api/members：获取全部学生会成员
•POST /api/members：批量覆盖更新成员列表，自动同步 Supabase
•PUT /api/member/{mid}：修改单条成员信息
•DELETE /api/member/{mid}：删除成员，同步云端删除账号
消息公告接口
•GET /api/messages：读取全部公告
•POST /api/messages：批量替换公告内容
登录认证接口
•POST /api/auth/login：账号密码登录鉴权
•POST /api/auth/register：新增干事账号
•GET /api/auth/users：获取所有账号档案
•PUT /api/auth/update：修改账号信息 / 重置密码
•DELETE /api/auth/delete：删除账号
•POST /api/auth/init：初始化默认管理员
系统工具接口
•GET /api/auth/status：查看 Supabase 开关状态
•GET /api/diagnose：诊断 Supabase 连接是否正常
十、项目亮点
1.多数据库自适应：零配置 SQLite 本地运行，支持 PostgreSQL 云持久化，Supabase 云端账号同步，一套代码适配多场景
2.轻量化无依赖：仅 Flask+gunicorn 两个第三方包，部署成本极低，无需 Redis、MySQL 等重型服务
3.数据安全：密码 PBKDF2 加盐哈希存储，不保存明文；线程锁保证并发读写数据库不损坏
4.全平台部署：本地电脑、Vercel Serverless、Railway、私有服务器全部兼容
5.PWA 移动端适配：manifest 配置，手机可添加桌面独立打开，适配竖屏展示
6.自动双向同步：本地修改成员数据自动推送至 Supabase 云端，多端数据统一
7.开箱即用：首次运行自动建表、插入默认管理员，无需手动初始化数据库
十一、常见问题 FAQ
1.启动后提示无法访问页面
￮确认端口 5000 未被占用，防火墙放行端口；访问http://127.0.0.1:5000
2.Vercel 部署后重启数据丢失
￮Vercel 无持久化磁盘，建议配置 Supabase 环境变量开启云端同步
3.Supabase 同步失败
￮检查SUPABASE_URL、SUPABASE_SERVICE_KEY环境变量是否正确，网络能否访问 Supabase 接口
4.忘记管理员密码
￮两种方案：①调用/api/auth/init重置默认账号；②直接修改数据库内 passwordHash 字段
十二、贡献指南
1.Fork 本仓库，新建功能分支 feature/xxx
2.本地调试通过后提交 Commit，规范提交注释
3.发起 Pull Request，描述新增功能 / 修复内容
4.代码规范：保持 Flask 接口分层、数据库操作加线程锁，兼容多数据库逻辑
十三、开源协议
MIT License
可自由用于校内教学、校园管理二次开发，商用请保留项目开源声明。
十四、补充说明
系统报错当前不支持该文件类型，请尝试其他文件为前端上传文件校验逻辑提示，仅前端交互弹窗，不影响后端接口与数据库运行。项目完全适配中学学生会轻量化人事管理需求，可根据学校部门、岗位自定义修改前端页面与默认初始化数据。
