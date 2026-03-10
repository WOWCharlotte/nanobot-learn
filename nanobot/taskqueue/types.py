"""Task queue types for self-managing AI system."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _format_datetime(dt: datetime) -> str:
    """Format datetime to ISO format, handling both naive and aware datetimes."""
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    # Format and ensure it ends with Z for UTC
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


class TaskState(Enum):
    """Task states representing lifecycle."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class Task:
    """Represents a task in the queue."""

    id: str
    title: str
    state: TaskState = TaskState.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tmux_session: str | None = None
    marker_file: str | None = None
    blocked_by: str | None = None
    error: str | None = None
    retry_count: int = 0
    priority: str = "normal"
    instructions: str = ""

    def to_markdown(self) -> str:
        """Convert task to markdown format."""
        lines = [f"- [{'x' if self.state == TaskState.DONE else ' '}] {self.id}: {self.title}"]

        if self.state == TaskState.PENDING:
            lines.append(f"  - created: {_format_datetime(self.created_at)}")
            if self.priority != "normal":
                lines.append(f"  - priority: {self.priority}")
            if self.instructions:
                lines.append(f"  - instructions: {self.instructions}")
        elif self.state == TaskState.RUNNING:
            lines.append(f"  - created: {_format_datetime(self.created_at)}")
            if self.started_at:
                lines.append(f"  - started: {_format_datetime(self.started_at)}")
            if self.tmux_session:
                lines.append(f"  - tmux_session: {self.tmux_session}")
        elif self.state == TaskState.DONE:
            lines.append(f"  - created: {_format_datetime(self.created_at)}")
            if self.completed_at:
                lines.append(f"  - completed: {_format_datetime(self.completed_at)}")
            if self.marker_file:
                lines.append(f"  - marker: {self.marker_file}")
        elif self.state == TaskState.BLOCKED:
            lines.append(f"  - created: {_format_datetime(self.created_at)}")
            if self.blocked_by:
                lines.append(f"  - blocked_by: {self.blocked_by}")
        elif self.state == TaskState.FAILED:
            lines.append(f"  - created: {_format_datetime(self.created_at)}")
            if self.error:
                lines.append(f"  - error: {self.error}")
            lines.append(f"  - retry_count: {self.retry_count}")

        return "\n".join(lines)
