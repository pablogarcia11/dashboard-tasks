"""Rutas de la web que cambian datos: Ajustes (festivos, redirecciones) y edición del parte de horas.

Cada test usa una base de datos temporal; no se arranca el servidor ni se llama a Claude.
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core import db, settings
from llm.claude_cli import ClaudeError
from web import app as web

DAY = "2026-11-10"   # martes


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "dashboard.db"
    real_connect = db.connect
    monkeypatch.setattr(db, "connect", lambda p=path: real_connect(p))
    monkeypatch.setattr(web, "today", lambda: date(2026, 11, 12))
    monkeypatch.setattr(web, "refresh_in_background", lambda *a, **k: None)   # nada de recogidas reales
    return TestClient(web.app)   # sin `with`: no corre el lifespan (que recoge datos al arrancar)


# --- Ajustes ---------------------------------------------------------------------------------------

def test_dias_libres_devuelve_la_lista_actualizada(client):
    r = client.post("/settings/days-off", data={"action": "add", "start": "2026-12-07", "end": "2026-12-08"},
                    headers={"HX-Request": "true", "HX-Current-URL": "http://127.0.0.1:8765/settings#days-off"})
    assert r.status_code == 200 and "HX-Redirect" not in r.headers
    assert 'id="days-off-control"' in r.text and "7 dic – 8 dic 2026" in r.text
    assert settings.days_off(db.connect()) == ["2026-12-07", "2026-12-08"]

    r = client.post("/settings/days-off", data={"action": "remove", "start": "2026-12-07", "end": "2026-12-08"})
    assert r.status_code == 200 and "Aún no has apuntado ninguno" in r.text
    assert settings.days_off(db.connect()) == []


@pytest.mark.parametrize("form, message", [
    ({"action": "add", "start": ""}, "Elige una fecha"),
    ({"action": "add", "start": "2026-11-14"}, "fin de semana"),
    ({"action": "add", "start": "2026-11-10", "end": "2026-11-09"}, "anterior"),
])
def test_dias_libres_rechaza(client, form, message):
    r = client.post("/settings/days-off", data=form)
    assert r.status_code == 422 and message in r.text


def test_redireccion_a_la_misma_pagina_pide_recargar(client):
    """Ir a /settings#ancla estando ya en /settings solo desplazaría la página: hace falta HX-Refresh."""
    same = client.post("/settings/git-authors", data={"email": "yo@example.com"},
                       headers={"HX-Current-URL": "http://127.0.0.1:8765/settings#repos"})
    assert same.headers["HX-Redirect"] == "/settings#repos" and same.headers["HX-Refresh"] == "true"
    other = client.post("/settings/git-authors", data={"email": "yo@example.com", "action": "remove"},
                        headers={"HX-Current-URL": "http://127.0.0.1:8765/day/2026-11-12"})
    assert other.headers["HX-Redirect"] == "/settings#repos" and "HX-Refresh" not in other.headers


# --- Parte de horas ----------------------------------------------------------------------------------

def blocks_form(*blocks):
    return {"blocks": json.dumps([dict(zip(("start", "end", "title", "category"), b)) for b in blocks])}


def test_guardar_bloques_rechazados_no_cambia_nada(client):
    con = db.connect()
    ok = client.post(f"/timesheet/day/{DAY}/blocks", data=blocks_form((540, 600, "A", "Documentación")))
    assert ok.status_code == 200 and "Editado a mano" in ok.text
    saved = db.get_summary(con, DAY, web.TIMESHEET_EDIT)["content_md"]

    bad = client.post(f"/timesheet/day/{DAY}/blocks",
                      data=blocks_form((540, 600, "A", "Documentación"), (570, 630, "B", "Documentación")))
    assert bad.status_code == 422 and bad.text == "«B» se solapa con «A»."   # el motivo, para mostrarlo tal cual
    assert db.get_summary(con, DAY, web.TIMESHEET_EDIT)["content_md"] == saved
    # La columna se puede volver a pedir y sigue siendo lo guardado
    again = client.get(f"/timesheet/day/{DAY}")
    assert again.status_code == 200 and 'data-start="540" data-end="600"' in again.text


def test_guardar_dia_con_reuniones_solapadas_y_cortas(client):
    r = client.post(f"/timesheet/day/{DAY}/blocks", data=blocks_form(
        (600, 660, "Daily", "Reunión"), (630, 690, "Cliente", "Reunión"), (720, 725, "Llamada", "Reunión"),
        (725, 780, "Informe", "Documentación")))
    assert r.status_code == 200
    assert 'data-start="720" data-end="725"' in r.text and 'data-start="630" data-end="690"' in r.text


def test_regenerar_conserva_lo_editado_si_claude_falla(client, monkeypatch):
    monkeypatch.setattr(web, "timesheet_inputs", lambda con, day, cfg: {
        "context": {"fecha": DAY}, "commits": [], "meetings": [], "has_work": True})

    def failing(*a, **k):
        raise ClaudeError("límite de uso alcanzado")
    monkeypatch.setattr(web, "generate", failing)
    con = db.connect()
    client.post(f"/timesheet/day/{DAY}/blocks", data=blocks_form((540, 600, "Lo mío", "Documentación")))

    r = client.post(f"/timesheet/day/{DAY}?force=true")
    assert r.status_code == 200 and "límite de uso alcanzado" in r.text and "Lo mío" in r.text
    assert db.get_summary(con, DAY, web.TIMESHEET_EDIT) is not None

    # Con Claude funcionando, regenerar sí descarta lo editado
    def ok(con, cfg, kind, work_date, context, force=False, validate=None):
        text = json.dumps({"tareas": [{"id": "t1", "titulo": "AI Risk - informe", "proyecto": "AI Risk",
                                       "categoria": "Documentación", "commits": [], "minutos": 60}]})
        db.save_summary(con, work_date, kind, text, "h")
        return text, False
    monkeypatch.setattr(web, "generate", ok)
    r = client.post(f"/timesheet/day/{DAY}?force=true")
    assert r.status_code == 200 and "Editado a mano" not in r.text
    assert db.get_summary(con, DAY, web.TIMESHEET_EDIT) is None
