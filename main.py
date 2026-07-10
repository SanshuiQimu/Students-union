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
@app.route('/api/members', methods=['GET'])
def get_members():
    with _lock:
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
    return jsonify({"ok": True})

@app.route('/api/member/<int:mid>', methods=['DELETE'])
def delete_member(mid):
    with _lock:
        if _use_pg:
            s = _Session()
            try:
                s.query(_Member).filter_by(id=mid).delete()
                s.commit()
            finally:
                s.close()
        else:
            conn = _sqlite_db()
            conn.execute("DELETE FROM members WHERE id=?", (mid,))
            conn.commit()
            conn.close()
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)