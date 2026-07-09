import os, json
from flask import Flask, send_from_directory, request, jsonify
from sqlalchemy import create_engine, Column, Integer, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import threading

app = Flask(__name__)

# ===== DATABASE =====
# 优先使用 DATABASE_URL 环境变量（Heroku / Render 等平台自动注入 PostgreSQL 连接串）
# 未设置时回退到本地 SQLite 文件，保证开发环境也能正常运行
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL:
    # 部署环境：PostgreSQL（SQLAlchemy 会自动识别 postgres:// 或 postgresql:// 前缀）
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
else:
    # 本地开发：SQLite
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')
    engine = create_engine(f'sqlite:///{DB_PATH}')

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class MemberRecord(Base):
    __tablename__ = 'members'
    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Text, nullable=False)

class MessageRecord(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Text, nullable=False)

class MetaRecord(Base):
    __tablename__ = 'meta'
    key = Column(Text, primary_key=True)
    value = Column(Text)

Base.metadata.create_all(engine)

_lock = threading.Lock()

def get_session():
    return SessionLocal()

# ===== 初始化默认成员数据 =====
def init_db():
    with _lock:
        session = get_session()
        try:
            row = session.query(MetaRecord).filter_by(key='initialized').first()
            if not row:
                default_members = [
                    {"id":1,"name":"林可翔","dept":"秘书处","position":"部长","duty":"统筹协调各部门工作、会议组织","joinDate":"2026-04-01","leaveDate":"","passwordHash":"d5a5d426cd7786950e59b8a714186ca384da908a40c7b7bfdccfbbb64b668df7"}
                ]
                for m in default_members:
                    session.add(MemberRecord(data=json.dumps(m, ensure_ascii=False)))
                session.add(MetaRecord(key='initialized', value='1'))
                session.commit()
        finally:
            session.close()

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
        session = get_session()
        try:
            rows = session.query(MemberRecord).order_by(MemberRecord.id).all()
        finally:
            session.close()
    members = [json.loads(r.data) for r in rows]
    return jsonify(members)

@app.route('/api/members', methods=['POST'])
def save_members():
    """全量保存成员数据（前端同步用）"""
    members = request.get_json(force=True)
    if not isinstance(members, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        session = get_session()
        try:
            session.query(MemberRecord).delete()
            for m in members:
                session.add(MemberRecord(data=json.dumps(m, ensure_ascii=False)))
            session.commit()
        finally:
            session.close()
    return jsonify({"ok": True})

@app.route('/api/member/<int:mid>', methods=['PUT'])
def update_member(mid):
    """更新单个成员"""
    data = request.get_json(force=True)
    with _lock:
        session = get_session()
        try:
            row = session.query(MemberRecord).filter_by(id=mid).first()
            if not row:
                return jsonify({"error": "not found"}), 404
            existing = json.loads(row.data)
            existing.update(data)
            row.data = json.dumps(existing, ensure_ascii=False)
            session.commit()
        finally:
            session.close()
    return jsonify({"ok": True})

@app.route('/api/member/<int:mid>', methods=['DELETE'])
def delete_member(mid):
    with _lock:
        session = get_session()
        try:
            session.query(MemberRecord).filter_by(id=mid).delete()
            session.commit()
        finally:
            session.close()
    return jsonify({"ok": True})

# ===== API: MESSAGES =====
@app.route('/api/messages', methods=['GET'])
def get_messages():
    with _lock:
        session = get_session()
        try:
            rows = session.query(MessageRecord).order_by(MessageRecord.id).all()
        finally:
            session.close()
    msgs = [json.loads(r.data) for r in rows]
    return jsonify(msgs)

@app.route('/api/messages', methods=['POST'])
def save_messages():
    """全量保存消息"""
    msgs = request.get_json(force=True)
    if not isinstance(msgs, list):
        return jsonify({"error": "expected array"}), 400
    with _lock:
        session = get_session()
        try:
            session.query(MessageRecord).delete()
            for m in msgs:
                session.add(MessageRecord(data=json.dumps(m, ensure_ascii=False)))
            session.commit()
        finally:
            session.close()
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)