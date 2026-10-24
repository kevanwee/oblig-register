"""oblig-register: contract obligations as data.

    load_register(path)              -> Register (validated)
    resolve(register, calendar=None) -> list[Resolved]   deadlines + traces
    to_ics(resolved, register)       -> str              RFC 5545 calendar
    render_markdown(...)             -> str
"""

from .ics import to_ics
from .models import (
    Category,
    NoticeClause,
    NoticeMethod,
    Obligation,
    Register,
    Trigger,
    load_register,
)
from .render import render_markdown, upcoming
from .resolve import Resolved, WorkingDayCalendar, resolve

__all__ = [
    "Register",
    "Obligation",
    "Trigger",
    "Category",
    "NoticeClause",
    "NoticeMethod",
    "load_register",
    "resolve",
    "Resolved",
    "WorkingDayCalendar",
    "to_ics",
    "render_markdown",
    "upcoming",
]

__version__ = "0.2.0"
