"""
settings.py — Central configuration for the Vedic Astrology AI System.

All environment variables are declared here with types and defaults.
Secrets (API keys, DB URIs) must be set in .env — never hardcoded.

Usage:
    from vedic_astro.settings import settings
    model_name = settings.synthesis_model
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEV     = "development"
    STAGING = "staging"
    PROD    = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─────────────────────────────────────────────────────
    # Application
    # ─────────────────────────────────────────────────────
    environment: Environment = Environment.DEV
    debug: bool = False

    # ─────────────────────────────────────────────────────
    # Swiss Ephemeris
    # ─────────────────────────────────────────────────────
    swisseph_path: str = "ephe"
    default_ayanamsha: str = "lahiri"   # must match AyanamshaType enum value

    # ─────────────────────────────────────────────────────
    # MongoDB
    # ─────────────────────────────────────────────────────
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "vedic_astro"

    # ─────────────────────────────────────────────────────
    # Redis cache
    # ─────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_natal_ttl: int = 0            # 0 = permanent (no expiry)
    cache_transit_slow_ttl: int = 86400 # 24 hours (outer planets)
    cache_transit_moon_ttl: int = 3600  # 1 hour (Moon)
    cache_panchang_ttl: int = 86400     # 24 hours
    cache_llm_response_ttl: int = 604800 # 7 days
    cache_response_ttl: int = 86400     # 24 hours

    # ─────────────────────────────────────────────────────
    # LLM models (per agent role — efficiency strategy)
    # ─────────────────────────────────────────────────────
    synthesis_model: str = "claude-sonnet-4-6"
    critic_model: str = "claude-haiku-4-5-20251001"    # small model for binary PASS/FAIL
    reviser_model: str = "claude-sonnet-4-6"
    natal_agent_model: str = "claude-sonnet-4-6"
    dasha_agent_model: str = "claude-sonnet-4-6"
    transit_agent_model: str = "claude-sonnet-4-6"
    divisional_agent_model: str = "claude-sonnet-4-6"

    # ─────────────────────────────────────────────────────
    # Self-correction thresholds (configurable, NOT hardcoded)
    # ─────────────────────────────────────────────────────
    critic_pass_threshold: float = 0.75     # below this → trigger ReviserAgent
    max_revision_passes: int = 1            # never loop more than once
    synthesis_max_context_tokens: int = 6000

    # ─────────────────────────────────────────────────────
    # Agent token budgets (per agent narrative output)
    # ─────────────────────────────────────────────────────
    natal_agent_max_tokens: int = 600
    dasha_agent_max_tokens: int = 500
    transit_agent_max_tokens: int = 400
    divisional_agent_max_tokens: int = 400
    synthesis_agent_max_tokens: int = 1500
    critic_agent_max_tokens: int = 512

    # ─────────────────────────────────────────────────────
    # Retrograde dignity rule
    # ─────────────────────────────────────────────────────
    retrograde_dignity_rule: str = "none"   # "none" | "kalidasa" | "mantreshwar"

    # ─────────────────────────────────────────────────────
    # Divisional chart formula school
    # ─────────────────────────────────────────────────────
    divisional_school: str = "parashari"    # "parashari" | "jaimini"

    # ─────────────────────────────────────────────────────
    # Geocoding
    # ─────────────────────────────────────────────────────
    opencage_api_key: Optional[str] = None
    geo_cache_ttl: int = 0               # permanent

    # ─────────────────────────────────────────────────────
    # Anthropic API
    # ─────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # ─────────────────────────────────────────────────────
    # LLM backend  ("anthropic" | "ollama")
    # ─────────────────────────────────────────────────────
    llm_backend: str = "anthropic"          # switch to "ollama" to use local models
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2:7b"          # model to use for all agents when backend=ollama

    # ─────────────────────────────────────────────────────
    # Vector store
    # ─────────────────────────────────────────────────────
    vector_store_type: str = "faiss"        # "faiss" | "chromadb"
    faiss_index_path: str = "data/embeddings/cases.index"
    chroma_persist_dir: str = "data/chroma"

    # ─────────────────────────────────────────────────────
    # VedAstro dataset
    # ─────────────────────────────────────────────────────
    vedastro_data_path: str = "data/raw/vedastro"
    classical_texts_path: str = "data/raw/texts"

    @field_validator("critic_pass_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"critic_pass_threshold must be 0.0–1.0, got {v}")
        return v

    @field_validator("retrograde_dignity_rule")
    @classmethod
    def validate_retro_rule(cls, v: str) -> str:
        valid = {"none", "kalidasa", "mantreshwar"}
        if v not in valid:
            raise ValueError(f"retrograde_dignity_rule must be one of {valid}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PROD


# Singleton instance — import this everywhere
settings = Settings()
