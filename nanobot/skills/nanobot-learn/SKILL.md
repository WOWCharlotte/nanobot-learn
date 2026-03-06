---
name: nanobot-learn
description: Learn nanobot architecture and prepare for interviews.
always: true
---

# nanobot-learn

Use the `nanobot learn` command to help users learn about nanobot's architecture or prepare for technical interviews.

## Two Modes

1. **Teacher Mode** - Answer questions about nanobot's technical principles based on documentation
2. **Quiz Mode** - Ask questions, evaluate user answers, and provide feedback

## Commands

### Teacher Mode (Default)

```
nanobot learn
nanobot learn --mode teacher
nanobot learn --mode teacher --day Day2
```

### Quiz Mode

```
nanobot learn --mode quiz
nanobot learn --mode quiz --day Day3
```

### Single Question Mode

```
nanobot learn --message "How does Agent Loop work?"
```

## Interactive Commands

When in interactive mode, users can use:

- `/mode teacher` - Switch to teacher mode
- `/mode quiz` - Switch to quiz mode
- `/stats` - View learning progress
- `/exit` - Exit learn mode

## When to Use

Use this skill when:

1. User asks about nanobot's architecture, design, or implementation
2. User wants to learn about nanobot's code structure
3. User is preparing for a nanobot-related technical interview
4. User wants to test their knowledge of nanobot

## Response Guidelines

- In teacher mode: Answer based on the Day1-7 documentation
- In quiz mode: Ask clear questions, provide constructive feedback
- Keep responses concise and encouraging
- Use Chinese (中文) for communication

## Day Topics

| Day | Topic |
|-----|-------|
| Day1 | 项目结构与核心概念 |
| Day2 | Agent Loop 与 Context |
| Day3 | Memory 与 Session |
| Day4 | Tool 与 Agent 扩展 |
| Day5 | Provider 系统 |
| Day6 | Channel 系统 |
| Day7 | CLI/Cron/Heartbeat |
