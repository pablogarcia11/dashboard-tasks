from datetime import date

from collectors.notion import (block_date, day_sections, inline_pending, is_pending_marker, parse_day,
                               parse_day_blocks)


def block(id_, type_, text="", children=None, checked=None):
    content = {"rich_text": [{"plain_text": text}] if text else []}
    if type_ == "child_page":
        content = {"title": text}
    if checked is not None:
        content["checked"] = checked
    return {"id": id_, "type": type_, "has_children": bool(children), type_: content, "_children": children or []}


class FakeClient:
    def children(self, block_id):
        return BLOCKS[block_id]["_children"]


BLOCKS = {}


def register(*blocks):
    for b in blocks:
        BLOCKS[b["id"]] = b
        register(*b["_children"])
    return list(blocks)


def test_journal_title_lee_el_titulo_actual():
    from collectors.notion import NotionCollector

    class Pages:
        def request(self, method, path):
            assert (method, path) == ("GET", "/pages/p1")
            return {"properties": {"Name": {"type": "title", "title": [{"plain_text": "Diario renombrado"}]}}}

    c = NotionCollector.__new__(NotionCollector)
    c.page_id, c.client = "p1", Pages()
    assert c.journal_title() == "Diario renombrado"
    c.page_id = None
    assert c.journal_title() is None


def test_parse_day():
    assert parse_day("Martes 10/11/2026") == date(2026, 11, 10)
    assert parse_day("Miércoles 1/2/26") == date(2026, 2, 1)
    assert parse_day("Notas sueltas") is None
    assert parse_day("Lunes 31/02/2026") is None


def test_parse_day_otros_formatos():
    hoy = date(2026, 11, 11)
    assert parse_day("2026-11-10", hoy) == date(2026, 11, 10)
    assert parse_day("10-11-2026", hoy) == date(2026, 11, 10)
    assert parse_day("10.11.2026", hoy) == date(2026, 11, 10)
    assert parse_day("10 de noviembre de 2026", hoy) == date(2026, 11, 10)
    assert parse_day("Martes, 10 nov. 2026", hoy) == date(2026, 11, 10)
    assert parse_day("Martes 10 de noviembre", hoy) == date(2026, 11, 10)        # sin año: este año
    assert parse_day("28 de diciembre", date(2027, 1, 4)) == date(2026, 12, 28)   # sin año, en enero
    assert parse_day("Sprint 3 de AI Risk", hoy) is None


def test_block_date_mencion_de_notion():
    b = {"type": "heading_2", "heading_2": {"rich_text": [
        {"plain_text": "Diario ", "type": "text"},
        {"plain_text": "November 10, 2026", "type": "mention", "mention": {"date": {"start": "2026-11-10"}}}]}}
    assert block_date(b) == date(2026, 11, 10)


def test_is_pending_marker():
    assert is_pending_marker("Pendiente:")
    assert is_pending_marker("  PENDIENTES ")
    assert is_pending_marker("Para mañana:")
    assert not is_pending_marker("Pendiente de revisar el informe")


def test_pendiente_en_la_misma_linea():
    assert inline_pending("Pendiente: probar el flujo completo") == "probar el flujo completo"
    assert inline_pending("Para mañana: revisar el plan") == "revisar el plan"
    assert inline_pending("Pendiente de revisar el informe") is None      # sin dos puntos es una nota
    assert inline_pending("Reunión: revisión del kit") is None
    blocks = register(block("i1", "bulleted_list_item", "Corregí el texto"),
                      block("i2", "bulleted_list_item", "Pendiente: probar el flujo completo"),
                      block("i3", "bulleted_list_item", "Añadí el aviso"))
    rows = [(text, pending) for _, _, text, _, pending in parse_day_blocks(FakeClient(), blocks)]
    assert rows == [("Corregí el texto", False), ("probar el flujo completo", True), ("Añadí el aviso", False)]


def test_parse_day_blocks_proyectos_y_pendientes():
    blocks = register(
        block("h-ai", "heading_3", "AI Risk"),
        block("b1", "bulleted_list_item", "Informe de roles:", [block("b1a", "bulleted_list_item", "Revisé la cola")]),
        block("b-empty", "bulleted_list_item", ""),
        block("p1", "bulleted_list_item", "Pendiente:", [block("p1a", "bulleted_list_item", "Probar flujo completo")]),
        block("b2", "bulleted_list_item", "Limpieza de logs"),
        block("h-kit", "heading_3", "Kit migración"),
        block("p2", "paragraph", "Pendiente"),
        block("k1", "bulleted_list_item", "Revisar plan agentes"),
        block("h-1mb", "heading_3", "1MB"),
        block("m1", "bulleted_list_item", "Sprint Review"),
    )
    out = parse_day_blocks(FakeClient(), blocks)
    rows = [(project, text, sub, pending) for _, project, text, sub, pending in out]
    assert rows == [
        ("AI Risk", "Informe de roles:", ["- Revisé la cola"], False),
        ("AI Risk", "Probar flujo completo", [], True),
        ("AI Risk", "Limpieza de logs", [], False),
        ("Kit migración", "Revisar plan agentes", [], True),   # "Pendiente" sin hijos: marca lo que sigue
        ("1MB", "Sprint Review", [], False),                    # un H3 nuevo cierra el modo pendiente
    ]


def test_parse_day_blocks_desplegables_casillas_y_sin_proyecto():
    blocks = register(
        block("g1", "bulleted_list_item", "Revisé el correo"),                       # sin proyecto
        block("t-ai", "toggle", "AI Risk", [block("t1", "to_do", "Corregir permisos", checked=True),
                                            block("t2", "to_do", "Probar flujo", checked=False)]),
        block("h-pm", "paragraph", "Para mañana:", [block("pm1", "bulleted_list_item", "Llamar a Hugo")]),
    )
    rows = [(project, text, pending) for _, project, text, _, pending in parse_day_blocks(FakeClient(), blocks)]
    assert rows == [
        ("General", "Revisé el correo", False),
        ("AI Risk", "Corregir permisos", False),   # casilla marcada: hecho
        ("AI Risk", "Probar flujo", True),         # casilla sin marcar: pendiente
        ("General", "Llamar a Hugo", True),
    ]


def test_day_sections_formatos_de_dia():
    hoy = date(2026, 11, 11)
    top = register(
        block("d1", "heading_1", "Martes 10/11/2026", [block("x1", "bulleted_list_item", "A")]),   # desplegable
        block("d2", "heading_2", "11 de noviembre de 2026"),                                     # sin desplegar
        block("y1", "bulleted_list_item", "B"),
        block("y2", "heading_3", "AI Risk"),                    # nivel inferior: sigue siendo del día 11
        block("y3", "bulleted_list_item", "C"),
        block("d3", "child_page", "2026-11-09", [block("z1", "bulleted_list_item", "D")]),     # página hija
        block("n1", "paragraph", "Una nota cualquiera sin fecha y bastante más larga de cuarenta letras"),
    )
    secs = day_sections(FakeClient(), top, today=hoy)
    assert [(d.isoformat(), [b["id"] for b in blocks], page) for d, blocks, page in secs] == [
        ("2026-11-10", ["x1"], None),
        ("2026-11-11", ["y1", "y2", "y3"], None),
        ("2026-11-09", ["z1"], "d3"),
    ]
    # Solo se descargan los días que interesan
    secs = day_sections(FakeClient(), top, wanted=lambda d: d.day == 9, today=hoy)
    assert [blocks is None for _, blocks, _ in secs] == [True, True, False]
