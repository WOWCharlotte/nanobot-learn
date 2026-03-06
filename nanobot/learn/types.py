"""Data types for learn mode."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class QuizQuestion(BaseModel):
    """面试问题"""

    id: str
    day: str  # 来源 Day1-Day7
    topic: str  # 主题
    question: str
    answer_hint: str  # 参考答案要点
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizRecord(BaseModel):
    """用户答题记录"""

    question_id: str
    user_answer: str
    score: int  # 0-100
    feedback: str  # 优化建议
    timestamp: datetime


class LearningProgress(BaseModel):
    """学习进度"""

    mode: Literal["teacher", "quiz"]
    current_day: str | None = None
    quiz_records: list[QuizRecord] = []
    total_questions_answered: int = 0
    average_score: float = 0.0


def get_progress_file() -> Path:
    """Get the path to the learning progress file."""
    from nanobot.config.loader import get_data_dir

    progress_dir = get_data_dir() / "learn"
    progress_dir.mkdir(parents=True, exist_ok=True)
    return progress_dir / "progress.json"
