# Memory System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 3 的补充材料

## 概述

`agent/memory.py` 是 nanobot 的 **两层记忆系统**（151行），负责：
1. 长期记忆（MEMORY.md）- 持久化的事实
2. 对话历史（HISTORY.md）- 可 grep 搜索的日志
3. 记忆整合（Consolidation）- LLM 驱动的记忆摘要

---

## 核心概念：两层记忆

```
┌─────────────────────────────────────────────────────────────────┐
│                        Session Messages                          │
│                   (短期记忆，保存在内存中)                        │
│  [user: Hello] [assistant: Hi] [user: ...] [assistant: ...]   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              Memory Consolidation (触发阈值后)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Long-term Memory                           │
├─────────────────────────────┬───────────────────────────────────┤
│      MEMORY.md            │           HISTORY.md               │
│  长期持久化的事实          │     可 grep 搜索的对话日志          │
│  - 用户偏好               │  [2026-03-04 14:30] USER: Hello    │
│  - 项目上下文             │  [2026-03-04 14:31] ASSISTANT: Hi  │
│  - 重要关系               │  ...                               │
└─────────────────────────────┴───────────────────────────────────┘
```

---

## 类：MemoryStore

### 初始化

```python
class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
```

**文件结构**：
```
workspace/
└── memory/
    ├── MEMORY.md    # 长期记忆（事实）
    └── HISTORY.md   # 对话历史（可 grep）
```

---

## 核心函数依赖关系

```
Session (消息累积)
       │
       ▼
consolidate()               # 记忆整合入口
       │
       ├─► read_long_term()           # 读取当前记忆
       ├─► LLM.chat()                 # 调用 LLM 进行摘要
       │
       ├─► append_history()           # 写入 HISTORY.md
       └─► write_long_term()           # 更新 MEMORY.md


get_memory_context()        # 供 ContextBuilder 调用
       │
       └─► read_long_term()           # 读取长期记忆
```

---

## 核心函数详解

### 1. `read_long_term()` - 读取长期记忆

```python
def read_long_term(self) -> str:
    if self.memory_file.exists():
        return self.memory_file.read_text(encoding="utf-8")
    return ""
```

**用途**：读取 MEMORY.md 内容

---

### 2. `write_long_term()` - 写入长期记忆

```python
def write_long_term(self, content: str) -> None:
    self.memory_file.write_text(content, encoding="utf-8")
```

**用途**：更新 MEMORY.md（由 LLM 整合后写入）

---

### 3. `append_history()` - 追加历史记录

```python
def append_history(self, entry: str) -> None:
    with open(self.history_file, "a", encoding="utf-8") as f:
        f.write(entry.rstrip() + "\n\n")
```

**特点**：
- 追加写入模式（append-only）
- 每次写入后添加两个换行符分隔条目
- 格式：`[YYYY-MM-DD HH:MM] 内容`

---

### 4. `get_memory_context()` - 获取记忆上下文

```python
def get_memory_context(self) -> str:
    long_term = self.read_long_term()
    return f"## Long-term Memory\n{long_term}" if long_term else ""
```

**用途**：供 `ContextBuilder.build_system_prompt()` 调用，将长期记忆注入 System Prompt

---

### 5. `consolidate()` - 记忆整合（核心）

```python
async def consolidate(
    self,
    session: Session,
    provider: LLMProvider,
    model: str,
    *,
    archive_all: bool = False,
    memory_window: int = 50,
) -> bool:
```

**触发条件**：

```python
# 1. archive_all = True (手动 /new 命令)
if archive_all:
    old_messages = session.messages

# 2. 自动触发 (消息数超过阈值)
else:
    keep_count = memory_window // 2  # 默认 25
    if len(session.messages) <= keep_count:
        return True  # 消息太少，跳过
    old_messages = session.messages[session.last_consolidated:-keep_count]
```

**整合流程**：

```
┌────────────────────────────────────────────────────────────────┐
│                    consolidate() 流程                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. 判断触发条件                                               │
│     ├─► archive_all (手动 /new)                               │
│     └─► 自动 (消息数 > memory_window/2)                        │
│                                                                │
│  2. 提取旧消息                                                 │
│     old_messages = session[last_consolidated : -keep_count]   │
│                                                                │
│  3. 格式化为文本                                               │
│     [2026-03-04 14:30] USER: Hello                            │
│     [2026-03-04 14:31] ASSISTANT: Hi [tools: read_file]      │
│                                                                │
│  4. 调用 LLM 进行摘要                                         │
│     ├─► system: "You are a memory consolidation agent..."     │
│     ├─► user: prompt with current memory + conversation       │
│     └─► tools: _SAVE_MEMORY_TOOL                              │
│                                                                │
│  5. 执行 tool call                                            │
│     ├─► history_entry: "2026-03-04 User discussed..."        │
│     └─► memory_update: "User prefers Python..."              │
│                                                                │
│  6. 写入文件                                                  │
│     ├─► append_history(entry)  → HISTORY.md                  │
│     └─► write_long_term(update) → MEMORY.md                  │
│                                                                │
│  7. 更新指针                                                  │
│     session.last_consolidated = len(session.messages) - keep_count│
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**LLM 工具调用**：

```python
_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]
```

---

## 触发时机

### 1. 自动触发（AgentLoop）

在 `agent/loop.py` 的 `_process_message()` 中：

```python
unconsolidated = len(session.messages) - session.last_consolidated
if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
    # 异步触发记忆整合
    _task = asyncio.create_task(_consolidate_and_unlock())
```

- 默认 `memory_window = 100`
- 当未整合消息数 ≥ 100 时触发
- 异步执行，不阻塞主流程

### 2. 手动触发（/new 命令）

```python
if cmd == "/new":
    # 立即归档所有消息
    await self._consolidate_memory(session, archive_all=True)
    session.clear()  # 清空当前会话
```

---

## 面试要点

1. **为什么选择两层记忆设计？**
   - MEMORY.md：事实类信息，每次都加载到 context
   - HISTORY.md：事件日志，不可加载，但可 grep 搜索
   - 分离关注点，减少 context 长度

2. **为什么用 LLM 驱动的记忆整合？**
   - 确定性行为：通过 tool call 让 LLM 决定保留什么
   - 可控性：LLM 自主判断哪些是重要事实
   - 一致性：格式统一，便于后续处理

3. **为什么 append-only？**
   - LLM cache 友好（追加不改变历史 hash）
   - 简化并发处理
   - 便于审计和回溯

4. **memory_window 的作用？**
   - 控制何时触发整合（默认 100 条消息）
   - 保留最近 50 条消息在 session 中

5. **Consolidation 失败怎么办？**
   - 返回 False，不更新 last_consolidated
   - 下次仍会尝试整合
   - 不阻塞当前对话

---

## 文件位置

- 源文件：`nanobot/agent/memory.py`
- 相关文件：
  - `nanobot/agent/loop.py` - 调用 consolidate()
  - `nanobot/agent/context.py` - 调用 get_memory_context()
  - `nanobot/session/manager.py` - Session 管理
