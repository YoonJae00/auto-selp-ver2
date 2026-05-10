from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "autoselp"
    DATABASE_URL: str = "postgresql+asyncpg://admin:password@db:5432/autoselp"
    SECRET_KEY: str = "yoursecretkeychangeit"
    ENCRYPTION_KEY: str = "D_Y7_n9_Z-w6Dt8ZPpgBKjTV0mNXB-OJp8HrCc="
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
