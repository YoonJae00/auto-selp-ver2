from clients.gemini_client import GeminiClient
from clients.openai_client import OpenAIClient
from clients.llm_client import LLMClient
from utils.prompt_manager import PromptManager

def get_llm_client(provider: str, prompt_manager: PromptManager = None) -> LLMClient:
    if provider.lower() == "openai":
        return OpenAIClient(prompt_manager)
    return GeminiClient(prompt_manager) # Default to Gemini

def get_vision_llm_client(provider: str, prompt_manager: PromptManager = None) -> LLMClient:
    if provider.lower() == "openai":
        return OpenAIClient(prompt_manager, model="gpt-5.6-luna")
    return GeminiClient(prompt_manager, model="gemini-3.1-flash-lite")
