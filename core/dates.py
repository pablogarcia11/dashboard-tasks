"""Lógica de días laborables (L–V) y rangos de fechas en la zona del usuario."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def is_workday(d: date, holidays=()) -> bool:
    return d.weekday() < 5 and d.isoformat() not in holidays


def previous_workday(d: date, holidays=()) -> date:
    d -= timedelta(days=1)
    while not is_workday(d, holidays):
        d -= timedelta(days=1)
    return d


def next_workday(d: date, holidays=()) -> date:
    d += timedelta(days=1)
    while not is_workday(d, holidays):
        d += timedelta(days=1)
    return d


def effective_today(today: date, holidays=()) -> tuple[date, bool]:
    """Día que muestra la vista "Hoy" y si hay que avisar de que no es laborable.

    En fin de semana o festivo se muestra el último día laborable.
    """
    if is_workday(today, holidays):
        return today, False
    return previous_workday(today, holidays), True


def day_bounds(d: date, tz: str) -> tuple[datetime, datetime]:
    """Inicio (incluido) y fin (excluido) del día en la zona dada. Respeta los cambios de hora."""
    z = ZoneInfo(tz)
    return datetime.combine(d, time.min, z), datetime.combine(d + timedelta(days=1), time.min, z)


def to_work_date(ts: str | datetime, tz: str) -> date:
    """Fecha local (zona del usuario) de un instante ISO 8601 con zona."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts.astimezone(ZoneInfo(tz)).date()


def workdays_between(start: date, end: date, holidays=()) -> list[date]:
    """Días laborables entre start y end, ambos incluidos."""
    days, d = [], start
    while d <= end:
        if is_workday(d, holidays):
            days.append(d)
        d += timedelta(days=1)
    return days


def date_ranges(days: list[str]) -> list[tuple[date, date]]:
    """Agrupa fechas ISO en rangos (inicio, fin) de días seguidos; un fin de semana en medio no corta
    el rango (unas vacaciones de lunes a viernes de la semana siguiente son un solo rango)."""
    ranges: list[list[date]] = []
    for d in sorted({date.fromisoformat(x) for x in days}):
        if ranges and d <= next_workday(ranges[-1][1]):
            ranges[-1][1] = d
        else:
            ranges.append([d, d])
    return [(a, b) for a, b in ranges]
