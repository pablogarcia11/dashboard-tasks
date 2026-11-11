from datetime import date

from collectors.notion import is_pending_marker, parse_day, parse_day_blocks


def block(id_, type_, text="", children=None):
    return {"id": id_, "type": type_, "has_children": bool(children),
            type_: {"rich_text": [{"plain_text": text}] if text else []}, "_children": children or []}


class FakeClient:
    def children(self, block_id):
        return BLOCKS[block_id]["_children"]


BLOCKS = {}


def register(*blocks):
    for b in blocks:
        BLOCKS[b["id"]] = b
        register(*b["_children"])
    return list(blocks)


def test_parse_day():
    assert parse_day("Martes 10/11/2026") == date(2026, 11, 10)
    assert parse_day("Miércoles 1/2/26") == date(2026, 2, 1)
    assert parse_day("Notas sueltas") is None
    assert parse_day("Lunes 31/02/2026") is None


def test_is_pending_marker():
    assert is_pending_marker("Pendiente:")
    assert is_pending_marker("  PENDIENTES ")
    assert not is_pending_marker("Pendiente de revisar el informe")


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
