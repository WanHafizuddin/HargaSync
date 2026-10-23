"""Settings read from environment variables (Replit Secrets or a local .env)."""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

AI_MODES = ("runpod", "fixture", "off")
PLACEHOLDER_SECRETS = {"change-me", "changeme", "secret"}
MIN_SECRET_LENGTH = 16


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    secret_key: str
    ai_mode: str
    runpod_api_key: str
    runpod_endpoint_id: str
    demo_seed: bool
    demo_password: str
    https_only: bool


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    secret_key = os.getenv("HARGASYNC_SECRET_KEY", "").strip()
    if secret_key in PLACEHOLDER_SECRETS or len(secret_key) < MIN_SECRET_LENGTH:
        secret_key = secrets.token_urlsafe(32)
        print(
            "WARNING: HARGASYNC_SECRET_KEY is missing, too short or a placeholder; "
            "using a random key (sessions reset on restart)."
        )
    runpod_api_key = os.getenv("RUNPOD_API_KEY", "")
    runpod_endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "")
    default_mode = "runpod" if runpod_api_key and runpod_endpoint_id else "fixture"
    ai_mode = os.getenv("AI_MODE", default_mode).strip().lower()
    if ai_mode not in AI_MODES:
        raise ValueError(f"AI_MODE must be one of {AI_MODES}, got {ai_mode!r}")
    return Settings(
        data_dir=Path(os.getenv("HARGASYNC_DATA_DIR", "data")),
        secret_key=secret_key,
        ai_mode=ai_mode,
        runpod_api_key=runpod_api_key,
        runpod_endpoint_id=runpod_endpoint_id,
        demo_seed=_flag("DEMO_SEED", True),
        demo_password=os.getenv("DEMO_PASSWORD", "demo1234"),
        https_only=_flag("HTTPS_ONLY", False),
    )
