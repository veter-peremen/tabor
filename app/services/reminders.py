from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..db import crud
from ..utils import format_event

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # секунд

# Насколько заранее срабатывает каждый тип напоминания
LEAD = {
    "week": dt.timedelta(days=7),
    "day": dt.timedelta(days=1),
}


def _human_left(delta: dt.timedelta) -> str:
    total_min = int(delta.total_seconds() // 60)
    days, rem = divmod(total_min, 60 * 24)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes and not days:
        parts.append(f"{minutes} мин.")
    return " ".join(parts) or "меньше минуты"


async def _run_once(bot: Bot, sessionmaker: async_sessionmaker) -> None:
    now = dt.datetime.now()
    async with sessionmaker() as session:
        rows = await crud.upcoming_favorites_with_users(session, now)
        for _fav, user, event in rows:
            starts = event.starts_at
            if starts <= now:
                continue

            due_kinds: list[str] = []
            if user.notify_week and now >= starts - LEAD["week"]:
                due_kinds.append("week")
            if user.notify_day and now >= starts - LEAD["day"]:
                due_kinds.append("day")
            if user.notify_sameday and now.date() == event.date:
                due_kinds.append("sameday")

            for kind in due_kinds:
                if await crud.reminder_already_sent(session, user.id, event.id, kind):
                    continue
                text = (
                    f"🔔 <b>Напоминание</b>\nДо начала: {_human_left(starts - now)}\n\n"
                    + format_event(event)
                )
                try:
                    await bot.send_message(user.id, text)
                    await crud.mark_reminder_sent(session, user.id, event.id, kind)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Не удалось отправить напоминание %s: %s", user.id, exc)


async def reminder_loop(bot: Bot, sessionmaker: async_sessionmaker) -> None:
    logger.info("Планировщик напоминаний запущен")
    while True:
        try:
            await _run_once(bot, sessionmaker)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка в цикле напоминаний: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL)
