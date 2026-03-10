"""Task queue service for self-managing AI system."""

import asyncio
import subprocess
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
        use_external: bool = True,  # 默认使用外部 Claude 实例
    ):
        self.workspace = workspace
        self.agent = agent
        self.todo_file = workspace / todo_filename
        self.storage = TaskQueueStorage(self.todo_file)
        self._on_result = on_result
        # 检查 tmux 是否可用
        self._tmux_available = self._check_tmux_available()
        # 如果用户要求外部执行但 tmux 不可用，自动降级
        self.use_external = use_external and self._tmux_available
        if use_external and not self._tmux_available:
            logger.warning(
                "tmux not available, falling back to internal agent execution. "
                "To use external Claude instances, please install tmux."
            )
        # 外部执行模式配置
        self.cases_dir = workspace / "cases"

    def _check_tmux_available(self) -> bool:
        """检查 tmux 是否可用."""
        try:
            result = subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def process_queue(self) -> None:
        """Process pending tasks in the queue."""
        try:
            # Parse current tasks
            tasks_by_state = self.storage.read_tasks()

            # Check status of external running tasks
            if self.use_external:
                await self._check_external_tasks(tasks_by_state)

            # Recover from any crashed RUNNING tasks
            await self._recover_running_tasks(tasks_by_state)

            # Get next executable task
            task = self._get_next_task(tasks_by_state)
            if not task:
                logger.debug("No pending tasks in queue")
                return

            # Execute the task
            if self.use_external:
                await self._execute_task_in_tmux(task)
            else:
                await self._execute_task(task)

        except Exception as e:
            logger.error(f"Error processing task queue: {e}")

    async def _check_external_tasks(self, tasks_by_state: dict[TaskState, list[Task]]) -> None:
        """检查外部运行的任务状态，处理已完成的任务."""
        running_tasks = tasks_by_state.get(TaskState.RUNNING, [])
        if not running_tasks:
            return

        for task in running_tasks:
            await self._handle_external_result(task)

    async def _handle_external_result(self, task: Task) -> None:
        """检查外部任务是否完成，并处理结果."""
        if not task.tmux_session or not task.result_file:
            return

        result_path = Path(task.result_file)

        # 检查结果文件是否存在
        if not result_path.exists():
            # 检查 tmux session 是否还存在
            try:
                result = subprocess.run(
                    ["tmux", "has-session", "-t", task.tmux_session],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    # session 不存在，可能是崩溃了
                    logger.warning(f"tmux session {task.tmux_session} not found, marking as failed")
                    await self._mark_failed(task, "External process terminated unexpectedly")
            except Exception as e:
                logger.error(f"Error checking tmux session: {e}")
            return

        # 读取结果
        try:
            content = result_path.read_text(encoding="utf-8")
            # 解析结果：检查是否包含错误标记
            if content.startswith("[ERROR]"):
                error_msg = content[7:].strip()
                await self._mark_failed(task, error_msg)
            else:
                await self._mark_done(task, content)
        except Exception as e:
            logger.error(f"Error reading result file: {e}")
            await self._mark_failed(task, f"Error reading result: {e}")

    async def _execute_task_in_tmux(self, task: Task) -> None:
        """在 tmux session 中启动外部 Claude 实例执行任务."""
        logger.info(f"Executing task {task.id} in external tmux session: {task.title}")

        # 1. 创建工作目录
        # 如果指定了 case_dir，使用 cases/{case_dir}，否则使用 cases/{task_id}
        if task.case_dir:
            task_workspace = self.cases_dir / task.case_dir
        else:
            task_workspace = self.cases_dir / task.id
        task_workspace.mkdir(parents=True, exist_ok=True)

        # 2. 写入任务指令到 PRD.md
        prd_file = task_workspace / "PRD.md"
        prd_file.write_text(task.instructions, encoding="utf-8")

        # 3. 创建结果文件路径
        result_file = str(task_workspace / ".result.md")

        # 4. 更新任务状态为 RUNNING (需要从 PENDING 移动到 RUNNING 列表)
        tasks_by_state = self.storage.read_tasks()

        # Find and remove from PENDING list
        moved_task = None
        for i, t in enumerate(tasks_by_state[TaskState.PENDING]):
            if t.id == task.id:
                # Update task state
                t.state = TaskState.RUNNING
                t.started_at = datetime.now()
                t.tmux_session = f"{self.TMUX_SESSION_PREFIX}{t.id}"
                t.workspace = str(task_workspace)
                t.result_file = result_file
                moved_task = t
                # Remove from PENDING list
                tasks_by_state[TaskState.PENDING].pop(i)
                break

        # Add to RUNNING list if found
        if moved_task:
            tasks_by_state[TaskState.RUNNING].append(moved_task)
            task = moved_task

        self.storage.write_tasks(tasks_by_state)

        # 5. 启动 tmux session
        tmux_session = task.tmux_session

        try:
            # 检查 session 是否已存在
            check_result = subprocess.run(
                ["tmux", "has-session", "-t", tmux_session],
                capture_output=True,
                text=True,
            )
            if check_result.returncode == 0:
                # session 已存在，先杀掉
                logger.info(f"tmux session {tmux_session} already exists, killing it first")
                subprocess.run(["tmux", "kill-session", "-t", tmux_session], capture_output=True)
                await asyncio.sleep(0.5)

            # 构建 claude 命令
            claude_params = task.claude_params
            cmd = f"cd {task_workspace} && claude {claude_params}"

            # 创建新的 tmux session 并启动 claude
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", tmux_session],
                capture_output=True,
                check=True,
            )
            # 发送命令到 tmux session
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, cmd, "C-m"],
                capture_output=True,
                check=True,
            )

            logger.info(f"Started tmux session {tmux_session} for task {task.id}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start tmux session: {e}")
            await self._mark_failed(task, f"Failed to start tmux session: {e}")
        except FileNotFoundError:
            # tmux 命令未找到，回退到内部执行
            logger.error("tmux not found, falling back to internal agent execution")
            self.use_external = False
            # 在内部执行任务
            await self._execute_task(task)
        except Exception as e:
            logger.error(f"Error executing task in tmux: {e}")
            await self._mark_failed(task, str(e))

    async def _recover_running_tasks(self, tasks_by_state: dict[TaskState, list[Task]]) -> None:
        """Recover from crashed tasks that were RUNNING."""
        running_tasks = tasks_by_state.get(TaskState.RUNNING, [])
        if not running_tasks:
            return

        # Only recover truly crashed tasks (has tmux_session but session doesn't exist)
        tasks_to_recover = []
        for task in running_tasks:
            if not task.tmux_session:
                # No tmux_session means internal execution task, can recover
                tasks_to_recover.append(task)
                continue

            # Check if tmux session still exists
            try:
                result = subprocess.run(
                    ["tmux", "has-session", "-t", task.tmux_session],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    # Session doesn't exist, task crashed
                    logger.info(f"Found crashed task {task.id}, session {task.tmux_session} not found")
                    tasks_to_recover.append(task)
                # else: session exists, task is running normally, skip
            except Exception:
                # On error, don't recover by default
                pass

        if not tasks_to_recover:
            return

        logger.info(f"Recovering {len(tasks_to_recover)} crashed RUNNING tasks")

        for task in tasks_to_recover:
            task.state = TaskState.PENDING
            task.started_at = None
            task.tmux_session = None
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

        # Update task state to RUNNING (need to move from PENDING to RUNNING list)
        tasks_by_state = self.storage.read_tasks()

        # Find and remove from PENDING list
        moved_task = None
        for i, t in enumerate(tasks_by_state[TaskState.PENDING]):
            if t.id == task.id:
                t.state = TaskState.RUNNING
                t.started_at = datetime.now()
                t.tmux_session = f"{self.TMUX_SESSION_PREFIX}{t.id}"
                moved_task = t
                # Remove from PENDING list
                tasks_by_state[TaskState.PENDING].pop(i)
                break

        # Add to RUNNING list if found
        if moved_task:
            tasks_by_state[TaskState.RUNNING].append(moved_task)
            task = moved_task

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
        case_dir: str = "",
        claude_params: str = "",
    ) -> Task:
        """Add a new task to the queue.

        Args:
            title: 任务标题
            instructions: 任务指令（会写入 PRD.md）
            priority: 优先级
            case_dir: case 目录名（如 "case1"），会创建为 cases/{case_dir}
            claude_params: 额外 claude 参数
        """
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
            case_dir=case_dir or None,
            claude_params=claude_params,
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
