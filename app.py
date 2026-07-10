import os, json, hashlib
from flask import Flask, send_from_directory, request, jsonify
import sqlite3
import threading

app = Flask(__name__)

# ===== DATABASE =====
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')
_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _lock:
        conn = get_db()
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
        # 初始化默认成员数据（仅首次）
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
        conn = get_db()
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
        conn = get_db()
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
        conn = get_db()
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
        conn = get_db()
        conn.execute("DELETE FROM members WHERE id=?", (mid,))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})

# ===== API: MESSAGES =====
@app.route('/api/messages', methods=['GET'])
def get_messages():
    with _lock:
        conn = get_db()
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
        conn = get_db()
        conn.execute("DELETE FROM messages")
        for m in msgs:
            conn.execute("INSERT INTO messages (data) VALUES (?)", (json.dumps(m, ensure_ascii=False),))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)