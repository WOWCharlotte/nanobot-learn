"""Question bank for learn mode quiz."""

from nanobot.learn.types import QuizQuestion

# 问题库 - 从 Day1-7 文档中提取的面试要点
QUESTIONS: list[QuizQuestion] = [
    # Day1 - 架构与配置
    QuizQuestion(
        id="d1_pydantic_why",
        day="Day1",
        topic="配置系统",
        question="为什么选择 Pydantic 作为配置验证方案？",
        answer_hint="类型安全、自动验证、默认值处理、环境变量支持",
        difficulty="easy",
    ),
    QuizQuestion(
        id="d1_provider_registry",
        day="Day1",
        topic="Provider架构",
        question="Nanobot 的 Provider 注册机制是如何工作的？",
        answer_hint="ProviderSpec、find_by_name、两步添加新provider",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d1_channel_design",
        day="Day1",
        topic="Channel架构",
        question="Channel 系统的设计原则是什么？",
        answer_hint="继承ChannelBase、实现send/start/stop、消息解析",
        difficulty="medium",
    ),
    # Day2 - Agent Loop
    QuizQuestion(
        id="d2_global_lock",
        day="Day2",
        topic="Agent Loop",
        question="为什么 Agent Loop 使用全局锁 _processing_lock？",
        answer_hint="防止并发处理导致会话状态混乱、简化上下文管理",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d2_memory_consolidation",
        day="Day2",
        topic="Agent Loop",
        question="Memory Consolidation 何时触发？",
        answer_hint="unconsolidated >= memory_window（默认100条消息）、异步执行",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d2_stop_command",
        day="Day2",
        topic="Agent Loop",
        question="如何处理 /stop 命令来取消正在执行的 agent？",
        answer_hint="通过 asyncio.Task 追踪活跃任务、取消主任务和所有子agent",
        difficulty="hard",
    ),
    QuizQuestion(
        id="d2_truncate_tool_result",
        day="Day2",
        topic="Agent Loop",
        question="为什么要截断工具结果？截断阈值是多少？",
        answer_hint="防止超过LLM context限制、500字符是合理阈值",
        difficulty="easy",
    ),
    QuizQuestion(
        id="d2_iteration_termination",
        day="Day2",
        topic="Agent Loop",
        question="迭代循环如何终止？",
        answer_hint="LLM无工具调用、达到max_iterations上限、LLM返回错误",
        difficulty="medium",
    ),
    # Day2 - Context
    QuizQuestion(
        id="d2_context_caching",
        day="Day2",
        topic="Context",
        question="Context 的缓存机制是如何工作的？",
        answer_hint="LRU缓存、基于session_key和prompt_cache_key、缓存命中减少token消耗",
        difficulty="hard",
    ),
    QuizQuestion(
        id="d2_system_prompt",
        day="Day2",
        topic="Context",
        question="System Prompt 包含哪些核心指令？",
        answer_hint="workspace限制、工具使用指南、响应格式要求",
        difficulty="medium",
    ),
    # Day3 - Memory
    QuizQuestion(
        id="d3_memory_design",
        day="Day3",
        topic="Memory系统",
        question="Nanobot 的 Memory 系统设计要点是什么？",
        answer_hint="滑动窗口、consolidation、summary持久化",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d3_summary_prompt",
        day="Day3",
        topic="Memory系统",
        question="Memory Consolidation 的 summary prompt 有什么要求？",
        answer_hint="英文提示词、压缩上下文、提取关键信息",
        difficulty="hard",
    ),
    QuizQuestion(
        id="d3_session_manager",
        day="Day3",
        topic="Session管理",
        question="Session Manager 的核心职责是什么？",
        answer_hint="会话列表、消息历史、session创建/删除/查询",
        difficulty="easy",
    ),
    # Day3 - Session
    QuizQuestion(
        id="d3_session_persistence",
        day="Day3",
        topic="Session管理",
        question="Session 数据是如何持久化的？",
        answer_hint="JSON文件存储、workspace目录、会话状态恢复",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d3_session_id_format",
        day="Day3",
        topic="Session管理",
        question="Session ID 的格式是什么？为什么这样设计？",
        answer_hint="channel:chat_id格式、唯一标识跨平台会话",
        difficulty="easy",
    ),
    # Day4 - Tools
    QuizQuestion(
        id="d4_tool_registry",
        day="Day4",
        topic="Tool系统",
        question="Tool Registry 的注册机制是如何工作的？",
        answer_hint="装饰器注册、get_tool方法、动态加载",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d4_shell_tool",
        day="Day4",
        topic="Tool系统",
        question="Shell Tool 的安全机制是什么？",
        answer_hint="restrict_to_workspace、工作区限制、命令白名单/黑名单",
        difficulty="hard",
    ),
    QuizQuestion(
        id="d4_web_tools",
        day="Day4",
        topic="Tool系统",
        question="Web Search 和 Web Fetch 工具的区别是什么？",
        answer_hint="搜索vs抓取、Brave API、BeautifulSoup解析",
        difficulty="easy",
    ),
    # Day4 - Subagent
    QuizQuestion(
        id="d4_subagent_design",
        day="Day4",
        topic="Subagent",
        question="Subagent 的设计目标是什么？",
        answer_hint="专业化任务处理、spawn机制、结果聚合",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d4_subagent_termination",
        day="Day4",
        topic="Subagent",
        question="Subagent 的生命周期如何管理？",
        answer_hint="独立运行、任务完成即终止、父agent负责调度",
        difficulty="hard",
    ),
    # Day4 - Skills
    QuizQuestion(
        id="d4_skills_loader",
        day="Day4",
        topic="Skills",
        question="Skills Loader 的工作流程是什么？",
        answer_hint="目录扫描、manifest.yaml、动态加载",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d4_skill_manifest",
        day="Day4",
        topic="Skills",
        question="Skill manifest.yaml 需要包含哪些字段？",
        answer_hint="name、description、tools、version",
        difficulty="easy",
    ),
    # Day5 - Provider
    QuizQuestion(
        id="d5_litellm",
        day="Day5",
        topic="Provider",
        question="LiteLLM Provider 的主要职责是什么？",
        answer_hint="统一API接口、模型前缀解析、请求转发",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d5_model_prefix",
        day="Day5",
        topic="Provider",
        question="模型前缀 (如 openai/, anthropic/) 的作用是什么？",
        answer_hint="路由到不同provider、provider_name解析",
        difficulty="easy",
    ),
    QuizQuestion(
        id="d5_custom_provider",
        day="Day5",
        topic="Provider",
        question="Custom Provider 适用于什么场景？",
        answer_hint="本地部署、OpenAI兼容API、自定义endpoint",
        difficulty="medium",
    ),
    # Day6 - Channel
    QuizQuestion(
        id="d6_channel_base",
        day="Day6",
        topic="Channel系统",
        question="ChannelBase 的核心方法有哪些？",
        answer_hint="send、start、stop、消息解析、用户识别",
        difficulty="easy",
    ),
    QuizQuestion(
        id="d6_message_bus",
        day="Day6",
        topic="Channel系统",
        question="Message Bus 在 Channel 通信中的作用是什么？",
        answer_hint="解耦channel和agent、pub/sub模式、消息队列",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d6_inbound_outbound",
        day="Day6",
        topic="Channel系统",
        question="InboundMessage 和 OutboundMessage 的区别是什么？",
        answer_hint="入站vs出站、channel/chat_id/sender_id",
        difficulty="easy",
    ),
    # Day7 - CLI & Cron & Heartbeat
    QuizQuestion(
        id="d7_cli_design",
        day="Day7",
        topic="CLI",
        question="CLI 使用 prompt_toolkit 的原因是什么？",
        answer_hint="跨平台、history支持、paste处理、终端兼容性",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d7_cron_service",
        day="Day7",
        topic="Cron",
        question="Cron Service 的核心设计是什么？",
        answer_hint="定时任务执行、job存储、回调机制",
        difficulty="medium",
    ),
    QuizQuestion(
        id="d7_heartbeat",
        day="Day7",
        topic="Heartbeat",
        question="Heartbeat Service 的设计目标是什么？",
        answer_hint="周期性主动执行、定时任务执行、结果通知",
        difficulty="hard",
    ),
    QuizQuestion(
        id="d7_config_schema",
        day="Day7",
        topic="配置",
        question="Pydantic 配置验证的优势是什么？",
        answer_hint="类型检查、自动转换、默认值、嵌套配置",
        difficulty="easy",
    ),
]


def get_questions_by_day(day: str) -> list[QuizQuestion]:
    """获取指定Day的问题"""
    return [q for q in QUESTIONS if q.day == day]


def get_questions_by_topic(topic: str) -> list[QuizQuestion]:
    """获取指定主题的问题"""
    return [q for q in QUESTIONS if q.topic == topic]


def get_random_question(difficulty: str | None = None, day: str | None = None) -> QuizQuestion:
    """随机获取一个问题"""
    import random

    filtered = QUESTIONS
    if difficulty:
        filtered = [q for q in filtered if q.difficulty == difficulty]
    if day:
        filtered = [q for q in filtered if q.day == day]

    if not filtered:
        return random.choice(QUESTIONS)

    return random.choice(filtered)
