from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import crud


class DataMiddleware(BaseMiddleware):
    """Открывает сессию БД на каждое обновление и подкладывает запись пользователя."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        superadmin_ids: set[int],
    ) -> None:
        self.sessionmaker = sessionmaker
        self.superadmin_ids = superadmin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # event — это Message или CallbackQuery (middleware навешан на эти observers)
        tg_user = getattr(event, "from_user", None)
        async with self.sessionmaker() as session:
            data["session"] = session
            data["superadmin_ids"] = self.superadmin_ids
            if tg_user is not None and not tg_user.is_bot:
                user = await crud.get_or_create_user(
                    session,
                    tg_user.id,
                    tg_user.username,
                    tg_user.full_name,
                    self.superadmin_ids,
                )
                # Забаненные пользователи полностью игнорируются
                if user.is_banned and user.id not in self.superadmin_ids:
                    return None
                data["user"] = user
                data["is_admin"] = user.is_admin
            else:
                data["user"] = None
                data["is_admin"] = False
            return await handler(event, data)
