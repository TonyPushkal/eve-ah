"""Validated configuration; environment overrides values in the local .env file."""

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class BotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(default="eve-ah", min_length=1, max_length=80)
    welcome: str = Field(default="Ask a question. Find the source.", max_length=300)
    instructions: str = Field(default="Answer clearly and concisely.", max_length=4000)
    mode: Literal["knowledge", "general"] = "knowledge"
    min_score: float = Field(default=0.3, ge=-1, le=1)
    top_k: int = Field(default=4, ge=1, le=20)
    chunk_tokens: int = Field(default=200, ge=16, le=2048)
    chunk_overlap: int = Field(default=32, ge=0)
    context_chars: int = Field(default=12000, ge=1000, le=40000)

    @model_validator(mode="after")
    def check_overlap(self):
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError("chunk_overlap must be smaller than chunk_tokens")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["gemini", "openai"] = "gemini"
    model: str = Field(default="gemini-2.5-flash", pattern=r"^[A-Za-z0-9._-]+$", max_length=100)
    api_key: SecretStr = SecretStr("")
    data_dir: Path = Path("data")
    storage_dir: Path = Path("storage")
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_tokens: int = Field(default=1024, ge=32, le=8192)
    timeout: float = Field(default=30, gt=0, le=120)
    max_file_bytes: int = Field(default=10_000_000, ge=1, le=100_000_000)
    max_corpus_bytes: int = Field(default=50_000_000, ge=1, le=500_000_000)
    max_pages: int = Field(default=200, ge=1, le=2000)
    bot: BotConfig = Field(default_factory=BotConfig)

    def require_key(self):
        if not self.api_key.get_secret_value() or self.api_key.get_secret_value() == "replace-with-your-api-key":
            raise ValueError("Set EVE_API_KEY in .env before starting the chat server.")


def load_settings(root: Path | None = None) -> Settings:
    root = (root or Path.cwd()).resolve()
    values = {**dotenv_values(root / ".env"), **os.environ}
    fields = {}
    for name in Settings.model_fields:
        key = "EVE_" + name.upper()
        if name != "bot" and key in values:
            fields[name] = values[key]
    if fields.get("provider") == "openai" and "model" not in fields:
        fields["model"] = "gpt-4.1-mini"
    for name in ("data_dir", "storage_dir"):
        path = Path(fields.get(name, "data" if name == "data_dir" else "storage"))
        fields[name] = (root / path).resolve()
    config_path = root / values.get("EVE_BOT_CONFIG", "bot.yaml")
    if config_path.exists():
        if config_path.stat().st_size > 65536:
            raise ValueError("Bot configuration exceeds 64 KB.")
        fields["bot"] = BotConfig.model_validate(yaml.safe_load(config_path.read_text()) or {})
    return Settings.model_validate(fields)
