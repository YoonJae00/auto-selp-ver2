from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient
from clients.llm_base import LLMClient

def get_llm_client(provider: str = "gemini") -> LLMClient:
    """
    LLM 공급자(Gemini, OpenAI)에 따른 클라이언트 팩토리
    """
    if provider.lower() == "openai":
        return OpenAIClient()
    return GeminiClient()
