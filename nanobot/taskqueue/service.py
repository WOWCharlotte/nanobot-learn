"""Task queue service for self-managing AI system."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

from nanobot.taskqueue.storage import TaskQueueStorage
from nanobot.taskqueue.types import Task, TaskState

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop


# Callback type for delivering task results to users
TaskResultCallback = Callable[[str, str], Awaitable[None]]
# Args: (task_id, result_content)


class TaskQueueService:
    """
    Service for managing task queue processing.

    Handles:
    - Parsing todo.md files
    - Task state transitions
    - Task execution in tmux sessions
    - Marker file creation
    - Result delivery to users
    """

    MAX_RETRIES = 3
    TMUX_SESSION_PREFIX = "nanobot-task-"

    def __init__(
        self,
        workspace: Path,
        agent: "AgentLoop",
        todo_filename: str = "todo.md",
        on_result: TaskResultCallback | None = None,
    ):
        self.workspace = workspace
        self.agent = agent
        self.todo_file = workspace / todo_filename
        self.storage = TaskQueueStorage(self.todo_file)
        self._on_result = on_result

    async def process_queue(self) -> None:
        """Process pending tasks in the queue."""
        try:
            # Parse current tasks
            tasks_by_state = self.storage.read_tasks()

            # Recover from any crashed RUNNING tasks
            await self._recover_running_tasks(tasks_by_state)

            # Get next executable task
            task = self._get_next_task(tasks_by_state)
            if not task:
                logger.debug("No pending tasks in queue")
                return

            # Execute the task
            await self._execute_task(task)

        except Exception as e:
            logger.error(f"Error processing task queue: {e}")

    async def _recover_running_tasks(self, tasks_by_state: dict[TaskState, list[Task]]) -> None:
        """Recover from crashed tasks that were RUNNING."""
        running_tasks = tasks_by_state.get(TaskState.RUNNING, [])
        if not running_tasks:
            return

        logger.info(f"Recovering {len(running_tasks)} crashed RUNNING tasks")

        for task in running_tasks:
            # Reset to PENDING for retry
            task.state = TaskState.PENDING
            task.started_at = None
            task.tmux_session = None
            # Increment retry count
            task.retry_count += 1

        self.storage.write_tasks(tasks_by_state)

    def _get_next_task(self, tasks_by_state: dict[TaskState, list[Task]]) -> Task | None:
        """Get next PENDING task that isn't blocked."""
        pending_tasks = tasks_by_state.get(TaskState.PENDING, [])
        blocked_ids = {task.id for task in tasks_by_state.get(TaskState.BLOCKED, [])}

        for task in pending_tasks:
            # Check if task is blocked
            if task.blocked_by and task.blocked_by in blocked_ids:
                continue
            # Check retry count
            if task.retry_count >= self.MAX_RETRIES:
                # Move to FAILED
                task.state = TaskState.FAILED
                task.error = f"Max retries ({self.MAX_RETRIES}) exceeded"
                continue

            return task

        return None

    async def _execute_task(self, task: Task) -> None:
        """Execute a task through the agent."""
        logger.info(f"Executing task {task.id}: {task.title}")

        # Update task state to RUNNING
        tasks_by_state = self.storage.read_tasks()

        # Find and update task
        for t in tasks_by_state[TaskState.PENDING]:
            if t.id == task.id:
                t.state = TaskState.RUNNING
                t.started_at = datetime.now()
                t.tmux_session = f"{self.TMUX_SESSION_PREFIX}{t.id}"
                task = t
                break

        self.storage.write_tasks(tasks_by_state)

        try:
            # Execute the task instructions through the agent
            session_key = f"taskqueue:{task.id}"

            # Process task with agent
            result = await self.agent.process_direct(
                content=task.instructions,
                session_key=session_key,
                channel="taskqueue",
                chat_id=task.id,
            )

            logger.info(f"Task {task.id} completed: {result[:100]}...")

            # Mark as done and deliver result
            await self._mark_done(task, result)

        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")
            await self._mark_failed(task, str(e))

    async def _mark_done(self, task: Task, result: str = "") -> None:
        """Mark task as DONE, create marker file, and deliver result to user."""
        tasks_by_state = self.storage.read_tasks()

        # Find and update task
        for t in tasks_by_state[TaskState.RUNNING]:
            if t.id == task.id:
                t.state = TaskState.DONE
                t.completed_at = datetime.now()
                t.marker_file = f".task-{t.id}.done"

                # Create marker file in workspace
                marker_path = self.workspace / t.marker_file
                marker_path.write_text(
                    f"Task completed at {t.completed_at.isoformat()}Z\nResult:\n{result}"
                )
                logger.info(f"Created marker file: {marker_path}")

                task = t
                break

        self.storage.write_tasks(tasks_by_state)

        # Deliver result to user via callback
        if self._on_result and result:
            try:
                await self._on_result(task.id, result)
            except Exception as e:
                logger.error(f"Failed to deliver result for task {task.id}: {e}")

    async def _mark_failed(self, task: Task, error: str) -> None:
        """Mark task as FAILED."""
        tasks_by_state = self.storage.read_tasks()

        # Find and update task
        for t in tasks_by_state[TaskState.RUNNING]:
            if t.id == task.id:
                t.state = TaskState.FAILED
                t.error = error
                t.retry_count += 1
                break

        self.storage.write_tasks(tasks_by_state)

    def add_task(
        self,
        title: str,
        instructions: str,
        priority: str = "normal",
    ) -> Task:
        """Add a new task to the queue."""
        tasks_by_state = self.storage.read_tasks()

        # Generate task ID
        existing_ids = set()
        for tasks in tasks_by_state.values():
            for t in tasks:
                if t.id.startswith("task-"):
                    try:
                        num = int(t.id.split("-")[1])
                        existing_ids.add(num)
                    except (IndexError, ValueError):
                        pass

        new_id_num = max(existing_ids, default=0) + 1
        task_id = f"task-{new_id_num:03d}"

        # Create new task
        task = Task(
            id=task_id,
            title=title,
            instructions=instructions,
            priority=priority,
            created_at=datetime.now(),
        )

        # Add to PENDING
        tasks_by_state[TaskState.PENDING].append(task)
        self.storage.write_tasks(tasks_by_state)

        logger.info(f"Added task {task_id}: {title}")
        return task

    def list_tasks(self, state: TaskState | None = None) -> list[Task]:
        """List tasks, optionally filtered by state."""
        tasks_by_state = self.storage.read_tasks()

        if state:
            return tasks_by_state.get(state, [])

        # Return all tasks
        all_tasks = []
        for tasks in tasks_by_state.values():
            all_tasks.extend(tasks)
        return all_tasks

    def get_task(self, task_id: str) -> Task | None:
        """Get a specific task by ID."""
        tasks_by_state = self.storage.read_tasks()

        for tasks in tasks_by_state.values():
            for task in tasks:
                if task.id == task_id:
                    return task
        return None

    def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        error: str | None = None,
    ) -> bool:
        """Update a task's state or error."""
        tasks_by_state = self.storage.read_tasks()

        # Find the task and its current state
        current_state = None
        target_task = None

        for s, tasks in tasks_by_state.items():
            for task in tasks:
                if task.id == task_id:
                    current_state = s
                    target_task = task
                    break
            if target_task:
                break

        if not target_task:
            return False

        # Update task fields
        if state and state != target_task.state:
            # Move task to new state list
            if current_state:
                tasks_by_state[current_state].remove(target_task)
            target_task.state = state
            tasks_by_state[state].append(target_task)

        if error:
            target_task.error = error

        self.storage.write_tasks(tasks_by_state)
        return True

    def create_initial_todo(self) -> None:
        """Create an initial empty todo.md file."""
        if not self.todo_file.exists():
            self.storage.write_tasks({state: [] for state in TaskState})
            logger.info(f"Created initial todo.md at {self.todo_file}")
