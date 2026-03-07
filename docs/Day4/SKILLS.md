# Skills System 深入解析

> 本文档是 [LEARNING_PLAN.md](../../LEARNING_PLAN.md) Day 4 的补充材料

## 概述

`agent/skills.py` 是 nanobot 的 **技能系统**（229行），负责：
1. 技能加载和管理
2. 技能元数据解析
3. 按需加载技能内容

---

## 核心概念

```
Skills (技能)
├── 定义：Markdown 文件 (SKILL.md)
├── 来源：
│   ├── workspace/skills/{skill}/SKILL.md  (用户自定义)
│   └── nanobot/skills/{skill}/SKILL.md   (内置)
├── 元数据：YAML frontmatter
│   ├── name
│   ├── description
│   ├── always: true    (常驻加载)
│   └── requires:       (依赖检查)
│       ├── bins: [gh, tmux]
│       └── env: [API_KEY]
```

---

## 类：SkillsLoader

### 初始化

```python
class SkillsLoader:
    """Loader for agent skills."""

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
```

**技能来源优先级**：
1. `workspace/skills/` (用户自定义，优先)
2. `nanobot/skills/` (内置)

---

## 技能文件结构

### SKILL.md 格式

```markdown
---
name: memory
description: Two-layer memory system with grep-based recall.
always: true
requires:
  bins: [gh, tmux]
  env: [API_KEY]
---

# Memory

## Structure

- `memory/MEMORY.md` — Long-term facts
- `memory/HISTORY.md` — Append-only event log

...
```

### 元数据字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 技能名称 |
| `description` | string | 技能描述 |
| `always` | boolean | 是否常驻加载到 context |
| `requires.bins` | array | 依赖的 CLI 工具 |
| `requires.env` | array | 依赖的环境变量 |

---

## 核心函数详解

### 1. `list_skills()` - 列出所有技能

```python
def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
    """List all available skills."""
    skills = []

    # 1. Workspace 技能 (高优先级)
    if self.workspace_skills.exists():
        for skill_dir in self.workspace_skills.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills.append({
                        "name": skill_dir.name,
                        "path": str(skill_file),
                        "source": "workspace"
                    })

    # 2. 内置技能
    if self.builtin_skills and self.builtin_skills.exists():
        for skill_dir in self.builtin_skills.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                # 避免重复
                if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                    skills.append({
                        "name": skill_dir.name,
                        "path": str(skill_file),
                        "source": "builtin"
                    })

    # 3. 按依赖过滤
    if filter_unavailable:
        return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
    return skills
```

---

### 2. `load_skill()` - 加载单个技能

```python
def load_skill(self, name: str) -> str | None:
    """Load a skill by name."""
    # 优先检查 workspace
    workspace_skill = self.workspace_skills / name / "SKILL.md"
    if workspace_skill.exists():
        return workspace_skill.read_text(encoding="utf-8")

    # 检查内置
    if self.builtin_skills:
        builtin_skill = self.builtin_skills / name / "SKILL.md"
        if builtin_skill.exists():
            return builtin_skill.read_text(encoding="utf-8")

    return None
```

---

### 3. `load_skills_for_context()` - 加载技能内容到 Context

```python
def load_skills_for_context(self, skill_names: list[str]) -> str:
    """Load specific skills for inclusion in agent context."""
    parts = []
    for name in skill_names:
        content = self.load_skill(name)
        if content:
            # 移除 frontmatter
            content = self._strip_frontmatter(content)
            parts.append(f"### Skill: {name}\n\n{content}")

    return "\n\n---\n\n".join(parts) if parts else ""
```

---

### 4. `build_skills_summary()` - 构建技能摘要

```python
def build_skills_summary(self) -> str:
    """Build XML-formatted skills summary for progressive loading."""
    all_skills = self.list_skills(filter_unavailable=False)
    if not all_skills:
        return ""

    lines = ["<skills>"]
    for s in all_skills:
        name = escape_xml(s["name"])
        path = s["path"]
        desc = escape_xml(self._get_skill_description(s["name"]))
        skill_meta = self._get_skill_meta(s["name"])
        available = self._check_requirements(skill_meta)

        lines.append(f'  <skill available="{str(available).lower()}">')
        lines.append(f'    <name>{name}</name>')
        lines.append(f'    <description>{desc}</description>')
        lines.append(f'    <location>{path}</location>')

        # 显示缺失的依赖
        if not available:
            missing = self._get_missing_requirements(skill_meta)
            if missing:
                lines.append(f'    <requires>{escape_xml(missing)}</requires>')

        lines.append("  </skill>")
    lines.append("</skills>")

    return "\n".join(lines)
```

**输出示例**：
```xml
<skills>
  <skill available="true">
    <name>memory</name>
    <description>Two-layer memory system...</description>
    <location>nanobot/skills/memory/SKILL.md</location>
  </skill>
  <skill available="false">
    <name>github</name>
    <description>Interact with GitHub...</description>
    <location>nanobot/skills/github/SKILL.md</location>
    <requires>CLI: gh</requires>
  </skill>
</skills>
```

---

### 5. `get_always_skills()` - 获取常驻技能

```python
def get_always_skills(self) -> list[str]:
    """Get skills marked as always=true that meet requirements."""
    result = []
    for s in self.list_skills(filter_unavailable=True):
        meta = self.get_skill_metadata(s["name"]) or {}
        skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
        if skill_meta.get("always") or meta.get("always"):
            result.append(s["name"])
    return result
```

---

### 6. 依赖检查

```python
def _check_requirements(self, skill_meta: dict) -> bool:
    """Check if skill requirements are met."""
    requires = skill_meta.get("requires", {})

    # 检查 CLI 工具
    for b in requires.get("bins", []):
        if not shutil.which(b):
            return False

    # 检查环境变量
    for env in requires.get("env", []):
        if not os.environ.get(env):
            return False

    return True
```

---

## 技能加载流程

```
ContextBuilder.build_system_prompt()
        │
        ▼
SkillsLoader.build_skills_summary()
        │
        ▼
生成 XML 摘要（所有技能列表）───────► System Prompt

        │
        ▼
SkillsLoader.get_always_skills()
        │
        ▼
SkillsLoader.load_skills_for_context(always_skills)
        │
        ▼
加载常驻技能内容 ─────────────────► System Prompt
```

---

## 内置技能

| 技能 | 说明 | 依赖 |
|------|------|------|
| `memory` | 两层记忆系统 | 无 (always: true) |
| `cron` | 定时任务管理 | 无 |
| `weather` | 天气查询 | 无 |
| `clawhub` | ClawHub 技能市场 | 无 |
| `skill-creator` | 技能创建工具 | 无 |
| `github` | GitHub CLI 操作 | `gh` CLI |
| `tmux` | Tmux 会话管理 | `tmux` CLI |
| `summarize` | 文本/音视频摘要 | `summarize` CLI |

---

## 面试要点

1. **为什么用 Skill 而不是直接内置？**
   - 可扩展：用户可自定义技能
   - 按需加载：非 always 技能不占用 context
   - 依赖检查：未安装依赖时自动禁用

2. **Skills 和 Tools 的区别？**
   - Tool：可执行的功能
   - Skill：如何使用工具的知识

3. **渐进式加载是什么？**
   - 摘要包含所有技能信息
   - Agent 决定何时读取完整技能
   - 减少不必要的 context 占用

4. **为什么区分 workspace 和 builtin？**
   - workspace 优先级高（用户自定义覆盖内置）
   - 内置提供基础能力

5. **always: true 的作用？**
   - 常驻加载到 System Prompt
   - 适合基础能力（如 memory）

6. **Skill 文件的格式是什么？为什么用 YAML frontmatter？**
   - Markdown 文件 + YAML frontmatter
   - frontmatter 存储元数据（name、description、always、requires）
   - 主体是技能的使用说明（Markdown 格式）
   - 好处：元数据与内容分离，便于程序解析

7. **技能优先级如何处理？**
   - workspace/skills/ 优先于 nanobot/skills/
   - 同名技能：用户自定义覆盖内置
   - 代码逻辑：`list_skills()` 先遍历 workspace，再遍历 builtin，避免重复

8. **如何检查技能依赖？**
   - `requires.bins`：检查 CLI 工具是否存在（通过 `shutil.which()`）
   - `requires.env`：检查环境变量是否设置（通过 `os.environ.get()`）
   - 依赖不满足时：技能标记为 `available="false"`，不加载到 context

9. **为什么用 XML 格式输出技能摘要？**
   - 结构化数据，便于 LLM 解析
   - 明确标记可用/不可用状态
   - 包含位置信息，Agent 可自行读取
   - 格式示例：`<skill available="true"><name>memory</name>...</skill>`

10. **Skill 会被缓存吗？**
    - 不会缓存，每次请求重新读取文件
    - 因为 Skill 内容可能随时更新
    - 适合场景：个人 AI 助手，请求频率不高

11. **用户如何自定义 Skill？**
    - 在 `workspace/skills/{skill_name}/SKILL.md` 创建目录和文件
    - 格式：YAML frontmatter + Markdown 说明
    - 示例：`workspace/skills/my_custom_skill/SKILL.md`

12. **内置技能有哪些？**
    - memory：两层记忆系统（always: true）
    - cron：定时任务管理
    - weather：天气查询
    - clawhub：ClawHub 技能市场
    - skill-creator：技能创建工具
    - github：GitHub CLI 操作（需要 gh）
    - tmux：Tmux 会话管理（需要 tmux）
    - summarize：文本/音视频摘要（需要 summarize CLI）

13. **Skill 如何与 Agent Loop 交互？**
    - ContextBuilder 构建 System Prompt 时调用 SkillsLoader
    - build_skills_summary()：生成所有技能摘要
    - get_always_skills()：获取常驻技能
    - load_skills_for_context()：加载指定技能内容
    - Agent 收到用户请求后，可能使用 read_file 工具读取 Skill 文件

14. **为什么 Skill 不是直接执行而是知识文档？**
    - Skill 是"如何使用"的知识，不是"执行什么"
    - Agent 理解 Skill 内容后，自主决定如何调用工具
    - 灵活性更高，适应复杂场景
    - Tool 是"能做什么"，Skill 是"怎么做的"

15. **Skill 的典型内容结构？**
    - 技能名称(必须)
    - 功能描述(必须)
    - 使用方法(必须)
    - 示例
    - 注意事项
    - Agent 通过阅读这些内容理解如何完成特定任务

16. **ClawHub 是什么？**
    - 公共技能市场
    - nanobot 内置的 skill：可搜索和安装社区共享的技能
    - 扩展 nanobot 能力的方式之一

---

## 文件位置

- 源文件：`nanobot/agent/skills.py`
- 相关文件：
  - `nanobot/agent/context.py` - 调用 SkillsLoader
  - `nanobot/skills/` - 内置技能目录
  - `workspace/skills/` - 用户技能目录
