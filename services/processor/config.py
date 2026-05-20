from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "yoursecretkeychangeit"
    
    # Platform APIs
    NAVER_API_BASE_URL: str = "https://api.naver.com"
    NAVER_API_KEY: str
    NAVER_SECRET_KEY: str
    NAVER_CUSTOMER_ID: str
    
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    
    Coupang_Access_Key: str
    Coupang_Secret_Key: str
    
    GEMINI_API_KEY: str
    OPENAI_API_KEY: str
    KIPRIS_API_KEY: str
    
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

settings = Settings()
