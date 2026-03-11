"""System prompts and few-shot examples for the agent."""

from src.prompts.few_shot import FEW_SHOT_EXAMPLES, get_few_shot_messages
from src.prompts.system import COPILOT_SYSTEM_PROMPT, build_system_prompt

__all__ = [
    "COPILOT_SYSTEM_PROMPT",
    "build_system_prompt",
    "FEW_SHOT_EXAMPLES",
    "get_few_shot_messages",
]
