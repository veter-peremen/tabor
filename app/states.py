from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class GenreForm(StatesGroup):
    name = State()


class LocationForm(StatesGroup):
    name = State()
    address = State()
    social_link = State()
    age_limit = State()


class EventForm(StatesGroup):
    """Единый сценарий для админского добавления и пользовательского предложения."""

    title = State()
    date = State()
    time = State()
    genre = State()
    location = State()
    link = State()
    description = State()


class EditEventForm(StatesGroup):
    value = State()


class LocationEditForm(StatesGroup):
    value = State()
