from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    PROCESSOR_BASE_URL: str = "http://processor:8002"
    INTERNAL_SERVICE_TOKEN: str

    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")


settings = Settings()
