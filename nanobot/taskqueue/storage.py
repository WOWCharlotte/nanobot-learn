"""Task queue storage for reading and writing todo.md files."""

import re
from datetime import datetime
from pathlib import Path

from nanobot.taskqueue.types import Task, TaskState


class TaskQueueStorage:
    """Handles parsing and serialization of todo.md files."""

    STATE_HEADERS = {
        TaskState.PENDING: "## PENDING",
        TaskState.RUNNING: "## RUNNING",
        TaskState.DONE: "## DONE",
        TaskState.BLOCKED: "## BLOCKED",
        TaskState.FAILED: "## FAILED",
    }

    def __init__(self, todo_file: Path):
        self.todo_file = todo_file

    def read_tasks(self) -> dict[TaskState, list[Task]]:
        """Read and parse todo.md file into task dictionary by state."""
        if not self.todo_file.exists():
            return {state: [] for state in TaskState}

        content = self.todo_file.read_text(encoding="utf-8")
        return self._parse_content(content)

    def write_tasks(self, tasks_by_state: dict[TaskState, list[Task]]) -> None:
        """Write tasks back to todo.md file."""
        lines = ["# Task Queue", ""]

        for state in TaskState:
            lines.append(self.STATE_HEADERS[state])
            tasks = tasks_by_state.get(state, [])
            if tasks:
                for task in tasks:
                    lines.append(task.to_markdown())
            else:
                lines.append("- (none)")
            lines.append("")

        # Ensure parent directory exists
        self.todo_file.parent.mkdir(parents=True, exist_ok=True)

        self.todo_file.write_text("\n".join(lines), encoding="utf-8")

    def _parse_content(self, content: str) -> dict[TaskState, list[Task]]:
        """Parse markdown content into tasks by state."""
        tasks_by_state = {state: [] for state in TaskState}

        # Find all state sections
        current_state: TaskState | None = None
        current_lines: list[str] = []

        for line in content.split("\n"):
            stripped = line.strip()

            # Check if this is a state header
            for state, header in self.STATE_HEADERS.items():
                if stripped == header:
                    # Process previous section
                    if current_state is not None and current_lines:
                        tasks = self._parse_tasks(current_state, current_lines)
                        tasks_by_state[current_state].extend(tasks)
                    current_state = state
                    current_lines = []
                    break
            else:
                if current_state is not None:
                    current_lines.append(line)

        # Process last section
        if current_state is not None and current_lines:
            tasks = self._parse_tasks(current_state, current_lines)
            tasks_by_state[current_state].extend(tasks)

        return tasks_by_state

    def _parse_tasks(self, state: TaskState, lines: list[str]) -> list[Task]:
        """Parse tasks from lines within a state section."""
        tasks = []
        current_task: dict | None = None

        for line in lines:
            stripped = line.strip()

            # Skip empty lines and "(none)"
            if not stripped or stripped == "- (none)":
                continue

            # Check for task item (starts with "- [ ]" or "- [x]")
            task_match = re.match(r"- \[([ x])\] (\S+): (.+)", stripped)
            if task_match:
                # Save previous task
                if current_task is not None:
                    task = self._build_task(current_task, state)
                    if task:
                        tasks.append(task)

                # Start new task
                current_task = {
                    "id": task_match.group(2),
                    "title": task_match.group(3),
                }
                continue

            # Parse metadata lines
            if current_task is not None:
                # created: 2026-03-10T10:00:00Z
                match = re.match(r"- (created|started|completed): (.+)", stripped)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    try:
                        # Try to parse ISO format
                        # Handle Z suffix properly - it means UTC
                        parsed_value = value
                        if parsed_value.endswith("Z"):
                            parsed_value = parsed_value[:-1] + "+00:00"
                        dt = datetime.fromisoformat(parsed_value)
                        current_task[key] = dt
                    except ValueError:
                        current_task[key] = value
                    continue

                # priority: high
                match = re.match(r"- priority: (.+)", stripped)
                if match:
                    current_task["priority"] = match.group(1)
                    continue

                # tmux_session: nanobot-task-001
                match = re.match(r"- tmux_session: (.+)", stripped)
                if match:
                    current_task["tmux_session"] = match.group(1)
                    continue

                # marker: .task-000.done
                match = re.match(r"- marker: (.+)", stripped)
                if match:
                    current_task["marker_file"] = match.group(1)
                    continue

                # blocked_by: task-001
                match = re.match(r"- blocked_by: (.+)", stripped)
                if match:
                    current_task["blocked_by"] = match.group(1)
                    continue

                # error: Permission denied
                match = re.match(r"- error: (.+)", stripped)
                if match:
                    current_task["error"] = match.group(1)
                    continue

                # retry_count: 3
                match = re.match(r"- retry_count: (\d+)", stripped)
                if match:
                    current_task["retry_count"] = int(match.group(1))
                    continue

                # instructions: some text
                match = re.match(r"- instructions: (.+)", stripped)
                if match:
                    current_task["instructions"] = match.group(1)
                    continue

        # Don't forget last task
        if current_task is not None:
            task = self._build_task(current_task, state)
            if task:
                tasks.append(task)

        return tasks

    def _build_task(self, data: dict, state: TaskState) -> Task | None:
        """Build Task object from parsed data."""
        try:
            created_at = data.get("created", datetime.now())
            if isinstance(created_at, str):
                if created_at.endswith("Z"):
                    created_at = created_at[:-1] + "+00:00"
                created_at = datetime.fromisoformat(created_at)

            return Task(
                id=data.get("id", ""),
                title=data.get("title", ""),
                state=state,
                created_at=created_at,
                started_at=data.get("started"),
                completed_at=data.get("completed"),
                tmux_session=data.get("tmux_session"),
                marker_file=data.get("marker_file"),
                blocked_by=data.get("blocked_by"),
                error=data.get("error"),
                retry_count=data.get("retry_count", 0),
                priority=data.get("priority", "normal"),
                instructions=data.get("instructions", ""),
            )
        except Exception:
            return None
