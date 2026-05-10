from abc import ABC, abstractmethod

class LLMClient(ABC):
    @abstractmethod
    async def refine_product_name(self, original_name: str) -> str:
        pass
    
    @abstractmethod
    async def generate_synonyms(self, refined_name: str) -> list[str]:
        pass

    @abstractmethod
    async def verify_trademark(self, word: str) -> bool:
        pass
