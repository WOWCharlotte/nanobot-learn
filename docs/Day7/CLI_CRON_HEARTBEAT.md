# CLI、Cron 与 Heartbeat 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 7 的补充材料

## 概述

Day 7 涵盖 nanobot 的进阶功能：
1. **CLI 命令行界面** - 与 Agent 交互
2. **Cron 定时任务** - 定时执行任务
3. **Heartbeat 心跳服务** - 主动唤醒 Agent

---

## 1. CLI 命令行界面

### 核心命令

```bash
nanobot onboard          # 初始化配置和工作区
nanobot agent            # 交互式聊天模式
nanobot agent -m "Hello" # 单消息模式
nanobot gateway          # 启动 Gateway（所有 Channel）
nanobot status           # 显示状态
```

### 架构

```
CLI Commands (Typer)
    │
    ├── onboard()        → 初始化配置
    ├── agent()          → 交互式/单消息模式
    ├── gateway()        → 启动所有 Channel
    ├── status()         → 显示状态
    ├── channels status  → Channel 状态
    ├── channels login   → 登录 Channel
    └── provider login   → OAuth 登录
```

### Agent 模式

```python
@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m"),
    session_id: str = typer.Option("cli:direct", "--session", "-s"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs"),
):
```

**两种模式**：

1. **单消息模式** (`-m "Hello"`) - 直接调用，返回结果
2. **交互式模式** - REPL 循环，支持历史记录

#### 单消息模式流程

```python
if message:
    # Single message mode — direct call, no bus needed
    async def run_once():
        with _thinking_ctx():
            response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
        _print_agent_response(response, render_markdown=markdown)
        await agent_loop.close_mcp()

    asyncio.run(run_once())
```

#### 交互式模式流程

```python
else:
    # Interactive mode — route through bus like other channels
    async def run_interactive():
        # 1. 启动 AgentLoop 作为后台任务
        bus_task = asyncio.create_task(agent_loop.run())

        # 2. 启动出站消息消费任务
        outbound_task = asyncio.create_task(_consume_outbound())

        # 3. REPL 循环读取用户输入
        while True:
            user_input = await _read_interactive_input_async()
            # 发布到 MessageBus
            await bus.publish_inbound(InboundMessage(...))

    asyncio.run(run_interactive())
```

#### 完整 Agent 模式架构图

```mermaid
sequenceDiagram
    participant User as 用户
    participant CLI as CLI (Typer)
    participant Bus as MessageBus
    participant Agent as AgentLoop
    participant LLM as LLM Provider

    alt 单消息模式 (-m "Hello")
        CLI->>Agent: process_direct(message)
        Agent->>LLM: chat()
        LLM-->>Agent: response
        Agent-->>CLI: response
        CLI->>User: 打印结果
    else 交互式模式
        User->>CLI: 输入消息
        CLI->>Bus: publish_inbound(InboundMessage)
        Bus-->>Agent: consume_inbound()
        Agent->>LLM: chat()
        LLM-->>Agent: response
        Agent->>Bus: publish_outbound()
        Bus-->>CLI: consume_outbound()
        CLI->>User: 打印响应
    end
```

#### AgentLoop.process_direct vs run()

| 方法 | 用途 | 调用方式 |
|------|------|----------|
| `process_direct()` | CLI 单消息模式 | 直接调用，不走 Bus |
| `run()` | Gateway/交互模式 | 后台任务，持续监听 Bus |

```python
# process_direct - 单次调用
async def process_direct(
    self,
    message: str,
    session_id: str = "cli:direct",
    on_progress: Callable | None = None,
) -> OutboundMessage | None:
    """Process a single message directly, bypassing the bus."""
    msg = InboundMessage(
        channel="cli",
        sender_id="cli",
        chat_id=session_id,
        content=message,
    )
    return await self._process_message(msg, on_progress=on_progress)

# run - 持续监听
async def run(self) -> None:
    """Run the agent loop, dispatching messages as tasks."""
    self._running = True

    while self._running:
        msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
        # 分发到 _process_message
        task = asyncio.create_task(self._dispatch(msg))
```

### Gateway 启动流程

```python
async def gateway(...):
    # 1. 加载配置
    config = load_config()

    # 2. 创建核心组件
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(workspace)

    # 3. 创建 Cron 服务
    cron = CronService(cron_store_path)

    # 4. 创建 Agent
    agent = AgentLoop(bus=bus, provider=provider, ...)

    # 5. 设置 Cron 回调
    cron.on_job = on_cron_job

    # 6. 创建 Heartbeat
    heartbeat = HeartbeatService(workspace=..., provider=provider, ...)

    # 7. 创建 Channel Manager
    channels = ChannelManager(config, bus)

    # 8. 启动所有服务
    await asyncio.gather(
        agent.run(),
        channels.start_all(),
    )
```

---

## 2. Cron 定时任务

### 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                      CronService                                  │
│                                                                  │
│  支持三种调度模式：                                               │
│  1. at     — 一次性任务                                         │
│  2. every  — 间隔任务                                           │
│  3. cron   — Cron 表达式                                        │
└─────────────────────────────────────────────────────────────────┘
```

### CronJob 数据结构

```python
@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""
    kind: Literal["at", "every", "cron"]
    at_ms: int | None = None           # 一次性任务的时间戳 (ms)
    every_ms: int | None = None        # 间隔任务的间隔 (ms)
    expr: str | None = None            # Cron 表达式 (如 "0 9 * * *")
    tz: str | None = None              # 时区

@dataclass
class CronPayload:
    """What to do when the job runs."""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""                  # 发送给 Agent 的消息内容
    deliver: bool = False              # 是否将响应投递到渠道
    channel: str | None = None         # 投递目标渠道 (如 "telegram")
    to: str | None = None              # 投递目标 (如手机号)

@dataclass
class CronJobState:
    """Runtime state of a job."""
    next_run_at_ms: int | None = None  # 下次执行时间 (ms)
    last_run_at_ms: int | None = None  # 上次执行时间 (ms)
    last_status: Literal["ok", "error", "skipped"] | None = None  # 上次状态
    last_error: str | None = None      # 上次错误信息

@dataclass
class CronJob:
    """A scheduled job."""
    id: str                            # 任务 ID
    name: str                          # 任务名称
    enabled: bool = True               # 是否启用
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0             # 创建时间
    updated_at_ms: int = 0             # 更新时间
    delete_after_run: bool = False     # 执行后是否删除 (一次性任务)

@dataclass
class CronStore:
    """Persistent store for cron jobs."""
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
```

#### 调度模式详解

| 模式 | kind | 参数 | 说明 |
|------|------|------|------|
| 一次性 | `at` | `at_ms` | 指定时间执行一次 |
| 间隔 | `every` | `every_ms` | 每隔固定时间执行 |
| Cron | `cron` | `expr`, `tz` | 标准 Cron 表达式 |

#### Payload 类型详解

| 类型 | 说明 |
|------|------|
| `agent_turn` | 作为用户消息发送给 Agent |
| `system_event` | 作为系统事件触发 |

### 使用方式

通过 `cron` 工具管理：

```python
# 添加定时任务
cron add every 1h "Reminder: check emails"

# 添加 cron 任务
cron add cron "0 9 * * *" "Morning summary"

# 列出任务
cron list

# 删除任务
cron delete <job_id>
```

### 定时任务流程图

```mermaid
sequenceDiagram
    participant User as 用户
    participant CronTool as CronTool
    participant CronService as CronService
    participant Store as CronStore<br/>(jobs.json)
    participant AgentLoop as AgentLoop
    participant LLM as LLM Provider
    participant Channel as Channel

    Note over User,Channel: 任务调度流程
    User->>CronTool: cron add every 1h "check emails"
    CronTool->>CronService: add_job()
    CronService->>Store: 保存任务到 jobs.json

    Note over CronService,Store: 启动阶段
    CronService->>Store: load_store() 加载任务
    CronService->>CronService: _recompute_next_runs() 计算下次执行时间
    CronService->>CronService: _arm_timer() 设置定时器

    loop 定时检查
        CronService->>CronService: _on_timer() 定时触发
        CronService->>CronService: 查找到期任务
        CronService->>CronService: _execute_job() 执行任务

        alt agent_turn 类型
            CronService->>AgentLoop: on_job(job) 回调
            AgentLoop->>LLM: chat(message)
            LLM-->>AgentLoop: response
            AgentLoop->>AgentLoop: process message
        else system_event 类型
            CronService->>AgentLoop: 触发系统事件
        end

        alt 需要投递响应
            AgentLoop->>Channel: bus.publish_outbound()
            Channel->>User: 发送响应消息
        end

        CronService->>CronService: 更新 job state
        CronService->>Store: save_store() 持久化
        CronService->>CronService: _arm_timer() 重新设置定时
    end
```

### CronService 核心方法流程

```mermaid
flowchart TD
    A[CronService 启动] --> B[_load_store 加载任务]
    B --> C[_recompute_next_runs 计算下次执行时间]
    C --> D[_arm_timer 设置定时器]
    D --> E{定时器触发}

    E --> F[_on_timer 处理到期任务]
    F --> G[查找到期任务: now >= next_run_at_ms]

    G --> H{遍历每个到期任务}
    H -->|执行任务| I[_execute_job]
    I --> J[调用 on_job 回调]
    J --> K{执行结果}
    K -->|成功| L[state.last_status = ok]
    K -->|失败| M[state.last_status = error]

    L --> N{任务类型}
    M --> N
    N -->|at 一次性| O[根据 delete_after_run 删除或禁用]
    N -->|every/cron| P[计算下次执行时间]
    O --> Q[save_store 持久化]
    P --> Q
    Q --> R[_arm_timer 重新设置定时]
    R --> E

    I -->|无需投递| Q
```

### 执行 job 状态流转

```mermaid
stateDiagram-v2
    [*] --> Enabled: 用户添加任务
    Enabled --> Running: 定时器触发
    Running --> Completed_OK: 执行成功
    Running --> Completed_Error: 执行失败
    Completed_OK --> Enabled: every/cron 模式
    Completed_OK --> Disabled: at 模式 (delete_after_run=false)
    Completed_OK --> [*]: at 模式 (delete_after_run=true)
    Completed_Error --> Enabled: 保留任务等待下次
    Disabled --> [*]: 任务结束
```

### 实现原理

```python
class CronService:
    def __init__(self, store_path: Path, on_job: Callable | None = None):
        self.store_path = store_path
        self.on_job = on_job  # 回调函数

    async def start(self) -> None:
        """启动定时任务服务"""
        self._running = True
        self._timer_task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        """主循环：检查并执行到期的任务"""
        while self._running:
            await asyncio.sleep(1)  # 每秒检查
            now = _now_ms()

            for job in self._get_due_jobs(now):
                if self.on_job:
                    asyncio.create_task(self.on_job(job))

    def _compute_next_run(self, schedule: CronSchedule, now_ms: int) -> int | None:
        """计算下次执行时间"""
        if schedule.kind == "at":
            return schedule.at_ms if schedule.at_ms > now_ms else None
        if schedule.kind == "every":
            return now_ms + schedule.every_ms
        if schedule.kind == "cron":
            # 使用 croniter 计算
            return croniter(schedule.expr, now).get_next()
```

---

## 3. Heartbeat 心跳服务

### 核心概念

Heartbeat 是 nanobot 的**主动唤醒机制**，让 Agent 定期检查是否有任务需要执行。

```
┌─────────────────────────────────────────────────────────────────┐
│                    HeartbeatService                              │
│                                                                  │
│  Phase 1 (决策): 读取 HEARTBEAT.md → LLM 决定 skip/run        │
│                                                                  │
│  Phase 2 (执行): 仅当 Phase 1 返回 "run" 时执行任务           │
└─────────────────────────────────────────────────────────────────┘
```

### HEARTBEAT.md 格式

```markdown
# Active Tasks

## Morning Review (9:00 AM)
- Check calendar for meetings
- Review pending PRs

## Hourly Checks
- Monitor CI pipeline status
- Check error logs
```

### 实现原理

```python
class HeartbeatService:
    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable | None = None,  # 执行回调
        on_notify: Callable | None = None,    # 通知回调
        interval_s: int = 30 * 60,          # 默认 30 分钟
        enabled: bool = True,
    ):
        ...

    async def start(self) -> None:
        """启动心跳服务"""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def _tick(self) -> None:
        """单次心跳"""
        # 1. 读取 HEARTBEAT.md
        content = self._read_heartbeat_file()
        if not content:
            return

        # 2. Phase 1: 决策
        action, tasks = await self._decide(content)

        if action != "run":
            return  # 跳过

        # 3. Phase 2: 执行
        if self.on_execute:
            response = await self.on_execute(tasks)

            # 4. 通知用户
            if self.on_notify:
                await self.on_notify(response)

    async def _decide(self, content: str) -> tuple[str, str]:
        """让 LLM 决定是否执行任务"""
        response = await self.provider.chat(
            messages=[
                {"role": "system", "content": "You are a heartbeat agent..."},
                {"role": "user", "content": f"Review HEARTBEAT.md and decide:\n{content}"}
            ],
            tools=_HEARTBEAT_TOOL,  # heartbeat 工具
            model=self.model,
        )

        # 解析工具调用结果
        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("tasks", "")
```

### heartbeat 工具

```python
_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "Report heartbeat decision after reviewing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                    },
                    "tasks": {
                        "type": "string",
                        "description": "Summary of active tasks (required for run)",
                    },
                },
                "required": ["action"],
            },
        },
    }
]
```

---

## 整体架构

```mermaid
flowchart TB
    subgraph CLI["CLI 命令行"]
        direction TB
        C1["nanobot onboard"]
        C2["nanobot agent"]
        C3["nanobot gateway"]
    end

    subgraph Core["核心组件"]
        direction TB
        Bus["MessageBus"]
        Bus1["inbound queue"]
        Bus2["outbound queue"]
        Bus --- Bus1
        Bus --- Bus2
    end

    subgraph AgentCore["Agent 核心"]
        direction LR
        Agent["AgentLoop"]
        LLM["LLM Provider"]
        Tools["Tool Registry"]
        Agent --> LLM
        Agent --> Tools
    end

    subgraph Channels["Channels"]
        direction LR
        TG["Telegram"]
        DC["Discord"]
        WA["WhatsApp"]
        FS["Feishu"]
        QQ["QQ"]
        SL["Slack"]
        Others["..."]
    end

    subgraph Scheduler["调度服务"]
        direction LR
        Cron["CronService"]
        CronJobs["Cron Jobs<br/>(jobs.json)"]
        HB["HeartbeatService"]
        HBFile["HEARTBEAT.md"]
        Cron --- CronJobs
        HB --- HBFile
    end

    %% CLI 关系
    C1 -->|"初始化"| Config["配置系统"]
    C2 -->|"单消息/交互"| Agent
    C3 --> Core

    %% 消息流向
    Channels -->|"消息"| Bus1
    Bus1 --> Agent
    Agent --> Bus2
    Bus2 --> Channels

    %% Agent 与调度
    Agent --> Cron
    Agent --> HB
    Cron --> Agent
    HB --> Agent
    HB --> LLM

    %% 样式
    classDef primary fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef secondary fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    classDef tertiary fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    class CLI,Core,AgentCore,Channels,Scheduler primary;
    class Bus,Agent,Cron,HB secondary;
    class TG,DC,WA,CronJobs,HBFile tertiary;
```

### 组件说明

| 组件 | 说明 |
|------|------|
| CLI | 命令行入口，支持 onboard/agent/gateway |
| MessageBus | 消息队列，解耦 Channel 和 Agent |
| AgentLoop | 核心处理引擎 |
| LLM Provider | 模型调用（OpenAI/Anthropic/DeepSeek...） |
| Tool Registry | 工具注册（shell/filesystem/web/mcp...） |
| Channels | 平台接入（Telegram/Discord/WhatsApp...） |
| CronService | 定时任务服务 |
| HeartbeatService | 心跳主动唤醒服务 |

### 数据流

```mermaid
sequenceDiagram
    participant CLI
    participant Bus
    participant Agent
    participant LLM
    participant Tools
    participant Channels
    participant Cron
    participant HB

    Note over CLI,Channels: nanobot gateway 模式

    %% CLI 启动
    CLI->>Bus: 创建 MessageBus
    CLI->>Agent: 创建 AgentLoop
    CLI->>Channels: 创建 ChannelManager
    CLI->>Cron: 创建 CronService
    CLI->>HB: 创建 HeartbeatService

    par 并行运行
        Agent->>Bus: consume_inbound() 监听消息
        Channels->>Bus: publish_inbound() 推送消息
        Cron->>Cron: 定时检查并触发
        HB->>LLM: 定期决策
    end

    %% 消息处理
    Bus->>Agent: 消费 inbound
    Agent->>LLM: chat()
    loop 工具调用
        Agent->>Tools: 执行工具
        Tools-->>Agent: 工具结果
    end
    LLM-->>Agent: response
    Agent->>Bus: publish_outbound()

    Bus-->>Channels: 消费 outbound
    Channels->>Channels: 发送到平台

    %% 定时任务
    Cron->>Agent: on_job 回调
    Agent->>Bus: publish_outbound()
    Bus-->>Channels: 投递响应
```

---

## 面试要点

1. **CLI 两种模式的区别？**
   - 单消息：直接调用 `process_direct()`
   - 交互式：通过 MessageBus 路由

2. **Cron 的三种调度模式？**
   - `at`: 一次性任务
   - `every`: 间隔任务
   - `cron`: Cron 表达式

3. **Heartbeat 的两阶段设计？**
   - Phase 1: LLM 决策（通过工具调用）
   - Phase 2: 仅当决策为 "run" 时执行

4. **为什么用工具调用而不是自由文本？**
   - 确定性：避免解析错误
   - 结构化：action + tasks 清晰

5. **Gateway 启动流程？**
   - 创建组件 → 设置回调 → 启动服务 → asyncio.gather

---

## 文件位置

- 源文件：
  - `nanobot/cli/commands.py` - CLI 命令
  - `nanobot/cron/service.py` - Cron 服务
  - `nanobot/cron/types.py` - Cron 数据类型
  - `nanobot/heartbeat/service.py` - Heartbeat 服务
- 相关文件：
  - `nanobot/agent/loop.py` - AgentLoop
  - `nanobot/channels/manager.py` - ChannelManager
  - `nanobot/bus/queue.py` - MessageBus
