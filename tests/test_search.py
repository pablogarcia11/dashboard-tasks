from collectors.base import Activity
from core import db
from core.search import fold, highlight, search


def item(kind, day, ext, title, body="", repo="", source=None):
    source = source or {"commit": "git", "meeting": "gcal"}.get(kind, "notion")
    return Activity(source=source, kind=kind, external_id=ext, ts=f"{day}T10:00:00+01:00", work_date=day,
                    title=title, body=body, project="Kit migración", extra={"repo": repo} if repo else {})


def test_fold_quita_tildes_sin_cambiar_la_longitud():
    assert fold("Migración ÁÉ ñ") == "migracion ae n"
    assert len(fold("Migración")) == len("Migración")


def test_search_sin_tildes_todas_las_palabras_y_mas_recientes_primero(tmp_path):
    con = db.connect(tmp_path / "t.db")
    db.upsert_activities(con, [
        item("commit", "2026-11-03", "c1", "fix: role permissions", repo="airisk-api"),
        item("note", "2026-11-10", "n1", "Revisé los permisos de roles", body="- Soporte e incidencias"),
        item("meeting", "2026-11-05", "m1", "Revisión del plan de migración"),
        item("task", "2026-11-12", "t1", "Permisos de roles (tarea de Notion: no se busca)"),
        item("commit", "2026-11-04", "c2", "feat: hide panel", repo="oculto"),
    ])
    db.set_repo_setting(con, "oculto", "visible", False)
    hits, total = search(con, "PERMISOS roles")
    assert [h["external_id"] for h in hits] == ["n1"] and total == 1
    assert [h["external_id"] for h in search(con, "revision plan")[0]] == ["m1"]        # sin tilde
    assert [h["external_id"] for h in search(con, "migracion")[0]] == ["n1", "m1", "c1"]  # también por proyecto; el oculto no sale
    assert [h["external_id"] for h in search(con, "airisk")[0]] == ["c1"]               # por repo
    assert search(con, "   ") == ([], 0)


def test_highlight_marca_lo_que_coincide_en_el_texto_original():
    assert highlight("Revisión de roles", "revision ROL") == [("Revisión", True), (" de ", False), ("rol", True), ("es", False)]
    assert highlight("nada", "x") == [("nada", False)]
