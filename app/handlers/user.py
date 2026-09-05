from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from .. import keyboards as kb
from ..db import crud
from ..db.models import Event, Location, User
from ..utils import format_event, format_location, format_schedule_line, month_bounds, week_bounds
from .eventform import start_event_form

router = Router(name="user")


async def _send_events(target: Message, session: AsyncSession, user: User, events: list[Event], empty: str) -> None:
    if not events:
        await target.answer(empty)
        return
    await target.answer(f"Найдено мероприятий: <b>{len(events)}</b>")
    for event in events:
        is_fav = await crud.is_favorite(session, user.id, event.id)
        await target.answer(format_event(event), reply_markup=kb.event_fav_kb(event, is_fav))


# ---------- Мероприятия ----------

@router.message(F.text == kb.BTN_EVENTS)
async def all_events(message: Message, session: AsyncSession, user: User) -> None:
    events = await crud.list_events(session, only_upcoming=True)
    await _send_events(message, session, user, events, "Пока нет предстоящих мероприятий.")


# ---------- Избранное ----------

@router.message(F.text == kb.BTN_FAVORITES)
async def favorites(message: Message, session: AsyncSession, user: User) -> None:
    events = await crud.list_favorite_events(session, user.id)
    await _send_events(message, session, user, events, "В избранном пока пусто. Отметьте ❤️ понравившиеся мероприятия.")


@router.callback_query(F.data.startswith("fav:toggle:"))
async def toggle_fav(call: CallbackQuery, session: AsyncSession, user: User) -> None:
    event_id = int(call.data.split(":")[2])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие уже удалено.", show_alert=True)
        return
    now_fav = await crud.toggle_favorite(session, user.id, event_id)
    await call.message.edit_reply_markup(reply_markup=kb.event_fav_kb(event, now_fav))
    await call.answer("Добавлено в избранное ❤️" if now_fav else "Убрано из избранного")


# ---------- Расписание: комбинируемые фильтры (дата + жанры + локация) ----------

_DATE_LABELS = {
    "any": "все предстоящие",
    "today": "сегодня",
    "week": "на этой неделе",
    "month": "в этом месяце",
}

_MAX_LIST = 40  # сколько мероприятий показываем одним сообщением


async def _get_filter(state: FSMContext) -> dict:
    data = await state.get_data()
    return {
        "date": data.get("sf_date", "any"),
        "genres": list(data.get("sf_genres", [])),  # список id
        "loc": data.get("sf_loc"),                   # id или None
    }


async def _filter_labels(session: AsyncSession, flt: dict) -> tuple[str, str, str]:
    date_label = _DATE_LABELS.get(flt["date"], "все предстоящие")

    gids = flt["genres"]
    if not gids:
        genre_label = "любые"
    else:
        genres = await crud.list_genres(session)
        names = [g.name for g in genres if g.id in set(gids)]
        genre_label = ", ".join(names) if len(names) <= 3 else f"выбрано: {len(names)}"

    loc_label = "любая"
    if flt["loc"]:
        loc = await session.get(Location, flt["loc"])
        loc_label = loc.name if loc else "любая"
    return date_label, genre_label, loc_label


async def _render_builder(target: Message, state: FSMContext, session: AsyncSession, edit: bool) -> None:
    flt = await _get_filter(state)
    d, g, l = await _filter_labels(session, flt)
    text = "📅 <b>Расписание</b>\nНастройте фильтры и нажмите «Показать»."
    markup = kb.schedule_builder_kb(d, g, l)
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


async def _events_for_filter(session: AsyncSession, flt: dict) -> list[Event]:
    today = dt.date.today()
    date_from = date_to = None
    if flt["date"] == "today":
        date_from = date_to = today
    elif flt["date"] == "week":
        date_from, date_to = week_bounds(today)
    elif flt["date"] == "month":
        start, date_to = month_bounds(today)
        date_from = max(start, today)
    return await crud.list_events(
        session,
        genre_ids=flt["genres"] or None,
        location_id=flt["loc"],
        date_from=date_from,
        date_to=date_to,
    )


async def _build_schedule_view(session: AsyncSession, flt: dict, bot_username: str) -> str:
    events = (await _events_for_filter(session, flt))[:_MAX_LIST]
    d, g, l = await _filter_labels(session, flt)
    header = f"Фильтр — дата: {d}; жанры: {g}; локация: {l}"
    if not events:
        return f"📅 <b>Расписание</b>\n{header}\n\nПо заданным фильтрам ничего не найдено."
    lines = [format_schedule_line(e, bot_username) for e in events]
    return (
        f"📅 <b>Расписание</b> ({len(events)})\n{header}\n\n"
        + "\n".join(lines)
        + "\n\n<i>Нажмите на название мероприятия, чтобы открыть карточку.</i>"
    )


@router.message(F.text == kb.BTN_SCHEDULE)
async def schedule(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _render_builder(message, state, session, edit=False)


@router.callback_query(F.data == "sf:back")
async def sf_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await _render_builder(call.message, state, session, edit=True)
    await call.answer()


@router.callback_query(F.data == "sf:reset")
async def sf_reset(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.update_data(sf_date="any", sf_genres=[], sf_loc=None)
    await _render_builder(call.message, state, session, edit=True)
    await call.answer("Фильтры сброшены")


@router.callback_query(F.data == "sf:datemenu")
async def sf_datemenu(call: CallbackQuery) -> None:
    await call.message.edit_text("🗓 Выберите период:", reply_markup=kb.schedule_date_kb())
    await call.answer()


@router.callback_query(F.data == "sf:genremenu")
async def sf_genremenu(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    genres = await crud.list_genres(session)
    if not genres:
        await call.answer("Жанры ещё не заведены.", show_alert=True)
        return
    flt = await _get_filter(state)
    await call.message.edit_text(
        "🎭 Отметьте жанры (можно несколько), затем «Готово»:",
        reply_markup=kb.schedule_genres_kb(genres, set(flt["genres"])),
    )
    await call.answer()


@router.callback_query(F.data == "sf:locmenu")
async def sf_locmenu(call: CallbackQuery, session: AsyncSession) -> None:
    locations = await crud.list_locations(session)
    await call.message.edit_text("📍 Выберите локацию:", reply_markup=kb.schedule_loc_kb(locations))
    await call.answer()


@router.callback_query(F.data.startswith("sf:setdate:"))
async def sf_setdate(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.update_data(sf_date=call.data.split(":")[2])
    await _render_builder(call.message, state, session, edit=True)
    await call.answer()


@router.callback_query(F.data.startswith("sf:tg:"))
async def sf_toggle_genre(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    gid = int(call.data.split(":")[2])
    flt = await _get_filter(state)
    selected = set(flt["genres"])
    selected.symmetric_difference_update({gid})
    await state.update_data(sf_genres=list(selected))
    genres = await crud.list_genres(session)
    await call.message.edit_reply_markup(reply_markup=kb.schedule_genres_kb(genres, selected))
    await call.answer()


@router.callback_query(F.data.startswith("sf:setloc:"))
async def sf_setloc(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    value = call.data.split(":")[2]
    await state.update_data(sf_loc=None if value == "any" else int(value))
    await _render_builder(call.message, state, session, edit=True)
    await call.answer()


@router.callback_query(F.data == "sf:show")
async def sf_show(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    flt = await _get_filter(state)
    me = await call.bot.me()
    text = await _build_schedule_view(session, flt, me.username)
    await call.answer()
    msg = await call.message.answer(text, disable_web_page_preview=True)
    # запоминаем сообщение со списком, чтобы обновлять его после правок/удаления
    await state.update_data(sf_list_chat=msg.chat.id, sf_list_msg=msg.message_id)


async def refresh_schedule_message(bot, state: FSMContext, session: AsyncSession) -> None:
    """Перерисовывает ранее показанное сообщение-расписание (если оно есть)."""
    data = await state.get_data()
    chat_id = data.get("sf_list_chat")
    msg_id = data.get("sf_list_msg")
    if not chat_id or not msg_id:
        return
    flt = await _get_filter(state)
    me = await bot.me()
    text = await _build_schedule_view(session, flt, me.username)
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=msg_id, disable_web_page_preview=True
        )
    except Exception:
        # сообщение могло быть удалено/устареть — не критично
        pass


# --- Карточка мероприятия (открывается по #ID из расписания) ---

async def send_event_card(target: Message, session: AsyncSession, user: User, is_admin: bool, event) -> None:
    is_fav = await crud.is_favorite(session, user.id, event.id)
    me = await target.bot.me()
    await target.answer(
        format_event(event, admin=is_admin, bot_username=me.username),
        reply_markup=kb.event_detail_kb(event, is_fav, is_admin),
        disable_web_page_preview=True,
    )


async def send_location_card(target: Message, is_admin: bool, location) -> None:
    await target.answer(
        format_location(location),
        reply_markup=kb.location_detail_kb(location, is_admin),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("efav:"))
async def detail_fav(call: CallbackQuery, session: AsyncSession, user: User, is_admin: bool) -> None:
    event_id = int(call.data.split(":")[1])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие уже удалено.", show_alert=True)
        return
    now_fav = await crud.toggle_favorite(session, user.id, event_id)
    await call.message.edit_reply_markup(reply_markup=kb.event_detail_kb(event, now_fav, is_admin))
    await call.answer("Добавлено в избранное ❤️" if now_fav else "Убрано из избранного")


@router.callback_query(F.data.startswith("edel:"))
async def detail_del(call: CallbackQuery, session: AsyncSession, user: User, is_admin: bool) -> None:
    if not is_admin:
        await call.answer("Недостаточно прав.", show_alert=True)
        return
    event_id = int(call.data.split(":")[1])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие уже удалено.", show_alert=True)
        return
    await call.message.edit_reply_markup(
        reply_markup=kb.event_detail_kb(event, False, is_admin, confirm_delete=True)
    )
    await call.answer("Подтвердите удаление")


@router.callback_query(F.data.startswith("edelno:"))
async def detail_del_no(call: CallbackQuery, session: AsyncSession, user: User, is_admin: bool) -> None:
    event_id = int(call.data.split(":")[1])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer()
        return
    is_fav = await crud.is_favorite(session, user.id, event_id)
    await call.message.edit_reply_markup(reply_markup=kb.event_detail_kb(event, is_fav, is_admin))
    await call.answer("Отменено")


@router.callback_query(F.data.startswith("edelyes:"))
async def detail_del_yes(call: CallbackQuery, state: FSMContext, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        await call.answer("Недостаточно прав.", show_alert=True)
        return
    event_id = int(call.data.split(":")[1])
    await crud.delete_event(session, event_id)
    await call.message.edit_text("🗑 Мероприятие удалено.")
    await refresh_schedule_message(call.bot, state, session)
    await call.answer("Удалено")


# ---------- Напоминания ----------

@router.message(F.text == kb.BTN_NOTIFY)
async def notify_settings(message: Message, user: User) -> None:
    await message.answer(
        "🔔 <b>Напоминания</b>\n\n"
        "Я напомню о мероприятиях из вашего <b>избранного</b>. "
        "Отметьте, за сколько предупреждать (можно несколько):",
        reply_markup=kb.notify_kb(user),
    )


@router.callback_query(F.data.startswith("ntf:"))
async def notify_toggle(call: CallbackQuery, session: AsyncSession, user: User) -> None:
    which = call.data.split(":")[1]
    if which == "week":
        user.notify_week = not user.notify_week
    elif which == "day":
        user.notify_day = not user.notify_day
    elif which == "sameday":
        user.notify_sameday = not user.notify_sameday
    await session.commit()
    await call.message.edit_reply_markup(reply_markup=kb.notify_kb(user))
    await call.answer("Сохранено")


# ---------- Предложить / Добавить мероприятие ----------

@router.message(F.text == kb.BTN_SUGGEST)
async def suggest(message: Message, state: FSMContext) -> None:
    await start_event_form(message, state, mode="suggest")


@router.message(F.text == kb.BTN_ADD)
async def add_event_btn(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not is_admin:
        return
    await start_event_form(message, state, mode="admin")
