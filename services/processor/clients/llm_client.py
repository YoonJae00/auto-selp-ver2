from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    async def refine_product_name(self, original_name: str) -> str:
        pass

    @abstractmethod
    async def get_synonyms(self, refined_name: str) -> list[str]:
        pass
