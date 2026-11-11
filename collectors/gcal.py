"""Colector de Google Calendar a través del conector de la cuenta de Claude.

`claude -p` (Haiku) solo puede usar `list_events`. Los eventos se leen del tool_result en bruto
del stream (JSON tal cual lo devuelve Google), nunca de la respuesta redactada por Claude.
"""
import json
from datetime import date

from collectors.base import Activity
from collectors.claude_connector import ConnectorError, result_text, run_connector, tool_results
from core.dates import day_bounds, to_work_date

LIST_EVENTS = "mcp__claude_ai_Google_Calendar__list_events"
SKIP_TYPES = {"workingLocation", "outOfOffice", "birthday"}


class GcalError(RuntimeError):
    pass


def events_from_stream(stream: str) -> list[dict]:
    """Eventos de todas las llamadas a list_events del stream (sin duplicados)."""
    events, errors, calls = {}, [], 0
    for r in tool_results(stream):
        text = result_text(r)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            if r.get("is_error"):
                errors.append(text[:300])
            continue
        if not isinstance(data, dict) or "summary" not in data and "events" not in data:
            continue
        calls += 1
        for e in data.get("events", []):
            events[e["id"]] = e
    if not calls:
        raise GcalError("; ".join(errors) or "Calendar no devolvió eventos (¿conector desconectado?)")
    return list(events.values())


def is_attended(e: dict) -> bool:
    if e.get("status") == "cancelled" or e.get("eventType") in SKIP_TYPES:
        return False
    me = next((a for a in e.get("attendees", []) if a.get("self")), None)
    return not me or me.get("responseStatus") != "declined"


def meeting_project(title: str, keywords: dict, default: str) -> str:
    t = title.lower()
    for project, words in keywords.items():
        if any(w.lower() in t for w in words):
            return project
    return default


class GcalCollector:
    source = "gcal"

    def __init__(self, config: dict):
        self.tz = config["user"]["timezone"]
        self.claude = config["claude"]
        self.keywords = config.get("meeting_keywords", {})
        self.default_project = config.get("company_meetings_project", "1MB")

    def fetch(self, start: date, end: date) -> list[dict]:
        since, until = day_bounds(start, self.tz)[0], day_bounds(end, self.tz)[1]
        prompt = (f"Llama a la herramienta list_events del calendario principal con timeMin={since.isoformat()} "
                  f"y timeMax={until.isoformat()} (zona {self.tz}), con el máximo de resultados por página. "
                  "Si la respuesta trae nextPageToken, vuelve a llamar con él hasta tenerlos todos. "
                  "No hagas nada más y responde solo 'hecho'.")
        try:
            stream = run_connector(prompt, [LIST_EVENTS], self.claude)
        except ConnectorError as e:
            raise GcalError(f"Calendar: {e}")
        return events_from_stream(stream)

    def collect(self, start: date, end: date) -> list[Activity]:
        items = []
        for e in self.fetch(start, end):
            st, en = e.get("start", {}), e.get("end", {})
            if "dateTime" not in st or not is_attended(e):  # eventos de día completo fuera
                continue
            title = e.get("summary", "(sin título)")
            items.append(Activity(
                source="gcal", kind="meeting", external_id=e["id"], ts=st["dateTime"],
                work_date=to_work_date(st["dateTime"], self.tz).isoformat(), title=title,
                url=e.get("htmlLink", ""), project=meeting_project(title, self.keywords, self.default_project),
                extra={"start": st["dateTime"], "end": en.get("dateTime", st["dateTime"]),
                       "attendees": len(e.get("attendees", [])), "meet": e.get("conferenceUrl", "")},
            ))
        return items
