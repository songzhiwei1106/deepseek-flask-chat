from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
import os
import httpx
import sqlite3
import json
from datetime import datetime

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY")
DB_NAME = "chat.db"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-flash"

SYSTEM_PROMPT = "你是一个耐心、清晰、适合大学生学习使用的 AI 助手。回答要简洁、有条理。"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(messages)")
    columns = [row["name"] for row in cursor.fetchall()]

    if "session_id" not in columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN session_id INTEGER")

    cursor.execute("SELECT id FROM sessions ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()

    if row is None:
        now = now_text()
        cursor.execute(
            "INSERT INTO sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
            ("默认会话", now, now)
        )
        default_session_id = cursor.lastrowid
    else:
        default_session_id = row["id"]

    cursor.execute(
        "UPDATE messages SET session_id = ? WHERE session_id IS NULL",
        (default_session_id,)
    )

    conn.commit()
    conn.close()


def create_session(title="新会话"):
    conn = get_conn()
    cursor = conn.cursor()

    now = now_text()

    cursor.execute(
        "INSERT INTO sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now)
    )

    session_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0
    }


def list_sessions():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            s.id,
            s.title,
            s.created_at,
            s.updated_at,
            COUNT(m.id) AS message_count
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        GROUP BY s.id
        ORDER BY s.updated_at DESC, s.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"]
        }
        for row in rows
    ]


def get_or_create_session(session_id=None):
    conn = get_conn()
    cursor = conn.cursor()

    if session_id:
        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()

        if row:
            conn.close()
            return row["id"]

    cursor.execute("SELECT id FROM sessions ORDER BY updated_at DESC, id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return row["id"]

    new_session = create_session()
    return new_session["id"]


def make_title(text):
    text = " ".join(text.split())

    if not text:
        return "新会话"

    if len(text) > 18:
        return text[:18] + "..."

    return text


def update_session_title_if_needed(session_id, user_msg):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            title,
            (SELECT COUNT(*) FROM messages WHERE session_id = ?) AS message_count
        FROM sessions
        WHERE id = ?
    """, (session_id, session_id))

    row = cursor.fetchone()

    if row:
        title = row["title"]
        message_count = row["message_count"]

        if title in ["新会话", "默认会话"] and message_count <= 1:
            new_title = make_title(user_msg)

            cursor.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now_text(), session_id)
            )

    conn.commit()
    conn.close()


def update_session_time(session_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now_text(), session_id)
    )

    conn.commit()
    conn.close()


def save_message(role, content, session_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now_text())
    )

    cursor.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now_text(), session_id)
    )

    conn.commit()
    conn.close()


def get_messages(session_id, limit=20):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit)
    )

    rows = cursor.fetchall()
    conn.close()

    messages = [
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in rows
    ]

    messages.reverse()
    return messages


def get_all_messages(session_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]


def clear_messages(session_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now_text(), session_id)
    )

    conn.commit()
    conn.close()


def delete_session(session_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sessions", methods=["GET"])
def api_list_sessions():
    sessions = list_sessions()

    if not sessions:
        session = create_session()
        sessions = [session]

    return jsonify({
        "sessions": sessions,
        "current_session_id": sessions[0]["id"]
    })


@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "新会话").strip() or "新会话"

    session = create_session(title)

    return jsonify({
        "message": "会话创建成功",
        "session": session
    })


@app.route("/api/sessions/<int:session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    delete_session(session_id)

    sessions = list_sessions()

    if not sessions:
        session = create_session()
        sessions = [session]

    return jsonify({
        "message": "会话已删除",
        "sessions": sessions,
        "current_session_id": sessions[0]["id"]
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    session_id = request.args.get("session_id", type=int)
    session_id = get_or_create_session(session_id)

    return jsonify({
        "session_id": session_id,
        "messages": get_all_messages(session_id)
    })


@app.route("/api/clear", methods=["POST"])
def api_clear():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    session_id = get_or_create_session(session_id)
    clear_messages(session_id)

    return jsonify({
        "message": "当前会话聊天记录已清空",
        "session_id": session_id
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"error": "没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件"}), 500

    data = request.get_json()
    user_msg = data.get("message", "").strip()
    session_id = data.get("session_id")

    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    session_id = get_or_create_session(session_id)

    save_message("user", user_msg, session_id)
    update_session_title_if_needed(session_id, user_msg)

    history_messages = get_messages(session_id, limit=20)

    system_message = {
        "role": "system",
        "content": SYSTEM_PROMPT
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [system_message] + history_messages,
        "stream": False
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.post(DEEPSEEK_URL, headers=headers, json=payload)

        result = response.json()

        if response.status_code != 200:
            return jsonify(result), response.status_code

        ai_reply = result["choices"][0]["message"]["content"]

        save_message("assistant", ai_reply, session_id)

        return jsonify({
            "reply": ai_reply,
            "session_id": session_id,
            "sessions": list_sessions()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if not API_KEY:
        return Response("没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件", mimetype="text/plain")

    data = request.get_json()
    user_msg = data.get("message", "").strip()
    session_id = data.get("session_id")

    if not user_msg:
        return Response("消息不能为空", mimetype="text/plain")

    session_id = get_or_create_session(session_id)

    save_message("user", user_msg, session_id)
    update_session_title_if_needed(session_id, user_msg)

    history_messages = get_messages(session_id, limit=20)

    system_message = {
        "role": "system",
        "content": SYSTEM_PROMPT
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [system_message] + history_messages,
        "stream": True
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    def generate():
        full_reply = ""

        try:
            with httpx.Client(timeout=60, trust_env=False) as client:
                with client.stream("POST", DEEPSEEK_URL, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        yield f"API 请求失败，状态码：{response.status_code}"
                        return

                    for line in response.iter_lines():
                        if not line:
                            continue

                        if line.startswith("data:"):
                            line = line.replace("data:", "").strip()

                        if line == "[DONE]":
                            break

                        try:
                            data = json.loads(line)
                            delta = data["choices"][0]["delta"]
                            content = delta.get("content", "")

                            if content:
                                full_reply += content
                                yield content

                        except Exception:
                            continue

            if full_reply:
                save_message("assistant", full_reply, session_id)

        except Exception as e:
            yield f"程序报错：{str(e)}"

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8"
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)