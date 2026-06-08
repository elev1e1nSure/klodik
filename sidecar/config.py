"""Configuration for the sidecar application.

Loads settings from environment variables and a `.env` file.
Validates provider-specific keys dynamically.
"""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from the project root (one level up from sidecar/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


class Settings(BaseSettings):
    """Application settings with multi-provider validation."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = Field(
        default="groq",
        alias="PROVIDER",
        description="LLM provider: groq, openai, gemini, ollama",
    )
    model: str = Field(
        default="groq/llama-3.3-70b-versatile",
        alias="MODEL",
        description="Model identifier (provider-prefixed for litellm)",
    )

    groq_api_key: str | None = Field(
        default=None,
        alias="GROQ_API_KEY",
        description="Groq API key",
    )
    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="OpenAI API key",
    )
    gemini_api_key: str | None = Field(
        default=None,
        alias="GEMINI_API_KEY",
        description="Google Gemini API key",
    )
    openrouter_api_key: str | None = Field(
        default=None,
        alias="OPENROUTER_API_KEY",
        description="OpenRouter API key",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
        description="OpenRouter API base URL",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
        description="Ollama API base URL",
    )

    temperature: float = Field(
        default=0.7,
        alias="TEMPERATURE",
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature",
    )
    max_tokens: int = Field(
        default=512,
        alias="MAX_TOKENS",
        ge=1,
        le=8192,
        description="Maximum tokens per response",
    )
    ws_port: int = Field(
        default=8765,
        alias="WS_PORT",
        ge=1024,
        le=65535,
        description="WebSocket server port",
    )
    memory_db_path: str = Field(
        default="sidecar/memory.db",
        alias="MEMORY_DB_PATH",
        description="Path to SQLite memory database",
    )

    @model_validator(mode="after")
    def check_provider_key(self):
        p = self.provider.lower()
        if p == "groq":
            if not self.groq_api_key:
                raise ValueError("GROQ_API_KEY is required for provider 'groq'")
            if not self.groq_api_key.startswith("gsk_"):
                raise ValueError("GROQ_API_KEY must start with 'gsk_'")
        elif p == "openai":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for provider 'openai'")
        elif p == "gemini":
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required for provider 'gemini'")
        elif p == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required for provider 'openrouter'")
        elif p == "ollama":
            if not self.model.startswith("ollama/"):
                self.model = f"ollama/{self.model}"
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
        return self


settings = Settings()

