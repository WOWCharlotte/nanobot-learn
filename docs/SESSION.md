# Session System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 3 的补充材料

## 概述

`session/manager.py` 是 nanobot 的 **会话管理系统**（213行），负责：
1. 会话数据模型（Session）
2. 会话持久化（JSONL 格式）
3. 会话缓存管理

---

## 核心概念

```
Session (会话)
├── key: str                    # channel:chat_id 标识
├── messages: list              # 消息列表
├── created_at: datetime        # 创建时间
├── updated_at: datetime        # 更新时间
├── metadata: dict              # 元数据
└── last_consolidated: int      # 已整合的消息数

SessionManager (会话管理器)
├── workspace                  # 工作目录
├── sessions_dir               # 会话文件目录
├── _cache: dict              # 内存缓存
└── 方法: get_or_create, save, load, list_sessions
```

---

## 类：Session

### 数据结构

```python
@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already consolidated to files
```

**关键设计**：
- **Append-only**：消息只追加，不修改（LLM cache 友好）
- **last_consolidated**：记录已整合到 MEMORY.md/HISTORY.md 的消息数

---

## 类：SessionManager

### 初始化

```python
class SessionManager:
    """Manages conversation sessions. Sessions are stored as JSONL files."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = Path.home() / ".nanobot" / "sessions"
        self._cache: dict[str, Session] = {}
```

**文件结构**：
```
workspace/
└── sessions/
    ├── cli_direct.jsonl
    ├── telegram_123456.jsonl
    └── discord_987654321.jsonl
```

**JSONL 格式**：
```jsonl
{"_type": "metadata", "key": "cli:direct", "created_at": "2026-03-04T10:00:00", "updated_at": "2026-03-04T10:30:00", "metadata": {}, "last_consolidated": 50}
{"role": "user", "content": "Hello", "timestamp": "2026-03-04T10:00:01"}
{"role": "assistant", "content": "Hi!", "timestamp": "2026-03-04T10:00:02"}
```

---

## 核心函数依赖关系

```
AgentLoop._process_message()
        │
        ▼
SessionManager.get_or_create(key)
        │
        ├─► _load()              # 从磁盘加载
        │       │
        │       └─► 尝试迁移旧会话
        │
        └─► Session.get_history()  # 获取历史消息
                │
                └─► 返回未整合的消息（对齐到用户回合）

处理完成后:
        │
        ▼
AgentLoop._save_turn()         # 保存新消息
        │
        ▼
SessionManager.save(session)    # 持久化到磁盘
```

---

## 核心函数详解

### 1. `get_or_create()` - 获取或创建会话

```python
def get_or_create(self, key: str) -> Session:
    """Get an existing session or create a new one."""
    if key in self._cache:
        return self._cache[key]

    session = self._load(key)
    if session is None:
        session = Session(key=key)

    self._cache[key] = session
    return session
```

**流程**：
```
1. 检查内存缓存
   └─► 存在 → 直接返回

2. 尝试从磁盘加载
   └─► 不存在 → 创建新 Session

3. 加入缓存并返回
```

---

### 2. `_load()` - 加载会话

```python
def _load(self, key: str) -> Session | None:
    """Load a session from disk."""
    path = self._get_session_path(key)

    # 1. 检查旧路径迁移
    if not path.exists():
        legacy_path = self._get_legacy_session_path(key)
        if legacy_path.exists():
            shutil.move(legacy_path, path)  # 自动迁移

    # 2. 读取 JSONL
    with open(path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("_type") == "metadata":
                # 提取元数据
                metadata = data.get("metadata", {})
                created_at = datetime.fromisoformat(data["created_at"])
                last_consolidated = data.get("last_consolidated", 0)
            else:
                # 消息
                messages.append(data)

    return Session(key, messages, created_at, metadata, last_consolidated)
```

**特点**：
- 自动迁移旧路径的会话
- 解析 JSONL 第一行作为 metadata
- 支持legacy路径（~/.nanobot/sessions/）

---

### 3. `save()` - 保存会话

```python
def save(self, session: Session) -> None:
    """Save a session to disk."""
    path = self._get_session_path(session.key)

    with open(path, "w", encoding="utf-8") as f:
        # 1. 写入 metadata
        metadata_line = {
            "_type": "metadata",
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "metadata": session.metadata,
            "last_consolidated": session.last_consolidated
        }
        f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")

        # 2. 写入所有消息
        for msg in session.messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    self._cache[session.key] = session
```

**特点**：
- 每次保存都重写整个文件
- 第一行是 metadata
- 后续行是消息（JSONL）
- **Append-only 设计**：只追加新消息，不修改历史

---

### 4. `get_history()` - 获取历史

```python
def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
    """Return unconsolidated messages for LLM input, aligned to a user turn."""
    # 1. 提取未整合的消息
    unconsolidated = self.messages[self.last_consolidated:]
    sliced = unconsolidated[-max_messages:]

    # 2. 对齐到用户回合（防止孤立的 tool_result）
    for i, m in enumerate(sliced):
        if m.get("role") == "user":
            sliced = sliced[i:]
            break

    # 3. 提取必要字段
    out = []
    for m in sliced:
        entry = {"role": m["role"], "content": m.get("content", "")}
        for k in ("tool_calls", "tool_call_id", "name"):
            if k in m:
                entry[k] = m[k]
        out.append(entry)
    return out
```

**关键设计**：
- 只返回 `last_consolidated` 之后的未整合消息
- 最多返回 `max_messages` 条
- **对齐到用户回合**：防止孤立的 tool_result（没有对应的 tool_call）

---

### 5. `clear()` - 清空会话

```python
def clear(self) -> None:
    """Clear all messages and reset session to initial state."""
    self.messages = []
    self.last_consolidated = 0
    self.updated_at = datetime.now()
```

**触发时机**：用户发送 `/new` 命令后

---

### 6. `list_sessions()` - 列出所有会话

```python
def list_sessions(self) -> list[dict[str, Any]]:
    """List all sessions."""
    sessions = []

    for path in self.sessions_dir.glob("*.jsonl"):
        with open(path, encoding="utf-8") as f:
            first_line = f.readline().strip()
            data = json.loads(first_line)
            if data.get("_type") == "metadata":
                sessions.append({
                    "key": key,
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "path": str(path)
                })

    return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
```

---

## 消息格式

```python
# 用户消息
{
    "role": "user",
    "content": "Hello",
    "timestamp": "2026-03-04T10:00:00"
}

# 助手消息
{
    "role": "assistant",
    "content": "Hi!",
    "timestamp": "2026-03-04T10:00:01"
}

# 工具调用
{
    "role": "assistant",
    "content": None,
    "tool_calls": [...],
    "timestamp": "2026-03-04T10:00:02"
}

# 工具结果
{
    "role": "tool",
    "tool_call_id": "call_xxx",
    "name": "read_file",
    "content": "file content...",
    "timestamp": "2026-03-04T10:00:03"
}
```

---

## 面试要点

1. **为什么用 JSONL 格式？**
   - 易于人类阅读
   - 追加写入效率高
   - 支持流式读取

2. **为什么 append-only？**
   - LLM cache 友好（消息 hash 不变）
   - 简化并发处理
   - 便于审计

3. **last_consolidated 的作用？**
   - 标记哪些消息已整合到 MEMORY.md
   - 避免重复整合
   - 支持增量整合

4. **为什么需要对齐到用户回合？**
   - 防止孤立的 tool_result
   - 确保 LLM 看到完整的 tool_call → tool_result 对

5. **内存缓存策略？**
   - `get_or_create()` 时加载到缓存
   - `save()` 时更新缓存
   - `invalidate()` 手动失效

---

## 文件位置

- 源文件：`nanobot/session/manager.py`
- 相关文件：
  - `nanobot/agent/loop.py` - 调用 SessionManager
  - `nanobot/agent/memory.py` - 读取 last_consolidated
  - `nanobot/agent/context.py` - 接收 history
