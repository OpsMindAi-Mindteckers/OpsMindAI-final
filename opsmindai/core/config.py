# from pydantic_settings import BaseSettings, SettingsConfigDict

# class Settings(BaseSettings):
#     CLERK_SECRET_KEY: str
#     CLERK_PUBLISHABLE_KEY: str
#     CLERK_FRONTEND_API: str  # e.g. https://amazing-cat-42.clerk.accounts.dev
#     DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

#     model_config = SettingsConfigDict(env_file=".env", extra="ignore")

#     @property
#     def CLERK_JWKS_URL(self) -> str:
#         return f"{self.CLERK_FRONTEND_API}/.well-known/jwks.json"

#     @property
#     def CLERK_ISSUER(self) -> str:
#         return self.CLERK_FRONTEND_API

# settings = Settings()











from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ── Clerk auth ────────────────────────────────────────────────────────────
    CLERK_SECRET_KEY:       str
    CLERK_PUBLISHABLE_KEY:  str
    CLERK_FRONTEND_API:     str   # e.g. https://amazing-cat-42.clerk.accounts.dev

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://default:UlZV4uuiRwNdx3uEAJJBTVqJN3e3CG8j@redis-17963.c261.us-east-1-4.ec2.cloud.redislabs.com:17963/0"

    # ── Celery (defaults to same Redis instance) ──────────────────────────────
    CELERY_BROKER_URL:    str = ""   # falls back to REDIS_URL if empty
    CELERY_RESULT_BACKEND: str = ""  # falls back to REDIS_URL if empty

    # ── LLM — local ───────────────────────────────────────────────────────────
    LOCAL_MODEL_NAME:  str   = "qwen2.5-coder:32b"
    OLLAMA_BASE_URL:   str   = "http://localhost:11434"
    CONFIDENCE_THRESHOLD: float = 0.80   # route to cloud below this

    # ── LLM — cloud ───────────────────────────────────────────────────────────
    CLOUD_LLM_PROVIDER: str = "anthropic"   # anthropic | openai
    ANTHROPIC_API_KEY:  str = ""
    OPENAI_API_KEY:     str = ""

    # ── Vector store ──────────────────────────────────────────────────────────
    VECTOR_STORE:   str = "chromadb"              # chromadb | qdrant
    CHROMADB_PATH:  str = "./data/chroma"
    QDRANT_URL:     str = "http://localhost:6333"

    # ── Monitoring ────────────────────────────────────────────────────────────
    PROMETHEUS_URL: str = "http://localhost:9090"
    LOKI_URL:       str = "http://localhost:3100"
    GRAFANA_URL:    str = "http://localhost:3000"

    # ── Alerting / notifications ──────────────────────────────────────────────
    SLACK_WEBHOOK_URL:        str = ""
    PAGERDUTY_ROUTING_KEY:    str = ""
    INCIDENT_WEBHOOK_SECRET:  str = ""   # HMAC secret for /incidents/ingest

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_TOKEN:          str = ""
    GITHUB_WEBHOOK_SECRET: str = ""
    REFACTOR_BRANCH_PREFIX: str = "opsmind/refactor"
    REFACTOR_DEFAULT_REPO_URL: str = ""  # used by post-incident refactor dispatch

    # ── App ───────────────────────────────────────────────────────────────────
    API_SECRET_KEY:     str = ""          # min 32 chars in production
    LOG_LEVEL:          str = "INFO"
    KUBECTL_NAMESPACE:  str = "default"
    COVERAGE_THRESHOLD: float = 0.80
    ADMIN_USER_IDS:     str = ""          # comma-separated Clerk user IDs

    # ── SLO thresholds (used by remediation_executor) ─────────────────────────
    SLO_P99_LATENCY_MS: float = 1000.0
    SLO_ERROR_RATE:     float = 0.01

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",         # ignore unknown env vars — safe for all envs
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def CLERK_JWKS_URL(self) -> str:
        return f"{self.CLERK_FRONTEND_API}/.well-known/jwks.json"

    @property
    def CLERK_ISSUER(self) -> str:
        return self.CLERK_FRONTEND_API

    @property
    def effective_broker_url(self) -> str:
        """Celery broker — falls back to REDIS_URL if CELERY_BROKER_URL not set."""
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def effective_result_backend(self) -> str:
        """Celery result backend — falls back to REDIS_URL if not set."""
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL


settings = Settings()