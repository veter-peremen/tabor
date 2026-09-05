from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Event,
    EventStatus,
    Favorite,
    Genre,
    Location,
    SentReminder,
    User,
    event_genres,
)


# ---------- Пользователи ----------

async def get_or_create_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None,
    full_name: str | None,
    superadmin_ids: set[int],
) -> User:
    user = await session.get(User, tg_id)
    force_admin = tg_id in superadmin_ids
    if user is None:
        user = User(
            id=tg_id,
            username=username,
            full_name=full_name,
            is_admin=force_admin,
        )
        session.add(user)
        await session.commit()
        return user

    changed = False
    if user.username != username:
        user.username = username
        changed = True
    if user.full_name != full_name:
        user.full_name = full_name
        changed = True
    if force_admin and not user.is_admin:
        user.is_admin = True
        changed = True
    if changed:
        await session.commit()
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def count_users(session: AsyncSession) -> int:
    res = await session.execute(select(func.count()).select_from(User))
    return int(res.scalar_one())


async def list_users(session: AsyncSession, *, offset: int = 0, limit: int = 8) -> list[User]:
    res = await session.execute(
        select(User).order_by(User.is_admin.desc(), User.created_at).offset(offset).limit(limit)
    )
    return list(res.scalars().all())


async def set_admin(session: AsyncSession, user: User, value: bool) -> None:
    user.is_admin = value
    await session.commit()


async def set_banned(session: AsyncSession, user: User, value: bool) -> None:
    user.is_banned = value
    await session.commit()


async def get_admins(session: AsyncSession) -> list[User]:
    res = await session.execute(select(User).where(User.is_admin.is_(True)))
    return list(res.scalars().all())


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    res = await session.execute(select(User.id))
    return [row[0] for row in res.all()]


async def set_notify_settings(
    session: AsyncSession, user: User, *, week: bool, day: bool, sameday: bool
) -> None:
    user.notify_week = week
    user.notify_day = day
    user.notify_sameday = sameday
    await session.commit()


# ---------- Жанры ----------

async def list_genres(session: AsyncSession) -> list[Genre]:
    res = await session.execute(select(Genre).order_by(Genre.name))
    return list(res.scalars().all())


async def add_genre(session: AsyncSession, name: str) -> Genre | None:
    # Сравнение в Python: SQLite lower() не понимает кириллицу
    existing = await list_genres(session)
    if any(g.name.lower() == name.lower() for g in existing):
        return None
    genre = Genre(name=name)
    session.add(genre)
    await session.commit()
    return genre


async def delete_genre(session: AsyncSession, genre_id: int) -> bool:
    genre = await session.get(Genre, genre_id)
    if not genre:
        return False
    await session.delete(genre)
    await session.commit()
    return True


# ---------- Локации ----------

async def list_locations(session: AsyncSession) -> list[Location]:
    res = await session.execute(select(Location).order_by(Location.name))
    return list(res.scalars().all())


async def add_location(
    session: AsyncSession,
    name: str,
    address: str | None,
    social_link: str | None,
    age_limit: str | None,
) -> Location | None:
    existing = await list_locations(session)
    if any(loc.name.lower() == name.lower() for loc in existing):
        return None
    loc = Location(
        name=name, address=address, social_link=social_link, age_limit=age_limit
    )
    session.add(loc)
    await session.commit()
    return loc


async def get_location(session: AsyncSession, location_id: int) -> Location | None:
    return await session.get(Location, location_id)


async def update_location(session: AsyncSession, location: Location, **fields) -> Location:
    for key, value in fields.items():
        setattr(location, key, value)
    await session.commit()
    return location


async def delete_location(session: AsyncSession, location_id: int) -> bool:
    loc = await session.get(Location, location_id)
    if not loc:
        return False
    await session.delete(loc)
    await session.commit()
    return True


# ---------- Мероприятия ----------

async def _genres_by_ids(session: AsyncSession, genre_ids: list[int]) -> list[Genre]:
    if not genre_ids:
        return []
    res = await session.execute(select(Genre).where(Genre.id.in_(genre_ids)))
    return list(res.scalars().all())


async def create_event(
    session: AsyncSession, *, genre_ids: list[int] | None = None, **fields
) -> Event:
    event = Event(**fields)
    event.genres = await _genres_by_ids(session, genre_ids or [])
    session.add(event)
    await session.commit()
    return await get_event(session, event.id)


async def get_event(session: AsyncSession, event_id: int) -> Event | None:
    res = await session.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.location), selectinload(Event.genres))
    )
    return res.scalar_one_or_none()


async def update_event(session: AsyncSession, event: Event, **fields) -> Event:
    for key, value in fields.items():
        setattr(event, key, value)
    await session.commit()
    return await get_event(session, event.id)


async def set_event_genres(session: AsyncSession, event: Event, genre_ids: list[int]) -> Event:
    event.genres = await _genres_by_ids(session, genre_ids)
    await session.commit()
    return await get_event(session, event.id)


async def delete_event(session: AsyncSession, event_id: int) -> bool:
    event = await session.get(Event, event_id)
    if not event:
        return False
    await session.execute(delete(Favorite).where(Favorite.event_id == event_id))
    await session.delete(event)
    await session.commit()
    return True


async def list_pending_events(session: AsyncSession) -> list[Event]:
    res = await session.execute(
        select(Event)
        .where(Event.status == EventStatus.pending)
        .options(selectinload(Event.location), selectinload(Event.genres))
        .order_by(Event.date, Event.time)
    )
    return list(res.scalars().all())


async def list_events(
    session: AsyncSession,
    *,
    only_upcoming: bool = True,
    genre_ids: list[int] | None = None,
    location_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    status: EventStatus = EventStatus.approved,
) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.status == status)
        .options(selectinload(Event.location), selectinload(Event.genres))
        .order_by(Event.date, Event.time)
    )
    if only_upcoming and date_from is None:
        stmt = stmt.where(Event.date >= dt.date.today())
    if genre_ids:
        # мероприятие подходит, если у него есть хотя бы один из выбранных жанров
        stmt = (
            stmt.join(event_genres, event_genres.c.event_id == Event.id)
            .where(event_genres.c.genre_id.in_(genre_ids))
            .distinct()
        )
    if location_id is not None:
        stmt = stmt.where(Event.location_id == location_id)
    if date_from is not None:
        stmt = stmt.where(Event.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Event.date <= date_to)
    res = await session.execute(stmt)
    return list(res.scalars().all())


# ---------- Избранное ----------

async def is_favorite(session: AsyncSession, user_id: int, event_id: int) -> bool:
    res = await session.execute(
        select(Favorite.id).where(
            Favorite.user_id == user_id, Favorite.event_id == event_id
        )
    )
    return res.scalar_one_or_none() is not None


async def toggle_favorite(session: AsyncSession, user_id: int, event_id: int) -> bool:
    """Возвращает True, если после операции мероприятие в избранном."""
    res = await session.execute(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.event_id == event_id
        )
    )
    fav = res.scalar_one_or_none()
    if fav:
        await session.delete(fav)
        await session.commit()
        return False
    session.add(Favorite(user_id=user_id, event_id=event_id))
    await session.commit()
    return True


async def list_favorite_events(session: AsyncSession, user_id: int) -> list[Event]:
    res = await session.execute(
        select(Event)
        .join(Favorite, Favorite.event_id == Event.id)
        .where(Favorite.user_id == user_id, Event.status == EventStatus.approved)
        .options(selectinload(Event.location), selectinload(Event.genres))
        .order_by(Event.date, Event.time)
    )
    return list(res.scalars().all())


# ---------- Напоминания ----------

async def upcoming_favorites_with_users(
    session: AsyncSession, now: dt.datetime
) -> list[tuple[Favorite, User, Event]]:
    res = await session.execute(
        select(Favorite, User, Event)
        .join(User, User.id == Favorite.user_id)
        .join(Event, Event.id == Favorite.event_id)
        .where(Event.status == EventStatus.approved, Event.date >= now.date())
        .options(selectinload(Event.location), selectinload(Event.genres))
    )
    return [tuple(row) for row in res.all()]


async def reminder_already_sent(
    session: AsyncSession, user_id: int, event_id: int, kind: str
) -> bool:
    res = await session.execute(
        select(SentReminder.id).where(
            SentReminder.user_id == user_id,
            SentReminder.event_id == event_id,
            SentReminder.kind == kind,
        )
    )
    return res.scalar_one_or_none() is not None


async def mark_reminder_sent(
    session: AsyncSession, user_id: int, event_id: int, kind: str
) -> None:
    session.add(SentReminder(user_id=user_id, event_id=event_id, kind=kind))
    await session.commit()
