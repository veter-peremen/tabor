from __future__ import annotations

import asyncio
import datetime as dt

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .. import keyboards as kb
from ..db import crud
from ..db.models import Event, EventStatus, User
from ..states import EditEventForm, GenreForm, LocationEditForm, LocationForm
from ..utils import format_event, format_location, parse_date, parse_time
from .eventform import start_event_form
from .user import refresh_schedule_message

router = Router(name="admin")


class IsAdmin(BaseFilter):
    async def __call__(self, event, is_admin: bool = False) -> bool:
        return bool(is_admin)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ---------- Панель ----------

@router.message(F.text == kb.BTN_ADMIN)
async def admin_panel(message: Message) -> None:
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_menu())


@router.callback_query(F.data == "adm:addevent")
async def adm_addevent(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await start_event_form(call.message, state, mode="admin")


# ---------- Жанры ----------

def _genre_list_kb(genres) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🗑 {g.name}", callback_data=f"gen:del:{g.id}")]
        for g in genres
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить жанр", callback_data="gen:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:genres")
async def adm_genres(call: CallbackQuery, session: AsyncSession) -> None:
    genres = await crud.list_genres(session)
    text = "🎭 <b>Жанры</b>\nНажмите на жанр, чтобы удалить."
    if not genres:
        text = "🎭 <b>Жанры</b>\nПока пусто."
    await call.message.edit_text(text, reply_markup=_genre_list_kb(genres))
    await call.answer()


@router.callback_query(F.data == "gen:add")
async def gen_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GenreForm.name)
    await call.message.answer("Введите название жанра (/cancel — отмена):")
    await call.answer()


@router.message(GenreForm.name, F.text)
async def gen_add_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    genre = await crud.add_genre(session, message.text.strip())
    if genre is None:
        await message.answer("Такой жанр уже существует.", reply_markup=kb.admin_menu())
    else:
        await message.answer(f"✅ Жанр «{genre.name}» добавлен.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("gen:del:"))
async def gen_del(call: CallbackQuery, session: AsyncSession) -> None:
    genre_id = int(call.data.split(":")[2])
    await crud.delete_genre(session, genre_id)
    genres = await crud.list_genres(session)
    text = "🎭 <b>Жанры</b>\nНажмите на жанр, чтобы удалить." if genres else "🎭 <b>Жанры</b>\nПока пусто."
    await call.message.edit_text(text, reply_markup=_genre_list_kb(genres))
    await call.answer("Удалено")


# ---------- Локации ----------

def _location_list_kb(locations) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🗑 {loc.name}", callback_data=f"loc:del:{loc.id}")]
        for loc in locations
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить локацию", callback_data="loc:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:locations")
async def adm_locations(call: CallbackQuery, session: AsyncSession) -> None:
    locations = await crud.list_locations(session)
    text = "📍 <b>Локации</b>\nНажмите, чтобы удалить." if locations else "📍 <b>Локации</b>\nПока пусто."
    await call.message.edit_text(text, reply_markup=_location_list_kb(locations))
    await call.answer()


@router.callback_query(F.data == "loc:add")
async def loc_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LocationForm.name)
    await call.message.answer("Название локации (/cancel — отмена):")
    await call.answer()


@router.message(LocationForm.name, F.text)
async def loc_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(LocationForm.address)
    await message.answer("Адрес (или /skip):")


@router.message(LocationForm.address, F.text)
async def loc_address(message: Message, state: FSMContext) -> None:
    value = None if message.text.strip() == "/skip" else message.text.strip()
    await state.update_data(address=value)
    await state.set_state(LocationForm.social_link)
    await message.answer("Ссылка на соцсеть (или /skip):")


@router.message(LocationForm.social_link, F.text)
async def loc_social(message: Message, state: FSMContext) -> None:
    value = None if message.text.strip() == "/skip" else message.text.strip()
    await state.update_data(social_link=value)
    await state.set_state(LocationForm.age_limit)
    await message.answer("Возрастное ограничение (например 18+) или /skip:")


@router.message(LocationForm.age_limit, F.text)
async def loc_age(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = None if message.text.strip() == "/skip" else message.text.strip()
    data = await state.get_data()
    await state.clear()
    loc = await crud.add_location(
        session,
        name=data["name"],
        address=data.get("address"),
        social_link=data.get("social_link"),
        age_limit=value,
    )
    if loc is None:
        await message.answer("Локация с таким названием уже есть.", reply_markup=kb.admin_menu())
    else:
        await message.answer(f"✅ Локация «{loc.name}» добавлена.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("loc:del:"))
async def loc_del(call: CallbackQuery, session: AsyncSession) -> None:
    loc_id = int(call.data.split(":")[2])
    await crud.delete_location(session, loc_id)
    locations = await crud.list_locations(session)
    text = "📍 <b>Локации</b>\nНажмите, чтобы удалить." if locations else "📍 <b>Локации</b>\nПока пусто."
    await call.message.edit_text(text, reply_markup=_location_list_kb(locations))
    await call.answer("Удалено")


# ---------- Редактирование площадки (из карточки площадки) ----------

async def _show_loc_edit_menu(target: Message, location) -> None:
    await target.answer(
        "✏️ <b>Редактирование площадки</b>\n\n" + format_location(location),
        reply_markup=kb.location_edit_fields_kb(location.id),
    )


@router.callback_query(F.data.startswith("locedit:"))
async def loc_edit_open(call: CallbackQuery, session: AsyncSession) -> None:
    loc_id = int(call.data.split(":")[1])
    location = await crud.get_location(session, loc_id)
    if not location:
        await call.answer("Площадка не найдена.", show_alert=True)
        return
    await call.answer()
    await _show_loc_edit_menu(call.message, location)


_LOC_FIELD_PROMPTS = {
    "name": "Введите новое название площадки:",
    "address": "Введите новый адрес (или /skip чтобы очистить):",
    "social": "Введите ссылку на соцсеть (или /skip чтобы очистить):",
    "age": "Введите возрастное ограничение, напр. 18+ (или /skip чтобы очистить):",
}


@router.callback_query(F.data.startswith("locf:"))
async def loc_edit_field(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    _, field, loc_id_s = call.data.split(":")
    loc_id = int(loc_id_s)
    location = await crud.get_location(session, loc_id)
    if not location:
        await call.answer("Площадка не найдена.", show_alert=True)
        return

    if field == "done":
        await call.answer("Готово")
        await call.message.answer("Сохранено:\n\n" + format_location(location))
        return

    await state.set_state(LocationEditForm.value)
    await state.update_data(loc_id=loc_id, field=field)
    await call.message.answer(_LOC_FIELD_PROMPTS[field])
    await call.answer()


@router.message(LocationEditForm.value, F.text)
async def loc_edit_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    field = data["field"]
    location = await crud.get_location(session, data["loc_id"])
    if not location:
        await state.clear()
        await message.answer("Площадка не найдена.")
        return

    text = message.text.strip()
    cleared = text == "/skip"
    if field == "name":
        if cleared or len(text) < 2:
            await message.answer("Название не может быть пустым. Введите название:")
            return
        await crud.update_location(session, location, name=text)
    elif field == "address":
        await crud.update_location(session, location, address=None if cleared else text)
    elif field == "social":
        await crud.update_location(session, location, social_link=None if cleared else text)
    elif field == "age":
        await crud.update_location(session, location, age_limit=None if cleared else text)

    await state.set_state(None)
    location = await crud.get_location(session, data["loc_id"])
    await _show_loc_edit_menu(message, location)


# ---------- Предложенные мероприятия (модерация) ----------

@router.callback_query(F.data == "adm:pending")
async def adm_pending(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    events = await crud.list_pending_events(session)
    if not events:
        await call.message.answer("Нет мероприятий на модерации.")
        return
    await call.message.answer(f"📝 На модерации: {len(events)}")
    for event in events:
        await call.message.answer(
            format_event(event, admin=True), reply_markup=kb.moderation_kb(event.id)
        )


@router.callback_query(F.data.startswith("mod:approve:"))
async def mod_approve(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[2])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    await crud.update_event(session, event, status=EventStatus.approved)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"✅ Мероприятие «{event.title}» добавлено в расписание.")
    await call.answer("Добавлено")
    if event.suggested_by:
        try:
            await call.bot.send_message(
                event.suggested_by,
                f"✅ Ваше мероприятие «{event.title}» добавлено в расписание!",
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("mod:reject:"))
async def mod_reject(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[2])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    suggested_by = event.suggested_by
    title = event.title
    await crud.update_event(session, event, status=EventStatus.rejected)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"❌ Мероприятие «{title}» отклонено.")
    await call.answer("Отклонено")
    if suggested_by:
        try:
            await call.bot.send_message(
                suggested_by, f"К сожалению, ваше мероприятие «{title}» отклонено администратором."
            )
        except Exception:
            pass


# ---------- Редактирование мероприятия ----------

async def _show_edit_menu(message: Message, event: Event) -> None:
    await message.answer(
        "✏️ <b>Редактирование</b>\n\n" + format_event(event, admin=True),
        reply_markup=kb.edit_fields_kb(event.id),
    )


@router.callback_query(F.data.startswith("mod:edit:"))
async def mod_edit(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[2])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    await call.answer()
    await _show_edit_menu(call.message, event)


# Редактирование из карточки мероприятия (кнопка ✏️)
@router.callback_query(F.data.startswith("eedit:"))
async def sched_edit(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[1])
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    await call.answer()
    await _show_edit_menu(call.message, event)


def _edit_loc_kb(event_id: int, locations) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=loc.name, callback_data=f"epick:loc:{event_id}:{loc.id}")]
        for loc in locations
    ]
    rows.append([InlineKeyboardButton(text="➖ Убрать", callback_data=f"epick:loc:{event_id}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _edit_genres_kb(event_id: int, genres, selected: set[int]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if g.id in selected else "▫️ ") + g.name,
                callback_data=f"emg:t:{event_id}:{g.id}",
            )
        ]
        for g in genres
    ]
    rows.append([InlineKeyboardButton(text="✔️ Готово", callback_data=f"emg:done:{event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("edit:"))
async def edit_field(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    _, field, event_id_s = call.data.split(":")
    event_id = int(event_id_s)
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return

    if field == "done":
        await call.answer("Готово")
        await call.message.answer(
            "Сохранено:\n\n" + format_event(event, admin=True),
            reply_markup=(
                kb.moderation_kb(event.id)
                if event.status == EventStatus.pending
                else kb.manage_event_kb(event.id)
            ),
        )
        return

    if field == "genre":
        genres = await crud.list_genres(session)
        selected = {g.id for g in event.genres}
        await call.message.answer(
            "Отметьте жанры (можно несколько), затем «Готово»:",
            reply_markup=_edit_genres_kb(event_id, genres, selected),
        )
        await call.answer()
        return
    if field == "location":
        locations = await crud.list_locations(session)
        await call.message.answer("Выберите локацию:", reply_markup=_edit_loc_kb(event_id, locations))
        await call.answer()
        return

    prompts = {
        "title": "Введите новое название:",
        "date": "Введите новую дату (ДД.ММ.ГГГГ):",
        "time": "Введите новое время (ЧЧ:ММ):",
        "link": "Введите новую ссылку (или /skip чтобы очистить):",
        "description": "Введите новое описание (или /skip чтобы очистить):",
    }
    await state.set_state(EditEventForm.value)
    await state.update_data(event_id=event_id, field=field)
    await call.message.answer(prompts[field])
    await call.answer()


@router.callback_query(F.data.startswith("epick:loc:"))
async def edit_pick_loc(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, is_admin: bool
) -> None:
    _, _, event_id_s, item_id_s = call.data.split(":")
    event_id, item_id = int(event_id_s), int(item_id_s)
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    event = await crud.update_event(session, event, location_id=item_id or None)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Обновлено")
    await _show_edit_menu(call.message, event)
    await refresh_schedule_message(call.bot, state, session)


@router.callback_query(F.data.startswith("emg:t:"))
async def edit_genre_toggle(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, is_admin: bool
) -> None:
    _, _, event_id_s, gid_s = call.data.split(":")
    event_id, gid = int(event_id_s), int(gid_s)
    event = await crud.get_event(session, event_id)
    if not event:
        await call.answer("Мероприятие не найдено.", show_alert=True)
        return
    selected = {g.id for g in event.genres}
    selected.symmetric_difference_update({gid})
    event = await crud.set_event_genres(session, event, list(selected))
    genres = await crud.list_genres(session)
    await call.message.edit_reply_markup(
        reply_markup=_edit_genres_kb(event_id, genres, {g.id for g in event.genres})
    )
    await call.answer()
    await refresh_schedule_message(call.bot, state, session)


@router.callback_query(F.data.startswith("emg:done:"))
async def edit_genre_done(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[2])
    event = await crud.get_event(session, event_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Жанры сохранены")
    if event:
        await _show_edit_menu(call.message, event)


@router.message(EditEventForm.value, F.text)
async def edit_value(
    message: Message, state: FSMContext, session: AsyncSession, user: User, is_admin: bool
) -> None:
    data = await state.get_data()
    field = data["field"]
    event = await crud.get_event(session, data["event_id"])
    if not event:
        await state.clear()
        await message.answer("Мероприятие не найдено.")
        return

    text = message.text.strip()
    if field == "title":
        await crud.update_event(session, event, title=text)
    elif field == "date":
        date = parse_date(text)
        if not date:
            await message.answer("Неверный формат даты. ДД.ММ.ГГГГ:")
            return
        await crud.update_event(session, event, date=date)
    elif field == "time":
        time = parse_time(text)
        if not time:
            await message.answer("Неверный формат времени. ЧЧ:ММ:")
            return
        await crud.update_event(session, event, time=time)
    elif field == "link":
        await crud.update_event(session, event, link=None if text == "/skip" else text)
    elif field == "description":
        await crud.update_event(session, event, description=None if text == "/skip" else text)

    # выходим из состояния редактирования, но НЕ трогаем сохранённый фильтр расписания
    await state.set_state(None)
    event = await crud.get_event(session, data["event_id"])
    await _show_edit_menu(message, event)
    await refresh_schedule_message(message.bot, state, session)


# ---------- Управление расписанием (удаление) ----------

@router.callback_query(F.data == "adm:manage")
async def adm_manage(call: CallbackQuery, session: AsyncSession) -> None:
    await call.answer()
    events = await crud.list_events(session, only_upcoming=True)
    if not events:
        await call.message.answer("В расписании нет предстоящих мероприятий.")
        return
    await call.message.answer(f"🗑 Управление расписанием ({len(events)}):")
    for event in events:
        await call.message.answer(
            format_event(event, admin=True), reply_markup=kb.manage_event_kb(event.id)
        )


@router.callback_query(F.data.startswith("mng:del:"))
async def mng_del(call: CallbackQuery) -> None:
    event_id = int(call.data.split(":")[2])
    await call.message.edit_reply_markup(reply_markup=kb.confirm_delete_kb(event_id))
    await call.answer()


@router.callback_query(F.data.startswith("mng:delno:"))
async def mng_delno(call: CallbackQuery) -> None:
    event_id = int(call.data.split(":")[2])
    await call.message.edit_reply_markup(reply_markup=kb.manage_event_kb(event_id))
    await call.answer("Отменено")


@router.callback_query(F.data.startswith("mng:delyes:"))
async def mng_delyes(call: CallbackQuery, session: AsyncSession) -> None:
    event_id = int(call.data.split(":")[2])
    await crud.delete_event(session, event_id)
    await call.message.edit_text("🗑 Мероприятие удалено.")
    await call.answer("Удалено")


# ---------- Управление пользователями (роли и бан) ----------

USERS_PAGE_SIZE = 8


def _user_role(target: User, superadmin_ids: set[int]) -> str:
    if target.id in superadmin_ids:
        return "суперадмин 👑"
    if target.is_admin:
        return "администратор 🛡"
    return "пользователь"


async def _render_users_list(call: CallbackQuery, session: AsyncSession, page: int, superadmin_ids: set[int]) -> None:
    total = await crud.count_users(session)
    total_pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    users = await crud.list_users(session, offset=page * USERS_PAGE_SIZE, limit=USERS_PAGE_SIZE)
    text = (
        f"👥 <b>Пользователи</b> (всего: {total})\n"
        f"Страница {page + 1}/{total_pages}\n\n"
        "👑 суперадмин · 🛡 админ · 🚫 забанен\n"
        "Нажмите на пользователя для управления."
    )
    await call.message.edit_text(
        text, reply_markup=kb.users_list_kb(users, page, total_pages, superadmin_ids)
    )


async def _render_user_card(call: CallbackQuery, session: AsyncSession, target: User, page: int, superadmin_ids: set[int]) -> None:
    from ..utils import _e

    uname = f"@{target.username}" if target.username else "—"
    text = (
        "👤 <b>Карточка пользователя</b>\n\n"
        f"Имя: {_e(target.full_name) or '—'}\n"
        f"Username: {_e(uname)}\n"
        f"ID: <code>{target.id}</code>\n"
        f"Роль: {_user_role(target, superadmin_ids)}\n"
        f"Статус: {'🚫 забанен' if target.is_banned else '✅ активен'}"
    )
    is_super = target.id in superadmin_ids
    await call.message.edit_text(text, reply_markup=kb.user_card_kb(target, page, is_super))


@router.callback_query(F.data.startswith("usr:list:"))
async def usr_list(call: CallbackQuery, session: AsyncSession, superadmin_ids: set[int]) -> None:
    page = int(call.data.split(":")[2])
    await _render_users_list(call, session, page, superadmin_ids)
    await call.answer()


@router.callback_query(F.data.startswith("usr:card:"))
async def usr_card(call: CallbackQuery, session: AsyncSession, superadmin_ids: set[int]) -> None:
    _, _, uid_s, page_s = call.data.split(":")
    target = await crud.get_user(session, int(uid_s))
    if not target:
        await call.answer("Пользователь не найден.", show_alert=True)
        return
    await _render_user_card(call, session, target, int(page_s), superadmin_ids)
    await call.answer()


@router.callback_query(F.data.startswith(("usr:mkadmin:", "usr:unadmin:", "usr:ban:", "usr:unban:")))
async def usr_action(call: CallbackQuery, session: AsyncSession, superadmin_ids: set[int]) -> None:
    _, action, uid_s, page_s = call.data.split(":")
    uid, page = int(uid_s), int(page_s)

    if uid == call.from_user.id:
        await call.answer("Нельзя менять собственную роль или статус.", show_alert=True)
        return
    if uid in superadmin_ids:
        await call.answer("Суперадмина нельзя изменить (задаётся через окружение).", show_alert=True)
        return

    target = await crud.get_user(session, uid)
    if not target:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    if action == "mkadmin":
        await crud.set_admin(session, target, True)
        note = "Назначен администратором"
    elif action == "unadmin":
        await crud.set_admin(session, target, False)
        note = "Снят с администраторов"
    elif action == "ban":
        if target.is_admin:
            await call.answer("Сначала снимите роль администратора.", show_alert=True)
            return
        await crud.set_banned(session, target, True)
        note = "Пользователь забанен"
    else:  # unban
        await crud.set_banned(session, target, False)
        note = "Пользователь разбанен"

    target = await crud.get_user(session, uid)
    await _render_user_card(call, session, target, page, superadmin_ids)
    await call.answer(note)

    # Уведомим пользователя и сразу обновим его меню (reply-клавиатуру)
    messages = {
        "mkadmin": "🛡 Вам выданы права администратора.",
        "unadmin": "Права администратора сняты.",
        "ban": "🚫 Вы заблокированы администратором и больше не можете пользоваться ботом.",
        "unban": "✅ Вас разблокировали. Снова можете пользоваться ботом.",
    }
    if action == "ban":
        markup = ReplyKeyboardRemove()
    else:
        # mkadmin/unadmin/unban — показываем меню под новую роль
        markup = kb.main_menu(target.is_admin)
    try:
        await call.bot.send_message(uid, messages[action], reply_markup=markup)
    except Exception:
        pass


# ---------- Рассылка ----------

@router.message(Command("broadcast"))
async def broadcast(message: Message, session: AsyncSession) -> None:
    if not message.reply_to_message:
        await message.answer(
            "Чтобы разослать сообщение всем пользователям, "
            "ответьте на нужное сообщение командой /broadcast."
        )
        return

    user_ids = await crud.get_all_user_ids(session)
    src_chat = message.chat.id
    src_msg = message.reply_to_message.message_id

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # мягкий троттлинг под лимиты Telegram

    await message.answer(f"📢 Рассылка завершена.\nОтправлено: {sent}\nНе доставлено: {failed}")
