import sqlite3

from core import db, settings


def connect(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_los_ajustes_guardados_mandan_sobre_config(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {"id": "user-123"})
    con = connect(tmp_path)
    cfg = {"git": {"repos_root": "C:/viejo", "scan_depth": 3}, "notion": {"tasks_database_id": "db"}}
    settings.set_value(con, settings.REPOS_ROOT, "D:/mis-repos")
    settings.set_value(con, settings.JOURNAL_PAGE_ID, "page-1")
    settings.set_value(con, settings.JOURNAL_PAGE_TITLE, "Mi diario")
    out = settings.effective_config(cfg, con)
    assert out["git"] == {"repos_root": "D:/mis-repos", "scan_depth": 3}
    assert out["notion"] == {"tasks_database_id": "db", "journal_page_id": "page-1",
                             "journal_page_title": "Mi diario", "user_id": "user-123"}
    assert cfg["git"]["repos_root"] == "C:/viejo"   # no modifica la config original


def test_sin_ajustes_ni_conexion(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {})
    out = settings.effective_config({}, connect(tmp_path))
    assert out == {"git": {}, "notion": {}}


def test_borrar_un_ajuste(tmp_path):
    con = connect(tmp_path)
    settings.set_value(con, settings.REPOS_ROOT, "X")
    settings.set_value(con, settings.REPOS_ROOT, None)
    assert settings.get_all(con) == {}
