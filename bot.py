from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import ErrorEvent

from app.config import load_config
from app.db.session import create_all, get_sessionmaker, init_engine
from app.handlers import admin, common, eventform, user
from app.middlewares import DataMiddleware
from app.services.reminders import reminder_loop

# Безвредные ошибки Telegram, которые не должны засорять логи и ронять апдейт
_BENIGN = (
    "message is not modified",
    "message to edit not found",
    "message can't be edited",
    "query is too old",
    "message to delete not found",
)


async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    text = str(exc)
    if isinstance(exc, TelegramBadRequest) and any(s in text for s in _BENIGN):
        return True  # игнорируем — пользователь просто повторил действие
    logging.getLogger("bot.errors").exception("Необработанная ошибка в хендлере: %s", exc)
    return True  # апдейт «обработан», бот продолжает работать


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    config = load_config()

    init_engine(config.db_url)
    await create_all()
    sessionmaker = get_sessionmaker()

    # Показываем, какой именно файл БД используется и сколько в нём записей —
    # чтобы сразу видеть, что данные на месте и открыт правильный файл.
    from sqlalchemy import func, select
    from app.db.models import Event, Genre, Location, User

    async with sessionmaker() as _s:
        counts = {
            "мероприятий": await _s.scalar(select(func.count()).select_from(Event)),
            "жанров": await _s.scalar(select(func.count()).select_from(Genre)),
            "локаций": await _s.scalar(select(func.count()).select_from(Location)),
            "пользователей": await _s.scalar(select(func.count()).select_from(User)),
        }
    logging.getLogger(__name__).info("База данных: %s", config.db_path)
    logging.getLogger(__name__).info(
        "В базе: %s", ", ".join(f"{k} — {v}" for k, v in counts.items())
    )

    # Необязательный прокси (если Telegram недоступен напрямую): PROXY в .env
    session = AiohttpSession(proxy=config.proxy) if config.proxy else None
    if config.proxy:
        logging.getLogger(__name__).info("Использую прокси для Telegram API")
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher()

    # Инъекция сессии БД и пользователя во все хендлеры.
    # ВАЖНО: именно outer-middleware — он выполняется до проверки фильтров,
    # поэтому is_admin/session уже доступны фильтрам (например, IsAdmin).
    middleware = DataMiddleware(sessionmaker, config.superadmin_ids)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)

    # Глобальный обработчик ошибок: гасит безвредные ошибки Telegram и логирует прочие
    dp.errors.register(on_error)

    # Порядок важен: сначала общие команды, затем eventform (FSM), потом остальное
    dp.include_router(common.router)
    dp.include_router(eventform.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    log = logging.getLogger(__name__)

    # Предполётная проверка связи с Telegram — понятная подсказка вместо traceback
    try:
        me = await bot.get_me()
    except TelegramNetworkError:
        log.error(
            "\n" + "=" * 64 + "\n"
            "❌ Не удаётся подключиться к Telegram (api.telegram.org).\n"
            "   Интернет есть, но доступ к Telegram заблокирован.\n\n"
            "   Что делать:\n"
            "   • включите VPN и запустите бота снова, ЛИБО\n"
            "   • пропишите прокси в .env:  PROXY=socks5://user:pass@host:port\n"
            "     (для socks5:  .\\.venv\\Scripts\\python.exe -m pip install aiohttp-socks)\n"
            + "=" * 64
        )
        await bot.session.close()
        return

    log.info("Авторизация успешна: @%s (id=%s)", me.username, me.id)

    # Фоновый планировщик напоминаний
    asyncio.create_task(reminder_loop(bot, sessionmaker))

    log.info("Бот запускается (long polling)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
