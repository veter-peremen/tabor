from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Связь многие-ко-многим: мероприятие ↔ жанры
event_genres = Table(
    "event_genres",
    Base.metadata,
    Column("event_id", ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class EventStatus(str, enum.Enum):
    approved = "approved"   # в расписании
    pending = "pending"     # предложено пользователем, ждёт модерации
    rejected = "rejected"   # отклонено админом


class User(Base):
    __tablename__ = "users"

    # Telegram user id
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Настройки напоминаний (по мероприятиям из избранного)
    notify_week: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_sameday: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    events: Mapped[list["Event"]] = relationship(
        secondary=event_genres, back_populates="genres"
    )


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    social_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_limit: Mapped[str | None] = mapped_column(String(16), nullable=True)  # напр. "18+"

    events: Mapped[list["Event"]] = relationship(back_populates="location")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus), default=EventStatus.approved, nullable=False
    )
    suggested_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    location: Mapped[Location | None] = relationship(back_populates="events")
    genres: Mapped[list[Genre]] = relationship(
        secondary=event_genres, back_populates="events"
    )

    @property
    def starts_at(self) -> dt.datetime:
        return dt.datetime.combine(self.date, self.time)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "event_id", name="uq_favorite"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="favorites")
    event: Mapped[Event] = relationship()


class SentReminder(Base):
    """Защита от повторной отправки одного и того же напоминания."""

    __tablename__ = "sent_reminders"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", "kind", name="uq_sent_reminder"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # week/day/sameday
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
