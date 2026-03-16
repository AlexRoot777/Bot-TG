from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    proxy_host: str
    proxy_port: int
    database_path: str
    proxy_gen_cmd: str | None
    mtproto_start_cmd: str | None


def _parse_admin_ids(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    return Settings(
        bot_token=token,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        proxy_host=os.getenv("PROXY_HOST", "127.0.0.1"),
        proxy_port=int(os.getenv("PROXY_PORT", "443")),
        database_path=os.getenv("DATABASE_PATH", "bot.db"),
        proxy_gen_cmd=os.getenv("PROXY_GEN_CMD", "").strip() or None,
        mtproto_start_cmd=os.getenv("MTPROTO_START_CMD", "").strip() or None,
    )