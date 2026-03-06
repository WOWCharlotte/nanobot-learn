# Nanobot 7天学习计划

> 目标：7天内掌握nanobot全部实现，达到求职要求

## 前置要求
- 具备Python基础（async/await、类型注解）
- 了解Pydantic基本用法
- 熟悉HTTP API和WebSocket概念

---

## Day 1: 项目结构与核心概念

### 上午：项目概览
**目标**：理解nanobot是什么，整体架构是怎样的

**学习内容**：
1. 阅读 README.md 完整了解项目
2. 阅读 pyproject.toml 了解依赖
3. 浏览项目目录结构：
   ```
   nanobot/
   ├── agent/          # 核心agent逻辑
   ├── channels/       # 聊天平台集成
   ├── providers/      # LLM provider抽象
   ├── session/        # 会话管理
   ├── config/         # 配置系统
   ├── bus/            # 消息总线
   ├── cron/           # 定时任务
   ├── heartbeat/      # 心跳/主动唤醒
   ├── skills/         # 内置技能
   └── cli/            # CLI命令
   ```

**下午：配置系统**
**目标**：理解配置如何加载和验证

**关键文件**：
- `config/schema.py` - Pydantic配置模型（重点：`Config`、`ProvidersConfig`、`ChannelConfig`）
- `config/loader.py` - 配置加载逻辑

> 📖 详细讲解：[docs/Day1/README.md](./docs/Day1/README.md)

**学习要点**：
- Pydantic模型的嵌套结构
- 配置验证逻辑
- 默认值处理

**动手练习**：
- 尝试修改配置模型，添加一个新配置项
- 运行 `nanobot status` 查看配置解析结果

---

## Day 2: Agent核心循环

### 上午：Agent Loop
**目标**：理解agent如何处理消息并与LLM交互

**关键文件**：
- `agent/loop.py` (510行) - **最核心的文件**

> 📖 详细讲解：[docs/Day2/AGENT_LOOP.md](./docs/Day2/AGENT_LOOP.md)

**核心流程**：
```
用户消息 -> Session管理 -> Context构建 -> LLM调用 -> Tool执行 -> 响应用户
                   ^                                              |
                   +------------------- Memory Consolidation <---+
```

**重点理解**：
1. `_run_agent_loop()` (行180-257) - LLM与工具的循环
2. `_process_message()` (行330-453) - 消息分发和处理
3. Memory Consolidation - 如何将长期记忆归档
4. Tool Call处理 - LLM返回的工具调用如何执行

### 下午：Context构建
**目标**：理解prompt如何生成

**关键文件**：
- `agent/context.py` (174行)

> 📖 详细讲解：[docs/Day2/CONTEXT.md](./docs/Day2/CONTEXT.md)

**学习要点**：
- System Prompt的组成（identity、bootstrap、memory、skills）
- 运行时上下文注入
- 多模态输入处理（图片base64编码）
- Thinking block支持

**动手练习**：
- 打印agent的system prompt，理解各部分内容
- 修改context.py，添加自定义内容到prompt

---

## Day 3: Memory与Session

### 上午：两层记忆系统
**目标**：理解nanobot如何管理对话历史和长期记忆

**关键文件**：
- `agent/memory.py` (151行)

> 📖 详细讲解：[docs/Day3/MEMORY.md](./docs/Day3/MEMORY.md)

**核心概念**：
- `MEMORY.md` - 长期持久化的事实（只增不减）
- `HISTORY.md` - 可grep搜索的对话日志
- `consolidate()` - LLM驱动的记忆摘要

**学习要点**：
- 何时触发记忆整合
- 如何决定哪些内容进入长期记忆
- 记忆文件的格式

### 下午：Session管理
**目标**：理解会话如何持久化和恢复

**关键文件**：
- `session/manager.py` (213行)

> 📖 详细讲解：[docs/Day3/SESSION.md](./docs/Day3/SESSION.md)

**学习要点**：
- 消息的追加写入模式（append-only）
- Session数据结构
- 与LLM cache的兼容性

**动手练习**：
- 发送几条消息，检查 `~/.nanobot/workspace/` 下的 MEMORY.md 和 HISTORY.md 如何变化

---

## Day 4: Tool与Agent扩展系统

### 上午：Tool与Skills系统
**目标**：理解工具和技能的注册机制

**关键文件**：
- `agent/tools/base.py` - Tool基类
- `agent/tools/registry.py` - 工具注册表
- `agent/skills.py` (229行) - 技能加载器

> 📖 详细讲解：
> - [docs/Day4/TOOL.md](./docs/Day4/TOOL.md) - Tool系统
> - [docs/Day4/SKILLS.md](./docs/Day4/SKILLS.md) - Skills系统

**学习要点 - Tool系统**：
- Tool接口定义（name、description、parameters）
- JSON Schema参数验证
- 工具执行流程（register → execute → result）
- ToolRegistry注册与管理

**学习要点 - Skills系统**：
- SKILL.md 定义技能
- 技能来源：workspace/skills/ (用户) 和 nanobot/skills/ (内置)
- YAML frontmatter 元数据
- always: true 常驻加载
- requires 依赖检查

**内置技能**：
| 技能 | 说明 | 依赖 |
|------|------|------|
| memory | 两层记忆系统 | 无 (always) |
| cron | 定时任务管理 | 无 |
| weather | 天气查询 | 无 |
| clawhub | ClawHub技能市场 | 无 |
| skill-creator | 技能创建工具 | 无 |
| github | GitHub CLI操作 | gh CLI |
| tmux | Tmux会话管理 | tmux CLI |
| summarize | 文本/音视频摘要 | summarize CLI |

---

### 下午：内置工具与Subagent
**目标**：理解内置工具实现和子Agent机制

**关键文件**：
1. `agent/tools/shell.py` - Shell命令执行
   - 安全防护机制（deny_patterns）
   - 路径限制（workspace边界）
   - 超时处理

2. `agent/tools/filesystem.py` - 文件操作
   - read_file/write_file/edit_file/list_dir
   - 路径解析和workspace限制

3. `agent/tools/message.py` - 消息发送
4. `agent/tools/web.py` - 网页搜索/抓取
5. `agent/tools/cron.py` - 定时任务管理
6. `agent/subagent.py` (247行) - 子Agent管理

> 📖 详细讲解：
> - [docs/Day4/SUBAGENT.md](./docs/Day4/SUBAGENT.md) - Subagent系统

**学习要点 - 内置工具**：
- ExecTool安全机制详解
- 文件操作工具路径限制
- 工具注册流程

**学习要点 - Subagent系统**：
- spawn() 启动子Agent
- _run_subagent() 独立执行循环（无message/spawn工具）
- _announce_result() 结果回传
- cancel_by_session() 任务取消
- 子Agent vs 主Agent对比

**动手练习**：
- 实现一个简单的自定义工具
- 添加到registry中测试

---

## Day 5: Provider系统与LLM集成

### 上午：Provider架构
**目标**：理解如何支持多种LLM

**关键文件**：
- `providers/registry.py` (463行) - **非常重要**
- `providers/base.py` - Provider接口

> 📖 详细讲解：[docs/Day5/PROVIDER.md](./docs/Day5/PROVIDER.md)

**学习要点**：
- `ProviderSpec` - Provider元数据定义
- 添加新Provider只需2步（重点！）
- 模型自动检测逻辑（find_by_model, find_gateway）
- Gateway vs Standard Provider

**支持的Provider**：
| 类型 | Provider |
|------|----------|
| Gateway | OpenRouter, AiHubMix, SiliconFlow, VolcEngine |
| Standard | Anthropic, OpenAI, DeepSeek, Gemini, Zhipu, DashScope, Moonshot, MiniMax |
| Local | vLLM |
| OAuth | OpenAI Codex, Github Copilot |

### 下午：LiteLLM集成
**目标**：理解LiteLLM如何封装各种LLM

**关键文件**：
- `providers/litellm_provider.py`
- `providers/custom_provider.py`

**学习要点**：
- LiteLLM的封装方式
- 请求/响应格式转换
- 错误处理

**动手练习**：
- 按照README中的指南，添加一个新的Provider

---

## Day 6: Channel系统

### 上午：Channel架构
**目标**：理解如何接入各种聊天平台

**关键文件**：
- `channels/base.py` - Channel基类
- `channels/manager.py` - Channel管理

> 📖 详细讲解：[docs/Day6/CHANNEL.md](./docs/Day6/CHANNEL.md)

**核心概念**：
- 继承 `BaseChannel`
- 实现 `start()`, `stop()`, `send()`, `is_allowed()`
- 消息队列集成（MessageBus）

**支持的Channel**：
| Channel | 协议 |
|---------|------|
| Telegram | Bot API |
| Discord | Gateway |
| WhatsApp | WebSocket |
| Feishu | WebSocket |
| QQ | botpy SDK |
| DingTalk | Stream |
| Slack | Socket Mode |
| Email | IMAP/SMTP |
| Matrix | Client-Server |
| Mochat | API |

### 下午：具体Channel实现
**目标**：理解各个平台如何集成

**推荐学习顺序**（由简单到复杂）：
1. `channels/telegram.py` - 最规范的实现
2. `channels/discord.py` - Discord Gateway
3. `channels/feishu.py` - WebSocket长连接
4. `channels/email.py` - IMAP/SMTP

**其他Channel**：
- WhatsApp, Slack, QQ, DingTalk, Matrix, Mochat

**学习要点**：
- 各平台API差异
- 消息格式转换（Markdown → 平台格式）
- 权限控制（allowFrom）

**动手练习**：
- 阅读一个Channel实现，尝试理解其消息收发流程

---

## Day 7: 进阶功能与实战

### 上午：Cron与Heartbeat

**关键文件**：
- `cli/commands.py` - CLI 命令
- `cron/service.py` - Cron 服务
- `heartbeat/service.py` - Heartbeat 服务

> 📖 详细讲解：[docs/Day7/CLI_CRON_HEARTBEAT.md](./docs/Day7/CLI_CRON_HEARTBEAT.md)

**学习要点 - Cron**：
- 支持 `at`、`every`、`cron` 三种调度模式
- 持久化到 JSON
- 通过 cron 工具管理任务

**学习要点 - Heartbeat**：
- 读取 `HEARTBEAT.md` 文件
- 两阶段执行：决策（LLM工具调用）+ 执行
- 避免自由文本解析的不确定性

**学习要点 - CLI**：
- Typer 框架
- 单消息模式 vs 交互式模式
- Gateway 启动流程

### 下午：项目总结

**整体串联**：
```
CLI/Commands
    |
    v
ChannelManager <---> Config
    |                   |
    v                   v
MessageBus <---------> Agent Loop
    |                   |
    v                   |
Outbound <---------- ContextBuilder
                         |
                    ToolRegistry
                         |
              +----------+----------+
              |          |          |
          Providers   Sessions    Memory
              |
          LiteLLM
```

**整体串联**：
```
CLI/Commands
    |
    v
ChannelManager <---> Config
    |                   |
    v                   v
MessageBus <---------> Agent Loop
    |                   |
    v                   |
Outbound <---------- ContextBuilder
                         |
                    ToolRegistry
                         |
              +----------+----------+
              |          |          |
          Providers   Sessions    Memory
              |
          LiteLLM
```

---

## 面试要点总结

### 必须掌握的核心概念
1. **Agent Loop** - LLM与Tool的循环调用
2. **Memory System** - 两层记忆设计（MEMORY.md + HISTORY.md）
3. **Tool System** - 工具注册和执行机制
4. **Provider抽象** - 如何支持多种LLM
5. **Channel抽象** - 如何接入多种聊天平台

### 可能会被问到的问题
1. 为什么选择append-only的session设计？（LLM cache友好）
2. Memory Consolidation的触发时机？（每N条消息）
3. 如何保证工具执行的安全性？（路径限制、deny patterns）
4. Channel之间如何协调消息发送？（MessageBus）
5. 添加新Provider的流程是怎样的？（2步法）

### 亮点要能说出来
1. ~4000行核心代码的轻量级设计
2. 2步添加新Provider的Registry模式
3. 两层记忆系统（短期session + 长期MEMORY.md）
4. 统一的Channel抽象（可扩展）
5. Tool-based的Memory Consolidation（确定性行为）

---

## 实践项目建议

完成学习后，可以尝试：
1. 添加一个新的Channel（如Line、Discord）
2. 添加一个新的Provider
3. 编写一个自定义Tool
4. 实现一个新的Skill
5. 给现有功能写单元测试

---

## 学习资源

- nanobot/README.md - 完整项目文档
- nanobot/skills/ - 内置技能示例
- nanobot/tests/ - 测试用例参考
- LiteLLM文档: https://docs.litellm.ai/
- 各平台API文档（Telegram Bot API、Discord Developer Portal等）
