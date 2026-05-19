from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import json
from dotenv import load_dotenv
import os
import httpx
import sqlite3
from datetime import datetime

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY")
DB_NAME = "chat.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_message(role, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
        (role, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

    conn.commit()
    conn.close()


def get_messages(limit=20):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )

    rows = cursor.fetchall()
    conn.close()

    messages = [
        {"role": row[0], "content": row[1]}
        for row in rows
    ]

    messages.reverse()
    return messages


def get_all_messages():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT role, content, created_at FROM messages ORDER BY id ASC"
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "role": row[0],
            "content": row[1],
            "created_at": row[2]
        }
        for row in rows
    ]


def clear_messages():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM messages")

    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/history", methods=["GET"])
def history():
    messages = get_all_messages()
    return jsonify({"messages": messages})


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"reply": "没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件"}), 500

    data_from_frontend = request.get_json()
    user_msg = data_from_frontend.get("message", "").strip()

    if not user_msg:
        return jsonify({"reply": "消息不能为空"}), 400

    save_message("user", user_msg)

    history_messages = get_messages(limit=20)

    system_message = {
        "role": "system",
        "content": "你是一个耐心、清晰、适合大学生学习使用的 AI 助手。回答要简洁、有条理。"
    }

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [system_message] + history_messages,
        "stream": False
    }

    url = "https://api.deepseek.com/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            response = client.post(url, headers=headers, json=payload)

        result = response.json()

        if response.status_code != 200:
            return jsonify({
                "reply": "API 请求失败",
                "error": result
            }), response.status_code

        ai_reply = result["choices"][0]["message"]["content"]

        save_message("assistant", ai_reply)

        return jsonify({"reply": ai_reply})

    except Exception as e:
        return jsonify({"reply": f"程序报错：{str(e)}"}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if not API_KEY:
        return Response("没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件", mimetype="text/plain")

    data_from_frontend = request.get_json()
    user_msg = data_from_frontend.get("message", "").strip()

    if not user_msg:
        return Response("消息不能为空", mimetype="text/plain")

    save_message("user", user_msg)

    history_messages = get_messages(limit=20)

    system_message = {
        "role": "system",
        "content": "你是一个耐心、清晰、适合大学生学习使用的 AI 助手。回答要简洁、有条理。"
    }

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [system_message] + history_messages,
        "stream": True
    }

    url = "https://api.deepseek.com/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    def generate():
        full_reply = ""

        try:
            with httpx.Client(timeout=60, trust_env=False) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        yield "API 请求失败"
                        return

                    for line in response.iter_lines():
                        if not line:
                            continue

                        if line.startswith("data: "):
                            line = line.replace("data: ", "")

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
                save_message("assistant", full_reply)

        except Exception as e:
            yield f"程序报错：{str(e)}"

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8"
    )
@app.route("/api/clear", methods=["POST"])
def clear():
    clear_messages()
    return jsonify({"message": "聊天记录已清空"})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)