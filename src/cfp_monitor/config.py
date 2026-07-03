"""Runtime settings + budget/boundary control (feat 11).

Reads secrets from the environment (.env supported via python-dotenv). Every knob
that affects cost or crawl size lives here so runs are predictable and debuggable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional: load a local .env if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


@dataclass
class Settings:
    # --- LLM extraction (LiteLLM provider string + key) ---
    # Reuses the same OpenRouter key/model pattern as the rest of the stack.
    llm_provider: str = os.getenv("CFP_LLM_PROVIDER", "openrouter/deepseek/deepseek-chat")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    llm_temperature: float = float(os.getenv("CFP_LLM_TEMPERATURE", "0.0"))
    llm_max_tokens: int = int(os.getenv("CFP_LLM_MAX_TOKENS", "1400"))
    chunk_token_threshold: int = int(os.getenv("CFP_CHUNK_TOKENS", "1400"))

    # --- Crawl budget & boundaries (per conference) ---
    max_depth: int = int(os.getenv("CFP_MAX_DEPTH", "2"))
    max_pages: int = int(os.getenv("CFP_MAX_PAGES", "12"))
    include_external: bool = os.getenv("CFP_INCLUDE_EXTERNAL", "false").lower() == "true"
    per_site_timeout_s: int = int(os.getenv("CFP_SITE_TIMEOUT_S", "180"))
    # How many of the top-scored discovered pages to run LLM extraction on.
    max_extract_pages: int = int(os.getenv("CFP_MAX_EXTRACT_PAGES", "8"))

    # --- Behaviour ---
    headless: bool = os.getenv("CFP_HEADLESS", "true").lower() != "false"
    verbose: bool = os.getenv("CFP_VERBOSE", "false").lower() == "true"

    # --- Popup / consent handling (crawl4ai NATIVE; on by default) ---
    # Conference sites routinely sit behind a GDPR "Manage Consent" (IAB TCF/CMP)
    # modal + a promo overlay that block the page. crawl4ai removes both natively
    # before extracting HTML — no custom click-Accept automation required.
    remove_consent_popups: bool = os.getenv("CFP_REMOVE_CONSENT", "true").lower() != "false"
    remove_overlay_elements: bool = os.getenv("CFP_REMOVE_OVERLAYS", "true").lower() != "false"
    # `magic` is a broader auto-handler — heavier/less predictable, so opt-in.
    crawl_magic: bool = os.getenv("CFP_CRAWL_MAGIC", "false").lower() == "true"

    def require_llm_key(self) -> None:
        if self.llm_provider.startswith(("openrouter/", "openai/", "anthropic/")) and not self.openrouter_api_key:
            raise RuntimeError(
                "No LLM API key. Set OPENROUTER_API_KEY (or switch CFP_LLM_PROVIDER to an "
                "ollama/* local model that needs no key). See .env.example."
            )


DEFAULT = Settings()
