from __future__ import annotations

import os
from typing import Optional
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # APP_CONFIG_FILE overrides the dotenv file (e.g. unset for keyless/mock
    # tests: APP_CONFIG_FILE=<path-that-does-not-exist> disables .env entirely).
    model_config = SettingsConfigDict(
        env_file=os.environ.get("APP_CONFIG_FILE", ".env"), extra="ignore"
    )

    app_name: str = "Agentic Dev Assistant"
    api_prefix: str = "/api"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""  # set to https://generativelanguage.googleapis.com/v1beta/openai for Gemini

    database_url: str = ""  # empty => local SQLite file
    redis_url: str = ""  # empty => in-memory agent memory

    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    workspace_root: str = "./workspaces"
    execution_timeout: int = 180
    max_debug_attempts: int = 3
    log_level: str = "INFO"

    @property
    def workspace_dir(self) -> Path:
        p = Path(self.workspace_root)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def mock_mode(self) -> bool:
        return not self.openai_api_key.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()