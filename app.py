import os, json, sqlite3
from flask import Flask, send_from_directory, request, jsonify
import threading

app = Flask(__name__)

# ===== DATABASE =====
# 优先使用 DATABASE_URL 环境变量连接 PostgreSQL 云数据库（数据持久化，部署不丢失）
# 未设置时回退本地 SQLite，保证开发环境正常运行
DATABASE_URL = os.environ.get('DATABASE_URL', '')

_use_postgres = False
_engine = None
_SessionFactory = None

if DATABASE_URL:
    try:
        from sqlalchemy import create_engine, Column, Integer, Text
        from sqlalchemy.orm import declarative_base, sessionmaker
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        _SessionFactory = sessionmaker(bind=_engine)
        _Base = declarative_base()

        class _MemberRecord(_Base):
            __tablename__ = 'members'
            id = Column(Integer, primary_key=True, autoincrement=True)
            data = Column(Text, nullable=False)

        class _MessageRecord(_Base):
            __tablename__ = 'messages'
            id = Column(Integer, primary_key=True, autoincrement=True)
            data = Column(Text, nullable=False)

        class _MetaRecord(_Base):
            __tablename__ = 'meta'
            key = Column(Text, primary_key=True)
            value = Column(Text)

        _Base.metadata.create_all(_engine)
        _use_postgres = True
        print("[DB] 已连接 PostgreSQL 云数据库")
    except Exception as e:
        print(f"[DB] PostgreSQL 连接失败，回退到 SQLite: {e}")

if not _use_postgres:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')
    print(f"[DB] 使用 SQLite: {DB_PATH}")

_lock = threading.Lock()

def _pg_session():
    return _SessionFactory()

def _pg_query_all(session, cls):
    return session.query(cls).order_by(cls.id).all()

# ===== 初始化默认成员数据 =====
def init_db():
    with _lock:
        if _use_postgres:
            session = _pg_session()
            try:
                from app import _MetaRecord as MetaRecord, _MemberRecord as MemberRecord
                row = session.query(MetaRecord).filter_by(key='initialized').first()
                if not row:
                    _insert_default_members_pg(session, MemberRecord, MetaRecord)
            finally:
                session.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute('''CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )''')
            row = conn.execute("SELECT value FROM meta WHERE key='initialized'").fetchone()
            if not row:
                default_members = [
                    {"id":1,"name":"林可翔","dept":"秘书处","position":"部长","duty":"统筹协调各部门工作、会议组织","joinDate":"2026-04-01","leaveDate":"","passwordHash":"d5a5d426cd7786950e59b8a714186ca384da908a40c7b7bfdccfbbb64b668df7"}
                ]
                for m in default_members:
                    conn.execute("INSERT INTO members (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
                conn.execute("INSERT INTO meta (key, value) VALUES ('initialized', '1')")
                conn.commit()
            conn.close()

def _insert_default_members_pg(session, MemberRecord, MetaRecord):
    default_members = [
        {"id":1,"name":"林可翔","dept":"秘书处","position":"部长","duty":"统筹协调各部门工作、会议组织","joinDate":"2026-04-01","leaveDate":"","passwordHash":"d5a5d426cd7786950e59b8a714186ca384da908a40c7b7bfdccfbbb64b668df7"}
    ]
    for m in default_members:
        session.add(MemberRecord(data=json.dumps(m, ensure_ascii=False)))
    session.add(MetaRecord(key='initialized', value='1'))
    session.commit()

init_db()

# ===== STATIC FILE =====
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
        if _use_postgres:
            session = _pg_session()
            try:
                rows = _pg_query_all(session, _MemberRecord)
            finally:
                session.close()
            members = [json.loads(r.data) for r in rows]
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT data FROM members ORDER BY id").fetchall()
            conn.close()
            members = [json.loads(r['data']) for r in rows]
    return jsonify(members)

@app.route('/api/members', methods=['POST'])
def save_members():
    """全量保存成员数据（前端同步用）"""
    members = request.get_json(force=True)
    if not isinstance(members, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        if _use_postgres:
            session = _pg_session()
            try:
                session.query(_MemberRecord).delete()
                for m in members:
                    session.add(_MemberRecord(data=json.dumps(m, ensure_ascii=False)))
                session.commit()
            finally:
                session.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM members")
            for m in members:
                conn.execute("INSERT INTO members (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
            conn.commit()
            conn.close()
    return jsonify({"ok": True})

@app.route('/api/member/<int:mid>', methods=['PUT'])
def update_member(mid):
    """更新单个成员"""
    data = request.get_json(force=True)
    with _lock:
        if _use_postgres:
            session = _pg_session()
            try:
                row = session.query(_MemberRecord).filter_by(id=mid).first()
                if not row:
                    return jsonify({"error": "not found"}), 404
                existing = json.loads(row.data)
                existing.update(data)
                row.data = json.dumps(existing, ensure_ascii=False)
                session.commit()
            finally:
                session.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
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
        if _use_postgres:
            session = _pg_session()
            try:
                session.query(_MemberRecord).filter_by(id=mid).delete()
                session.commit()
            finally:
                session.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM members WHERE id=?", (mid,))
            conn.commit()
            conn.close()
    return jsonify({"ok": True})

# ===== API: MESSAGES =====
@app.route('/api/messages', methods=['GET'])
def get_messages():
    with _lock:
        if _use_postgres:
            session = _pg_session()
            try:
                rows = _pg_query_all(session, _MessageRecord)
            finally:
                session.close()
            msgs = [json.loads(r.data) for r in rows]
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT data FROM messages ORDER BY id").fetchall()
            conn.close()
            msgs = [json.loads(r['data']) for r in rows]
    return jsonify(msgs)

@app.route('/api/messages', methods=['POST'])
def save_messages():
    """全量保存消息"""
    msgs = request.get_json(force=True)
    if not isinstance(msgs, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        if _use_postgres:
            session = _pg_session()
            try:
                session.query(_MessageRecord).delete()
                for m in msgs:
                    session.add(_MessageRecord(data=json.dumps(m, ensure_ascii=False)))
                session.commit()
            finally:
                session.close()
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM messages")
            for m in msgs:
                conn.execute("INSERT INTO messages (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
            conn.commit()
            conn.close()
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)