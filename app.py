from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import os
import httpx
import sqlite3
import json
import re
from datetime import datetime

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY")
DB_NAME = "chat.db"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-flash"

SYSTEM_PROMPT = "你是一个耐心、清晰、适合大学生学习使用的 AI 助手。回答要简洁、有条理。"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"txt", "md", "pdf"}

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_ext(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def read_uploaded_file(file_path, ext):
    if ext == "pdf":
        try:
            reader = PdfReader(file_path)
            texts = []

            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""

                if page_text.strip():
                    texts.append(f"第 {i + 1} 页：\n{page_text.strip()}")

            content = "\n\n".join(texts)

            if not content.strip():
                return "该 PDF 未能提取到有效文本，可能是扫描版 PDF 或图片型 PDF。"

            return content

        except Exception as e:
            return f"PDF 解析失败：{str(e)}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="gbk", errors="ignore") as f:
            return f.read()


def split_text(text, chunk_size=900, overlap=120):
    text = (text or "").strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk.strip())

        start = end - overlap

        if start < 0:
            start = 0

        if start >= len(text):
            break

    return chunks


def tokenize_text(text):
    text = (text or "").lower()

    stop_words = {
        "的", "了", "是", "在", "和", "与", "及", "或", "我", "你", "他", "她", "它",
        "我们", "你们", "他们", "什么", "怎么", "如何", "根据", "上传", "文档",
        "请问", "一下", "这个", "那个", "一个", "可以", "进行", "pdf", "txt", "md",
        "总结", "概括", "主要", "内容", "讲了", "什么"
    }

    tokens = []

    english_words = re.findall(r"[a-zA-Z0-9_]+", text)
    tokens.extend([w for w in english_words if len(w) >= 2 and w not in stop_words])

    chinese_parts = re.findall(r"[\u4e00-\u9fff]+", text)

    for part in chinese_parts:
        chars = [ch for ch in part if ch not in stop_words]

        for i in range(len(chars)):
            if i + 2 <= len(chars):
                tokens.append("".join(chars[i:i + 2]))

            if i + 3 <= len(chars):
                tokens.append("".join(chars[i:i + 3]))

            if i + 4 <= len(chars):
                tokens.append("".join(chars[i:i + 4]))

    return tokens


def score_chunk(query_tokens, chunk):
    if not query_tokens:
        return 0

    chunk_lower = (chunk or "").lower()
    score = 0

    for token in query_tokens:
        if token in chunk_lower:
            score += len(token)

    return score


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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
        ON document_chunks(document_id)
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

    ensure_document_chunks()


def create_document_chunks(document_id, content):
    chunks = split_text(content, chunk_size=900, overlap=120)

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))

    now = now_text()

    for index, chunk in enumerate(chunks):
        cursor.execute(
            """
            INSERT INTO document_chunks (document_id, chunk_index, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (document_id, index, chunk, now)
        )

    conn.commit()
    conn.close()

    return len(chunks)


def ensure_document_chunks():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT d.id, d.content
        FROM documents d
        LEFT JOIN document_chunks c ON c.document_id = d.id
        GROUP BY d.id
        HAVING COUNT(c.id) = 0
    """)

    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        create_document_chunks(row["id"], row["content"] or "")


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


def save_message(role, content, session_id):
    conn = get_conn()
    cursor = conn.cursor()

    now = now_text()

    cursor.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now)
    )

    cursor.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now, session_id)
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


def has_documents():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM documents")
    row = cursor.fetchone()

    conn.close()

    return row["count"] > 0


def get_relevant_document_context(query, max_chars=6000, top_k=6):
    query_lower = (query or "").lower()

    want_pdf = "pdf" in query_lower
    want_txt = "txt" in query_lower or "md" in query_lower or "markdown" in query_lower

    summary_keywords = [
        "总结", "概括", "主要内容", "主要讲", "讲了什么", "内容是什么",
        "summarize", "summary"
    ]

    is_summary_request = any(keyword in query_lower for keyword in summary_keywords)

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            d.id AS document_id,
            d.filename AS filename,
            c.chunk_index AS chunk_index,
            c.content AS chunk_content
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        ORDER BY d.id DESC, c.chunk_index ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return ""

    filtered_rows = []

    for row in rows:
        filename = row["filename"].lower()

        if want_pdf and not filename.endswith(".pdf"):
            continue

        if want_txt and not (filename.endswith(".txt") or filename.endswith(".md")):
            continue

        filtered_rows.append(row)

    rows = filtered_rows

    if not rows:
        return ""

    def build_context_from_rows(selected_rows):
        parts = []
        used_chars = 0

        for row in selected_rows:
            filename = row["filename"]
            chunk_index = row["chunk_index"]
            chunk = row["chunk_content"] or ""

            part = f"【文档：{filename}｜片段：{chunk_index + 1}】\n{chunk}"

            if used_chars + len(part) > max_chars:
                remaining = max_chars - used_chars

                if remaining <= 0:
                    break

                part = part[:remaining]

            parts.append(part)
            used_chars += len(part)

            if used_chars >= max_chars:
                break

        return "\n\n".join(parts)

    if is_summary_request and want_pdf:
        return build_context_from_rows(rows)

    query_tokens = tokenize_text(query)

    candidates = []

    for row in rows:
        score = score_chunk(query_tokens, row["chunk_content"] or "")

        if score > 0:
            candidates.append({
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "chunk": row["chunk_content"],
                "score": score
            })

    if not candidates and is_summary_request:
        return build_context_from_rows(rows)

    if not candidates and want_pdf:
        return build_context_from_rows(rows)

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x["score"], reverse=True)

    selected = []
    used_chars = 0

    for item in candidates[:top_k]:
        filename = item["filename"]
        chunk_index = item["chunk_index"]
        chunk = item["chunk"]

        part = f"【文档：{filename}｜片段：{chunk_index + 1}】\n{chunk}"

        if used_chars + len(part) > max_chars:
            remaining = max_chars - used_chars

            if remaining <= 0:
                break

            part = part[:remaining]

        selected.append(part)
        used_chars += len(part)

        if used_chars >= max_chars:
            break

    return "\n\n".join(selected)


def build_system_message(user_msg):
    document_context = get_relevant_document_context(user_msg)

    if document_context:
        system_content = f"""
{SYSTEM_PROMPT}

以下是根据用户问题从知识库中检索到的相关文档片段。

回答规则：
1. 如果用户的问题与文档片段相关，请优先根据文档内容回答。
2. 如果文档片段中没有相关信息，请明确说明“上传的文档中没有找到相关内容”。
3. 不要编造文档中不存在的信息。
4. 如果用户明确要求根据 PDF 回答，只能依据 PDF 文档片段，不要参考 txt 或 md 文档。
5. 如果用户明确要求根据 txt 或 md 回答，只能依据 txt 或 md 文档片段，不要参考 PDF。
6. 可以适当补充解释，但必须区分“文档内容”和“补充说明”。

相关文档片段如下：

{document_context}
"""
    else:
        if has_documents():
            system_content = f"""
{SYSTEM_PROMPT}

当前用户已经上传了知识库文档，但系统没有检索到与本次问题明显相关的文档片段。

回答规则：
1. 如果用户明确要求“根据上传文档”回答，请说明“上传的文档中没有找到相关内容”。
2. 如果用户明确要求根据 PDF 回答，但没有检索到 PDF 内容，请说明“上传的 PDF 中没有找到相关内容”。
3. 如果用户只是普通提问，可以正常回答。
4. 不要假装看到了文档中不存在的内容。
"""
        else:
            system_content = SYSTEM_PROMPT

    return {
        "role": "system",
        "content": system_content
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "DeepSeek Flask Chat is running"
    })


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


@app.route("/api/documents", methods=["GET"])
def api_list_documents():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            d.id,
            d.filename,
            d.created_at,
            COUNT(c.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks c ON c.document_id = d.id
        GROUP BY d.id
        ORDER BY d.id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    documents = [
        {
            "id": row["id"],
            "filename": row["filename"],
            "created_at": row["created_at"],
            "chunk_count": row["chunk_count"]
        }
        for row in rows
    ]

    return jsonify({
        "documents": documents
    })


@app.route("/api/documents/<int:document_id>", methods=["GET"])
def api_get_document(document_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, filename, content, created_at
        FROM documents
        WHERE id = ?
        """,
        (document_id,)
    )

    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "文档不存在"}), 404

    cursor.execute(
        "SELECT COUNT(*) AS chunk_count FROM document_chunks WHERE document_id = ?",
        (document_id,)
    )

    chunk_row = cursor.fetchone()
    conn.close()

    content = row["content"] or ""

    max_preview_chars = 12000
    is_truncated = len(content) > max_preview_chars

    return jsonify({
        "id": row["id"],
        "filename": row["filename"],
        "created_at": row["created_at"],
        "content": content[:max_preview_chars],
        "content_length": len(content),
        "chunk_count": chunk_row["chunk_count"],
        "is_truncated": is_truncated
    })


@app.route("/api/documents/upload", methods=["POST"])
def api_upload_document():
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "只支持 .txt、.md 和 .pdf 文件"}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    original_filename = file.filename
    safe_filename = secure_filename(original_filename)

    ext = get_file_ext(original_filename)

    if not safe_filename:
        safe_filename = f"document_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"

    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(file_path)

    content = read_uploaded_file(file_path, ext)

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO documents (filename, content, created_at) VALUES (?, ?, ?)",
        (original_filename, content, now_text())
    )

    document_id = cursor.lastrowid

    conn.commit()
    conn.close()

    chunk_count = create_document_chunks(document_id, content)

    return jsonify({
        "message": "文件上传成功",
        "filename": original_filename,
        "document_id": document_id,
        "chunk_count": chunk_count
    })


@app.route("/api/documents/<int:document_id>", methods=["DELETE"])
def api_delete_document(document_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    conn.commit()
    conn.close()

    return jsonify({
        "message": "文档已删除",
        "document_id": document_id
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({
            "error": "没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件"
        }), 500

    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    session_id = data.get("session_id")

    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    session_id = get_or_create_session(session_id)

    save_message("user", user_msg, session_id)
    update_session_title_if_needed(session_id, user_msg)

    history_messages = get_messages(session_id, limit=20)

    system_message = build_system_message(user_msg)

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
        return Response(
            "没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件",
            mimetype="text/plain; charset=utf-8"
        )

    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    session_id = data.get("session_id")

    if not user_msg:
        return Response(
            "消息不能为空",
            mimetype="text/plain; charset=utf-8"
        )

    session_id = get_or_create_session(session_id)

    save_message("user", user_msg, session_id)
    update_session_title_if_needed(session_id, user_msg)

    history_messages = get_messages(session_id, limit=20)

    system_message = build_system_message(user_msg)

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
                with client.stream(
                    "POST",
                    DEEPSEEK_URL,
                    headers=headers,
                    json=payload
                ) as response:

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


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )