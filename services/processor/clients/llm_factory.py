from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient
from clients.llm_client import LLMClient

def get_llm_client(provider: str) -> LLMClient:
    if provider.lower() == "openai":
        return OpenAIClient()
    return GeminiClient() # Default to Gemini
