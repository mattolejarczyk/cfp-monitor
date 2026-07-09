"""Runtime settings + budget/boundary control (feat 11).

Reads secrets from the environment (.env supported via python-dotenv). Every knob
that affects cost or crawl size lives here so runs are predictable and debuggable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional: load a local .env if present
    from dotenv import load_dotenv

    # utf-8-sig tolerates a UTF-8 BOM (Windows editors / PowerShell Set-Content add one, which
    # would otherwise corrupt the FIRST variable name and silently drop it).
    load_dotenv(encoding="utf-8-sig")
except Exception:  # pragma: no cover - dotenv is optional
    pass


# Bumped when we ship a customer build; the proxy can refuse versions below a per-license floor.
CLIENT_VERSION = "1.0.0"


@dataclass
class Settings:
    # --- LLM extraction (LiteLLM provider string + key) ---
    # Reuses the same OpenRouter key/model pattern as the rest of the stack.
    llm_provider: str = os.getenv("CFP_LLM_PROVIDER", "openrouter/deepseek/deepseek-chat")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    llm_temperature: float = float(os.getenv("CFP_LLM_TEMPERATURE", "0.0"))
    llm_max_tokens: int = int(os.getenv("CFP_LLM_MAX_TOKENS", "1400"))
    chunk_token_threshold: int = int(os.getenv("CFP_CHUNK_TOKENS", "1400"))

    # --- Licensing (Option D: vendor-controlled LLM proxy = kill switch + token metering) ---
    # In a CUSTOMER build these are set and OPENROUTER_API_KEY is NOT: extraction is routed to the
    # vendor's proxy authenticated with the license key. Revoking the key stops crawling. When
    # llm_proxy_url is empty (dev / vendor machine), extraction calls the provider directly as before.
    llm_proxy_url: str | None = os.getenv("CFP_LLM_PROXY_URL")
    license_key: str | None = os.getenv("CFP_LICENSE_KEY")
    client_version: str = os.getenv("CFP_CLIENT_VERSION", CLIENT_VERSION)

    # --- Crawl budget & boundaries (per conference) ---
    max_depth: int = int(os.getenv("CFP_MAX_DEPTH", "2"))
    max_pages: int = int(os.getenv("CFP_MAX_PAGES", "12"))
    include_external: bool = os.getenv("CFP_INCLUDE_EXTERNAL", "false").lower() == "true"
    per_site_timeout_s: int = int(os.getenv("CFP_SITE_TIMEOUT_S", "180"))
    # Cap the crawl4ai PRIMARY attempt so a slow/blocked page fails fast, leaving budget
    # for the Playwright fallback (a doomed crawl4ai attempt can otherwise eat 60-90s).
    primary_page_timeout_s: int = int(os.getenv("CFP_PRIMARY_TIMEOUT_S", "35"))
    # How many of the top-scored discovered pages to run LLM extraction on.
    max_extract_pages: int = int(os.getenv("CFP_MAX_EXTRACT_PAGES", "8"))
    # Fraction of the per-site budget the CRAWL may use before stopping to leave time for
    # extraction. Prevents link-heavy sites from timing out with the homepage never extracted.
    explore_budget_fraction: float = float(os.getenv("CFP_EXPLORE_FRACTION", "0.6"))

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

    # --- Playwright fallback fetch ---
    # crawl4ai's browser sometimes captures a slow JS site's early loading shell and
    # its anti-bot detector false-flags "no <body>" (verified: Complianz/WordPress conf
    # sites like ushydrogenforum.com). For those we render with our OWN Playwright,
    # dismiss the cookie-consent banner (the real blocker), wait for content, then feed
    # the rendered HTML to crawl4ai (raw://) for markdown.
    playwright_fallback: bool = os.getenv("CFP_PW_FALLBACK", "true").lower() != "false"
    # Fallback runs HEADED by default: headless browsers get 403'd by some platforms
    # (verified: Reuters Events / OneTrust). Headed also fits the "you'll see the browser" model.
    fallback_headless: bool = os.getenv("CFP_FALLBACK_HEADLESS", "false").lower() == "true"
    fallback_wait_s: float = float(os.getenv("CFP_FALLBACK_WAIT_S", "8"))
    # Hard cap on the fallback render's page load (Playwright-native, so it actually
    # interrupts). Keeps a slow render from consuming the whole per-site budget.
    fallback_render_timeout_s: int = int(os.getenv("CFP_FALLBACK_RENDER_S", "45"))
    # CDP: drive a REAL Chrome via its debug port (beats IP-reputation anti-bot like
    # Reuters — verified). Launch Chrome with scripts/launch_chrome_cdp.bat, then set
    # CFP_CDP_URL=http://localhost:9222 (or a ws:// url). When set, the fallback ATTACHES
    # to that real (ideally signed-in) browser instead of launching its own headless/headed one.
    cdp_url: str | None = os.getenv("CFP_CDP_URL")

    def require_llm_key(self) -> None:
        # Customer build: extraction goes through the licensed proxy, so a license key is what's
        # required (the provider key lives only on the vendor's proxy).
        if self.llm_proxy_url:
            if not self.license_key:
                raise RuntimeError(
                    "No license key. Set CFP_LICENSE_KEY (provided with your subscription). "
                    "Without an active license the monitor cannot run."
                )
            return
        # Dev / vendor build: talk to the provider directly. Supports both OpenAI and OpenRouter.
        if self.llm_provider.startswith("openai/") and not self.openai_api_key:
            raise RuntimeError("No OpenAI API key. Set OPENAI_API_KEY in your .env (or switch "
                               "CFP_LLM_PROVIDER to an openrouter/* model).")
        if self.llm_provider.startswith("openrouter/") and not self.openrouter_api_key:
            raise RuntimeError("No OpenRouter API key. Set OPENROUTER_API_KEY in your .env (or switch "
                               "CFP_LLM_PROVIDER to an openai/* model with OPENAI_API_KEY).")

    def provider_key(self) -> str | None:
        """The right provider key for the configured model (OpenAI vs OpenRouter)."""
        return self.openai_api_key if self.llm_provider.startswith("openai/") else self.openrouter_api_key


DEFAULT = Settings()
