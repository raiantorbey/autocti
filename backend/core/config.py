"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values come from .env / environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- App ----
    app_name: str = "AutoCTI"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ---- Security ----
    jwt_secret: str = Field(default="change-me-in-prod-32bytes-min!!")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    bcrypt_rounds: int = 12
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ---- Postgres ----
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "autocti"
    postgres_password: str = "autocti_pw"
    postgres_db: str = "autocti"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---- Neo4j ----
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "autocti_neo4j"

    # ---- Redis ----
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ---- Chroma ----
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "autocti_incidents"

    # ---- Ollama ----
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "llama3"

    # ---- External APIs (all optional — mock mode if missing) ----
    virustotal_api_key: str = ""
    abuseipdb_api_key: str = ""
    shodan_api_key: str = ""
    geoip_api_key: str = ""  # ipinfo.io token
    # WHOIS uses python-whois (no key)

    # ---- ML ----
    model_dir: str = "/app/data/models"
    dataset_dir: str = "/app/data/datasets"
    embedding_model: str = "all-MiniLM-L6-v2"

    # ---- Risk weights (Risk = αS + βE + γC) ----
    risk_alpha: float = 0.5  # severity
    risk_beta: float = 0.3   # enrichment / exposure
    risk_gamma: float = 0.2  # correlation / context


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
