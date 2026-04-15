from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    CLERK_SECRET_KEY: str
    CLERK_PUBLISHABLE_KEY: str
    CLERK_FRONTEND_API: str  # e.g. https://amazing-cat-42.clerk.accounts.dev
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def CLERK_JWKS_URL(self) -> str:
        return f"{self.CLERK_FRONTEND_API}/.well-known/jwks.json"

    @property
    def CLERK_ISSUER(self) -> str:
        return self.CLERK_FRONTEND_API

settings = Settings()