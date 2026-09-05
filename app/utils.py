from __future__ import annotations

import datetime as dt
import html

from .db.models import Event


def parse_date(text: str) -> dt.date | None:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_time(text: str) -> dt.time | None:
    text = text.strip()
    for fmt in ("%H:%M", "%H.%M", "%H:%M:%S"):
        try:
            return dt.datetime.strptime(text, fmt).time().replace(second=0, microsecond=0)
        except ValueError:
            continue
    return None


def month_bounds(today: dt.date) -> tuple[dt.date, dt.date]:
    first = today.replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    last = next_first - dt.timedelta(days=1)
    return first, last


def week_bounds(today: dt.date) -> tuple[dt.date, dt.date]:
    # С сегодняшнего дня до конца текущей недели (воскресенье)
    end = today + dt.timedelta(days=(6 - today.weekday()))
    return today, end


def _e(value: str | None) -> str:
    return html.escape(value) if value else ""


def format_schedule_line(event: Event, bot_username: str) -> str:
    """Строка расписания: «дата время • Название (ссылка-карточка)»."""
    date = event.date.strftime("%d.%m.%Y")
    time = event.time.strftime("%H:%M")
    title = _e(event.title)
    if bot_username:
        link = f"https://t.me/{bot_username}?start=event_{event.id}"
        title = f'<a href="{link}">{title}</a>'
    return f"👉 {date} {time} • {title}"


def format_location(loc) -> str:
    lines = [f"📍 <b>{_e(loc.name)}</b>"]
    lines.append(f"🔞 Возрастное ограничение: {_e(loc.age_limit) if loc.age_limit else '—'}")
    lines.append(f"🗺 Адрес: {_e(loc.address) if loc.address else '—'}")
    lines.append(f"🔗 Соцсеть: {_e(loc.social_link) if loc.social_link else '—'}")
    return "\n".join(lines)


def format_event(event: Event, *, admin: bool = False, bot_username: str | None = None) -> str:
    lines: list[str] = []
    lines.append(f"🎫 <b>{_e(event.title)}</b>")
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][event.date.weekday()]
    lines.append(f"📅 {event.date.strftime('%d.%m.%Y')} ({weekday}) в {event.time.strftime('%H:%M')}")

    if event.genres:
        names = ", ".join(_e(g.name) for g in event.genres)
        label = "Жанры" if len(event.genres) > 1 else "Жанр"
        lines.append(f"🎭 {label}: {names}")

    if event.location:
        loc = event.location
        # название площадки — кликабельная ссылка на её карточку (deep-link)
        if bot_username:
            link = f"https://t.me/{bot_username}?start=loc_{loc.id}"
            name = f'<a href="{link}">{_e(loc.name)}</a>'
        else:
            name = _e(loc.name)
        # Возрастное ограничение площадки в карточке события не показываем —
        # у мероприятия оно может отличаться; смотреть в карточке площадки.
        lines.append(f"📍 {name}")
        if loc.address:
            lines.append(f"   🗺 {_e(loc.address)}")

    if event.description:
        lines.append("")
        lines.append(_e(event.description))

    if event.link:
        lines.append("")
        lines.append(f"➡️ {_e(event.link)}")

    if admin:
        lines.append("")
        lines.append(f"<i>id={event.id}, статус={event.status.value}</i>")

    return "\n".join(lines)
