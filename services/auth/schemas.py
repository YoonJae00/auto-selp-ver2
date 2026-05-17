from pydantic import BaseModel, ConfigDict
import uuid

class UserBase(BaseModel):
    username: str
    nickname: str | None = None
    is_admin: bool = False

class UserCreate(UserBase):
    password: str | None = None
    admin_secret_key: str | None = None
    provider: str = "local"
    provider_id: str | None = None

class UserResponse(UserBase):
    id: uuid.UUID
    provider: str
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
