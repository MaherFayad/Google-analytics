"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables with validation.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable loading."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    
    # Environment
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    
    # Database
    DATABASE_URL: str = Field(
        description="PostgreSQL connection URL (via pgBouncer)"
    )
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379")
    
    # OpenAI
    OPENAI_API_KEY: str = Field(description="OpenAI API key for embeddings and LLM")
    
    # Google OAuth & GA4
    GOOGLE_CLIENT_ID: str = Field(description="Google OAuth client ID")
    GOOGLE_CLIENT_SECRET: str = Field(description="Google OAuth client secret")
    
    # NextAuth
    NEXTAUTH_SECRET: str = Field(description="NextAuth.js secret (min 32 chars)")
    NEXTAUTH_URL: str = Field(default="http://localhost:3000")
    
    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"]
    )
    
    # Monitoring
    SENTRY_DSN: str = Field(default="")
    
    # API Configuration
    API_V1_PREFIX: str = Field(default="/api/v1")
    API_SECRET: str = Field(
        default="development-secret",
        description="Shared secret for NextAuth → FastAPI communication"
    )
    
    @field_validator("NEXTAUTH_SECRET")
    @classmethod
    def validate_nextauth_secret(cls, v: str) -> str:
        """Ensure NextAuth secret is at least 32 characters."""
        if len(v) < 32:
            raise ValueError("NEXTAUTH_SECRET must be at least 32 characters")
        return v
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


# Global settings instance
settings = Settings()

