import sqlite3

from core import db, settings


def connect(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_los_ajustes_guardados_mandan_sobre_config(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {"id": "user-123"})
    con = connect(tmp_path)
    cfg = {"git": {"repos_root": "C:/viejo", "scan_depth": 3}, "notion": {"tasks_database_id": "db"}}
    settings.set_repos_roots(con, ["D:/mis-repos", "E:/otros"])
    settings.set_value(con, settings.JOURNAL_PAGE_ID, "page-1")
    settings.set_value(con, settings.JOURNAL_PAGE_TITLE, "Mi diario")
    out = settings.effective_config(cfg, con)
    assert out["git"] == {"repos_root": "C:/viejo", "repos_roots": ["D:/mis-repos", "E:/otros"], "scan_depth": 3}
    assert out["notion"] == {"tasks_database_id": "db", "journal_page_id": "page-1",
                             "journal_page_title": "Mi diario", "user_id": "user-123"}
    assert cfg["git"]["repos_root"] == "C:/viejo"   # no modifica la config original


def test_sin_ajustes_ni_conexion(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {})
    out = settings.effective_config({}, connect(tmp_path))
    assert out == {"git": {}, "notion": {}, "user": {}}


def test_emails_de_autor_manuales(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {})
    con = connect(tmp_path)
    settings.set_extra_authors(con, ["b@x.com", "a@x.com", "a@x.com"])
    assert settings.extra_authors(con) == ["a@x.com", "b@x.com"]
    out = settings.effective_config({"user": {"git_authors": ["c@x.com"]}}, con)
    assert out["user"]["git_authors"] == ["c@x.com", "a@x.com", "b@x.com"]
    settings.set_extra_authors(con, [])
    assert settings.extra_authors(con) == []


def test_delete_kinds_borra_solo_esas_notas(tmp_path):
    from collectors.base import Activity
    con = connect(tmp_path)
    acts = [Activity("notion", kind, f"id-{kind}", "2026-11-10T00:00:00+01:00", "2026-11-10")
            for kind in ("note", "task_plan", "task")] + [
            Activity("git", "commit", "sha", "2026-11-10T10:00:00+01:00", "2026-11-10")]
    db.upsert_activities(con, acts)
    db.delete_kinds(con, "notion", ["note", "task_plan"])
    left = sorted((a["source"], a["kind"]) for a in db.activities(con, "2026-11-10", "2026-11-10"))
    assert left == [("git", "commit"), ("notion", "task")]


def test_horario_propio_del_parte_de_horas(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notion_owner", lambda: {})
    con = connect(tmp_path)
    company = {"timesheet": {"day_start": "08:30", "day_end": "17:30", "min_daily_hours": 8, "categories": ["X"]}}
    settings.set_value(con, "timesheet.day_end", "15:00")
    settings.set_value(con, "timesheet.min_daily_hours", "6")
    ts = settings.effective_config(company, con)["timesheet"]
    assert ts == {"day_start": "08:30", "day_end": "15:00", "min_daily_hours": 6.0, "categories": ["X"]}


def test_varias_carpetas_de_repos_y_migracion_de_la_antigua(tmp_path):
    con = connect(tmp_path)
    settings.set_value(con, settings.REPOS_ROOT, "C:/repos")        # guardada cuando solo había una
    assert settings.repos_roots(con) == ["C:/repos"]
    settings.set_repos_roots(con, ["C:/repos", "D:/otros", "C:/repos"])
    assert settings.repos_roots(con) == ["C:/repos", "D:/otros"]
    assert settings.REPOS_ROOT not in settings.get_all(con)
    settings.set_repos_roots(con, [])
    assert settings.repos_roots(con) == [] and settings.get_all(con) == {}


def test_borrar_actividad_de_repos_quitados(tmp_path):
    from collectors.base import Activity
    con = connect(tmp_path)
    db.upsert_activities(con, [
        Activity("git", "commit", sha, "2026-11-10T10:00:00+01:00", "2026-11-10", extra={"repo": repo})
        for sha, repo in (("a", "quitado"), ("b", "sigue"))] + [
        Activity("notion", "note", "n", "2026-11-10T00:00:00+01:00", "2026-11-10", extra={"repo": "quitado"})])
    db.delete_git_repos(con, ["quitado"])
    left = sorted(a["external_id"] for a in db.activities(con, "2026-11-10", "2026-11-10"))
    assert left == ["b", "n"]


def test_borrar_un_ajuste(tmp_path):
    con = connect(tmp_path)
    settings.set_value(con, settings.REPOS_ROOT, "X")
    settings.set_value(con, settings.REPOS_ROOT, None)
    assert settings.get_all(con) == {}
