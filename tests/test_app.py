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
