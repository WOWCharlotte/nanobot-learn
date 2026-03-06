"""Learn engine for teacher and quiz modes."""

import json
from datetime import datetime
from pathlib import Path

from nanobot.learn.questions import QUESTIONS, get_random_question
from nanobot.learn.types import LearningProgress, QuizRecord, get_progress_file


# 文档路径
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"


def load_docs_content(days: list[str] | None = None) -> str:
    """加载指定Day的文档内容"""
    if days is None:
        days = [f"Day{i}" for i in range(1, 8)]

    content_parts = []
    for day in days:
        doc_path = DOCS_DIR / day
        if not doc_path.exists():
            continue

        # 尝试加载 README.md 或主要文档
        readme = doc_path / "README.md"
        if readme.exists():
            content_parts.append(f"# {day}\n\n{readme.read_text(encoding='utf-8')}")

        # 加载其他 .md 文件
        for md_file in sorted(doc_path.glob("*.md")):
            if md_file.name == "README.md":
                continue
            content_parts.append(f"# {day} - {md_file.stem}\n\n{md_file.read_text(encoding='utf-8')}")

    return "\n\n---\n\n".join(content_parts)


def get_docs_context_for_question(question_id: str) -> str:
    """获取与问题相关的文档上下文"""
    question = next((q for q in QUESTIONS if q.id == question_id), None)
    if not question:
        return load_docs_content()

    # 加载对应Day的文档
    day_num = question.day.replace("Day", "")
    return load_docs_content([f"Day{day_num}"])


class LearnEngine:
    """学习引擎 - 支持老师模式和面试官模式"""

    def __init__(self, mode: str = "teacher"):
        self.mode = mode
        self.current_question: str | None = None
        self.progress = self._load_progress()

    def _load_progress(self) -> LearningProgress:
        """加载学习进度"""
        progress_file = get_progress_file()
        if progress_file.exists():
            try:
                data = json.loads(progress_file.read_text(encoding="utf-8"))
                return LearningProgress(**data)
            except Exception:
                pass
        return LearningProgress(mode=self.mode)

    def _save_progress(self) -> None:
        """保存学习进度"""
        progress_file = get_progress_file()
        progress_file.write_text(
            self.progress.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def start_teacher_mode(self, day: str | None = None) -> str:
        """启动老师模式，返回欢迎消息"""
        self.mode = "teacher"
        self.progress.mode = "teacher"

        days = [day] if day else [f"Day{i}" for i in range(1, 8)]
        docs_content = load_docs_content(days)

        welcome = f"""# 老师模式已启动

我已加载了 {"、".join(days)} 的文档内容，你可以问我关于 Nanobot 技术原理的问题。

**示例问题：**
- Agent Loop 是如何工作的？
- Memory 系统是如何设计的？
- Tool Registry 是如何工作的？

输入 `/mode quiz` 切换到面试官模式
输入 `/exit` 退出学习模式
"""
        return welcome

    def start_quiz_mode(self, day: str | None = None) -> str:
        """启动面试官模式，返回第一个问题"""
        self.mode = "quiz"
        self.progress.mode = "quiz"
        if day:
            self.progress.current_day = day

        question = get_random_question(day=day)
        self.current_question = question.id

        welcome = f"""# 面试官模式已启动

**当前问题 ({question.difficulty.upper()})：**

{question.question}

请输入你的回答，完成后我会给你打分并给出反馈。

**快捷命令：**
- `/mode teacher` - 切换到老师模式
- `/stats` - 查看学习进度
- `/exit` 退出学习模式
"""
        return welcome

    def get_next_question(self, day: str | None = None) -> str:
        """获取下一个问题"""
        question = get_random_question(day=day or self.progress.current_day)
        self.current_question = question.id
        return f"**{question.question}**\n\n难度: {question.difficulty}"

    def evaluate_answer(self, user_answer: str) -> str:
        """评估用户答案并打分"""
        if not self.current_question:
            return "请先启动面试官模式"

        question = next((q for q in QUESTIONS if q.id == self.current_question), None)
        if not question:
            return "问题不存在"

        # 构建评估提示
        evaluation_prompt = f"""你是一个技术面试官。请根据以下问题评估候选人的回答。

## 问题
{question.question}

## 参考答案要点
{question.answer_hint}

## 候选人的回答
{user_answer}

请给出：
1. 分数 (0-100)
2. 优点
3. 需要改进的地方
4. 总体反馈

请用中文回复，格式如下：
```
分数: XX/100

优点:
- ...

需要改进:
- ...

总体反馈:
...
```
"""

        return evaluation_prompt

    def record_answer(self, question_id: str, user_answer: str, score: int, feedback: str) -> None:
        """记录答题结果"""
        record = QuizRecord(
            question_id=question_id,
            user_answer=user_answer,
            score=score,
            feedback=feedback,
            timestamp=datetime.now()
        )
        self.progress.quiz_records.append(record)
        self.progress.total_questions_answered += 1

        # 计算平均分
        total = sum(r.score for r in self.progress.quiz_records)
        self.progress.average_score = total / len(self.progress.quiz_records)

        self._save_progress()

    def get_stats(self) -> str:
        """获取学习统计"""
        progress = self.progress

        stats = f"""# 学习进度统计

- **总答题数**: {progress.total_questions_answered}
- **平均分**: {progress.average_score:.1f}/100
- **当前模式**: {progress.mode}
"""
        if progress.quiz_records:
            stats += "\n## 最近答题记录\n"
            for record in progress.quiz_records[-5:]:
                question = next((q for q in QUESTIONS if q.id == record.question_id), None)
                topic = question.topic if question else "未知"
                stats += f"- {topic}: {record.score}/100 ({record.timestamp.strftime('%Y-%m-%d %H:%M')})\n"

        return stats


def create_learn_engine(mode: str = "teacher") -> LearnEngine:
    """创建学习引擎实例"""
    return LearnEngine(mode=mode)
