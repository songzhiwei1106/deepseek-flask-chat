# DeepSeek Flask Chat

这是一个基于 Flask 和 DeepSeek API 的 AI 聊天网页项目。

本项目实现了一个简单的网页聊天助手：用户在网页输入问题，后端通过 Flask 接收请求，并调用 DeepSeek API 返回 AI 回复。

## 功能

- Flask 后端服务
- DeepSeek API 调用
- 前端聊天页面
- 支持用户输入并返回 AI 回复
- 使用 `.env` 文件保护 API Key
- 使用 `requirements.txt` 管理依赖

## 项目结构

```text
AI_PROJECT/
├── app.py
├── .env
├── .gitignore
├── requirements.txt
├── README.md
├── templates/
│   └── index.html
├── tests/
│   ├── test_deepseek.py
│   └── test_httpx.py
└── venv/
```

## 环境要求

- Python 3.10+
- VSCode
- DeepSeek API Key

## 安装与运行

### 1. 创建虚拟环境

```bash
python -m venv venv
```

### 2. 激活虚拟环境

Windows PowerShell：

```bash
.\venv\Scripts\Activate.ps1
```

如果是 CMD：

```bash
venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 创建 `.env` 文件

在项目根目录下创建 `.env` 文件，并写入：

```env
DEEPSEEK_API_KEY=你的DeepSeek API Key
```

注意：不要把真实 API Key 上传到 GitHub。

### 5. 启动项目

```bash
python app.py
```

### 6. 浏览器访问

```text
http://127.0.0.1:5000
```

## `.gitignore` 内容

```gitignore
venv/
.env
__pycache__/
*.pyc
```

## 技术栈

- Python
- Flask
- HTML
- CSS
- JavaScript
- DeepSeek API
- httpx
- python-dotenv

## 当前版本

### v1.8

已完成：

- Flask 项目搭建
- DeepSeek API 接入
- 前端聊天页面
- 支持多轮对话记忆
- 支持 SQLite 保存聊天记录
- 支持多会话管理
- 支持新建、切换、删除会话
- 支持 Markdown 渲染
- 支持代码高亮显示
- 支持 AI 回复流式输出
- 支持浅色 / 深色模式切换
- 支持 `/health` 健康检查接口
- 支持本地运行
- 支持 Cloudflare Quick Tunnel 临时公网访问
## 临时公网访问

本项目支持使用 Cloudflare Quick Tunnel 生成临时公网访问链接。

先启动 Flask 项目：

```bash
python app.py