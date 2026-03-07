# Memory System 深入解析

> 本文档是 [LEARNING_PLAN.md](../../LEARNING_PLAN.md) Day 3 的补充材料

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

**Less is More的设计思想**<br>
cited by [nanobot 记忆系统：少即是多](https://github.com/HKUDS/nanobot/discussions/566)
```
# **🐈 nanobot 记忆系统：少即是多 #566**


李小龙曾说：

> “不是每日增加，而是每日减少。砍掉那些不必要的东西。”

大多数 AI 智能体的记忆系统都在追求同样的模式：向量数据库、嵌入模型、语义检索、分块策略、重排序流水线……他们试图构建一个看起来像人类大脑的大脑。但智能体不是人类。它们不需要“回忆”——它们需要的是**寻找**。

> “吸收有用的，丢弃无用的，并加入你特有的东西。”

所以我们问自己：能够真正发挥作用的最简单的记忆系统是什么样的？

---

### **系统架构**

只需两个文件。仅此而已。

| 文件 | 角色 | 访问方式 |
| :--- | :--- | :--- |
| `MEMORY.md` | 长期事实（用户是谁、偏好、项目背景） | 始终包含在系统提示词中 |
| `HISTORY.md` | 仅追加的事件日志（带有时间戳的对话摘要） | 按需使用 `grep` 检索 |

没有向量数据库。没有嵌入模型。没有 RAG 流水线。没有外部依赖。

**为什么对于智能体记忆来说，grep 优于 RAG：**

1.  **确定性** —— 同样的查询，每次都能得到相同的结果。没有嵌入漂移，无需调整相似度阈值。
2.  **可审计** —— 打开文件，用眼睛就能阅读。试试对向量数据库这么做。
3.  **零成本** —— 没有嵌入 API 调用费用，无需数据库托管，没有索引维护开销。
4.  **可组合** —— `grep -i "user preference" HISTORY.md` 在任何 Shell、任何操作系统、任何上下文中都能运行。

Claude Code 也采用了同样的方法 —— 没有 RAG，只有文本文件和 grep 搜索。如果这对于 Anthropic 自家的编码智能体来说足够好，那么对我们来说也足够了。

---

### **自动整合 (Auto-Consolidation)**

当对话增长超过可配置的阈值（`memoryWindow`）时，nanobot 会自动执行：

1.  **总结旧消息** → 追加到 `HISTORY.md`。
2.  **提取新的长期事实** → 更新 `MEMORY.md`。
3.  **修剪会话** → 保留最近的上下文。

智能体不需要“决定”去记住。它自然而然地发生。就像呼吸一样。

**“像水一样吧，我的朋友。”** 水不会决定去填满杯子，它只是流淌。nanobot 的记忆不需要智能体去管理——它会自动适应对话的形状。

---

### **数据指标**

*   **记忆模块**：110 行 → 30 行（减少了 73%）
*   **新增外部依赖**：0
*   **配置项**：一个数字（`memoryWindow: 50`）

更少的代码，更少的 Bug，更高的可靠性。

我们相信最好的智能体基础设施是那种让你忘记它存在的东西。如果你对这种方法感兴趣，请查看 PR #565 或亲自尝试 —— 运行 `nanobot onboard` 开始聊天。

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

6. **为什么选择 grep 而不是 RAG/向量数据库？**
   - **确定性**：同样查询每次结果相同，没有嵌入漂移，无需调参
   - **可审计**：直接打开文件阅读，向量数据库无法做到
   - **零成本**：无嵌入 API 费用，无数据库托管，无索引维护
   - **可组合**：grep 在任何 Shell、OS、上下文中都能运行
   - Claude Code 也采用同样方法（无 RAG，只有文本文件和 grep）

7. **记忆整合的触发条件是什么？**
   - **自动触发**：`unconsolidated >= memory_window`（默认100条消息）
   - **手动触发**：用户发送 `/new` 命令，立即归档所有消息
   - **keep_count**：`memory_window // 2` = 50条，保留最近50条在 session 中

8. **整合过程中保留多少条消息在 session 中？**
   - `keep_count = memory_window // 2` = 50条
   - 整合范围：`session.messages[last_consolidated : -keep_count]`
   - 即：跳过已整合的消息，保留最近50条在活跃 session 中
   - 更新 `session.last_consolidated` 指针

9. **如何保证整合过程的原子性？**
   - nanobot 采用乐观策略：
     - 整合失败 → 返回 False，不更新 `last_consolidated`
     - 下次继续尝试整合，不会丢失数据
     - 不使用复杂的事务锁机制，简化代码
   - LLM 调用可能失败（如网络超时），通过 try-except 捕获

10. **HISTORY.md 的格式是什么？为什么这样设计？**
    - 格式：`[YYYY-MM-DD HH:MM] 内容`
    - 设计要点：
      - 时间戳便于 grep 搜索和回溯
      - 追加写入（append-only）保证 LLM cache 友好
      - 两个换行符分隔条目，便于阅读
      - 不加载到 context，仅按需 grep 搜索

11. **记忆整合会调用多少次 LLM？**
    - **一次**：调用 LLM 进行摘要，返回 tool call
    - 工具 `_SAVE_MEMORY_TOOL` 包含两个字段：
      - `history_entry`：追加到 HISTORY.md 的摘要
      - `memory_update`：更新后的 MEMORY.md 内容
    - 通过 tool call 保证写入的一致性

12. **与 RAG 系统相比的优劣？**
    - **优势**：简单、零外部依赖、无向量计算成本、确定性
    - **劣势**：
      - 语义搜索能力弱（grep 仅支持关键词）
      - 无法做相似度检索
      - 大型历史文件读取成本增加
    - **适用场景**：个人 AI 助手（数据量小、简单）
    - **不适用场景**：企业知识库（数据量大、需要语义搜索）

13. **记忆丢失的风险和防护？**
    - **风险**：整合过程中程序崩溃导致 `last_consolidated` 未更新
    - **防护**：
      - 整合成功后更新 `last_consolidated`
      - 失败则不更新，下次继续尝试
      - MEMORY.md 和 HISTORY.md 追加写入，崩溃不损坏
    - **建议**：定期备份 workspace 目录

14. **多会话场景下的记忆隔离？**
    - 每个 session 有独立的 `last_consolidated` 指针
    - MEMORY.md 和 HISTORY.md 是共享的（跨会话）
    - LLM 决定哪些事实写入 MEMORY.md（全局记忆）
    - 适合单用户多会话场景
    - 多用户场景需考虑隔离（可通过 workspace 目录隔离）

15. **记忆压缩率如何？**
    - 取决于对话内容
    - 通常：100条消息 → 1-2条 HISTORY + 若干条 MEMORY
    - 示例：100条消息约 10KB → 摘要后约 500-1KB
    - 压缩比约 10-20x

16. **如何审计和回溯记忆？**
    - 直接查看 `~/.nanobot/workspace/memory/` 目录
    - `MEMORY.md` 包含所有长期事实
    - `HISTORY.md` 可 grep 搜索历史
    - 示例：`grep -i "python" ~/.nanobot/workspace/memory/HISTORY.md`
    - 无数据库锁，可直接文本编辑器打开

---

## 文件位置

- 源文件：`nanobot/agent/memory.py`
- 相关文件：
  - `nanobot/agent/loop.py` - 调用 consolidate()
  - `nanobot/agent/context.py` - 调用 get_memory_context()
  - `nanobot/session/manager.py` - Session 管理
