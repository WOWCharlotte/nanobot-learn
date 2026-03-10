"""Task queue tool for managing self-managing AI tasks."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.taskqueue.service import TaskQueueService
from nanobot.taskqueue.types import TaskState


class TaskQueueTool(Tool):
    """Tool to manage task queue for self-managing AI system."""

    def __init__(self, workspace: Path, service: TaskQueueService | None = None):
        self._workspace = workspace
        self._service = service
        self._channel = ""
        self._chat_id = ""

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id

    def _get_service(self) -> TaskQueueService:
        """Get or create the task queue service."""
        if self._service is None:
            self._service = TaskQueueService(
                workspace=self._workspace,
                agent=None,  # Will be set later if needed
            )
        return self._service

    @property
    def name(self) -> str:
        return "taskqueue"

    @property
    def description(self) -> str:
        return "Manage task queue for self-managing AI. Actions: add, list, get, update."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "get", "update"],
                    "description": "Action to perform",
                },
                "title": {
                    "type": "string",
                    "description": "Task title (for add)",
                },
                "instructions": {
                    "type": "string",
                    "description": "Task instructions (for add)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                    "description": "Task priority (for add)",
                    "default": "normal",
                },
                "state": {
                    "type": "string",
                    "enum": ["PENDING", "RUNNING", "DONE", "BLOCKED", "FAILED"],
                    "description": "Filter by state (for list) or set state (for update)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (for get, update)",
                },
                "error": {
                    "type": "string",
                    "description": "Error message (for update when marking failed)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        title: str = "",
        instructions: str = "",
        priority: str = "normal",
        state: str | None = None,
        task_id: str = "",
        error: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute task queue action."""
        service = self._get_service()

        if action == "add":
            if not title:
                return "Error: title is required for add action"
            task = service.add_task(
                title=title,
                instructions=instructions,
                priority=priority,
            )
            return f"Added task {task.id}: {task.title}\nState: {task.state.value}"

        elif action == "list":
            state_filter = TaskState(state) if state else None
            tasks = service.list_tasks(state_filter)

            if not tasks:
                return "No tasks found"

            lines = ["Tasks:"]
            for task in tasks:
                lines.append(
                    f"  - {task.id}: {task.title} [{task.state.value}]"
                )
                if task.priority != "normal":
                    lines[-1] += f" (priority: {task.priority})"
            return "\n".join(lines)

        elif action == "get":
            if not task_id:
                return "Error: task_id is required for get action"
            task = service.get_task(task_id)
            if not task:
                return f"Task {task_id} not found"

            lines = [
                f"Task: {task.id}",
                f"Title: {task.title}",
                f"State: {task.state.value}",
                f"Created: {task.created_at.isoformat()}Z",
            ]
            if task.started_at:
                lines.append(f"Started: {task.started_at.isoformat()}Z")
            if task.completed_at:
                lines.append(f"Completed: {task.completed_at.isoformat()}Z")
            if task.priority != "normal":
                lines.append(f"Priority: {task.priority}")
            if task.instructions:
                lines.append(f"Instructions: {task.instructions}")
            if task.error:
                lines.append(f"Error: {task.error}")
            if task.retry_count:
                lines.append(f"Retry count: {task.retry_count}")

            return "\n".join(lines)

        elif action == "update":
            if not task_id:
                return "Error: task_id is required for update action"

            state_enum = TaskState(state) if state else None
            success = service.update_task(
                task_id=task_id,
                state=state_enum,
                error=error or None,
            )

            if success:
                return f"Updated task {task_id}"
            return f"Task {task_id} not found"

        return f"Unknown action: {action}"
