from dotenv import load_dotenv
import os
import httpx

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError("没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件")

url = "https://api.deepseek.com/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

data = {
    "model": "deepseek-v4-flash",
    "messages": [
        {"role": "user", "content": "你好，请简单介绍一下你自己"}
    ],
    "stream": False
}

with httpx.Client(timeout=30, trust_env=False) as client:
    response = client.post(url, headers=headers, json=data)

print("状态码：", response.status_code)
print("返回内容：")
print(response.text)