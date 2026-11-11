import json

from core.timesheet import build_blocks, fmt, free_intervals, hm, parse_tasks, place_lunch

CFG = {"day_start": "08:30", "day_end": "17:30", "lunch_start": "14:00", "lunch_end": "15:00",
       "min_daily_hours": 8}
CATS = ["Desarrollo de negocio", "Reunión", "Documentación", "Tareas administrativas", "Formación"]


def commit(sha, hhmm, project="AI Risk"):
    return {"sha": sha, "minute": hm(hhmm), "project": project, "subject": f"cambio {sha}"}


def task(id_, commits, minutes=None, category="Desarrollo de negocio"):
    return {"id": id_, "project": "AI Risk", "title": f"AI Risk - {id_}", "category": category,
            "commits": commits, "minutes": minutes}


def spans(blocks):
    return [(fmt(b.start), fmt(b.end), b.title) for b in blocks]


def test_free_intervals():
    assert free_intervals(510, 1050, [(660, 720), (840, 900)]) == [(510, 660), (720, 840), (900, 1050)]


def test_place_lunch_evita_commits_y_reuniones():
    assert place_lunch([], [], hm("14:00"), 60) == (hm("14:00"), hm("15:00"))
    # commit a las 14:20: la comida se mueve al hueco libre más cercano
    s, e = place_lunch([hm("14:20")], [], hm("14:00"), 60)
    assert not (s < hm("14:20") < e)
    assert place_lunch([], [(hm("13:30"), hm("15:00"))], hm("14:00"), 60) == (hm("15:00"), hm("16:00"))


def test_bloques_por_huecos_entre_commits():
    commits = [commit("a", "09:40"), commit("b", "10:10"), commit("c", "11:30"), commit("d", "13:50"),
               commit("e", "16:00"), commit("f", "17:25")]
    tasks = [task("t1", ["a", "b"]), task("t2", ["c", "d"]), task("t3", ["e", "f"])]
    blocks, warnings = build_blocks(CFG, [], commits, tasks)
    assert spans(blocks) == [
        ("08:30", "10:10", "AI Risk - t1"),
        ("10:10", "14:00", "AI Risk - t2"),
        ("15:00", "17:30", "AI Risk - t3"),
    ]
    assert warnings == []


def test_reuniones_fijas_y_tareas_sin_commits_en_huecos():
    commits = [commit("a", "10:00"), commit("b", "12:00")]
    tasks = [task("t1", ["a", "b"]), task("doc", [], minutes=60, category="Documentación")]
    meetings = [{"start": hm("11:00"), "end": hm("11:30"), "title": "Migración - Revisión kit",
                 "project": "Kit migración"}]
    blocks, warnings = build_blocks(CFG, meetings, commits, tasks)
    assert spans(blocks) == [
        ("08:30", "11:00", "AI Risk - t1"),
        ("11:00", "11:30", "Migración - Revisión kit"),
        ("11:30", "12:00", "AI Risk - t1"),
        ("12:00", "14:00", "AI Risk - doc"),
        ("15:00", "17:30", "AI Risk - doc"),
    ]
    assert blocks[1].category == "Reunión"
    assert sum(b.minutes for b in blocks) == 8 * 60


def test_minimo_diez_minutos_y_total_ocho_horas():
    commits = [commit("a", "09:00"), commit("b", "09:05"), commit("c", "12:00")]
    tasks = [task("t1", ["a"]), task("t2", ["b"]), task("t3", ["c"])]
    blocks, _ = build_blocks(CFG, [], commits, tasks)
    assert all(b.minutes >= 10 for b in blocks)
    assert sum(b.minutes for b in blocks) >= 8 * 60


def test_tareas_contiguas_con_el_mismo_titulo_se_fusionan():
    commits = [commit("a", "10:00"), commit("b", "11:00")]
    t1, t2 = task("t1", ["a"]), task("t2", ["b"])
    t2["title"] = t1["title"]
    blocks, _ = build_blocks(CFG, [], commits, [t1, t2])
    assert spans(blocks)[0] == ("08:30", "14:00", "AI Risk - t1")


def test_trabajo_fuera_de_jornada_alarga_el_dia():
    blocks, warnings = build_blocks(CFG, [], [commit("a", "18:40")], [task("t1", ["a"])])
    assert blocks[-1].end == hm("18:40")
    assert sum(b.minutes for b in blocks) > 8 * 60


def test_sin_trabajo_avisa():
    blocks, warnings = build_blocks(CFG, [], [], [])
    assert any("Por definir" in b.title for b in blocks)
    assert warnings


def test_parse_tasks_valida_y_completa():
    commits = [commit("a", "09:00"), commit("b", "10:00"), commit("c", "11:00")]
    text = "```json\n" + json.dumps({"tareas": [
        {"id": "t1", "proyecto": "AI Risk", "titulo": "AI Risk - Uno", "categoria": "Desarrollo de negocio",
         "commits": ["a", "zzz"]},
        {"id": "t2", "proyecto": "AI Risk", "titulo": "AI Risk - Dos", "categoria": "Inventada",
         "commits": ["a", "b"]},
        {"id": "t3", "proyecto": "AI Risk", "titulo": "AI Risk - Informe", "categoria": "Documentación",
         "commits": [], "minutos": 30},
    ]}) + "\n```"
    tasks = parse_tasks(text, commits, CATS)
    assert [(t["id"], t["commits"], t["category"]) for t in tasks] == [
        ("t1", ["a"], "Desarrollo de negocio"),
        ("t2", ["b"], "Desarrollo de negocio"),   # "a" ya estaba asignado; categoría inválida corregida
        ("t3", [], "Documentación"),
        ("c-c", ["c"], "Desarrollo de negocio"),  # commit sin asignar: tarea propia
    ]
