# Channel System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 6 的补充材料

## 概述

nanobot 的 **Channel 系统**是聊天平台集成层，负责：
1. 接收各平台消息
2. 发送响应到各平台
3. 消息格式转换

目前支持 **11 个平台**！

---

## 支持的 Channel

| Channel | 协议 | 说明 |
|---------|------|------|
| Telegram | Bot API | 长轮询，无需公网 |
| Discord | Gateway | Discord 机器人 |
| WhatsApp | WebSocket | WhatsApp Business API |
| Feishu | WebSocket | 飞书/Lark |
| QQ | botpy SDK | QQ 机器人 |
| DingTalk | Stream | 钉钉 Stream 模式 |
| Slack | Socket Mode | Slack 机器人 |
| Email | IMAP/SMTP | 邮件收发 |
| Matrix | Client-Server | Matrix 协议，支持 E2EE |
| Mochat | API | 莫愁机器人 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      ChannelManager                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ channels: dict[str, BaseChannel]                        │   │
│  │  - telegram    → TelegramChannel                        │   │
│  │  - discord     → DiscordChannel                        │   │
│  │  - whatsapp    → WhatsAppChannel                       │   │
│  │  - ...                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  职责：                                                        │
│  1. 初始化所有启用的 Channel                                   │
│  2. 启动/停止所有 Channel                                      │
│  3. 路由 outbound 消息                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MessageBus                                 │
│                                                                 │
│   inbound_queue  ◄────── Channel._handle_message()            │
│                                                                  │
│   outbound_queue ◄───── AgentLoop._process_message()          │
│                              │                                  │
│                              ▼                                  │
│                    ChannelManager._dispatch_outbound()          │
│                              │                                  │
│                              ▼                                  │
│                    Channel.send() ──────────► 用户              │
└─────────────────────────────────────────────────────────────────┘
```

---

## BaseChannel 抽象基类

```python
class BaseChannel(ABC):
    """Abstract base class for chat channel implementations."""

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start the channel and begin listening for messages."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through this channel."""
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """Check if sender is permitted. Empty list → deny all; "*" → allow all."""
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            return False
        if "*" in allow_list:
            return True
        return sender_id in allow_list

    async def _handle_message(self, sender_id: str, chat_id: str, content: str, ...) -> None:
        """Handle incoming message, check permissions, forward to bus."""
        if not self.is_allowed(sender_id):
            return
        msg = InboundMessage(channel=self.name, sender_id=..., chat_id=..., content=...)
        await self.bus.publish_inbound(msg)
```

---

## ChannelManager

```python
class ChannelManager:
    """Manages chat channels and coordinates message routing."""

    def __init__(self, config: Config, bus: MessageBus):
        self.channels: dict[str, BaseChannel] = {}
        self._init_channels()  # 根据配置初始化启用的 Channel

    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        if self.config.channels.telegram.enabled:
            self.channels["telegram"] = TelegramChannel(...)

        if self.config.channels.discord.enabled:
            self.channels["discord"] = DiscordChannel(...)

        # ... 其他 Channel

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        # 启动 outbound 分发器
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # 启动所有 Channel
        for name, channel in self.channels.items():
            await channel.start()

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        while True:
            msg = await self.bus.consume_outbound()
            channel = self.channels.get(msg.channel)
            if channel:
                await channel.send(msg)
```

---

## Channel 实现示例：Telegram

```python
class TelegramChannel(BaseChannel):
    name = "telegram"

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        # 1. 构建 Application
        self._app = Application.builder().token(self.config.token).build()

        # 2. 添加处理器
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._forward_command))
        self._app.add_handler(MessageHandler(filters.TEXT, self._on_message))

        # 3. 启动长轮询
        await self._app.run_polling()

    async def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        if self._app:
            await self._app.stop()

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to Telegram."""
        # Markdown → HTML 转换
        html = _markdown_to_telegram_html(msg.content)

        # 分片发送（最大 4096 字符）
        chunks = _split_message(html)
        for chunk in chunks:
            await self._bot.send_message(
                chat_id=msg.chat_id,
                text=chunk,
                parse_mode="HTML"
            )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming message."""
        await self._handle_message(
            sender_id=str(update.message.from_user.id),
            chat_id=str(update.message.chat_id),
            content=update.message.text,
        )
```

---

## 消息流程

### Inbound（用户 → Agent）

```
1. 用户在 Telegram 发送消息
       │
       ▼
2. Telegram Bot API 接收到 Update
       │
       ▼
3. TelegramChannel._on_message()
       │
       ▼
4. is_allowed() 检查权限
       │
       ▼
5. _handle_message() 创建 InboundMessage
       │
       ▼
6. bus.publish_inbound() 发送到队列
       │
       ▼
7. AgentLoop._process_message() 处理
```

### Outbound（Agent → 用户）

```
1. AgentLoop 处理完成
       │
       ▼
2. bus.publish_outbound() 发送 OutboundMessage
       │
       ▼
3. ChannelManager._dispatch_outbound() 分发
       │
       ▼
4. 查找对应的 Channel
       │
       ▼
5. Channel.send() 发送到平台
       │
       ▼
6. 用户收到消息
```

---

## 权限控制

每个 Channel 支持 `allow_from` 配置：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "xxx",
      "allow_from": ["123456789", "987654321"]
    }
  }
}
```

- `[]` (空) → 拒绝所有
- `["*"]` → 允许所有
- `["id1", "id2"]` → 只允许指定用户

---

## 添加新 Channel

1. **创建 Channel 类**（继承 BaseChannel）
   ```python
   class NewChannel(BaseChannel):
       name = "newchannel"

       async def start(self) -> None: ...
       async def stop(self) -> None: ...
       async def send(self, msg: OutboundMessage) -> None: ...
   ```

2. **在 ChannelManager 中注册**
   ```python
   if self.config.channels.newchannel.enabled:
       self.channels["newchannel"] = NewChannel(...)
   ```

3. **在 Config 中添加配置**
   - 在 `config/schema.py` 添加 `NewChannelConfig`

---

## 面试要点

1. **Channel 的核心职责？**
   - 消息接收（start + _handle_message）
   - 消息发送（send）
   - 权限控制（is_allowed）

2. **ChannelManager 的作用？**
   - 统一管理所有 Channel
   - 路由 outbound 消息
   - 启动/停止协调

3. **消息流程？**
   - Inbound：平台 → _handle_message → MessageBus → AgentLoop
   - Outbound：AgentLoop → MessageBus → ChannelManager → Channel.send() → 平台

4. **为什么用 MessageBus 解耦？**
   - Channel 和 Agent 独立
   - 支持多个 Channel
   - 异步处理

5. **如何添加新 Channel？**
   - 继承 BaseChannel
   - 实现 start/stop/send
   - 在 ChannelManager 注册
   - 在 Config 添加配置

---

## 文件位置

- 源文件：
  - `nanobot/channels/base.py` - BaseChannel 基类
  - `nanobot/channels/manager.py` - Channel 管理器
  - `nanobot/channels/telegram.py` - Telegram 实现
  - `nanobot/channels/discord.py` - Discord 实现
  - `nanobot/channels/email.py` - Email 实现
  - 其他 Channel 实现...
- 相关文件：
  - `nanobot/bus/queue.py` - MessageBus
  - `nanobot/bus/events.py` - 消息事件
  - `nanobot/config/schema.py` - Channel 配置
