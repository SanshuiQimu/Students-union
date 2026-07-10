import os, json, hashlib, sqlite3, threading
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

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), path)

# ===== API: MEMBERS =====
def _sync_members_to_supabase(members):
    """将成员列表同步到 Supabase user_account 表"""
    if not _use_supabase:
        return
    # 获取 Supabase 中现有用户
    existing = _supabase_get('user_account', 'select=username')
    existing_names = {u.get('username') for u in existing} if existing else set()
    # upsert 每个成员
    for m in members:
        name = m.get('name', '')
        if not name:
            continue
        pwd_hash = m.get('passwordHash', '')
        if not pwd_hash:
            # 默认密码 123456 的 SHA-256
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
            _supabase_patch('user_account', f"username=eq.{name}", user_data)
        else:
            _supabase_post('user_account', user_data)

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
        _sync_members_to_supabase(members)
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
    return jsonify({"ok": True})

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
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
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
        # 兼容旧 SHA-256 哈希
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored
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
    url = f"{SUPABASE_URL}/rest/v1/{path}"
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)