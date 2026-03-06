# Subagent System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 4 的补充材料

## 概述

`agent/subagent.py` 是 nanobot 的 **子 Agent 系统**（247行），负责：
1. 后台任务执行
2. 子 Agent 生命周期管理
3. 结果回传主 Agent

---

## 核心概念

```
Main Agent
    │
    ├── 处理用户请求
    │
    ├── 发现耗时任务
    │
    ▼
Spawn Subagent ──────────────────────────────────────┐
    │                                                │
    │ 1. 创建独立 Task                               │
    │ 2. 分配 task_id                               │
    │ 3. 注册到 _running_tasks                       │
    │                                                │
    ▼                                                │
Subagent 执行                                         │
    │                                                │
    │ - 独立 ToolRegistry (无 message/spawn 工具)     │
    │ - 独立 Agent Loop (最多 15 次迭代)            │
    │ - 结果通过 MessageBus 回传                     │
    │                                                │
    ▼                                                │
Announce Result ─────────────────────────────────────┘
    │
    │ 注入 system message 到主 Agent
    │
    ▼
Main Agent 汇总结果给用户
```

---

## 类：SubagentManager

### 初始化

```python
class SubagentManager:
    """Manages background subagent execution."""

    def __init__(
        self,
        provider: LLMProvider,      # LLM 提供者
        workspace: Path,            # 工作目录
        bus: MessageBus,            # 消息总线
        model: str | None = None,
        temperature: float = 0.7,  # 比主 Agent 高
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        brave_api_key: str | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        restrict_to_workspace: bool = False,
    ):
        self._running_tasks: dict[str, asyncio.Task[None]] = {}  # task_id → Task
        self._session_tasks: dict[str, set[str]] = {}  # session_key → {task_id, ...}
```

---

## 核心函数依赖关系

```
SpawnTool.execute()
        │
        ▼
spawn()                  # 创建子 Agent
        │
        ├─► 创建 task_id
        ├─► 创建 asyncio.Task
        ├─► 注册到 _running_tasks
        └─► 注册到 _session_tasks

        │
        ▼
_run_subagent()         # 执行子 Agent
        │
        ├─► 构建独立 ToolRegistry
        ├─► 构建 system prompt
        ├─► 循环调用 LLM + Tools
        │
        └─► _announce_result()  # 回传结果

        │
        ▼
_announce_result()      # 通知结果
        │
        └─► 发布 InboundMessage 到 MessageBus
```

---

## 核心函数详解

### 1. `spawn()` - 启动子 Agent

```python
async def spawn(
    self,
    task: str,                    # 任务描述
    label: str | None = None,    # 显示标签
    origin_channel: str = "cli",  # 来源渠道
    origin_chat_id: str = "direct",  # 来源聊天ID
    session_key: str | None = None,
) -> str:
    """Spawn a subagent to execute a task in the background."""
    task_id = str(uuid.uuid4())[:8]  # 短 ID
    display_label = label or task[:30] + ("..." if len(task) > 30 else "")

    # 创建后台任务
    bg_task = asyncio.create_task(
        self._run_subagent(task_id, task, display_label, origin)
    )
    self._running_tasks[task_id] = bg_task

    # 按 session 追踪
    if session_key:
        self._session_tasks.setdefault(session_key, set()).add(task_id)

    # 任务完成后清理
    bg_task.add_done_callback(_cleanup)

    return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."
```

**关键设计**：
- 返回立即响应，不阻塞主 Agent
- 后台异步执行
- Session 级别的任务追踪

---

### 2. `_run_subagent()` - 执行子 Agent

```python
async def _run_subagent(
    self,
    task_id: str,
    task: str,
    label: str,
    origin: dict[str, str],
) -> None:
    """Execute the subagent task and announce the result."""
    # 1. 构建子 Agent 专用工具（无 message, 无 spawn）
    tools = ToolRegistry()
    tools.register(ReadFileTool(...))
    tools.register(WriteFileTool(...))
    tools.register(EditFileTool(...))
    tools.register(ListDirTool(...))
    tools.register(ExecTool(...))
    tools.register(WebSearchTool(...))
    tools.register(WebFetchTool(...))

    # 2. 构建 System Prompt
    system_prompt = self._build_subagent_prompt()

    # 3. 独立 Agent Loop (最多 15 次迭代)
    max_iterations = 15
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    while iteration < max_iterations:
        response = await self.provider.chat(messages=messages, tools=tools.get_definitions(), ...)

        if response.has_tool_calls:
            # 执行工具
            for tool_call in response.tool_calls:
                result = await tools.execute(tool_call.name, tool_call.arguments)
                messages.append({"role": "tool", ...})
        else:
            final_result = response.content
            break

    # 4. 回传结果
    await self._announce_result(task_id, label, task, final_result, origin, "ok")
```

**关键设计**：
- **限制工具**：无 message（防止无限循环）、无 spawn
- **迭代限制**：最多 15 次，防止失控
- **独立执行**：不依赖主 Agent 的 session

---

### 3. `_announce_result()` - 回传结果

```python
async def _announce_result(
    self,
    task_id: str,
    label: str,
    task: str,
    result: str,
    origin: dict[str, str],
    status: str,
) -> None:
    """Announce the subagent result to the main agent via the message bus."""
    status_text = "completed successfully" if status == "ok" else "failed"

    # 构建提示，让主 Agent 总结给用户
    announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

    # 注入为 system message，触发主 Agent 处理
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id=f"{origin['channel']}:{origin['chat_id']}",
        content=announce_content,
    )

    await self.bus.publish_inbound(msg)
```

**关键设计**：
- 通过 MessageBus 注入消息，而非直接回复
- 要求主 Agent 用自然语言总结给用户
- 隐藏技术细节（不提及 subagent、task_id）

---

### 4. `_build_subagent_prompt()` - 构建子 Agent Prompt

```python
def _build_subagent_prompt(self) -> str:
    """Build a focused system prompt for the subagent."""
    time_ctx = ContextBuilder._build_runtime_context(None, None)

    parts = [f"""# Subagent

{time_ctx}

You are a subagent spawned by the main agent to complete a specific task.
Stay focused on the assigned task. Your final response will be reported back to the main agent.

## Workspace
{self.workspace}"""]

    # 添加技能摘要
    skills_summary = SkillsLoader(self.workspace).build_skills_summary()
    if skills_summary:
        parts.append(f"## Skills\n\n{skills_summary}")

    return "\n\n".join(parts)
```

---

### 5. `cancel_by_session()` - 取消会话的子 Agent

```python
async def cancel_by_session(self, session_key: str) -> int:
    """Cancel all subagents for the given session. Returns count cancelled."""
    tasks = [self._running_tasks[tid] for tid in self._session_tasks.get(session_key, [])
             if tid in self._running_tasks and not self._running_tasks[tid].done()]

    for t in tasks:
        t.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return len(tasks)
```

**触发时机**：用户发送 `/stop` 命令时

---

## Subagent vs Main Agent

| 特性 | Main Agent | Subagent |
|------|------------|----------|
| 工具 | 全部 | 仅基础工具（无 message/spawn） |
| 迭代限制 | 40 | 15 |
| Temperature | 0.1 | 0.7 |
| Session | 共享 | 独立 |
| 结果返回 | 直接回复 | 注入 system message |

---

## 面试要点

1. **为什么子 Agent 需要独立的 ToolRegistry？**
   - 防止无限循环（无 spawn 工具）
   - 防止消息发送混乱（无 message 工具）
   - 减少权限暴露

2. **子 Agent 结果如何回传？**
   - 通过 MessageBus 注入 system message
   - 主 Agent 负责总结给用户
   - 隐藏技术细节

3. **子 Agent 如何与主 Agent 隔离？**
   - 独立 asyncio.Task
   - 独立 ToolRegistry
   - 独立 message list

4. **为什么子 Agent 用更高的 temperature？**
   - 主 Agent 需要确定性（0.1）
   - 子 Agent 需要创造性（0.7）

5. **/stop 命令如何取消子 Agent？**
   - 按 session_key 追踪
   - asyncio.Task.cancel()
   - 批量取消

---

## 文件位置

- 源文件：`nanobot/agent/subagent.py`
- 相关文件：
  - `nanobot/agent/tools/spawn.py` - SpawnTool 调用 spawn()
  - `nanobot/agent/loop.py` - 管理 SubagentManager
  - `nanobot/bus/queue.py` - MessageBus 传递消息
