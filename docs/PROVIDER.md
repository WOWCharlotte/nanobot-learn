# Provider System 深入解析

> 本文档是 [LEARNING_PLAN.md](./LEARNING_PLAN.md) Day 5 的补充材料

## 概述

nanobot 的 **Provider 系统**是 LLM 抽象层（463行 registry.py），负责：
1. 支持多种 LLM Provider
2. 自动模型检测
3. Provider 注册与查找

**核心亮点**：添加新 Provider 只需 **2 步**！

---

## 核心概念

### Provider 类型

| 类型 | 说明 | 示例 |
|------|------|------|
| Gateway | 路由任何模型 | OpenRouter, AiHubMix, SiliconFlow, VolcEngine |
| Standard | 特定模型 | Anthropic, OpenAI, DeepSeek, Gemini, Zhipu, DashScope, Moonshot, MiniMax |
| Local | 本地部署 | vLLM |
| OAuth | OAuth 认证 | OpenAI Codex, Github Copilot |

### ProviderSpec 元数据

```python
@dataclass(frozen=True)
class ProviderSpec:
    # 标识
    name: str                       # 配置字段名，如 "dashscope"
    keywords: tuple[str, ...]       # 模型名关键词匹配
    env_key: str                    # LiteLLM 环境变量
    display_name: str               # 显示名称

    # 模型前缀
    litellm_prefix: str             # 自动前缀："qwen" → "dashscope/qwen"
    skip_prefixes: tuple[str, ...] # 跳过前缀

    # 网关/本地检测
    is_gateway: bool                # 是否网关
    is_local: bool                 # 是否本地
    detect_by_key_prefix: str       # API Key 前缀检测
    detect_by_base_keyword: str     # API Base URL 关键词检测

    # 其他
    strip_model_prefix: bool        # 剥离前缀后重新添加
    model_overrides: tuple          # 模型参数覆盖
    is_oauth: bool                 # OAuth 认证
    supports_prompt_caching: bool  # 支持 Prompt Caching
```

---

## Provider 列表

### Gateway（网关）

| Provider | API Key 前缀 | Base URL 关键词 | 特点 |
|----------|--------------|----------------|------|
| OpenRouter | `sk-or-` | `openrouter` | 全球网关 |
| AiHubMix | - | `aihubmix` | 需 strip 前缀 |
| SiliconFlow | - | `siliconflow` | 硅基流动 |
| VolcEngine | - | `volces` | 火山引擎 |

### Standard（标准）

| Provider | 关键词 | 前缀 | 备注 |
|----------|--------|------|------|
| Anthropic | `claude` | 无 | 原生支持 |
| OpenAI | `gpt` | 无 | 原生支持 |
| DeepSeek | `deepseek` | `deepseek/` | |
| Gemini | `gemini` | `gemini/` | |
| Zhipu | `glm`, `zhipu` | `zai/` | |
| DashScope | `qwen` | `dashscope/` | 阿里云 |
| Moonshot | `kimi` | `moonshot/` | Kimi |
| MiniMax | `minimax` | `minimax/` | |

### OAuth

| Provider | 说明 |
|----------|------|
| OpenAI Codex | OAuth 认证 |
| Github Copilot | OAuth 认证 |

### Local

| Provider | 说明 |
|----------|------|
| vLLM | 本地 OpenAI 兼容服务器 |

---

## 核心函数

### 1. find_by_model() - 按模型名查找

```python
def find_by_model(model: str) -> ProviderSpec | None:
    """Match a provider by model-name keyword (case-insensitive)."""
    # 1. 优先精确匹配
    model_prefix = model_lower.split("/", 1)[0]
    for spec in std_specs:
        if model_prefix == spec.name:
            return spec

    # 2. 关键词匹配
    for spec in std_specs:
        if any(kw in model_lower for kw in spec.keywords):
            return spec
    return None
```

### 2. find_gateway() - 查找网关

```python
def find_gateway(
    provider_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> ProviderSpec | None:
    """Detect gateway/local provider."""
    # 1. 直接按配置名匹配
    if provider_name:
        spec = find_by_name(provider_name)
        if spec and (spec.is_gateway or spec.is_local):
            return spec

    # 2. API Key 前缀检测 (如 sk-or- → OpenRouter)
    for spec in PROVIDERS:
        if spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
            return spec

    # 3. API Base URL 关键词检测
    for spec in PROVIDERS:
        if spec.detect_by_base_keyword and spec.detect_by_base_keyword in api_base:
            return spec

    return None
```

### 3. find_by_name() - 按名称查找

```python
def find_by_name(name: str) -> ProviderSpec | None:
    """Find a provider spec by config field name."""
    for spec in PROVIDERS:
        if spec.name == name:
            return spec
    return None
```

---

## 添加新 Provider（2 步法）

### Step 1: 添加 ProviderSpec

在 `providers/registry.py` 的 `PROVIDERS` 元组中添加：

```python
# Example: 添加 "myprovider"
ProviderSpec(
    name="myprovider",                   # 配置字段名
    keywords=("myprovider", "mymodel"), # 模型名关键词
    env_key="MYPROVIDER_API_KEY",       # LiteLLM 环境变量
    display_name="My Provider",          # 显示名称
    litellm_prefix="myprovider",        # 自动前缀
    skip_prefixes=("myprovider/",),     # 跳过前缀
    env_extras=(),                       # 额外环境变量
    is_gateway=False,                    # 是否网关
    is_local=False,                      # 是否本地
    detect_by_key_prefix="",             # Key 前缀检测
    detect_by_base_keyword="",           # URL 关键词检测
    default_api_base="",                 # 默认 Base URL
    strip_model_prefix=False,            # 剥离前缀
    model_overrides=(),                  # 模型参数覆盖
)
```

### Step 2: 添加配置字段

在 `config/schema.py` 的 `ProvidersConfig` 中添加：

```python
class ProvidersConfig(BaseModel):
    # ...
    myprovider: ProviderConfig = ProviderConfig()
```

**完成！** 以下功能自动生效：
- ✅ 环境变量支持
- ✅ 模型前缀自动处理
- ✅ 配置匹配
- ✅ `nanobot status` 显示

---

## LLMProvider 接口

```python
class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request."""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model for this provider."""
        pass
```

### LLMResponse

```python
@dataclass
class LLMResponse:
    content: str | None                      # 文本内容
    tool_calls: list[ToolCallRequest]        # 工具调用
    finish_reason: str = "stop"               # 结束原因
    usage: dict[str, int]                   # 用量统计
    reasoning_content: str | None            # 推理内容 (DeepSeek, Kimi)
    thinking_blocks: list[dict] | None      # Thinking 块 (Anthropic)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
```


## LiteLLMProvider 实现

`LiteLLMProvider` 是 nanobot 的核心 LLM 实现，基于 **LiteLLM** 库提供多 Provider 支持。

### 类定义

```python
class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.

    Supports OpenRouter, Anthropic, OpenAI, Gemini, MiniMax, and many other providers through
    a unified interface. Provider-specific logic is driven by the registry
    (see providers/registry.py) — no if-elif chains needed here.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
```

### 初始化参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `api_key` | str \| None | API Key（可选） |
| `api_base` | str \| None | 自定义 API 端点 |
| `default_model` | str | 默认模型 |
| `extra_headers` | dict \| None | 额外请求头（如 APP-Code） |
| `provider_name` | str \| None | 配置中的 Provider 名称 |

### 核心方法

#### 1. chat() - 发送聊天请求

```python
async def chat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
) -> LLMResponse:
```

**流程**：
1. 解析模型名（应用前缀）
2. 检查是否支持 Prompt Caching
3. 清理消息格式
4. 应用模型参数覆盖
5. 调用 LiteLLM
6. 解析响应

#### 2. _resolve_model() - 模型名解析

```python
def _resolve_model(self, model: str) -> str:
    """Resolve model name by applying provider/gateway prefixes."""
    if self._gateway:
        # Gateway 模式：应用网关前缀
        prefix = self._gateway.litellm_prefix
        if self._gateway.strip_model_prefix:
            model = model.split("/")[-1]
        if prefix and not model.startswith(f"{prefix}/"):
            model = f"{prefix}/{model}"
        return model

    # Standard 模式：自动前缀
    spec = find_by_model(model)
    if spec and spec.litellm_prefix:
        model = f"{spec.litellm_prefix}/{model}"
    return model
```

**示例**：
- `qwen-max` → `dashscope/qwen-max`（DashScope）
- `claude-3` → `anthropic/claude-3`（Gateway 模式）

#### 3. _supports_cache_control() - Prompt Caching 检测

```python
def _supports_cache_control(self, model: str) -> bool:
    """Return True when the provider supports cache_control on content blocks."""
    if self._gateway is not None:
        return self._gateway.supports_prompt_caching
    spec = find_by_model(model)
    return spec is not None and spec.supports_prompt_caching
```

#### 4. _apply_cache_control() - 注入缓存控制

```python
def _apply_cache_control(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Return copies of messages and tools with cache_control injected."""
```

在 system message 和 tools 最后一项注入 `cache_control: {"type": "ephemeral"}`。

#### 5. _sanitize_messages() - 消息清理

```python
@staticmethod
def _sanitize_messages(
    messages: list[dict[str, Any]],
    extra_keys: frozenset[str] = frozenset()
) -> list[dict[str, Any]]:
    """Strip non-standard keys and ensure assistant messages have a content key."""
    allowed = _ALLOWED_MSG_KEYS | extra_keys
    # 移除不支持的键
    # 确保 assistant 消息有 content 字段
```

#### 6. _parse_response() - 响应解析

```python
def _parse_response(self, response: Any) -> LLMResponse:
    """Parse LiteLLM response into our standard format."""
    choice = response.choices[0]
    message = choice.message

    # 解析 tool_calls
    # 提取 usage
    # 提取 reasoning_content (DeepSeek/Kimi)
    # 提取 thinking_blocks (Anthropic)
```

### 环境变量设置

```python
def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
    """Set environment variables based on detected provider."""
    spec = self._gateway or find_by_model(model)

    # Gateway 覆盖环境变量；Standard 用 setdefault
    if self._gateway:
        os.environ[spec.env_key] = api_key
    else:
        os.environ.setdefault(spec.env_key, api_key)

    # 处理 env_extras 占位符
    # {api_key} → 用户 API Key
    # {api_base} → API Base URL
```

### 模型参数覆盖

```python
def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
    """Apply model-specific parameter overrides from the registry."""
    spec = find_by_model(model)
    if spec:
        for pattern, overrides in spec.model_overrides:
            if pattern in model.lower():
                kwargs.update(overrides)
```

**示例**：某些模型需要特殊 temperature 设置。

### 错误处理

```python
try:
    response = await acompletion(**kwargs)
    return self._parse_response(response)
except Exception as e:
    # 优雅降级：错误信息作为 content 返回
    return LLMResponse(
        content=f"Error calling LLM: {str(e)}",
        finish_reason="error",
    )
```

---

## 面试要点

1. **为什么用 Provider 抽象？**
   - 统一接口：所有 LLM 用法一致
   - 易于扩展：2 步添加新 Provider
   - 自动检测：模型/Key/URL 自动识别

2. **Gateway vs Standard 的区别？**
   - Gateway：可路由任何模型（如 OpenRouter）
   - Standard：特定模型（如 Claude、GPT）

3. **模型前缀的作用？**
   - LiteLLM 需要特定格式
   - 如 `qwen-max` → `dashscope/qwen-max`

4. **strip_model_prefix 的作用？**
   - 某些网关不理解带组织的前缀
   - 如 `anthropic/claude-3` → `claude-3` → `openai/claude-3`

5. **OAuth Provider 如何处理？**
   - 不使用 API Key
   - 使用 OAuth 流程获取 Token

---

## 文件位置

- 源文件：
  - `nanobot/providers/registry.py` - Provider 注册表
  - `nanobot/providers/base.py` - Provider 接口
  - `nanobot/providers/litellm_provider.py` - LiteLLM 实现
  - `nanobot/providers/custom_provider.py` - 自定义 Provider
  - `nanobot/providers/openai_codex_provider.py` - OAuth Provider
  - `nanobot/config/schema.py` - Provider 配置
