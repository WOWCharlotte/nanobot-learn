# Context Builder 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 2 的补充材料

## 概述

`agent/context.py` 是 nanobot 的 **Prompt 构建器**（174行），负责：
1. 构建 System Prompt（身份、引导文件、记忆、技能）
2. 构建完整的消息列表
3. 处理多模态输入（图片）
4. 管理工具调用结果

---

## 类：ContextBuilder

### 初始化

```python
class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
```

**依赖组件**：
| 组件 | 用途 |
|------|------|
| `workspace` | 工作目录路径 |
| `memory` (MemoryStore) | 长期记忆管理 |
| `skills` (SkillsLoader) | 技能加载器 |

---

## 核心函数依赖关系

```
build_messages()           # 主入口：构建完整消息列表
    │
    ├─► _build_runtime_context()     # 构建运行时上下文
    ├─► _build_user_content()        # 构建用户内容（含多模态）
    │
    └─► build_system_prompt()        # 构建系统Prompt
            │
            ├─► _get_identity()              # 获取身份信息
            ├─► _load_bootstrap_files()       # 加载引导文件
            ├─► memory.get_memory_context()   # 获取记忆上下文
            ├─► skills.get_always_skills()    # 获取常驻技能
            ├─► skills.load_skills_for_context()  # 加载技能内容
            └─► skills.build_skills_summary() # 构建技能摘要


add_assistant_message()     # 在 agent loop 中调用
add_tool_result()           # 在 agent loop 中调用
```

---

## 核心函数详解

### 1. `build_system_prompt()` - 构建系统Prompt

```python
def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
    """Build the system prompt from identity, bootstrap files, memory, and skills."""
    parts = [self._get_identity()]

    # 1. 引导文件 (AGENTS.md, SOUL.md, USER.md, TOOLS.md, IDENTITY.md)
    bootstrap = self._load_bootstrap_files()
    if bootstrap:
        parts.append(bootstrap)

    # 2. 长期记忆
    memory = self.memory.get_memory_context()
    if memory:
        parts.append(f"# Memory\n\n{memory}")

    # 3. 常驻技能 (always-on)
    always_skills = self.skills.get_always_skills()
    if always_skills:
        always_content = self.skills.load_skills_for_context(always_skills)
        if always_content:
            parts.append(f"# Active Skills\n\n{always_content}")

    # 4. 技能摘要 (按需加载)
    skills_summary = self.skills.build_skills_summary()
    if skills_summary:
        parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

    return "\n\n---\n\n".join(parts)
```

**System Prompt 组成顺序**：

```
┌─────────────────────────────────────────────────────┐
│ 1. Identity (身份)                                  │
│    - nanobot 基本信息                                │
│    - Runtime (OS, Python版本)                       │
│    - Workspace 路径                                 │
│    - Guidelines (行为准则)                          │
├─────────────────────────────────────────────────────┤
│ 2. Bootstrap Files (引导文件)                       │
│    - AGENTS.md, SOUL.md, USER.md, TOOLS.md,        │
│      IDENTITY.md (按顺序)                           │
├─────────────────────────────────────────────────────┤
│ 3. Memory (长期记忆)                                 │
│    - 从 MEMORY.md 读取的事实                        │
├─────────────────────────────────────────────────────┤
│ 4. Active Skills (常驻技能)                          │
│    - skills.yaml 中标记为 always: true 的技能        │
├─────────────────────────────────────────────────────┤
│ 5. Skills Summary (技能摘要)                         │
│    - 所有可用技能列表                               │
│    - 告诉 Agent 如何使用技能                        │
└─────────────────────────────────────────────────────┘
```

---

### 2. `_get_identity()` - 身份信息

```python
def _get_identity(self) -> str:
    """Get the core identity section."""
    workspace_path = str(self.workspace.expanduser().resolve())
    system = platform.system()
    runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

    return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## nanobot Guidelines
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.

Reply directly with text for conversations. Only use the 'message' tool to send to a specific chat channel."""
```

**关键信息**：
- 告知 Agent workspace 路径
- 告知记忆文件位置
- 告知技能使用方式
- 行为准则（Tool调用前声明意图、先读文件再修改等）

---

### 3. `_build_runtime_context()` - 运行时上下文

```python
@staticmethod
def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
    """Build untrusted runtime metadata block for injection before the user message."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    tz = time.strftime("%Z") or "UTC"
    lines = [f"Current Time: {now} ({tz})"]
    if channel and chat_id:
        lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
    return ContextBuilder._RUNTIME_CONTEXT" + "\n_TAG + "\n".join(lines)
```

**输出示例**：
```
[Runtime Context — metadata only, not instructions]
Current Time: 2026-03-04 15:30 (CST)
Channel: telegram
Chat ID: 123456789
```

**设计要点**：
- 添加 `_RUNTIME_CONTEXT_TAG` 标签，明确这是元数据而非指令
- 包含当前时间（带时区）
- 包含来源渠道和聊天ID

---

### 4. `_load_bootstrap_files()` - 引导文件

```python
def _load_bootstrap_files(self) -> str:
    """Load all bootstrap files from workspace."""
    parts = []

    for filename in self.BOOTSTRAP_FILES:
        file_path = self.workspace / filename
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            parts.append(f"## {filename}\n\n{content}")

    return "\n\n".join(parts) if parts else ""
```

**引导文件列表**（按优先级）：
1. `AGENTS.md` - Agent 相关配置
2. `SOUL.md` - 灵魂/性格设定
3. `USER.md` - 用户信息
4. `TOOLS.md` - 工具配置
5. `IDENTITY.md` - 身份定义

这些文件在 `workspace` 根目录下，由用户自定义。

---

### 5. `build_messages()` - 构建完整消息列表

```python
def build_messages(
    self,
    history: list[dict[str, Any]],
    current_message: str,
    skill_names: list[str] | None = None,
    media: list[str] | None = None,
    channel: str | None = None,
    chat_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build the complete message list for an LLM call."""
    runtime_ctx = self._build_runtime_context(channel, chat_id)
    user_content = self._build_user_content(current_message, media)

    # 合并运行时上下文和用户消息
    # 避免连续同角色消息（某些provider会拒绝）
    if isinstance(user_content, str):
        merged = f"{runtime_ctx}\n\n{user_content}"
    else:
        merged = [{"type": "text", "text": runtime_ctx}] + user_content

    return [
        {"role": "system", "content": self.build_system_prompt(skill_names)},
        *history,
        {"role": "user", "content": merged},
    ]
```

**消息列表结构**：

```
[
    {"role": "system", "content": "完整的 System Prompt"},
    ...history (之前的对话历史),
    {"role": "user", "content": "运行时上下文 + 当前消息"}
]
```

**设计要点**：
- 运行时上下文注入到用户消息中，避免连续 system 消息
- 支持多模态（图片 base64 编码）

---

### 6. `_build_user_content()` - 用户内容（多模态支持）

```python
def _build_user_content(self, text: str, media: list[str] | None = None) -> str | list[dict[str, Any]]:
    """Build user message content with optional base64-encoded images."""
    if not media:
        return text

    images = []
    for path in media:
        p = Path(path)
        mime, _ = mimetypes.guess_type(path)
        if not p.is_file() or not mime or not mime.startswith("image/"):
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    if not images:
        return text
    return images + [{"type": "text", "text": text}]
```

**多模态处理流程**：
```
1. 检查 media 列表
2. 遍历每个媒体文件
   ├─► 检查是否为图片 (image/*)
   ├─► 读取文件内容
   ├─► base64 编码
   └─► 转换为 {type: "image_url", image_url: {url: "data:image/xxx;base64,..."}}
3. 返回 [images..., {type: "text", text: "..."}]
```

---

### 7. `add_tool_result()` - 添加工具结果

```python
def add_tool_result(
    self, messages: list[dict[str, Any]],
    tool_call_id: str, tool_name: str, result: str,
) -> list[dict[str, Any]]:
    """Add a tool result to the message list."""
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": result
    })
    return messages
```

**调用位置**：在 `_run_agent_loop()` 中，每次工具执行后调用

---

### 8. `add_assistant_message()` - 添加助手消息

```python
def add_assistant_message(
    self, messages: list[dict[str, Any]],
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning_content: str | None = None,
    thinking_blocks: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Add an assistant message to the message list."""
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    if thinking_blocks:
        msg["thinking_blocks"] = thinking_blocks
    messages.append(msg)
    return messages
```

**支持的字段**：
- `content` - 文本内容
- `tool_calls` - 工具调用列表
- `reasoning_content` - 推理内容（如 DeepSeek）
- `thinking_blocks` - Thinking 块（如 OpenAI o1）

---

## 完整消息流程图

```
┌────────────────────────────────────────────────────────────────┐
│                     build_messages()                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. System Prompt                                             │
│     ┌──────────────────────────────────────────────────────┐   │
│     │ build_system_prompt()                                │   │
│     │  ├─► _get_identity()                                │   │
│     │  ├─► _load_bootstrap_files()                        │   │
│     │  ├─► memory.get_memory_context()                    │   │
│     │  ├─► skills.get_always_skills()                     │   │
│     │  └─► skills.build_skills_summary()                  │   │
│     └──────────────────────────────────────────────────────┘   │
│                                                                │
│  2. History (来自 Session)                                     │
│     [ {"role": "user", "content": "..."},                     │
│       {"role": "assistant", "content": "..."},                 │
│       {"role": "tool", "content": "..."}, ... ]               │
│                                                                │
│  3. Current User Message                                       │
│     ┌──────────────────────────────────────────────────────┐   │
│     │ runtime_ctx + user_content                          │   │
│     │  ├─► _build_runtime_context()                      │   │
│     │  └─► _build_user_content() (含图片base64)          │   │
│     └──────────────────────────────────────────────────────┘   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                  Agent Loop (迭代中)                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  for each iteration:                                           │
│    ├─► LLM Response (assistant message)                       │
│    │      add_assistant_message(messages, content,            │
│    │                             tool_calls, reasoning...)     │
│    │                                                          │
│    ├─► Tool Execution                                         │
│    │      add_tool_result(messages, tool_call_id,             │
│    │                       tool_name, result)                  │
│    │                                                          │
│    └─► Next LLM Call (messages 包含所有历史)                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 面试要点

1. **为什么把运行时上下文注入到用户消息中？**
   - 避免连续同角色消息（某些 provider 如 Anthropic 会拒绝）
   - `_RUNTIME_CONTEXT_TAG` 标签明确这是元数据

2. **Bootstrap 文件的作用？**
   - 用户自定义 agent 行为
   - 按优先级顺序加载

3. **Memory 和 Skills 的区别？**
   - Memory：长期记忆事实（自动累积：按需加载的能力）
   - Skills扩展

4. **多模态如何处理？**
   - base64 编码图片
   - 转换为 `image_url` 格式

5. **为什么 System Prompt 分多个部分？**
   - 模块化，便于维护
   - 条件加载（memory、skills 可选）

---

## 文件位置

- 源文件：`nanobot/agent/context.py`
- 相关文件：
  - `nanobot/agent/memory.py` - 记忆系统
  - `nanobot/agent/skills.py` - 技能加载
  - `nanobot/agent/loop.py` - 调用 context 的 agent 循环
