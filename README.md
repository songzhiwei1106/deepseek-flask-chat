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
## 项目亮点

- 基于 Flask 搭建后端服务，完成聊天、历史记录、会话管理、文档上传、文档预览等接口设计
- 使用 DeepSeek API 实现 AI 对话能力，并支持流式输出，回复体验接近 ChatGPT
- 使用 SQLite 保存聊天记录、会话数据和上传文档内容
- 支持多会话管理，可新建、切换、删除不同聊天会话
- 支持 Markdown 渲染和代码高亮，适合学习、编程问答场景
- 支持上传 `.txt` / `.md` / `.pdf` 文档，并基于文档内容进行知识库问答
- 使用 PyPDF2 解析 PDF 文本内容，并将解析结果保存到数据库
- 实现了基于关键词检索的简易 RAG，根据用户问题从知识库中匹配相关文档片段
- 支持根据用户问题区分 PDF 与 txt / md 文档来源，避免 PDF 问答误用 txt 内容
- 支持点击文档查看提取出的文本内容，方便调试 PDF 是否成功解析
- 使用 `.env` 和 `.gitignore` 管理敏感信息，避免 API Key、数据库和上传文件被提交到 GitHub
- 支持 Cloudflare Quick Tunnel 临时公网访问，方便项目演示

## 技术栈

- Python
- Flask
- HTML
- CSS
- JavaScript
- DeepSeek API
- httpx
- python-dotenv
## 项目预览

![项目预览](assets/screenshot.png)

## 当前版本

### v2.2 文档内容预览与 PDF 提取调试版

当前项目已从基础 AI 聊天助手升级为支持本地知识库问答的 AI 学习助手。

用户可以上传 `.txt`、`.md`、`.pdf` 文档，系统会将文档内容解析并保存到 SQLite 数据库中。用户提问时，后端会根据问题从知识库文档中检索相关片段，并将相关内容注入提示词，引导 DeepSeek 根据上传文档进行回答。

v2.2 新增了文档内容预览功能，用户可以点击左侧文档列表中的文件名，查看系统实际提取出来的文档文本内容，便于判断 PDF 是否解析成功，尤其适合调试扫描版 PDF 或论文类 PDF。

已完成：

- Flask 后端项目搭建
- DeepSeek API 接入
- 前端聊天页面
- 多轮对话记忆
- SQLite 聊天记录保存
- 多会话管理
- Markdown 渲染
- 代码高亮
- AI 回复流式输出
- 浅色 / 深色模式切换
- Cloudflare Quick Tunnel 临时公网访问
- 支持上传 `.txt` / `.md` / `.pdf` 文档
- 支持文档列表展示与删除
- 支持 PDF 文本解析
- 支持点击文档查看提取出的文本内容
- 支持显示文档上传时间、提取字符数和预览内容
- 支持根据上传文档内容进行知识库问答
- 支持基于关键词检索相关文档片段
- 支持根据用户问题区分 PDF 与 txt / md 文档来源
- 支持 PDF 提取结果调试，方便判断 PDF 是否为扫描版或图片型 PDF
## 临时公网访问

本项目支持使用 Cloudflare Quick Tunnel 生成临时公网访问链接。

先启动 Flask 项目：

```bash
python app.py
