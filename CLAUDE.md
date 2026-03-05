# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**nanobot** is an ultra-lightweight personal AI assistant (~4,000 lines of core agent code). It connects to various chat platforms (Telegram, Discord, WhatsApp, Feishu, QQ, DingTalk, Slack, Email, Matrix, Mochat) and provides an agentic AI with tools for file manipulation, shell execution, web search, scheduled tasks, and more.

## Common Commands

### Development Setup
```bash
pip install -e .              # Install in editable mode
pip install -e ".[dev]"       # Install with dev dependencies
pip install -e ".[matrix]"    # Install with Matrix support
```

### Running Tests
```bash
pytest                          # Run all tests
pytest tests/test_file.py      # Run specific test file
pytest -k "test_name"          # Run tests matching pattern
pytest --cov=nanobot           # Run with coverage
```

### Linting
```bash
ruff check nanobot/            # Lint code
ruff check nanobot/ --fix      # Auto-fix issues
```

### Running the Application
```bash
nanobot onboard                # Initialize config & workspace
nanobot agent                  # Interactive chat mode
nanobot agent -m "Hello!"      # Single message mode
nanobot gateway                # Start gateway (connects all enabled channels)
nanobot status                 # Show status
```

### Docker
```bash
docker compose up -d nanobot-gateway  # Start gateway via Docker Compose
docker compose run --rm nanobot agent -m "Hello!"  # Run CLI command
```

## Architecture

### Core Components

| Directory | Purpose |
|-----------|---------|
| `agent/` | Core agent logic: agent loop, context/prompt builder, memory, skills loader, subagent execution |
| `channels/` | Chat platform integrations (Telegram, Discord, WhatsApp, Feishu, QQ, DingTalk, Slack, Email, Matrix, Mochat) |
| `providers/` | LLM provider abstraction layer using LiteLLM |
| `session/` | Conversation session management |
| `config/` | Configuration loading and schema validation |
| `bus/` | Message routing and event system |
| `cron/` | Scheduled task execution |
| `heartbeat/` | Periodic proactive agent wake-up |
| `skills/` | Bundled skills (github, weather, tmux, etc.) |

### Key Files

- `nanobot/agent/loop.py` - Main agent loop (LLM ↔ tool execution cycle)
- `nanobot/agent/context.py` - Prompt building with caching support
- `nanobot/agent/memory.py` - Persistent conversation memory
- `nanobot/agent/tools/registry.py` - Tool registration and discovery
- `nanobot/providers/registry.py` - Provider registry (add new providers in 2 steps)
- `nanobot/config/schema.py` - Pydantic configuration schema
- `nanobot/cli/commands.py` - CLI entry point (Typer-based)

### Adding a New Provider

Adding a new LLM provider takes only 2 steps (no if-elif chains):

1. Add a `ProviderSpec` entry to `PROVIDERS` in `nanobot/providers/registry.py`
2. Add a field to `ProvidersConfig` in `nanobot/config/schema.py`

Environment variables, model prefixing, and auto-detection work automatically.

### Channel Development

Each channel in `nanobot/channels/` inherits from `ChannelBase` and implements:
- `send()` - Send message to user
- `start()` / `stop()` - Lifecycle management
- Message parsing and user identification

### Tool System

Built-in tools in `nanobot/agent/tools/`:
- `shell.py` - Execute shell commands
- `filesystem.py` - File read/write/edit operations
- `web.py` - Web search and fetch
- `message.py` - Send messages to users
- `cron.py` - Manage scheduled tasks
- `spawn.py` - Spawn subagents
- `mcp.py` - MCP server integration

## Configuration

Config file: `~/.nanobot/config.json`

Key configuration sections:
- `providers` - LLM provider settings (apiKey, apiBase, etc.)
- `agents.defaults.model` - Default model selection
- `channels` - Chat platform credentials and settings
- `tools` - Tool permissions and MCP server configuration

## Testing Patterns

- Tests are in `tests/` directory
- Use `pytest-asyncio` for async tests
- Test files follow `test_*.py` naming convention
- Key test patterns: CLI input, cron service, memory consolidation, channel behavior
