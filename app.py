from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
import httpx

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("DEEPSEEK_API_KEY")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    if not API_KEY:
        return jsonify({"reply": "没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件"}), 500

    data_from_frontend = request.get_json()
    messages = data_from_frontend.get("messages", [])

    if not messages:
        return jsonify({"reply": "消息不能为空"}), 400

    url = "https://api.deepseek.com/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    system_message = {
        "role": "system",
        "content": "你是一个耐心、清晰、适合大学生学习使用的 AI 助手。回答要简洁、有条理。"
    }

    final_messages = [system_message] + messages[-20:]

    payload = {
        "model": "deepseek-v4-flash",
        "messages": final_messages,
        "stream": False
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

        return jsonify({"reply": ai_reply})

    except Exception as e:
        return jsonify({"reply": f"程序报错：{str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)