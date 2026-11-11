import json

import pytest

from collectors.gcal import GcalError, events_from_stream, is_attended, meeting_project


def stream(*results):
    lines = [json.dumps({"type": "system", "subtype": "init"})]
    for content, is_error in results:
        lines.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "content": [{"type": "text", "text": content}], "is_error": is_error}]}}))
    lines.append(json.dumps({"type": "result", "result": "hecho"}))
    return "\n".join(lines)


EVENT = {"id": "e1", "summary": "Migración - Revisión kit", "status": "confirmed",
         "start": {"dateTime": "2026-11-10T11:00:00+01:00"}, "end": {"dateTime": "2026-11-10T12:00:00+01:00"},
         "attendees": [{"email": "yo@x", "self": True, "responseStatus": "accepted"}]}


def test_events_from_stream_lee_el_json_en_bruto_y_deduplica():
    page = json.dumps({"summary": "yo@x", "events": [EVENT]})
    s = stream(("tool_reference", False), (page, False), (page, False))
    assert [e["id"] for e in events_from_stream(s)] == ["e1"]


def test_dia_sin_eventos_no_es_error():
    assert events_from_stream(stream((json.dumps({"summary": "yo@x"}), False))) == []


def test_error_del_conector():
    with pytest.raises(GcalError, match="Insufficient scope"):
        events_from_stream(stream(("Insufficient scope", True)))


def test_is_attended():
    assert is_attended(EVENT)
    declined = {**EVENT, "attendees": [{"self": True, "responseStatus": "declined"}]}
    assert not is_attended(declined)
    assert not is_attended({**EVENT, "eventType": "workingLocation"})
    assert not is_attended({**EVENT, "status": "cancelled"})


def test_meeting_project():
    kw = {"Kit migración": ["migración", "kit"], "AI Risk": ["ai risk"]}
    assert meeting_project("Migración - Revisión kit", kw, "1MB") == "Kit migración"
    assert meeting_project("Sprint Review", kw, "1MB") == "1MB"
