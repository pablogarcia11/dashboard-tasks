from datetime import date

from collectors.base import Activity
from core import db
from core.views import standup_markdown, visible_git, written_journal_md


def test_written_journal_md_conserva_proyectos_subvinetas_y_pendientes(tmp_path):
    con = db.connect(tmp_path / "t.db")
    ts = "2026-11-10T00:00:00+01:00"
    db.upsert_activities(con, [
        Activity("notion", "note", "n1", ts, "2026-11-10", title="Informe de roles:", project="AI Risk",
                 body="- Revisé la cola de aprobaciones.\n  - Solo Alta dirección."),
        Activity("notion", "task_plan", "p1", ts, "2026-11-10", title="Probar flujo completo", project="AI Risk"),
        Activity("notion", "note", "n2", ts, "2026-11-10", title="Reunión del kit.", project="Kit migración"),
    ])
    assert written_journal_md(con, date(2026, 11, 10)) == (
        "### AI Risk\n- Informe de roles:\n  - Revisé la cola de aprobaciones.\n    - Solo Alta dirección.\n"
        "- Pendiente:\n  - Probar flujo completo\n### Kit migración\n- Reunión del kit."
    )
    assert written_journal_md(con, date(2026, 11, 11)) == ""


def test_las_notas_salen_en_el_orden_del_diario(tmp_path):
    con = db.connect(tmp_path / "t.db")
    ts = "2026-11-10T00:00:00+01:00"
    titles = [f"Nota {i}" for i in range(12)]
    db.upsert_activities(con, [Activity("notion", "note", f"zz-{9 - i % 10}-{i}", ts, "2026-11-10",
                                        title=t, project="P") for i, t in enumerate(titles)])
    assert [a["title"] for a in db.activities(con, "2026-11-10", "2026-11-10")] == titles


def act(source, kind, repo=""):
    return {"source": source, "kind": kind, "extra": {"repo": repo} if repo else {}}


def test_visible_git_oculta_repo_entero_o_solo_wip():
    items = [act("git", "commit", "airisk-api"), act("git", "wip", "airisk-api"),
             act("git", "commit", "millie/apiREST"), act("git", "wip", "millie/apiREST"),
             act("git", "wip", "ibh/ibh-api"), act("notion", "note")]
    settings = {"millie/apiREST": {"visible": False, "show_wip": True},
                "ibh/ibh-api": {"visible": True, "show_wip": False}}
    kept = [(a["kind"], a["extra"].get("repo")) for a in visible_git(items, settings)]
    assert kept == [("commit", "airisk-api"), ("wip", "airisk-api"), ("note", None)]


def test_standup_markdown_pone_linea_en_blanco_tras_cada_lista():
    md = ("Buenos días!\n**Ayer**\n- AI Risk\n    - Corregir permisos\n**Hoy**\n- 1MB\n    - Sprint review\n")
    assert standup_markdown(md) == ("Buenos días!\n**Ayer**\n- AI Risk\n    - Corregir permisos\n\n**Hoy**\n"
                                  "- 1MB\n    - Sprint review\n")
    ya_separado = "- a\n\n**Hoy**\n- b"
    assert standup_markdown(ya_separado) == ya_separado   # no duplica líneas en blanco


def test_standup_markdown_traduce_restos_del_formato_de_slack():
    slack = "Hola :wave:\n*Ayer*\n• AI Risk\n    ◦ Subir **ya negrita** y 2*3*4\n◦ Sin sangría\n*Hoy*"
    assert standup_markdown(slack) == ("Hola :wave:\n**Ayer**\n- AI Risk\n    - Subir **ya negrita** y 2*3*4\n"
                                       "    - Sin sangría\n\n**Hoy**")
