"""Interfaz común de los colectores."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class Activity:
    source: str          # git | notion | gcal | slack | github
    kind: str            # commit | wip | task | task_plan | meeting | message | pr | review
    external_id: str
    ts: str              # ISO 8601 con zona
    work_date: str       # YYYY-MM-DD en la zona del usuario
    title: str = ""
    body: str = ""
    url: str = ""
    project: str = ""
    status: str = ""
    extra: dict = field(default_factory=dict)


class Collector(Protocol):
    source: str

    def collect(self, since: datetime, until: datetime) -> list[Activity]: ...
