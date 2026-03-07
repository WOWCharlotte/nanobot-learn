# Session System 深入解析

> 本文档是 [LEARNING_PLAN.md](../../LEARNING_PLAN.md) Day 3 的补充材料

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

6. **会话 key 的格式是什么？如何实现多平台隔离？**
   - 格式：`channel:chat_id`（如 `telegram:123456789`）
   - 每个 Channel + 用户 ID 组合对应一个独立会话
   - 多平台隔离：Telegram 和 Discord 用户相同 ID 不会混淆
   - 适合场景：单用户在多平台的会话管理

7. **会话文件的命名规则？**
   - 文件名：`{channel}_{chat_id}.jsonl`（如 `telegram_123456789.jsonl`）
   - 特殊：`cli_direct.jsonl`（命令行直接会话）
   - 路径：`workspace/sessions/` 目录

8. **会话的持久化时机？**
   - 每轮对话结束后自动保存（在 `AgentLoop._save_turn()` 中调用）
   - 不是实时写入，而是批量写入
   - 优势：减少 I/O 次数，提升性能
   - 风险：程序异常退出可能丢失少量消息

9. **会话加载时的自动迁移机制？**
   - 自动检查旧路径 `~/.nanobot/sessions/` 是否存在
   - 如果存在，自动移动到新路径 `workspace/sessions/`
   - 兼容旧版本升级，无需手动迁移
   - 迁移是一次性的，之后直接读取新路径

10. **为什么 save() 时每次都重写整个文件？**
    - 实现简单，无需维护文件指针
    - JSONL 追加写入虽然高效，但读取时需要扫描整个文件
    - 权衡：写入次数少（每轮一次），读取次数多（每次加载）
    - 适合场景：个人 AI 助手，请求频率不高

11. **会话缓存会无限增长吗？**
    - 会话缓存是懒加载的，只有被访问过的会话才会进入缓存
    - 没有显式的缓存淘汰机制
    - 生产环境建议：定期重启或手动调用 `invalidate()` 清理
    - 内存占用：每个会话约几 KB~几 MB，取决于对话长度

12. **如何处理超长会话的性能问题？**
    - `get_history(max_messages=500)` 限制返回消息数
    - 超过限制时只返回最近的 500 条
    - 配合记忆整合（consolidate）定期压缩历史
    - LLM 调用成本与消息数成正比，需权衡

13. **会话消息包含哪些字段？**
    - `role`：user/assistant/tool
    - `content`：消息内容（文本）
    - `timestamp`：ISO 格式时间戳
    - `tool_calls`：工具调用列表（仅 assistant）
    - `tool_call_id`：工具调用 ID（仅 tool）
    - `name`：工具名称（仅 tool）

14. **为什么工具结果需要对齐到用户回合？**
    - 示例：用户发送消息 → LLM 调用工具 → 工具返回结果
    - 如果只保留最后几条，可能丢失 tool_call，只保留 tool_result
    - LLM 看不到 tool_call 会导致上下文不完整
    - 对齐逻辑：找到最近的用户消息作为起点，返回该消息之后的所有内容

15. **多用户并发场景下的会话管理？**
    - SessionManager 使用内存字典 `_cache` 存储会话
    - 无锁设计，依赖 Python GIL
    - 每个 Channel 消息通过 `session_key` 路由到对应会话
    - 不同用户的消息在 AgentLoop 中通过 `_processing_lock` 串行处理
    - 适合场景：多用户并发访问，但单用户内串行

16. **会话清理机制？**
    - 目前没有自动清理机制
    - `/new` 命令只清空当前会话的内存消息，不删除文件
    - 需要手动删除 `sessions/*.jsonl` 文件
    - 建议：定期归档或删除不活跃的会话文件

17. **会话的 created_at 和 updated_at 用途？**
    - `created_at`：会话创建时间，用于排序和展示
    - `updated_at`：最后更新时间，每次保存时更新
    - `list_sessions()` 按 `updated_at` 倒序排列

---

## 文件位置

- 源文件：`nanobot/session/manager.py`
- 相关文件：
  - `nanobot/agent/loop.py` - 调用 SessionManager
  - `nanobot/agent/memory.py` - 读取 last_consolidated
  - `nanobot/agent/context.py` - 接收 history
