"""
Central configuration for ULTRON Commerce.

All business-critical limits (budgets, autonomy mode, approval thresholds) live
here and in the `operating_policies` DB table -- NOT inside agent prompts or
agent code. Agents read these values; they cannot write to the enforced ones.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Identity / auth ---
    app_name: str = "ULTRON Commerce"
    secret_key: str = "CHANGE_ME_INSECURE_DEV_SECRET_DO_NOT_USE_IN_PRODUCTION"
    access_token_expire_minutes: int = 60 * 12
    owner_email: str = "owner@example.com"
    # bcrypt hash of a dev-only default password "ultron-dev-only".
    # MUST be rotated via the /auth/change-password flow before any real deployment.
    owner_password_hash: str = "$2b$12$w.a/2RLclw1gwE.fXCdSs.H3X/OrbNBf8x6dsRTR8emJO93O5FSNC"

    # --- Database ---
    database_url: str = f"sqlite:///{(BASE_DIR / 'ultron.db').as_posix()}"

    # --- Autonomy & operating mode ---
    autonomy_mode: Literal["SUPERVISED", "HYBRID", "AUTONOMOUS"] = "SUPERVISED"

    # --- Budget defaults (section 23) ---
    startup_budget_ceiling_usd: float = 1000.00
    monthly_ai_budget_usd: float = 150.00
    monthly_image_gen_budget_usd: float = 50.00
    advertising_budget_usd: float = 0.00  # disabled until explicitly authorized
    advertising_enabled: bool = False
    max_spend_per_action_usd: float = 25.00
    max_spend_per_workflow_usd: float = 75.00
    max_concurrent_agent_jobs: int = 3
    max_retries_per_task: int = 3
    daily_product_generation_limit: int = 5

    # --- AI providers (left blank => agents run in MOCK_LLM mode) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    default_model_routine: str = "claude-haiku-4-5-20251001"
    default_model_complex: str = "claude-opus-5"

    # --- Marketplace integrations (left blank => adapters run in MOCK mode) ---
    etsy_api_key: str | None = None
    etsy_api_secret: str | None = None
    etsy_shop_id: str | None = None
    etsy_oauth_redirect_uri: str = "http://localhost:8000/integrations/etsy/callback"
    frontend_base_url: str = "http://localhost:3000"

    printify_api_token: str | None = None
    printful_api_token: str | None = None

    shopify_store_domain: str | None = None
    shopify_admin_api_token: str | None = None

    # --- Notifications ---
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    notify_email: str | None = None

    @property
    def etsy_configured(self) -> bool:
        return bool(self.etsy_api_key and self.etsy_api_secret and self.etsy_shop_id)

    @property
    def printify_configured(self) -> bool:
        return bool(self.printify_api_token)

    @property
    def printful_configured(self) -> bool:
        return bool(self.printful_api_token)

    @property
    def shopify_configured(self) -> bool:
        return bool(self.shopify_store_domain and self.shopify_admin_api_token)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
