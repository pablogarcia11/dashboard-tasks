from datetime import UTC, date

from core.dates import (day_bounds, effective_today, is_workday, next_workday, previous_workday,
                        to_work_date, workdays_between)

TZ = "Europe/Madrid"


def test_lunes_da_viernes():
    assert previous_workday(date(2026, 11, 9)) == date(2026, 11, 6)


def test_martes_da_lunes():
    assert previous_workday(date(2026, 11, 10)) == date(2026, 11, 9)


def test_sabado_y_domingo_dan_viernes():
    assert previous_workday(date(2026, 11, 14)) == date(2026, 11, 13)
    assert previous_workday(date(2026, 11, 15)) == date(2026, 11, 13)


def test_cambio_de_mes_y_de_anio():
    assert previous_workday(date(2026, 12, 1)) == date(2026, 11, 30)
    assert previous_workday(date(2027, 1, 4)) == date(2027, 1, 1)    # lunes → viernes 1/1 (sin festivos configurados)
    assert previous_workday(date(2027, 1, 1)) == date(2026, 12, 31)  # viernes 1/1 → jueves 31/12


def test_festivos():
    hol = ["2026-12-08"]
    assert not is_workday(date(2026, 12, 8), hol)
    assert previous_workday(date(2026, 12, 9), hol) == date(2026, 12, 7)
    assert next_workday(date(2026, 12, 7), hol) == date(2026, 12, 9)


def test_next_workday_viernes_da_lunes():
    assert next_workday(date(2026, 11, 13)) == date(2026, 11, 16)


def test_effective_today_fin_de_semana():
    assert effective_today(date(2026, 11, 11)) == (date(2026, 11, 11), False)
    assert effective_today(date(2026, 11, 14)) == (date(2026, 11, 13), True)
    assert effective_today(date(2026, 11, 15)) == (date(2026, 11, 13), True)


def test_day_bounds_cambio_horario():
    # 25/10/2026: se retrasa la hora (día de 25 h); 29/03/2026: se adelanta (23 h)
    # (en UTC: restar dos datetime de la misma zona compara la hora de reloj, no el tiempo real)
    s, e = day_bounds(date(2026, 10, 25), TZ)
    assert (e.astimezone(UTC) - s.astimezone(UTC)).total_seconds() == 25 * 3600
    s, e = day_bounds(date(2026, 3, 29), TZ)
    assert (e.astimezone(UTC) - s.astimezone(UTC)).total_seconds() == 23 * 3600
    s, _ = day_bounds(date(2026, 11, 10), TZ)
    assert s.isoformat() == "2026-11-10T00:00:00+01:00"


def test_to_work_date_usa_zona_del_usuario():
    # 23:30 UTC del día 10 son las 00:30 del 11 en Madrid
    assert to_work_date("2026-11-10T23:30:00+00:00", TZ) == date(2026, 11, 11)
    assert to_work_date("2026-11-10T23:30:00+01:00", TZ) == date(2026, 11, 10)


def test_workdays_between_salta_fin_de_semana():
    assert workdays_between(date(2026, 11, 13), date(2026, 11, 16)) == [date(2026, 11, 13), date(2026, 11, 16)]


def test_date_ranges_agrupa_dias_seguidos_saltando_fines_de_semana():
    from core.dates import date_ranges
    days = ["2026-12-24", "2026-12-25", "2026-12-28", "2026-12-08", "2026-12-30"]
    assert date_ranges(days) == [(date(2026, 12, 8), date(2026, 12, 8)), (date(2026, 12, 24), date(2026, 12, 28)),
                                 (date(2026, 12, 30), date(2026, 12, 30))]
    assert date_ranges([]) == []
