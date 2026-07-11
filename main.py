import os, json, hashlib, sqlite3, threading, urllib.parse
from flask import Flask, send_from_directory, request, jsonify

app = Flask(__name__)

_lock = threading.Lock()

# ===== DATABASE =====
# 优先使用 DATABASE_URL 连接 PostgreSQL 云数据库（数据持久化，部署不丢失）
# 未设置时回退本地 SQLite
DATABASE_URL = os.environ.get('DATABASE_URL', '')
_use_pg = False

if DATABASE_URL:
    try:
        from sqlalchemy import create_engine, Column, Integer, Text
        from sqlalchemy.orm import declarative_base, sessionmaker
        # Railway 的 DATABASE_URL 以 postgres:// 开头，SQLAlchemy 需要 postgresql://
        db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        _engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
        _Session = sessionmaker(bind=_engine)
        _Base = declarative_base()

        class _Member(_Base):
            __tablename__ = 'members'
            id = Column(Integer, primary_key=True, autoincrement=True)
            data = Column(Text, nullable=False)

        class _Message(_Base):
            __tablename__ = 'messages'
            id = Column(Integer, primary_key=True, autoincrement=True)
            data = Column(Text, nullable=False)

        class _Meta(_Base):
            __tablename__ = 'meta'
            key = Column(Text, primary_key=True)
            value = Column(Text)

        _Base.metadata.create_all(_engine)
        _use_pg = True
        print("[DB] 已连接 PostgreSQL 云数据库")
    except Exception as e:
        print(f"[DB] PostgreSQL 连接失败，回退 SQLite: {e}")

if not _use_pg:
    # 优先使用持久化卷路径（Railway Volume 挂载点 /data）
    _vol = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '')
    if _vol and os.path.isdir(_vol):
        DB_PATH = os.path.join(_vol, 'data.db')
    elif os.path.isdir('/data'):
        DB_PATH = '/data/data.db'
    elif os.path.isdir('/tmp'):
        # Vercel serverless 环境只有 /tmp 可写
        DB_PATH = '/tmp/data.db'
    else:
        DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')
    print(f"[DB] 使用 SQLite: {DB_PATH}")

def _sqlite_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock:
        if _use_pg:
            s = _Session()
            try:
                if not s.query(_Meta).filter_by(key='initialized').first():
                    defaults = [
                        {"id":1,"name":"林可翔","dept":"秘书处","position":"处长","duty":"统筹协调各部门工作、会议组织","joinDate":"2026-04-01","leaveDate":"","passwordHash":"d5a5d426cd7786950e59b8a714186ca384da908a40c7b7bfdccfbbb64b668df7"}
                    ]
                    for m in defaults:
                        s.add(_Member(data=json.dumps(m, ensure_ascii=False)))
                    s.add(_Meta(key='initialized', value='1'))
                    s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            conn.execute('''CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)''')
            if not conn.execute("SELECT value FROM meta WHERE key='initialized'").fetchone():
                defaults = [
                    {"id":1,"name":"林可翔","dept":"秘书处","position":"处长","duty":"统筹协调各部门工作、会议组织","joinDate":"2026-04-01","leaveDate":"","passwordHash":"d5a5d426cd7786950e59b8a714186ca384da908a40c7b7bfdccfbbb64b668df7"}
                ]
                for m in defaults:
                    conn.execute("INSERT INTO members (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
                conn.execute("INSERT INTO meta (key, value) VALUES ('initialized', '1')")
                conn.commit()
            conn.close()

init_db()

# ===== STATIC =====
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/api/diagnose')
def diagnose():
    """诊断端点：检查 Supabase 连接状态"""
    result = {
        'supabase_configured': _use_supabase,
        'supabase_url': SUPABASE_URL if _use_supabase else '(未配置)',
        'has_key': bool(SUPABASE_KEY),
    }
    if _use_supabase:
        try:
            users = _supabase_get('user_account', 'select=username&limit=1')
            result['supabase_connected'] = True
            result['user_count'] = len(_supabase_get('user_account', 'select=username'))
        except Exception as e:
            result['supabase_connected'] = False
            result['error'] = str(e)
    return jsonify(result)

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), path)

# ===== API: MEMBERS =====
def _sync_members_to_supabase(members):
    """将成员列表批量同步到 Supabase user_account 表"""
    if not _use_supabase:
        return {'synced': False, 'reason': 'Supabase 未配置'}
    try:
        # 获取 Supabase 中现有用户名
        existing = _supabase_get('user_account', 'select=username')
        existing_names = {u.get('username') for u in existing} if existing else set()

        to_insert = []
        to_update = []
        for m in members:
            name = m.get('name', '')
            if not name:
                continue
            pwd_hash = m.get('passwordHash', '')
            if not pwd_hash:
                pwd_hash = hashlib.sha256('123456'.encode('utf-8')).hexdigest()
            user_data = {
                'username': name,
                'password_hash': pwd_hash,
                'name': name,
                'dept': m.get('dept', ''),
                'position': m.get('position', ''),
                'duty': m.get('duty', ''),
                'join_date': m.get('joinDate', ''),
                'leave_date': m.get('leaveDate', '')
            }
            if name in existing_names:
                to_update.append((name, user_data))
            else:
                to_insert.append(user_data)

        # 批量插入新用户
        if to_insert:
            _supabase_post('user_account', to_insert)

        # 逐条更新已有用户（Supabase PATCH 不支持批量）
        for name, user_data in to_update:
            _supabase_patch('user_account', f"username=eq.{name}", user_data)

        return {'synced': True, 'inserted': len(to_insert), 'updated': len(to_update)}
    except Exception as e:
        print(f"[Supabase] 同步失败: {e}")
        return {'synced': False, 'reason': str(e)}

def _load_members_from_supabase():
    """从 Supabase 加载成员列表"""
    if not _use_supabase:
        return None
    users = _supabase_get('user_account', 'select=*')
    if not users:
        return []
    result = []
    for u in users:
        result.append({
            'id': len(result) + 1,
            'name': u.get('name', ''),
            'dept': u.get('dept', ''),
            'position': u.get('position', ''),
            'duty': u.get('duty', ''),
            'joinDate': u.get('join_date', ''),
            'leaveDate': u.get('leave_date', ''),
            'passwordHash': u.get('password_hash', '')
        })
    return result

@app.route('/api/members', methods=['GET'])
def get_members():
    with _lock:
        # 优先从 Supabase 加载
        if _use_supabase:
            data = _load_members_from_supabase()
            if data is not None:
                return jsonify(data)
        # 回退 SQLite
        if _use_pg:
            s = _Session()
            try:
                rows = s.query(_Member).order_by(_Member.id).all()
            finally:
                s.close()
            return jsonify([json.loads(r.data) for r in rows])
        else:
            conn = _sqlite_db()
            rows = conn.execute("SELECT data FROM members ORDER BY id").fetchall()
            conn.close()
            return jsonify([json.loads(r['data']) for r in rows])

@app.route('/api/members', methods=['POST'])
def save_members():
    members = request.get_json(force=True)
    if not isinstance(members, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        # 同步到 Supabase
        sync_result = _sync_members_to_supabase(members)
        # 同时存 SQLite（作为本地缓存）
        if _use_pg:
            s = _Session()
            try:
                s.query(_Member).delete()
                for m in members:
                    s.add(_Member(data=json.dumps(m, ensure_ascii=False)))
                s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            conn.execute("DELETE FROM members")
            for m in members:
                conn.execute("INSERT INTO members (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
            conn.commit()
            conn.close()
    return jsonify({"ok": True, "sync": sync_result})

@app.route('/api/member/<int:mid>', methods=['PUT'])
def update_member(mid):
    data = request.get_json(force=True)
    with _lock:
        # 先从 SQLite 获取当前成员数据
        if _use_pg:
            s = _Session()
            try:
                row = s.query(_Member).filter_by(id=mid).first()
                if not row:
                    return jsonify({"error": "not found"}), 404
                existing = json.loads(row.data)
                existing.update(data)
                row.data = json.dumps(existing, ensure_ascii=False)
                s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            row = conn.execute("SELECT data FROM members WHERE id=?", (mid,)).fetchone()
            if not row:
                conn.close()
                return jsonify({"error": "not found"}), 404
            existing = json.loads(row['data'])
            existing.update(data)
            conn.execute("UPDATE members SET data=? WHERE id=?", (json.dumps(existing, ensure_ascii=False), mid))
            conn.commit()
            conn.close()
        # 同步到 Supabase
        if _use_supabase and existing.get('name'):
            supa_data = {}
            for k in ['dept', 'position', 'duty', 'name']:
                if k in data:
                    supa_data[k] = data[k]
            if 'joinDate' in data:
                supa_data['join_date'] = data['joinDate']
            if 'leaveDate' in data:
                supa_data['leave_date'] = data['leaveDate']
            if 'passwordHash' in data:
                supa_data['password_hash'] = data['passwordHash']
            if supa_data:
                old_name = existing.get('name', '')
                _supabase_patch('user_account', f"username=eq.{old_name}", supa_data)
    return jsonify({"ok": True})

@app.route('/api/member/<int:mid>', methods=['DELETE'])
def delete_member(mid):
    with _lock:
        # 先获取成员名字（用于删除 Supabase 记录）
        member_name = None
        if _use_pg:
            s = _Session()
            try:
                row = s.query(_Member).filter_by(id=mid).first()
                if row:
                    member_name = json.loads(row.data).get('name')
                s.query(_Member).filter_by(id=mid).delete()
                s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            row = conn.execute("SELECT data FROM members WHERE id=?", (mid,)).fetchone()
            if row:
                member_name = json.loads(row['data']).get('name')
            conn.execute("DELETE FROM members WHERE id=?", (mid,))
            conn.commit()
            conn.close()
        # 同步删除 Supabase 记录
        if _use_supabase and member_name:
            _supabase_delete('user_account', f"username=eq.{member_name}")
    return jsonify({"ok": True})

# ===== API: MESSAGES =====
@app.route('/api/messages', methods=['GET'])
def get_messages():
    with _lock:
        if _use_pg:
            s = _Session()
            try:
                rows = s.query(_Message).order_by(_Message.id).all()
            finally:
                s.close()
            return jsonify([json.loads(r.data) for r in rows])
        else:
            conn = _sqlite_db()
            rows = conn.execute("SELECT data FROM messages ORDER BY id").fetchall()
            conn.close()
            return jsonify([json.loads(r['data']) for r in rows])

@app.route('/api/messages', methods=['POST'])
def save_messages():
    msgs = request.get_json(force=True)
    if not isinstance(msgs, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        if _use_pg:
            s = _Session()
            try:
                s.query(_Message).delete()
                for m in msgs:
                    s.add(_Message(data=json.dumps(m, ensure_ascii=False)))
                s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            conn.execute("DELETE FROM messages")
            for m in msgs:
                conn.execute("INSERT INTO messages (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
            conn.commit()
            conn.close()
    return jsonify({"ok": True})

# ===== SUPABASE AUTH =====
import hashlib, secrets, urllib.request, urllib.error

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
# 兼容新版和旧版环境变量名
SUPABASE_KEY = os.environ.get('SUPABASE_SECRET_KEY', '') or os.environ.get('SUPABASE_SERVICE_KEY', '')
_use_supabase = bool(SUPABASE_URL and SUPABASE_KEY)

if _use_supabase:
    print(f"[Auth] Supabase 认证已启用: {SUPABASE_URL}")

# PBKDF2 密码哈希（Python 内置，无需外部依赖）
def _hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"pbkdf2${salt}${dk.hex()}"

def _verify_password(password, stored):
    try:
        if stored.startswith('pbkdf2$'):
            parts = stored.split('$')
            salt = parts[1]
            expected = parts[2]
            dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
            return secrets.compare_digest(dk.hex(), expected)
        # 兼容前端带盐 SHA-256 哈希（HASH_SALT = 'SU_HG_2025_LGKJ'）
        salted = 'SU_HG_2025_LGKJ' + password
        return secrets.compare_digest(hashlib.sha256(salted.encode('utf-8')).hexdigest(), stored)
    except Exception:
        return False

def _supabase_headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }

def _supabase_request(method, path, body=None):
    # 对路径中的中文进行 URL 编码
    encoded_path = urllib.parse.quote(path, safe='=/&?')
    url = f"{SUPABASE_URL}/rest/v1/{encoded_path}"
    headers = _supabase_headers()
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8') if e.fp else ''
        print(f"[Supabase] {method} {path} 失败: {e.code} {raw}")
        return e.code, None
    except Exception as e:
        print(f"[Supabase] {method} {path} 异常: {e}")
        return 0, None

def _supabase_get(table, filter_str=''):
    path = table + (f"?{filter_str}" if filter_str else "")
    status, data = _supabase_request('GET', path)
    return data if (status == 200 and isinstance(data, list)) else []

def _supabase_post(table, data):
    status, result = _supabase_request('POST', table, data)
    return result if status in (200, 201) else None

def _supabase_patch(table, filter_str, data):
    status, result = _supabase_request('PATCH', f"{table}?{filter_str}", data)
    return result if status == 200 else None

def _supabase_delete(table, filter_str):
    status, _ = _supabase_request('DELETE', f"{table}?{filter_str}")
    return status in (200, 204)

@app.route('/api/auth/status')
def auth_status():
    return jsonify({'supabase': _use_supabase})

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    if not _use_supabase:
        return jsonify({'error': 'Supabase 未配置'}), 503
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': '请输入用户名和密码'}), 400

    users = _supabase_get('user_account', f"username=eq.{username}&select=*")
    if not users:
        return jsonify({'error': '用户名或密码错误'}), 401

    user = users[0]
    if not _verify_password(password, user.get('password_hash', '')):
        return jsonify({'error': '用户名或密码错误'}), 401

    # 返回用户数据（不含密码哈希）
    safe = {k: v for k, v in user.items() if k != 'password_hash'}
    return jsonify(safe)

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    if not _use_supabase:
        return jsonify({'error': 'Supabase 未配置'}), 503
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '123456')
    name = data.get('name', '')
    dept = data.get('dept', '')
    position = data.get('position', '')
    duty = data.get('duty', '')
    join_date = data.get('joinDate', data.get('join_date', ''))

    if not username or not name:
        return jsonify({'error': '用户名和姓名不能为空'}), 400

    # 检查是否已存在
    existing = _supabase_get('user_account', f"username=eq.{username}&select=id")
    if existing:
        return jsonify({'error': '用户名已存在'}), 409

    new_user = {
        'username': username,
        'password_hash': _hash_password(password),
        'name': name,
        'dept': dept,
        'position': position,
        'duty': duty,
        'join_date': join_date,
        'leave_date': ''
    }
    result = _supabase_post('user_account', new_user)
    if result:
        return jsonify({'ok': True})
    return jsonify({'error': '注册失败'}), 500

@app.route('/api/auth/users')
def auth_users():
    if not _use_supabase:
        return jsonify([])
    users = _supabase_get('user_account', 'select=id,username,name,dept,position,duty,join_date,leave_date&order=created_at.asc')
    result = []
    for u in users:
        result.append({
            'id': u.get('id'),
            'username': u.get('username'),
            'name': u.get('name'),
            'dept': u.get('dept', ''),
            'position': u.get('position', ''),
            'duty': u.get('duty', ''),
            'joinDate': u.get('join_date', ''),
            'leaveDate': u.get('leave_date', '')
        })
    return jsonify(result)

@app.route('/api/auth/update', methods=['PUT'])
def auth_update():
    if not _use_supabase:
        return jsonify({'error': 'Supabase 未配置'}), 503
    data = request.get_json(force=True)
    username = data.get('username', '')
    updates = {}
    for k in ['name', 'dept', 'position', 'duty']:
        if k in data:
            updates[k] = data[k]
    if 'joinDate' in data:
        updates['join_date'] = data['joinDate']
    if 'leaveDate' in data:
        updates['leave_date'] = data['leaveDate']
    if 'password' in data and data['password']:
        updates['password_hash'] = _hash_password(data['password'])

    _supabase_patch('user_account', f"username=eq.{username}", updates)
    return jsonify({'ok': True})

@app.route('/api/auth/delete', methods=['DELETE'])
def auth_delete():
    if not _use_supabase:
        return jsonify({'error': 'Supabase 未配置'}), 503
    data = request.get_json(force=True)
    username = data.get('username', '')
    _supabase_delete('user_account', f"username=eq.{username}")
    return jsonify({'ok': True})

@app.route('/api/auth/init', methods=['POST'])
def auth_init():
    if not _use_supabase:
        return jsonify({'error': 'Supabase 未配置'}), 503
    # 检查是否已有数据
    existing = _supabase_get('user_account', 'select=id&limit=1')
    if existing:
        return jsonify({'ok': True, 'message': '已有用户数据，跳过初始化'})
    # 插入默认管理员
    default = {
        'username': '林可翔',
        'password_hash': _hash_password('123456'),
        'name': '林可翔',
        'dept': '秘书处',
        'position': '处长',
        'duty': '统筹协调各部门工作、会议组织',
        'join_date': '2026-04-01',
        'leave_date': ''
    }
    _supabase_post('user_account', default)
    return jsonify({'ok': True, 'message': '默认管理员已创建（用户名: 林可翔，密码: 123456）'})

# ===== API: VERSION MANAGEMENT =====
def _get_versions():
    """从 meta 表读取版本列表"""
    if _use_pg:
        s = _Session()
        try:
            row = s.query(_Meta).filter_by(key='app_versions').first()
            if row and row.value:
                return json.loads(row.value)
        finally:
            s.close()
    else:
        conn = _sqlite_db()
        row = conn.execute("SELECT value FROM meta WHERE key='app_versions'").fetchone()
        conn.close()
        if row and row['value']:
            return json.loads(row['value'])
    return []

def _save_versions(versions):
    """保存版本列表到 meta 表"""
    data = json.dumps(versions, ensure_ascii=False)
    if _use_pg:
        s = _Session()
        try:
            row = s.query(_Meta).filter_by(key='app_versions').first()
            if row:
                row.value = data
            else:
                s.add(_Meta(key='app_versions', value=data))
            s.commit()
        finally:
            s.close()
    else:
        conn = _sqlite_db()
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('app_versions', ?)", (data,))
        conn.commit()
        conn.close()

def _default_versions():
    """全部历史版本数据"""
    return [
        {"version":"3.0.310.2","versionCode":3102,"date":"2026-07-11","tag":"正式版内测","changelog":["检测更新卡片移至版本列表页置顶","版本类型标签(Beta/正式版内测/正式版公开/已撤包)","修复应用图标模糊","WebView禁缓存，每次加载最新页面"],"downloadUrl":"/api/download/apk"},
        {"version":"3.0.310.0","versionCode":3100,"date":"2026-07-11","tag":"正式版公开","changelog":["数据存储由阿里云与Supabase提供支持","防火墙与CDN加速由Cloudflare提供支持","代码存放由GitHub提供支持"],"downloadUrl":"/api/download/apk"},
        {"version":"3.0.309.0","versionCode":3090,"date":"2026-07-11","tag":"正式版公开","changelog":["返回键逻辑优化","同设备免登录"],"downloadUrl":""},
        {"version":"3.0.307.1","versionCode":3071,"date":"2026-07-11","tag":"Beta","changelog":["更新系统更新模块数据表，新增版本更新日志独立存储表","系统更新设置项归类至设置页面独立分组","版本列表页面全新重构，展示历史迭代记录","优化深色模式文字对比度"],"downloadUrl":""},
        {"version":"3.0.306.1","versionCode":3061,"date":"2026-07-11","tag":"Beta","changelog":["更新系统更新模块数据表，新增版本更新日志独立存储表","系统更新设置项归类至设置页面独立分组","版本列表页面全新重构，展示历史迭代记录","优化深色模式文字对比度"],"downloadUrl":""},
        {"version":"3.0.306.0","versionCode":3060,"date":"2026-07-10","tag":"正式版公开","changelog":["编译Android安装包StudentsUnion.apk，规范安装包版本命名规则","实现前端消息推送逻辑，前端3秒轮询、后端10秒广播推送站内通知","修复Android WebView专属样式失效问题，二级页面顶部遮罩视觉bug全部修复","统一页面顶部渐变遮罩参数，调整遮罩高度、羽化透明度，优化滚动渐变动画效果"],"downloadUrl":""},
        {"version":"3.0.304.0","versionCode":3040,"date":"2026-07-10","tag":"正式版公开","changelog":["彻底修复移动端深浅色跟随系统切换失效bug，页面自动跟随手机系统明暗模式","移动端全部页面内容下移200px，完美避开手机状态栏遮挡，适配各类机型屏幕"],"downloadUrl":""},
        {"version":"3.0.208.0","versionCode":2080,"date":"2026-07-09","tag":"正式版公开","changelog":["重构密码校验流程，SHA-256哈希校验逻辑迁移后端API执行，前端不参与加密运算","群发通知功能迁移至设置页面独立选项，拆分全站通知、部门定向通知两类推送","新增定向部门通知发布功能，管理员可单独给指定部门全员推送站内公告","添加PWA manifest配置，网页端支持安装至手机桌面，具备离线基础访问能力"],"downloadUrl":""},
        {"version":"3.0.204.0","versionCode":2040,"date":"2026-07-09","tag":"正式版公开","changelog":["基本实现安卓端功能，可以推进","下调页面顶部遮罩模糊度，多层渐变分层延伸，滚动动态调整透明度","移动端页面下移参数统一规范，遮罩高度80px/120px双模式适配不同页面","统一box-shadow填充规则，空页面原色填充，消除空白区域视觉断层"],"downloadUrl":""},
        {"version":"3.0.114.0","versionCode":1140,"date":"2026-07-09","tag":"正式版公开","changelog":["修复本地缓存与Supabase批量双向同步报错问题，批量导入导出不再丢失档案数据","优化Supabase数据库连接逻辑，适配新版service_key密钥校验规则","修复成员管理API跨端同步异常，网页、App、桌面端人员数据实时互通","修复Vercel Serverless服务崩溃问题，兼容SQLite本地缓存与线上PostgreSQL数据库"],"downloadUrl":""},
        {"version":"3.0.110.0","versionCode":1100,"date":"2026-07-09","tag":"已撤包","changelog":["新增群发通知功能","新增部门消息功能","优化系统稳定性"],"downloadUrl":""},
        {"version":"3.0.101.0","versionCode":1010,"date":"2026-07-08","tag":"正式版公开","changelog":["新增会长专属职位权限配置，职位表联动PostgreSQL数据库权限字段","完善Docker容器化部署配置文件，统一Railway、Vercel两套部署环境变量","修复Dock导航点击状态残留bug，切换页面重置导航激活标识","优化移动端本地存储Volume持久化路径，重启App缓存数据不丢失"],"downloadUrl":""},
        {"version":"3.0.2.0","versionCode":200,"date":"2026-07-07","tag":"正式版公开","changelog":["前端sha256函数加盐值，后端验证同步加盐，PBKDF2和带盐SHA-256两种格式都能正确验证","构建Android端APP并初次上线","接入Supabase完整后端账号认证体系，统一三端登录、鉴权校验规则","全局新增底部统一版权信息","优化Dock底部导航栏玻璃磨砂动画","移除项目冗余python依赖库，精简requirements打包配置"],"downloadUrl":""},
        {"version":"2.0.219.0","versionCode":2190,"date":"2026-07-06","tag":"Beta","changelog":["尝试用C++重构","大部分语言已调整为Python","修复系统稳定性"],"downloadUrl":""},
        {"version":"2.0.214.0","versionCode":2140,"date":"2026-07-05","tag":"正式版公开","changelog":["多种编译语言逐渐采用Python编译","优化页面初始隐藏加载CSS动画，页面打开过渡更柔和"],"downloadUrl":""},
        {"version":"2.0.208.0","versionCode":2081,"date":"2026-07-03","tag":"正式版公开","changelog":["完善数据库兼容逻辑，无DATABASE_URL环境变量时自动切换本地SQLite缓存","全局替换SQLAlchemy数据库交互写法，优化PostgreSQL云库查询效率","Tongle页面全屏玻璃磨砂效果重构，新增多层渐变折射动画，滚动实时渲染","底部导航图标默认透明，点击切换高亮渐变，统一全页面动效节奏"],"downloadUrl":""},
        {"version":"2.0.201.0","versionCode":2010,"date":"2026-07-02","tag":"Beta","changelog":["修复Railway部署502服务异常问题，完善bash一键部署启动脚本","删除运行冗余缓存文件、旧版依赖配置，重置requirements标准依赖清单","回滚部分底层基础代码，解决新版本构建失败问题","恢复项目Profile配置、gunicorn启动服务参数，适配Vercel后台运行规则","修复通知系统bug"],"downloadUrl":""},
        {"version":"2.0.200.0","versionCode":2000,"date":"2026-07-02","tag":"已撤包","changelog":["新增消息通知功能","新增挂牌补办功能","优化系统稳定性"],"downloadUrl":""},
        {"version":"2.0.105.0","versionCode":1050,"date":"2026-07-01","tag":"正式版公开","changelog":["修复SHA256加密函数漏洞，H数组每次调用自动重置，避免加密结果错乱","SHA256哈希方法迁移全局公共工具库，修复修改密码、角色鉴权加密异常","新增登录页修改密码功能，首次登录默认密码弹窗强制提醒修改","新增忘记密码重置数据入口，独立密码找回页面","支持关闭液态玻璃效果选项，新增高斯模糊毛玻璃质感组件"],"downloadUrl":""},
        {"version":"2.0.104.0","versionCode":1040,"date":"2026-06-30","tag":"正式版公开","changelog":["区分超级管理员/部门部长/普通干事三级账号权限，数据访问自动隔离","录入人员时职位、部门双向联动校验，管理层职位绑定对应分管部门","新增operation_logs日志数据表，记录登录、修改、导入、删除全操作行为","支持管理员冻结违规账号，冻结后全端禁止登录，解冻后方可正常使用"],"downloadUrl":""},
        {"version":"2.0.7.0","versionCode":2070,"date":"2026-06-29","tag":"正式版公开","changelog":["提供标准导入模板，导入时自动校验部门、职位字段，冲突条目标红提示","支持批量标记人员离职、批量调整人员部门与职位，一键导出筛选后档案","成员、部门、通知表建立复合索引，大批量数据筛选速度大幅提升","后台新增手动一键备份、每日凌晨自动全量备份，保留近30天备份快照"],"downloadUrl":""},
        {"version":"2.0.6.0","versionCode":2060,"date":"2026-06-28","tag":"Beta","changelog":["人员新增表单实时同步最新部门、职位列表，停用选项自动隐藏","删除部门、职位仅做软标记，历史人员档案完整保留，不会级联清空数据"],"downloadUrl":""},
        {"version":"2.0.2.0","versionCode":2020,"date":"2026-06-27","tag":"Beta","changelog":["满血Liquid glass设计，优化视效和交互体验","新增导入Excel导出数据双功能按钮，采用区分式配色，按钮增加hover动效","支持Excel表格批量导入学生会成员档案，一键导出全系统人事数据存档","支持批量修改部门简介，一键筛选所有已停用部门","新建positions数据表，存储职位名称、权限等级、归属层级"],"downloadUrl":""},
        {"version":"1.0.103","versionCode":1030,"date":"2026-06-26","tag":"正式版公开","changelog":["添加修改密码功能，登录时默认密码弹窗提示修改","修复crypto.subtle兼容性+SHA256纯JS实现+app.py直接读取文件","优化系统稳定性"],"downloadUrl":""},
        {"version":"1.0.100.0","versionCode":1000,"date":"2026-06-25","tag":"Beta","changelog":["Liquid glass风格首次登场","修复登录函数缩进错误导致的运行报错","首次引入图片模块，图像服务由蜜蜂图床提供支持","实时统计各部门在岗总人数，卡片点击可快速跳转对应部门成员列表","新增部门简介展示栏","添加requirements.txt和Procfile修复Railway部署"],"downloadUrl":""},
        {"version":"1.0.9.0","versionCode":1090,"date":"2026-06-24","tag":"正式版公开","changelog":["密码SHA-256哈希加密存储，防止明文泄露","优化系统稳定性"],"downloadUrl":""},
        {"version":"1.0.4.0","versionCode":1040,"date":"2026-06-23","tag":"正式版公开","changelog":["全线启用深色夜间模式，优化个人信息卡片圆角、金色高亮标识，头像文字模块分层阴影重做，解决低亮度屏幕文字发灰问题","统一底部导航栏选中态金色高亮规范","管理员身份标签自动高亮区分，个人信息页自动填充当前登录账号部门","修复部分机型卡片内容挤压错位bug"],"downloadUrl":""},
        {"version":"1.0.1.0","versionCode":1010,"date":"2026-06-23","tag":"正式版公开","changelog":["系统上线，由Railway提供部署服务，由Github提供代码托管","UI视觉：整体风格简约清新","系统设计：大部分以静态资源为主设计"],"downloadUrl":""},
    ]

@app.route('/api/version/latest')
def version_latest():
    """获取最新版本信息"""
    versions = _get_versions()
    if not versions:
        versions = _default_versions()
        _save_versions(versions)
    return jsonify(versions[0])

@app.route('/api/version/list')
def version_list():
    """获取所有版本列表"""
    versions = _get_versions()
    if not versions:
        versions = _default_versions()
        _save_versions(versions)
    return jsonify(versions)

@app.route('/api/version/<int:vc>')
def version_detail(vc):
    """获取指定版本的详细更新日志"""
    versions = _get_versions()
    for v in versions:
        if v.get('versionCode') == vc:
            return jsonify(v)
    return jsonify({'error': '版本不存在'}), 404

@app.route('/api/version/upload', methods=['POST'])
def version_upload():
    """上传新版本信息（需要管理员密码）"""
    auth = request.headers.get('X-Auth', '')
    # 简单密码验证
    if auth != 'sqgm-admin-2026':
        return jsonify({'error': '无权限'}), 403

    data = request.get_json()
    if not data or 'version' not in data or 'versionCode' not in data:
        return jsonify({'error': '缺少必要字段'}), 400

    versions = _get_versions()
    # 移除同版本号的旧记录
    versions = [v for v in versions if v.get('versionCode') != data['versionCode']]
    # 新版本插入到最前面
    new_ver = {
        'version': data['version'],
        'versionCode': data['versionCode'],
        'date': data.get('date', ''),
        'summary': data.get('summary', ''),
        'changelog': data.get('changelog', []),
        'downloadUrl': '/api/download/apk'
    }
    versions.insert(0, new_ver)
    _save_versions(versions)
    return jsonify({'ok': True, 'message': '版本已添加'})

@app.route('/api/download/apk')
def download_apk():
    """下载最新版 APK"""
    base = os.path.dirname(os.path.abspath(__file__))
    apk_path = os.path.join(base, 'downloads', 'StudentsUnion.apk')
    if os.path.isfile(apk_path):
        return send_from_directory(os.path.join(base, 'downloads'), 'StudentsUnion.apk', as_attachment=True)
    return jsonify({'error': 'APK 文件不存在'}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)