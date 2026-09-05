from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import crud
from ..db.models import EventStatus, User
from ..keyboards import (
    main_menu,
    moderation_kb,
    pick_genres_kb,
    pick_location_kb,
)
from ..states import EventForm
from ..utils import format_event, parse_date, parse_time

router = Router(name="eventform")


async def start_event_form(message: Message, state: FSMContext, mode: str) -> None:
    """mode: 'admin' (сразу в расписание) или 'suggest' (на модерацию)."""
    await state.clear()
    await state.set_state(EventForm.title)
    await state.update_data(mode=mode)
    await message.answer(
        "📝 <b>Новое мероприятие</b>\n\nВведите <b>название</b>:\n\n"
        "(отправьте /cancel для отмены)"
    )


@router.message(EventForm.title, F.text)
async def form_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if len(title) < 2:
        await message.answer("Слишком короткое название, попробуйте ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(EventForm.date)
    await message.answer("Введите <b>дату</b> в формате ДД.ММ.ГГГГ (например 25.12.2026):")


@router.message(EventForm.date, F.text)
async def form_date(message: Message, state: FSMContext) -> None:
    date = parse_date(message.text)
    if not date:
        await message.answer("Не понял дату. Формат: ДД.ММ.ГГГГ, например 25.12.2026:")
        return
    await state.update_data(date=date.isoformat())
    await state.set_state(EventForm.time)
    await message.answer("Введите <b>время</b> в формате ЧЧ:ММ (например 19:30):")


@router.message(EventForm.time, F.text)
async def form_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    time = parse_time(message.text)
    if not time:
        await message.answer("Не понял время. Формат: ЧЧ:ММ, например 19:30:")
        return
    await state.update_data(time=time.isoformat(), genre_ids=[])
    genres = await crud.list_genres(session)
    await state.set_state(EventForm.genre)
    await message.answer(
        "Выберите <b>жанры</b> (можно несколько), затем нажмите «Готово»:",
        reply_markup=pick_genres_kb(genres, set()),
    )


@router.callback_query(EventForm.genre, F.data.startswith("fg:t:"))
async def form_genre_toggle(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    gid = int(call.data.split(":")[2])
    data = await state.get_data()
    selected = set(data.get("genre_ids", []))
    selected.symmetric_difference_update({gid})
    await state.update_data(genre_ids=list(selected))
    genres = await crud.list_genres(session)
    await call.message.edit_reply_markup(reply_markup=pick_genres_kb(genres, selected))
    await call.answer()


@router.callback_query(EventForm.genre, F.data == "fg:done")
async def form_genre_done(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    locations = await crud.list_locations(session)
    await state.set_state(EventForm.location)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("Выберите <b>локацию</b>:", reply_markup=pick_location_kb(locations))
    await call.answer()


@router.callback_query(EventForm.location, F.data.startswith("pick:loc:"))
async def form_location(call: CallbackQuery, state: FSMContext) -> None:
    loc_id = int(call.data.split(":")[2])
    await state.update_data(location_id=loc_id or None)
    await state.set_state(EventForm.link)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        "Отправьте <b>ссылку</b> на мероприятие (или /skip, чтобы пропустить):"
    )
    await call.answer()


@router.message(EventForm.link, F.text == "/skip")
async def form_link_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(link=None)
    await state.set_state(EventForm.description)
    await message.answer("Введите <b>описание</b> (или /skip, чтобы пропустить):")


@router.message(EventForm.link, F.text)
async def form_link(message: Message, state: FSMContext) -> None:
    await state.update_data(link=message.text.strip())
    await state.set_state(EventForm.description)
    await message.answer("Введите <b>описание</b> (или /skip, чтобы пропустить):")


@router.message(EventForm.description, F.text == "/skip")
async def form_desc_skip(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.update_data(description=None)
    await _finish(message, state, session, user)


@router.message(EventForm.description, F.text)
async def form_desc(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.update_data(description=message.text.strip())
    await _finish(message, state, session, user)


async def _finish(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    import datetime as dt

    data = await state.get_data()
    await state.clear()

    mode = data.get("mode", "admin")
    status = EventStatus.approved if mode == "admin" else EventStatus.pending

    event = await crud.create_event(
        session,
        genre_ids=data.get("genre_ids") or [],
        title=data["title"],
        date=dt.date.fromisoformat(data["date"]),
        time=dt.time.fromisoformat(data["time"]),
        location_id=data.get("location_id"),
        link=data.get("link"),
        description=data.get("description"),
        status=status,
        suggested_by=user.id if mode == "suggest" else None,
    )

    if mode == "admin":
        await message.answer(
            "✅ Мероприятие добавлено в расписание:\n\n" + format_event(event, admin=True),
            reply_markup=main_menu(True),
        )
    else:
        await message.answer(
            "✅ Спасибо! Ваше мероприятие отправлено на модерацию администраторам.\n\n"
            + format_event(event),
            reply_markup=main_menu(user.is_admin),
        )
        await _notify_admins(message, session, event, user)


async def _notify_admins(message: Message, session: AsyncSession, event, suggester: User) -> None:
    admins = await crud.get_admins(session)
    who = f"@{suggester.username}" if suggester.username else suggester.full_name or suggester.id
    text = (
        f"🆕 <b>Пользователь предложил мероприятие</b>\nОт: {who}\n\n"
        + format_event(event, admin=True)
    )
    for admin in admins:
        try:
            await message.bot.send_message(
                admin.id, text, reply_markup=moderation_kb(event.id)
            )
        except Exception:
            continue
