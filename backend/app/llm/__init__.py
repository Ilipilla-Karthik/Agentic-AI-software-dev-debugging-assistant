from .base import LLMProvider, ToolCall, ToolDef, extract_json, parse_fixed_files
from .mock_provider import MockProvider
from .openai_provider import OpenAIProvider

__all__ = [
    "LLMProvider",
    "MockProvider",
    "OpenAIProvider",
    "ToolCall",
    "ToolDef",
    "extract_json",
    "parse_fixed_files",
    "get_provider",
]


def get_provider() -> LLMProvider:
    from ..config import settings

    if settings.mock_mode:
        return MockProvider()
    return OpenAIProvider()