from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import crud
from ..db.models import EventStatus, User
from ..keyboards import main_menu
from .user import send_event_card, send_location_card

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    is_admin: bool,
) -> None:
    # Deep-link: /start event_<id> — карточка мероприятия, /start loc_<id> — карточка площадки
    payload = (command.args or "").strip()
    if payload.startswith("event_"):
        try:
            eid = int(payload[len("event_"):])
        except ValueError:
            eid = None
        event = await crud.get_event(session, eid) if eid else None
        if event and event.status == EventStatus.approved:
            await send_event_card(message, session, user, is_admin, event)
            return
        await message.answer("Мероприятие не найдено или снято с расписания.",
                             reply_markup=main_menu(is_admin))
        return
    if payload.startswith("loc_"):
        try:
            lid = int(payload[len("loc_"):])
        except ValueError:
            lid = None
        location = await crud.get_location(session, lid) if lid else None
        if location:
            await send_location_card(message, is_admin, location)
            return
        await message.answer("Площадка не найдена.", reply_markup=main_menu(is_admin))
        return

    await state.clear()
    hello = (
        f"👋 Привет, {user.full_name or 'друг'}!\n\n"
        "Я бот-афиша: веду расписание мероприятий и напоминаю о том, "
        "что тебе интересно!\n\n"
        "• 🎫 Мероприятия — смотреть все предстоящие\n"
        "• 📅 Расписание — фильтр по дате, жанру, локации\n"
        "• ❤️ Избранное — что ты отметил\n"
        "• ➕ Предложить мероприятие — добавить своё (после модерации)\n"
        "• 🔔 Напоминания — за сколько предупреждать\n"
    )
    if is_admin:
        hello += "\n🛠 Тебе доступна админ-панель."
    await message.answer(hello, reply_markup=main_menu(is_admin))


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool) -> None:
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "Пользуйтесь кнопками меню внизу.\n"
        "/cancel — отменить текущее действие\n"
        "/myid — узнать свой Telegram ID\n"
    )
    if is_admin:
        text += (
            "\n<b>Админ-панель:</b>\n"
            "• жанры, локации, мероприятия, модерация предложенного;\n"
            "• 👥 Пользователи — назначение/снятие админов и бан пользователей.\n\n"
            "<b>Админ-команды:</b>\n"
            "/broadcast — ответьте этой командой на любое сообщение, "
            "и оно будет разослано всем пользователям бота.\n"
        )
    await message.answer(text, reply_markup=main_menu(is_admin))


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>")


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext, is_admin: bool) -> None:
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer("Нечего отменять.", reply_markup=main_menu(is_admin))
    else:
        await message.answer("❌ Действие отменено.", reply_markup=main_menu(is_admin))
