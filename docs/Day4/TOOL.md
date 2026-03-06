# Tool System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 4 的补充材料

## 概述

nanobot 的 **Tool 系统** 是 Agent 与外部世界交互的桥梁，包含：
1. **Tool 抽象基类** - 统一的接口定义
2. **Tool Registry** - 工具注册和管理
3. **内置工具** - 文件操作、Shell 执行、网页搜索等

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        ToolRegistry                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ _tools: dict[str, Tool]                                 │   │
│  │  - read_file    → ReadFileTool                          │   │
│  │  - write_file   → WriteFileTool                         │   │
│  │  - edit_file    → EditFileTool                          │   │
│  │  - list_dir     → ListDirTool                           │   │
│  │  - exec         → ExecTool                              │   │
│  │  - web_search   → WebSearchTool                         │   │
│  │  - web_fetch    → WebFetchTool                          │   │
│  │  - message      → MessageTool                           │   │
│  │  - spawn        → SpawnTool                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                           Tool (ABC)                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │ name          │  │ description   │  │ parameters       │   │
│  │ (property)    │  │ (property)    │  │ (property)       │   │
│  └───────────────┘  └───────────────┘  └───────────────────┘   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ execute(**kwargs) → str                                    │  │
│  │ (abstract method)                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ validate_params() → list[str]                              │  │
│  │ to_schema() → dict                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Tool 基类 (base.py)

### 核心接口

```python
class Tool(ABC):
    """Abstract base class for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given parameters."""
        pass
```

### 参数验证

```python
def validate_params(self, params: dict[str, Any]) -> list[str]:
    """Validate tool parameters against JSON schema. Returns error list."""
    schema = self.parameters or {}
    return self._validate(params, {**schema, "type": "object"}, "")
```

**支持的验证**：
- 类型检查 (string, integer, number, boolean, array, object)
- 枚举值 (enum)
- 数值范围 (minimum, maximum)
- 字符串长度 (minLength, maxLength)
- 必填字段 (required)
- 嵌套对象和数组

### 转换为 Schema

```python
def to_schema(self) -> dict[str, Any]:
    """Convert tool to OpenAI function schema format."""
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        },
    }
```

---

## 2. Tool Registry (registry.py)

### 核心功能

```python
class ToolRegistry:
    """Registry for agent tools. Allows dynamic registration and execution."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name with given parameters."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            # 1. 参数验证
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)

            # 2. 执行
            result = await tool.execute(**params)

            # 3. 错误处理
            if isinstance(result, str) and result.startswith("Error"):
                return result + "\n\n[Analyze the error above and try a different approach.]"
            return result
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + _HINT
```

---

## 3. 内置工具详解

### 3.1 文件操作工具 (filesystem.py)

#### ReadFileTool - 读取文件

```python
class ReadFileTool(Tool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "The file path to read"}},
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs) -> str:
        file_path = _resolve_path(path, self._workspace, self._allowed_dir)
        if not file_path.exists():
            return f"Error: File not found: {path}"
        return file_path.read_text(encoding="utf-8")
```

#### WriteFileTool - 写入文件

```python
class WriteFileTool(Tool):
    async def execute(self, path: str, content: str, **kwargs) -> str:
        file_path = _resolve_path(path, self._workspace, self._allowed_dir)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {file_path}"
```

#### EditFileTool - 编辑文件

```python
class EditFileTool(Tool):
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs) -> str:
        content = file_path.read_text(encoding="utf-8")
        if old_text not in content:
            return self._not_found_message(old_text, content, path)
        new_content = content.replace(old_text, new_text, 1)
        file_path.write_text(new_content, encoding="utf-8")
        return f"Successfully edited {file_path}"
```

#### ListDirTool - 列出目录

```python
class ListDirTool(Tool):
    async def execute(self, path: str, **kwargs) -> str:
        dir_path = _resolve_path(path, self._workspace, self._allowed_dir)
        items = [f"{'📁 ' if item.is_dir() else '📄 '}{item.name}" for item in dir_path.iterdir()]
        return "\n".join(sorted(items))
```

**路径安全**：
```python
def _resolve_path(path: str, workspace: Path, allowed_dir: Path) -> Path:
    """Resolve path against workspace and enforce directory restriction."""
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p
    resolved = p.resolve()
    if allowed_dir:
        resolved.relative_to(allowed_dir.resolve())  # 越界则抛异常
    return resolved
```

---

### 3.2 Shell 执行工具 (shell.py)

#### ExecTool - 执行Shell命令

```python
class ExecTool(Tool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        self.timeout = timeout
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\bformat\b",                    # format
            r"\b(mkfs|diskpart)\b",          # 磁盘操作
            r"\bdd\s+if=",                   # dd
            r"\b(shutdown|reboot|poweroff)\b",  # 系统电源
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
        ]
        self.restrict_to_workspace = restrict_to_workspace

    async def execute(self, command: str, working_dir: str | None = None, **kwargs) -> str:
        # 1. 安全检查
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        # 2. 执行命令
        process = await asyncio.create_subprocess_shell(command, ...)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)

        # 3. 处理输出
        if process.returncode != 0:
            return f"{stdout}\nSTDERR:{stderr}\nExit code: {process.returncode}"
        return stdout or "(no output)"
```

**安全机制**：

1. **Deny Patterns** - 危险命令黑名单
   ```python
   r"\brm\s+-[rf]{1,2}\b"     # 禁止 rm -rf
   r"\bdel\s+/[fq]\b"         # 禁止 del /f
   r"\bformat\b"              # 禁止 format
   r"\b(shutdown|reboot)\b"   # 禁止关机
   ```

2. **Allow Patterns** - 白名单（可选）
   ```python
   allow_patterns = [r"^git", r"^npm", r"^pytest"]
   ```

3. **Workspace 限制** - 防止路径穿越
   ```python
   if self.restrict_to_workspace:
       if ".." in command:  # 检测 .. 路径穿越
           return "Error: path traversal detected"
       # 禁止访问 workspace 外的绝对路径
   ```

4. **超时控制** - 默认 60 秒

5. **输出截断** - 最大 10000 字符

---

### 3.3 其他工具

| 工具 | 文件 | 功能 |
|------|------|------|
| `web_search` | web.py | Brave Search 网页搜索 |
| `web_fetch` | web.py | 网页内容抓取 |
| `message` | message.py | 发送消息到聊天渠道 |
| `spawn` | spawn.py | 启动子 Agent |
| `cron` | cron.py | 定时任务管理 |

---

## 4. 工具注册流程

在 `AgentLoop` 初始化时：

```python
def _register_default_tools(self) -> None:
    """Register the default set of tools."""
    allowed_dir = self.workspace if self.restrict_to_workspace else None

    # 文件操作
    for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
        self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))

    # Shell 执行
    self.tools.register(ExecTool(
        working_dir=str(self.workspace),
        timeout=self.exec_config.timeout,
        restrict_to_workspace=self.restrict_to_workspace,
        path_append=self.exec_config.path_append,
    ))

    # 网页
    self.tools.register(WebSearchTool(api_key=self.brave_api_key, proxy=self.web_proxy))
    self.tools.register(WebFetchTool(proxy=self.web_proxy))

    # 消息发送
    self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))

    # 子 Agent
    self.tools.register(SpawnTool(manager=self.subagents))
```

---

## 5. 面试要点

1. **为什么用 Tool 而不是直接执行？**
   - 可控性：参数验证、错误处理
   - 可观测性：记录工具调用
   - 安全性：安全检查、路径限制

2. **Tool 调用的完整流程？**
   - LLM 返回 tool_call
   - AgentLoop 执行 `tools.execute(name, params)`
   - 参数验证 → 执行 → 结果返回
   - 结果添加到 messages 继续循环

3. **如何保证工具执行安全？**
   - 路径限制（workspace 边界）
   - 命令黑名单（危险命令）
   - 超时控制
   - 输出截断

4. **为什么参数验证自定义实现？**
   - 轻量级，不需要引入 jsonschema 依赖
   - 足够满足基本需求

5. **Tool 和 MCP 的区别？**
   - Tool：内置功能，直接执行
   - MCP：外部服务代理，通过协议调用远程工具

---

## 文件位置

- 源文件：
  - `nanobot/agent/tools/base.py` - Tool 基类
  - `nanobot/agent/tools/registry.py` - 工具注册表
  - `nanobot/agent/tools/filesystem.py` - 文件操作
  - `nanobot/agent/tools/shell.py` - Shell 执行
  - `nanobot/agent/tools/web.py` - 网页工具
  - `nanobot/agent/tools/message.py` - 消息工具
  - `nanobot/agent/tools/spawn.py` - 子 Agent
  - `nanobot/agent/tools/cron.py` - 定时任务
  - `nanobot/agent/tools/mcp.py` - MCP 集成
- 相关文件：
  - `nanobot/agent/loop.py` - 调用 ToolRegistry
