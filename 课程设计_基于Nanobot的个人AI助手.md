# 基于Nanobot的个人AI助手课程设计

## 一、项目背景及意义

随着大语言模型（LLM）技术的快速发展，个人AI助手已成为人机交互的重要载体。然而，现有商业AI助手通常体积庞大、代码复杂，难以进行二次开发和学习研究。**nanobot** 是一个由香港大学开源的超轻量级个人AI助手，其核心代码仅约**4,000行**，相比同类产品OpenClaw的43万行代码，体积缩小了99%。这种极简设计使得开发者能够快速理解AI Agent的核心原理，掌握LLM与工具调用的交互机制，并在此基础上进行定制化开发。

本课程设计基于nanobot项目，旨在通过七天系统学习，深入理解AI Agent的架构设计、核心循环（LLM ↔ Tool）、两层记忆系统、Provider抽象以及Channel集成等关键技术。通过本课程设计，学生将具备独立开发、扩展和维护个人AI助手的能力，为未来从事AI Agent相关开发工作奠定坚实基础。

---

## 二、项目基础

### 2.1 nanobot简介

**nanobot** 是HKUDS开源的超轻量级个人AI助手，采用模块化架构设计，支持多种聊天平台接入和多个LLM Provider。其核心特性包括：

| 特性 | 说明 |
|------|------|
| 超轻量 | 约4,000行核心代码，99%小于同类产品 |
| 多平台 | 支持Telegram、Discord、WhatsApp、飞书、QQ、钉钉、Slack、Email、Matrix、Mochat等11+平台 |
| 多模型 | 支持Claude、GPT、DeepSeek、通义千问、Kimi、智谱GLM、MiniMax等主流LLM |
| 工具生态 | 内置Shell、文件系统、Web搜索、MCP集成、定时任务等工具 |
| 主动唤醒 | Heartbeat机制支持定期检查任务并主动执行 |

### 2.2 核心架构

nanobot采用分层架构设计，主要包含以下核心模块：

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI 命令行                            │
│  (nanobot onboard / agent / gateway / status)              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      配置系统 (Pydantic)                     │
│  agents / channels / providers / tools                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      核心组件 (AgentLoop)                    │
│                      MessageBus 消息总线                     │
└─────────────────────────────────────────────────────────────┘
          │               │               │               │
          ▼               ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ Channels │    │Providers │   │  Tools   │   │  Memory  │
    │  聊天平台 │    │ LLM抽象层 │   │ 工具系统  │   │  记忆系统  │
    └──────────┘    └──────────┘   └──────────┘   └──────────┘
                                                      │
                                    ┌─────────────────┴─────────────────┐
                                    ▼                               ▼
                              session/                          agent/
                              manager.py                       memory.py
```

### 2.3 核心概念

#### Agent Loop（代理循环）
Agent Loop是nanobot的核心引擎，负责LLM与工具之间的循环调用。当用户发送消息时，Agent Loop构建上下文（Context），调用LLM生成回复；若LLM返回工具调用请求，则执行相应工具并把结果返回给LLM，如此往复直到任务完成。

#### Memory System（记忆系统）
nanobot采用两层记忆设计：
- **ORY.md** - 长期记忆，存储Agent的角色设定、技能和工具描述
- **HISTORY** - 会话历史，记录当前对话的交互内容

#### Provider抽象
通过Provider Registry模式，nanobot支持快速接入新的LLM。添加新Provider仅需两步：在`providers/registry.py`添加`ProviderSpec`条目，在`config/schema.py`添加配置字段。

#### Channel抽象
每个聊天平台（Channel）继承自`ChannelBase`基类，实现消息收发、用户识别等接口，实现真正的多平台接入。

---

## 三、技术栈及环境要求

### 3.1 技术栈

| 层次 | 技术/框架 | 说明 |
|------|-----------|------|
| **编程语言** | Python ≥3.11 | 核心开发语言 |
| **配置管理** | Pydantic | 类型安全的配置验证 |
| **LLM集成** | LiteLLM | 统一的多Provider调用接口 |
| **异步框架** | asyncio | 高并发异步编程 |
| **CLI框架** | Typer | 命令行界面构建 |
| **消息队列** | asyncio.Queue | 组件间消息传递 |
| **日志管理** | loguru | 现代化日志输出 |

### 3.2 主要依赖

```
# pyproject.toml 核心依赖
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings",
    "litellm>=1.0",
    "typer[all]",
    "loguru",
    "httpx",
    "aiohttp",
    "python-dotenv",
]

# 可选依赖
extras = {
    "dev": ["pytest", "pytest-asyncio", "ruff"],
    "matrix": ["mautrix", "mautrix-whatsapp"],
}
```

### 3.3 环境要求

#### 运行环境
- **操作系统**：Linux / macOS / Windows
- **Python版本**：≥ 3.11
- **内存建议**：至少4GB RAM
- **磁盘空间**：至少500MB

#### 必需配置
- **LLM API Key**：需要从支持的Provider获取API密钥
  - 推荐：OpenRouter（全球用户）
  - 国内：硅基流动、通义千问、智谱GLM、MiniMax等
- **工作目录**：~/.nanobot/workspace/

#### 可选配置
- **聊天平台Token**：如Telegram Bot Token、Discord Bot Token等
- **MCP服务器**：用于扩展工具能力

### 3.4 快速启动

```bash
# 1. 安装项目
git clone https://github.com/HKUDS/nanobot.git
cd nanobot
pip install -e .

# 2. 初始化配置
nanobot onboard

# 3. 配置API密钥（编辑 ~/.nanobot/config.json）
# 添加 providers.openrouter.apiKey

# 4. 开始对话
nanobot agent -m "你好！"
```

---

## 四、学习计划

本课程设计分为七天学习计划：

| Day | 主题 | 核心文件 |
|-----|------|----------|
| Day 1 | 项目结构与配置系统 | `config/schema.py`, `config/loader.py` |
| Day 2 | Agent核心循环 | `agent/loop.py`, `agent/context.py` |
| Day 3 | Memory与Session | `agent/memory.py`, `session/manager.py` |
| Day 4 | Tool与Skill扩展系统 | `agent/tools/`, `agent/skills.py` |
| Day 5 | Provider系统与LLM集成 | `providers/registry.py` |
| Day 6 | Channel系统 | `channels/base.py`, `channels/manager.py` |
| Day 7 | 进阶功能与实战 | `cron/service.py`, `heartbeat/service.py` |

---

## 五、总结

本课程设计基于nanobot项目，通过系统学习AI Agent的核心技术，帮助学生掌握：
- 模块化软件架构设计
- LLM与工具的交互机制
- 多平台接入的抽象设计
- 异步编程与配置管理

完成本课程设计后，学生将能够独立开发、定制和扩展个人AI助手，为未来在AI Agent领域的研究和应用开发打下坚实基础。

---

*文档版本：v1.0*
*更新时间：2026-03-06*
