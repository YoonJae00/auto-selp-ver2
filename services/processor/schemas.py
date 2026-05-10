from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Dict

class ProcessRequest(BaseModel):
    file_id: str
    column_mapping: Dict[str, str]
    llm_provider: Optional[str] = "gemini"

class PromptBase(BaseModel):
    template: str
    description: Optional[str] = None

class PromptUpdate(BaseModel):
    template: str
    description: Optional[str] = None

class PromptResponse(PromptBase):
    key: str
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
