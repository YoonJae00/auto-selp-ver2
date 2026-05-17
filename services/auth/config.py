from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "autoselp"
    DATABASE_URL: str = "postgresql+asyncpg://admin:password@db:5432/autoselp"
    SECRET_KEY: str = "yoursecretkeychangeit"
    ENCRYPTION_KEY: str = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="
    
    # Base URL for redirects (Frontend URL)
    BASE_URL: str = "http://localhost:3000"
    
    # Backend Public URL (Gateway)
    BACKEND_URL: str = "http://localhost"
    
    # Admin Security
    ADMIN_SECRET_KEY: str = "admin_secret_123"
    
    # OAuth Settings
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Google redirects to the BACKEND callback
    GOOGLE_REDIRECT_URI: str = "{BACKEND_URL}/api/auth/google/callback"
    
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    # Naver redirects to the BACKEND callback
    NAVER_REDIRECT_URI: str = "{BACKEND_URL}/api/auth/naver/callback"
    
    @property
    def google_redirect_uri(self) -> str:
        return self.GOOGLE_REDIRECT_URI.format(BACKEND_URL=self.BACKEND_URL)
    
    @property
    def naver_redirect_uri(self) -> str:
        return self.NAVER_REDIRECT_URI.format(BACKEND_URL=self.BACKEND_URL)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
