import json

import pytest

from collectors.claude_connector import ConnectorError
from collectors.slack import messages_from_stream, own_standups, parse_messages

RAW = (
    "Channel: #equipo-tecnologia-stand-up (C056VQM4E74)\n\n"
    "Ana Pérez <ana@empresa.com>: Buenos días! :saluting_face:\n*Tareas realizadas el último día*\n"
    "• AI Risk\n    ◦ Revisar permisos de roles [2026-11-11 09:18:04 CET]\n\n"
    "Luis <luis@empresa.com>: buenas, sigo con lo mismo [2026-11-11 09:02:21 CET]\n\n"
    "Ana Pérez <ana@empresa.com>: Buenos días! :saluting_face:\n*Tareas realizadas el último día*\n"
    "• Kit migración\n    ◦ Reunión revisión kit [2026-11-10 09:47:42 CET]"
)


def test_parse_messages_con_varias_lineas():
    msgs = parse_messages(RAW)
    assert [(m["name"], m["email"], m["ts"][:10]) for m in msgs] == [
        ("Ana Pérez", "ana@empresa.com", "2026-11-11"),
        ("Luis", "luis@empresa.com", "2026-11-11"),
        ("Ana Pérez", "ana@empresa.com", "2026-11-10"),
    ]
    assert msgs[0]["text"].endswith("◦ Revisar permisos de roles")   # sin la marca de tiempo


RAW_B = (
    "Channel: #equipo-tecnologia-stand-up (C056VQM4E74)\n\n"
    "=== Message from Ana Pérez <ana@empresa.com> (U0B1F4CJ8CA) at 2026-11-11 09:18:04 CET === \n"
    "Message TS: 1794385084.628719\nBuenos días! :saluting_face:\n*Tareas realizadas el último día*\n"
    "• AI Risk\n    ◦ Revisar permisos de roles\n\n"
    "=== Message from Luis <luis@empresa.com> (U02) at 2026-11-11 09:02:21 CET === \n"
    "Message TS: 1794384141.1\nbuenas, sigo con lo mismo\n"
)


def test_parse_messages_formato_con_cabeceras():
    msgs = parse_messages(RAW_B)
    assert [(m["name"], m["email"], m["ts"]) for m in msgs] == [
        ("Ana Pérez", "ana@empresa.com", "2026-11-11 09:18:04 CET"),
        ("Luis", "luis@empresa.com", "2026-11-11 09:02:21 CET"),
    ]
    assert msgs[0]["text"].startswith("Buenos días!") and "Message TS" not in msgs[0]["text"]
    assert own_standups(msgs, {"ana@empresa.com"}) == [msgs[0]["text"]]


def test_own_standups_solo_los_suyos_y_recientes_primero():
    msgs = parse_messages(RAW)
    examples = own_standups(msgs, {"ana@empresa.com"}, n=1)
    assert len(examples) == 1 and "Revisar permisos" in examples[0]
    assert own_standups(msgs, {"otra@empresa.com"}) == []


def test_messages_from_stream():
    line = {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": [{"type": "text", "text": json.dumps({"messages": RAW})}]}]}}
    assert len(messages_from_stream(json.dumps(line))) == 3
    with pytest.raises(ConnectorError):
        messages_from_stream("")
