from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .db.models import Event, Genre, Location, User


# ---------- Главное меню (reply) ----------

BTN_SCHEDULE = "📅 Расписание"
BTN_EVENTS = "🎫 Мероприятия"
BTN_FAVORITES = "❤️ Избранное"
BTN_SUGGEST = "➕ Предложить мероприятие"
BTN_ADD = "➕ Добавить мероприятие"
BTN_NOTIFY = "🔔 Напоминания"
BTN_ADMIN = "🛠 Админ-панель"


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    # Админу — прямое добавление (без модерации), пользователю — предложение
    add_btn = BTN_ADD if is_admin else BTN_SUGGEST
    rows = [
        [KeyboardButton(text=BTN_SCHEDULE), KeyboardButton(text=BTN_EVENTS)],
        [KeyboardButton(text=BTN_FAVORITES), KeyboardButton(text=add_btn)],
        [KeyboardButton(text=BTN_NOTIFY)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ---------- Фильтры расписания (комбинируемые: дата + жанр + локация) ----------

def schedule_builder_kb(date_label: str, genre_label: str, loc_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🗓 Дата: {date_label}", callback_data="sf:datemenu")],
            [InlineKeyboardButton(text=f"🎭 Жанр: {genre_label}", callback_data="sf:genremenu")],
            [InlineKeyboardButton(text=f"📍 Локация: {loc_label}", callback_data="sf:locmenu")],
            [
                InlineKeyboardButton(text="✅ Показать", callback_data="sf:show"),
                InlineKeyboardButton(text="♻️ Сбросить", callback_data="sf:reset"),
            ],
        ]
    )


def schedule_date_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗓 Сегодня", callback_data="sf:setdate:today")],
            [InlineKeyboardButton(text="📆 На этой неделе", callback_data="sf:setdate:week")],
            [InlineKeyboardButton(text="🗓 В этом месяце", callback_data="sf:setdate:month")],
            [InlineKeyboardButton(text="♾ Все предстоящие", callback_data="sf:setdate:any")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="sf:back")],
        ]
    )


def _multi_genre_kb(
    genres: list[Genre], selected: set[int], toggle_prefix: str, done_cb: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if g.id in selected else "▫️ ") + g.name,
                callback_data=f"{toggle_prefix}:{g.id}",
            )
        ]
        for g in genres
    ]
    rows.append([InlineKeyboardButton(text="✔️ Готово", callback_data=done_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def schedule_genres_kb(genres: list[Genre], selected: set[int]) -> InlineKeyboardMarkup:
    return _multi_genre_kb(genres, selected, "sf:tg", "sf:back")


def schedule_loc_kb(locations: list[Location]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Любая", callback_data="sf:setloc:any")]]
    rows += [
        [InlineKeyboardButton(text=loc.name, callback_data=f"sf:setloc:{loc.id}")]
        for loc in locations
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sf:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Кнопка избранного под мероприятием ----------

def event_fav_kb(event: Event, is_fav: bool) -> InlineKeyboardMarkup:
    text = "💔 Убрать из избранного" if is_fav else "❤️ В избранное"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"fav:toggle:{event.id}")]
        ]
    )


# ---------- Карточка мероприятия ----------

def event_detail_kb(
    event: Event, is_fav: bool, is_admin: bool, confirm_delete: bool = False
) -> InlineKeyboardMarkup:
    """Карточка мероприятия: избранное (всем) + редактирование/удаление (админам)."""
    if confirm_delete:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"edelyes:{event.id}"),
            InlineKeyboardButton(text="✖️ Отмена", callback_data=f"edelno:{event.id}"),
        ]])
    fav_text = "💔 Убрать из избранного" if is_fav else "❤️ В избранное"
    rows = [[InlineKeyboardButton(text=fav_text, callback_data=f"efav:{event.id}")]]
    if is_admin:
        rows.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"eedit:{event.id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"edel:{event.id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Карточка площадки ----------

def location_detail_kb(location: Location, is_admin: bool) -> InlineKeyboardMarkup | None:
    """Карточка площадки: админу — кнопка редактирования, остальным без кнопок."""
    if not is_admin:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Редактировать площадку", callback_data=f"locedit:{location.id}")
    ]])


def location_edit_fields_kb(location_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("Название", "name"),
        ("Адрес", "address"),
        ("Соцсеть", "social"),
        ("Возрастное ограничение", "age"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"locf:{field}:{location_id}")]
        for label, field in fields
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Готово", callback_data=f"locf:done:{location_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Выбор жанров/локации при создании мероприятия ----------

def pick_genres_kb(genres: list[Genre], selected: set[int]) -> InlineKeyboardMarkup:
    return _multi_genre_kb(genres, selected, "fg:t", "fg:done")


def pick_location_kb(locations: list[Location]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=loc.name, callback_data=f"pick:loc:{loc.id}")]
        for loc in locations
    ]
    rows.append([InlineKeyboardButton(text="➖ Без локации", callback_data="pick:loc:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Настройки напоминаний ----------

def notify_kb(user: User) -> InlineKeyboardMarkup:
    def mark(on: bool) -> str:
        return "✅" if on else "☑️"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{mark(user.notify_week)} За неделю", callback_data="ntf:week")],
            [InlineKeyboardButton(text=f"{mark(user.notify_day)} За день", callback_data="ntf:day")],
            [InlineKeyboardButton(text=f"{mark(user.notify_sameday)} В день события", callback_data="ntf:sameday")],
        ]
    )


# ---------- Админ-панель ----------

def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить мероприятие", callback_data="adm:addevent")],
            [InlineKeyboardButton(text="🎭 Жанры", callback_data="adm:genres")],
            [InlineKeyboardButton(text="📍 Локации", callback_data="adm:locations")],
            [InlineKeyboardButton(text="📝 Предложенные мероприятия", callback_data="adm:pending")],
            [InlineKeyboardButton(text="🗑 Управление расписанием", callback_data="adm:manage")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="usr:list:0")],
        ]
    )


# ---------- Управление пользователями ----------

def _user_label(u: "User", superadmin_ids: set[int]) -> str:
    name = u.full_name or (f"@{u.username}" if u.username else str(u.id))
    marks = ""
    if u.id in superadmin_ids:
        marks += " 👑"
    elif u.is_admin:
        marks += " 🛡"
    if u.is_banned:
        marks += " 🚫"
    return f"{name}{marks}"


def users_list_kb(
    users: list["User"], page: int, total_pages: int, superadmin_ids: set[int]
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_user_label(u, superadmin_ids), callback_data=f"usr:card:{u.id}:{page}")]
        for u in users
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"usr:list:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"usr:list:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_card_kb(target: "User", page: int, is_superadmin_target: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_superadmin_target:
        if target.is_admin:
            rows.append([InlineKeyboardButton(text="⬇️ Снять админа", callback_data=f"usr:unadmin:{target.id}:{page}")])
        else:
            rows.append([InlineKeyboardButton(text="⬆️ Сделать админом", callback_data=f"usr:mkadmin:{target.id}:{page}")])
        # Банить можно только не-админа
        if not target.is_admin:
            if target.is_banned:
                rows.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"usr:unban:{target.id}:{page}")])
            else:
                rows.append([InlineKeyboardButton(text="🚫 Забанить", callback_data=f"usr:ban:{target.id}:{page}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data=f"usr:list:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def moderation_kb(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Добавить", callback_data=f"mod:approve:{event_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"mod:reject:{event_id}"),
            ],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"mod:edit:{event_id}")],
        ]
    )


def edit_fields_kb(event_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("Название", "title"),
        ("Дата", "date"),
        ("Время", "time"),
        ("Жанр", "genre"),
        ("Локация", "location"),
        ("Ссылка", "link"),
        ("Описание", "description"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"edit:{field}:{event_id}")]
        for label, field in fields
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Готово", callback_data=f"edit:done:{event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manage_event_kb(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"mod:edit:{event_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"mng:del:{event_id}"),
            ]
        ]
    )


def confirm_delete_kb(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"mng:delyes:{event_id}"),
                InlineKeyboardButton(text="Отмена", callback_data=f"mng:delno:{event_id}"),
            ]
        ]
    )
