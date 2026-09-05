from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта (папка, где лежит bot.py) — на уровень выше пакета app/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    superadmin_ids: set[int]
    db_path: str  # всегда абсолютный путь
    proxy: str | None = None

    @property
    def db_url(self) -> str:
        # Асинхронный движок SQLite; as_posix() — корректный формат пути в URL на Windows
        return f"sqlite+aiosqlite:///{Path(self.db_path).as_posix()}"


def _parse_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                continue
    return ids


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите токен бота."
        )
    proxy = (os.getenv("PROXY") or "").strip() or None

    # Путь к БД делаем абсолютным и привязанным к папке проекта,
    # чтобы файл был один и тот же независимо от того, откуда запущен бот.
    raw_db = os.getenv("DB_PATH", "events.db").strip() or "events.db"
    db_path = Path(raw_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return Config(
        bot_token=token,
        superadmin_ids=_parse_ids(os.getenv("SUPERADMIN_IDS")),
        db_path=str(db_path),
        proxy=proxy,
    )
