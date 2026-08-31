"""App settings (pydantic-settings). Override via env vars prefixed RTG_."""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent  # rtg-tracker-build/


class Settings(BaseSettings):
    app_name: str = "TwinWorks"
    # data source: 'snapshot' (offline JSON) or 'live' (IFS MCP over OAuth)
    data_source: str = "snapshot"
    ifs_mcp_url: str = "https://ifs-mcp-auth.prod.azure.gd-ms.us/mcp"
    # LLM adapter for WI extraction: 'claude' (ai-critic MCP) or 'gpt' (when available)
    llm_provider: str = "claude"
    wis_dir: Path = BASE_DIR / "wis"
    data_dir: Path = BASE_DIR / "data"
    database_url: str = f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'rtg_app_migrated.db').as_posix()}"
    # port the app runs on — the OAuth callback must come back to THIS port
    app_port: int = 8000
    # ML: forward scored ships (per program) before the trained model replaces empirical bias.
    # Per-program because Aegis (~5 WIP units) would never reach 25 on its own.
    n_train_threshold: dict[str, int] = {"ELEV": 25, "RAD": 25, "AEGIS": 12}
    n_train_threshold_default: int = 25   # fallback for any unlisted program
    # cleaned-dwell feature: fall back to raw dwell if the cleaner misbehaves
    use_cleaned_dwell: bool = True
    # program config source: 'db' (program table, default) or 'routers' (hardcoded fallback).
    # Rollback lever during the add-program migration — flip to 'routers' to ignore the DB.
    program_source: str = "db"
    # Resource model: legacy remains authoritative until shadow parity and owner gates pass.
    resource_source: str = "legacy"  # legacy | db-shadow | db-active
    # Fernet key for encrypting OAuth tokens at rest (generate one for prod)
    token_encryption_key: str = ""
    log_level: str = "INFO"

    model_config = {"env_prefix": "RTG_", "extra": "ignore"}


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
