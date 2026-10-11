from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (prefix-free) or a .env file.

    Settings that also appear in More → Admin are listed in services/appsettings.py (LOCKABLE).
    Setting one of those here locks it: the value is written to the database at every start and
    the admin panel can't change it until the variable is removed. Empty values count as unset.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    public_url: str = "http://localhost:8080"
    secret_key: str = "change-me"
    data_dir: Path = Path("./data")
    database_url: str | None = None
    static_dir: Path | None = None
    geo_dir: Path | None = None

    # Auth
    local_login_enabled: bool = True
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_admin_group: str | None = None
    oidc_auto_create: bool = True
    oidc_link_by_email: bool = True
    oidc_button_label: str = "Pocket ID"
    session_days: int = 30

    # OCR / VLM
    ocr_detector_model: str = "yolo-v9-s-608-license-plate-end2end"
    ocr_model: str = "cct-s-v2-global-model"
    ocr_detector_conf: float = 0.3
    ollama_url: str = "http://127.0.0.1:11434"
    vlm_model: str = "qwen3-vl:8b"
    vlm_timeout: float = 120.0
    # *_DEFAULT is only the starting value (still changeable in the panel); VLM_MODE / OCR_THRESHOLD lock it.
    vlm_mode_default: Literal["auto", "always", "off"] = "auto"
    ocr_threshold_default: int = Field(85, ge=50, le=99)
    vlm_mode: Literal["auto", "always", "off"] | None = None
    ocr_threshold: int | None = Field(None, ge=50, le=99)

    # Map tiles (OpenFreeMap by default; point these at self-hosted styles for an offline setup)
    map_style_light: str = "https://tiles.openfreemap.org/styles/positron"
    map_style_dark: str = "https://tiles.openfreemap.org/styles/dark"

    # Uploads
    max_upload_mb: int = Field(25, ge=1, le=500)
    import_dir: Path | None = None
    import_user: str | None = None

    # iCloud link to the iOS Shortcut (README → iOS Shortcut)
    shortcut_url: str | None = None

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'platedex.db').resolve()}"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
